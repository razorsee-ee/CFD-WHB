"""Result of the tube-bank check: pressure drop and heat removed.

python model/cell_result.py [--from T] <case> [<case> ...]
Steady case - last values; transient - time average from T
(default: second half of the run). Case parameters from case_info.txt.
"""
import math
import sys
from pathlib import Path

args = sys.argv[1:]
t_from = None
if args and args[0] == "--from":
    t_from = float(args[1])
    args = args[2:]


def table(path):
    return [[float(v) for v in l.split()] for l in Path(path).read_text().splitlines()
            if l.strip() and not l.startswith("#")]


def info(case):
    d = {"ncol": 1, "ntubes": 12, "T_IN": 973.15, "T_TUBE": 673.15, "CP": 1200.0,
         "S1": 0.1, "DZ": 0.01, "P_ABS": 113325.0}
    f = Path(case) / "case_info.txt"
    if f.exists():
        for l in f.read_text().split("\n"):
            if l.strip():
                k, v = l.split()
                d[k] = float(v)
    return d


print(f"{'case':26s} {'time/iter':>10s} {'dp, Pa':>7s} {'dp min..max':>13s} {'Tout, C':>8s} "
      f"{'Q, kW/m2':>9s} {'htc, W/m2K':>9s}")
for c in args:
    I = info(c)
    pp = Path(c) / "postProcessing"
    io = table(next(pp.glob("io/*/surfaceFieldValue.dat")))
    fl = table(next(pp.glob("flow/*/surfaceFieldValue.dat")))
    to = table(next(pp.glob("Tout/*/surfaceFieldValue.dat")))
    t_end = io[-1][0]
    transient = t_end < 10           # transient cases run in seconds
    t0 = (t_from if t_from is not None else t_end / 2) if transient else t_end
    sel = lambda tab: [r[1] for r in tab if r[0] >= t0 - 1e-12]
    p, m, T = sel(io), sel(fl), sel(to)
    dp = sum(p) / len(p) - I["P_ABS"]
    mdot = -sum(m) / len(m)
    Tout = sum(T) / len(T)
    Q = mdot * I["CP"] * (I["T_IN"] - Tout)
    width = I["ncol"] * I["S1"]
    A = I["ncol"] * I["ntubes"] * math.pi * 0.038 * I["DZ"]
    d1, d2 = I["T_IN"] - I["T_TUBE"], Tout - I["T_TUBE"]
    alpha = Q / (A * (d1 - d2) / math.log(d1 / d2))
    tlab = f"{t0:.2f}-{t_end:.2f}s" if transient else f"{int(t_end)}"
    print(f"{Path(c).name:26s} {tlab:>10s} {dp:7.1f} {min(p) - I['P_ABS']:6.0f}..{max(p) - I['P_ABS']:<6.0f} "
          f"{Tout - 273.15:8.1f} {Q / (width * I['DZ']) / 1e3:9.1f} {alpha:9.1f}")
