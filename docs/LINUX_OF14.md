# Переход на Linux и OpenFOAM-14 (решение 21.11.2026)

## Решение

| | Windows (blueCFD-Core 2024) | Linux (новая система) |
|---|---|---|
| OpenFOAM | 12 (Foundation) | **14 (Foundation)**, пакет `openfoam14` |
| Система | Windows, MSYS2 | **Ubuntu 26.04 LTS** рядом с Windows (dual boot) |
| Что считаем | старые проекты как есть (CFD-Venturi, котёл на OF-12) | новые проекты и переписанные под OF-14 |

Windows на этом ПК (i7-9700, 8 ядер, 16 ГБ) остаётся: на нём blueCFD. Ubuntu ставится рядом.

Почему 14, а не 12: на Windows blueCFD дальше 12 нет; синтаксис 12 → 14 заметно поменялся,
и всё, что пишем сейчас на 12, через год пришлось бы переносить. Почему 26.04: пакеты OF-14 для неё есть,
поддержка до 2031, следующая версия OF почти наверняка тоже будет под неё.

## Установка OpenFOAM-14 (Ubuntu 26.04)

По странице https://openfoam.org/download/14-ubuntu/ (из контейнера Claude сайт закрыт, команды сверить с ней):

```bash
sudo apt update && sudo apt -y upgrade
```

```bash
sudo sh -c "wget -O - https://dl.openfoam.org/gpg.key > /etc/apt/trusted.gpg.d/openfoam.asc"
```

```bash
sudo add-apt-repository http://dl.openfoam.org/ubuntu
```

**На 26.04:** если эта команда пишет предупреждение про архитектуру (amd64v3), нужна ещё одна команда
со страницы загрузки, чтобы apt брал `amd64`. Без неё `openfoam14` не найдётся.

```bash
sudo apt update && sudo apt -y install openfoam14 git python3-numpy python3-matplotlib tmux
```

```bash
echo 'source /opt/openfoam14/etc/bashrc' >> ~/.bashrc && source ~/.bashrc
```

Проверка: `echo $WM_PROJECT_VERSION` → `14`, `which foamRun`, `nproc` → `8`.
ParaView ставится вместе с пакетом в `/opt`.

## Что меняется в синтаксисе 12 → 14 (то, что уже видно по туториалам)

Сверено по исходникам OpenFOAM-12 и OpenFOAM-14 (GitHub), туториал `multiphaseEuler/fluidisedBed`:

| OF-12 | OF-14 |
|---|---|
| `type basicMultiphaseSystem;` в `phaseProperties` | строки нет |
| `drag`, `virtualMass`, `lift`, … в `phaseProperties` | отдельный файл `constant/momentumTransfer` |
| `heatTransfer` в `phaseProperties` | отдельный файл `constant/heatTransfer` |
| `diameterModel constant; constantCoeffs { d …; }` | `diameterModel { type constant; d …; }` |
| `setFields` + `0/alpha.*.orig` | поле сразу задаётся зонами: `internalField { type zonal; zones { … box … } }` |
| `topoSet`/`cellZoneSet` для зон | новые mesh zones (с OF-13), задаются генераторами зон |
| function objects в `controlDict` | `system/functions` (с OF-13) |
| частицы: `lagrangian` (`cloudProperties`) | старая библиотека ещё есть; рядом новая `Lagrangian` (`constant/Lagrangian/<cloud>/…`) |

Также в 14: размерности проверяются при вводе (единицы), переделаны `coded`-объекты, field functions
для начальных полей. Детали — по каждому проекту при переносе, по туториалам `$FOAM_TUTORIALS` версии 14.

## Что уходит вместе с Windows (на Linux не нужно)

Из таблицы `docs/NEW_PROJECT_OPENFOAM.md` §2.1: `:` в именах полей, cp1252, окно matplotlib под MSYS,
отличие сетки snappy (`minTetQuality 1e-15`), CRLF, `/proc/cpuinfo`, `taskkill`. Остановить решатель:
`pkill -x foamRun`. Команды пользователю — для обычного терминала Ubuntu (Ctrl+Alt+T).

## Контейнер Claude

