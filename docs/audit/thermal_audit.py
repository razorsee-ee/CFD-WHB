"""Independent 1-D thermal audit of the WHB model (no OpenFOAM).

Run: ~/venvs/cfd/bin/python thermal_audit.py
Everything here is first-principles / correlations; model values are only read for comparison.
"""
import math
from functools import lru_cache
import numpy as np
from scipy.optimize import brentq
import CoolProp.CoolProp as CP

SIG = 5.670e-8
# ------------------------------------------------------------------ gas
kmol = {"N2": 6796.0, "CO2": 1433.1, "H2O": 1667.0, "O2": 253.42}
kmol["H2O"] += 14000 / 18.015
air = 10000 / 22.414
kmol["O2"] += 0.21 * air
kmol["N2"] += 0.79 * air + 2000 / 22.414
MW = {"N2": 28.013, "CO2": 44.01, "H2O": 18.015, "O2": 31.999}
CPN = {"N2": "Nitrogen", "CO2": "CarbonDioxide", "H2O": "Water", "O2": "Oxygen"}
ntot = sum(kmol.values())
X = {k: v / ntot for k, v in kmol.items()}
M = sum(X[k] * MW[k] for k in X)
MDOT = ntot * M / 3600
P = 111800.0


def pure(k, T):
    p = 1e4   # low pressure: ideal-gas-like transport
    mu = CP.PropsSI("V", "T", T, "P", p, CPN[k])
    lam = CP.PropsSI("L", "T", T, "P", p, CPN[k])
    cp = CP.PropsSI("CP0MASS", "T", T, "P", p, CPN[k])
    return mu, lam, cp


def gas_props(T):
    return _gp(round(T, 0))


@lru_cache(maxsize=None)
def _gp(T):
    ks = list(X)
    mu = {}; lam = {}; cpm = {}
    for k in ks:
        mu[k], lam[k], cpm[k] = pure(k, T)
    def phi(i, j):
        return (1 + (mu[i] / mu[j]) ** 0.5 * (MW[j] / MW[i]) ** 0.25) ** 2 / (8 * (1 + MW[i] / MW[j])) ** 0.5
    mum = sum(X[i] * mu[i] / sum(X[j] * phi(i, j) for j in ks) for i in ks)          # Wilke
    lamm = sum(X[i] * lam[i] / sum(X[j] * phi(i, j) for j in ks) for i in ks)        # Wassiljewa/Mason-Saxena
    w = {k: X[k] * MW[k] / M for k in ks}
    cp = sum(w[k] * cpm[k] for k in ks)
    rho = P * M / (8314.46 * T)
    return dict(mu=mum, k=lamm, cp=cp, rho=rho, Pr=mum * cp / lamm, nu=mum / rho)


def mean_cp(T1, T2, n=20):
    Ts = np.linspace(T1, T2, n)
    return float(np.mean([gas_props(t)["cp"] for t in Ts]))


# dust: 40 % of 50 t/h through the bundles (model assumption)
DUST = 0.4 * 50000 / 3600
CP_DUST = 850.0

# ------------------------------------------------------------------ geometry
D = 0.038; S1 = 0.100; NACR = 46; H = 6.7; W = 4.666
BUND = {"EVAP": (4, 0.264), "IIIb": (12, 0.78), "IIIa": (12, 0.78), "II": (12, 0.78), "I": (12, 0.78)}
A_FRONT = H * W
SIGMA = 1 - D / S1


def area(name):
    nt, _ = BUND[name]
    return NACR * nt * math.pi * D * H


# ------------------------------------------------------------------ convective htc
def h_zuk(U, T, nrows):
    g = gas_props(T)
    Re = U / SIGMA * D / g["nu"]
    Nu = 0.27 * Re ** 0.63 * g["Pr"] ** 0.36
    c2 = {4: 0.90, 12: 0.99}.get(nrows, 1.0)
    return c2 * Nu * g["k"] / D, Re


def h_vdi(U, T, nrows, s2):
    """VDI Heat Atlas G7 (Gnielinski), in-line bundle, approach velocity U."""
    g = gas_props(T)
    a, b = S1 / D, s2 / D
    psi = 1 - math.pi / (4 * a)
    l = math.pi * D / 2
    Re = U * l / (psi * g["nu"])
    Pr = g["Pr"]
    nl = 0.664 * Re ** 0.5 * Pr ** (1 / 3)
    nt = 0.037 * Re ** 0.8 * Pr / (1 + 2.443 * Re ** -0.1 * (Pr ** (2 / 3) - 1))
    nu0 = 0.3 + (nl ** 2 + nt ** 2) ** 0.5
    fA = 1 + 0.7 * (b / a - 0.3) / (psi ** 1.5 * (b / a + 0.7) ** 2)
    fn = (1 + (nrows - 1) * fA) / nrows if nrows < 10 else fA
    return fn * nu0 * g["k"] / l


