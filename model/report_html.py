"""Self-contained HTML report of several runs: comparison table, deltas vs the first run, comparison charts,
and the images of every run (zoomed hopper view, scheme, sections, convergence).

python model/report_html.py <out.html> [--title T] [--note N] <label=case_dir> [<label=case_dir> ...]

Reads summary.json of each case (written by whb_summary.py) and case_info.txt. Images are embedded as
base64, so the file can be opened or sent on its own. views_hopper.png is made on the fly if missing
(needs the latest time of the case). The first case is the reference for the deltas.
Reference columns: OF-12 0.1 m night run (docs/runs/cal_0.1m_pass3_summary.txt) and DCS.
"""
import base64
import html
import io
import json
import re
import sys
from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).parent))

STAGES = [("SH4", "SH I"), ("SH3", "SH II"), ("SH2", "SH IIIa"), ("SH1", "SH IIIb")]
BUNDLE_NAMES = {"EVAP": "EVAP", "SH1": "SH IIIb", "SH2": "SH IIIa", "SH3": "SH II", "SH4": "SH I"}
GAPS = [("before_SH1", "EVAP→IIIb"), ("before_SH2", "IIIb→IIIa"), ("before_SH3", "IIIa→II"),
        ("before_SH4", "II→I"), ("after_SH4", "behind SH I")]
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
BCOL = dict(zip(("EVAP", "SH1", "SH2", "SH3", "SH4"), SERIES))   # colour follows the bundle in every chart
INK, MUTED, GRID = "#1d1d1f", "#6b6b6b", "#e4e4e4"

# OF-12, 0.1 m, LTS, pass 3 (user's night run, blueCFD) and DCS
REF = {
    "OF-12 0.1 m (night run)": {
        "T_out": 617, "steam_out": 443, "Q_sh": 8.73, "Q_gas": 15.9, "dp": 122,
        "Q": {"SH4": 2.40, "SH3": 2.19, "SH2": 2.10, "SH1": 2.03, "EVAP": 1.13},
        "through": {"EVAP": 92, "SH1": 91, "SH2": 66, "SH3": 56, "SH4": 68},
        "probes": {"SH1": 715, "SH2": 695, "SH3": 666, "SH4": 632},
    },
    "DCS": {
        "T_out": 618, "steam_out": 441, "Q_sh": 8.4,
        "Q": {"SH4": 2.19, "SH3": 2.30, "SH2": 2.15, "SH1": 1.76},
        "probes": {"SH1": 702, "SH2": 681, "SH3": 655, "SH4": 621},
    },
}


def from_case(d):
    s = json.loads((Path(d) / "summary.json").read_text(encoding="utf-8"))
    p = s.get("probes", {})
    below = {}
    for k, _ in GAPS:
        b = s.get("bulk", {}).get(k)
        if b and b["all"][1]:
            below[k] = max(0.0, b["below"][1] / b["all"][1] * 100)
    return {
        "T_out": s.get("T_out_patch"), "steam_out": s.get("steam_out"), "Q_sh": s.get("Q_sh_MW"),
        "Q_gas": s.get("Q_gas_MW"), "dp": s.get("dp_Pa"), "Q": s.get("Q_MW", {}),
        "through": s.get("through_pct", {}), "iteration": s.get("iteration"), "below": below,
        "probes": {n: p.get(f"before_{n}_mid") for n in ("SH1", "SH2", "SH3", "SH4")},
    }


def case_info(d):
    f = Path(d) / "case_info.txt"
    if not f.exists():
        return {}
    return dict(l.split(" ", 1) for l in f.read_text(encoding="utf-8").splitlines() if " " in l)


def fmt(v, nd=0):
    if v is None:
        return "—"
    return f"{v:.{nd}f}"


def dfmt(v, v0, nd=0):
    if v is None or v0 is None:
        return "—"
    d = v - v0
    if abs(d) < 0.5 * 10 ** -nd:
        return "0"
    return f"{d:+.{nd}f}"


def png_b64(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=100)
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()


def style(ax):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(MUTED)
    ax.tick_params(colors=MUTED, labelsize=8)
    ax.yaxis.grid(True, color=GRID, lw=0.8)
    ax.set_axisbelow(True)


