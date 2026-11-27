#!/bin/bash
# Watch a running series (run_series_of14.sh): status in the terminal + live convergence plots of the
# current case in the browser ($FOAM_RUN/watch/monitor.html, refreshes itself). Stop: Ctrl+C.
#
#   bash model/watch_series.sh [prefix] [seconds]        (default: bypass15 60)
PREFIX=${1:-bypass15}; DT=${2:-60}
REPO=$(cd "$(dirname "$0")/.." && pwd)
RUN=${FOAM_RUN:-$HOME/OpenFOAM/ed-14/run}
PY=$(command -v python3)
OUT=$RUN/watch
mkdir -p "$OUT"
opened=0
while true; do
    C=$(ls -td "$RUN/${PREFIX}"_*_[0-9] 2>/dev/null | head -1)
    clear
    echo "=== $(date '+%d.%m %H:%M:%S')  series $PREFIX   (Ctrl+C - stop watching; the run goes on)"
    grep "^===" "$RUN/bypass_pc.out" 2>/dev/null | tail -3
    echo
    if [ -n "$C" ] && [ -f "$C/log.foamRun" ]; then
        it=$(grep -c "^Time = " "$C/log.foamRun")
        last=$(grep "^ExecutionTime" "$C/log.foamRun" | tail -1 | awk '{print $3}')
        pass=${C##*_}
        tot=$([ "$pass" = 1 ] && echo "${ITERS1:-3000}" || echo "${ITERSN:-1500}")
        spi=$(awk -v t="$last" -v i="$it" 'BEGIN{if(i>0) printf "%.2f", t/i}')
        eta=$(awk -v s="$spi" -v i="$it" -v n="$tot" 'BEGIN{if(s>0) printf "%.0f", (n-i)*s/60}')
        echo "current: $(basename "$C")   iteration $it / $tot   ${spi} s/iter   pass left ~${eta} min"
        grep -q "End" "$C/log.foamRun" && echo "(foamRun finished, post-processing)"
        "$PY" "$REPO/model/monitor.py" "$C" --out "$OUT" > /dev/null 2>&1
        if [ $opened = 0 ] && [ -f "$OUT/monitor.html" ]; then
            xdg-open "$OUT/monitor.html" > /dev/null 2>&1 &
            opened=1
        fi
    else
        echo "no running case yet"
    fi
    echo
    echo "--- finished variants ($RUN/${PREFIX}_summary.txt):"
    cat "$RUN/${PREFIX}_summary.txt" 2>/dev/null
    echo
    echo "full report so far: bash model/final_bypass_report.sh  -> results/${PREFIX}_full_report.html"
    sleep "$DT"
done
