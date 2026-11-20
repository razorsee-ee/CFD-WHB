"""Standard end-of-run views of the boiler case (png + html report), no ParaView needed.

python model/views.py <case_dir>

Uses the latest written time (T, U, p_rgh and cell centres C in ascii, written by cases from
make_case.py) and summary.json (from whb_summary.py) and draws:
  views_scheme.png — side scheme of the bundles: steam in/out temperatures and heat per stage,
                     gas share through each bundle, bulk gas temperatures in the gaps (above and
                     below the bundle bottoms), point probes; DCS values in brackets;
  views_long.png   — longitudinal section at mid-width: T, |U| with arrows, p_rgh;
  views_cross.png  — cross-section in the SH IIIa – SH II gap: T and Ux (gas under the bundles);
  views.html       — everything together + summary.txt.
Colour scales are fixed so that variants can be compared.
Open (Windows):  explorer.exe "$(cygpath -w <case_dir>/views.html)"
"""
import html
import json
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
STAGE = {"EVAP": "Evaporator", "SH1": "SH IIIb", "SH2": "SH IIIa", "SH3": "SH II", "SH4": "SH I"}
DCS_STEAM = {"SH4": (251, 291), "SH3": (290, 343), "SH2": (341, 395), "SH1": (394, 441)}
DCS_Q = {"SH4": 2.19, "SH3": 2.30, "SH2": 2.15, "SH1": 1.76}
DCS_TC = {"before_SH1": 702, "before_SH2": 681, "before_SH3": 655, "before_SH4": 621}

info = {}
for l in (case / "case_info.txt").read_text(encoding="utf-8").splitlines():
    k, v = l.split(" ", 1)
    info[k] = v
RES = float(info.get("RES", 0.3))
NY = int(float(info.get("NY", 12)))
S = json.loads((case / "summary.json").read_text(encoding="utf-8")) if (case / "summary.json").exists() else {}
Zh, Zc = g.Z_HOP, g.Z_CEIL
BX = {n: (x0, x1) for n, x0, x1 in g.BUNDLES}

