"""Bundle pressure drop check: Gaddis-Gnielinski (VDI Heat Atlas L1.4, in-line banks) for the WHB
superheaters (vertical tubes d 38, pitch across 100, along 60 in a 3-tube group / 100 between groups,
12 rows) and the evaporator (4 rows, pitch 88), clean and with a uniform deposit layer delta.

The model (make_case_of14.py) uses Eu per row 0.159 (SH) / 0.18 (EVAP), referred to u_max = u0/sigma,
sigma = 1 - d/s1, and multiplies by --bundle_dp_fac. Here: what Eu and dp the correlation gives for the
grouped geometry, and how much a deposit layer raises dp (factor to put into --bundle_dp_fac).

    python3 docs/audit/bundle_dp.py
"""
import math

S1 = 0.100            # pitch across the gas flow (46 columns)
P_ABS, M_GAS, MU = 111800.0, 28.0, 3.89e-5


def rho(T_c):
    return P_ABS * M_GAS / (8314.0 * (T_c + 273.15))


def xi_inline(a, b, Re, n_rows):
    """Pressure drop coefficient per row, in-line bank (Gaddis), Re on u_max and d."""
    f_lam = 280 * math.pi * ((b ** 0.5 - 0.6) ** 2 + 0.75) / ((4 * a * b - math.pi) * a ** 1.6)
    xi_lam = f_lam / Re
    f_turb = ((0.22 + 1.2 * (1 - 0.94 / b) ** 0.6 / (a - 0.85) ** 1.3) * 10 ** (0.47 * (b / a - 1.5))
              + 0.03 * (a - 1) * (b - 1))
    xi_turb = f_turb / Re ** (0.1 * b / a)
    f_n = (1 / a ** 2) * (1 / n_rows - 0.1) if n_rows < 10 else 0.0   # inlet/outlet rows
    return xi_lam + (xi_turb + f_n) * (1 - math.exp(-(Re + 1000) / 2000))


def bundle(d, pitches, u0, T_c):
    """dp of a bundle (pitches along flow between consecutive tubes, the first row gets the mean pitch),
    Eu per row on u_max = u0 / sigma. Returns dp, mean Eu, Re."""
    a = S1 / d
    sig = 1 - d / S1
    r = rho(T_c)
    umax = u0 / sig
    Re = umax * d * r / MU
    n = len(pitches) + 1
    bs = [sum(pitches) / len(pitches)] + list(pitches)
    xis = [xi_inline(a, max(bb, 1.05 * d) / d, Re, n) for bb in bs]
    eu = sum(xis) / n
    return n * eu * r * umax ** 2 / 2, eu, Re


SH = [0.060, 0.060, 0.100] * 3 + [0.060, 0.060]     # 12 tubes: 4 groups of 3
EV = [0.088] * 3
D0 = 0.038


def model_dp(n, eu, d, u0, T_c):
    return n * eu * rho(T_c) * (u0 / (1 - d / S1)) ** 2 / 2


if __name__ == "__main__":
    print("Clean bundles, Gaddis vs model (Eu per row on u_max)")
    print(f"{'bundle':6s} {'u0':>4s} {'T':>4s} {'Re':>6s} {'Eu_corr':>8s} {'Eu_model':>8s} {'dp_corr':>8s} {'dp_model':>8s}")
    for name, p, eum, T in (("EVAP", EV, 0.18, 740), ("SH", SH, 0.159, 670)):
        for u0 in (3, 5, 7):
            dp, eu, Re = bundle(D0, p, u0, T)
            print(f"{name:6s} {u0:4.0f} {T:4.0f} {Re:6.0f} {eu:8.3f} {eum:8.3f} {dp:8.1f} {model_dp(len(p) + 1, eum, D0, u0, T):8.1f}")

    # uniform b for comparison (what a uniform 60 or 100 mm bank would give)
    for b in (0.060, 0.0709, 0.100):
        dp, eu, Re = bundle(D0, [b] * 11, 5, 670)
        print(f"  SH uniform pitch {b * 1000:.0f} mm, u0 5: Eu {eu:.3f}")

    print("\nDeposit layer delta (uniform around the tube); deposit lambda -> delta for R = 0.051 m2K/W:")
    for lam in (0.1, 0.15, 0.2, 0.3):
        d = D0 * math.exp(2 * lam * 0.051 / D0)
        print(f"  lambda {lam:.2f} W/mK: delta {(d - D0) / 2 * 1000:4.1f} mm")
    print(f"\n{'delta,mm':>8s} {'d_eff':>6s} {'sigma':>6s} {'gap_in_group':>12s} {'Eu':>6s} {'dp SH,Pa':>9s} {'x clean':>8s}  (u0 5 m/s, 670 C)")
    dp0 = bundle(D0, SH, 5, 670)[0]
    for dl in (0, 2, 4, 6, 8, 10, 12, 15):
        d = D0 + 2 * dl / 1000
        gap = 0.060 - d
        if gap > 0.002:
            dp, eu, _ = bundle(d, SH, 5, 670)
            note = f"{gap * 1000:10.0f}mm"
        else:
            # group bridged: 3 tubes = one elongated body d x (0.12 + d); 4 bodies, gaps 100 - d... as 4 rows
            # with pitch 0.18 between body centres: approximate by an in-line bank of 4 rows of d at pitch 0.18
            # plus friction along the flat sides (small) -> lower bound
            dp, eu, _ = bundle(d, [0.18] * 3, 5, 670)
            note = "  bridged"
        print(f"{dl:8.0f} {d * 1000:6.0f} {1 - d / S1:6.2f} {note:>12s} {eu:6.3f} {dp:9.1f} {dp / dp0:8.2f}")
