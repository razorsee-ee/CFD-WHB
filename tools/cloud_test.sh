#!/bin/bash
# Test run on a fresh cloud server (Hetzner, AWS ...) with Ubuntu 22.04/24.04, as root or with sudo.
#
#   bash tools/cloud_test.sh            # full test, ~30-60 min on 16 cores
#
# 1) installs OpenFOAM-12 (package) and python if missing
# 2) speed test tools/bench.sh on 4, 8, ... up to all cores (0.2 m mesh, 300 iterations each)
# 3) real calibrated case on a 0.15 m mesh (~330 000 cells), 3 coupled passes (3000+1500+1500),
#    on the physical cores -> grid check against the 0.3 m calibration (gas 618 C, steam 441 C)
# 4) packs the small results (summaries, pictures, logs; no fields) into ~/cloud_test_results.tgz
#
# Environment overrides: RES (0.15), NP (physical cores), PASSES (3), SKIP_BENCH=1, PORT (8080).
#
# Live view while it runs: a status page (stage, iteration, convergence plots, bench table, pictures
# after each pass) refreshed every 30 s, served on the server's localhost:PORT only. From your computer:
#   ssh -L 8080:localhost:8080 root@<server_ip>      then open http://localhost:8080
set -u
REPO=$(cd "$(dirname "$0")/.." && pwd)
SUDO=""; [ "$(id -u)" != 0 ] && SUDO=sudo
export DEBIAN_FRONTEND=noninteractive
log() { echo "[cloud $(date +%H:%M:%S)] $*"; }

# ---------------------------------------------------------------- 1) install
if [ ! -f /opt/openfoam12/etc/bashrc ] && [ -z "${WM_PROJECT_DIR:-}" ]; then
    log "installing OpenFOAM-12"
    $SUDO apt-get update -qq
    $SUDO apt-get install -y -qq wget software-properties-common git python3-numpy python3-matplotlib tmux
    $SUDO sh -c "wget -qO - https://dl.openfoam.org/gpg.key > /etc/apt/trusted.gpg.d/openfoam.asc"
    $SUDO add-apt-repository -y http://dl.openfoam.org/ubuntu
    $SUDO apt-get update -qq
    $SUDO apt-get install -y -qq openfoam12 || { log "openfoam12 install failed"; exit 1; }
fi
if [ -z "${WM_PROJECT_DIR:-}" ]; then
    set +u; source /opt/openfoam12/etc/bashrc; set -u
fi
grep -q "openfoam12/etc/bashrc" ~/.bashrc 2>/dev/null || echo 'source /opt/openfoam12/etc/bashrc' >> ~/.bashrc
# mpirun as root (cloud servers usually log in as root)
export OMPI_ALLOW_RUN_AS_ROOT=1 OMPI_ALLOW_RUN_AS_ROOT_CONFIRM=1
mkdir -p "$FOAM_RUN"

# ---------------------------------------------------------------- live status page
WATCH="$FOAM_RUN/watch"
mkdir -p "$WATCH"
PORT=${PORT:-8080}
stage() { echo "$*" > "$WATCH/stage.txt"; log "$*"; }
status_page() {
    local C IT
    C=$(ls -dt "$FOAM_RUN"/bench_np*_1 "$FOAM_RUN"/cloud_k_now_*_[0-9] 2>/dev/null | head -1)
    IT=""
    if [ -n "$C" ] && [ -f "$C/log.foamRun" ]; then
        IT=$(grep "^ExecutionTime" "$C/log.foamRun" | wc -l)
        python3 "$REPO/model/monitor.py" "$C" --out "$WATCH" > /dev/null 2>&1
    fi
    for f in views_long.png views_scheme.png views_cross.png; do
        L=$(ls -t "$FOAM_RUN"/cloud_k_now_*_[0-9]/$f 2>/dev/null | head -1)
        [ -n "$L" ] && cp "$L" "$WATCH/$f"
    done
    S=$(ls -t "$FOAM_RUN"/cloud_k_now_*_[0-9]/summary.txt 2>/dev/null | head -1)
    {
        echo '<html><head><meta charset="utf-8"><meta http-equiv="refresh" content="30">'
        echo '<title>cloud test</title></head><body style="font-family:sans-serif">'
        echo "<h3>$(cat "$WATCH/stage.txt" 2>/dev/null)</h3>"
        echo "<p>$(date +%H:%M:%S) &nbsp; case: <b>$(basename "${C:-none}")</b> &nbsp; iterations: <b>${IT:-0}</b>"
        [ -n "$C" ] && echo " &nbsp; last: $(grep '^ExecutionTime' "$C/log.foamRun" 2>/dev/null | tail -1)"
        echo " &nbsp; load: $(cut -d' ' -f1-3 /proc/loadavg)</p>"
        [ -f "$WATCH/monitor.png" ] && echo "<img src=\"monitor.png?$(date +%s)\" style=\"width:100%\">"
        echo "<h4>Speed test</h4><pre>$(cat "$FOAM_RUN/bench_results.txt" 2>/dev/null)</pre>"
        [ -n "$S" ] && echo "<h4>Last finished pass: $S</h4><pre>$(cat "$S")</pre>"
        for f in views_scheme.png views_long.png views_cross.png; do
            [ -f "$WATCH/$f" ] && echo "<img src=\"$f?$(date +%s)\" style=\"width:100%\">"
        done
        echo "<h4>Machine</h4><pre>$(cat "$FOAM_RUN/cloud_machine.txt" 2>/dev/null)</pre></body></html>"
    } > "$WATCH/index.html.tmp" && mv "$WATCH/index.html.tmp" "$WATCH/index.html"
}
stage "starting"
status_page
( while true; do status_page; sleep 30; done ) &
LOOP_PID=$!
trap 'kill $LOOP_PID 2>/dev/null' EXIT
if ! ss -ltn 2>/dev/null | grep -q ":$PORT "; then
    (cd "$WATCH" && nohup python3 -m http.server "$PORT" --bind 127.0.0.1 > /dev/null 2>&1 &)
