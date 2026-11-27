"""Zoomed view of the hoppers under the bundles (bypass region): |U| with streamlines and T at mid-width,
skirts/plates (SKIRTS zone boxes from system/createZonesDict) drawn as hatched boxes.

python model/views_hopper.py <case_dir>        -> <case_dir>/views_hopper.png

Needs the latest written time with ascii C, U, T (as written by make_case*.py cases).
"""
import re
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.tri as mtri
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import geometry as g

X0, X1, Z0, Z1 = 8.8, 21.0, 3.8, 20.2
T_LEV = np.linspace(560, 760, 41)
U_LEV = np.linspace(0, 12, 25)


def latest(case):
    ts = [p for p in case.iterdir() if p.is_dir() and re.fullmatch(r"[0-9.e+-]+", p.name) and float(p.name) > 0]
    return max(ts, key=lambda p: float(p.name)) if ts else None


def read(path):
    txt = path.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"internalField\s+nonuniform\s+List<(\w+)>\s*(\d+)\s*\(", txt)
    if not m:
        raise SystemExit(f"{path}: ascii nonuniform field required")
    n, body = int(m.group(2)), txt[m.end():]
    if m.group(1) == "vector":
        a = np.array(re.findall(r"\(([^()]+)\)", body)[:n])
        return np.array([s.split() for s in a], float)
    return np.array(body.split(")")[0].split()[:n], float)


def skirt_boxes(case):
    f = case / "system" / "createZonesDict"
    if not f.exists():
        f = case / "createZonesDict"          # copied flat next to summary.json (results kept in git)
    if not f.exists():
        return []
    m = re.search(r"SKIRTS\s*\{(.*?)\}", f.read_text(), re.S)
    if not m:
        return []
    nums = [float(v) for v in re.findall(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", m.group(1))]
    return [(nums[i], nums[i + 3], nums[i + 2], nums[i + 5]) for i in range(0, len(nums) - 5, 6)]


def main(case):
    case = Path(case)
    info = dict(l.split(" ", 1) for l in (case / "case_info.txt").read_text().splitlines() if " " in l)
    res = float(info.get("RES", 0.3))
    ny = int(float(info.get("NY", 12)))
    t = latest(case)
    if t is None:
        raise SystemExit("no written time")
    C, U, T = read(t / "C"), read(t / "U"), read(t / "T") - 273.15
    x, y, z = C.T
    w = np.where(z >= g.Z_HOP, g.W, g.W_HOP_BOT + (g.W - g.W_HOP_BOT) * z / g.Z_HOP)
    sel = (y > 0) & (y < w / ny * 1.01) & (x > X0 - 1) & (x < X1 + 1) & (z > Z0 - 1) & (z < Z1 + 1)
    px, pz, Us, Ts = x[sel], z[sel], U[sel], T[sel]
    tri = mtri.Triangulation(px, pz)
    xt, zt = px[tri.triangles], pz[tri.triangles]
    edge = np.max(np.hypot(xt - np.roll(xt, 1, 1), zt - np.roll(zt, 1, 1)), axis=1)
    tri.set_mask(edge > 3 * res)
    # regular grid for streamlines, masked outside the fluid
    gx, gz = np.linspace(X0, X1, 260), np.linspace(Z0, Z1, 340)
    GX, GZ = np.meshgrid(gx, gz)
    finder = tri.get_trifinder()
    out = finder(GX, GZ) < 0
    ux = mtri.LinearTriInterpolator(tri, Us[:, 0])(GX, GZ).filled(np.nan)
    uz = mtri.LinearTriInterpolator(tri, Us[:, 2])(GX, GZ).filled(np.nan)
    ux[out] = np.nan
    uz[out] = np.nan
    boxes = skirt_boxes(case)

    fig, axes = plt.subplots(1, 2, figsize=(15, 9.5))
    for ax, (f, lev, cm, lab) in zip(axes, ((np.linalg.norm(Us, axis=1), U_LEV, "viridis", "|U|, m/s"),
                                            (Ts, T_LEV, "inferno", "T, °C"))):
        cs = ax.tricontourf(tri, np.clip(f, lev[0], lev[-2]), lev, cmap=cm)
        plt.colorbar(cs, ax=ax, label=lab, pad=0.01, shrink=0.85)
        if "|U|" in lab:
            ax.streamplot(gx, gz, np.nan_to_num(ux), np.nan_to_num(uz), density=2.2, color="w", linewidth=0.6,
                          arrowsize=0.8, broken_streamlines=True)
        for n, b0, b1 in g.BUNDLES:
            ax.add_patch(plt.Rectangle((b0, g.Z_HOP), b1 - b0, g.BUNDLE_DEPTH, fill=False,
                                       ec="lime" if n == "EVAP" else "w", lw=1))
        for bx0, bx1, bz0, bz1 in boxes:
            ax.add_patch(plt.Rectangle((bx0, max(bz0, Z0)), bx1 - bx0, bz1 - max(bz0, Z0), fc="#d0d0d0",
                                       ec="#ff3b3b", lw=1.6, hatch="////", zorder=5))
        ax.axhline(g.Z_HOP, color="w", ls=":", lw=0.8)
        ax.set_xlim(X0, X1); ax.set_ylim(Z0, Z1); ax.set_aspect("equal")
        ax.set_title(lab, fontsize=10); ax.set_xlabel("x, m (gas flow direction)"); ax.set_ylabel("z, m")
    sk = info.get("skirts", "-")
    hf = info.get("hopper2_fill", "")
    fig.suptitle(f"{case.name}: hoppers under the bundles, mid-width (iteration {t.name}); "
                 f"skirts {sk}; right hopper fill {hf}. Red hatched = plates", fontsize=10)
    fig.tight_layout()
    out_png = case / "views_hopper.png"
    fig.savefig(out_png, dpi=85)
    plt.close(fig)
    return out_png


if __name__ == "__main__":
    print(main(sys.argv[1]))
