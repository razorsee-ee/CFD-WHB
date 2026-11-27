"""Rough 1-D comparison: OUR WHB (1766 m2 SH, no partitions, CFD gas shares) vs the OLD WHB
(~2500 m2, partitions -> ~all gas through bundles, very dirty).

Reuses the functions of docs/audit/thermal_audit.py (copied to audit_lib.py, outputs stripped).
Same gas as ours for both boilers (old-boiler gas/steam data are unknown) unless stated.
Run: ~/venvs/cfd/bin/python boiler_compare.py
"""
import math
import os
import sys
from scipy.optimize import brentq

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audit_lib as L  # noqa: E402

order = ["IIIb", "IIIa", "II", "I"]
m_st = {"I": 15.92, "II": 15.96, "IIIa": 16.01, "IIIb": 16.10}
A1 = L.area("I")                       # 442 m2 per SH stage
A_SH = 4 * A1                          # 1766 m2
A_EV = L.area("EVAP")                  # 147 m2
A_WALL_BOILER = 868.0                  # CFD v0 boiler walls (HANDOFF 9e / audit 5)
T0 = 706.0
WALL_K = 3.1

phi_all = {s: 1.0 for s in order}
phi_cfd = {"IIIb": 0.90, "IIIa": 0.66, "II": 0.56, "I": 0.67}


def chain(R, phi, af=1.0, vfac=1.0, mfac=1.0, T0=T0):
    """Gas IIIb -> I, steam counter-current, bypass mixes in the gaps.
    af   - area factor per stage (extra area = deeper bundles, same frontal velocity)
    vfac - frontal velocity factor (e.g. extra area from a larger cross-section -> vfac < 1)
    mfac - gas mass flow factor (steam flow kept)."""
    mdot = L.MDOT * mfac
    Tsm = {"I": 271, "II": 317, "IIIa": 368, "IIIb": 418}
    for _ in range(80):
        Tg = T0
        Q = {}
        for s in order:
            ph = phi[s]
            Cb = ph * mdot * L.cpeff
            U0 = vfac * ph * mdot / L.gas_props(Tg + 273.15)["rho"] / L.A_FRONT
            hc = L.h_zuk(U0, Tg + 273.15, 12)[0]
            hs = L.h_steam(Tsm[s], m_st[s])[0]
            Ts = Tsm[s] + 100
            for _ in range(20):
                hr = L.h_rad(Tg + 273.15, Ts + 273.15, s)
                Uo = 1 / (1 / (hc + hr) + R + 1 / hs)
                Ts = Tsm[s] + Uo * (Tg - Tsm[s]) * (R + 1 / hs)
            UA = Uo * A1 * af
            Tout_b = Tsm[s] + (Tg - Tsm[s]) * math.exp(-UA / Cb)
            Q[s] = Cb * (Tg - Tout_b)
            Tg = ph * Tout_b + (1 - ph) * Tg - WALL_K / mfac
        h = L.hst(251.0)
        Tin, Tout = {}, {}
        for s in reversed(order):
            if s == "II":
                h = (15.92 * h + 0.04 * 1087e3) / 15.96
            if s == "IIIa":
                h = (15.96 * h + 0.05 * 1087e3) / 16.01
            if s == "IIIb":
                h = (16.01 * h + 0.09 * 1087e3) / 16.10
            Tin[s] = L.Tst(h)
            h += Q[s] / m_st[s]
            Tout[s] = L.Tst(h)
        new = {s: 0.5 * (Tin[s] + Tout[s]) for s in order}
        if max(abs(new[s] - Tsm[s]) for s in order) < 0.05:
            break
        Tsm = {s: 0.5 * (Tsm[s] + new[s]) for s in order}
    hfin = (16.10 * h + 0.07 * 1087e3) / 16.17
    return sum(Q.values()) / 1e6, L.Tst(hfin), Tg, Uo


out = []


def pr(*s):
    out.append(" ".join(str(x) for x in s))


# DCS steam-side heat (same as audit)
dcs_T = {"I": (251, 291), "II": (290, 343), "IIIa": (341, 395), "IIIb": (394, 441)}
QD = sum(m_st[s] * (L.hst(b) - L.hst(a)) for s, (a, b) in dcs_T.items()) / 1e6
R_ours = brentq(lambda R: chain(R, phi_cfd)[0] - QD, 0.0, 0.3)
pr(f"SH area per stage {A1:.0f} m2, SH {A_SH:.0f} m2, EVAP {A_EV:.0f} m2, boiler walls {A_WALL_BOILER:.0f} m2")
pr(f"DCS SH heat {QD:.2f} MW; 1-D R fitting DCS with CFD gas shares (ours today) R_ours = {R_ours:.4f}")

# area interpretations of '2500 m2'
A_tot_ours = A_SH + A_EV + A_WALL_BOILER
interp = {
    "A: 2500 = SH only": 2500 / A_SH,
    "B: 2500 = SH+EVAP": 2500 * A_SH / (A_SH + A_EV) / A_SH,
    "C: 2500 = SH+EVAP+walls": 2500 * A_SH / A_tot_ours / A_SH,
}
pr(f"ours SH+EVAP = {A_SH + A_EV:.0f} m2, SH+EVAP+boiler walls = {A_tot_ours:.0f} m2")
for k, f in interp.items():
    pr(f"  {k}: old SH area = {f * A_SH:.0f} m2 (x{f:.3f} of ours)")

