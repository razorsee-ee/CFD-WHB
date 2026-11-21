#!/bin/bash
# Boiler run with steam-temperature coupling: after each pass the steam temperatures per stage
# are recomputed from the bundle heat (counterflow); the next pass starts from the previous solution.
#
#   bash model/run_coupled.sh <dir> <cores> <cell_m> <passes> [make_case.py arguments ...]
#
# GEN=make_case_of14.py selects the OpenFOAM-14 generator (default: make_case.py, OpenFOAM-12).
# TA=SH1,SH2,SH3,SH4 sets the steam temperatures of the first pass.
#
# Result: <dir>_1 ... <dir>_N, each with summary.txt; the final answer is summary.txt of the last pass.

BASE=$1; NP=$2; RES=$3; NOUT=$4; shift 4
EXTRA="$*"
REPO=$(cd "$(dirname "$0")/.." && pwd)
PY=$(command -v python3 || command -v python)
export PYTHONUTF8=1 PYTHONIOENCODING=utf-8
. "$WM_PROJECT_DIR/bin/tools/RunFunctions"
NY=$("$PY" -c "print(max(6, round(4.65 / (2 * $RES))))")

TA="${TA:-}"
GEN="${GEN:-make_case.py}"
PREV=""
for k in $(seq 1 "$NOUT"); do
    DIR="${BASE}_$k"
    ITERS=$([ "$k" = 1 ] && echo "${ITERS1:-3000}" || echo "${ITERSN:-1500}")
    echo "$(date +%H:%M) pass $k/$NOUT: $DIR ${TA:+(steam: $TA)}"
    "$PY" "$REPO/model/$GEN" "$DIR" --res "$RES" --ny "$NY" --np "$NP" --iters "$ITERS" \
        ${TA:+--ta $TA} $EXTRA > "$DIR.make.txt" 2>&1 || { cat "$DIR.make.txt"; exit 1; }
    (
        cd "$DIR" || exit 1
        runApplication blockMesh
        if [ -f system/createZonesDict ]; then runApplication createZones; else runApplication topoSet; fi
        [ -n "$PREV" ] && runApplication mapFields "$PREV" -consistent -sourceTime latestTime
        runApplication decomposePar
        runParallel foamRun
        runApplication reconstructPar -latestTime
    )
    "$PY" "$REPO/model/whb_summary.py" "$DIR" > "$DIR/summary.txt" 2>&1
    cat "$DIR/summary.txt"
    # images (if matplotlib is available): convergence and standard views
    "$PY" "$REPO/model/monitor.py" "$DIR" > /dev/null 2>&1
    "$PY" "$REPO/model/views.py" "$DIR" > "$DIR/views.log" 2>&1 && echo "Views: $DIR/views.html"
    NEXT=$(cat "$DIR/ta_next.txt" 2>/dev/null)
    # under-relaxation of steam temperatures 50/50 (otherwise passes oscillate)
    OLD=${TA:-413,361,312,270}
    [ -n "$NEXT" ] && TA=$("$PY" -c "o=[float(x) for x in '$OLD'.split(',')]; n=[float(x) for x in '$NEXT'.split(',')]; print(','.join(f'{(a+b)/2:.1f}' for a,b in zip(o,n)))")
    PREV="$DIR"
done
