# Open a WHB case in the ParaView GUI with the standard view ready:
#   cd <case> && paraview --script=$HOME/OpenFOAM/run/CFD-WHB/tools/paraview/open_whb.py
# Mid-width slice coloured by |U| (0-15 m/s), bundle outlines, skirts/plates (SKIRTS boxes from
# system/createZonesDict) as red boxes. Other colourings: macros whb_2..whb_5 from this folder.
import os
import re

from paraview.simple import *

HERE = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else \
    os.path.expanduser("~/OpenFOAM/run/CFD-WHB/tools/paraview")
case = os.getcwd()
foam = os.path.join(case, os.path.basename(case) + ".foam")
if not os.path.exists(foam):
    open(foam, "w").close()
reader = OpenFOAMReader(registrationName=os.path.basename(foam), FileName=foam)
reader.MeshRegions = ["internalMesh"]
reader.CellArrays = ["T", "U", "p_rgh", "p"]

for macro in ("whb_1_setup.py", "whb_3_colour_U.py"):
    with open(os.path.join(HERE, macro)) as f:
        ns = {"__name__": "__main__", "Hide3DWidgets": lambda *a, **k: None}   # missing in --script mode
        exec(compile(f.read(), macro, "exec"), ns)

# skirts / plates
view = GetActiveViewOrCreate("RenderView")
zd = os.path.join(case, "system", "createZonesDict")
if os.path.exists(zd):
    m = re.search(r"SKIRTS\s*\{(.*?)\}", open(zd).read(), re.S)
    if m:
        v = [float(t) for t in re.findall(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", m.group(1))]
        for i in range(0, len(v) - 5, 6):
            x0, z0, x1, z1 = v[i], max(v[i + 2], 4.0), v[i + 3], v[i + 5]
            b = Box(registrationName=f"WHB_skirt_{i // 6}")
            b.XLength, b.YLength, b.ZLength = x1 - x0, 0.05, z1 - z0
            b.Center = [(x0 + x1) / 2, -2.1, (z0 + z1) / 2]
            d = Show(b, view)
            d.SetRepresentationType("Surface")
            d.AmbientColor = d.DiffuseColor = [1.0, 0.25, 0.25]
SetActiveSource(FindSource("WHB_slice"))
Render()
