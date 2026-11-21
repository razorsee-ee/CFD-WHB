"""Self-contained HTML report: comparison table of several runs + reference columns + images of the main run.

python model/report_html.py <out.html> <label=case_dir> [<label=case_dir> ...]

Reads summary.json of each case (written by whb_summary.py). The images (views_*.png, monitor.png)
of the FIRST case are embedded as base64, so the file can be opened or sent on its own.
Reference columns: OF-12 0.1 m night run (docs/runs/cal_0.1m_pass3_summary.txt) and DCS.
"""
import base64
import html
import json
import sys
from datetime import datetime
from pathlib import Path

STAGES = [("SH4", "SH I"), ("SH3", "SH II"), ("SH2", "SH IIIa"), ("SH1", "SH IIIb")]

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
    return {
        "T_out": s.get("T_out_patch"), "steam_out": s.get("steam_out"), "Q_sh": s.get("Q_sh_MW"),
        "Q_gas": s.get("Q_gas_MW"), "dp": s.get("dp_Pa"), "Q": s.get("Q_MW", {}),
        "through": s.get("through_pct", {}), "iteration": s.get("iteration"),
        "probes": {n: p.get(f"before_{n}_mid") for n in ("SH1", "SH2", "SH3", "SH4")},
    }


def fmt(v, nd=0):
    if v is None:
        return "—"
    return f"{v:.{nd}f}"


def main():
    out = Path(sys.argv[1])
    out.parent.mkdir(parents=True, exist_ok=True)
    runs = []
    for arg in sys.argv[2:]:
        label, d = arg.split("=", 1)
        runs.append((label, Path(d), from_case(d)))
    cols = [(l, r) for l, _, r in runs] + list(REF.items())

    rows = [
        ("Газ на выходе, °C", lambda r: fmt(r.get("T_out"))),
        ("Пар на выходе, °C", lambda r: fmt(r.get("steam_out"))),
        ("Тепло SH всего, МВт", lambda r: fmt(r.get("Q_sh"), 2)),
    ]
    for n, st in STAGES:
        rows.append((f"Тепло {st}, МВт", lambda r, n=n: fmt(r.get("Q", {}).get(n), 2)))
    rows.append(("Тепло испарителя, МВт", lambda r: fmt(r.get("Q", {}).get("EVAP"), 2)))
    rows.append(("Тепло газа всего, МВт", lambda r: fmt(r.get("Q_gas"), 1)))
    for n, st in [("EVAP", "EVAP")] + [(n, st) for n, st in reversed(STAGES)]:
        rows.append((f"Газ через {st}, %", lambda r, n=n: fmt(r.get("through", {}).get(n))))
    for n, st in reversed(STAGES):
        rows.append((f"Зонд перед {st} (середина), °C", lambda r, n=n: fmt(r.get("probes", {}).get(n))))
    rows.append(("Перепад вход–выход, Па", lambda r: fmt(r.get("dp"))))

    head = "".join(f"<th>{html.escape(l)}</th>" for l, _ in cols)
    body = "\n".join("<tr><td>" + html.escape(name) + "</td>" + "".join(f"<td>{f(r)}</td>" for _, r in cols) + "</tr>"
                     for name, f in rows)

    imgs = []
    main_dir = runs[0][1]
    for fn, cap in [("views_scheme.png", "Схема пучков: температуры и доли газа"),
                    ("views_long.png", "Продольный разрез: T, |U|, p_rgh"),
                    ("views_cross.png", "Поперечное сечение SH IIIa–II"),
                    ("monitor.png", "Ход расчёта")]:
        f = main_dir / fn
        if f.exists():
            b64 = base64.b64encode(f.read_bytes()).decode()
            imgs.append(f"<figure><img src='data:image/png;base64,{b64}'><figcaption>{cap}</figcaption></figure>")

    summary_txt = (main_dir / "summary.txt")
    pre = html.escape(summary_txt.read_text(encoding="utf-8")) if summary_txt.exists() else ""

    out.write_text(f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>WHB OF-14 results</title>
<style>
:root {{ --bg:#fff; --fg:#1d1d1f; --mut:#666; --line:#ddd; --head:#f3f3f5; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#1b1b1d; --fg:#e8e8ea; --mut:#999; --line:#3a3a3d; --head:#26262a; }} }}
body {{ background:var(--bg); color:var(--fg); font:15px/1.45 system-ui, sans-serif; margin:0 auto; max-width:1200px; padding:16px; }}
h1 {{ font-size:22px; margin:0 0 4px; }} .mut {{ color:var(--mut); }}
.tw {{ overflow-x:auto; }} table {{ border-collapse:collapse; margin:16px 0; }}
th, td {{ border-bottom:1px solid var(--line); padding:5px 12px; text-align:right; white-space:nowrap; }}
th {{ background:var(--head); }} td:first-child, th:first-child {{ text-align:left; }}
td:nth-child(2) {{ font-weight:600; }}
figure {{ margin:24px 0; }} img {{ max-width:100%; background:#fff; }} figcaption {{ color:var(--mut); }}
pre {{ background:var(--head); padding:12px; overflow-x:auto; font-size:12px; }}
</style></head><body>
<h1>Котёл-утилизатор: расчёт на OpenFOAM-14</h1>
<div class="mut">Основной кейс: {html.escape(runs[0][0])} ({html.escape(str(main_dir))}), итерация {runs[0][2].get('iteration')}.
Отложения 0.08 / 0.10 / 0.05 м²·К/Вт, сценарий A, один заход с температурами пара из ночного прогона 0.1 м.
Сформировано {datetime.now():%d.%m.%Y %H:%M}.</div>
<div class="tw"><table><tr><th></th>{head}</tr>
{body}
</table></div>
<p class="mut">Зонды DCS — термопары с неизвестным положением (ориентир). SH1…SH4 в модели = SH IIIb, IIIa, II, I (по газу).</p>
{''.join(imgs)}
<h2>Полная сводка</h2>
<pre>{pre}</pre>
</body></html>
""", encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
