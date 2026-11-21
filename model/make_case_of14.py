"""OpenFOAM-14 case generator for the waste heat boiler (WHB).

Port of make_case.py (OpenFOAM-12), same physics and arguments. Changes for OF-14:
  - porosityForce coefficients sub-dictionary: porosityForceCoeffs -> porosityForce
  - externalTemperature no longer reads thicknessLayers/kappaLayers (silently ignored):
    deposits are folded into h = 1/(1/h_wall + R), identical to the OF-12 series sum
  - surfaceFieldValue: "select sampledSurface; sampledSurfaceDict {..}" -> "sampledSurface {..}"
  - topoSet (deprecated) -> createZones (system/createZonesDict)

python model/make_case.py <case_dir> [--res 0.3] [--ny 12] [--np 4] [options, see --help]

Mesh: blockMesh of the side contour (x-z) extruded across the width y; the hoppers narrow
towards the bottom across the width as well. Bundles are porous cellZones (bundle edges
coincide with cell faces) with DarcyForchheimer resistance and heat extraction via
heatTransfer (htc from the Zukauskas correlation as a function of velocity, plus radiation).
"""
import argparse
import math
import shutil
import sys
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import geometry as g

ap = argparse.ArgumentParser()
ap.add_argument("case")
ap.add_argument("--res", type=float, default=0.3, help="cell size in the side section, m")
ap.add_argument("--ny", type=int, default=12, help="cells across the width")
ap.add_argument("--np", type=int, default=4, help="number of processes")
ap.add_argument("--iters", type=int, default=3000)
ap.add_argument("--bundle_R", type=float, default=0.0,
                help="thermal resistance of tube deposits in the bundles, m2K/W")
ap.add_argument("--dust_frac", type=float, default=0.4,
                help="share of the 50 t/h of ash that passes the first hopper into the bundles")
ap.add_argument("--hopper_fill", type=float, default=0.10, help="ash fill of the hoppers, volume fraction")
ap.add_argument("--hopper2_fill", type=float, default=None, help="ash fill of the right hopper (default = hopper_fill)")
ap.add_argument("--skirts", default="",
                help="vertical skirts from the bundle bottoms downwards, 'place:depth_m,...'; places: evap (after the evaporator), "
                     "sh1, sh2, sh3 (after that bundle), sh4 (between SH4 and the wall), sh4end (right behind SH4, down to the hopper wall)")
ap.add_argument("--extra_water_t_h", type=float, default=14.0, help="unmetered water into the furnace, t/h (added to gas H2O)")
ap.add_argument("--extra_air_nm3_h", type=float, default=10000.0, help="unmetered air (burners), Nm3/h")
ap.add_argument("--extra_n2_nm3_h", type=float, default=2000.0, help="nitrogen from seals, Nm3/h")
ap.add_argument("--o2", type=float, default=None, help="bring wet O2 up to this fraction by extra air (default: as it comes out)")
ap.add_argument("--steam_kg_s", type=float, default=15.9, help="steam through the superheaters before sprays, kg/s (DCS: 16.17 at outlet)")
ap.add_argument("--spray_kg_s", type=float, default=0.25, help="spray water into steam (total), kg/s; applied before SH1 (IIIb)")
ap.add_argument("--spray_h", type=float, default=1087.0, help="spray water enthalpy, kJ/kg (1087 = drum water at 250 C)")
ap.add_argument("--duct_R", type=float, default=None,
                help="deposits on the duct walls (inclined + vertical duct), m2K/W; default = wall_R")
ap.add_argument("--wall_R", type=float, default=0.0,
                help="thermal resistance of deposits on the membrane walls, m2K/W (0 = clean)")
ap.add_argument("--bundle_fac", type=float, default=1.0,
                help="multiplier on the gas-side htc in the bundles (fouling and uncertainty)")
ap.add_argument("--ta", default="", help="steam temperatures SH1,SH2,SH3,SH4, C (default 413,361,312,270)")
ap.add_argument("--relax_p", type=float, default=0.3, help="under-relaxation of p_rgh")
ap.add_argument("--relax_u", type=float, default=0.5, help="under-relaxation of U, h, k, epsilon")
ap.add_argument("--lts", action="store_true", help="local time stepping (pseudo-transient) instead of SIMPLE")
ap.add_argument("--lts_co", type=float, default=1.0, help="max Courant number for --lts")
ap.add_argument("--absorb", type=float, default=None,
                help="gas+dust absorption coefficient for P1, 1/m (default: from dust load; 0 = no radiation)")
ap.add_argument("--scenario", choices=["A", "B"], default="A",
                help="A: correlations (Gaddis, Zukauskas); B: transient tube-bank CFD (discarded, docs/CALIBRATION.md)")
a = ap.parse_args()
R = a.res

HDR = """/*--------------------------------*- C++ -*----------------------------------*\\
  =========                 |
  \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox
   \\\\    /   O peration     | Website:  https://openfoam.org
    \\\\  /    A nd           | Version:  14
     \\\\/     M anipulation  |
\\*---------------------------------------------------------------------------*/
FoamFile
{{
    format      ascii;
    class       {cls};
    object      {obj};
}}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

"""

case = Path(a.case)
if case.exists():
    shutil.rmtree(case)
for d in ("0", "constant", "system"):
    (case / d).mkdir(parents=True)


def write(rel, body, cls="dictionary"):
    obj = Path(rel).name
    (case / rel).write_text(HDR.format(cls=cls, obj=obj) + body + "\n", encoding="utf-8")


def n_cells(length, res=R):
    return max(1, round(length / res))


