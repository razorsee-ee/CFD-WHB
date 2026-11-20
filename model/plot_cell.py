"""Velocity and temperature fields in the tube-bank check piece.

python model/plot_cell.py <png> <case1> [<case2> ...]
Cases must contain ascii fields C (writeCellCentres), U, T at the latest time
(model/cell_ascii.sh prepares that).
"""
import re
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.tri as mtri
import numpy as np


def read_field(path):
    txt = Path(path).read_text()
    m = re.search(r"internalField\s+nonuniform\s+List<(\w+)>\s*(\d+)\s*\(", txt)
    n = int(m.group(2))
    body = txt[m.end():]
    if m.group(1) == "vector":
        vals = re.findall(r"\(([^()]+)\)", body)[:n]
        return np.array([[float(v) for v in s.split()] for s in vals])
    return np.array([float(v) for v in body.split(")")[0].split()][:n])


def latest(case):
    ts = [p for p in Path(case).iterdir() if re.fullmatch(r"[0-9.e+-]+", p.name) and p.name != "0"]
    return max(ts, key=lambda p: float(p.name))


# same colour scales for all images
U_LEV = np.linspace(0, 20.5, 42)
T_LEV = np.linspace(400, 710, 63)
out = sys.argv[1]
cases = sys.argv[2:]
fig, axes = plt.subplots(2 * len(cases), 1, figsize=(14, 2.6 * 2 * len(cases)))
for i, c in enumerate(cases):
    t = latest(c)
    C = read_field(t / "C")
    U = read_field(t / "U")
    T = read_field(t / "T") - 273.15
    x, y = C[:, 0], C[:, 1]
    tri = mtri.Triangulation(x, y)
    # drop triangles that bridge over the tubes (long edges)
    xt, yt = x[tri.triangles], y[tri.triangles]
    edge = np.max(np.hypot(xt - np.roll(xt, 1, 1), yt - np.roll(yt, 1, 1)), axis=1)
    tri.set_mask(edge > 0.012)
    for j, (f, lab, cm, lv) in enumerate(((np.linalg.norm(U, axis=1), "|U|, m/s", "viridis", U_LEV),
                                           (T, "T, °C", "inferno", T_LEV))):
        ax = axes[2 * i + j]
        cs = ax.tricontourf(tri, np.clip(f, lv[0], lv[-2]), lv, cmap=cm)
        fig.colorbar(cs, ax=ax, label=lab, pad=0.01)
        ax.set_aspect("equal")
        ax.set_xlim(x.min(), min(x.max(), 1.4))
        ax.set_title(f"{Path(c).name}: {lab}", fontsize=9)
fig.tight_layout()
fig.savefig(out, dpi=110)
print("ok", out)
