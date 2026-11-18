"""Стандартные виды по окончании расчёта котла (картинки + html-отчёт), без ParaView.

python model/views.py <папка_кейса>

Берёт последнее записанное время (поля T, U, p_rgh и центры ячеек C в ascii — их пишет
кейс из make_case.py) и рисует:
  views_long.png  — продольный разрез посередине ширины: T, |U| со стрелками, p_rgh;
  views_cross.png — поперечный разрез в промежутке SH2–SH3: T и скорость вдоль котла Ux
                    (видно, сколько газа идёт над бункером под пучками);
  views.html      — всё вместе + summary.txt.
Шкалы фиксированные, чтобы варианты можно было сравнивать.
Открыть (Windows):  explorer.exe "$(cygpath -w <папка>/views.html)"
"""
import html
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.tri as mtri
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import geometry as g

case = Path(sys.argv[1])
T_LEV = np.linspace(250, 760, 52)
U_LEV = np.linspace(0, 15, 31)
UX_LEV = np.linspace(-6, 15, 43)

info = {}
for l in (case / "case_info.txt").read_text(encoding="utf-8").splitlines():
    k, v = l.split(" ", 1)
    info[k] = v
RES = float(info.get("RES", 0.3))
NY = int(float(info.get("NY", 12)))


def latest():
    ts = [p for p in case.iterdir() if p.is_dir() and re.fullmatch(r"[0-9.e+-]+", p.name) and float(p.name) > 0]
    if not ts:
        sys.exit("Нет записанного времени (расчёт не дошёл до записи или не собран reconstructPar)")
    return max(ts, key=lambda p: float(p.name))


def read(path):
    txt = path.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"internalField\s+nonuniform\s+List<(\w+)>\s*(\d+)\s*\(", txt)
    if not m:
        sys.exit(f"{path}: нужен ascii nonuniform")
    n, body = int(m.group(2)), txt[m.end():]
    if m.group(1) == "vector":
        return np.array([[float(v) for v in s.split()] for s in re.findall(r"\(([^()]+)\)", body)[:n]])
    return np.array([float(v) for v in body.split(")")[0].split()[:n]])


t = latest()
C, U = read(t / "C"), read(t / "U")
T = read(t / "T") - 273.15
prgh = read(t / "p_rgh") if (t / "p_rgh").exists() else None
x, y, z = C[:, 0], C[:, 1], C[:, 2]
Zh = g.Z_HOP


def width(zz):
    return np.where(zz >= Zh, g.W, g.W_HOP_BOT + (g.W - g.W_HOP_BOT) * zz / Zh)


def tri_plot(ax, px, pz, f, lev, cmap, label, edge):
    tri = mtri.Triangulation(px, pz)
    xt, zt = px[tri.triangles], pz[tri.triangles]
    e = np.max(np.hypot(xt - np.roll(xt, 1, 1), zt - np.roll(zt, 1, 1)), axis=1)
    tri.set_mask(e > edge)
    cs = ax.tricontourf(tri, np.clip(f, lev[0], lev[-2]), lev, cmap=cmap, extend="neither")
    plt.colorbar(cs, ax=ax, label=label, pad=0.01, shrink=0.9)
    return tri


def bundles(ax):
    for n, x0, x1 in g.BUNDLES:
        ax.add_patch(plt.Rectangle((x0, Zh), x1 - x0, g.BUNDLE_DEPTH, fill=False,
                                   ec="w" if n != "EVAP" else "lime", lw=0.8))


# ---------- продольный разрез: средний слой ячеек (y > 0, ближайший к оси)
dy = width(z) / NY
sel = (y > 0) & (y < dy * 1.01)
px, pz = x[sel], z[sel]
panels = [(T[sel], T_LEV, "inferno", "T, °C"),
          (np.linalg.norm(U[sel], axis=1), U_LEV, "viridis", "|U|, м/с")]
if prgh is not None:
    pr = prgh[sel]
    lo, hi = np.percentile(pr, 1), np.percentile(pr, 99)
    panels.append((pr, np.linspace(lo, hi + 1e-6, 41), "coolwarm", "p_rgh (без гидростатики), Па"))