# ---------------------------------------------------------------- operating point
P_ABS = 112000 - 200             # at the OUTLET, Pa abs: inlet 1.120 bar minus ~2 mbar estimated drop
# Composition (user, top of CFB): N2 6796, CO2 1433.1, H2O 1667, O2 253.42 kmol/h (O2 2.5 %).
# Plus unmetered burner air, seal N2 and furnace water; optional --o2 adds air to reach a given O2.
_kmol = {"N2": 6796.0, "CO2": 1433.1, "H2O": 1667.0, "O2": 253.42}
_kmol["H2O"] += a.extra_water_t_h * 1000 / 18.015
_air = a.extra_air_nm3_h / 22.414
_kmol["O2"] += 0.21 * _air
_kmol["N2"] += 0.79 * _air + a.extra_n2_nm3_h / 22.414
_tot = sum(_kmol.values())
_add_o2 = max(0.0, (a.o2 * _tot - _kmol["O2"]) / (1 - 4.76 * a.o2)) if a.o2 else 0.0
_kmol["O2"] += _add_o2
_kmol["N2"] += 3.76 * _add_o2
_MW = {"N2": 28.013, "CO2": 44.01, "H2O": 18.015, "O2": 31.999}
_CP = {"N2": 1.12, "CO2": 1.21, "H2O": 2.21, "O2": 1.06}      # kJ/(kg K) at ~650 C
KMOL_H = sum(_kmol.values())
X_CO2, X_H2O = _kmol["CO2"] / KMOL_H, _kmol["H2O"] / KMOL_H
_mass = {k: _kmol[k] * _MW[k] for k in _kmol}
M_GAS = round(sum(_mass.values()) / KMOL_H, 3)  # kg/kmol
MDOT = KMOL_H * M_GAS / 3600    # kg/s
T_IN = 750 + 273.15            # mixed gas from the cyclones (DCS: 754 and 746 C)
T_WALL = 250 + 273.15
CP_GAS = round(1000 * sum(_mass[k] * _CP[k] for k in _mass) / sum(_mass.values()), 1)
MU = 3.7e-5
PR = 0.72
K_GAS = 0.064                   # gas conductivity at ~650 C, W/(m K)

# Dust passing through the bundles: share of 50 t/h (user), particles ~20 um (assumption)
DUST_KG_H = a.dust_frac * 50000
D_DUST = 20e-6
RHO_DUST = 2500.0
CP_DUST = 850.0
CP = CP_GAS + DUST_KG_H / 3600 / MDOT * CP_DUST     # heat capacity of gas + dust per kg of gas
if a.absorb is None:
    _c = DUST_KG_H / 3600 / (MDOT / (P_ABS * M_GAS / (8314 * 923.15)))   # kg/m3 at ~650 C
    a.absorb = round(0.16 + 1.5 * _c / (RHO_DUST * D_DUST), 3)        # gas ~0.16 1/m + dust
# Expected mean gas temperature in each bundle, C (for radiation; refine from results)
TG_RAD = {"EVAP": 740, "SH1": 700, "SH2": 670, "SH3": 640, "SH4": 610}

# "Ambient" temperature of the bundles: steam (counterflow 250 -> 440 C, equal steps); updated by coupling
TA = {"EVAP": 250, "SH4": 270, "SH3": 312, "SH2": 361, "SH1": 413}
if a.ta:
    for _n, _t in zip(("SH1", "SH2", "SH3", "SH4"), a.ta.split(",")):
        TA[_n] = float(_t)
K_ASH = 0.2           # deposit conductivity, W/(m K); layer thickness = R * K_ASH

# ---------------------------------------------------------------- sections along x
# Each section: (length, number of cells). Bundle edges = section edges.
def sections(x_from, x_to, bundles):
    secs, x = [], x_from
    for name, b0, b1 in bundles:
        if b0 > x + 1e-9:
            secs.append((b0 - x, n_cells(b0 - x)))
        nb = max(1, round((b1 - b0) / R))
        secs.append((b1 - b0, nb))
        x = b1
    if x_to > x + 1e-9:
        secs.append((x_to - x, n_cells(x_to - x)))
    return secs


def grading_spec(secs):
    tot_l = sum(s[0] for s in secs)
    tot_n = sum(s[1] for s in secs)
    if len(secs) == 1:
        return tot_n, "1"
    parts = " ".join(f"({l / tot_l:.10g} {n / tot_n:.10g} 1)" for l, n in secs)
    return tot_n, f"({parts})"


evap = [b for b in g.BUNDLES if b[0] == "EVAP"]
shs = [b for b in g.BUNDLES if b[0] != "EVAP"]
# An evaporator thinner than a cell still gets one cell
sec_left = sections(g.SHAFT, g.X_APEX, evap)
sec_right = sections(g.X_APEX, g.X_RIGHT, shs)

ns = n_cells(g.SHAFT)                       # across the vertical duct
nz_b = n_cells(g.BUNDLE_DEPTH)              # height of the bundle zone
nz_h = n_cells(g.Z_HOP)                     # depth of the hoppers
lx_incl = math.dist(g.BEND_INNER, g.INLET_INNER)
n_incl = n_cells(lx_incl)
n_shaft = n_cells(g.BEND_INNER[1] - g.Z_CEIL)
n_out = n_cells(g.X_OUT - g.X_RIGHT)
n_ext = n_cells(g.OUTLET_EXT, R)

# ---------------------------------------------------------------- blocks (x, z)
Zc, Zh = g.Z_CEIL, g.Z_HOP
xo_end = g.X_OUT + g.OUTLET_EXT
split1 = g.HOP1_BOT[0] + (g.HOP1_BOT[1] - g.HOP1_BOT[0]) * g.SHAFT / g.X_APEX


