# Макросы ParaView для кейсов котла (WHB)

Кнопки на панели ParaView, которые за один клик делают стандартные виды. Проверены в ParaView 5.11
(pvbatch, Linux) на кейсе из `model/make_case.py`; в ParaView из blueCFD не проверены.

| макрос | что делает |
|---|---|
| `whb_1_setup` | последний момент времени, продольный разрез посередине ширины, контуры пучков (испаритель зелёный), раскраска T (250–760 °C, в K), вид сбоку. **Нажимать первым.** |
| `whb_2_colour_T` | раскраска разреза по температуре, фиксированная шкала |
| `whb_3_colour_U` | по модулю скорости, 0–15 м/с |
| `whb_4_colour_prgh` | по p_rgh (давление без гидростатики) — где теряется напор |
| `whb_5_cross` | поперечный разрез между SH IIIa и SH II, скорость вдоль котла Ux (синее — обратный ток); видно газ под пучками |
| `whb_6_screenshots` | сам прогоняет 1–5 и сохраняет `pv_T.png`, `pv_U.png`, `pv_prgh.png`, `pv_cross_Ux.png` в папку кейса |

## Установка (один раз)

ParaView → меню **Macros → Import new macro...** → выбрать все файлы `whb_*.py` из
`CFD-WHB/tools/paraview/`. Они появятся в меню Macros и кнопками на панели «Macros Toolbars».
(Файлы копируются в папку макросов ParaView: Windows `%APPDATA%\ParaView\Macros`, Linux `~/.config/ParaView/Macros`.)
После обновления проекта (`git pull`) — импортировать заново, чтобы обновились копии.

## Использование

```bash
cd $FOAM_RUN/cal_3 && paraFoam -builtin
```
В ParaView: Properties → Case Type (Reconstructed / Decomposed) → **Apply** → кнопка `whb_1_setup` →
дальше любые кнопки 2–5, или сразу `whb_6_screenshots`.