# ------------------------------------------------------------------ radiation in the bundle
def eps_gas_wsgg(T, pL):
    K = [0.4303, 7.055, 178.1]
    B = [[5.150, -2.303, 0.9779, -1.494], [0.7749, 3.399, -2.297, 0.3770], [1.907, -1.824, 0.5608, -0.5122]]
    F = [1e-1, 1e-4, 1e-7, 1e-11]
    return sum(sum(bj * f * T ** j for j, (bj, f) in enumerate(zip(b, F))) * (1 - math.exp(-k * pL))
               for k, b in zip(K, B))


def emiss(T, L, dust_Q=1.0, dust_d=20e-6):
    pL = (X["CO2"] + X["H2O"]) * P / 101325 * L
    eg = eps_gas_wsgg(T, pL)
    c = DUST / (MDOT / gas_props(T)["rho"])
    kd = 1.5 * c * dust_Q / (2500 * dust_d)
    ed = 1 - math.exp(-kd * L)
    return 1 - (1 - eg) * (1 - ed), eg, ed, kd


def h_rad(Tg, Ts, name):
    nt, L = BUND[name]
    s2 = L / nt
    Lb = 1.08 * (S1 * s2 - math.pi * D ** 2 / 4) / D
    e = emiss(Tg, Lb)[0]
    return SIG * (0.8 + 1) / 2 * e * (Tg ** 4 - Ts ** 4) / (Tg - Ts)


# ------------------------------------------------------------------ steam side
P_ST = 40.5e5           # SH pressure (drum 40.7 barg = 41.7 bar a, minus SH drop) - assumed
N_PAR = 138             # parallel tubes (46 elements x 3 tubes) - assumed from geometry/docs
DI = 0.030              # 38x4 (element mass 337.5 kg ~ 38x4..4.5) - assumed


def h_steam(T, m):
    return _hs(round(T, 0), round(m, 3))


@lru_cache(maxsize=None)
def _hs(T, m):
    Tk = T + 273.15
    mu = CP.PropsSI("V", "T", Tk, "P", P_ST, "Water"); lam = CP.PropsSI("L", "T", Tk, "P", P_ST, "Water")
    cp = CP.PropsSI("C", "T", Tk, "P", P_ST, "Water")
    G = m / (N_PAR * math.pi * DI ** 2 / 4)
    Re = G * DI / mu; Pr = mu * cp / lam
    f = (0.79 * math.log(Re) - 1.64) ** -2
    Nu = f / 8 * (Re - 1000) * Pr / (1 + 12.7 * (f / 8) ** 0.5 * (Pr ** (2 / 3) - 1))
    hi = Nu * lam / DI
    return hi * DI / D, hi, Re, G       # referred to the outer area


def hst(T, p=P_ST):
    Tsat = CP.PropsSI("T", "P", p, "Q", 1, "Water") - 273.15
    if T <= Tsat + 0.05:
        return CP.PropsSI("H", "P", p, "Q", 1, "Water")
    return CP.PropsSI("H", "T", T + 273.15, "P", p, "Water")


def Tst(h, p=P_ST):
    hg = CP.PropsSI("H", "P", p, "Q", 1, "Water")
    if h <= hg:
        return CP.PropsSI("T", "P", p, "Q", 1, "Water") - 273.15
    return CP.PropsSI("T", "H", h, "P", p, "Water") - 273.15


out = []
pr = lambda *s: out.append(" ".join(str(x) for x in s))

pr("=== 1. Gas ===")
pr(f"composition X: " + ", ".join(f"{k} {100 * v:.1f}%" for k, v in X.items()) + f"; M = {M:.2f}; mdot = {MDOT:.1f} kg/s")
for T in (600, 650, 700, 750):
    g = gas_props(T + 273.15)
    pr(f"T={T} C: cp={g['cp']:.0f} J/kgK  mu={g['mu']:.3e}  k={g['k']:.4f}  Pr={g['Pr']:.3f}  rho={g['rho']:.3f}")