def hopper_fill_z(frac):
    """Height of an ash layer filling the fraction frac of hopper 1 (section area ~ Lx(z)*Wy(z))."""
    def area(z):
        lx = (g.HOP1_BOT[1] - g.HOP1_BOT[0]) + (g.X_APEX - (g.HOP1_BOT[1] - g.HOP1_BOT[0])) * z / Zh
        wy = g.W_HOP_BOT + (g.W - g.W_HOP_BOT) * z / Zh
        return lx * wy
    zs = [Zh * i / 2000 for i in range(2001)]
    vol = [0.0]
    for z0, z1 in zip(zs, zs[1:]):
        vol.append(vol[-1] + 0.5 * (area(z0) + area(z1)) * (z1 - z0))
    for z, v in zip(zs, vol):
        if v >= frac * vol[-1]:
            return z
    return 0.0


Z_ASH = hopper_fill_z(a.hopper_fill) if a.hopper_fill > 0 else 0.0
_f2 = a.hopper_fill if a.hopper2_fill is None else a.hopper2_fill
Z_ASH2 = hopper_fill_z(_f2) if _f2 > 0 else 0.0     # both hoppers have nearly the same shape
nz_h = n_cells(Zh - Z_ASH)
nz_h2 = n_cells(Zh - Z_ASH2)


def at_z(p_low, p_high, z):
    """Point on segment p_low -> p_high at height z."""
    t = (z - p_low[1]) / (p_high[1] - p_low[1])
    return (p_low[0] + t * (p_high[0] - p_low[0]), z)


def hop(q):
    """Hopper block cut at the bottom by the ash level."""
    p0, p1, p2, p3 = q
    return hop_z(q, Z_ASH)


def hop_z(q, z):
    p0, p1, p2, p3 = q
    return (at_z(p0, p3, z), at_z(p1, p2, z), p2, p3)

blocks = [
    # name, (p0, p1, p2, p3) anticlockwise in (x, z); (n1, grading1), (n2, grading2)
    ("incl", (g.BEND_INNER, g.BEND_OUTER, g.INLET_OUTER, g.INLET_INNER), (ns, "1"), (n_incl, "1")),
    ("shaft", ((0, Zc), (g.SHAFT, Zc), g.BEND_OUTER, g.BEND_INNER), (ns, "1"), (n_shaft, "1")),
    ("col", ((0, Zh), (g.SHAFT, Zh), (g.SHAFT, Zc), (0, Zc)), (ns, "1"), (nz_b, "1")),
    ("left", ((g.SHAFT, Zh), (g.X_APEX, Zh), (g.X_APEX, Zc), (g.SHAFT, Zc)), grading_spec(sec_left), (nz_b, "1")),
    ("right", ((g.X_APEX, Zh), (g.X_RIGHT, Zh), (g.X_RIGHT, Zc), (g.X_APEX, Zc)), grading_spec(sec_right), (nz_b, "1")),
    ("trans", ((g.X_RIGHT, Zh), (g.X_OUT, g.Z_OUT_BOT), (g.X_OUT, g.Z_OUT_TOP), (g.X_RIGHT, Zc)), (n_out, "1"), (nz_b, "1")),
    ("ext", ((g.X_OUT, g.Z_OUT_BOT), (xo_end, g.Z_OUT_BOT), (xo_end, g.Z_OUT_TOP), (g.X_OUT, g.Z_OUT_TOP)), (n_ext, "1"), (nz_b, "1")),
    ("hop1a", hop(((g.HOP1_BOT[0], 0), (split1, 0), (g.SHAFT, Zh), (0, Zh))), (ns, "1"), (nz_h, "1")),
    ("hop1b", hop(((split1, 0), (g.HOP1_BOT[1], 0), (g.X_APEX, Zh), (g.SHAFT, Zh))), grading_spec(sec_left), (nz_h, "1")),
    ("hop2", hop_z(((g.HOP2_BOT[0], 0), (g.HOP2_BOT[1], 0), (g.X_RIGHT, Zh), (g.X_APEX, Zh)), Z_ASH2), grading_spec(sec_right), (nz_h2, "1")),
]


def half_w(z):
    if z >= Zh - 1e-9:
        return g.W / 2
    return (g.W_HOP_BOT + (g.W - g.W_HOP_BOT) * z / Zh) / 2


verts, vid = [], {}


def vertex(x, y, z):
    key = (round(x, 6), round(y, 6), round(z, 6))
    if key not in vid:
        vid[key] = len(verts)
        verts.append(key)
    return vid[key]


