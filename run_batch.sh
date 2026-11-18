#!/bin/bash
# Серия расчётов котла по очереди: запустил и ушёл.
#
#   bash run_batch.sh [ядер]
#
# 1) whb_03_B  — ячейка 0.3 м, губка B (по CFD куска пучка)
# 2) whb_03_A  — ячейка 0.3 м, губка A (по корреляциям)
# 3) whb_015_B — ячейка 0.15 м, губка B
# Считается прямо в окне (без фона): окно MSYS2 не закрывать.
# В каждой папке: summary.txt и DONE; в конце — $FOAM_RUN/BATCH_DONE и общая
# сводка $FOAM_RUN/batch_summary.txt.

NP=${1:-8}
ITERS=${ITERS:-4000}
CASES=${CASES:-"whb_03_B:0.3:B whb_03_A:0.3:A whb_015_B:0.15:B"}
REPO=$(cd "$(dirname "$0")" && pwd)
PY=$(command -v python3 || command -v python)
export PYTHONUTF8=1 PYTHONIOENCODING=utf-8   # Windows: иначе кириллица в выводе роняет Python

[ -z "$WM_PROJECT_DIR" ] && { echo "Не видно OpenFOAM: запускайте из терминала blueCFD"; exit 1; }
[ -z "$PY" ] && { echo "Нет python"; exit 1; }
[ -z "$FOAM_RUN" ] && { echo "Не задан FOAM_RUN"; exit 1; }

for spec in $CASES; do
    d=${spec%%:*}
    if [ -e "$FOAM_RUN/$d" ]; then
        echo "Папка $FOAM_RUN/$d уже есть, удалите: rm -rf $FOAM_RUN/$d"
        exit 1
    fi
done
rm -f "$FOAM_RUN/BATCH_DONE" "$FOAM_RUN/batch_summary.txt"
echo "Серия ($NP ядер, $ITERS итераций): $CASES в $FOAM_RUN"
echo "Считается прямо в этом окне. Окно НЕ закрывать."

for spec in $CASES; do
    IFS=: read -r d res sc <<< "$spec"
    DIR="$FOAM_RUN/$d"
    echo
    echo "$(date +%H:%M) ===== $d: ячейка $res м, губка $sc"
    NY=$("$PY" -c "print(max(6, round(4.65 / (2 * $res))))")
    if ! "$PY" "$REPO/model/make_case.py" "$DIR" --res "$res" --ny "$NY" --np "$NP" \
            --iters "$ITERS" --scenario "$sc" > "$FOAM_RUN/$d.make.txt" 2>&1; then
        echo "ОШИБКА при создании кейса:"
        cat "$FOAM_RUN/$d.make.txt"
        echo "===== $d: ОШИБКА при создании кейса, см. $FOAM_RUN/$d.make.txt" >> "$FOAM_RUN/batch_summary.txt"
        continue
    fi
    (cd "$DIR" && bash ./Allrun 2>&1 | tee log.Allrun)
    "$PY" "$REPO/model/whb_summary.py" "$DIR" > "$DIR/summary.txt" 2>&1
    date > "$DIR/DONE"
    cat "$DIR/summary.txt"
    { echo "===== $d (ячейка $res м, губка $sc)"; cat "$DIR/summary.txt"; echo; } >> "$FOAM_RUN/batch_summary.txt"
done
date > "$FOAM_RUN/BATCH_DONE"
echo
echo "$(date +%H:%M) ===== серия закончена. Итог: cat $FOAM_RUN/batch_summary.txt"
