# WHB macro 2: colour the active slice by gas temperature, fixed scale 250..760 C.
from paraview.simple import *

view = GetActiveViewOrCreate("RenderView")
src = FindSource("WHB_slice") or GetActiveSource()
disp = GetDisplayProperties(src, view)
for _n in ("T", "U", "p_rgh"):                       # keep only the scalar bar of this macro
    try:
        GetScalarBar(GetColorTransferFunction(_n), view).Visibility = 0
    except Exception:
        pass
ColorBy(disp, ("POINTS", "T"))
lut = GetColorTransferFunction("T")
lut.ApplyPreset("Inferno (matplotlib)", True)
lut.RescaleTransferFunction(523.15, 1033.15)
GetOpacityTransferFunction("T").RescaleTransferFunction(523.15, 1033.15)
disp.SetScalarBarVisibility(view, True)
GetScalarBar(lut, view).Title = "T, K  (C = K - 273)"
GetScalarBar(lut, view).ComponentTitle = ""
Render()
