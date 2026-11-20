# CFD-WHB

CFD-расчёты котла-утилизатора за CFB-топкой (OpenFOAM-12 Foundation; у пользователя — blueCFD-Core 2024 на Windows).

**Новый чат: начинать с `docs/HANDOFF.md`** (полная передача проекта), затем `docs/MODEL_SETUP.md`.

- `docs/HANDOFF.md` — пользователь, объект, данные DCS, модель, калибровка, выводы, состояние, следующие шаги.
- `docs/MODEL_SETUP.md` — все условия модели. `docs/PROJECT_NOTES.md` — исходные данные и результаты по ходу.
- `docs/CALIBRATION.md` — калибровка «губки» (пористых пучков). `docs/HOME_RUN.md` — запуск у пользователя.
- `model/` — генератор кейса, увязка пара, сводка, картинки. `run_night.sh`, `run_variants.sh` — серии.
- `tools/setup_openfoam12.sh` — установка OpenFOAM-12 в облачном контейнере Claude.
