# Расчёт котла дома: запустил и ушёл

> Актуально: `run_night.sh` (калиброванный кейс, по умолчанию сетка 0.1 м) и `run_variants.sh` (варианты переделок).
> `run_home.sh` и `run_batch.sh` удалены — разделы ниже про них устарели.

Всё в терминале blueCFD (MSYS2), каждая команда отдельно.

## Первый раз: забрать проект

```bash
cd $FOAM_RUN && git clone -b claude/compassionate-rubin-t8h1bo https://github.com/razorsee-ee/CFD-WHB.git
```

## Последующие разы: обновить проект

```bash
cd $FOAM_RUN/CFD-WHB && git checkout -- . && git pull
```

## Чтобы компьютер не уснул (один раз)

```bash
powercfg /change standby-timeout-ac 0
```

## Запуск (очень грубая сетка, ~70 тыс. ячеек, 8 ядер)

```bash
cd $FOAM_RUN/CFD-WHB && bash run_home.sh
```

Скрипт сам создаёт кейс в `$FOAM_RUN/whb_coarse`, строит сетку и запускает расчёт в фоне (3000 итераций).
Окно MSYS2 не закрывать. Ориентир по времени: несколько минут (у Claude 100 итераций на 2 ядрах — 10 с).

Если папка уже есть от прошлого раза, удалить её:
```bash
rm -rf $FOAM_RUN/whb_coarse
```

## Проверить, идёт ли

```bash
tail -3 $FOAM_RUN/whb_coarse/log.foamRun
```

## Результат

Готово, когда появился файл `DONE`. Сводка:
```bash
cat $FOAM_RUN/whb_coarse/summary.txt
```
Её и `tail -30 log.foamRun` прислать Claude.

Посмотреть поля:
```bash
cd $FOAM_RUN/whb_coarse && paraFoam -builtin
```
В ParaView: Apply → в списке времён выбрать последнее → раскраска T или U → Slice (нормаль Y) для продольного разреза.

## Сетка мельче (по желанию, когда грубая прошла)

Ячейка 0.15 м, ~0.4 млн ячеек, ориентировочно полчаса–час:
```bash
cd $FOAM_RUN/CFD-WHB && bash run_home.sh $FOAM_RUN/whb_015 8 0.15
```

## Серия из трёх расчётов по очереди (грубая B, грубая A, 0.15 м B)

```bash
cd $FOAM_RUN/CFD-WHB && bash run_batch.sh
```
Готово, когда есть `$FOAM_RUN/BATCH_DONE`. Общая сводка:
```bash
cat $FOAM_RUN/batch_summary.txt
```

## Ночная серия (сетка 0.15 м, пар увязан, 3 варианта отложений)

```bash
cd $FOAM_RUN/CFD-WHB && git checkout -- . && git pull
```
```bash
cd $FOAM_RUN/CFD-WHB && bash run_night.sh
```
Итог:
```bash
cat $FOAM_RUN/night_summary.txt
```

## Графики хода расчёта и стандартные виды

Один раз поставить matplotlib (если ещё нет):
```bash
pacman -S mingw-w64-x86_64-python-numpy mingw-w64-x86_64-python-matplotlib
```

Следить за идущим расчётом — во **втором** окне MSYS2 (страница в браузере обновляется сама каждые 30 с):
```bash
cd $FOAM_RUN/CFD-WHB && bash model/watch.sh $FOAM_RUN/n1
```
(`n1` — префикс варианта: сам переключается на заходы n1_1, n1_2, n1_3.) Остановить: Ctrl+C.

Стандартные виды строятся сами в конце каждого захода (`<папка>/views.html`). Вручную:
```bash
cd $FOAM_RUN/CFD-WHB && python model/views.py $FOAM_RUN/n1_3
```
```bash
explorer.exe "$(cygpath -w $FOAM_RUN/n1_3/views.html)"
```
Для кейсов, посчитанных до появления views.py, сначала записать центры ячеек:
```bash
cd $FOAM_RUN/n1_3 && foamPostProcess -func writeCellCentres -latestTime
```
