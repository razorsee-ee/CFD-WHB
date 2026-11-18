#!/bin/bash
# Ночная серия: котёл на сетке 0.15 м, пар увязан (3 захода на вариант), считается в окне.
#
#   bash run_night.sh [ядер]
#
# Варианты (м²·К/Вт): газоходы / стенки котла / налёт на трубах пучков
#   n1: 0.08 / 0.03 / 0.03
#   n2: 0.08 / 0.03 / 0.05
#   n3: 0.12 / 0.05 / 0.04
# Итог: $FOAM_RUN/night_summary.txt (сводка последнего захода каждого варианта).

NP=${1:-8}
REPO=$(cd "$(dirname "$0")" && pwd)
[ -z "$WM_PROJECT_DIR" ] && { echo "Не видно OpenFOAM: запускайте из терминала blueCFD"; exit 1; }
[ -z "$FOAM_RUN" ] && { echo "Не задан FOAM_RUN"; exit 1; }
VARIANTS=${VARIANTS:-"n1:0.08:0.03:0.03 n2:0.08:0.03:0.05 n3:0.12:0.05:0.04"}
RES=${RES:-0.15}

for v in $VARIANTS; do
    d=${v%%:*}
    if ls -d "$FOAM_RUN/${d}_"* > /dev/null 2>&1; then
        echo "Есть папки $FOAM_RUN/${d}_*, удалите: rm -rf $FOAM_RUN/${d}_*"; exit 1
    fi
done
rm -f "$FOAM_RUN/night_summary.txt" "$FOAM_RUN/NIGHT_DONE"
echo "$(date +%H:%M) ночная серия: $VARIANTS, сетка $RES м, $NP ядер. Окно НЕ закрывать."

for v in $VARIANTS; do
    IFS=: read -r d duct wall bund <<< "$v"
    echo
    echo "$(date +%H:%M) ===== $d: газоходы $duct, стенки $wall, трубы $bund"
    bash "$REPO/model/run_coupled.sh" "$FOAM_RUN/$d" "$NP" "$RES" 3 \
        --duct_R "$duct" --wall_R "$wall" --bundle_R "$bund"
    { echo "===== $d: газоходы $duct, стенки $wall, трубы $bund"; cat "$FOAM_RUN/${d}_3/summary.txt"; echo; } \
        >> "$FOAM_RUN/night_summary.txt"
done
date > "$FOAM_RUN/NIGHT_DONE"
echo "$(date +%H:%M) ===== серия закончена. Итог: cat $FOAM_RUN/night_summary.txt"
