#!/bin/bash
# Серия расчётов котла по очереди: запустил и ушёл.
#
#   bash run_batch.sh [ядер]
#
# 1) whb_03_B  — ячейка 0.3 м, губка B (по CFD куска пучка)
# 2) whb_03_A  — ячейка 0.3 м, губка A (по корреляциям)
# 3) whb_015_B — ячейка 0.15 м, губка B
# В каждой папке: summary.txt и DONE. В конце — $FOAM_RUN/BATCH_DONE и общая сводка
# $FOAM_RUN/batch_summary.txt. Окно MSYS2 не закрывать.

NP=${1:-8}
ITERS=${ITERS:-4000}
REPO=$(cd "$(dirname "$0")" && pwd)
PY=$(command -v python3 || command -v python)
export PYTHONUTF8=1 PYTHONIOENCODING=utf-8   # Windows: иначе кириллица в выводе роняет Python
[ -z "$WM_PROJECT_DIR" ] && { echo "Не видно OpenFOAM: запускайте из терминала blueCFD"; exit 1; }
[ -z "$PY" ] && { echo "Нет python"; exit 1; }

CASES=${CASES:-"whb_03_B:0.3:B whb_03_A:0.3:A whb_015_B:0.15:B"}
for spec in $CASES; do
    d=${spec%%:*}
    [ -e "$FOAM_RUN/$d" ] && { echo "Папка $FOAM_RUN/$d уже есть, удалите: rm -rf $FOAM_RUN/$d"; exit 1; }
done
rm -f "$FOAM_RUN/BATCH_DONE" "$FOAM_RUN/batch_summary.txt"

cat > "$FOAM_RUN/.batch_job.sh" <<EOF
for spec in $CASES; do
    IFS=: read d res sc <<< "\$spec"
    DIR="$FOAM_RUN/\$d"
    NY=\$("$PY" -c "print(max(6, round(4.65 / (2 * \$res))))")
    "$PY" "$REPO/model/make_case.py" "\$DIR" --res \$res --ny \$NY --np $NP --iters $ITERS --scenario \$sc \
        > "$FOAM_RUN/\$d.make.txt" 2>&1 || { echo "===== \$d: ОШИБКА при создании кейса, см. $FOAM_RUN/\$d.make.txt" >> "$FOAM_RUN/batch_summary.txt"; continue; }
    (cd "\$DIR" && ./Allrun > log.Allrun 2>&1)
    "$PY" "$REPO/model/whb_summary.py" "\$DIR" > "\$DIR/summary.txt" 2>&1
    date > "\$DIR/DONE"
    { echo "===== \$d (ячейка \$res м, губка \$sc)"; cat "\$DIR/summary.txt"; echo; } >> "$FOAM_RUN/batch_summary.txt"
done
date > "$FOAM_RUN/BATCH_DONE"
EOF
nohup bash "$FOAM_RUN/.batch_job.sh" > "$FOAM_RUN/batch.log" 2>&1 &

echo "Серия запущена ($NP ядер, $ITERS итераций): whb_03_B, whb_03_A, whb_015_B в $FOAM_RUN"
echo "Окно MSYS2 НЕ закрывать. Готово, когда есть $FOAM_RUN/BATCH_DONE"
echo "Итог: cat $FOAM_RUN/batch_summary.txt"
