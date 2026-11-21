# WHB macro 1: standard longitudinal view.
# Uses the OpenFOAM reader already open in ParaView (paraFoam -builtin), goes to the last time,
# makes a mid-width slice (normal Y), outlines the bundles, colours by T with a fixed scale and
# looks from the side (-Y). Run it once after opening the case; then use the colour macros.
from paraview.simple import *

# geometry of the model (model/geometry.py), metres
BUNDLES = {"EVAP": (9.796, 10.060), "SH IIIb": (11.696, 12.476), "SH IIIa": (14.141, 14.921),
           "SH II": (16.395, 17.175), "SH I": (18.602, 19.382)}
Z_HOP, Z_CEIL, W = 13.11, 19.81, 4.666


def find_reader():
    for (name, _), src in GetSources().items():
        if src.GetXMLName() in ("OpenFOAMReader", "POpenFOAMReader") or name.lower().endswith((".foam", ".openfoam")):
            return src
    raise RuntimeError("No OpenFOAM case open: start ParaView with 'paraFoam -builtin' in the case folder")


reader = find_reader()
try:
    reader.MeshRegions = ["internalMesh"]
except AttributeError:
    pass
reader.UpdatePipelineInformation()
scene = GetAnimationScene()
scene.UpdateAnimationUsingDataTimeSteps()
scene.GoToLast()

view = GetActiveViewOrCreate("RenderView")
Hide(reader, view)

sl = FindSource("WHB_slice")
if sl is None:
    sl = Slice(registrationName="WHB_slice", Input=reader)
sl.SliceType = "Plane"
sl.SliceType.Origin = [0.0, 0.0, 0.0]
sl.SliceType.Normal = [0.0, 1.0, 0.0]
try:
    sl.HyperTreeGridSlicer = "Plane"
except AttributeError:
    pass
disp = Show(sl, view)
try:
    sl.SliceType.Visibility = 0          # hide the plane widget if the property exists
except AttributeError:
    pass
Hide3DWidgets(proxy=sl.SliceType)

for _n in ("T", "U", "p_rgh"):                       # keep only the scalar bar of this macro
    try:
        GetScalarBar(GetColorTransferFunction(_n), view).Visibility = 0
    except Exception:
        pass
ColorBy(disp, ("POINTS", "T"))
lut = GetColorTransferFunction("T")
lut.ApplyPreset("Inferno (matplotlib)", True)
lut.RescaleTransferFunction(523.15, 1033.15)          # 250 .. 760 C (field is in K)
GetOpacityTransferFunction("T").RescaleTransferFunction(523.15, 1033.15)
disp.SetScalarBarVisibility(view, True)
bar = GetScalarBar(lut, view)
bar.Title = "T, K  (C = K - 273)"
bar.ComponentTitle = ""

# bundle outlines (white boxes in the slice plane)
for name, (x0, x1) in BUNDLES.items():
    reg = "WHB_box_" + name.replace(" ", "_")
    box = FindSource(reg)
    if box is None:
        box = Box(registrationName=reg)
    box.XLength, box.YLength, box.ZLength = x1 - x0, 0.05, Z_CEIL - Z_HOP
    box.Center = [(x0 + x1) / 2, -2.0, (Z_HOP + Z_CEIL) / 2]   # just in front of the slice
    bd = Show(box, view)
    bd.SetRepresentationType("Outline")
    bd.AmbientColor = bd.DiffuseColor = [0.2, 1.0, 0.2] if name == "EVAP" else [1.0, 1.0, 1.0]
    bd.LineWidth = 2.0

# side view from -Y
view.CameraPosition = [12.0, -120.0, 22.0]
view.CameraFocalPoint = [12.0, 0.0, 22.0]
view.CameraViewUp = [0.0, 0.0, 1.0]
view.CameraParallelProjection = 1
view.ResetCamera(False)
SetActiveSource(sl)
Render()
