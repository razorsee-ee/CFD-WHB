"""Генератор кейса OpenFOAM-12 для котла-утилизатора (WHB).

python model/make_case.py <папка_кейса> [--res 0.3] [--ny 12] [--np 4]

Сетка: blockMesh по контуру сечения (x-z), вытянутому по ширине y; бункеры
сужаются по ширине к дну. Пучки — пористые cellZone (границы пучков совпадают
с гранями ячеек), с сопротивлением DarcyForchheimer и отбором тепла
heatTransfer (htc по корреляции Жукаускаса как функция скорости).
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
ap.add_argument("--res", type=float, default=0.3, help="размер ячейки в сечении, м")
ap.add_argument("--ny", type=int, default=12, help="ячеек по ширине")
ap.add_argument("--np", type=int, default=4, help="число процессов")
ap.add_argument("--iters", type=int, default=3000)
ap.add_argument("--bundle_R", type=float, default=0.0,
                help="тепловое сопротивление налёта на трубах пучков, м²·К/Вт")
ap.add_argument("--dust_frac", type=float, default=0.4,
                help="доля от 50 т/ч золы, пролетающая первый бункер в пучки")
ap.add_argument("--hopper_fill", type=float, default=0.10, help="заполнение бункеров золой, доля объёма")
ap.add_argument("--wall_R", type=float, default=0.0,
                help="тепловое сопротивление отложений на мембранных стенках, м²·К/Вт (0 — чистые)")
ap.add_argument("--bundle_fac", type=float, default=1.0,
                help="множитель к α газа в пучках (загрязнение труб и неопределённость)")
ap.add_argument("--ta", default="", help="температуры пара SH1,SH2,SH3,SH4, °C (по умолчанию 413,361,312,270)")
ap.add_argument("--absorb", type=float, default=None,
                help="коэффициент поглощения газа+пыли для P1, 1/м (по умолчанию — из пыли; 0 — без излучения)")
ap.add_argument("--scenario", choices=["A", "B"], default="B",
                help="A — по корреляциям (Гаддис, Жукаускас); B — по CFD куска пучка (docs/CALIBRATION.md)")
a = ap.parse_args()
R = a.res

HDR = """/*--------------------------------*- C++ -*----------------------------------*\\
  =========                 |
  \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox
   \\\\    /   O peration     | Website:  https://openfoam.org
    \\\\  /    A nd           | Version:  12
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


# ---------------------------------------------------------------- режим работы
P_ABS = 112000 - 200             # на ВЫХОДЕ, Па абс.: вход 1.120 бар минус оценка перепада ~2 мбар
# Состав (пользователь, верх CFB, 757 °C): N2 66.96, CO2 14.12, H2O 16.42, O2 2.50 % об.,
# 10149 кмоль/ч = 227 332 Нм³/ч (влажн.). Свойства смеси при ~650 °C.
X_CO2, X_H2O = 0.1412, 0.1642
M_GAS = 28.73                   # кг/кмоль
KMOL_H = 10149.0
MDOT = KMOL_H * M_GAS / 3600    # кг/с (~81.0)
T_IN = 745 + 273.15            # газ из циклонов 740–750 °C (пользователь)
T_WALL = 250 + 273.15
CP_GAS = 1250.0
MU = 3.7e-5
PR = 0.72
K_GAS = 0.064                   # теплопроводность газа ~650 °C, Вт/(м·К)

# Пыль, идущая через пучки: 20 % от 50 т/ч (пользователь), частицы ~20 мкм (допущение)
DUST_KG_H = a.dust_frac * 50000
D_DUST = 20e-6
RHO_DUST = 2500.0
CP_DUST = 850.0
CP = CP_GAS + DUST_KG_H / 3600 / MDOT * CP_DUST     # теплоёмкость потока газ + пыль на 1 кг газа
if a.absorb is None:
    _c = DUST_KG_H / 3600 / (MDOT / (P_ABS * M_GAS / (8314 * 923.15)))   # кг/м³ при ~650 °C
    a.absorb = round(0.16 + 1.5 * _c / (RHO_DUST * D_DUST), 3)        # газ ~0.16 1/м + пыль
# Ожидаемая средняя температура газа в пучке, °C (для излучения; уточнять по расчёту)
TG_RAD = {"EVAP": 740, "SH1": 700, "SH2": 670, "SH3": 640, "SH4": 610}

# Температура «окружения» для пучков: пар (противоток 250 -> 440 °C, поровну по ступеням)
TA = {"EVAP": 250, "SH4": 270, "SH3": 312, "SH2": 361, "SH1": 413}
if a.ta:
    for _n, _t in zip(("SH1", "SH2", "SH3", "SH4"), a.ta.split(",")):
        TA[_n] = float(_t)
K_ASH = 0.2           # теплопроводность отложений, Вт/(м·К) — толщина слоя = wall_R * K_ASH

# ---------------------------------------------------------------- секции по x
# Каждая секция: (длина, число ячеек). Границы пучков = границы секций.
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
# Если испаритель тоньше ячейки — всё равно одна ячейка
sec_left = sections(g.SHAFT, g.X_APEX, evap)
sec_right = sections(g.X_APEX, g.X_RIGHT, shs)

ns = n_cells(g.SHAFT)                       # поперёк газохода
nz_b = n_cells(g.BUNDLE_DEPTH)              # высота зоны пучков
nz_h = n_cells(g.Z_HOP)                     # глубина бункеров
lx_incl = math.dist(g.BEND_INNER, g.INLET_INNER)
n_incl = n_cells(lx_incl)
n_shaft = n_cells(g.BEND_INNER[1] - g.Z_CEIL)
n_out = n_cells(g.X_OUT - g.X_RIGHT)
n_ext = n_cells(g.OUTLET_EXT, 2 * R)

# ---------------------------------------------------------------- блоки (x, z)
Zc, Zh = g.Z_CEIL, g.Z_HOP
xo_end = g.X_OUT + g.OUTLET_EXT
split1 = g.HOP1_BOT[0] + (g.HOP1_BOT[1] - g.HOP1_BOT[0]) * g.SHAFT / g.X_APEX


def hopper_fill_z(frac):
    """Высота слоя золы, занимающего долю frac объёма бункера 1 (площадь сечения ~ Lx(z)·Wy(z))."""
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
nz_h = n_cells(Zh - Z_ASH)


def at_z(p_low, p_high, z):
    """Точка на отрезке p_low -> p_high на высоте z."""
    t = (z - p_low[1]) / (p_high[1] - p_low[1])
    return (p_low[0] + t * (p_high[0] - p_low[0]), z)


def hop(q):
    """Бункерный блок, обрезанный снизу по уровню золы."""
    p0, p1, p2, p3 = q
    return (at_z(p0, p3, Z_ASH), at_z(p1, p2, Z_ASH), p2, p3)

blocks = [
    # имя, (p0, p1, p2, p3) против часовой в (x, z); (n1, grading1), (n2, grading2)
    ("incl", (g.BEND_INNER, g.BEND_OUTER, g.INLET_OUTER, g.INLET_INNER), (ns, "1"), (n_incl, "1")),
    ("shaft", ((0, Zc), (g.SHAFT, Zc), g.BEND_OUTER, g.BEND_INNER), (ns, "1"), (n_shaft, "1")),
    ("col", ((0, Zh), (g.SHAFT, Zh), (g.SHAFT, Zc), (0, Zc)), (ns, "1"), (nz_b, "1")),
    ("left", ((g.SHAFT, Zh), (g.X_APEX, Zh), (g.X_APEX, Zc), (g.SHAFT, Zc)), grading_spec(sec_left), (nz_b, "1")),
    ("right", ((g.X_APEX, Zh), (g.X_RIGHT, Zh), (g.X_RIGHT, Zc), (g.X_APEX, Zc)), grading_spec(sec_right), (nz_b, "1")),
    ("trans", ((g.X_RIGHT, Zh), (g.X_OUT, g.Z_OUT_BOT), (g.X_OUT, g.Z_OUT_TOP), (g.X_RIGHT, Zc)), (n_out, "1"), (nz_b, "1")),
    ("ext", ((g.X_OUT, g.Z_OUT_BOT), (xo_end, g.Z_OUT_BOT), (xo_end, g.Z_OUT_TOP), (g.X_OUT, g.Z_OUT_TOP)), (n_ext, "1"), (nz_b, "1")),
    ("hop1a", hop(((g.HOP1_BOT[0], 0), (split1, 0), (g.SHAFT, Zh), (0, Zh))), (ns, "1"), (nz_h, "1")),
    ("hop1b", hop(((split1, 0), (g.HOP1_BOT[1], 0), (g.X_APEX, Zh), (g.SHAFT, Zh))), grading_spec(sec_left), (nz_h, "1")),
    ("hop2", hop(((g.HOP2_BOT[0], 0), (g.HOP2_BOT[1], 0), (g.X_RIGHT, Zh), (g.X_APEX, Zh))), grading_spec(sec_right), (nz_h, "1")),
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
faces_inlet, faces_outlet, faces_ash = [], [], []
for name, quad, (n1, g1), (n2, g2) in blocks:
    front = [vertex(x, +half_w(z), z) for x, z in quad]
    back = [vertex(x, -half_w(z), z) for x, z in quad]
    # проверка правой тройки: (p1-p0) x (p3-p0) . (back0-front0) > 0
    p = [verts[i] for i in front]
    q = verts[back[0]]
    e1 = [p[1][k] - p[0][k] for k in range(3)]
    e2 = [p[3][k] - p[0][k] for k in range(3)]
    e3 = [q[k] - p[0][k] for k in range(3)]
    cr = [e1[1] * e2[2] - e1[2] * e2[1], e1[2] * e2[0] - e1[0] * e2[2], e1[0] * e2[1] - e1[1] * e2[0]]
    assert sum(cr[k] * e3[k] for k in range(3)) > 0, name
    hexes.append(f"    hex ({' '.join(map(str, front + back))}) {name} ({n1} {n2} {a.ny})\n"
                 f"        simpleGrading ({g1} {g2} 1)")
    if name == "incl":   # грань p2-p3 (вход)
        faces_inlet.append((front[3], front[2], back[2], back[3]))
    if name == "ext":    # грань p1-p2 (выход)
        faces_outlet.append((front[1], front[2], back[2], back[1]))
    if name.startswith("hop") and Z_ASH > 0:   # грань p0-p1 (поверхность золы)
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

# ---------------------------------------------------------------- зоны пучков
eps = 1e-3
actions = []
for name, x0, x1 in g.BUNDLES:
    actions.append(f"""    {{
        name    {name};
        type    cellZoneSet;
        action  new;
        source  boxToCell;
        box     ({x0 + eps:.6f} -100 {Zh:.6f}) ({x1 - eps:.6f} 100 {Zc:.6f});
    }}""")
write("system/topoSetDict", "actions\n(\n" + "\n".join(actions) + "\n);\n")

# ---------------------------------------------------------------- пористость и теплообмен
sigma = 1 - g.D_TUBE / g.S_TRANS                 # живое сечение поперёк хода газа
# Калибровка (docs/CALIBRATION.md): Эйлер на ряд по Гаддису–Гнилинскому (VDI) для шагов пучка;
# сценарий B — множители по нестационарному CFD куска пучка (Δp x0.72, α x0.71).
EU_CORR = {"EVAP": 0.18, "SH": 0.159}
DP_FAC, H_FAC = {"A": (1.0, 1.0), "B": (0.72, 0.71)}[a.scenario]
H_STEAM = 600.0                                  # α со стороны пара (на наружную поверхность), SH


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
    """Степень черноты смеси CO2+H2O (WSGG, Smith, Shen, Friedman 1982, pw/pc = 1), pL в атм·м."""
    K = [0.4303, 7.055, 178.1]
    B = [[5.150, -2.303, 0.9779, -1.494], [0.7749, 3.399, -2.297, 0.3770], [1.907, -1.824, 0.5608, -0.5122]]
    F = [1e-1, 1e-4, 1e-7, 1e-11]
    return sum(sum(bj * f * T ** j for j, (bj, f) in enumerate(zip(b, F))) * (1 - math.exp(-k * pL))
               for k, b in zip(K, B))


def h_rad(name):
    """Эквивалентный коэффициент излучения газа и пыли на трубы пучка, Вт/(м²·К)."""
    nt = g.TUBES[name]
    L = [x1 - x0 for n, x0, x1 in g.BUNDLES if n == name][0]
    s2 = L / nt
    Lb = 1.08 * (g.S_TRANS * s2 - math.pi * g.D_TUBE ** 2 / 4) / g.D_TUBE   # эффективная толщина слоя
    Tg, Tw = TG_RAD[name] + 273.15, TA[name] + 273.15 + (0 if name == "EVAP" else 30)
    eg = eps_gas(Tg, (X_CO2 + X_H2O) * P_ABS / 101325 * Lb)
    c_dust = DUST_KG_H / 3600 / (MDOT / (P_ABS * M_GAS / (8314 * Tg)))     # кг/м³ при Tg
    ed = 1 - math.exp(-1.5 * c_dust * Lb / (RHO_DUST * D_DUST))
    e = 1 - (1 - eg) * (1 - ed)
    eps_w = 0.8
    return 5.67e-8 * (eps_w + 1) / 2 * e * (Tg ** 4 - Tw ** 4) / (Tg - Tw), eg, ed


TAB = {}


def tab_for(name):
    """Таблица htc(U): конвекция (калибровка) + излучение газа и пыли; для пароперегревателей
    последовательно — сопротивление пара."""
    hr = h_rad(name)[0]
    rows = [(u, 1 / (1 / (h + hr) + a.bundle_R)) for u, h in htc_table()]   # налёт на трубах
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
    porosityForceCoeffs
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
    # Излучение в объёме (P1): газ CO2+H2O на толщине ~3 м eps ~0.38 -> a ~0.16 1/м;
    # пыль 10 т/ч, 20 мкм -> a ~0.44 1/м. Стенки — мембрана, eps 0.8.
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
write("constant/fvModels", "\n".join(models))

# ---------------------------------------------------------------- свойства
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

# ---------------------------------------------------------------- начальные и граничные условия
ASH_BC = {  # поверхность горячей золы в бункерах: без теплообмена (и без излучения)
    "U": "type noSlip;", "p": "type calculated;\nvalue $internalField;",
    "p_rgh": "type fixedFluxPressure;\nvalue $internalField;", "T": "type zeroGradient;",
    "k": "type kqRWallFunction;\nvalue $internalField;", "epsilon": "type epsilonWallFunction;\nvalue $internalField;",
    "nut": "type nutkWallFunction;\nvalue uniform 0;",
    "alphat": "type compressible::alphatWallFunction;\nPrt 0.85;\nvalue uniform 0;", "G": "type zeroGradient;",
}


def field(name, cls, dim, internal, inlet, outlet, walls):
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
    ash
    {{
{I(ASH_BC[name])}
    }}
}}
""", cls=cls)


I = lambda s: "\n".join("        " + l for l in s.strip().splitlines())
U0 = MDOT / (P_ABS * M_GAS / (8314 * T_IN)) / (g.SHAFT * g.W)   # ~ скорость в газоходе
field("U", "volVectorField", "[0 1 -1 0 0 0 0]", "uniform (0 0 0)",
      I(f"type flowRateInletVelocity;\nmassFlowRate {MDOT:.4g};\nvalue uniform (0 0 0);"),
      I("type pressureInletOutletVelocity;\nvalue uniform (0 0 0);"),
      I("type noSlip;"))
field("p", "volScalarField", "[1 -1 -2 0 0 0 0]", f"uniform {P_ABS}",
      I("type calculated;\nvalue $internalField;"), I("type calculated;\nvalue $internalField;"),
      I("type calculated;\nvalue $internalField;"))
field("p_rgh", "volScalarField", "[1 -1 -2 0 0 0 0]", "uniform 0",
      I("type fixedFluxPressure;\nvalue $internalField;"),
      I("type prghPressure;\np uniform 0;\nvalue $internalField;"),
      I("type fixedFluxPressure;\nvalue $internalField;"))
field("T", "volScalarField", "[0 0 0 1 0 0 0]", f"uniform {T_IN - 100:.2f}",
      I(f"type fixedValue;\nvalue uniform {T_IN:.2f};"),
      I(f"type inletOutlet;\ninletValue uniform {T_IN - 200:.2f};\nvalue $internalField;"),
      I(f"type fixedValue;\nvalue uniform {T_WALL:.2f};") if a.wall_R <= 0 else
      I(f"type externalTemperature;\nTa constant {T_WALL:.2f};\nh uniform 2500;\n"
        f"thicknessLayers ({a.wall_R * K_ASH:.5g});\nkappaLayers ({K_ASH});\n"
        + ("qr qr;\nqrRelaxation 0.2;\n" if a.absorb > 0 else "") + f"relaxation 0.2;\nvalue uniform {T_WALL:.2f};"))
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

write("system/controlDict", f"""application     foamRun;

solver          fluid;

startFrom       latestTime;
startTime       0;
stopAt          endTime;
endTime         {a.iters};
deltaT          1;

writeControl    timeStep;
writeInterval   500;
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
    default         steadyState;
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
""")

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
}

PIMPLE
{
    momentumPredictor yes;
    nNonOrthogonalCorrectors 1;
}

relaxationFactors
{
    fields
    {
        rho             1.0;
        p_rgh           0.3;
    }
    equations
    {
        U               0.5;
        h               0.5;
        "(k|epsilon)"   0.5;
    }
}
""")

write("system/decomposeParDict", f"""numberOfSubdomains {a.np};

decomposer      scotch;
""")

(case / "Allrun").write_text("""#!/bin/sh
cd ${0%/*} || exit 1
. $WM_PROJECT_DIR/bin/tools/RunFunctions

runApplication blockMesh
runApplication checkMesh
runApplication topoSet
runApplication decomposePar
runParallel foamRun
runApplication reconstructPar -latestTime
""", encoding="utf-8", newline="\n")
(case / "Allrun").chmod(0o755)

(case / "case_info.txt").write_text(
    f"MDOT {MDOT}\nCP {CP}\nT_IN {T_IN}\nP_ABS {P_ABS}\nM_GAS {M_GAS}\nwall_R {a.wall_R}\n"
    f"bundle_fac {a.bundle_fac}\nbundle_R {a.bundle_R}\ndust_frac {a.dust_frac}\n"
    f"hopper_fill {a.hopper_fill}\nabsorb {a.absorb}\nscenario {a.scenario}\n"
    + "".join(f"Ta_{n} {TA[n] + 273.15}\nAv_{n} {Av}\n" for n, _, _, _, Av, _ in [(i[0], 0, 0, 0, i[4], 0) for i in info])
    + "".join(f"htc_{n} " + " ".join(f"{u:g}:{h:.5g}" for u, h in TAB[n]) + "\n" for n, _, _ in g.BUNDLES),
    encoding="utf-8")

# сводка
print(f"m = {MDOT:.1f} кг/с, U в газоходе ~ {U0:.1f} м/с")
print("пучок   L, м   f_x, 1/м  f_y, 1/м  Av, 1/м  Ta, °C")
for n, L, fx, fy, Av, Ta in info:
    print(f"{n:5s} {L:6.3f} {fx:9.2f} {fy:9.2f} {Av:8.2f} {Ta:6.0f}")
for n, _, _ in g.BUNDLES:
    hr, eg, ed = h_rad(n)
    print(f"{n}: излучение h = {hr:.1f} Вт/(м²·К) (газ eps = {eg:.3f}, пыль eps = {ed:.3f})")
print("htc(U):", ", ".join(f"{u:g}:{h:.0f}" for u, h in htc_table()))