**`tools/setup_openfoam14.sh`** — готовый пакет без сборки. `dl.openfoam.org` в контейнере закрыт, но те же `.deb`
лежат на SourceForge (проект `foam`, `foam/ubuntu/dists/<codename>/main/binary-amd64/`), а он открыт.
Скрипт берёт самый свежий `openfoam14_<дата>_amd64.deb` под версию Ubuntu, сверяет SHA-256 из списка файлов
SourceForge и ставит через apt с `--no-install-recommends` (без ParaView/Qt). Окружение: `source /opt/of14env.sh`.

Проверено 21.11.2026 (контейнер Ubuntu 24.04): `openfoam14_20261008`, 126 МБ за 11 с, SHA-256 OK, 83 пакета
из обычных зеркал; **вся установка 21–28 с**. Туториал `multiphaseEuler/fluidisedBed` до 0.05 с на 4 ядрах — 3 с, без ошибок.
Скачивание идёт через случайное зеркало `*.dl.sourceforge.net`; в окружении с открытыми пакетными менеджерами
отдельных разрешений не нужно.
Для Ubuntu 26.04 (resolute) на SourceForge тоже есть `openfoam14_20261008`, скрипт подходит и для неё.

**Окружение «CFD-WHB»** (личное, создано 21.11.2026, привязано к `razorsee-ee/CFD-WHB`): его setup script ставит
OpenFOAM-14 этим же способом при создании контейнера, до старта Claude. Новый чат по CFD запускать в этом окружении —
OpenFOAM уже есть, `source /opt/of14env.sh`. Если `/opt/of14env.sh` нет — запустить `tools/setup_openfoam14.sh`.
(Первый запуск окружения ещё не проверен.) Сборка из исходников (~1 ч) — только если SourceForge недоступен.

## Claude прямо на Ubuntu (автоматизация)

Десктопное приложение Claude официально для macOS и Windows; на Ubuntu ставится **Claude Code** (терминал):

```bash
curl -fsSL https://claude.ai/install.sh | bash
```

Дальше в папке проекта `claude` → вход в аккаунт. Тогда Claude сам запускает расчёты, читает логи,
делает картинки — без пересылки скриншотов и `tail`. Чтобы тот же сеанс был виден с телефона или из
claude.ai: в папке проекта `claude remote-control`, сеанс появится в приложении Claude Code.
Облачный чат тоже может подключиться к такой папке (с подтверждением пользователя).

Правила, когда Claude работает на машине пользователя: длинные расчёты в `tmux`; ничего вне папки
проекта без спроса; `sudo` — только с явного согласия.

### Claude Desktop для Linux (бета)

С лета 2026 есть официальная бета (https://code.claude.com/docs/en/desktop-linux): Ubuntu 22.04+ / Debian 12+, x86_64.
Работают чат, вкладка **Code** (сессии Claude Code прямо на этом ПК, терминал, просмотр правок) и Cowork.
Нет: computer use (управление экраном), диктовка. Ставится из apt-репозитория Anthropic:

```bash
sudo apt install curl gnupg
```

```bash
sudo curl -fsSLo /usr/share/keyrings/claude-desktop-archive-keyring.asc https://downloads.claude.ai/claude-desktop/key.asc
```

```bash
gpg --show-keys /usr/share/keyrings/claude-desktop-archive-keyring.asc
```

Отпечаток должен быть ровно `31DDDE24DDFAB679F42D7BD2BAA929FF1A7ECACE`.

```bash
echo "deb [arch=amd64,arm64 signed-by=/usr/share/keyrings/claude-desktop-archive-keyring.asc] https://downloads.claude.ai/claude-desktop/apt/stable stable main" | sudo tee /etc/apt/sources.list.d/claude-desktop.list
```

```bash
sudo apt update && sudo apt install claude-desktop
```

Запуск: «Claude» в меню приложений или `claude-desktop`; не от root. Обновления — обычным `apt upgrade`.
Cowork дополнительно требует KVM/QEMU (`sudo usermod -aG kvm $USER` и др., см. страницу) — нам не обязателен.
Remote Control (`/remote-control` в сессии вкладки Code или настройка в Settings → Code): сессия идёт на ПК,
а смотреть и писать в неё можно с телефона или из claude.ai. ПК при этом должен быть включён.
