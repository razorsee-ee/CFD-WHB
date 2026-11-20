#!/bin/bash
# Series of calibrated boiler runs (steam coupled, 3 passes per variant), runs in the window.
#
#   bash run_night.sh [cores]
#
# VARIANTS: "name:duct_R:wall_R:bundle_R ..." (deposit resistances, m2K/W); RES: cell size, m.
# Default: the DCS-calibrated case on a 0.1 m mesh.
# Result: $FOAM_RUN/night_summary.txt (summary of the last pass of each variant) and
#         <name>_3/views.html.
# Resumable: finished variants (<name>_3/summary.txt with bundle heat) are skipped,
# unfinished ones are deleted and recomputed. After a crash just run it again.

NP=${1:-8}
REPO=$(cd "$(dirname "$0")" && pwd)
[ -z "$WM_PROJECT_DIR" ] && { echo "OpenFOAM not found: run from the blueCFD terminal"; exit 1; }
[ -z "$FOAM_RUN" ] && { echo "FOAM_RUN is not set"; exit 1; }
VARIANTS=${VARIANTS:-"cal:0.08:0.10:0.05"}
RES=${RES:-0.1}

done_variant() { grep -qE "Superheaters:|Пароперегреватели" "$FOAM_RUN/$1_3/summary.txt" 2>/dev/null; }
rm -f "$FOAM_RUN/NIGHT_DONE"
echo "$(date +%H:%M) series: $VARIANTS, cell $RES m, $NP cores. Do NOT close this window."

for v in $VARIANTS; do
    IFS=: read -r d duct wall bund <<< "$v"
    echo
    if done_variant "$d"; then
        echo "$(date +%H:%M) ===== $d already finished - skipping"
        continue
    fi
    echo "$(date +%H:%M) ===== $d: ducts $duct, walls $wall, tubes $bund"
    rm -rf "$FOAM_RUN/${d}_1" "$FOAM_RUN/${d}_2" "$FOAM_RUN/${d}_3" "$FOAM_RUN/${d}_"?.make.txt
    bash "$REPO/model/run_coupled.sh" "$FOAM_RUN/$d" "$NP" "$RES" 3 \
        --duct_R "$duct" --wall_R "$wall" --bundle_R "$bund"
done
rm -f "$FOAM_RUN/night_summary.txt"
for v in $VARIANTS; do
    IFS=: read -r d duct wall bund <<< "$v"
    { echo "===== $d: ducts $duct, walls $wall, tubes $bund (cell $RES m)"
      cat "$FOAM_RUN/${d}_3/summary.txt" 2>/dev/null || echo "(not finished)"; echo; } >> "$FOAM_RUN/night_summary.txt"
done
date > "$FOAM_RUN/NIGHT_DONE"
echo "$(date +%H:%M) ===== series finished. Result: cat $FOAM_RUN/night_summary.txt"
