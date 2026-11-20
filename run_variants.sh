#!/bin/bash
# Series of modification variants (skirts, ash level in the right hopper, cleaner tubes)
# on the DCS-calibrated base.
#
#   bash run_variants.sh [cores] [cell_m]
#
# BASE: make_case.py arguments common to all variants (default: calibrated deposits, DCS operating
# point 15.9 + 0.25 kg/s steam). VARIANTS: lines "name|extra arguments".
# Resumable like run_night.sh: finished variants are skipped.
# Result: $FOAM_RUN/variants_summary.txt (short table) and summaries/views in <name>_3.

NP=${1:-8}
RES=${2:-0.3}
REPO=$(cd "$(dirname "$0")" && pwd)
[ -z "$WM_PROJECT_DIR" ] && { echo "OpenFOAM not found: run from the blueCFD terminal"; exit 1; }
[ -z "$FOAM_RUN" ] && { echo "FOAM_RUN is not set"; exit 1; }
PY=$(command -v python3 || command -v python)
export PYTHONUTF8=1 PYTHONIOENCODING=utf-8

BASE=${BASE:-"--duct_R 0.08 --wall_R 0.10 --bundle_R 0.05"}
VARIANTS=${VARIANTS:-"
A_base|
A_hop95|--hopper2_fill 0.95
A_seal|--skirts sh4end:4
A_clean25|--bundle_R 0.025
A_clean25_hop95|--bundle_R 0.025 --hopper2_fill 0.95
"}

done_variant() { grep -qE "Superheaters:|Пароперегреватели" "$FOAM_RUN/$1_3/summary.txt" 2>/dev/null; }

echo "$VARIANTS" | while IFS='|' read -r name extra; do
    [ -z "$name" ] && continue
    if done_variant "$name"; then echo "$(date +%H:%M) $name already finished - skipping"; continue; fi
    echo "$(date +%H:%M) ===== $name: $extra"
    rm -rf "$FOAM_RUN/${name}_1" "$FOAM_RUN/${name}_2" "$FOAM_RUN/${name}_3"
    bash "$REPO/model/run_coupled.sh" "$FOAM_RUN/$name" "$NP" "$RES" 3 $BASE $extra > "$FOAM_RUN/$name.log" 2>&1
    grep -E "Gas at outlet|Superheaters:|Steam \(model" "$FOAM_RUN/${name}_3/summary.txt"
done

# short table from summary.json
{
    printf "%-16s %7s %7s %7s %7s %7s %7s %7s %7s\n" variant "SH,MW" "steam,C" "gas,C" "IIIa,%" "II,%" "I,%" "dp,Pa" "Umax"
    echo "$VARIANTS" | while IFS='|' read -r name extra; do
        [ -z "$name" ] && continue
        f="$FOAM_RUN/${name}_3/summary.json"
        [ -f "$f" ] || { echo "$name: not finished"; continue; }
        "$PY" - "$f" "$name" <<'PYEOF'
import json, sys
s = json.load(open(sys.argv[1], encoding="utf-8"))
t = s.get("through_pct", {})
ob = s.get("bulk", {}).get("outlet", {}).get("all", [None])[0] or s.get("T_out_patch", 0)
um = max(s.get("Umax", {}).values() or [0])
print(f"{sys.argv[2]:16s} {s.get('Q_sh_MW', 0):7.2f} {s.get('steam_out', 0):7.0f} {ob:7.0f} "
      f"{t.get('SH2', 0):7.0f} {t.get('SH3', 0):7.0f} {t.get('SH4', 0):7.0f} {s.get('dp_Pa', 0):7.0f} {um:7.1f}")
PYEOF
    done
} > "$FOAM_RUN/variants_summary.txt"
cat "$FOAM_RUN/variants_summary.txt"