cpg = mean_cp(618 + 273.15, 750 + 273.15)
cpeff = cpg + DUST / MDOT * CP_DUST
pr(f"mean cp gas 618-750 C = {cpg:.0f}; with 40% dust = {cpeff:.0f} J/kgK (model 1247 / 1338)")
Cg = MDOT * cpeff
pr(f"C_gas = {Cg / 1e3:.1f} kW/K; heat 750->618 = {Cg * 132 / 1e6:.2f} MW")
cap_dust = (50000 - 0.4 * 50000) / 3600
pr(f"captured dust 30 t/h (8.3 kg/s) cooling 750->500 C in hoppers: {cap_dust * 850 * 250 / 1e6:.2f} MW (not in model)")

pr("\n=== 2. Geometry ===")
for n in BUND:
    nt, L = BUND[n]
    pr(f"{n:5s}: rows along {nt}, A = {area(n):.0f} m2, Av = {area(n) / (L * W * H):.2f} 1/m")
pr(f"SH total A = {4 * area('I'):.0f} m2, EVAP {area('EVAP'):.0f} m2; front {A_FRONT:.2f} m2, sigma = {SIGMA:.2f}")
for T in (700, 650):
    V = MDOT / gas_props(T + 273.15)["rho"]
    pr(f"at {T} C: V = {V:.0f} m3/s; U0 (all gas) = {V / A_FRONT:.2f} m/s, in gaps {V / A_FRONT / SIGMA:.2f} m/s")

pr("\n=== 3. Convective htc (U = superficial velocity) ===")
pr("U m/s | Re_max | Zukauskas (12 rows) | VDI (s2 = 65 mm avg) | VDI s2=60 | model conv. (k=0.064, rho@650, no Pr fn)")
for U in (3, 4, 5, 6, 7, 8):
    hz, Re = h_zuk(U, 923.15, 12)
    hv = h_vdi(U, 923.15, 12, 0.065); hv60 = h_vdi(U, 923.15, 12, 0.060)
    rho = 111800 * 28.002 / (8314 * 923.15); Rem = U / SIGMA * D / (3.7e-5 / rho)
    hm = 0.27 * Rem ** 0.63 * 0.72 ** 0.36 * 0.064 / D
    pr(f"{U:4.0f} | {Re:6.0f} | {hz:6.1f} | {hv:6.1f} | {hv60:6.1f} | {hm:6.1f}")

pr("\n=== 4. Radiation ===")
for n, Tg in (("I", 630), ("IIIb", 700)):
    nt, L = BUND[n]; s2 = L / nt
    Lb = 1.08 * (S1 * s2 - math.pi * D ** 2 / 4) / D
    e, eg, ed, kd = emiss(Tg + 273.15, Lb)
    pr(f"in bundle {n}: Lb={Lb:.3f} m eps_gas={eg:.3f} eps_dust={ed:.3f} total={e:.3f}; k_dust={kd:.2f} 1/m")
    for Ts in (300, 450, 600):
        pr(f"   h_rad(Tg={Tg}, Ts={Ts}) = {h_rad(Tg + 273.15, Ts + 273.15, n):.1f} W/m2K")
# cavity between bundles 1.5 x 4.666 x 6.7
Vc = 1.5 * W * H; Ac = 2 * (1.5 * W + 1.5 * H + W * H)
Lm = 3.6 * Vc / Ac
for Q in (1.0, 0.5, 0.3):
    e, eg, ed, kd = emiss(683 + 273.15, Lm, dust_Q=Q)
    pr(f"cavity Lm={Lm:.2f} m, dust Qabs={Q}: eps_gas={eg:.2f} eps_dust={ed:.2f} total={e:.2f} (k_dust {kd:.2f} 1/m)")
e3 = emiss(700 + 273.15, 3.0)
pr(f"gas only over 3 m: eps={e3[1]:.3f} -> a={-math.log(1 - e3[1]) / 3:.3f} 1/m; dust k (Q=1) {e3[3]:.2f} -> sum {e3[3] - math.log(1 - e3[1]) / 3:.2f} (model 0.923)")

pr("\n=== 5. Steam side ===")
for T, m in ((271, 15.92), (317, 15.96), (368, 16.01), (418, 16.10)):
    ho, hi, Re, G = h_steam(T, m)
    pr(f"T={T}: G={G:.0f} kg/m2s Re={Re:.0f} h_i={hi:.0f} h_o(ref. outer)={ho:.0f} W/m2K  (model {600 * (15.9 / 13.9) ** 0.8:.0f})")
