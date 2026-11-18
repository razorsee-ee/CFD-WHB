#!/bin/bash
# Расчёт котла с увязкой температуры пара: после каждого захода температуры пара по ступеням
# пересчитываются из тепла пучков (50 т/ч, противоток), следующий заход стартует с прошлого решения.
#
#   bash model/run_coupled.sh <папка> <ядер> <ячейка_м> <заходов> [аргументы make_case.py ...]
#
# Результат: <папка>_1 ... <папка>_N, в каждой summary.txt; итог — summary.txt последнего захода.

BASE=$1; NP=$2; RES=$3; NOUT=$4; shift 4
EXTRA="$*"
REPO=$(cd "$(dirname "$0")/.." && pwd)
PY=$(command -v python3 || command -v python)
export PYTHONUTF8=1 PYTHONIOENCODING=utf-8
. "$WM_PROJECT_DIR/bin/tools/RunFunctions"
NY=$("$PY" -c "print(max(6, round(4.65 / (2 * $RES))))")

TA=""
PREV=""
for k in $(seq 1 "$NOUT"); do
    DIR="${BASE}_$k"
    ITERS=$([ "$k" = 1 ] && echo "${ITERS1:-3000}" || echo "${ITERSN:-1500}")
    echo "$(date +%H:%M) заход $k/$NOUT: $DIR ${TA:+(пар: $TA)}"
    "$PY" "$REPO/model/make_case.py" "$DIR" --res "$RES" --ny "$NY" --np "$NP" --iters "$ITERS" \
        ${TA:+--ta $TA} $EXTRA > "$DIR.make.txt" 2>&1 || { cat "$DIR.make.txt"; exit 1; }
    (
        cd "$DIR" || exit 1
        runApplication blockMesh
        runApplication topoSet
        [ -n "$PREV" ] && runApplication mapFields "$PREV" -consistent -sourceTime latestTime
        runApplication decomposePar
        runParallel foamRun
        runApplication reconstructPar -latestTime
    )
    "$PY" "$REPO/model/whb_summary.py" "$DIR" > "$DIR/summary.txt" 2>&1
    cat "$DIR/summary.txt"
    # картинки (если есть matplotlib): ход расчёта и стандартные виды
    "$PY" "$REPO/model/monitor.py" "$DIR" > /dev/null 2>&1
    "$PY" "$REPO/model/views.py" "$DIR" > "$DIR/views.log" 2>&1 && echo "Виды: $DIR/views.html"
    NEXT=$(cat "$DIR/ta_next.txt" 2>/dev/null)
    # нижняя релаксация температуры пара 50/50 (иначе заходы раскачиваются)
    OLD=${TA:-413,361,312,270}
    [ -n "$NEXT" ] && TA=$("$PY" -c "o=[float(x) for x in '$OLD'.split(',')]; n=[float(x) for x in '$NEXT'.split(',')]; print(','.join(f'{(a+b)/2:.1f}' for a,b in zip(o,n)))")
    PREV="$DIR"
done
