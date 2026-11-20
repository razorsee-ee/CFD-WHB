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
# Environment overrides: RES (0.15), NP (physical cores), PASSES (3), SKIP_BENCH=1.
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
    log "speed test on:$LIST cores"
    bash "$REPO/tools/bench.sh" $LIST
fi

# ---------------------------------------------------------------- 3) real case
RES=${RES:-0.15}
PASSES=${PASSES:-3}
NAME="cloud_k_now_${RES}"
log "calibrated case, mesh $RES m, $NP processes, $PASSES passes"
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
log "done: ~/cloud_test_results.tgz ($(du -h ~/cloud_test_results.tgz | cut -f1))"
