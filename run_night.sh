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
# Продолжаемая: досчитанные варианты (есть <вариант>_3/summary.txt с теплом пучков) пропускаются,
# недосчитанные удаляются и считаются заново. После сбоя — просто запустить ещё раз.

NP=${1:-8}
REPO=$(cd "$(dirname "$0")" && pwd)
[ -z "$WM_PROJECT_DIR" ] && { echo "Не видно OpenFOAM: запускайте из терминала blueCFD"; exit 1; }
[ -z "$FOAM_RUN" ] && { echo "Не задан FOAM_RUN"; exit 1; }
VARIANTS=${VARIANTS:-"n1:0.08:0.03:0.03 n2:0.08:0.03:0.05 n3:0.12:0.05:0.04"}
RES=${RES:-0.15}

done_variant() { grep -q "Пароперегреватели" "$FOAM_RUN/$1_3/summary.txt" 2>/dev/null; }
rm -f "$FOAM_RUN/NIGHT_DONE"
echo "$(date +%H:%M) ночная серия: $VARIANTS, сетка $RES м, $NP ядер. Окно НЕ закрывать."

for v in $VARIANTS; do
    IFS=: read -r d duct wall bund <<< "$v"
    echo
    if done_variant "$d"; then
        echo "$(date +%H:%M) ===== $d уже досчитан — пропускаю"
        continue
    fi
    echo "$(date +%H:%M) ===== $d: газоходы $duct, стенки $wall, трубы $bund"
    rm -rf "$FOAM_RUN/${d}_1" "$FOAM_RUN/${d}_2" "$FOAM_RUN/${d}_3" "$FOAM_RUN/${d}_"?.make.txt
    bash "$REPO/model/run_coupled.sh" "$FOAM_RUN/$d" "$NP" "$RES" 3 \
        --duct_R "$duct" --wall_R "$wall" --bundle_R "$bund"
done
rm -f "$FOAM_RUN/night_summary.txt"
for v in $VARIANTS; do
    IFS=: read -r d duct wall bund <<< "$v"
    { echo "===== $d: газоходы $duct, стенки $wall, трубы $bund"
      cat "$FOAM_RUN/${d}_3/summary.txt" 2>/dev/null || echo "(не досчитан)"; echo; } >> "$FOAM_RUN/night_summary.txt"
done
date > "$FOAM_RUN/NIGHT_DONE"
echo "$(date +%H:%M) ===== серия закончена. Итог: cat $FOAM_RUN/night_summary.txt"
