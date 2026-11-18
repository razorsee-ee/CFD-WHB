"""Картинки геометрии v0: вид сбоку с размерами и 3D-вид.

python model/plot_geometry.py [папка_для_png] [эскиз.png для наложения]
"""
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

sys.path.insert(0, str(Path(__file__).parent))
import geometry as g

out = Path(sys.argv[1] if len(sys.argv) > 1 else "docs/img")
out.mkdir(parents=True, exist_ok=True)

pts = np.array([g.P[k] for k in g.OUTLINE])
closed = np.vstack([pts, pts[:1]])
COL = {"EVAP": "tab:green"}


def side(ax, dims=True):
    ax.fill(pts[:, 0], pts[:, 1], color="#dfe9f5")
    ax.plot(closed[:, 0], closed[:, 1], "k-", lw=1.8)
    ot, ob = g.P["outlet_top"], g.P["outlet_bot"]
    ext = ot[0] + g.OUTLET_EXTENSION
    ax.fill([ot[0], ext, ext, ob[0]], [ot[1], ot[1], ob[1], ob[1]], color="#eeeeee")
    ax.plot([ot[0], ext], [ot[1]] * 2, "k--", lw=1)
    ax.plot([ob[0], ext], [ob[1]] * 2, "k--", lw=1)
    ax.text(ot[0] + 0.5, (ot[1] + ob[1]) / 2, "продление\nвыхода → p", va="center", fontsize=8)
    for n, x0, x1, z0, z1 in g.BUNDLES:
        ax.add_patch(plt.Rectangle((x0, z0), x1 - x0, z1 - z0,
                                   color=COL.get(n, "tab:red"), alpha=0.6))
        ax.text((x0 + x1) / 2, z1 + 0.3, n, ha="center", fontsize=7)
    i0, i1 = g.P["inlet_outer"], g.P["inlet_inner"]
    ax.plot([i0[0], i1[0]], [i0[1], i1[1]], color="tab:blue", lw=4)
    ax.annotate("ВХОД\nm = 82 кг/с, 750 °C", ((i0[0] + i1[0]) / 2, (i0[1] + i1[1]) / 2),
                (-14, 40), fontsize=9, color="tab:blue", arrowprops=dict(arrowstyle="->"))
    if dims:
        def dim(a, b, txt, off):
            ax.annotate("", a, b, arrowprops=dict(arrowstyle="<->", color="gray", lw=0.8))
            ax.text((a[0] + b[0]) / 2 + off[0], (a[1] + b[1]) / 2 + off[1], txt,
                    fontsize=8, color="dimgray", ha="center")
        dim((-1.5, 0), (-1.5, 33.7), "33.7", (-0.9, 0))
        dim((0, 25), (3.63, 25), f"{3.63:.1f}", (0, 0.4))
        z_gap = g.BUNDLES[0][3]
        dim((10.26, 12.89), (10.26, z_gap), f"{z_gap - 12.89:.1f}", (0.8, -0.2))
        dim((21.5, 0), (21.5, z_gap), f"низ пучков {z_gap:.1f}", (1.7, 0))
        dim((21.5, z_gap), (21.5, 19.81), f"{19.81 - z_gap:.1f}", (0.7, 0))
        dim((-1.5, 0), (22.97, 0), "", (0, 0))
        ax.text(10, -1.4, f"длина по низу {22.97 + 1.5 - 1.5:.1f} от левой стенки газохода", fontsize=8,
                color="dimgray", ha="center")
    ax.set_aspect("equal")
    ax.grid(alpha=0.3)
    ax.set_xlabel("x, м (по ходу газа)")
    ax.set_ylabel("z, м")


fig, ax = plt.subplots(figsize=(11, 13))
side(ax)
ax.set_title(f"WHB, геометрия v0 (с эскиза, масштаб по 33.7 м), ширина {g.WIDTH} м — оценка")
fig.tight_layout()
fig.savefig(out / "geometry_v0_side.png", dpi=110)