def short(label):
    return label.split(" ", 1)[0] if re.match(r"^\w+ ", label) else label[:6]


def charts(runs):
    """Comparison charts; variants on the x axis in run order (simple -> radical)."""
    names = [short(l) for l, _, _ in runs]
    R = [r for _, _, r in runs]
    xs = list(range(len(R)))
    out = []

    # 1. key results: one bar per variant, the first (reference) dark, deltas printed on the others
    metrics = [("Q_sh", "Тепло пароперегревателей, МВт", 2), ("steam_out", "Пар на выходе, °C", 1),
               ("T_out", "Газ на выходе, °C", 1), ("dp", "Перепад вход–выход, Па", 0),
               ("Q_gas", "Тепло газа всего, МВт", 2), (("Q", "SH4"), "Тепло SH I, МВт", 2)]
    fig, axes = plt.subplots(2, 3, figsize=(15, 7.5))
    for ax, (key, title, nd) in zip(axes.flat, metrics):
        vals = [(r[key[0]].get(key[1]) if isinstance(key, tuple) else r[key]) for r in R]
        v0 = vals[0]
        good = [v for v in vals if v is not None]
        if not good:
            ax.axis("off")
            continue
        lo, hi = min(good), max(good)
        pad = max((hi - lo) * 0.35, abs(hi) * 0.004 + 10 ** -nd)
        cols = ["#184f95"] + ["#86b6ef"] * (len(vals) - 1)
        ax.bar(xs, [v if v is not None else 0 for v in vals], color=cols, width=0.62, edgecolor="white", lw=2)
        ax.set_ylim(lo - pad, hi + pad)
        for i, v in enumerate(vals):
            if v is None:
                continue
            txt = f"{v:.{nd}f}" if i == 0 else f"{v:.{nd}f}\n{dfmt(v, v0, nd)}"
            ax.text(i, v + pad * 0.06, txt, ha="center", va="bottom", fontsize=7.5, color=INK)
        ax.set_xticks(xs, names)
        ax.set_title(title, fontsize=10, color=INK, loc="left")
        style(ax)
    fig.suptitle("Основные показатели по вариантам (тёмный столбец — эталон, под значением — отличие от него)",
                 fontsize=11, color=INK)
    fig.tight_layout()
    out.append((png_b64(fig), "Основные показатели по вариантам"))

    # 2. lines across variants: gas through bundles, gas under the bundle bottoms, heat per stage
    def lines(ax, series, title, unit):
        for j, (lab, ys, c) in enumerate(series):
            ax.plot(xs, ys, "-o", color=c, lw=2, ms=6, mec="white", mew=1.5, label=lab)
            last = [(i, y) for i, y in enumerate(ys) if y is not None]
            if last:
                i, y = last[-1]
                ax.annotate(lab, (i, y), xytext=(6, 0), textcoords="offset points", va="center", fontsize=8,
                            color=INK)
        ax.set_xticks(xs, names)
        ax.set_xlim(-0.3, len(xs) - 0.3 + 0.9)
        ax.set_title(title, fontsize=10, color=INK, loc="left")
        ax.set_ylabel(unit, fontsize=8, color=MUTED)
        ax.legend(fontsize=7.5, frameon=False, ncol=5, loc="upper left", bbox_to_anchor=(0, -0.08))
        style(ax)

    fig, axes = plt.subplots(1, 3, figsize=(16, 5.6))
    lines(axes[0], [(BUNDLE_NAMES[n], [r["through"].get(n) for r in R], BCOL[n]) for n in ("EVAP", "SH1", "SH2", "SH3", "SH4")],
          "Доля газа, прошедшего через пучок", "%")
    lines(axes[1], [(lab, [r["below"].get(k) for r in R], BCOL.get(k.replace("before_", ""), SERIES[7]))
                    for k, lab in GAPS],
          "Доля газа ниже низа пучков (цвет — пучок за промежутком)", "% расхода")
    lines(axes[2], [(st, [r["Q"].get(n) for r in R], BCOL[n]) for n, st in STAGES],
          "Тепло по ступеням", "МВт")
    fig.tight_layout()
    out.append((png_b64(fig), "Распределение газа и тепла по вариантам"))
    return out


