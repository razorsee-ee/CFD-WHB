"""Boiler (WHB) run summary: gas flow through the bundles, bundle/wall heat, steam temperatures.

python model/whb_summary.py <case_dir>

Monitors come from postProcessing; bundle heat and bulk temperatures from the fields of the latest
written time (T, U, Vc, C in ascii) and the htc tables in case_info.txt.
Also writes <case_dir>/summary.json (used by views.py) and ta_next.txt (steam temperatures for the
next coupling pass).

Bulk ("mixing-cup") gas temperature of a section is computed from the enthalpy flux:
    T_bulk = sum(m_i * (cp*T_i + |U_i|^2/2)) / sum(m_i * cp),   m_i = rho_i * Ux_i * dA_i
i.e. weighted by the local mass flux (faster gas counts more), kinetic energy included.
"""
import json
import math
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent))
import geometry as g

case = Path(sys.argv[1])
pp = case / "postProcessing"

info = {}
for l in (case / "case_info.txt").read_text(encoding="utf-8").splitlines():
    k, v = l.split(" ", 1)
    info[k] = v
F = lambda k, d=None: float(info[k]) if k in info else d
MDOT, CP, T_IN, P_ABS, M_GAS = F("MDOT"), F("CP"), F("T_IN"), F("P_ABS"), F("M_GAS")
RES, NY = F("RES", 0.3), int(F("NY", 12))
NUM = re.compile(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?")
STAGE = {"SH1": "SH IIIb", "SH2": "SH IIIa", "SH3": "SH II", "SH4": "SH I", "EVAP": "EVAP"}
# DCS reference (period with 16.2 kg/s steam, sprays ~0.25 kg/s)
DCS_GAS = {"before_SH1": 702, "before_SH2": 681, "before_SH3": 655, "before_SH4": 621, "outlet": 618,
           "shaft": 725}
DCS_STEAM = {"SH4": (251, 291), "SH3": (290, 343), "SH2": (341, 395), "SH1": (394, 441)}
DCS_Q = {"SH4": 2.19, "SH3": 2.30, "SH2": 2.15, "SH1": 1.76}


def last_row(name, fname):
    files = sorted(pp.glob(f"{name}/*/{fname}"), key=lambda p: float(p.parent.name))
    rows = [l for l in files[-1].read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")]
    return rows[-1]


def nums(row):
    return [float(v) for v in NUM.findall(row)]


def latest_time():
    ts = [p for p in case.iterdir() if p.is_dir() and re.fullmatch(r"[0-9.e+-]+", p.name) and float(p.name) > 0]
    return max(ts, key=lambda p: float(p.name)) if ts else None


def read_internal(path):
    txt = path.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"internalField\s+(uniform|nonuniform)", txt)
    body = txt[m.end():]
    if m.group(1) == "uniform":
        return None
    m2 = re.search(r"(\d+)\s*\(", body)
    n = int(m2.group(1))
    body = body[m2.end():]
    if body.lstrip().startswith("("):
        vals = re.findall(r"\(([^()]+)\)", body)[:n]
        return [[float(x) for x in v.split()] for v in vals]
    return [float(x) for x in body.split(")")[0].split()[:n]]


def cell_zones():
    txt = (case / "constant/polyMesh/cellZones").read_text(encoding="utf-8")
    zones = {}
    for m in re.finditer(r"(\w+)\s*\{[^{}]*?cellLabels\s+List<label>\s+(\d+)\s*\(([^)]*)\)", txt, re.S):
        zones[m.group(1)] = [int(x) for x in m.group(3).split()]
    return zones


def htc(name, u):
    tab = [tuple(map(float, p.split(":"))) for p in info[f"htc_{name}"].split()]
    if u <= tab[0][0]:
        return tab[0][1]
    for (u0, h0), (u1, h1) in zip(tab, tab[1:]):
        if u <= u1:
            return h0 + (h1 - h0) * (u - u0) / (u1 - u0)
    return tab[-1][1]


# steam tables, 40 bar: T [°C] -> h [kJ/kg]
TH = [(250.4, 2800.8), (275, 2886.2), (300, 2961.7), (350, 3093.3), (400, 3214.5),
      (450, 3331.2), (500, 3446.0), (550, 3559.7), (600, 3674.9), (700, 3906.3)]


def T_of(h):
    if h <= TH[0][1]:
        return TH[0][0]
    for (t0, h0), (t1, h1) in zip(TH, TH[1:]):
        if h <= h1:
            return t0 + (t1 - t0) * (h - h0) / (h1 - h0)
    return TH[-1][0]


out = {"case": case.name}
it = nums(last_row("outletT", "surfaceFieldValue.dat"))
T_out = it[1]                                   # flux-weighted on the outlet patch (OpenFOAM)
Q_tot = MDOT * CP * (T_IN - T_out)
p_in = nums(last_row("pressures", "surfaceFieldValue.dat"))[1]
out.update(iteration=int(it[0]), T_out_patch=T_out - 273.15, Q_gas_MW=Q_tot / 1e6, dp_Pa=p_in - P_ABS)

print(f"Skirts: {info.get('skirts', '-')}; right hopper ash fill {F('hopper2_fill', F('hopper_fill', 0)) * 100:.0f} %")
print(f"Iteration {int(it[0])}: deposits R [m2K/W]: ducts {info.get('duct_R', info['wall_R'])}, boiler walls "
      f"{F('wall_R'):g}, tubes {info.get('bundle_R', '0')}; dust to bundles {F('dust_frac', 0.2) * 100:.0f} %; "
      f"absorption {info.get('absorb', '?')} 1/m; sponge {info['scenario']}")
for nm, lab in (("T_shaftExit", "Gas at the bottom of the vertical duct (area mean)"),
                ("T_beforeEvap", "Gas before the evaporator (area mean of whole section)")):
    try:
        print(f"{lab}: {nums(last_row(nm, 'surfaceFieldValue.dat'))[1] - 273.15:.0f} °C")
    except (IndexError, StopIteration):
        pass
print(f"Gas at outlet (mass-flux weighted): {T_out - 273.15:.0f} °C   (DCS 618 °C)")
print(f"Heat given by gas: {Q_tot / 1e6:.1f} MW   Pressure drop inlet-outlet: {p_in - P_ABS:.0f} Pa")

A = g.BUNDLE_DEPTH * g.W
t = latest_time()
Qb, Umax, bulk = {}, {}, {}
if t is not None and (t / "Vc").exists():
    T, U, V = read_internal(t / "T"), read_internal(t / "U"), read_internal(t / "Vc")
    Z = cell_zones()
    for n, _, _ in g.BUNDLES:
        Ta, Av = F(f"Ta_{n}"), F(f"Av_{n}")
        Qb[n] = sum(htc(n, math.sqrt(sum(c * c for c in U[i]))) * Av * (T[i] - Ta) * V[i] for i in Z[n])
        Umax[n] = max(math.sqrt(sum(c * c for c in U[i])) for i in Z[n])
    # bulk (enthalpy-flux) temperatures in planes between bundles: whole section, above and below
    # the bundle bottoms (below = gas passing under the bundles, over the hopper)
    if (t / "C").exists():
        C = read_internal(t / "C")
        bx = {n: (x0, x1) for n, x0, x1 in g.BUNDLES}
        planes = {"before_SH1": (bx["EVAP"][1] + bx["SH1"][0]) / 2, "before_SH2": (bx["SH1"][1] + bx["SH2"][0]) / 2,
                  "before_SH3": (bx["SH2"][1] + bx["SH3"][0]) / 2, "before_SH4": (bx["SH3"][1] + bx["SH4"][0]) / 2,
                  "after_SH4": (bx["SH4"][1] + g.X_RIGHT) / 2, "outlet": g.X_OUT + 2.0}
        for pn, xp in planes.items():
            acc = {"all": [0.0, 0.0, 0.0], "above": [0.0, 0.0, 0.0], "below": [0.0, 0.0, 0.0]}
            dx = RES
            for i, c in enumerate(C):
                if abs(c[0] - xp) >= 0.5 * dx:
                    continue
                dA = V[i] / dx                                      # cell volume / cell length along x
                rho = P_ABS * M_GAS / (8314 * T[i])
                m = rho * U[i][0] * dA
                e = CP * T[i] + 0.5 * sum(u * u for u in U[i])
                for key in ("all", "above" if c[2] >= g.Z_HOP else "below"):
                    acc[key][0] += m * e
                    acc[key][1] += m * CP
                    acc[key][2] += m
            bulk[pn] = {k: (v[0] / v[1] - 273.15 if abs(v[1]) > 1e-9 else None, v[2]) for k, v in acc.items()}

print("\nBundle     gas T, °C  Ux, m/s  gas through bundle  heat, MW  max |U|, m/s")
through = {}
for n, _, _ in g.BUNDLES:
    v = nums(last_row(f"{n}_T", "volFieldValue.dat"))
    Tz, ux = v[1], v[2]
    rho = P_ABS * M_GAS / (8314 * Tz)
    through[n] = rho * ux * A / MDOT * 100
    q = f"{Qb[n] / 1e6:8.2f}" if n in Qb else "     -"
    um = f"{Umax[n]:10.1f}" if n in Umax else ""
    print(f"{n:5s} {STAGE[n]:8s} {Tz - 273.15:6.0f} {ux:8.2f} {through[n]:14.0f} %      {q}  {um}")
out.update(through_pct=through, Q_MW={n: q / 1e6 for n, q in Qb.items()}, Umax=Umax)

if Qb:
    Q_sh = sum(Qb[n] for n in Qb if n != "EVAP")
    m_s, m_sp, h_sp = F("steam_kg_s", 13.9), F("spray_kg_s", 0.0), F("spray_h", 1087.0)
    print(f"\nSuperheaters: {Q_sh / 1e6:.2f} MW   (steam {m_s:g} kg/s + spray {m_sp:g} kg/s)")
    print(f"Evaporator: {Qb['EVAP'] / 1e6:.2f} MW   Walls (remainder): {(Q_tot - sum(Qb.values())) / 1e6:.1f} MW")
    # counterflow: steam enters SH4 (= SH I, last on the gas side); spray before SH1 (= SH IIIb)
    h, m = TH[0][1], m_s
    steam, mean, txt = {}, {}, []
    for n in ("SH4", "SH3", "SH2", "SH1"):
        if n == "SH1" and m_sp > 0:
            h = (m * h + m_sp * h_sp) / (m + m_sp)
            m += m_sp
        T_in = T_of(h)
        h += Qb[n] / 1e3 / m
        steam[n] = (T_in, T_of(h))
        mean[n] = (T_in + T_of(h)) / 2
        txt.append(f"{STAGE[n]}: {T_in:.0f}->{T_of(h):.0f}")
    print("Steam (model, 40 bar steam tables): " + ", ".join(txt) + f" °C  -> outlet {T_of(h):.0f} °C")
    print("Steam (DCS, 16.2 kg/s):             " + ", ".join(f"{STAGE[n]}: {a}->{b}" for n, (a, b) in DCS_STEAM.items())
          + " °C")
    print("Stage heat SH I / II / IIIa / IIIb, MW: model " + " / ".join(f"{Qb[n] / 1e6:.2f}" for n in ("SH4", "SH3", "SH2", "SH1"))
          + f" = {Q_sh / 1e6:.1f};  DCS 2.19 / 2.30 / 2.15 / 1.76 = 8.4")
    used = ", ".join(f"{STAGE[n]} {F(f'Ta_{n}') - 273.15:.0f}" for n in ("SH4", "SH3", "SH2", "SH1"))
    print(f"Steam temperature used in this pass (stage mean): {used} °C")
    (case / "ta_next.txt").write_text(",".join(f"{mean[n]:.1f}" for n in ("SH1", "SH2", "SH3", "SH4")))
    out.update(Q_sh_MW=Q_sh / 1e6, steam=steam, steam_out=T_of(h))

if bulk:
    print("\nBulk gas temperature (enthalpy flux) between bundles, °C:   whole | above bundle bottom | below "
          "(over hopper) | share of flow below")
    for pn, lab in (("before_SH1", "before SH IIIb"), ("before_SH2", "before SH IIIa"), ("before_SH3", "before SH II"),
                    ("before_SH4", "before SH I"), ("after_SH4", "after SH I"), ("outlet", "outlet duct")):
        b = bulk[pn]
        fmt = lambda v: f"{v:5.0f}" if v is not None else "    -"
        share = b["below"][1] / b["all"][1] * 100 if b["all"][1] else float("nan")
        ref = DCS_GAS.get(pn, DCS_GAS["outlet"] if pn == "outlet" else None)
        print(f"  {lab:15s} {fmt(b['all'][0])} | {fmt(b['above'][0])} | {fmt(b['below'][0])} | {share:5.0f} %"
              + (f"   (DCS thermocouple {ref})" if ref else ""))
    out["bulk"] = bulk

# thermocouple-like probes (DCS is a guide only: exact positions unknown)
names = info.get("probes", "").split(",") if info.get("probes") else []
pf = sorted(pp.glob("tc/*/T"), key=lambda p: float(p.parent.name))
if names and pf:
    row = [l for l in pf[-1].read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")][-1]
    vals = {k: v - 273.15 for k, v in zip(names, nums(row)[1:])}
    print("\nPoint probes between bundles, mid-width, °C:")
    print("before          top     mid     low    DCS")
    for gname, lab in (("before_SH1", "SH IIIb"), ("before_SH2", "SH IIIa"), ("before_SH3", "SH II"),
                       ("before_SH4", "SH I"), ("after_SH4", "after SH I")):
        v = [vals.get(f"{gname}_{h}", float("nan")) for h in ("top", "mid", "low")]
        d = DCS_GAS.get(gname)
        print(f"{lab:12s} {v[0]:7.0f} {v[1]:7.0f} {v[2]:7.0f}   {d if d else '':>4}")
    print(f"outlet duct, centre: {vals.get('outlet_mid', float('nan')):.0f} °C (DCS 618)")
    if "shaftwall_22" in vals:
        print("Vertical duct (DCS 'vertical path' ~725 °C, thermocouple near the wall at mid-width):")
        for zz in ("22", "26", "30"):
            print(f"  z = {zz} m: near wall {vals[f'shaftwall_{zz}']:.0f} °C, centre {vals[f'shaftmid_{zz}']:.0f} °C")
    out["probes"] = vals

print("\nShare < 100 %: the rest of the gas bypasses the bundle (underneath, over the hopper).")
(case / "summary.json").write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