# Наложение на эскиз (проверка масштаба)
if len(sys.argv) > 2:
    from PIL import Image
    im = np.asarray(Image.open(sys.argv[2]).convert("L"))
    s = 33.7 / (793 - 218)
    H, W = im.shape
    fig, ax = plt.subplots(figsize=(8, 10))
    ax.imshow(im, cmap="gray", extent=(-240 * s, (W - 240) * s, (793 - H) * s, 793 * s))
    ax.plot(closed[:, 0], closed[:, 1], "c-", lw=1.5)
    for n, x0, x1, z0, z1 in g.BUNDLES:
        ax.add_patch(plt.Rectangle((x0, z0), x1 - x0, z1 - z0, fill=False, ec="b"))
    fig.savefig(out / "geometry_v0_overlay.png", dpi=90)

# 3D: профиль, вытянутый на ширину; бункеры сужаются к дну по y
def half_w(z):
    if z >= g.HOPPER_TOP_Z:
        return g.WIDTH / 2
    t = z / g.HOPPER_TOP_Z
    return (g.HOPPER_BOTTOM_WIDTH + t * (g.WIDTH - g.HOPPER_BOTTOM_WIDTH)) / 2


fig = plt.figure(figsize=(12, 10))
ax = fig.add_subplot(projection="3d")
faces = []
n = len(pts)
for i in range(n):
    (x0, z0), (x1, z1) = pts[i], pts[(i + 1) % n]
    if g.OUTLINE[i] in ("outlet_top", "inlet_inner"):
        continue  # открытые грани: выход и вход
    faces.append([(x0, -half_w(z0), z0), (x1, -half_w(z1), z1),
                  (x1, half_w(z1), z1), (x0, half_w(z0), z0)])
ax.add_collection3d(Poly3DCollection(faces, facecolor="#9db7d5", edgecolor="k",
                                     lw=0.4, alpha=0.25))
back = [(x, half_w(z), z) for x, z in pts]
ax.add_collection3d(Poly3DCollection([back], facecolor="#9db7d5", edgecolor="k",
                                     lw=0.6, alpha=0.15))
for nme, x0, x1, z0, z1 in g.BUNDLES:
    w = g.WIDTH / 2
    box = [[(x0, -w, z0), (x1, -w, z0), (x1, -w, z1), (x0, -w, z1)],
           [(x0, w, z0), (x1, w, z0), (x1, w, z1), (x0, w, z1)],
           [(x0, -w, z0), (x1, -w, z0), (x1, w, z0), (x0, w, z0)],
           [(x0, -w, z0), (x0, w, z0), (x0, w, z1), (x0, -w, z1)],
           [(x1, -w, z0), (x1, w, z0), (x1, w, z1), (x1, -w, z1)]]
    ax.add_collection3d(Poly3DCollection(box, facecolor=COL.get(nme, "tab:red"),
                                         edgecolor="k", lw=0.3, alpha=0.7))
i0, i1 = g.P["inlet_outer"], g.P["inlet_inner"]
w = g.WIDTH / 2
ax.add_collection3d(Poly3DCollection([[(i0[0], -w, i0[1]), (i1[0], -w, i1[1]),
                                       (i1[0], w, i1[1]), (i0[0], w, i0[1])]],
                                     facecolor="tab:blue", alpha=0.8))
ax.set_xlim(-7, 24); ax.set_ylim(-15.5, 15.5); ax.set_zlim(0, 46)
ax.set_box_aspect((31, 31, 46))
ax.view_init(elev=18, azim=-60)
ax.set_xlabel("x, м"); ax.set_ylabel("y, м"); ax.set_zlabel("z, м")
ax.set_title("WHB v0, 3D (синий — вход, зелёный — испаритель, красные — пароперегреватели)")
fig.tight_layout()
fig.savefig(out / "geometry_v0_3d.png", dpi=110)
print("ok", out)
