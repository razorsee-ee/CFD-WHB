"""Слежение за расчётом котла: графики по итерациям (png + html с автообновлением).

python model/monitor.py <папка_кейса> [--loop 30] [--out <папка_для_картинок>]

Рисует: невязки; температуры газа (вход газохода внизу, перед испарителем, на выходе);
среднюю скорость Ux и долю газа через каждый пучок; перепад давления вход-выход.
С --loop N перерисовывает каждые N секунд, пока не остановите (Ctrl+C).
Открыть в браузере (Windows):  explorer.exe "$(cygpath -w <папка>/monitor.html)"
"""
import re
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).parent))
import geometry as g

args = sys.argv[1:]
loop = 0
out = None
if "--out" in args:
    i = args.index("--out")
    out = Path(args[i + 1])
    del args[i:i + 2]
if "--loop" in args:
    i = args.index("--loop")
    loop = int(args[i + 1])
    del args[i:i + 2]
case = Path(args[0])
pp = case / "postProcessing"
out = out or case
out.mkdir(parents=True, exist_ok=True)
NUM = re.compile(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?")


def info():
    d = {}
    f = case / "case_info.txt"
    if f.exists():
        for l in f.read_text(encoding="utf-8").splitlines():
            k, v = l.split(" ", 1)
            d[k] = v
    return d


def series(name, fname, col=1):
    """Склеить данные функции из всех папок времени (перезапуски), вернуть (итерации, значения)."""
    files = sorted(pp.glob(f"{name}/*/{fname}"), key=lambda p: float(p.parent.name))
    x, y = [], []
    for f in files:
        for l in f.read_text(encoding="utf-8", errors="replace").splitlines():
            if not l.strip() or l.startswith("#"):
                continue
            v = [float(t) for t in NUM.findall(l)]
            if len(v) > col:
                if x and v[0] <= x[-1]:          # перезапуск: отбросить перекрытие
                    while x and x[-1] >= v[0]:
                        x.pop(); y.pop()
                x.append(v[0]); y.append(v[col])
    return x, y


def residuals():
    files = sorted(pp.glob("residuals*/*/residuals.dat"), key=lambda p: float(p.parent.name))
    names, data = None, {}
    for f in files:
        for l in f.read_text(encoding="utf-8", errors="replace").splitlines():
            if l.startswith("# Time"):
                names = l[1:].split()[1:]
                continue
            if not l.strip() or l.startswith("#") or names is None:
                continue
            parts = l.split()
            it = float(parts[0])
            for n, v in zip(names, parts[1:]):
                try:
                    val = float(v)
                except ValueError:
                    continue
                data.setdefault(n, ([], []))
                data[n][0].append(it); data[n][1].append(val)
    return data


def draw():
    I = info()
    P_ABS = float(I.get("P_ABS", 111800)); M = float(I.get("M_GAS", 28.73)); MDOT = float(I.get("MDOT", 81.0))
    fig, ax = plt.subplots(2, 2, figsize=(14, 9))
    a = ax[0, 0]
    for n, (x, y) in residuals().items():
        if y:
            a.semilogy(x, y, label=n, lw=1)
    a.set_title("Невязки (начальные)"); a.legend(fontsize=8); a.grid(alpha=0.3, which="both")
    a = ax[0, 1]
    for nm, lab in (("T_shaftExit", "низ газохода"), ("T_beforeEvap", "перед испарителем"),
                    ("outletT", "выход котла")):
        x, y = series(nm, "surfaceFieldValue.dat")
        if y:
            a.plot(x, [v - 273.15 for v in y], label=f"{lab}: {y[-1] - 273.15:.0f} °C")
    a.axhline(700, color="gray", ls=":", lw=1); a.axhline(600, color="gray", ls="--", lw=1)
    a.set_title("Температура газа, °C (пунктир: установка 700 / 600)"); a.legend(fontsize=8); a.grid(alpha=0.3)
    a = ax[1, 0]
    A = g.BUNDLE_DEPTH * g.W
    for n, _, _ in g.BUNDLES:
        x, T = series(f"{n}_T", "volFieldValue.dat", 1)
        _, ux = series(f"{n}_T", "volFieldValue.dat", 2)
        k = min(len(T), len(ux))
        if k:
            fr = [P_ABS * M / (8314 * T[i]) * ux[i] * A / MDOT * 100 for i in range(k)]
            a.plot(x[:k], fr, label=f"{n}: {fr[-1]:.0f} %")
    a.axhline(100, color="gray", ls=":", lw=1)
    a.set_title("Доля газа через пучок, %"); a.legend(fontsize=8); a.grid(alpha=0.3)
    a = ax[1, 1]
    x, p = series("pressures", "surfaceFieldValue.dat")
    if p:
        a.plot(x, [v - P_ABS for v in p], color="tab:purple", label=f"{p[-1] - P_ABS:.0f} Па")
        a.legend(fontsize=8)
    a.set_title("Давление на входе минус на выходе, Па"); a.grid(alpha=0.3)
    for a in ax.flat:
        a.set_xlabel("итерация")
    fig.suptitle(f"{case.name}   {time.strftime('%H:%M:%S')}", fontsize=10)
    fig.tight_layout()
    fig.savefig(out / "monitor.png", dpi=90)
    plt.close(fig)
    (out / "monitor.html").write_text(
        f'<html><head><meta charset="utf-8"><meta http-equiv="refresh" content="{max(loop, 30)}">'
        f'<title>{case.name}</title></head><body style="margin:0">'
        f'<img src="monitor.png?{int(time.time())}" style="width:100%"></body></html>', encoding="utf-8")


while True:
    try:
        draw()
        print(f"{time.strftime('%H:%M:%S')} обновлено: {out / 'monitor.png'}")
    except Exception as e:      # файлы могут писаться в этот момент — попробуем в следующий раз
        print("пропуск:", e)
    if not loop:
        break
    time.sleep(loop)
