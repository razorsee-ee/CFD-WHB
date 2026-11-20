# Linux: лаптоп, WSL, облако (AWS)

## Состояние (20.11.2026)
Лаптоп пользователя (ThinkPad, i7-11850H 8 ядер/16 потоков, 32 ГБ): **Ubuntu 24.04.5 рядом с Windows**,
`/` = nvme0n1p6 (ext4, 157 ГБ), **OpenFOAM-12 пакетом** установлен и проверен (`foamRun` найден).
Осталось подчистить временное (см. ниже) и прогнать тест скорости.

## Установка OpenFOAM-12 (Ubuntu 22.04/24.04 — лаптоп, WSL, облако одинаково)
```
sudo apt update && sudo apt -y upgrade
sudo sh -c "wget -O - https://dl.openfoam.org/gpg.key > /etc/apt/trusted.gpg.d/openfoam.asc"
sudo add-apt-repository -y http://dl.openfoam.org/ubuntu
sudo apt update && sudo apt -y install openfoam12 git python3-numpy python3-matplotlib tmux
echo 'source /opt/openfoam12/etc/bashrc' >> ~/.bashrc && source ~/.bashrc
mkdir -p $FOAM_RUN && cd $FOAM_RUN
git clone https://github.com/razorsee-ee/CFD-WHB.git && cd CFD-WHB && git checkout claude/compassionate-rubin-t8h1bo
```
Ubuntu 26.04 не брать: пакета openfoam12 под неё, скорее всего, нет, а сборка 12 новым GCC рискованна.

## Тест скорости: `tools/bench.sh`
Калиброванный кейс, сетка 0.2 м (139 272 ячейки), 300 итераций SIMPLE, 1 заход. Время на итерацию
считается по итерациям 50–300 (без старта). Результаты дописываются в `$FOAM_RUN/bench_results.txt`.
```
bash tools/bench.sh 8          # одно число ядер
bash tools/bench.sh 4 8 16     # масштабирование
```
`gas_out` — контроль, что кейс тот же (после 300 итераций не сошёлся, но должен быть одинаков: 568 °C).

| машина | ядра | s/iter | wall |
|---|---|---|---|
| контейнер Claude (облачная VM) | 2 | 0.350 | 118 с |
| контейнер Claude | 4 | 0.187 | 68 с |
| лаптоп, Ubuntu, от сети (сильный нагрев) | 4 | 0.248 | 83 с |
| лаптоп, Ubuntu, от сети (сильный нагрев) | 8 | 0.234 | 77 с |
| домашний ПК, blueCFD | 8 | ? | |

4→8 ядер на лаптопе почти не ускоряет: 2 канала памяти + перегрев (троттлинг). Ориентир для сетки 0.1 м (~1 млн ячеек): s/iter ≈ s/iter(0.2 м) × ~7–8.

## Удалить временное после установки Ubuntu (из Windows, PowerShell от администратора)
```
bcdedit /delete '{fcdc36e4-9297-11f0-923d-e61d8e39978f}'
mountvol S: /S
Remove-Item -Recurse -Force S:\EFI\ubuntu-live
mountvol S: /D
```
Раздел L: (nvme0n1p4, FAT32 8.6 ГБ) — Disk Management → Delete Volume. Пространство останется
неразмеченным между C: и Ubuntu; C: расширить можно только если оно сразу за C: (так и есть).

## AWS (план, не проверено)
- AMI Ubuntu 24.04 LTS, дальше те же команды. Запуск в `tmux`; результаты — `git`/`scp`/S3.
- OpenFOAM упирается в пропускную способность памяти: ~50–100 тыс. ячеек на ядро, np = физические ядра
  (на AWS «vCPU» — это потоки; у Intel/AMD-инстансов обычно 2 vCPU = 1 ядро, у `hpc*` и Graviton — 1:1).
- Кандидаты: compute-optimized `c7i`/`c7a` (x86), `hpc7a` (AMD, много ядер, дёшево за ядро, не во всех
  регионах), Graviton `c7g`/`c8g` (ARM — пакет openfoam12 для arm64 проверить; иначе сборка из исходников).
- Spot-инстансы заметно дешевле; серии продолжаемые (`run_night.sh`, `run_variants.sh` пропускают готовое).
- Первый шаг на любом инстансе: `bash tools/bench.sh <ядра>` и сравнить с таблицей выше.
