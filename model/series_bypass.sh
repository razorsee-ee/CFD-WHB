#!/bin/bash
# Bypass-closing series under the bundles (simple -> radical), calibrated model, OpenFOAM-14.
#
#   bash model/series_bypass.sh <cores> <variant names ...>      (no names = all)
#
# Mesh 0.15 m, 2 passes (3000 + 1500 iterations) with steam coupling. Skirt places (gaps between bundles):
# evap (after EVAP), sh1/sh2/sh3 (after SH IIIb/IIIa/II), sh4end (right behind SH I). Depth = from the bundle
# bottoms (z 13.11) down; a depth beyond the hopper wall/ash (z 4.41) is clipped there.
# Full depths: evap 1.82, sh1 8.70, sh2 8.70, sh3 7.19, sh4end 2.52 m.
NP=$1; shift
V=(
  "v0_base|0 Base (calibrated)|"
  "v1_sh1end|1 Plate behind SH I to hopper wall|--skirts sh4end:3"
  "v2_sk15|2 Skirts 1.5 m in all gaps + plate behind SH I|--skirts evap:1.5,sh1:1.5,sh2:1.5,sh3:1.5,sh4end:3"
  "v3_sk3|3 Skirts 3 m in all gaps + plate behind SH I|--skirts evap:3,sh1:3,sh2:3,sh3:3,sh4end:3"
  "v4_sk6|4 Skirts 6 m (gap 1.2-2.7 m above ash)|--skirts evap:3,sh1:6,sh2:6,sh3:6,sh4end:3"
  "v5_part_gap|5 Partitions to hopper floor, 0.5 m gap|--skirts evap:1.3,sh1:8.2,sh2:8.2,sh3:6.7,sh4end:2.0"
  "v6_part_full|6 Partitions to hopper floor, sealed|--skirts evap:13,sh1:13,sh2:13,sh3:13,sh4end:13"
  "v7_hop95|7 Right hopper 95 % (false floor under bundles)|--hopper2_fill 0.95"
)
SEL=()
for v in "${V[@]}"; do
    n=${v%%|*}
    if [ $# -eq 0 ] || [[ " $* " == *" $n "* ]]; then SEL+=("$v"); fi
done
REPO=$(cd "$(dirname "$0")/.." && pwd)
exec bash "$REPO/model/run_series_of14.sh" bypass15 0.15 "$NP" 2 "${SEL[@]}"
