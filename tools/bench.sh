#!/bin/bash
# Speed test: the calibrated boiler case on a 0.2 m mesh (~140 000 cells), 300 SIMPLE iterations,
# one pass, for each core count given. Same test on every machine -> comparable seconds/iteration.
#
#   bash tools/bench.sh 8            # one run on 8 cores
#   bash tools/bench.sh 4 8 16       # scaling test
#
# Prints and appends to $FOAM_RUN/bench_results.txt: host, cores, cells, s/iteration
# (iterations 50..300, start-up excluded), wall time, outlet gas temperature (sanity check).
REPO=$(cd "$(dirname "$0")/.." && pwd)
[ -z "$WM_PROJECT_DIR" ] && { echo "OpenFOAM not found: source its bashrc first"; exit 1; }
[ -z "$FOAM_RUN" ] && { echo "FOAM_RUN is not set"; exit 1; }
mkdir -p "$FOAM_RUN"
OUT="$FOAM_RUN/bench_results.txt"
[ $# -eq 0 ] && set -- 4
export PYTHONUTF8=1 PYTHONIOENCODING=utf-8

for NP in "$@"; do
    DIR="$FOAM_RUN/bench_np$NP"
    rm -rf "${DIR:?}_1" "${DIR}_1.make.txt"
    echo "$(date +%H:%M) bench: $NP cores ..."
    T0=$(date +%s)
    ITERS1=300 bash "$REPO/model/run_coupled.sh" "$DIR" "$NP" 0.2 1 \
        --duct_R 0.08 --wall_R 0.10 --bundle_R 0.05 > "$DIR.log" 2>&1
    T1=$(date +%s)
    LOG="${DIR}_1/log.foamRun"
    if ! grep -q "^ExecutionTime" "$LOG" 2>/dev/null; then
        echo "  FAILED, see $DIR.log and $LOG"; continue
    fi
    CELLS=$(grep -m1 "nCells:" "${DIR}_1/log.blockMesh" | awk '{print $2}')
    S50=$(grep "^ExecutionTime" "$LOG" | sed -n '50p' | awk '{print $3}')
    S300=$(grep "^ExecutionTime" "$LOG" | sed -n '300p' | awk '{print $3}')
    SPI=$(awk -v a="$S50" -v b="$S300" 'BEGIN{ if (b=="") print "n/a"; else printf "%.3f", (b-a)/250 }')
    GAS=$(grep -m1 "Gas at outlet" "${DIR}_1/summary.txt" | grep -oE "[0-9]+ °C" | head -1)
    LINE=$(printf "%s  %-20s np=%-3s cells=%-7s s/iter=%-6s wall=%ss  gas_out=%s  (OpenFOAM-%s)" \
        "$(date +%F)" "$(hostname)" "$NP" "$CELLS" "$SPI" "$((T1 - T0))" "${GAS:-?}" "$WM_PROJECT_VERSION")
    echo "  $LINE"
    echo "$LINE" >> "$OUT"
done
echo "All results: $OUT"
