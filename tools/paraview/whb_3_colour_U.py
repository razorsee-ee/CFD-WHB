# WHB macro 3: colour the active slice by velocity magnitude, fixed scale 0..15 m/s.
from paraview.simple import *

view = GetActiveViewOrCreate("RenderView")
src = FindSource("WHB_slice") or GetActiveSource()
disp = GetDisplayProperties(src, view)
for _n in ("T", "U", "p_rgh"):                       # keep only the scalar bar of this macro
    try:
        GetScalarBar(GetColorTransferFunction(_n), view).Visibility = 0
    except Exception:
        pass
ColorBy(disp, ("POINTS", "U", "Magnitude"))
lut = GetColorTransferFunction("U")
lut.VectorMode = "Magnitude"
lut.ApplyPreset("Viridis (matplotlib)", True)
lut.RescaleTransferFunction(0.0, 15.0)
GetOpacityTransferFunction("U").RescaleTransferFunction(0.0, 15.0)
disp.SetScalarBarVisibility(view, True)
GetScalarBar(lut, view).Title = "|U|, m/s"
GetScalarBar(lut, view).ComponentTitle = ""
Render()