hexes = []
faces_inlet, faces_outlet, faces_ash, faces_duct = [], [], [], []
DUCT_SIDES = {"incl": (1, 3), "shaft": (1, 3), "col": (3,)}
for name, quad, (n1, g1), (n2, g2) in blocks:
    front = [vertex(x, +half_w(z), z) for x, z in quad]
    back = [vertex(x, -half_w(z), z) for x, z in quad]
    # right-handedness check: (p1-p0) x (p3-p0) . (back0-front0) > 0
    p = [verts[i] for i in front]
    q = verts[back[0]]
    e1 = [p[1][k] - p[0][k] for k in range(3)]
    e2 = [p[3][k] - p[0][k] for k in range(3)]
    e3 = [q[k] - p[0][k] for k in range(3)]
    cr = [e1[1] * e2[2] - e1[2] * e2[1], e1[2] * e2[0] - e1[0] * e2[2], e1[0] * e2[1] - e1[1] * e2[0]]
    assert sum(cr[k] * e3[k] for k in range(3)) > 0, name
    hexes.append(f"    hex ({' '.join(map(str, front + back))}) {name} ({n1} {n2} {a.ny})\n"
                 f"        simpleGrading ({g1} {g2} 1)")
    if name == "incl":   # face p2-p3 (inlet)
        faces_inlet.append((front[3], front[2], back[2], back[3]))
    if name == "ext":    # face p1-p2 (outlet)
        faces_outlet.append((front[1], front[2], back[2], back[1]))
    if name in DUCT_SIDES:   # duct walls: side faces y = +-W/2 and contour walls
        faces_duct.append(tuple(front))
        faces_duct.append((back[0], back[3], back[2], back[1]))
        for s_ in DUCT_SIDES[name]:
            faces_duct.append((front[s_], back[s_], back[(s_ + 1) % 4], front[(s_ + 1) % 4]))
    if name.startswith("hop") and Z_ASH > 0:   # face p0-p1 (ash surface)
        faces_ash.append((front[0], back[0], back[1], front[1]))

vtxt = "\n".join(f"    ({x:.15g} {y:.15g} {z:.15g})" for x, y, z in verts)
ftxt = lambda fl: "\n".join(f"            ({' '.join(map(str, f))})" for f in fl)
write("system/blockMeshDict", f"""convertToMeters 1;

vertices
(
{vtxt}
);

blocks
(
{chr(10).join(hexes)}
);

boundary
(
    inlet
    {{
        type patch;
        faces
        (
{ftxt(faces_inlet)}
        );
    }}
    outlet
    {{
        type patch;
        faces
        (
{ftxt(faces_outlet)}
        );
    }}
    ductWalls
    {{
        type wall;
        faces
        (
{ftxt(faces_duct)}
        );
    }}
    ash
    {{
        type wall;
        faces
        (
{ftxt(faces_ash)}
        );
    }}
);

defaultPatch
{{
    name walls;
    type wall;
}}
""")

# ---------------------------------------------------------------- bundle zones
eps = 1e-3
zones = []
for name, x0, x1 in g.BUNDLES:
    zones.append(f"""{name}
{{
    type        box;
    zoneType    cell;
    box         ({x0 + eps:.6f} -100 {Zh:.6f}) ({x1 - eps:.6f} 100 {Zc:.6f});
}}
""")
# skirts: a column of cells across the full width from the bundle bottoms downwards
_bx = {n: (x0, x1) for n, x0, x1 in g.BUNDLES}
SKIRT_X = {"evap": (_bx["EVAP"][1] + _bx["SH1"][0]) / 2, "sh1": (_bx["SH1"][1] + _bx["SH2"][0]) / 2,
           "sh2": (_bx["SH2"][1] + _bx["SH3"][0]) / 2, "sh3": (_bx["SH3"][1] + _bx["SH4"][0]) / 2,
           "sh4": (_bx["SH4"][1] + g.X_RIGHT) / 2,
           # right behind SH4: vertically down to the sloped hopper wall - closes the gas exit from under the bundles
           "sh4end": _bx["SH4"][1] + 0.5 * R}
SKIRTS = []
for item in filter(None, a.skirts.split(",")):
    where, depth = item.split(":")
    SKIRTS.append((where, SKIRT_X[where], float(depth)))
if SKIRTS:
    _boxes = " ".join(f"({xs - 0.55 * R:.6f} -100 {Zh - depth:.6f}) ({xs + 0.55 * R:.6f} 100 {Zh:.6f})"
                      for _, xs, depth in SKIRTS)
    zones.append(f"""SKIRTS
{{
    type        box;
    zoneType    cell;
    boxes       ({_boxes});
}}
""")
write("system/createZonesDict", "\n".join(zones))

# ---------------------------------------------------------------- porosity and heat transfer
sigma = 1 - g.D_TUBE / g.S_TRANS                 # free area across the gas flow
# Resistance (docs/CALIBRATION.md): Euler number per row by Gaddis-Gnielinski (VDI) for the bundle pitches;
# scenario B: factors from the transient tube-bank CFD (dp x0.72, htc x0.71) - discarded, kept for reference.
EU_CORR = {"EVAP": 0.18, "SH": 0.159}
DP_FAC, H_FAC = {"A": (1.0, 1.0), "B": (0.72, 0.71)}[a.scenario]
# steam-side htc on the outer surface: ~600 at 13.9 kg/s (estimate: 138 tubes ~30 mm i.d.), ~ flow^0.8
H_STEAM = 600.0 * (a.steam_kg_s / 13.9) ** 0.8


def htc_table():
    rho = P_ABS * M_GAS / (8314.0 * (650 + 273.15))
    nu = MU / rho
    rows = []
    for U in [0, 0.25, 0.5, 1, 1.5, 2, 3, 4, 5, 6, 7, 8, 10, 12, 15, 20, 30]:
        Re = (U / sigma) * g.D_TUBE / nu
        Nu = 0.27 * Re ** 0.63 * PR ** 0.36 if Re > 0 else 0
        rows.append((U, max(5.0, Nu * K_GAS / g.D_TUBE) * H_FAC * a.bundle_fac))
    return rows


def eps_gas(T, pL):
    """Emissivity of a CO2+H2O mixture (WSGG, Smith, Shen, Friedman 1982, pw/pc = 1), pL in atm*m."""
    K = [0.4303, 7.055, 178.1]
    B = [[5.150, -2.303, 0.9779, -1.494], [0.7749, 3.399, -2.297, 0.3770], [1.907, -1.824, 0.5608, -0.5122]]
    F = [1e-1, 1e-4, 1e-7, 1e-11]
    return sum(sum(bj * f * T ** j for j, (bj, f) in enumerate(zip(b, F))) * (1 - math.exp(-k * pL))
               for k, b in zip(K, B))


