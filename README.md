# CFD-WHB

CFD-расчёты котла-утилизатора за CFB-топкой (OpenFOAM-12 Foundation; у пользователя — blueCFD-Core 2024 на Windows).

**Новый чат: начинать с `CLAUDE.md`, затем `docs/HANDOFF.md`** (полная передача проекта), затем `docs/MODEL_SETUP.md`.

- `docs/LINUX_OF14.md` — **решение 21.11.2026**: Ubuntu 26.04 + OpenFOAM-14 на ПК пользователя, старые кейсы остаются на blueCFD (OF-12); установка и отличия синтаксиса 12 → 14.
- `docs/INSTALL_UBUNTU26_PC.md` — как ставили Ubuntu 26.04 рядом с Windows на домашнем ПК без флешки.
- `docs/NEW_PROJECT_OPENFOAM.md` — с чего начинать: пользователь и его система, стартовые точки для CFB, известные грабли OpenFOAM-12 и Windows.
- `tools/setup_openfoam14.sh` — OpenFOAM-14 пакетом в облачном контейнере Claude (`source /opt/of14env.sh`).

- `docs/HANDOFF.md` — пользователь, объект, данные DCS, модель, калибровка, выводы, состояние, следующие шаги.
- `docs/MODEL_SETUP.md` — все условия модели. `docs/PROJECT_NOTES.md` — исходные данные и результаты по ходу.
- `docs/CALIBRATION.md` — калибровка «губки» (пористых пучков). `docs/HOME_RUN.md` — запуск у пользователя.
- `model/` — генератор кейса, увязка пара, сводка, картинки. `run_night.sh`, `run_variants.sh` — серии.
- `tools/setup_openfoam12.sh` — установка OpenFOAM-12 в облачном контейнере Claude.