fi
log "live page: ssh -L $PORT:localhost:$PORT root@<server_ip>  ->  http://localhost:$PORT"

# ---------------------------------------------------------------- machine info
THREADS=$(nproc)
CORES=$(lscpu -p=CORE,SOCKET 2>/dev/null | grep -v '^#' | sort -u | wc -l)
[ "$CORES" -ge 1 ] 2>/dev/null || CORES=$THREADS
NP=${NP:-$CORES}
INFO="$FOAM_RUN/cloud_machine.txt"
{
    echo "host: $(hostname)   date: $(date)"
    lscpu | grep -E "Model name|Socket|Core\(s\)|Thread\(s\)|NUMA node\(s\)|L3"
    free -g | head -2
    echo "threads: $THREADS  physical cores: $CORES  NP used: $NP"
    echo "OpenFOAM-$WM_PROJECT_VERSION"
} > "$INFO"
cat "$INFO"

# ---------------------------------------------------------------- 2) speed test
if [ -z "${SKIP_BENCH:-}" ]; then
    LIST=""
    for n in 4 8 12 16 24 32 48 64 96; do [ "$n" -le "$THREADS" ] && LIST="$LIST $n"; done
    stage "1/2 speed test on:$LIST cores"
    bash "$REPO/tools/bench.sh" $LIST
fi

# ---------------------------------------------------------------- 3) real case
RES=${RES:-0.15}
PASSES=${PASSES:-3}
NAME="cloud_k_now_${RES}"
stage "2/2 calibrated case, mesh $RES m, $NP processes, $PASSES passes"
T0=$(date +%s)
bash "$REPO/model/run_coupled.sh" "$FOAM_RUN/$NAME" "$NP" "$RES" "$PASSES" \
    --duct_R 0.08 --wall_R 0.10 --bundle_R 0.05 > "$FOAM_RUN/$NAME.log" 2>&1
T1=$(date +%s)
LAST="$FOAM_RUN/${NAME}_$PASSES"
CELLS=$(grep -m1 "nCells:" "$LAST/log.blockMesh" | awk '{print $2}')
NIT=$(grep -c "^ExecutionTime" "$LAST/log.foamRun" 2>/dev/null)
{
    echo "case $NAME: cells $CELLS, wall time $(( (T1 - T0) / 60 )) min for $PASSES passes"
    grep -E "Gas at the bottom|Gas at outlet|Superheaters:|Steam \(model" "$LAST/summary.txt"
} | tee -a "$INFO"
[ "$NIT" -gt 0 ] || log "WARNING: no iterations in the last pass, see $FOAM_RUN/$NAME.log"

# ---------------------------------------------------------------- 4) pack results
cd "$FOAM_RUN" || exit 1
tar czf ~/cloud_test_results.tgz cloud_machine.txt bench_results.txt ./*.log \
    $(ls -d ${NAME}_*/ 2>/dev/null | while read -r d; do
        ls "$d"summary.* "$d"*.png "$d"*.html "$d"log.foamRun "$d"ta_next.txt 2>/dev/null; done) 2>/dev/null
stage "finished"; status_page
log "done: ~/cloud_test_results.tgz ($(du -h ~/cloud_test_results.tgz | cut -f1))"
