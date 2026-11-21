# WHB macro 6: save the standard set of screenshots into the case folder:
#   pv_T.png, pv_U.png, pv_prgh.png (longitudinal slice), pv_cross_Ux.png (cross-section).
# Runs macros 1..5 itself; the case must be open (paraFoam -builtin).
import os
from paraview.simple import *

# the other macros are looked up next to this file or in the ParaView macro folders
CANDIDATES = []
if "__file__" in globals():
    CANDIDATES.append(os.path.dirname(os.path.abspath(__file__)))
CANDIDATES += [os.path.expanduser("~/.config/ParaView/Macros"),
               os.path.join(os.environ.get("APPDATA", ""), "ParaView", "Macros")]


def run(name):
    for d in CANDIDATES:
        path = os.path.join(d, name)
        if os.path.exists(path):
            exec(open(path, encoding="utf-8").read(), {"__file__": path, "__name__": "__main__"})
            return
    raise RuntimeError(f"macro {name} not found in {CANDIDATES}")


reader = None
for (n, _), s in GetSources().items():
    if s.GetXMLName() in ("OpenFOAMReader", "POpenFOAMReader") or n.lower().endswith((".foam", ".openfoam")):
        reader = s
if reader is None:
    raise RuntimeError("No OpenFOAM case open")
case_dir = os.path.dirname(reader.FileName)
view = GetActiveViewOrCreate("RenderView")
res = [1800, 1000]

run("whb_1_setup.py")
SaveScreenshot(os.path.join(case_dir, "pv_T.png"), view, ImageResolution=res)
run("whb_3_colour_U.py")
SaveScreenshot(os.path.join(case_dir, "pv_U.png"), view, ImageResolution=res)
run("whb_4_colour_prgh.py")
SaveScreenshot(os.path.join(case_dir, "pv_prgh.png"), view, ImageResolution=res)
run("whb_5_cross.py")
SaveScreenshot(os.path.join(case_dir, "pv_cross_Ux.png"), view, ImageResolution=[1000, 1200])
# back to the longitudinal view
for (n, _), s in GetSources().items():
    if n == "WHB_cross":
        Hide(s, view)
run("whb_1_setup.py")
print("saved pv_*.png in", case_dir)
