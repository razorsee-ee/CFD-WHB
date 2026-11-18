#!/bin/sh
# Подготовить последний момент кейса для model/plot_cell.py: ascii + центры ячеек
cd "$1" || exit 1
[ -d processor0 ] && reconstructPar -latestTime > log.reconstructPar 2>&1
sed -i 's/^writeFormat binary;/writeFormat ascii;/' system/controlDict
foamFormatConvert -latestTime > log.convert 2>&1
foamPostProcess -func writeCellCentres -latestTime > log.C 2>&1
