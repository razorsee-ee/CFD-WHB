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

pr = None  # placeholder
# from the audit's output section: effective cp of gas + 40 % dust, 618-750 C
cpg = mean_cp(618 + 273.15, 750 + 273.15)
cpeff = cpg + DUST / MDOT * CP_DUST
