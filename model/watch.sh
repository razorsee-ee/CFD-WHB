#!/bin/bash
# Watch a running case: plots every N seconds, the browser page refreshes itself.
#
#   bash model/watch.sh <dir_or_prefix> [seconds]
#
# Prefix: e.g. $FOAM_RUN/n1 - follows the latest pass n1_1, n1_2, ...
# Images: $FOAM_RUN/watch/monitor.png and monitor.html. Stop: Ctrl+C.
PAT=$1; DT=${2:-30}
REPO=$(cd "$(dirname "$0")/.." && pwd)
PY=$(command -v python3 || command -v python)
export PYTHONUTF8=1 PYTHONIOENCODING=utf-8
OUT=${FOAM_RUN:-.}/watch
mkdir -p "$OUT"
opened=0
while true; do
    C=$(ls -d "$PAT" "${PAT}"_[0-9]* 2>/dev/null | grep -v '\.txt$' | sort -V | tail -1)
    if [ -n "$C" ] && [ -d "$C/postProcessing" ]; then
        "$PY" "$REPO/model/monitor.py" "$C" --out "$OUT" | sed "s|^|$(basename "$C"): |"
        if [ $opened = 0 ] && [ -f "$OUT/monitor.html" ] && command -v explorer.exe > /dev/null; then
            explorer.exe "$(cygpath -w "$OUT/monitor.html")"
            opened=1
        fi
    else
        echo "$(date +%H:%M:%S) waiting for the run to start: $PAT"
    fi
    sleep "$DT"
done
