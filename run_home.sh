#!/bin/bash
# Расчёт котла дома: запустил и ушёл.
#
#   ./run_home.sh [папка_кейса] [ядер] [размер_ячейки_м]
#
# По умолчанию: $FOAM_RUN/whb_coarse, 8 ядер, ячейка 0.3 м (очень грубо, ~70 тыс. ячеек).
# Создаёт кейс из model/make_case.py (сценарий B, см. docs/CALIBRATION.md), запускает
# сетку и расчёт в фоне. В конце пишет summary.txt (доля газа через пучки, температуры)
# и файл DONE. Окно MSYS2 не закрывать.

DIR=${1:-$FOAM_RUN/whb_coarse}
NP=${2:-8}
RES=${3:-0.3}
REPO=$(cd "$(dirname "$0")" && pwd)
PY=$(command -v python3 || command -v python)

if [ -z "$WM_PROJECT_DIR" ]; then
    echo "Не видно OpenFOAM: запускайте из терминала blueCFD (MSYS2), где работает blockMesh"; exit 1
fi
if [ -z "$PY" ]; then
    echo "Нет python: pacman -S mingw-w64-x86_64-python"; exit 1
fi
if [ -e "$DIR" ]; then
    echo "Папка $DIR уже есть. Удалите её (rm -rf $DIR) или укажите другую."; exit 1
fi

NY=$("$PY" -c "print(max(6, round(4.65 / (2 * $RES))))")   # по ширине ячейка вдвое крупнее
"$PY" "$REPO/model/make_case.py" "$DIR" --res "$RES" --ny "$NY" --np "$NP" --iters ${ITERS:-3000} --scenario B \
    > "$REPO/.last_case.txt" || { echo "Ошибка при создании кейса"; exit 1; }
cat "$REPO/.last_case.txt"

cd "$DIR" || exit 1
nohup bash -c "./Allrun; \"$PY\" \"$REPO/model/whb_summary.py\" . > summary.txt 2>&1; date > DONE" \
    > log.Allrun 2>&1 &

echo
echo "Расчёт запущен в $DIR ($NP ядер, ячейка $RES м)."
echo "Можно уходить. Окно MSYS2 НЕ закрывать, компьютер не должен засыпать."
echo "Ход расчёта:   tail -3 $DIR/log.foamRun"
echo "Готово, когда есть файл $DIR/DONE; итог: cat $DIR/summary.txt"
