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
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import geometry as g

ap = argparse.ArgumentParser()
ap.add_argument("case")
ap.add_argument("--res", type=float, default=0.3, help="размер ячейки в сечении, м")
ap.add_argument("--ny", type=int, default=12, help="ячеек по ширине")
ap.add_argument("--np", type=int, default=4, help="число процессов")
ap.add_argument("--iters", type=int, default=3000)
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
P_ABS = 101325 + 12000          # 120 мбар(и) на входе, Па
M_GAS = 28.5                    # кг/кмоль (дымовой газ с H2O, оценка)
NM3_H = 230000
RHO_N = M_GAS / 22.414
MDOT = NM3_H * RHO_N / 3600     # кг/с
T_IN = 750 + 273.15
T_WALL = 250 + 273.15
CP = 1200.0
MU = 3.9e-5
PR = 0.72
K_GAS = 0.066                   # теплопроводность газа ~650 °C, Вт/(м·К)

# Температура «окружения» для пучков: пар (противоток 250 -> 440 °C, поровну по ступеням)
TA = {"EVAP": 250, "SH4": 270, "SH3": 312, "SH2": 361, "SH1": 413}

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

blocks = [
    # имя, (p0, p1, p2, p3) против часовой в (x, z); (n1, grading1), (n2, grading2)
    ("incl", (g.BEND_INNER, g.BEND_OUTER, g.INLET_OUTER, g.INLET_INNER), (ns, "1"), (n_incl, "1")),
    ("shaft", ((0, Zc), (g.SHAFT, Zc), g.BEND_OUTER, g.BEND_INNER), (ns, "1"), (n_shaft, "1")),
    ("col", ((0, Zh), (g.SHAFT, Zh), (g.SHAFT, Zc), (0, Zc)), (ns, "1"), (nz_b, "1")),
    ("left", ((g.SHAFT, Zh), (g.X_APEX, Zh), (g.X_APEX, Zc), (g.SHAFT, Zc)), grading_spec(sec_left), (nz_b, "1")),
    ("right", ((g.X_APEX, Zh), (g.X_RIGHT, Zh), (g.X_RIGHT, Zc), (g.X_APEX, Zc)), grading_spec(sec_right), (nz_b, "1")),
    ("trans", ((g.X_RIGHT, Zh), (g.X_OUT, g.Z_OUT_BOT), (g.X_OUT, g.Z_OUT_TOP), (g.X_RIGHT, Zc)), (n_out, "1"), (nz_b, "1")),
    ("ext", ((g.X_OUT, g.Z_OUT_BOT), (xo_end, g.Z_OUT_BOT), (xo_end, g.Z_OUT_TOP), (g.X_OUT, g.Z_OUT_TOP)), (n_ext, "1"), (nz_b, "1")),
    ("hop1a", ((g.HOP1_BOT[0], 0), (split1, 0), (g.SHAFT, Zh), (0, Zh)), (ns, "1"), (nz_h, "1")),
    ("hop1b", ((split1, 0), (g.HOP1_BOT[1], 0), (g.X_APEX, Zh), (g.SHAFT, Zh)), grading_spec(sec_left), (nz_h, "1")),
    ("hop2", ((g.HOP2_BOT[0], 0), (g.HOP2_BOT[1], 0), (g.X_RIGHT, Zh), (g.X_APEX, Zh)), grading_spec(sec_right), (nz_h, "1")),
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
faces_inlet, faces_outlet = [], []
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
EU = 0.25                                        # Эйлер на ряд (коридорный пучок, Re ~ 4e3)


def htc_table():
    rho = P_ABS * M_GAS / (8314.0 * (650 + 273.15))
    nu = MU / rho
    rows = []
    for U in [0, 0.25, 0.5, 1, 1.5, 2, 3, 4, 5, 6, 7, 8, 10, 12, 15, 20, 30]:
        Re = (U / sigma) * g.D_TUBE / nu
        Nu = 0.27 * Re ** 0.63 * PR ** 0.36 if Re > 0 else 0
        rows.append((U, max(5.0, Nu * K_GAS / g.D_TUBE)))
    return rows


tab = "\n".join(f"                ({u:g} {h:.4g})" for u, h in htc_table())
models = []
info = []
for name, x0, x1 in g.BUNDLES:
    L = x1 - x0
    nt = g.TUBES[name]
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
{tab}
        );
        outOfBounds clamp;
    }}
}}
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
      I(f"type fixedValue;\nvalue uniform {T_WALL:.2f};"))
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
writeFormat     binary;
writePrecision  8;
writeCompression off;
timeFormat      general;
timePrecision   6;
runTimeModifiable true;

functions
{{
    #includeFunc residuals(p_rgh, U, h, k, epsilon)

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

# сводка
print(f"m = {MDOT:.1f} кг/с, U в газоходе ~ {U0:.1f} м/с")
print("пучок   L, м   f_x, 1/м  f_y, 1/м  Av, 1/м  Ta, °C")
for n, L, fx, fy, Av, Ta in info:
    print(f"{n:5s} {L:6.3f} {fx:9.2f} {fy:9.2f} {Av:8.2f} {Ta:6.0f}")
print("htc(U):", ", ".join(f"{u:g}:{h:.0f}" for u, h in htc_table()))
