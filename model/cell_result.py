"""Итог проверочного расчёта куска пучка: перепад давления и снятое тепло.

python model/cell_result.py <кейс> [<кейс> ...]
Берёт последние строки postProcessing: p на входе (среднее), сумму phi, T на выходе.
"""
import math
import sys
from pathlib import Path

P_ABS = 101325 + 12000
CP = 1200.0
T_IN = 700 + 273.15
S1 = 0.1
DZ = 0.01


def last(path):
    rows = [l.split() for l in Path(path).read_text().splitlines() if l and not l.startswith("#")]
    return [float(v) for v in rows[-1]], len(rows)


def tail_spread(path, col=1, n=50):
    rows = [l.split() for l in Path(path).read_text().splitlines() if l and not l.startswith("#")]
    v = [float(r[col]) for r in rows[-n:]]
    return max(v) - min(v)


T_TUBE = 400 + 273.15
A_TUBES = {"SH": 12, "EVAP": 4}
print(f"{'кейс':28s} {'итер':>5s} {'dp, Па':>8s} {'±':>5s} {'m, г/с':>8s} {'Tвых, °C':>9s} {'Q, кВт/м²фронта':>16s} {'α, Вт/м²К':>10s}")
def alpha(c, Q, Tout):
    n = A_TUBES["EVAP" if "EVAP" in Path(c).name else "SH"]
    A = n * math.pi * 0.038 * DZ
    d1, d2 = T_IN - T_TUBE, Tout - T_TUBE
    lmtd = (d1 - d2) / math.log(d1 / d2)
    return Q / (A * lmtd)


for c in sys.argv[1:]:
    pp = Path(c) / "postProcessing"
    io, n = last(next(pp.glob("io/*/surfaceFieldValue.dat")))
    fl, _ = last(next(pp.glob("flow/*/surfaceFieldValue.dat")))
    to, _ = last(next(pp.glob("Tout/*/surfaceFieldValue.dat")))
    dp = io[1] - P_ABS
    sp = tail_spread(next(pp.glob("io/*/surfaceFieldValue.dat")))
    m = -fl[1]                     # phi на входе отрицательна (втекает), кг/с
    Q = m * CP * (T_IN - to[1])    # Вт на канал S1 x DZ
    print(f"{Path(c).name:28s} {int(io[0]):5d} {dp:8.1f} {sp:5.1f} {m * 1e3:8.3f} {to[1] - 273.15:9.1f} "
          f"{Q / (S1 * DZ) / 1e3:16.1f} {alpha(c, Q, to[1]):10.1f}")