def h_rad(name):
    """Equivalent radiation htc of gas and dust to the bundle tubes, W/(m2 K)."""
    nt = g.TUBES[name]
    L = [x1 - x0 for n, x0, x1 in g.BUNDLES if n == name][0]
    s2 = L / nt
    Lb = 1.08 * (g.S_TRANS * s2 - math.pi * g.D_TUBE ** 2 / 4) / g.D_TUBE   # mean beam length in the bundle
    Tg, Tw = TG_RAD[name] + 273.15, TA[name] + 273.15 + (0 if name == "EVAP" else 30)
    eg = eps_gas(Tg, (X_CO2 + X_H2O) * P_ABS / 101325 * Lb)
    c_dust = DUST_KG_H / 3600 / (MDOT / (P_ABS * M_GAS / (8314 * Tg)))     # kg/m3 at Tg
    ed = 1 - math.exp(-1.5 * c_dust * Lb / (RHO_DUST * D_DUST))
    e = 1 - (1 - eg) * (1 - ed)
    eps_w = 0.8
    return 5.67e-8 * (eps_w + 1) / 2 * e * (Tg ** 4 - Tw ** 4) / (Tg - Tw), eg, ed


TAB = {}


def tab_for(name):
    """htc(U) table: convection (correlation) + gas and dust radiation, through the tube deposit;
    for the superheaters the steam-side resistance in series."""
    hr = h_rad(name)[0]
    rows = [(u, 1 / (1 / (h + hr) + a.bundle_R)) for u, h in htc_table()]   # tube deposits
    if name != "EVAP":
        rows = [(u, 1 / (1 / h + 1 / H_STEAM)) for u, h in rows]
    TAB[name] = rows
    return "\n".join(f"                ({u:g} {h:.4g})" for u, h in rows)

models = []
info = []
for name, x0, x1 in g.BUNDLES:
    L = x1 - x0
    nt = g.TUBES[name]
    EU = EU_CORR["EVAP" if name == "EVAP" else "SH"] * DP_FAC
    fx = nt * EU / (L * sigma ** 2)
    sig_y = 1 - g.D_TUBE / (L / nt)
    fy = (1 / g.S_TRANS) * 0.3 / sig_y ** 2
    fz = 0.5
    Av = g.N_ACROSS * nt * math.pi * g.D_TUBE / (L * g.W)
    info.append((name, L, fx, fy, Av, TA[name]))
    models.append(f"""{name}_porosity
{{
    type            porosityForce;
    porosityForce
    {{
        cellZone        {name};
        type            DarcyForchheimer;
        d   (0 0 0);
        f   ({fx:.4g} {fy:.4g} {fz:.4g});
        coordinateSystem
        {{
            type    cartesian;
            origin  (0 0 0);
            coordinateRotation
            {{
                type    axesRotation;
                e1      (1 0 0);
                e3      (0 0 1);
            }}
        }}
    }}
}}

{name}_heat
{{
    type            heatTransfer;
    libs            ("libinterRegionFvModels.so");
    select          cellZone;
    cellZone        {name};
    semiImplicit    yes;
    Ta              {TA[name] + 273.15:.2f};
    Av              {Av:.4g};
    heatTransferCoefficientModel function1;
    htcFunc
    {{
        type    table;
        values
        (
{tab_for(name)}
        );
        outOfBounds clamp;
    }}
}}
""")
if a.absorb > 0:
    # Volume radiation (P1): CO2+H2O over ~3 m eps ~0.38 -> a ~0.16 1/m;
    # plus dust (20 um) from the dust load. Walls: membrane with deposits, eps 0.8.
    models.append("""radiation
{
    type    radiation;
    libs    ("libradiationModels.so");
}
""")
    write("constant/radiationProperties", f"""radiationModel  P1;

solverFreq      1;

absorptionEmissionModel constant;

constantCoeffs
{{
    absorptivity    {a.absorb};
    emissivity      {a.absorb};
    E               0;
}}

scatterModel    none;

sootModel       none;
""")
if SKIRTS:
    # skirt = practically impermeable layer of cells (very high resistance in all directions)
    models.append("""SKIRTS_blockage
{
    type            porosityForce;
    porosityForce
    {
        cellZone        SKIRTS;
        type            DarcyForchheimer;
        d   (1e7 1e7 1e7);
        f   (1e4 1e4 1e4);
        coordinateSystem
        {
            type    cartesian;
            origin  (0 0 0);
            coordinateRotation { type axesRotation; e1 (1 0 0); e3 (0 0 1); }
        }
    }
}
""")
write("constant/fvModels", "\n".join(models))

# ---------------------------------------------------------------- properties
write("constant/physicalProperties", f"""thermoType
{{
    type            heRhoThermo;
    mixture         pureMixture;
    transport       const;
    thermo          hConst;
    equationOfState perfectGas;
    specie          specie;
    energy          sensibleEnthalpy;
}}

mixture
{{
    specie
    {{
        molWeight       {M_GAS};
    }}
    thermodynamics
    {{
        Cp              {CP};
        hf              0;
    }}
    transport
    {{
        mu              {MU};
        Pr              {PR};
    }}
}}
""")
write("constant/momentumTransport", """simulationType RAS;

RAS
{
    model           kEpsilon;
    turbulence      on;
    printCoeffs     on;
}
""")
write("constant/g", "dimensions      [0 1 -2 0 0 0 0];\nvalue           (0 0 -9.81);\n",
      cls="uniformDimensionedVectorField")