pr("\n=== 1. OUR boiler (1766 m2 SH, CFD gas shares 0.90/0.66/0.56/0.67) ===")
pr("R | SH MW | steam out (no spray control) | gas after SH I | U W/m2K (SH I)")
for R in (R_ours, 0.05, 0.03, 0.02, 0.015, 0.01):
    q, ts, tg, U = chain(R, phi_cfd)
    pr(f"{R:.4f} | {q:.2f} | {ts:.0f} | {tg:.0f} | {U:.1f}")

pr("\n=== 2. OLD boiler, same gas, partitions (phi = 1), R scan ===")
pr("interp | R | SH MW | vs ours DCS | steam out | gas after SH I | NTU per stage")
for k, f in interp.items():
    for R in (0.03, 0.04, 0.05, 0.06, 0.08, 0.10):
        q, ts, tg, U = chain(R, phi_all, af=f)
        ntu = U * A1 * f / (L.MDOT * L.cpeff)
        pr(f"{k[:2]} | {R:.2f} | {q:.2f} | {100 * (q / QD - 1):+.0f} % | {ts:.0f} | {tg:.0f} | {ntu:.3f}")

pr("\n=== 3. R the old boiler needs to MATCH ours (SH = DCS 8.31 MW) ===")
pr("interp | R_old (phi=1) | R_old/R_ours | R_old if partitions leak (CFD shares) | (velocity x0.7, phi=1)")
for k, f in interp.items():
    r1 = brentq(lambda R: chain(R, phi_all, af=f)[0] - QD, 0.0, 0.5)
    r2 = brentq(lambda R: chain(R, phi_cfd, af=f)[0] - QD, 0.0, 0.5)
    r3 = brentq(lambda R: chain(R, phi_all, af=f, vfac=0.7)[0] - QD, 0.0, 0.5)
    pr(f"{k} | {r1:.4f} | {r1 / R_ours:.2f} | {r2:.4f} | {r3:.4f}")

pr("\n=== 4. Levers separately, starting from ours today (R_ours, 1766 m2, CFD shares) ===")
q0 = chain(R_ours, phi_cfd)[0]
cases = [
    ("partitions only (phi=1)", dict(R=R_ours, phi=phi_all)),
    ("area x1.42 only (2500 SH)", dict(R=R_ours, phi=phi_cfd, af=2500 / A_SH)),
    ("area x1.42 + partitions", dict(R=R_ours, phi=phi_all, af=2500 / A_SH)),
    ("R -> 0.02 only", dict(R=0.02, phi=phi_cfd)),
    ("R -> 0.03 only", dict(R=0.03, phi=phi_cfd)),
    ("R -> 0.08 only (dirtier)", dict(R=0.08, phi=phi_cfd)),
    ("R -> 0.10 only (dirtier)", dict(R=0.10, phi=phi_cfd)),
    ("old: 2500 SH, phi=1, R 0.08", dict(R=0.08, phi=phi_all, af=2500 / A_SH)),
    ("old: 2500 SH, phi=1, R 0.10", dict(R=0.10, phi=phi_all, af=2500 / A_SH)),
]
pr(f"base | {q0:.2f} MW")
for lab, kw in cases:
    q, ts, tg, _ = chain(kw["R"], kw["phi"], af=kw.get("af", 1.0))
    pr(f"{lab} | {q:.2f} | {100 * (q / q0 - 1):+.1f} % | steam {ts:.0f} | gas {tg:.0f}")

pr("\n=== 5. Partitions effect at other R / area (gain of phi=1 over CFD shares) ===")
for f in (1.0, 2500 / A_SH):
    for R in (0.01, 0.02, 0.05, 0.08, 0.10):
        qa = chain(R, phi_cfd, af=f)[0]
        qb = chain(R, phi_all, af=f)[0]
        pr(f"area x{f:.2f} R {R:.2f}: {qa:.2f} -> {qb:.2f} MW ({100 * (qb / qa - 1):+.1f} %)")

pr("\n=== 6. Sensitivity of old-boiler result to its (unknown) gas: 2500 SH, phi=1, R 0.08 ===")
qb = chain(0.08, phi_all, af=2500 / A_SH)[0]
pr(f"base same gas: {qb:.2f} MW")
for lab, kw in (("gas flow x0.8", dict(mfac=0.8)), ("gas flow x1.2", dict(mfac=1.2)),
                ("T before SH -50 K", dict(T0=T0 - 50)), ("T before SH +50 K", dict(T0=T0 + 50)),
                ("velocity x0.7 (larger section)", dict(vfac=0.7))):
    q = chain(0.08, phi_all, af=2500 / A_SH, **kw)[0]
    pr(f"{lab}: {q:.2f} MW ({100 * (q / qb - 1):+.0f} %)")

pr("\n=== 7. Deposit thickness for R (cylindrical, tube 38 mm, outer area ref.) ===")
pr("R | k=0.05 | k=0.1 | k=0.2 W/mK -> mm (gap in 3-tube group 22 mm)")
for R in (0.01, 0.02, 0.05, 0.06, 0.08, 0.10):
    ds = [1000 * 0.019 * (math.exp(R * k / 0.019) - 1) for k in (0.05, 0.1, 0.2)]
    pr(f"{R:.2f} | " + " | ".join(f"{d:.1f}" for d in ds))

print("\n".join(out))
open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "boiler_compare_out.txt"), "w").write("\n".join(out) + "\n")
