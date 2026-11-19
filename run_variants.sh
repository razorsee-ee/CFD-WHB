#!/bin/bash
# Серия вариантов переделки (юбки, уровень золы в правом бункере) на одной базе отложений.
#
#   bash run_variants.sh [ядер] [ячейка_м]
#
# Режим: пар 17.5 кг/с без впрыска (вопрос: дотягивает ли пар до 450 °C), газ — как сейчас.
# Продолжаемая, как run_night.sh: досчитанные варианты пропускаются.
# Итог: $FOAM_RUN/variants_summary.txt (короткая таблица) и сводки/виды в папках v_*_3.

NP=${1:-8}
RES=${2:-0.3}
REPO=$(cd "$(dirname "$0")" && pwd)
[ -z "$WM_PROJECT_DIR" ] && { echo "Не видно OpenFOAM: запускайте из терминала blueCFD"; exit 1; }
[ -z "$FOAM_RUN" ] && { echo "Не задан FOAM_RUN"; exit 1; }
PY=$(command -v python3 || command -v python)
export PYTHONUTF8=1 PYTHONIOENCODING=utf-8

# база отложений (м²·К/Вт) и режим
BASE=${BASE:-"--duct_R 0.12 --wall_R 0.05 --bundle_R 0.03 --steam_kg_s 17.5 --spray_kg_s 0"}
# имя | дополнительные аргументы (v_now — проверка базы в нынешнем режиме: 13 кг/с + впрыск 1 кг/с)
VARIANTS=${VARIANTS:-"
v_now|--steam_kg_s 13 --spray_kg_s 1
v_base|
v_sh4_3|--skirts sh4:3
v_sh4_5|--skirts sh4:5
v_evap_3|--skirts evap:3
v_both|--skirts evap:3,sh4:5
v_hop30|--hopper2_fill 0.3
v_hop50|--hopper2_fill 0.5
"}

done_variant() { grep -q "Пароперегреватели" "$FOAM_RUN/$1_3/summary.txt" 2>/dev/null; }

echo "$VARIANTS" | while IFS='|' read -r name extra; do
    [ -z "$name" ] && continue
    if done_variant "$name"; then echo "$(date +%H:%M) $name уже досчитан — пропускаю"; continue; fi
    echo "$(date +%H:%M) ===== $name: $extra"
    rm -rf "$FOAM_RUN/${name}_1" "$FOAM_RUN/${name}_2" "$FOAM_RUN/${name}_3"
    bash "$REPO/model/run_coupled.sh" "$FOAM_RUN/$name" "$NP" "$RES" 3 $BASE $extra > "$FOAM_RUN/$name.log" 2>&1
    grep -E "Газ на выходе|Пароперегреватели|Пар \\(" "$FOAM_RUN/${name}_3/summary.txt"
done

# короткая таблица
{
    printf "%-10s %8s %8s %8s %8s %8s %8s %8s %9s\n" вариант "SH,МВт" "пар,°C" "газ,°C" "SH2,%" "SH3,%" "SH4,%" "dp,Па" "Umax,м/с"
    echo "$VARIANTS" | while IFS='|' read -r name extra; do
        [ -z "$name" ] && continue
        f="$FOAM_RUN/${name}_3/summary.txt"
        [ -f "$f" ] || { echo "$name: не досчитан"; continue; }
        "$PY" - "$f" "$name" <<'PYEOF'
import re, sys
t = open(sys.argv[1], encoding="utf-8").read()
g = lambda p: (re.search(p, t) or [None, "?"])[1]
fr = {n: g(rf"\n{n}\s+\S+\s+\S+\s+(\d+) %") for n in ("SH2", "SH3", "SH4")}
um = max([float(x) for x in re.findall(r"%\s+\S+\s+(\d+\.\d)\s*$", t, re.M)] or [0])
print(f"{sys.argv[2]:10s} {g(r'Пароперегреватели: ([\d.]+)'):>8s} {g(r'на выходе (\d+) °C \(установка'):>8s} "
      f"{g(r'Газ на выходе: (\d+)'):>8s} {fr['SH2']:>8s} {fr['SH3']:>8s} {fr['SH4']:>8s} "
      f"{g(r'вход-выход: (-?\d+)'):>8s} {um:9.1f}")
PYEOF
    done
} > "$FOAM_RUN/variants_summary.txt"
cat "$FOAM_RUN/variants_summary.txt"