write("constant/pRef", f"dimensions      [1 -1 -2 0 0 0 0];\nvalue           {P_ABS};\n",
      cls="uniformDimensionedScalarField")

# ---------------------------------------------------------------- initial and boundary conditions
ASH_BC = {  # surface of hot ash in the hoppers: no heat exchange (and no radiation)
    "U": "type noSlip;", "p": "type calculated;\nvalue $internalField;",
    "p_rgh": "type fixedFluxPressure;\nvalue $internalField;", "T": "type zeroGradient;",
    "k": "type kqRWallFunction;\nvalue $internalField;", "epsilon": "type epsilonWallFunction;\nvalue $internalField;",
    "nut": "type nutkWallFunction;\nvalue uniform 0;",
    "alphat": "type compressible::alphatWallFunction;\nPrt 0.85;\nvalue uniform 0;", "G": "type zeroGradient;",
}


def field(name, cls, dim, internal, inlet, outlet, walls, duct=None):
    write(f"0/{name}", f"""dimensions      {dim};

internalField   {internal};

boundaryField
{{
    inlet
    {{
{inlet}
    }}
    outlet
    {{
{outlet}
    }}
    walls
    {{
{walls}
    }}
    ductWalls
    {{
{duct if duct is not None else walls}
    }}
    ash
    {{
{I(ASH_BC[name])}
    }}
}}
""", cls=cls)


I = lambda s: "\n".join("        " + l for l in s.strip().splitlines())
U0 = MDOT / (P_ABS * M_GAS / (8314 * T_IN)) / (g.SHAFT * g.W)   # ~ velocity in the vertical duct
field("U", "volVectorField", "[0 1 -1 0 0 0 0]", "uniform (0 0 0)",
      I(f"type flowRateInletVelocity;\nmassFlowRate {MDOT:.4g};\nvalue uniform (0 0 0);"),
      I("type inletOutlet;\ninletValue uniform (0 0 0);\nvalue uniform (0 0 0);"),
      I("type noSlip;"))
field("p", "volScalarField", "[1 -1 -2 0 0 0 0]", f"uniform {P_ABS}",
      I("type calculated;\nvalue $internalField;"), I("type calculated;\nvalue $internalField;"),
      I("type calculated;\nvalue $internalField;"))
field("p_rgh", "volScalarField", "[1 -1 -2 0 0 0 0]", "uniform 0",
      I("type fixedFluxPressure;\nvalue $internalField;"),
      I("type prghPressure;\np uniform 0;\nvalue $internalField;"),
      I("type fixedFluxPressure;\nvalue $internalField;"))
def wall_T(R):
    if R <= 0:
        return I(f"type fixedValue;\nvalue uniform {T_WALL:.2f};")
    # OF-14 ignores thicknessLayers/kappaLayers here: deposit resistance R in series with h = 800
    return I(f"type externalTemperature;\nTa constant {T_WALL:.2f};\nh uniform {1 / (1 / 800 + R):.6g};\n"
             + ("qr qr;\nqrRelaxation 0.2;\nqrPrevious uniform 0;\n" if a.absorb > 0 else "") + f"relaxation 0.2;\nvalue uniform {T_WALL:.2f};")


DUCT_R = a.wall_R if a.duct_R is None else a.duct_R
field("T", "volScalarField", "[0 0 0 1 0 0 0]", f"uniform {T_IN - 100:.2f}",
      I(f"type fixedValue;\nvalue uniform {T_IN:.2f};"),
      I(f"type inletOutlet;\ninletValue uniform {T_IN - 200:.2f};\nvalue $internalField;"),
      wall_T(a.wall_R), wall_T(DUCT_R))
k0 = 1.5 * (0.05 * U0) ** 2
eps0 = 0.09 ** 0.75 * k0 ** 1.5 / 0.3
field("k", "volScalarField", "[0 2 -2 0 0 0 0]", f"uniform {k0:.4g}",
      I("type turbulentIntensityKineticEnergyInlet;\nintensity 0.05;\nvalue $internalField;"),
      I("type inletOutlet;\ninletValue $internalField;\nvalue $internalField;"),
      I("type kqRWallFunction;\nvalue $internalField;"))
field("epsilon", "volScalarField", "[0 2 -3 0 0 0 0]", f"uniform {eps0:.4g}",
      I("type turbulentMixingLengthDissipationRateInlet;\nmixingLength 0.3;\nvalue $internalField;"),
      I("type inletOutlet;\ninletValue $internalField;\nvalue $internalField;"),
      I("type epsilonWallFunction;\nvalue $internalField;"))
field("nut", "volScalarField", "[0 2 -1 0 0 0 0]", "uniform 0",
      I("type calculated;\nvalue uniform 0;"), I("type calculated;\nvalue uniform 0;"),
      I("type nutkWallFunction;\nvalue uniform 0;"))
field("alphat", "volScalarField", "[1 -1 -1 0 0 0 0]", "uniform 0",
      I("type calculated;\nvalue uniform 0;"), I("type calculated;\nvalue uniform 0;"),
      I("type compressible::alphatWallFunction;\nPrt 0.85;\nvalue uniform 0;"))

if a.absorb > 0:
    field("G", "volScalarField", "[1 0 -3 0 0 0 0]", "uniform 0",
          I("type MarshakRadiation;\nemissivityMode lookup;\nemissivity uniform 1;\nvalue uniform 0;"),
          I("type MarshakRadiation;\nemissivityMode lookup;\nemissivity uniform 1;\nvalue uniform 0;"),
          I("type MarshakRadiation;\nemissivityMode lookup;\nemissivity uniform 0.8;\nvalue uniform 0;"))

