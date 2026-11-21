# WHB macro 5: cross-section in the gap between SH IIIa and SH II (x = 15.66 m), coloured by the
# velocity along the boiler Ux (red = forward, blue = backflow). Shows the gas going under the
# bundles over the right hopper. Looks along the boiler (from -X). Run macro 1 first.
from paraview.simple import *

X_CUT = 15.658
reader = None
for (name, _), s in GetSources().items():
    if s.GetXMLName() in ("OpenFOAMReader", "POpenFOAMReader") or name.lower().endswith((".foam", ".openfoam")):
        reader = s
if reader is None:
    raise RuntimeError("No OpenFOAM case open")

view = GetActiveViewOrCreate("RenderView")
cut = FindSource("WHB_cross")
if cut is None:
    cut = Slice(registrationName="WHB_cross", Input=reader)
cut.SliceType = "Plane"
cut.SliceType.Origin = [X_CUT, 0.0, 10.0]
cut.SliceType.Normal = [1.0, 0.0, 0.0]
Hide3DWidgets(proxy=cut.SliceType)
for (name, _), s in GetSources().items():            # show only the cross-section
    if name != "WHB_cross":
        Hide(s, view)
disp = Show(cut, view)
for _n in ("T", "U", "p_rgh"):                       # keep only the scalar bar of this macro
    try:
        GetScalarBar(GetColorTransferFunction(_n), view).Visibility = 0
    except Exception:
        pass
ColorBy(disp, ("POINTS", "U", "X"))
lut = GetColorTransferFunction("U")
lut.VectorMode = "Component"
lut.VectorComponent = 0
lut.ApplyPreset("Blue Orange (divergent)", True)
lut.RescaleTransferFunction(-6.0, 15.0)
disp.SetScalarBarVisibility(view, True)
GetScalarBar(lut, view).Title = "Ux, m/s"
GetScalarBar(lut, view).ComponentTitle = ""

view.CameraPosition = [-100.0, 0.0, 10.0]
view.CameraFocalPoint = [X_CUT, 0.0, 10.0]
view.CameraViewUp = [0.0, 0.0, 1.0]
view.CameraParallelProjection = 1
view.ResetCamera(False)
SetActiveSource(cut)
Render()
