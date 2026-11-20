"""Geometry of the waste heat boiler (WHB), parameters in metres. Version v1.

Sources: user's sketch (scaled by 33.7 m from the inner bend of the duct
to the bottom of the left hopper), plan section through the bundles (pitches and gaps in mm),
superheater element drawing, side view with headers
(bundles 6.7 m deep in the gas from the ceiling; bundle bottoms = hopper tops = ridge).
Elevations (ceiling 19.81, hopper bottom 0) are from the sketch; check against drawings.

Coordinates: x - along the boiler in the gas flow direction, z - up, y - across (width,
y = 0 at mid-width). x = 0 - left wall of the vertical duct, z = 0 - hopper bottom.
Simplifications v1: lateral offset of the duct ignored; outlet narrowing across the width
ignored (outlet over the full width); small steps of the contour smoothed.
"""

W = 4.666                # gas width: 4686 between membrane tube axes minus 20 mm tube, m
W_HOP_BOT = 1.6          # hopper bottom width across the boiler, m (estimate from sketch)

Z_CEIL = 19.81           # boiler ceiling (sketch)
BUNDLE_DEPTH = 6.7       # bundles in the gas below the ceiling
Z_HOP = Z_CEIL - BUNDLE_DEPTH   # bundle bottoms = hopper tops = ridge

SHAFT = 3.7              # vertical duct along x
X_APEX = 10.26           # ridge between the hoppers (sketch)

# Inclined duct (sketch), points (x, z)
INLET_OUTER = (-5.27, 44.84)
INLET_INNER = (-6.27, 40.44)
BEND_INNER = (0.0, 33.70)        # reference point of the 33.7 m dimension
BEND_OUTER = (SHAFT, 35.38)

# Bundles along x from the plan (mm): evaporator 264, SH 780 each; gaps 1636/1665/1474/1427
# The evaporator ends ~0.2 m before the ridge (side view).
X_EVAP0 = X_APEX - 0.2 - 0.264
_seq = [("EVAP", 0.264), ("gap", 1.636), ("SH1", 0.78), ("gap", 1.665),
        ("SH2", 0.78), ("gap", 1.474), ("SH3", 0.78), ("gap", 1.427), ("SH4", 0.78)]
BUNDLES = []             # (name, x0, x1); SH1..SH4 by gas = SH IIIb, IIIa, II, I
_x = X_EVAP0
for _n, _l in _seq:
    if _n != "gap":
        BUNDLES.append((_n, _x, _x + _l))
    _x += _l
X_RIGHT = BUNDLES[-1][2] + 0.92   # right hopper wall / start of the outlet narrowing (side view)

# Outlet (side view): bottom rises 2.37 m, ceiling drops 1.23 m over 2.75 m
X_OUT = X_RIGHT + 2.75
Z_OUT_BOT = Z_HOP + 2.37
Z_OUT_TOP = Z_CEIL - 1.23
OUTLET_EXT = 8.0          # extension of the outlet duct

# Hoppers: bottom flat ~1.2 m along x, centres 10 m apart
HOP1_BOT = (4.70, 5.90)
HOP2_BOT = (14.70, 15.90)

# Tube bundles (in-line, vertical tubes d = 38 mm)
D_TUBE = 0.038
S_TRANS = 0.100           # pitch across the width, 46 rows
N_ACROSS = 46
TUBES = {  # tubes along the gas flow
    "EVAP": 4,            # pitch 88
    "SH1": 12, "SH2": 12, "SH3": 12, "SH4": 12,   # 4 groups of 3, pitches 60/100
}
