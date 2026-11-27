#!/bin/bash
# Series of calibrated OpenFOAM-14 variants (resumable: a variant with a final summary.json is skipped).
#
#   bash model/run_series_of14.sh <prefix> <cell_m> <cores> <passes> "name|label|extra make_case args" ...
#
# Every variant: model/run_coupled.sh with make_case_of14.py, calibrated deposits (0.08/0.10/0.05), LTS,
# steam temperatures of the first pass from the 0.1 m night run (TA), steam coupling between passes.
# After each variant: <prefix>_summary.txt (table of all finished variants) and an HTML report
# (results/<prefix>_report.html, first finished variant's images).
# Env: ITERS1 (3000), ITERSN (1500), TA, PY (python with matplotlib), FOAM_RUN.

PREFIX=$1; RES=$2; NP=$3; NPASS=$4; shift 4
REPO=$(cd "$(dirname "$0")/.." && pwd)
PY=${PY:-$(command -v python3)}
export ITERS1=${ITERS1:-3000} ITERSN=${ITERSN:-1500} GEN=make_case_of14.py
export TA=${TA:-416.5,376,323,273.5}
CAL="--duct_R 0.08 --wall_R 0.10 --bundle_R 0.05 --lts --lts_co 5"
OUT=$FOAM_RUN/${PREFIX}_summary.txt
cd "$FOAM_RUN" || exit 1

for spec in "$@"; do
    IFS='|' read -r name label extra <<< "$spec"
    dir=$FOAM_RUN/${PREFIX}_$name
    if [ -f "${dir}_$NPASS/summary.json" ]; then echo "skip $name (done)"; continue; fi
    echo "=== $(date '+%d.%m %H:%M') $name: $label [$extra]"
    rm -rf "${dir}"_[0-9]*
    bash "$REPO/model/run_coupled.sh" "$dir" "$NP" "$RES" "$NPASS" $CAL $extra > "$dir.log" 2>&1
    grep -E "Gas at outlet|Superheaters|Steam \(model" "${dir}_$NPASS/summary.txt"

    # table of all finished variants + HTML report
    args=()
    {
        printf "%-12s %-44s %7s %7s %7s %7s %6s  %s\n" variant label T_out steam Q_SH Q_gas dp "through EVAP/IIIb/IIIa/II/I %"
        for s2 in "$@"; do
            IFS='|' read -r n2 l2 _ <<< "$s2"
            j=$FOAM_RUN/${PREFIX}_${n2}_$NPASS/summary.json
            [ -f "$j" ] || continue
            args+=("$l2=$FOAM_RUN/${PREFIX}_${n2}_$NPASS")
            "$PY" -c "
import json; d = json.load(open('$j')); t = d['through_pct']
print('%-12s %-44s %7.1f %7.1f %7.2f %7.2f %6.0f  %s' % ('$n2', '$l2'[:44], d['T_out_patch'], d['steam_out'], d['Q_sh_MW'],
      d['Q_gas_MW'], d['dp_Pa'], '/'.join('%.0f' % t[k] for k in ('EVAP', 'SH1', 'SH2', 'SH3', 'SH4'))))"
        done
    } > "$OUT"
    cat "$OUT"
    "$PY" "$REPO/model/report_html.py" "$REPO/results/${PREFIX}_report.html" "${args[@]}" > /dev/null
done
echo "=== $(date '+%d.%m %H:%M') series $PREFIX done"