# ---------------------------------------------------------------- system
zones_vol = "\n".join(f"""    {n}_T
    {{
        type            volFieldValue;
        libs            ("libfieldFunctionObjects.so");
        writeControl    timeStep;
        writeInterval   10;
        writeFields     false;
        log             false;
        select          cellZone;
        cellZone        {n};
        operation       volAverage;
        fields          (T U);
    }}""" for n, _, _ in g.BUNDLES)

# thermocouple-like probes: mid-gap before each SH bundle and at the boiler outlet;
# 3 heights (1 m below the ceiling, mid-bundle, 0.5 m above the bundle bottoms), mid-width
_gaps = {"before_SH1": (_bx["EVAP"][1] + _bx["SH1"][0]) / 2, "before_SH2": (_bx["SH1"][1] + _bx["SH2"][0]) / 2,
         "before_SH3": (_bx["SH2"][1] + _bx["SH3"][0]) / 2, "before_SH4": (_bx["SH3"][1] + _bx["SH4"][0]) / 2,
         "after_SH4": (_bx["SH4"][1] + g.X_RIGHT) / 2}
PROBE_LIST = []
for _n, _x in _gaps.items():
    for _lab, _z in (("top", Zc - 1.0), ("mid", Zh + g.BUNDLE_DEPTH / 2), ("low", Zh + 0.5)):
        PROBE_LIST.append((f"{_n}_{_lab}", (_x, 0.0, _z)))
PROBE_LIST.append(("outlet_mid", (g.X_OUT + 2.0, 0.0, (g.Z_OUT_BOT + g.Z_OUT_TOP) / 2)))
# "vertical path" thermocouple (~725 C): vertical duct, mid-width of the 3.7 m wall,
# short insertion (~0.15 m from the wall); height unknown - three heights, near wall and centre
for _z in (22.0, 26.0, 30.0):
    PROBE_LIST.append((f"shaftwall_{_z:.0f}", (g.SHAFT / 2, g.W / 2 - 0.15, _z)))
    PROBE_LIST.append((f"shaftmid_{_z:.0f}", (g.SHAFT / 2, 0.0, _z)))
PROBES = "\n".join(f"            ({p[0]:.4f} {p[1]:.4f} {p[2]:.4f})" for _, p in PROBE_LIST)
write("system/controlDict", f"""application     foamRun;

solver          fluid;

startFrom       latestTime;
startTime       0;
stopAt          endTime;
endTime         {a.iters};
deltaT          1;

writeControl    timeStep;
writeInterval   {a.iters if a.iters % 500 else 500};
purgeWrite      2;
writeFormat     ascii;
writePrecision  8;
writeCompression off;
timeFormat      general;
timePrecision   6;
runTimeModifiable true;

functions
{{
    #includeFunc residuals(p_rgh, U, h, k, epsilon)

    cellVolumes
    {{
        type            writeCellVolumes;
        libs            ("libfieldFunctionObjects.so");
        writeControl    writeTime;
    }}
    cellCentres
    {{
        type            writeCellCentres;
        libs            ("libfieldFunctionObjects.so");
        writeControl    writeTime;
    }}
    wallQ
    {{
        type            wallHeatFlux;
        libs            ("libfieldFunctionObjects.so");
        writeControl    writeTime;
        patches         (walls);
        log             false;
    }}

    inletOutlet
    {{
        type            surfaceFieldValue;
        libs            ("libfieldFunctionObjects.so");
        writeControl    timeStep;
        writeInterval   10;
        log             false;
        writeFields     false;
        select          patches;
        patches         (inlet outlet);
        operation       sum;
        fields          (phi);
    }}
    tc
    {{
        type            probes;
        libs            ("libsampling.so");
        writeControl    timeStep;
        writeInterval   50;
        fields          (T);
        probeLocations
        (
{PROBES}
        );
    }}
    T_shaftExit
    {{
        type            surfaceFieldValue;
        libs            ("libfieldFunctionObjects.so");
        writeControl    timeStep;
        writeInterval   10;
        log             false;
        writeFields     false;
        sampledSurface
        {{
            type        cutPlane;
            planeType   pointAndNormal;
            point       ({g.SHAFT / 2} 0 {g.Z_CEIL + 1.0});
            normal      (0 0 1);
            interpolate false;
        }}
        operation       areaAverage;
        fields          (T);
    }}
    T_beforeEvap
    {{
        $T_shaftExit;
        sampledSurface
        {{
            type        cutPlane;
            planeType   pointAndNormal;
            point       ({g.BUNDLES[0][1] - 0.3} 0 10);
            normal      (1 0 0);
            interpolate false;
        }}
    }}
    outletT
    {{
        type            surfaceFieldValue;
        libs            ("libfieldFunctionObjects.so");
        writeControl    timeStep;
        writeInterval   10;
        log             false;
        writeFields     false;
        select          patch;
        patch           outlet;
        operation       average;
        weightField     phi;
        fields          (T);
    }}
    pressures
    {{
        type            surfaceFieldValue;
        libs            ("libfieldFunctionObjects.so");
        writeControl    timeStep;
        writeInterval   10;
        log             false;
        writeFields     false;
        select          patches;
        patches         (inlet);
        operation       areaAverage;
        fields          (p);
    }}
{zones_vol}
}}
""")

