# CFD-WHB

CFD-расчёты котла (OpenFOAM-12 Foundation; у пользователя — blueCFD-Core 2024 на Windows).

- `docs/NEW_PROJECT_OPENFOAM.md` — с чего начинать: пользователь и его система, установка OpenFOAM в облаке, стартовые точки для CFB, известные грабли OpenFOAM-12 и Windows.
- `tools/setup_openfoam12.sh` — установка OpenFOAM-12 в облачном контейнере Claude:
  `bash tools/setup_openfoam12.sh > /tmp/setup_openfoam12.log 2>&1`, затем `source /opt/of12env.sh`.

Соседний проект с теми же приёмами: `razorsee-ee/CFD-Venturi` (скруббер Вентури).