pr(f"if all 552 legs were parallel (G/4): h_o ~ {h_steam(368, 16.01 / 4)[0]:.0f}")

pr("\n=== 6. DCS steam-side heats (CoolProp, p=40.5 bar) ===")
dcs_T = {"I": (251, 291), "II": (290, 343), "IIIa": (341, 395), "IIIb": (394, 441)}
m_st = {"I": 15.92, "II": 15.96, "IIIa": 16.01, "IIIb": 16.10}   # spray 0.04/0.05/0.09 between stages, 0.07 final
Qdcs = {}
for s, (a, b) in dcs_T.items():
    Qdcs[s] = m_st[s] * (hst(b) - hst(a)) / 1e6
pr("DCS stage heat, MW: " + ", ".join(f"{s} {q:.2f}" for s, q in Qdcs.items()) + f"; sum {sum(Qdcs.values()):.2f}")
# spray check: 0.25 kg/s water at h 1087 kJ/kg lumped before IIIb
hmix = (15.9 * hst(395) + 0.25 * 1087e3) / 16.15
pr(f"0.25 kg/s spray lumped before IIIb would drop 395 -> {Tst(hmix):.0f} C (DCS IIIb inlet 394)")
pr(f"spray latent load 0.25 kg/s from 1087 kJ/kg to 441 C: {0.25 * (hst(441) - 1087e3) / 1e6:.2f} MW")

pr("\n=== 7. Overall U required by DCS (model-independent) ===")
order = ["IIIb", "IIIa", "II", "I"]
Tg_dcs = [702, 681, 655, 621, 618]
Tg_cfd = [706, 685, 662, 640, 621]


def clean_U(name, Tg, Tsm, phi=1.0, R=0.0):
    U0 = phi * MDOT / gas_props(Tg + 273.15)["rho"] / A_FRONT
    hc = h_zuk(U0, Tg + 273.15, BUND[name][0])[0]
    # radiation with the deposit-surface temperature (iterate)
    hs = h_steam(Tsm, 16.0)[0] if name != "EVAP" else 1e9
    Ts = Tsm + 30
    for _ in range(30):
        hr = h_rad(Tg + 273.15, Ts + 273.15, name)
        Uo = 1 / (1 / (hc + hr) + R + 1 / hs)
        q = Uo * (Tg - Tsm)
        Ts = Tsm + q * (R + 1 / hs)
    return Uo, hc, hr, hs, U0


A = area("I")
pr("stage | Q_DCS | Tg mean DCS | Ts mean | U_req(DCS T) | U_req(CFD bulk T) | clean U (phi=1 / CFD phi) | R needed (phi=1 / CFD phi)")
PHI = {"EVAP": 0.91, "IIIb": 0.90, "IIIa": 0.66, "II": 0.56, "I": 0.67}
for i, s in enumerate(order):
    a, b = dcs_T[s]
    Tsm = (a + b) / 2
    lm = lambda T1, T2: ((T1 - b) - (T2 - a)) / math.log((T1 - b) / (T2 - a))  # counterflow LMTD
    Ureq = Qdcs[s] * 1e6 / (A * lm(Tg_dcs[i], Tg_dcs[i + 1]))
    Ureq2 = Qdcs[s] * 1e6 / (A * lm(Tg_cfd[i], Tg_cfd[i + 1]))
    Tg = (Tg_dcs[i] + Tg_dcs[i + 1]) / 2
    U1 = clean_U(s, Tg, Tsm, 1.0)[0]
    U2 = clean_U(s, Tg, Tsm, PHI[s])[0]
    Rn1 = brentq(lambda R: clean_U(s, Tg, Tsm, 1.0, R)[0] - Ureq, 0, 1)
    Rn2 = brentq(lambda R: clean_U(s, Tg, Tsm, PHI[s], R)[0] - Ureq, 0, 1)
    pr(f"{s:5s} | {Qdcs[s]:.2f} | {Tg:.0f} | {Tsm:.0f} | {Ureq:.1f} | {Ureq2:.1f} | {U1:.0f} / {U2:.0f} | {Rn1:.3f} / {Rn2:.3f}")

pr("\n=== 8. 1-D chain: EVAP(skip) -> IIIb -> IIIa -> II -> I, steam counter-current ===")
T0_IIIb = 706.0      # CFD bulk before SH IIIb (DCS TC 702)
WALL_K_PER_STAGE = 3.1   # gas cooling by boiler walls per bundle+gap (CFD: 1.48 MW over 4 stages)