fig, axes = plt.subplots(1, len(panels), figsize=(7 * len(panels), 8))
for ax, (f, lev, cm, lab) in zip(axes, panels):
    tri_plot(ax, px, pz, f, lev, cm, lab, 3 * RES)
    bundles(ax)
    if "|U|" in lab:
        Us = U[sel]
        k = np.arange(len(px))[:: max(1, len(px) // 700)]
        ax.quiver(px[k], pz[k], Us[k, 0], Us[k, 2], color="w", scale=300, width=0.002, alpha=0.8)
    ax.set_aspect("equal"); ax.set_title(lab, fontsize=10)
    ax.set_xlabel("x, м (по ходу газа)"); ax.set_ylabel("z, м")
fig.suptitle(f"{case.name}: продольный разрез посередине ширины (итерация {t.name})", fontsize=11)
fig.tight_layout()
fig.savefig(case / "views_long.png", dpi=90)
plt.close(fig)

# ---------- поперечный разрез в промежутке SH2–SH3
sh2 = [b for b in g.BUNDLES if b[0] == "SH2"][0]
sh3 = [b for b in g.BUNDLES if b[0] == "SH3"][0]
xc = 0.5 * (sh2[2] + sh3[1])
x0 = xc
# полоса вокруг сечения; из ячеек с одинаковыми (y, z) — ближайшая к сечению
# (в бункере ячейки наклонные, точного слоя по x там нет)
band = np.where(np.abs(x - xc) < RES * 0.75)[0]
best = {}
for i in band:
    key = (round(y[i] / (RES * 0.25)), round(z[i] / (RES * 0.25)))
    if key not in best or abs(x[i] - xc) < abs(x[best[key]] - xc):
        best[key] = i
sel2 = np.zeros(len(x), bool)
sel2[list(best.values())] = True
qy, qz = y[sel2], z[sel2]
fig, axes = plt.subplots(1, 2, figsize=(12, 8))
for ax, (f, lev, cm, lab) in zip(axes, ((T[sel2], T_LEV, "inferno", "T, °C"),
                                        (U[sel2, 0], UX_LEV, "RdBu_r", "Ux вдоль котла, м/с"))):
    tri_plot(ax, qy, qz, f, lev, cm, lab, 3 * RES)
    ax.axhline(Zh, color="w", ls="--", lw=0.8)
    ax.text(0, Zh + 0.2, "низ пучков", color="w", ha="center", fontsize=8)
    ax.set_aspect("equal"); ax.set_title(lab, fontsize=10); ax.set_xlabel("y, м (ширина)"); ax.set_ylabel("z, м")
# доля расхода над / под низом пучков в этом сечении
ux, Tk = U[sel2, 0], T[sel2] + 273.15
rho = float(info.get("P_ABS", 111800)) * float(info.get("M_GAS", 28.73)) / (8314 * Tk)
dA = (width(qz) / NY) * RES                              # приближённая площадь ячейки в сечении
m_up = np.sum((rho * ux * dA)[qz >= Zh]); m_dn = np.sum((rho * ux * dA)[qz < Zh])
fig.suptitle(f"{case.name}: сечение x = {x0:.2f} м (между SH2 и SH3). Расход над низом пучков "
             f"{m_up / (m_up + m_dn) * 100:.0f} %, под ним {m_dn / (m_up + m_dn) * 100:.0f} % (оценка)", fontsize=10)
fig.tight_layout()
fig.savefig(case / "views_cross.png", dpi=90)
plt.close(fig)

# ---------- отчёт
summ = (case / "summary.txt").read_text(encoding="utf-8") if (case / "summary.txt").exists() else ""
imgs = "".join(f'<h3>{t_}</h3><img src="{f}" style="max-width:100%">' for f, t_ in
               (("views_long.png", "Продольный разрез"), ("views_cross.png", "Поперечный разрез между SH2 и SH3"),
                ("monitor.png", "Ход расчёта")) if (case / f).exists())
(case / "views.html").write_text(
    f'<html><head><meta charset="utf-8"><title>{case.name}</title></head><body style="font-family:sans-serif">'
    f"<h2>{case.name}</h2><pre>{html.escape(summ)}</pre>{imgs}</body></html>", encoding="utf-8")
print("готово:", case / "views.html")
