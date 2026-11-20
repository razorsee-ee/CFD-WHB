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
print(f"Юбки: {info.get('skirts', '-')}; правый бункер заполнен {float(info.get('hopper2_fill', info.get('hopper_fill', 0))) * 100:.0f} %")
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
Umax = {}
if t is not None and (t / "Vc").exists():
    T, U, V = read_internal(t / "T"), read_internal(t / "U"), read_internal(t / "Vc")
    Z = cell_zones()
    for n, _, _ in g.BUNDLES:
        Ta, Av = F(f"Ta_{n}"), F(f"Av_{n}")
        Qb[n] = sum(htc(n, math.sqrt(sum(c * c for c in U[i]))) * Av * (T[i] - Ta) * V[i] for i in Z[n])
        Umax[n] = max(math.sqrt(sum(c * c for c in U[i])) for i in Z[n])
print("\nПучок   T газа, °C   Ux, м/с   доля газа через пучок   тепло, МВт   макс |U|, м/с")
for n, _, _ in g.BUNDLES:
    v = nums(last_row(f"{n}_T", "volFieldValue.dat"))
    Tz, ux = v[1], v[2]
    rho = P_ABS * M_GAS / (8314 * Tz)
    q = f"{Qb[n] / 1e6:8.2f}" if n in Qb else "   —"
    um = f"{Umax[n]:10.1f}" if n in Umax else ""
    print(f"{n:5s} {Tz - 273.15:10.0f} {ux:10.2f} {rho * ux * A / MDOT * 100:14.0f} %        {q}   {um}")
if Qb:
    Q_sh = sum(Qb[n] for n in Qb if n != "EVAP")
    m_s = float(info.get("steam_kg_s", 50000 / 3600))
    m_sp = float(info.get("spray_kg_s", 0.0))
    h_sp = float(info.get("spray_h", 1087.0))
    print(f"\nПароперегреватели: {Q_sh / 1e6:.2f} МВт   (пар {m_s:g} кг/с + впрыск {m_sp:g} кг/с)")
    print(f"Испаритель: {Qb['EVAP'] / 1e6:.2f} МВт   Стенки (остаток): {(Q_tot - sum(Qb.values())) / 1e6:.1f} МВт")
    # Пар 40 бар: энтальпия по таблице водяного пара (кДж/кг); противоток — пар входит в SH4,
    # впрыск (если есть) — перед SH1.
    TH = [(250.4, 2800.8), (275, 2886.2), (300, 2961.7), (350, 3093.3), (400, 3214.5),
          (450, 3331.2), (500, 3446.0), (550, 3559.7), (600, 3674.9), (700, 3906.3)]

    def h_of(T):
        for (t0, h0), (t1, h1) in zip(TH, TH[1:]):
            if T <= t1:
                return h0 + (h1 - h0) * (T - t0) / (t1 - t0)
        return TH[-1][1]

    def T_of(h):
        if h <= TH[0][1]:
            return TH[0][0]
        for (t0, h0), (t1, h1) in zip(TH, TH[1:]):
            if h <= h1:
                return t0 + (t1 - t0) * (h - h0) / (h1 - h0)
        return TH[-1][0]

    h, m = TH[0][1], m_s
    out, mean = [], {}
    for n in ("SH4", "SH3", "SH2", "SH1"):
        if n == "SH1" and m_sp > 0:
            h = (m * h + m_sp * h_sp) / (m + m_sp)
            m += m_sp
        T_in = T_of(h)
        h += Qb[n] / 1e3 / m
        mean[n] = (T_in + T_of(h)) / 2
        out.append(f"{n}: {T_in:.0f}->{T_of(h):.0f}")
    print(f"Пар (40 бар, по таблице): " + ", ".join(out) + f" °C   -> на выходе {T_of(h):.0f} °C")
    print("Пар DCS (16.2 кг/с):        SH4(I): 251->291, SH3(II): 290->343, SH2(IIIa): 341->395, SH1(IIIb): 394->441 °C"
          "  | тепло DCS: 2.19 / 2.30 / 2.15 / 1.76 = 8.4 МВт")
    print("Тепло модели по ступеням:   " + " / ".join(f"{Qb[n] / 1e6:.2f}" for n in ("SH4", "SH3", "SH2", "SH1"))
          + f" = {Q_sh / 1e6:.1f} МВт")
    used = ", ".join(f"{n} {F(f'Ta_{n}') - 273.15:.0f}" for n in ("SH4", "SH3", "SH2", "SH1"))
    print(f"Пар в расчёте был задан (средний по ступени): {used} °C")
    (case / "ta_next.txt").write_text(",".join(f"{mean[n]:.1f}" for n in ("SH1", "SH2", "SH3", "SH4")))
# зонды-«термопары» (ориентир к DCS)
DCS = {"before_SH1": 702, "before_SH2": 681, "before_SH3": 655, "before_SH4": 621, "after_SH4": None}
names = info.get("probes", "").split(",") if info.get("probes") else []
pf = sorted(pp.glob("tc/*/T"), key=lambda p: float(p.parent.name))
if names and pf:
    row = [l for l in pf[-1].read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")][-1]
    vals = dict(zip(names, nums(row)[1:]))
    print("\nЗонды между пучками, °C (по газу; DCS — ориентир, термопары = SH IIIb, IIIa, II, I):")
    print("перед         верх   середина   низ     DCS")
    for gname, lab in (("before_SH1", "SH IIIb"), ("before_SH2", "SH IIIa"), ("before_SH3", "SH II"),
                       ("before_SH4", "SH I"), ("after_SH4", "за SH I")):
        v = [vals.get(f"{gname}_{h}", float("nan")) - 273.15 for h in ("top", "mid", "low")]
        d = DCS[gname]
        print(f"{lab:10s} {v[0]:7.0f} {v[1]:9.0f} {v[2]:7.0f}   {d if d else '':>5}")
    print(f"выходной газоход, середина: {vals.get('outlet_mid', float('nan')) - 273.15:.0f} °C (DCS 618)")
    if "shaftwall_22" in vals:
        print("Вертикальный газоход (DCS «vertical path» ~725 °C, термопара у стенки посередине):")
        for zz in ("22", "26", "30"):
            print(f"  z = {zz} м: у стенки {vals[f'shaftwall_{zz}'] - 273.15:.0f} °C, в центре {vals[f'shaftmid_{zz}'] - 273.15:.0f} °C")
print("\nДоля < 100 % — остальной газ обходит пучок (снизу, через бункер).")
