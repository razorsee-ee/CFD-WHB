# Расчёт на арендованном сервере (пошагово)

Пример — Hetzner Cloud (почасовая оплата, ЕС). Любой другой провайдер устроен так же:
создать машину → зайти по SSH → поставить OpenFOAM → посчитать → забрать результаты → **удалить машину**.

## Сколько стоит и когда имеет смысл

- Ориентир (сторонние трекеры, середина 2026): ~0.03 $ за vCPU-час у машин с выделенными ядрами (CCX).
  Например, 16 vCPU ≈ 0.5 $/ч. Перед арендой сверить с ценами на сайте Hetzner — в июне 2026 они сильно выросли.
- **vCPU — это поток, а не ядро.** 16 vCPU ≈ 8 физических ядер ≈ ваш i7-9700. Выигрыш по скорости дают машины от 32–48 vCPU.
- 30 € ≈ 30 часов на 32 vCPU или ~60 часов на 16 vCPU. Деньги идут, **пока машина существует** — даже выключенная.

## 1. Ключ SSH (один раз, в MSYS2)

```bash
ssh-keygen -t ed25519
```
(Enter на все вопросы.) Показать открытый ключ — его вставить на сайте:
```bash
cat ~/.ssh/id_ed25519.pub
```

## 2. Создать сервер (в браузере)

1. Зарегистрироваться на hetzner.com → Cloud → новый проект.
2. Security → SSH Keys → Add → вставить строку из `cat`.
3. Add Server: локация любая в ЕС; образ **Ubuntu 24.04**; тип **Dedicated vCPU (CCX)**; отметить свой SSH-ключ; Create.
4. Записать IP-адрес сервера (дальше вместо `1.2.3.4`).

## 3. Зайти и поставить OpenFOAM-12

```bash
ssh root@1.2.3.4
```
Дальше команды выполняются **на сервере** (официальная установка с openfoam.org):
```bash
sh -c "wget -O - https://dl.openfoam.org/gpg.key > /etc/apt/trusted.gpg.d/openfoam.asc"
```
```bash
add-apt-repository -y http://dl.openfoam.org/ubuntu
```
```bash
apt-get update && apt-get -y install openfoam12 git python3-numpy python3-matplotlib tmux
```
```bash
echo '. /opt/openfoam12/etc/bashrc' >> ~/.bashrc && . ~/.bashrc
```
Если официальный способ не сработает — запасной: склонировать проект (шаг 4) и `bash tools/setup_openfoam12.sh`.

## 4. Проект и расчёт

```bash
git clone -b claude/compassionate-rubin-t8h1bo https://github.com/razorsee-ee/CFD-WHB.git && cd CFD-WHB
```
Сессия `tmux`, чтобы расчёт не умер, если связь оборвётся:
```bash
tmux new -s run
```
Сгенерировать кейс на все ядра сервера и запустить (`nproc` — число vCPU):
```bash
python3 model/make_case.py ~/whb --res 0.1 --ny 46 --np $(nproc) && cd ~/whb && export OMPI_ALLOW_RUN_AS_ROOT=1 OMPI_ALLOW_RUN_AS_ROOT_CONFIRM=1 && ./Allrun
```
Выйти из tmux, не останавливая расчёт: **Ctrl+b, затем d**. Можно закрыть окно и выключить свой компьютер.

Вернуться позже:
```bash
ssh root@1.2.3.4
```
```bash
tmux attach -t run
```
Посмотреть ход расчёта:
```bash
tail -5 ~/whb/log.foamRun
```

## 5. Забрать результаты (на своём компьютере, в MSYS2)

На сервере упаковать только последнее время и настройки:
```bash
cd ~/whb && tar czf ~/whb.tgz constant system $(foamListTimes -latestTime) postProcessing log.*
```
Скачать (команда на своём компьютере):
```bash
scp root@1.2.3.4:~/whb.tgz /d/cfd/
```

## 6. Удалить сервер

В браузере: сервер → Delete. Проверить, что в проекте не осталось серверов, дисков (Volumes) и снимков (Snapshots) — за них тоже платят.