write("system/fvSchemes", """ddtSchemes
{
    default         @DDT@;
}

gradSchemes
{
    default         Gauss linear;
    limited         cellLimited Gauss linear 1;
    grad(U)         $limited;
    grad(h)         $limited;
    grad(k)         $limited;
    grad(epsilon)   $limited;
}

divSchemes
{
    default         none;
    div(phi,U)      bounded Gauss linearUpwind limited;
    div(phi,K)      bounded Gauss upwind;
    div(phi,h)      bounded Gauss upwind;
    div(phi,k)      bounded Gauss upwind;
    div(phi,epsilon) bounded Gauss upwind;
    div(((rho*nuEff)*dev2(T(grad(U))))) Gauss linear;
}

laplacianSchemes
{
    default         Gauss linear limited corrected 0.5;
}

interpolationSchemes
{
    default         linear;
}

snGradSchemes
{
    default         limited corrected 0.5;
}

wallDist
{
    method meshWave;
}
""".replace("@DDT@", "localEuler" if a.lts else "steadyState"))

# local time stepping (pseudo-transient) start: robust on fine meshes started from rest
LTS_FINAL = """
    "rho.*"
    {
        solver          diagonal;
    }

    p_rghFinal
    {
        $p_rgh;
        relTol          0;
    }

    "(U|h|k|epsilon)Final"
    {
        $U;
        relTol          0;
    }

    GFinal
    {
        $G;
        relTol          0;
    }"""
LTS_PIMPLE = f"""    nOuterCorrectors 1;
    nCorrectors     2;
    maxCo           {a.lts_co};
    rDeltaTSmoothingCoeff 0.1;
    rDeltaTDampingCoeff 1;
    maxDeltaT       1;"""
write("system/fvSolution", """solvers
{
    p_rgh
    {
        solver          GAMG;
        smoother        DIC;
        tolerance       1e-7;
        relTol          0.01;
    }

    "(U|h|k|epsilon)"
    {
        solver          PBiCGStab;
        preconditioner  DILU;
        tolerance       1e-8;
        relTol          0.1;
    }

    G
    {
        solver          PCG;
        preconditioner  DIC;
        tolerance       1e-6;
        relTol          0.1;
    }
@FINAL@
}

PIMPLE
{
    momentumPredictor yes;
    nNonOrthogonalCorrectors 1;
@LTS@
}

relaxationFactors
{
    fields
    {
        rho             1.0;
        p_rgh           @RP@;
    }
    equations
    {
        U               @RU@;
        h               @RU@;
        "(k|epsilon)"   @RU@;
    }
}
""".replace("@RP@", str(a.relax_p)).replace("@RU@", str(a.relax_u))
     .replace("@FINAL@", LTS_FINAL if a.lts else "").replace("@LTS@", LTS_PIMPLE if a.lts else ""))

write("system/decomposeParDict", f"""numberOfSubdomains {a.np};

decomposer      scotch;
""")

(case / "Allrun").write_text("""#!/bin/sh
cd ${0%/*} || exit 1
. $WM_PROJECT_DIR/bin/tools/RunFunctions

runApplication blockMesh
runApplication checkMesh
runApplication createZones
runApplication decomposePar
runParallel foamRun
runApplication reconstructPar -latestTime
""", encoding="utf-8", newline="\n")
(case / "Allrun").chmod(0o755)

(case / "case_info.txt").write_text(
    f"MDOT {MDOT}\nCP {CP}\nT_IN {T_IN}\nP_ABS {P_ABS}\nM_GAS {M_GAS}\nwall_R {a.wall_R}\n"
    f"bundle_fac {a.bundle_fac}\nbundle_R {a.bundle_R}\ndust_frac {a.dust_frac}\n"
    f"hopper_fill {a.hopper_fill}\nabsorb {a.absorb}\nduct_R {DUCT_R}\nscenario {a.scenario}\n"
    f"RES {a.res}\nNY {a.ny}\nZ_ASH {Z_ASH}\n"
    f"steam_kg_s {a.steam_kg_s}\nspray_kg_s {a.spray_kg_s}\nspray_h {a.spray_h}\n"
    f"skirts {a.skirts or '-'}\nhopper2_fill {_f2}\nextra_water_t_h {a.extra_water_t_h}\n"
    f"extra_air_nm3_h {a.extra_air_nm3_h}\nextra_n2_nm3_h {a.extra_n2_nm3_h}\nX_O2 {_kmol['O2'] / KMOL_H}\nX_H2O {X_H2O}\n"
    f"probes {','.join(n for n, _ in PROBE_LIST)}\n"
    + "".join(f"Ta_{n} {TA[n] + 273.15}\nAv_{n} {Av}\n" for n, _, _, _, Av, _ in [(i[0], 0, 0, 0, i[4], 0) for i in info])
    + "".join(f"htc_{n} " + " ".join(f"{u:g}:{h:.5g}" for u, h in TAB[n]) + "\n" for n, _, _ in g.BUNDLES),
    encoding="utf-8")

# summary
print(f"m = {MDOT:.1f} kg/s, U in vertical duct ~ {U0:.1f} m/s")
print("bundle  L, m   f_x, 1/m  f_y, 1/m  Av, 1/m  Ta, C")
for n, L, fx, fy, Av, Ta in info:
    print(f"{n:5s} {L:6.3f} {fx:9.2f} {fy:9.2f} {Av:8.2f} {Ta:6.0f}")
for n, _, _ in g.BUNDLES:
    hr, eg, ed = h_rad(n)
    print(f"{n}: radiation h = {hr:.1f} W/(m2 K) (gas eps = {eg:.3f}, dust eps = {ed:.3f})")
print("htc(U):", ", ".join(f"{u:g}:{h:.0f}" for u, h in htc_table()))
