"""Проверка пористой модели пучка: кусок реального пучка против пористого блока.

python model/make_cell_case.py <папка> --mode resolved|porous --U0 7 [--bundle SH|EVAP]

2D-канал (x — по ходу газа, y — поперёк, z — толщина 1 ячейка, empty) высотой
в один поперечный шаг S1 = 100 мм, сверху и снизу — symmetryPlane (бесконечная
решётка). resolved: трубы 38 мм с O-сеткой до стенки (y+ ~ 1, kOmegaSST);
porous: тот же канал, пучок заменён пористой зоной с теми же f_x, Av, htc(U),
что и в модели котла (model/make_case.py).
Стенка труб и Ta пористой зоны — одна и та же температура T_TUBE.
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
ap.add_argument("--mode", choices=["resolved", "porous"], required=True)
ap.add_argument("--U0", type=float, default=7.0, help="скорость перед пучком, м/с")
ap.add_argument("--bundle", choices=["SH", "EVAP"], default="SH")
ap.add_argument("--eu", type=float, default=0.25, help="Эйлер на ряд (пористый)")
ap.add_argument("--hfac", type=float, default=1.0, help="множитель к htc (пористый)")
ap.add_argument("--ncol", type=int, default=1, help="колонн труб поперёк; >1 — периодические границы")
ap.add_argument("--transient", type=float, default=0, help="нестационарный расчёт до этого времени, с")
ap.add_argument("--iters", type=int, default=4000)
ap.add_argument("--np", type=int, default=4)
ap.add_argument("--nt", type=int, default=24, help="ячеек на четверть окружности")
ap.add_argument("--nr", type=int, default=40, help="ячеек по радиусу")
a = ap.parse_args()

P_ABS = 101325 + 12000
# Состав (пользователь): N2 66.96, CO2 14.12, H2O 16.42, O2 2.50 % об.; свойства смеси при ~650 °C
M_GAS, CP, MU, PR, K_GAS = 28.73, 1250.0, 3.7e-5, 0.72, 0.064
T_IN = 700 + 273.15
T_TUBE = 400 + 273.15
S1, D = g.S_TRANS, g.D_TUBE
r = D / 2
DZ = 0.01
X_IN, X_OUT_LEN = 0.3, 1.5

if a.bundle == "SH":   # 4 группы по 3 трубы, шаг 60 в группе, 100 между группами
    xc = [gi * 0.22 + k * 0.06 for gi in range(4) for k in range(3)]
else:                  # испаритель: 4 трубы с шагом 88
    xc = [k * 0.088 for k in range(4)]
N = len(xc)

# коробки вокруг труб: границы посередине между соседними трубами, но не дальше 0.03
boxes = []
for i, x in enumerate(xc):
    left = min(0.03, (x - xc[i - 1]) / 2) if i > 0 else 0.03
    right = min(0.03, (xc[i + 1] - x) / 2) if i < N - 1 else 0.03
    boxes.append((x - left, x + right))
x0_b, x1_b = boxes[0][0], boxes[-1][1]
L_ZONE = x1_b - x0_b

HDR = """/*--------------------------------*- C++ -*----------------------------------*\\
| OpenFOAM-12                                                                 |
\\*---------------------------------------------------------------------------*/
FoamFile
{{
    format      ascii;
    class       {cls};
    object      {obj};
}}