# ---------------------------------------------------------------- 1. bundle scheme (not to scale)
if S:
    Q, thr = S.get("Q_MW", {}), S.get("through_pct", {})
    steam = {k: tuple(v) for k, v in S.get("steam", {}).items()}
    bulk, probes = S.get("bulk", {}), S.get("probes", {})
    order = ["EVAP", "SH1", "SH2", "SH3", "SH4"]
    gap_after = {"EVAP": "before_SH1", "SH1": "before_SH2", "SH2": "before_SH3", "SH3": "before_SH4",
                 "SH4": "after_SH4"}
    W_B, W_G, H = 1.2, 3.0, 5.0                      # scheme bundle width, gap width, bundle height
    fig, ax = plt.subplots(figsize=(18, 9))
    X = {n: 2.5 + i * (W_B + W_G) for i, n in enumerate(order)}
    x_end = X["SH4"] + W_B + W_G
    ax.plot([0, x_end + 1.5], [H + 0.15] * 2, "k-", lw=2)                       # ceiling
    ax.plot([0, x_end + 1.5], [0, 0], color="gray", ls=":", lw=1)               # bundle bottoms
    ax.text(x_end + 1.6, 0, "bundle bottoms", va="center", fontsize=8, color="gray")
    ax.fill_between([0, x_end + 1.5], -3.2, 0, color="#f3e9d2", lw=0)            # zone over hoppers
    ax.text(0.2, -3.0, "open space over the hoppers", fontsize=8, color="#8a6d3b")
    for n in order:
        x0 = X[n]
        col = "#5cb85c" if n == "EVAP" else "#d9534f"
        ax.add_patch(plt.Rectangle((x0, 0), W_B, H, color=col, alpha=0.85))
        ax.text(x0 + W_B / 2, H / 2, STAGE[n], rotation=90, ha="center", va="center", fontsize=10, color="w",
                weight="bold")
        lines = [f"{STAGE[n]}"]
        if n in steam:
            a_, b_ = steam[n]
            da, db = DCS_STEAM[n]
            lines += [f"steam {a_:.0f} → {b_:.0f} °C", f"   DCS {da} → {db}",
                      f"Q {Q.get(n, 0):.2f} MW (DCS {DCS_Q[n]})"]
        elif n in Q:
            lines += ["boiling water 250 °C", f"Q {Q[n]:.2f} MW"]
        lines.append(f"gas through: {thr.get(n, 0):.0f} %")
        ax.text(x0 + W_B / 2, H + 0.5, "\n".join(lines), ha="center", va="bottom", fontsize=8.5,
                bbox=dict(fc="w", ec=col, lw=1))
        gb = bulk.get(gap_after[n])
        xg = x0 + W_B + W_G / 2
        if gb:
            whole, above, below = gb["all"][0], gb["above"][0], gb["below"][0]
            share = gb["below"][1] / gb["all"][1] * 100 if gb["all"][1] else 0
            txt = f"bulk {whole:.0f} °C"
            if above is not None:
                txt += f"\nabove bottoms {above:.0f}"
            nxt = gap_after[n]
            if nxt in DCS_TC:
                txt += f"\nprobe {probes.get(nxt + '_mid', float('nan')):.0f}\nDCS TC {DCS_TC[nxt]}"
            ax.text(xg, H / 2, txt, ha="center", va="center", fontsize=8, color="#1f4e79")
            if below is not None and share > 0:
                ax.annotate("", (xg + 1.0, -1.0), (xg - 1.0, -1.0),
                            arrowprops=dict(arrowstyle="-|>", color="#c0392b", lw=0.8 + share / 8,
                                            mutation_scale=10 + share / 3))
                ax.text(xg, -1.5, f"{share:.0f} % of gas\nunder bundles\n{below:.0f} °C", ha="center", va="top",
                        fontsize=8, color="#c0392b")
    # inlet and outlet
    sh = probes.get("shaftmid_26"), probes.get("shaftwall_26")
    ax.annotate("", (2.3, H / 2), (0.3, H / 2), arrowprops=dict(arrowstyle="-|>", lw=2, color="k"))
    intxt = "gas from the\nvertical duct"
    if sh[0] is not None:
        intxt += f"\ncentre {sh[0]:.0f} °C\nnear wall {sh[1]:.0f}\n(DCS 725)"
    ax.text(0.2, H / 2 + 0.4, intxt, fontsize=8, va="bottom")
    ob = bulk.get("outlet", {}).get("all", [None])[0]
    ax.annotate("", (x_end + 1.5, H / 2), (x_end - 0.2, H / 2), arrowprops=dict(arrowstyle="-|>", lw=2, color="k"))
    ax.text(x_end + 0.7, H / 2 + 0.4, f"outlet\n{ob:.0f} °C\n(DCS 618)" if ob is not None else "outlet",
            ha="center", va="bottom", fontsize=9)
    # steam path
    ys = H + 3.6
    ax.annotate("", (X["SH1"], ys), (X["SH4"] + W_B, ys), arrowprops=dict(arrowstyle="-|>", color="tab:blue", lw=1.5))
    ax.text(X["SH4"] + W_B + 0.2, ys, "steam in 251 °C", color="tab:blue", va="center", fontsize=9)
    if "steam_out" in S:
        ax.text(X["SH1"] - 0.2, ys, f"steam out {S['steam_out']:.0f} °C (DCS 441)", color="tab:blue", va="center",
                ha="right", fontsize=9)
    ax.set_xlim(-0.2, x_end + 3.2); ax.set_ylim(-4.2, H + 4.6)
    ax.axis("off")
    ax.set_title(f"{case.name} (scheme, not to scale): superheaters {S.get('Q_sh_MW', 0):.2f} MW (DCS 8.4), "
                 f"gas gave {S.get('Q_gas_MW', 0):.1f} MW, Δp {S.get('dp_Pa', 0):.0f} Pa", fontsize=11)
    fig.tight_layout()
    fig.savefig(case / "views_scheme.png", dpi=100)
    plt.close(fig)


# ---------------------------------------------------------------- fields
def latest():
    ts = [p for p in case.iterdir() if p.is_dir() and re.fullmatch(r"[0-9.e+-]+", p.name) and float(p.name) > 0]
    if not ts:
        sys.exit("No written time (run did not reach a write, or reconstructPar was not run)")
    return max(ts, key=lambda p: float(p.name))


