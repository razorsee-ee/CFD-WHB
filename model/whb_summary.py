"""Сводка расчёта котла: доля газа через пучки, тепло пучков и стенок, температура пара.

python model/whb_summary.py <папка_кейса>
Мониторы — из postProcessing; тепло пучков — по полям последнего записанного времени
(T, U, V в ascii) и таблицам htc из case_info.txt.
"""
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
F = lambda k: float(info[k])
MDOT, CP, T_IN, P_ABS, M_GAS = F("MDOT"), F("CP"), F("T_IN"), F("P_ABS"), F("M_GAS")


def last_row(name, fname):
    files = sorted(pp.glob(f"{name}/*/{fname}"), key=lambda p: float(p.parent.name))
    rows = [l for l in files[-1].read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")]
    return rows[-1]


def nums(row):
    return [float(v) for v in re.findall(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", row)]


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


it = nums(last_row("outletT", "surfaceFieldValue.dat"))
T_out = it[1]
Q_tot = MDOT * CP * (T_IN - T_out)
p_in = nums(last_row("pressures", "surfaceFieldValue.dat"))[1]
print(f"Итерация {int(it[0])}: зола на стенках R = {F('wall_R'):g}, налёт на трубах R = {info.get('bundle_R', '0')} м²К/Вт; "
      f"пыль в пучки {float(info.get('dust_frac', 0.2)) * 100:.0f} %; бункеры {float(info.get('hopper_fill', 0)) * 100:.0f} %; "
      f"поглощение {info.get('absorb', '?')} 1/м; газоходы R = {info.get('duct_R', info['wall_R'])}; губка {info['scenario']}")
for nm, lab, ref in (("T_shaftExit", "Газ внизу вертикального газохода", ""),
                     ("T_beforeEvap", "Газ перед испарителем (среднее по сечению)", "   (установка ~700 °C)")):
    try:
        print(f"{lab}: {nums(last_row(nm, 'surfaceFieldValue.dat'))[1] - 273.15:.0f} °C{ref}")
    except (IndexError, StopIteration):
        pass
print(f"Газ на выходе: {T_out - 273.15:.0f} °C   (установка ~600 °C)")
print(f"Газ отдал всего: {Q_tot / 1e6:.1f} МВт   Перепад давления вход-выход: {p_in - P_ABS:.0f} Па")

A = g.BUNDLE_DEPTH * g.W
t = latest_time()
Qb = {}
if t is not None and (t / "Vc").exists():
    T, U, V = read_internal(t / "T"), read_internal(t / "U"), read_internal(t / "Vc")
    Z = cell_zones()
    for n, _, _ in g.BUNDLES:
        Ta, Av = F(f"Ta_{n}"), F(f"Av_{n}")
        Qb[n] = sum(htc(n, math.sqrt(sum(c * c for c in U[i]))) * Av * (T[i] - Ta) * V[i] for i in Z[n])
print("\nПучок   T газа, °C   Ux, м/с   доля газа через пучок   тепло, МВт")
for n, _, _ in g.BUNDLES:
    v = nums(last_row(f"{n}_T", "volFieldValue.dat"))
    Tz, ux = v[1], v[2]
    rho = P_ABS * M_GAS / (8314 * Tz)
    q = f"{Qb[n] / 1e6:8.2f}" if n in Qb else "   —"
    print(f"{n:5s} {Tz - 273.15:10.0f} {ux:10.2f} {rho * ux * A / MDOT * 100:14.0f} %        {q}")
if Qb:
    Q_sh = sum(Qb[n] for n in Qb if n != "EVAP")
    print(f"\nПароперегреватели: {Q_sh / 1e6:.2f} МВт   (установка ~7.0 МВт: 50 т/ч, 250 -> 440 °C)")
    print(f"Испаритель: {Qb['EVAP'] / 1e6:.2f} МВт   Стенки (остаток): {(Q_tot - sum(Qb.values())) / 1e6:.1f} МВт")
    # температуры пара по ступеням при 50 т/ч (противоток: пар входит в SH4)
    m_s, cp_s = 50000 / 3600, 2670.0
    Ts = 250.0
    out, mean = [], {}
    for n in ("SH4", "SH3", "SH2", "SH1"):
        Ts_in = Ts
        Ts += Qb[n] / (m_s * cp_s)
        mean[n] = (Ts_in + Ts) / 2
        out.append(f"{n}: {Ts_in:.0f}->{Ts:.0f}")
    print("Пар (50 т/ч, cp ~2.67 кДж/кг·К): " + ", ".join(out) + " °C")
    used = ", ".join(f"{n} {F(f'Ta_{n}') - 273.15:.0f}" for n in ("SH4", "SH3", "SH2", "SH1"))
    print(f"Пар в расчёте был задан (средний по ступени): {used} °C")
    (case / "ta_next.txt").write_text(",".join(f"{mean[n]:.1f}" for n in ("SH1", "SH2", "SH3", "SH4")))
print("\nДоля < 100 % — остальной газ обходит пучок (снизу, через бункер).")