"""
case = Path(a.case)
if case.exists():
    shutil.rmtree(case)
for d in ("0", "constant", "system"):
    (case / d).mkdir(parents=True)


def write(rel, body, cls="dictionary"):
    (case / rel).write_text(HDR.format(cls=cls, obj=Path(rel).name) + body + "\n", encoding="utf-8")


verts, vid = [], {}
YO = 0.0   # сдвиг колонны по y


def V(x, y, z):
    y = y + YO
    key = (round(x, 9), round(y, 9), round(z, 9))
    if key not in vid:
        vid[key] = len(verts)
        verts.append(key)
    return vid[key]


blocks, edges = [], []
patches = {"inlet": [], "outlet": [], "tubes": [], "sym": []}


def block(quad, n1, n2, grad, zone="", faces=None):
    """quad: 4 точки (x, y) против часовой; x1 = p0->p1, x2 = p0->p3.
    faces: {имя_патча: [индексы сторон 0:p0p1 1:p1p2 2:p2p3 3:p3p0]}"""
    (ax, ay), (bx, by), (dx, dy) = quad[0], quad[1], quad[3]
    if (bx - ax) * (dy - ay) - (by - ay) * (dx - ax) < 0:
        raise ValueError("quad must be counter-clockwise")
    lo = [V(x, y, 0) for x, y in quad]
    hi = [V(x, y, DZ) for x, y in quad]
    blocks.append(f"    hex ({' '.join(map(str, lo + hi))}) {zone} ({n1} {n2} 1) simpleGrading {grad}")
    for pname, sides in (faces or {}).items():
        for s in sides:
            i, j = s, (s + 1) % 4
            patches[pname].append((lo[i], lo[j], hi[j], hi[i]))


n_t, n_r = a.nt, a.nr
c45 = r / math.sqrt(2)
rad_grad = 30.0     # отношение размеров ячеек: у границы коробки / у трубы

def build_column():
    global ny_io
    if a.mode == "resolved":
        for (bl, br), x in zip(boxes, xc):
            yb, yt = -S1 / 2, S1 / 2
            C = {  # точки на окружности и углы коробки
                "c_ru": (x + c45, c45), "c_lu": (x - c45, c45), "c_ld": (x - c45, -c45), "c_rd": (x + c45, -c45),
                "b_ru": (br, yt), "b_lu": (bl, yt), "b_ld": (bl, yb), "b_rd": (br, yb),
            }
            # блоки: x1 — по окружности (против часовой), x2 — радиально наружу
            # правый: c_rd -> c_ru (по дуге), наружу к b_rd/b_ru
            quads = {
                "R": (C["c_rd"], C["c_ru"], C["b_ru"], C["b_rd"]),
                "T": (C["c_ru"], C["c_lu"], C["b_lu"], C["b_ru"]),
                "L": (C["c_lu"], C["c_ld"], C["b_ld"], C["b_lu"]),
                "B": (C["c_ld"], C["c_rd"], C["b_rd"], C["b_ld"]),
            }
            # x1 вдоль дуги против часовой, x2 наружу: x1 x x2 = -z, поэтому меняем местами
            # первую сторону: берём x1 = наружу, x2 = вдоль дуги (p0 -> p3 вдоль дуги)
            for k, (p0, p1, p2, p3) in quads.items():
                q = (p0, p3, p2, p1)       # p0 -> p3(наружу) ... против часовой
                # стороны q: 0: p0->p3 (радиальная), 1: p3->p2 (сторона коробки), 2: p2->p1 (радиальная), 3: p1->p0 (дуга)
                faces = {"tubes": [3]}
                if k in ("T", "B"):
                    faces["sym"] = [1]
                block(q, n_r, n_t, f"({rad_grad} 1 1)", faces=faces)
            for (p, q_), ang in (((C["c_rd"], C["c_ru"]), 0), ((C["c_ru"], C["c_lu"]), 90),
                                 ((C["c_lu"], C["c_ld"]), 180), ((C["c_ld"], C["c_rd"]), 270)):
                mx, my = x + r * math.cos(math.radians(ang)), r * math.sin(math.radians(ang))
                for z in (0, DZ):
                    edges.append(f"    arc {V(p[0], p[1], z)} {V(q_[0], q_[1], z)} ({mx:.12g} {my + YO:.12g} {z:g})")
        # промежутки между группами
        for i in range(N - 1):
            g0, g1 = boxes[i][1], boxes[i + 1][0]
            if g1 - g0 > 1e-9:
                nx = max(2, round((g1 - g0) / 0.004))
                block(((g0, -S1 / 2), (g1, -S1 / 2), (g1, S1 / 2), (g0, S1 / 2)), nx, n_t, "(1 1 1)",
                      faces={"sym": [0, 2]})
        ny_io = n_t
    else:
        ny_io = 20
        nx = round(L_ZONE / 0.01)
        block(((x0_b, -S1 / 2), (x1_b, -S1 / 2), (x1_b, S1 / 2), (x0_b, S1 / 2)), nx, ny_io, "(1 1 1)",
              zone="bundle", faces={"sym": [0, 2]})

    # вход и выход
    block(((x0_b - X_IN, -S1 / 2), (x0_b, -S1 / 2), (x0_b, S1 / 2), (x0_b - X_IN, S1 / 2)), 40, ny_io,
          "(0.1 1 1)", faces={"sym": [0, 2], "inlet": [3]})
    block(((x1_b, -S1 / 2), (x1_b + X_OUT_LEN, -S1 / 2), (x1_b + X_OUT_LEN, S1 / 2), (x1_b, S1 / 2)), 120, ny_io,
          "(10 1 1)", faces={"sym": [0, 2], "outlet": [1]})


for _j in range(a.ncol):
    YO = _j * S1
    build_column()
YO = 0.0

vt = "\n".join(f"    ({x:.12g} {y:.12g} {z:.12g})" for x, y, z in verts)
# плоскость симметрии должна быть плоской: делим на верх и низ
Y_TOP = (a.ncol - 0.5) * S1
patches["symTop"] = [f for f in patches["sym"] if abs(verts[f[0]][1] - Y_TOP) < 1e-6]
patches["symBottom"] = [f for f in patches["sym"] if abs(verts[f[0]][1] + S1 / 2) < 1e-6]
del patches["sym"]
PER = a.ncol > 1
ptypes = {"inlet": "patch", "outlet": "patch", "tubes": "wall",
          "symTop": "cyclic;\n        neighbourPatch symBottom" if PER else "symmetryPlane",
          "symBottom": "cyclic;\n        neighbourPatch symTop" if PER else "symmetryPlane"}
bnd = []
for p, fl in patches.items():
    if not fl:
        continue
    ff = "\n".join(f"            ({' '.join(map(str, f))})" for f in fl)
    bnd.append(f"    {p}\n    {{\n        type {ptypes[p]};\n        faces\n        (\n{ff}\n        );\n    }}")
write("system/blockMeshDict", f"""convertToMeters 1;
vertices
(
{vt}
);
blocks
(
{chr(10).join(blocks)}
);
edges
(
{chr(10).join(edges)}
);
boundary
(
{chr(10).join(bnd)}
);
defaultPatch {{ name frontAndBack; type empty; }}
""")

# ---------------------------------------------------------------- физика
write("constant/physicalProperties", f"""thermoType
{{
    type heRhoThermo; mixture pureMixture; transport const; thermo hConst;
    equationOfState perfectGas; specie specie; energy sensibleEnthalpy;
}}
mixture
{{
    specie {{ molWeight {M_GAS}; }}
    thermodynamics {{ Cp {CP}; hf 0; }}
    transport {{ mu {MU}; Pr {PR}; }}
}}
""")
write("constant/momentumTransport", "simulationType RAS;\nRAS { model kOmegaSST; turbulence on; printCoeffs on; }\n")
write("constant/g", "dimensions [0 1 -2 0 0 0 0];\nvalue (0 0 0);\n", cls="uniformDimensionedVectorField")
write("constant/pRef", f"dimensions [1 -1 -2 0 0 0 0];\nvalue {P_ABS};\n", cls="uniformDimensionedScalarField")

if a.mode == "porous":
    # те же формулы, что в make_case.py
    sigma = 1 - D / S1
    EU = a.eu
    nt_ = N
    fx = nt_ * EU / (L_ZONE * sigma ** 2)
    Av = nt_ * math.pi * D / (L_ZONE * S1)   # не зависит от числа колонн   # на единицу объёма канала высотой S1
    rho = P_ABS * M_GAS / (8314.0 * (650 + 273.15))
    nu = MU / rho
    tab = []
    for U in [0, 0.25, 0.5, 1, 1.5, 2, 3, 4, 5, 6, 7, 8, 10, 12, 15, 20, 30]:
        Re = (U / sigma) * D / nu
        h = 0.27 * Re ** 0.63 * PR ** 0.36 * K_GAS / D if Re > 0 else 0
        tab.append(f"({U:g} {max(5.0, h) * a.hfac:.4g})")
    write("constant/fvModels", f"""porosity
{{
    type porosityForce;
    porosityForceCoeffs
    {{
        cellZone bundle;
        type DarcyForchheimer;
        d (0 0 0);
        f ({fx:.5g} {fx:.5g} 0.5);
        coordinateSystem {{ type cartesian; origin (0 0 0);
            coordinateRotation {{ type axesRotation; e1 (1 0 0); e3 (0 0 1); }} }}
    }}
}}
heat
{{
    type heatTransfer;
    libs ("libinterRegionFvModels.so");
    select cellZone;
    cellZone bundle;
    semiImplicit yes;
    Ta {T_TUBE:.2f};
    Av {Av:.5g};
    heatTransferCoefficientModel function1;
    htcFunc {{ type table; values ({' '.join(tab)}); outOfBounds clamp; }}
}}
""")
    (case / "porous_info.txt").write_text(f"L={L_ZONE} fx={fx} Av={Av}\n")


def field(name, cls, dim, internal, bc):
    body = "\n".join(f"    {p}\n    {{\n" + "\n".join("        " + l for l in s.strip().splitlines()) + "\n    }"
                     for p, s in bc.items())
    write(f"0/{name}", f"dimensions {dim};\ninternalField {internal};\nboundaryField\n{{\n{body}\n"
                       f"    \"sym.*\" {{ type {'cyclic' if a.ncol > 1 else 'symmetryPlane'}; }}\n"
                       "    frontAndBack { type empty; }\n}\n", cls=cls)


tubes = a.mode == "resolved"
rho_in = P_ABS * M_GAS / (8314 * T_IN)
k_in = 1.5 * (0.05 * a.U0) ** 2
om_in = math.sqrt(k_in) / (0.09 ** 0.25 * 0.01)


def bcs(inlet, outlet, wall):
    d = {"inlet": inlet, "outlet": outlet}
    if tubes:
        d["tubes"] = wall
    return d


VY = 0.02 * a.U0 if a.ncol > 1 else 0.0   # наклон потока ~1° — сломать симметрию
field("U", "volVectorField", "[0 1 -1 0 0 0 0]", f"uniform ({a.U0} 0 0)",
      bcs(f"type fixedValue; value uniform ({a.U0} {VY:g} 0);", "type pressureInletOutletVelocity; value uniform (0 0 0);",
          "type noSlip;"))
field("p", "volScalarField", "[1 -1 -2 0 0 0 0]", f"uniform {P_ABS}",
      bcs("type calculated; value $internalField;", "type calculated; value $internalField;",
          "type calculated; value $internalField;"))
field("p_rgh", "volScalarField", "[1 -1 -2 0 0 0 0]", "uniform 0",
      bcs("type fixedFluxPressure; value $internalField;", f"type prghPressure; p uniform 0; value $internalField;",
          "type fixedFluxPressure; value $internalField;"))
field("T", "volScalarField", "[0 0 0 1 0 0 0]", f"uniform {T_IN}",
      bcs(f"type fixedValue; value uniform {T_IN};", f"type inletOutlet; inletValue uniform {T_IN}; value $internalField;",
          f"type fixedValue; value uniform {T_TUBE};"))
field("k", "volScalarField", "[0 2 -2 0 0 0 0]", f"uniform {k_in:.5g}",
      bcs("type fixedValue; value $internalField;", "type inletOutlet; inletValue $internalField; value $internalField;",
          "type kLowReWallFunction; value uniform 1e-10;"))
field("omega", "volScalarField", "[0 0 -1 0 0 0 0]", f"uniform {om_in:.5g}",
      bcs("type fixedValue; value $internalField;", "type inletOutlet; inletValue $internalField; value $internalField;",
          "type omegaWallFunction; value $internalField;"))
field("nut", "volScalarField", "[0 2 -1 0 0 0 0]", "uniform 0",
      bcs("type calculated; value uniform 0;", "type calculated; value uniform 0;",
          "type nutLowReWallFunction; value uniform 0;"))
field("alphat", "volScalarField", "[1 -1 -1 0 0 0 0]", "uniform 0",
      bcs("type calculated; value uniform 0;", "type calculated; value uniform 0;",
          "type compressible::alphatWallFunction; Prt 0.85; value uniform 0;"))

if a.transient > 0:
    CTRL_TIME = (f"endTime {a.transient};\ndeltaT 1e-6;\nadjustTimeStep yes;\nmaxCo 0.5;\nmaxDeltaT 1e-5;\n"
                 f"writeControl adjustableRunTime;\nwriteInterval {a.transient / 5:g};\npurgeWrite 2;")
else:
    CTRL_TIME = f"endTime {a.iters};\ndeltaT 1;\nwriteControl timeStep;\nwriteInterval {a.iters};\npurgeWrite 1;"
write("system/controlDict", f"""application foamRun;
solver fluid;
startFrom latestTime;
startTime 0;
stopAt endTime;
{CTRL_TIME}
writeFormat binary;
runTimeModifiable true;
functions
{{
    #includeFunc residuals(p_rgh, U, h, k, omega)
    io
    {{
        type surfaceFieldValue; libs ("libfieldFunctionObjects.so");
        writeControl timeStep; writeInterval 10; log false; writeFields false;
        select patches; patches (inlet); operation areaAverage; fields (p);
    }}
    flow
    {{
        type surfaceFieldValue; libs ("libfieldFunctionObjects.so");
        writeControl timeStep; writeInterval 10; log false; writeFields false;
        select patches; patches (inlet); operation sum; fields (phi);
    }}
    Tout
    {{
        type surfaceFieldValue; libs ("libfieldFunctionObjects.so");
        writeControl timeStep; writeInterval 10; log false; writeFields false;
        select patch; patch outlet; operation average; weightField phi; fields (T);
    }}
    {"yPlus { type yPlus; libs (\"libfieldFunctionObjects.so\"); writeControl writeTime; }" if tubes else ""}
}}
""")
write("system/fvSchemes", ("ddtSchemes { default Euler; }" if a.transient > 0 else "ddtSchemes { default steadyState; }") + """
gradSchemes { default Gauss linear; }
divSchemes
{
    default none;
    div(phi,U) bounded Gauss linearUpwind grad(U);
    div(phi,K) bounded Gauss linear;
    div(phi,h) bounded Gauss linearUpwind grad(h);
    div(phi,k) bounded Gauss upwind;
    div(phi,omega) bounded Gauss upwind;
    div(((rho*nuEff)*dev2(T(grad(U))))) Gauss linear;
}
laplacianSchemes { default Gauss linear corrected; }
interpolationSchemes { default linear; }
snGradSchemes { default corrected; }
wallDist { method meshWave; }
""")
write("system/fvSolution", """solvers
{
    p_rgh { solver GAMG; smoother DIC; tolerance 1e-8; relTol 0.01; }
    "(U|h|k|omega)" { solver PBiCGStab; preconditioner DILU; tolerance 1e-9; relTol 0.1; }
""" + ("""    "rho.*" { solver diagonal; }
    p_rghFinal { solver GAMG; smoother DIC; tolerance 1e-8; relTol 0; }
    "(U|h|k|omega)Final" { solver PBiCGStab; preconditioner DILU; tolerance 1e-9; relTol 0; }
}
PIMPLE { momentumPredictor yes; nOuterCorrectors 2; nCorrectors 2; nNonOrthogonalCorrectors 1; }
relaxationFactors { equations { ".*" 1; } }
""" if a.transient > 0 else """}
PIMPLE { momentumPredictor yes; nNonOrthogonalCorrectors 1; }
relaxationFactors
{
    fields { rho 1; p_rgh 0.3; }
    equations { U 0.5; h 0.5; "(k|omega)" 0.5; }
}
"""))
write("system/decomposeParDict", f"numberOfSubdomains {a.np};\ndecomposer scotch;\n")
(case / "case_info.txt").write_text(
    f"ncol {a.ncol}\nntubes {N}\nT_IN {T_IN}\nT_TUBE {T_TUBE}\nCP {CP}\nS1 {S1}\nDZ {DZ}\nP_ABS {P_ABS}\n")
print(f"{a.mode} {a.bundle} U0={a.U0}: N={N}, L_zone={L_ZONE:.3f} м, вершин {len(verts)}, блоков {len(blocks)}")