def chain(R, phi, area_fac=1.0, T0=T0_IIIb, hfac=1.0, Rst=None):
    """returns stage heats, steam temps, gas after SH I. phi: dict stage->through share."""
    Rst = Rst or {s: R for s in order}
    Tsm = {"I": 271, "II": 317, "IIIa": 368, "IIIb": 418}
    for it in range(60):
        Tg = T0
        Q = {}
        for s in order:
            ph = phi[s]
            Cb = ph * MDOT * cpeff
            U0 = ph * MDOT / gas_props(Tg + 273.15)["rho"] / A_FRONT
            hc = hfac * h_zuk(U0, Tg + 273.15, 12)[0]
            hs = h_steam(Tsm[s], m_st[s])[0]
            Ts = Tsm[s] + 100
            for _ in range(20):
                hr = h_rad(Tg + 273.15, Ts + 273.15, s)
                Uo = 1 / (1 / (hc + hr) + Rst[s] + 1 / hs)
                Ts = Tsm[s] + Uo * (Tg - Tsm[s]) * (Rst[s] + 1 / hs)
            UA = Uo * A * area_fac
            # steam mean temperature known (iterated) -> gas through bundle exponential approach
            Tout_b = Tsm[s] + (Tg - Tsm[s]) * math.exp(-UA / Cb)
            Q[s] = Cb * (Tg - Tout_b)
            Tmix = ph * Tout_b + (1 - ph) * Tg
            Tg = Tmix - WALL_K_PER_STAGE
        # steam side, counter-current: enters SH I
        h = hst(251.0)
        Tin = {}; Tout = {}
        for s in reversed(order):
            if s == "II":
                h = (15.92 * h + 0.04 * 1087e3) / 15.96
            if s == "IIIa":
                h = (15.96 * h + 0.05 * 1087e3) / 16.01
            if s == "IIIb":
                h = (16.01 * h + 0.09 * 1087e3) / 16.10
            Tin[s] = Tst(h)
            h += Q[s] / m_st[s]
            Tout[s] = Tst(h)
        new = {s: 0.5 * (Tin[s] + Tout[s]) for s in order}
        if max(abs(new[s] - Tsm[s]) for s in order) < 0.05:
            break
        Tsm = {s: 0.5 * (Tsm[s] + new[s]) for s in order}
    hfin = (16.10 * h + 0.07 * 1087e3) / 16.17
    return Q, Tin, Tout, Tg, Tst(hfin)


phi_all = {s: 1.0 for s in order}
phi_cfd = {"IIIb": 0.90, "IIIa": 0.66, "II": 0.56, "I": 0.67}
phi_v1 = {"IIIb": 0.91, "IIIa": 0.67, "II": 0.59, "I": 0.80}
phi_hi = {"IIIb": 0.92, "IIIa": 0.88, "II": 0.87, "I": 0.87}
pr("case | Q I / II / IIIa / IIIb, MW | sum | steam out | gas after SH I")
pr(f"DCS  | {Qdcs['I']:.2f} / {Qdcs['II']:.2f} / {Qdcs['IIIa']:.2f} / {Qdcs['IIIb']:.2f} | {sum(Qdcs.values()):.2f} | 441 | 618")
pr("CFD v0 | 2.39 / 2.17 / 2.08 / 2.03 | 8.66 | 441 | 621")
res = {}
for lab, R, phi in (("R0.05 phi=1", 0.05, phi_all), ("R0.05 phiCFD", 0.05, phi_cfd),
                    ("R0.02 phiCFD", 0.02, phi_cfd), ("R0.01 phi=1", 0.01, phi_all), ("R0.01 phiCFD", 0.01, phi_cfd),
                    ("R0.005 phiCFD", 0.005, phi_cfd), ("R0 phiCFD", 0.0, phi_cfd)):
    Q, Ti, To, Tg, Tf = chain(R, phi)
    res[lab] = (Q, Tf, Tg)
    pr(f"{lab:14s} | {Q['I'] / 1e6:.2f} / {Q['II'] / 1e6:.2f} / {Q['IIIa'] / 1e6:.2f} / {Q['IIIb'] / 1e6:.2f} | "
       f"{sum(Q.values()) / 1e6:.2f} | {Tf:.0f} | {Tg:.0f}")
QD = sum(Qdcs.values()) * 1e6
for lab, phi in (("phi=1", phi_all), ("phiCFD", phi_cfd)):
    Rfit = brentq(lambda R: sum(chain(R, phi)[0].values()) - QD, 0.0, 0.2)
    pr(f"uniform R fitting DCS 8.4 MW, {lab}: R = {Rfit:.4f} m2K/W")