def read(path):
    txt = path.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"internalField\s+nonuniform\s+List<(\w+)>\s*(\d+)\s*\(", txt)
    if not m:
        sys.exit(f"{path}: ascii nonuniform field required")
    n, body = int(m.group(2)), txt[m.end():]
    if m.group(1) == "vector":
        return np.array([[float(v) for v in s.split()] for s in re.findall(r"\(([^()]+)\)", body)[:n]])
    return np.array([float(v) for v in body.split(")")[0].split()[:n]])


t = latest()
C, U = read(t / "C"), read(t / "U")
T = read(t / "T") - 273.15
prgh = read(t / "p_rgh") if (t / "p_rgh").exists() else None
x, y, z = C[:, 0], C[:, 1], C[:, 2]


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


# ---------- 2. longitudinal section: middle cell layer (y > 0, closest to the axis)
dy = width(z) / NY
sel = (y > 0) & (y < dy * 1.01)
px, pz = x[sel], z[sel]
panels = [(T[sel], T_LEV, "inferno", "T, °C"),
          (np.linalg.norm(U[sel], axis=1), U_LEV, "viridis", "|U|, m/s")]
if prgh is not None:
    pr = prgh[sel]
    lo, hi = np.percentile(pr, 1), np.percentile(pr, 99)
    panels.append((pr, np.linspace(lo, hi + 1e-6, 41), "coolwarm", "p_rgh (hydrostatics removed), Pa"))
fig, axes = plt.subplots(1, len(panels), figsize=(7 * len(panels), 8))
for ax, (f, lev, cm, lab) in zip(axes, panels):
    tri_plot(ax, px, pz, f, lev, cm, lab, 3 * RES)
    bundles(ax)
    if "|U|" in lab:
        Us = U[sel]
        k = np.arange(len(px))[:: max(1, len(px) // 700)]
        ax.quiver(px[k], pz[k], Us[k, 0], Us[k, 2], color="w", scale=300, width=0.002, alpha=0.8)
    ax.set_aspect("equal"); ax.set_title(lab, fontsize=10)
    ax.set_xlabel("x, m (gas flow direction)"); ax.set_ylabel("z, m")
fig.suptitle(f"{case.name}: longitudinal section at mid-width (iteration {t.name})", fontsize=11)
fig.tight_layout()
fig.savefig(case / "views_long.png", dpi=90)
plt.close(fig)

# ---------- 3. cross-section in the SH IIIa – SH II gap
xc = 0.5 * (BX["SH2"][1] + BX["SH3"][0])
# band around the plane; for cells with the same (y, z) take the closest one
# (hopper cells are skewed, there is no exact x-layer there)
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
                                        (U[sel2, 0], UX_LEV, "RdBu_r", "Ux along the boiler, m/s"))):
    tri_plot(ax, qy, qz, f, lev, cm, lab, 3 * RES)
    ax.axhline(Zh, color="w", ls="--", lw=0.8)
    ax.text(0, Zh + 0.2, "bundle bottoms", color="w", ha="center", fontsize=8)
    ax.set_aspect("equal"); ax.set_title(lab, fontsize=10); ax.set_xlabel("y, m (width)"); ax.set_ylabel("z, m")
b = S.get("bulk", {}).get("before_SH3")
if b and b["all"][1]:
    share = b["below"][1] / b["all"][1] * 100
    sub = f"gas below the bundle bottoms: {share:.0f} % of the flow (bulk {b['below'][0]:.0f} °C)"
else:
    sub = ""
fig.suptitle(f"{case.name}: section x = {xc:.2f} m (between SH IIIa and SH II). {sub}", fontsize=10)
fig.tight_layout()
fig.savefig(case / "views_cross.png", dpi=90)
plt.close(fig)

# ---------- report
summ = (case / "summary.txt").read_text(encoding="utf-8") if (case / "summary.txt").exists() else ""
imgs = "".join(f'<h3>{t_}</h3><img src="{f}" style="max-width:100%">' for f, t_ in
               (("views_scheme.png", "Bundles: steam, heat, gas"), ("views_long.png", "Longitudinal section"),
                ("views_cross.png", "Cross-section between SH IIIa and SH II"), ("monitor.png", "Convergence"))
               if (case / f).exists())
(case / "views.html").write_text(
    f'<html><head><meta charset="utf-8"><title>{case.name}</title></head><body style="font-family:sans-serif">'
    f"<h2>{case.name}</h2><pre>{html.escape(summ)}</pre>{imgs}</body></html>", encoding="utf-8")
print("done:", case / "views.html")