def main():
    argv = sys.argv[1:]
    out = Path(argv.pop(0))
    title, note = "Котёл-утилизатор: расчёт на OpenFOAM-14", ""
    runs = []
    while argv:
        a = argv.pop(0)
        if a == "--title":
            title = argv.pop(0)
        elif a == "--note":
            note = argv.pop(0)
        else:
            label, d = a.split("=", 1)
            runs.append((label, Path(d), from_case(d)))
    out.parent.mkdir(parents=True, exist_ok=True)
    cols = [(l, r) for l, _, r in runs] + list(REF.items())

    rows = [
        ("Газ на выходе, °C", lambda r: r.get("T_out"), 1),
        ("Пар на выходе, °C", lambda r: r.get("steam_out"), 1),
        ("Тепло SH всего, МВт", lambda r: r.get("Q_sh"), 2),
    ]
    for n, st in STAGES:
        rows.append((f"Тепло {st}, МВт", lambda r, n=n: r.get("Q", {}).get(n), 2))
    rows.append(("Тепло испарителя, МВт", lambda r: r.get("Q", {}).get("EVAP"), 2))
    rows.append(("Тепло газа всего, МВт", lambda r: r.get("Q_gas"), 2))
    for n, st in [("EVAP", "EVAP")] + [(n, st) for n, st in reversed(STAGES)]:
        rows.append((f"Газ через {st}, %", lambda r, n=n: r.get("through", {}).get(n), 0))
    for k, lab in GAPS:
        rows.append((f"Газ под пучками, {lab}, %", lambda r, k=k: r.get("below", {}).get(k), 0))
    for n, st in reversed(STAGES):
        rows.append((f"Зонд перед {st} (середина), °C", lambda r, n=n: r.get("probes", {}).get(n), 0))
    rows.append(("Перепад вход–выход, Па", lambda r: r.get("dp"), 0))

    head = "".join(f"<th>{html.escape(l)}</th>" for l, _ in cols)
    body = "\n".join("<tr><td>" + html.escape(name) + "</td>" + "".join(f"<td>{fmt(f(r), nd)}</td>" for _, r in cols)
                     + "</tr>" for name, f, nd in rows)
    r0 = runs[0][2]
    dhead = "".join(f"<th>{html.escape(l)}</th>" for l, _, _ in runs[1:])
    dbody = "\n".join("<tr><td>" + html.escape(name) + "</td>" + "".join(f"<td>{dfmt(f(r), f(r0), nd)}</td>"
                                                                          for _, _, r in runs[1:]) + "</tr>"
                      for name, f, nd in rows)

    # variant list
    vrows = []
    for label, d, r in runs:
        ci = case_info(d)
        geo = []
        if ci.get("skirts", "-") not in ("-", "None", ""):
            geo.append("листы " + ci["skirts"])
        if ci.get("hopper2_fill") and ci.get("hopper2_fill") != ci.get("hopper_fill"):
            geo.append(f"правый бункер заполнен {float(ci['hopper2_fill']) * 100:.0f} %")
        if ci.get("refine"):
            geo.append("сгущение " + ci["refine"])
        vrows.append(f"<tr><td>{html.escape(label)}</td><td>{html.escape('; '.join(geo) or 'без изменений')}</td>"
                     f"<td>{html.escape(ci.get('RES', '?'))}</td><td>{r.get('iteration')}</td>"
                     f"<td class='mut'>{html.escape(d.name)}</td></tr>")

    chart_html = "".join(f"<figure><img src='data:image/png;base64,{b}' alt='{html.escape(c)}'>"
                         f"<figcaption>{html.escape(c)}</figcaption></figure>" for b, c in charts(runs)) if len(runs) > 1 else ""

    # images of every run
    sections = []
    for i, (label, d, _) in enumerate(runs):
        if not (d / "views_hopper.png").exists():
            try:
                import views_hopper
                views_hopper.main(d)
            except BaseException as e:  # noqa: BLE001 - a missing view must not kill the report
                print(f"views_hopper {d}: {e}", file=sys.stderr)
        imgs = []
        for fn, cap in [("views_hopper.png", "Бункеры под пучками: скорость с линиями тока и температура; листы — красная штриховка"),
                        ("views_scheme.png", "Схема пучков: температуры, тепло, доли газа"),
                        ("views_long.png", "Продольный разрез по середине ширины: T, |U|, p_rgh"),
                        ("views_cross.png", "Поперечное сечение между SH IIIa и SH II"),
                        ("monitor.png", "Ход расчёта")]:
            f = d / fn
            if f.exists():
                b64 = base64.b64encode(f.read_bytes()).decode()
                imgs.append(f"<figure><img src='data:image/png;base64,{b64}' alt='{html.escape(cap)}'>"
                            f"<figcaption>{cap}</figcaption></figure>")
        st = d / "summary.txt"
        pre = f"<details><summary>Полная сводка</summary><pre>{html.escape(st.read_text(encoding='utf-8'))}</pre></details>" \
            if st.exists() else ""
        sections.append(f"<details class='run'{' open' if i == 0 else ''}><summary>{html.escape(label)}</summary>"
                        f"{''.join(imgs)}{pre}</details>")

    out.write_text(f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>WHB OF-14 results</title>
<style>
:root {{ --bg:#fff; --fg:#1d1d1f; --mut:#666; --line:#ddd; --head:#f3f3f5; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#1b1b1d; --fg:#e8e8ea; --mut:#999; --line:#3a3a3d; --head:#26262a; }} }}
body {{ background:var(--bg); color:var(--fg); font:15px/1.45 system-ui, sans-serif; margin:0 auto; max-width:1500px; padding:16px; }}
h1 {{ font-size:22px; margin:0 0 4px; }} h2 {{ font-size:18px; margin:28px 0 6px; }} .mut {{ color:var(--mut); }}
.tw {{ overflow-x:auto; }} table {{ border-collapse:collapse; margin:12px 0; }}
th, td {{ border-bottom:1px solid var(--line); padding:5px 12px; text-align:right; white-space:nowrap; }}
th {{ background:var(--head); position:sticky; top:0; }} td:first-child, th:first-child {{ text-align:left; }}
table.v td {{ text-align:left; white-space:normal; }}
figure {{ margin:18px 0; }} img {{ max-width:100%; background:#fff; border-radius:4px; }} figcaption {{ color:var(--mut); font-size:13px; }}
details.run {{ border:1px solid var(--line); border-radius:6px; padding:6px 12px; margin:10px 0; }}
details.run > summary {{ font-weight:600; cursor:pointer; padding:4px 0; }}
pre {{ background:var(--head); padding:12px; overflow-x:auto; font-size:12px; }}
</style></head><body>
<h1>{html.escape(title)}</h1>
<div class="mut">{html.escape(note) + '<br>' if note else ''}Отложения 0.08 / 0.10 / 0.05 м²·К/Вт, сценарий A, LTS.
Эталон для отличий — «{html.escape(runs[0][0])}». Сформировано {datetime.now():%d.%m.%Y %H:%M}.</div>
<h2>Варианты</h2>
<div class="tw"><table class="v"><tr><th>Вариант</th><th>Что изменено</th><th>Сетка, м</th><th>Итерация</th><th>Кейс</th></tr>
{''.join(vrows)}</table></div>
<h2>Результаты</h2>
<div class="tw"><table><tr><th></th>{head}</tr>
{body}
</table></div>
<p class="mut">Зонды DCS — термопары с неизвестным положением (ориентир). SH1…SH4 в модели = SH IIIb, IIIa, II, I (по газу).
«Газ под пучками» — доля расхода ниже отметки низа пучков (z 13.11) в промежутке.</p>
{f'<h2>Отличие от эталона</h2><div class="tw"><table><tr><th></th>{dhead}</tr>{dbody}</table></div>' if len(runs) > 1 else ''}
{f'<h2>Графики сравнения</h2>{chart_html}' if chart_html else ''}
<h2>Картинки по вариантам</h2>
<p class="mut">Нажмите на вариант, чтобы раскрыть. Цветовые шкалы одинаковые во всех вариантах.</p>
{''.join(sections)}
</body></html>
""", encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