for Rr in (0.01, 0.005, 0.02):
    af = brentq(lambda f: sum(chain(Rr, phi_cfd, area_fac=f)[0].values()) - QD, 0.05, 1.5)
    pr(f"with R={Rr}: area factor needed to get 8.4 MW = {af:.2f} (i.e. effective area {af * 4 * A:.0f} m2)")
for hf in (0.5,):
    Rfit = brentq(lambda R: sum(chain(R, phi_cfd, hfac=hf)[0].values()) - QD, 0.0, 0.2)
    pr(f"if convective htc were x{hf}: R needed = {Rfit:.4f}")
try:
    ph = brentq(lambda p: sum(chain(0.01, {s: p for s in order})[0].values()) - QD, 0.005, 1.0)
    pr(f"uniform through-share needed with R=0.01: {ph:.3f}")
except ValueError as e:
    pr("no phi in (0.005,1) reaches 8.4 MW with R=0.01:", e)

pr("\n=== 9. Plates / bypass closing (1-D, same R) ===")
pr("R | Q phiCFD | Q phi_v1 (plate behind SH I) | Q phi ~0.87-0.92 all | gain v1 / gain full")
for R in (0.05, 0.02, 0.01, 0.005):
    q0 = sum(chain(R, phi_cfd)[0].values()) / 1e6
    q1 = sum(chain(R, phi_v1)[0].values()) / 1e6
    q2 = sum(chain(R, phi_hi)[0].values()) / 1e6
    pr(f"{R} | {q0:.2f} | {q1:.2f} | {q2:.2f} | +{(q1 / q0 - 1) * 100:.1f} % / +{(q2 / q0 - 1) * 100:.1f} %")
# at equal effective area compensation: R=0.01 with area factor matched to DCS
Rr = 0.01
af = brentq(lambda f: sum(chain(Rr, phi_cfd, area_fac=f)[0].values()) - QD, 0.05, 1.5)
q0 = sum(chain(Rr, phi_cfd, area_fac=af)[0].values()) / 1e6
q2 = sum(chain(Rr, phi_hi, area_fac=af)[0].values()) / 1e6
pr(f"R=0.01 + area x{af:.2f} (calibrated alternative): bypass closed -> +{(q2 / q0 - 1) * 100:.1f} %")

pr("\n=== 10. Resistance shares at 7 / 4.7 m/s, Tg 680, Ts 370 ===")
for U in (7.0, 4.7):
    hc = h_zuk(U, 953.15, 12)[0]
    for R in (0.05, 0.01):
        hs = h_steam(368, 16.0)[0]
        Ts = 600 if R == 0.05 else 450
        hr = h_rad(953.15, Ts + 273.15, "IIIa")
        tot = 1 / (hc + hr) + R + 1 / hs
        pr(f"U={U}: hc={hc:.0f} hr={hr:.0f} R={R}: gas {100 / (hc + hr) / tot:.0f} %, deposit {100 * R / tot:.0f} %, "
           f"steam {100 / hs / tot:.0f} %; U={1 / tot:.1f}")

pr("\n=== 11. Deposit thickness equivalent to R (cylindrical, outer area ref.) ===")
for R in (0.05, 0.02, 0.01):
    for k in (0.1, 0.2, 0.4):
        d = 0.019 * (math.exp(R * k / 0.019) - 1)
        pr(f"R={R}, k={k}: delta = {1000 * d:.1f} mm (gap in 3-tube group 22 mm -> {22 - 2000 * d:.0f} mm)")

pr("\n=== 12. Walls ===")
for R in (0.10, 0.08):
    hw = 1 / (1 / 800 + R)
    pr(f"R={R}: h_w={hw:.2f}; max q (surface = gas 700 C) = {hw * 450 / 1e3:.2f} kW/m2")
e = emiss(700 + 273.15, 3.0)[0]
pr(f"clean membrane, gas 700 C, eps_gas(3 m)={e:.2f}: q_rad ~ {SIG * e * 0.8 * ((973.15) ** 4 - (523.15 + 30) ** 4) / 1e3:.1f} kW/m2 (+conv ~1-2)")
pr("CFD v0 boiler walls (wallQ): 3.30 MW over 868 m2 = 3.81 kW/m2 (min 3.03, max 4.43)")

print("\n".join(out))
open(__file__.replace(".py", "_out.txt"), "w").write("\n".join(out) + "\n")
