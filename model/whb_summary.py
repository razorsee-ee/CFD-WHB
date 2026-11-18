"""Сводка расчёта котла: какая доля газа идёт через пучки, температуры, перепад давления.

python model/whb_summary.py <папка_кейса>
Читает postProcessing (последние записанные значения). Числа — средние по зоне пучка.
"""
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent))
import geometry as g

case = Path(sys.argv[1])
pp = case / "postProcessing"
P_ABS = 101325 + 12000
M_GAS = 28.73
MDOT = 10149.0 * M_GAS / 3600


def last_row(name, fname):
    files = sorted(pp.glob(f"{name}/*/{fname}"), key=lambda p: float(p.parent.name))
    rows = [l for l in files[-1].read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")]
    return rows[-1]


def nums(row):
    return [float(v) for v in re.findall(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", row)]


it = nums(last_row("outletT", "surfaceFieldValue.dat"))
print(f"Итерация {int(it[0])}")
print(f"Температура газа на выходе (по расходу): {it[1] - 273.15:.0f} °C")
p_in = nums(last_row("pressures", "surfaceFieldValue.dat"))[1]
print(f"Давление на входе выше, чем на выходе, на: {p_in - P_ABS:.0f} Па")
A = g.BUNDLE_DEPTH * g.W
print("\nПучок   T газа, °C   Ux, м/с   доля газа через пучок")
for n, _, _ in g.BUNDLES:
    v = nums(last_row(f"{n}_T", "volFieldValue.dat"))
    T, ux = v[1], v[2]
    rho = P_ABS * M_GAS / (8314 * T)
    print(f"{n:5s} {T - 273.15:10.0f} {ux:10.2f} {rho * ux * A / MDOT * 100:12.0f} %")
print("\nДоля < 100 % — остальной газ обходит пучок (снизу, через бункер).")
