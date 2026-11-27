#!/bin/bash
# Final report of the 0.15 m bypass series: PC variants v0-v4 from $FOAM_RUN + cloud variants v5-v7
# from branch origin/claude/bypass-cloud (docs/runs/bypass15_cloud/<variant>/, extracted without checkout).
#
#   bash model/final_bypass_report.sh [--wait]     (--wait: first wait for "series bypass15 done" in bypass_pc.out)
# -> results/bypass15_full_report.html
REPO=$(cd "$(dirname "$0")/.." && pwd)
RUN=${FOAM_RUN:-$HOME/OpenFOAM/ed-14/run}
PY=${PY:-$HOME/venvs/cfd/bin/python}
if [ "$1" = "--wait" ]; then
    until grep -q "series bypass15 done" "$RUN/bypass_pc.out" 2>/dev/null; do sleep 300; done
fi
CLOUD=$RUN/bypass15_cloud_fetched
rm -rf "$CLOUD"; mkdir -p "$CLOUD"
cd "$REPO"
if git fetch -q origin claude/bypass-cloud 2>/dev/null; then
    git archive FETCH_HEAD docs/runs/bypass15_cloud 2>/dev/null | tar -x -C "$CLOUD" --strip-components=3 \
        || echo "no docs/runs/bypass15_cloud on the cloud branch yet"
else
    echo "cloud branch not found"
fi
args=()
add() {  # label dir
    [ -f "$2/summary.json" ] && args+=("$1=$2") || echo "missing: $1 ($2)"
}
add "v0 Base (calibrated)"                        "$RUN/bypass15_v0_base_2"
add "v1 Plate behind SH I to hopper wall"         "$RUN/bypass15_v1_sh1end_2"
add "v2 Skirts 1.5 m + plate behind SH I"         "$RUN/bypass15_v2_sk15_2"
add "v3 Skirts 3 m + plate behind SH I"           "$RUN/bypass15_v3_sk3_2"
add "v4 Skirts 6 m (gap 1.2-2.7 m above ash)"     "$RUN/bypass15_v4_sk6_2"
add "v5 Partitions to hopper floor, 0.5 m gap"    "$CLOUD/v5_part_gap"
add "v6 Partitions to hopper floor, sealed"       "$CLOUD/v6_part_full"
add "v7 Right hopper 95 % (false floor)"          "$CLOUD/v7_hop95"
[ ${#args[@]} -gt 0 ] || { echo "nothing finished yet"; exit 1; }
"$PY" model/report_html.py results/bypass15_full_report.html \
    --title "Котёл-утилизатор: перекрытие байпаса под пучками, сетка 0.15 м" \
    --note "Серия от простых решений к радикальным; 2 прохода с увязкой пара. v0–v4 — ПК (8 ядер), v5–v7 — облако (4 ядра)." \
    "${args[@]}"
