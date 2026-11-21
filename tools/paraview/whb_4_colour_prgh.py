# WHB macro 4: colour the active slice by p_rgh (pressure without the hydrostatic part).
# Shows where the pressure is lost (bundles, turns). Range from the data (1..99 % would need numpy,
# so the full data range is used; adjust with "Rescale to custom range" if needed).
from paraview.simple import *

view = GetActiveViewOrCreate("RenderView")
src = FindSource("WHB_slice") or GetActiveSource()
disp = GetDisplayProperties(src, view)
for _n in ("T", "U", "p_rgh"):                       # keep only the scalar bar of this macro
    try:
        GetScalarBar(GetColorTransferFunction(_n), view).Visibility = 0
    except Exception:
        pass
ColorBy(disp, ("POINTS", "p_rgh"))
lut = GetColorTransferFunction("p_rgh")
lut.ApplyPreset("Cool to Warm", True)
disp.RescaleTransferFunctionToDataRange(False, True)
disp.SetScalarBarVisibility(view, True)
GetScalarBar(lut, view).Title = "p_rgh, Pa (relative to pRef)"
GetScalarBar(lut, view).ComponentTitle = ""
Render()
