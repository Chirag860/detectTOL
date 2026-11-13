"""Independent re-computation of every hand-derived golden value.

Purpose: root.md asks for a human check of the golden values. The maintainer
delegated that check (2026-11-13: "verify it on your own, just don't falsely
verify it"). This script is that check. It is deliberately independent of the
library:

- it imports nothing from ``detecttol`` and nothing outside the standard library;
- it does not reuse the closed-form formulas the library uses where a more
  primitive route exists: probabilities and moments are obtained by numerical
  integration (composite Simpson) of the defining integrals, geometry by
  explicit rotation matrices, sensitivities by finite differences;
- every result is compared with the constant written in the test suite.

Run:  python validation/verify_golden.py
Exit code 0 means every value agreed within the stated tolerance.
"""

from __future__ import annotations

import math
import sys

CHECKS: list[tuple[str, float, float, float]] = []


def check(
    label: str, computed: float, expected: float, rel: float = 6e-7, abs_tol: float = 0.0
) -> None:
    """Record a comparison.

    Default rel = 6e-7: the test constants are written to 7 significant figures,
    so rounding alone can differ by up to 5e-7 relative (half a unit in the 7th
    figure when the leading digit is 1).
    """
    CHECKS.append((label, computed, expected, max(rel * abs(expected), abs_tol)))


def pdf(z: float) -> float:
    return math.exp(-0.5 * z * z) / math.sqrt(2.0 * math.pi)


def simpson(f, a: float, b: float, n: int = 20000) -> float:  # type: ignore[no-untyped-def]
    if n % 2:
        n += 1
    h = (b - a) / n
    total = f(a) + f(b)
    for i in range(1, n):
        total += f(a + i * h) * (4 if i % 2 else 2)
    return total * h / 3.0


def cdf(z: float) -> float:
    """Phi(z) by integrating the density (not erf), so it is independent of the library."""
    if z <= -12.0:
        return 0.0
    if z <= 0.0:
        return simpson(pdf, -12.0, z, 40000)
    return 1.0 - cdf(-z)


def tail(z: float) -> float:
    """1 - Phi(z) for z >= 0, integrated directly so small values keep precision."""
    return simpson(pdf, z, z + 12.0, 40000)


# --------------------------------------------------------------------------- #
# Phase 1: linear stacks
# --------------------------------------------------------------------------- #


def linear(contribs, lsl=None, usl=None, constant=0.0):  # type: ignore[no-untyped-def]
    """contribs: (nominal, upper, lower, a, kind, cp). Returns mean, W, sigma, p_fail."""
    mean = constant
    worst = 0.0
    var = 0.0
    for nominal, upper, lower, a, kind, cp in contribs:
        mu = nominal + (upper + lower) / 2.0
        t = (upper - lower) / 2.0
        if kind == "uniform":
            # variance of U[mu-t, mu+t] by integration of (x-mu)^2 / (2t)
            v = simpson(lambda x, mu=mu, t=t: (x - mu) ** 2 / (2 * t), mu - t, mu + t, 2000)
        else:
            s = t / (3.0 * cp)
            v = s * s
        mean += a * mu
        worst += abs(a) * t
        var += a * a * v
    sigma = math.sqrt(var)
    p = 0.0
    if lsl is not None:
        p += tail((mean - lsl) / sigma) if mean >= lsl else 1 - tail((lsl - mean) / sigma)
    if usl is not None:
        p += tail((usl - mean) / sigma) if usl >= mean else 1 - tail((mean - usl) / sigma)
    return mean, worst, sigma, p


A = [(50.0, 0.1, -0.1, 1, "n", 1.0)] + [(16.6, 0.05, -0.05, -1, "n", 1.0)] * 3
m, w, s, p = linear(A, lsl=0.0)
check("A mean", m, 0.20, abs_tol=1e-12)
check("A worst-case half-range", w, 0.25)
check("A sigma", s, 0.04409586)
check("A 3 sigma", 3 * s, 0.1322876)
check("A P_fail", p, 2.872356e-6)
check("A Cpl", (m - 0.0) / (3 * s), 1.511858)
check("A RSS % slot", 100 * (0.1 / 3) ** 2 / s**2, 57.142857)
check("A Bender 1.5", 1.5 * math.sqrt(0.1**2 + 3 * 0.05**2), 0.1984313)
m, w, s, p = linear(A, lsl=0.0, constant=0.05)
check("H P_fail (constant 0.05)", p, 7.162118e-9)

B = [(30.0, 0.2, 0.0, 1, "n", 1.0), (29.8, 0.0, -0.1, -1, "n", 1.0)]
m, w, s, p = linear(B, lsl=0.10, usl=0.50)
check("B mean", m, 0.35, abs_tol=1e-12)
check("B W", w, 0.15)
check("B sigma", s, 0.03726780)
check("B P_fail", p, 2.849707e-5)
check("B Cpu", (0.5 - m) / (3 * s), 1.341641)
check("B Cpl", (m - 0.1) / (3 * s), 2.236068)

C = [(20.0, 0.3, -0.3, 1, "uniform", 1.0), (19.0, 0.1, -0.1, -1, "n", 1.0)]
m, w, s, p = linear(C, lsl=0.5, usl=1.6)
check("C sigma", s, 0.1763834)
check("C P_fail (normal approx.)", p, 2.628061e-3)
check("C Cpl", (m - 0.5) / (3 * s), 0.9449112)

D = [(25.0, 0.12, -0.12, 1, "n", 2.0), (10.0, 0.06, -0.06, 1, "n", 1.0)]
m, w, s, p = linear(D, usl=35.10)
check("D sigma", s, 0.02828427)
check("D P_fail", p, 2.034760e-4)
check("D Cpu", (35.1 - m) / (3 * s), 1.178511)


def truncated_sd_factor(k: float) -> float:
    mass = simpson(pdf, -k, k)
    second = simpson(lambda z: z * z * pdf(z), -k, k)
    return math.sqrt(second / mass)


check("E truncated factor k=3", truncated_sd_factor(3.0), 0.9865784)
check("E truncated factor k=2", truncated_sd_factor(2.0), 0.8796257)


def wilson(x: int, n: int) -> tuple[float, float]:
    """Solve the score equation |p_hat - p| = z sqrt(p(1-p)/n) by bisection."""
    z = 1.959964
    ph = x / n

    def g(pp: float) -> float:
        return (ph - pp) ** 2 - z * z * pp * (1 - pp) / n

    def root(lo: float, hi: float) -> float:
        for _ in range(200):
            mid = (lo + hi) / 2
            if (g(lo) > 0) == (g(mid) > 0):
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2

    lower = 0.0 if x == 0 else root(0.0, ph)
    upper = 1.0 if x == n else root(ph, 1.0)
    return lower, upper


check("Wilson upper x=0 N=1000", wilson(0, 1000)[1], 3.826759e-3)
check("Wilson lower x=5 N=1000", wilson(5, 1000)[0], 2.137536e-3)
check("Wilson upper x=5 N=1000", wilson(5, 1000)[1], 1.165096e-2)
check("Wilson lower x=3 N=1e5", wilson(3, 100000)[0], 1.020276e-5)
check("Wilson upper x=3 N=1e5", wilson(3, 100000)[1], 8.820805e-5)


def zero_failure_bound(n: int) -> float:
    lo, hi = 0.0, 1.0
    for _ in range(200):  # solve (1-p)^n = 0.05 by bisection
        mid = (lo + hi) / 2
        if (1 - mid) ** n > 0.05:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


check("zero-failure bound N=1000", zero_failure_bound(1000), 2.991250e-3)
check("zero-failure bound N=1e5", zero_failure_bound(100000), 2.995687e-5)

# --------------------------------------------------------------------------- #
# Phase 3: vector loops (explicit rotation matrices, finite-difference sensitivities)
# --------------------------------------------------------------------------- #


def matmul(a, b):  # type: ignore[no-untyped-def]
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def rz(t: float):  # type: ignore[no-untyped-def]
    c, s_ = math.cos(t), math.sin(t)
    return [[c, -s_, 0], [s_, c, 0], [0, 0, 1]]


def ry(t: float):  # type: ignore[no-untyped-def]
    c, s_ = math.cos(t), math.sin(t)
    return [[c, 0, s_], [0, 1, 0], [-s_, 0, c]]


def rx(t: float):  # type: ignore[no-untyped-def]
    c, s_ = math.cos(t), math.sin(t)
    return [[1, 0, 0], [0, c, -s_], [0, s_, c]]


def chain(x: list[float], n: tuple[float, float, float]) -> float:
    """x = [L, yaw, pitch, roll] per vector, flattened. Returns n . sum L R e_x."""
    r = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
    total = [0.0, 0.0, 0.0]
    for i in range(0, len(x), 4):
        length, yaw, pitch, roll = x[i : i + 4]
        r = matmul(matmul(matmul(r, rz(yaw)), ry(pitch)), rx(roll))
        for k in range(3):
            total[k] += length * r[k][0]
    return sum(total[k] * n[k] for k in range(3))


def loop_stats(x, tol, n):  # type: ignore[no-untyped-def]
    """Mean, sensitivities (central differences, h = 1e-6), W and sigma (cp = 1)."""
    mean = chain(x, n)
    sens = []
    for i in range(len(x)):
        hi, lo = list(x), list(x)
        hi[i] += 1e-6
        lo[i] -= 1e-6
        sens.append((chain(hi, n) - chain(lo, n)) / 2e-6)
    worst = sum(abs(a) * t for a, t in zip(sens, tol, strict=True))
    sigma = math.sqrt(sum((a * t / 3.0) ** 2 for a, t in zip(sens, tol, strict=True)))
    return mean, sens, worst, sigma


DEG = math.pi / 180.0
X, Y, Z = (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)
FD = {"rel": 2e-6}  # finite-difference sensitivities: looser than the 7-figure constants

mean, sens, worst, sigma = loop_stats([100.0, 0.3, 0, 0], [0.2, 0.006, 0, 0], Y)
check("pin mean 100 sin 0.3", mean, 29.55202)
check("pin dY/dL", sens[0], 0.2955202, **FD)
check("pin dY/dtheta", sens[1], 95.53365, **FD)
check("pin W", worst, 0.6323059, **FD)
check("pin sigma", sigma, 0.1920803, **FD)

mean, sens, worst, sigma = loop_stats([80.0, 15 * DEG, 0, 0], [0.1, 0.5 * DEG, 0, 0], Y)
check("wedge mean", mean, 20.70552)
check("wedge dY/dtheta", sens[1], 77.27407, **FD)
check("wedge W", worst, 0.7002253, **FD)
check("wedge sigma", sigma, 0.2249466, **FD)
check(
    "wedge P_fail", tail((mean - 20.0) / sigma) + tail((21.4 - mean) / sigma), 1.865106e-3, rel=2e-5
)
check("wedge Cpu", (21.4 - mean) / (3 * sigma), 1.029098, rel=2e-6)

bracket = [60.0, math.pi / 6, 0, 0, 40.0, -math.pi / 2, 0, 0]
btol = [0.1, 0.004, 0, 0, 0.1, 0.004, 0, 0]
mean, sens, worst, sigma = loop_stats(bracket, btol, X)
check("bracket x mean", mean, 71.96152)
check("bracket x dY/dphi1", sens[1], 4.641016, **FD)
check("bracket x dY/dphi2", sens[5], 34.64102, **FD)
check("bracket x W", worst, 0.2937307, **FD)
check("bracket x sigma", sigma, 0.05729517, **FD)
mean, sens, worst, sigma = loop_stats(bracket, btol, Y)
check("bracket y mean", mean, -4.641016)
check("bracket y dY/dphi1", sens[1], 71.96152, **FD)
check("bracket y W", worst, 0.5044486, **FD)
check("bracket y sigma", sigma, 0.1050161, **FD)

single = [50.0, 30 * DEG, 20 * DEG, 0]
stol = [0.1, 0.2 * DEG, 0.2 * DEG, 0]
for label, n, e_mean, e_w, e_s in (
    ("x", X, 40.68988, 0.2150797, 0.04218975),
    ("y", Y, 23.49232, 0.2188660, 0.05085075),
    ("z", Z, -17.10101, 0.1982093, 0.05584520),
):
    mean, sens, worst, sigma = loop_stats(single, stol, n)
    check(f"3D single {label} mean", mean, e_mean)
    check(f"3D single {label} W", worst, e_w, **FD)
    check(f"3D single {label} sigma", sigma, e_s, **FD)

roll = [30.0, 0, 0, 10 * DEG, 40.0, 90 * DEG, 0, 0]
rtol = [0, 0, 0, 0.5 * DEG, 0.05, 0, 0, 0]
mean, sens, worst, sigma = loop_stats(roll, rtol, Z)
check("3D roll z mean", mean, 6.945927)
check("3D roll z dY/droll", sens[3], 39.39231, **FD)
check("3D roll z W", worst, 0.3524452, **FD)
check("3D roll z sigma", sigma, 0.1146241, **FD)
check(
    "3D box diagonal",
    chain([3, 0, 0, 0, 4, 90 * DEG, 0, 0, 12, 0, -90 * DEG, 0], (3 / 13, 4 / 13, 12 / 13)),
    13.0,
    abs_tol=1e-9,
)

# exact moments of trigonometric functions of a normal angle, by integration
sd = math.sqrt(simpson(lambda z: (100 * math.sin(0.01 * z)) ** 2 * pdf(z), -12, 12))
check("pin exact std, theta sigma 0.01", sd, 0.9999500)
sd = math.sqrt(simpson(lambda z: (100 * math.sin(0.3 * z)) ** 2 * pdf(z), -12, 12))
check("pin exact std, theta sigma 0.3", sd, 28.69928)
mu = simpson(lambda z: 100 * math.cos(0.01 * z) * pdf(z), -12, 12)
sd = math.sqrt(simpson(lambda z: (100 * math.cos(0.01 * z) - mu) ** 2 * pdf(z), -12, 12))
check("cos case exact mean", mu, 99.99500)
check("cos case exact std", sd, 0.007070714)

# --------------------------------------------------------------------------- #
# Phase 4: GD&T
# --------------------------------------------------------------------------- #

check("flatness stack sigma", math.sqrt(0.1**2 + 0.05**2 + 0.02**2) / 3, 0.03785939)
check("flatness stack P_fail", tail(0.2 / (math.sqrt(0.0129) / 3)), 6.364498e-8)
check("parallelism stack sigma", math.sqrt(0.1**2 + 0.05**2 + 0.03**2) / 3, 0.03858612)
s = math.sqrt(0.1**2 + 0.15**2) / 3
check("position RFS sigma", s, 0.06009252)
check("position RFS P_fail", 2 * tail(0.2 / s), 8.740872e-4)


def bonus(z: float, t: float = 0.1, sigma: float = 0.1 / 3) -> float:
    """Clamped bonus of a size t + sigma z above its MMC size (size range 2t)."""
    return min(max(t + sigma * z, 0.0), 2 * t)


T = 0.2
second = simpson(lambda z: (T + bonus(z)) ** 2 * pdf(z), -12, 12, 40000)
check("MMC hole sigma_delta", math.sqrt(second) / 6, 0.05030616)
second = simpson(lambda z: (0.1 + bonus(z, 0.05, 0.05 / 3)) ** 2 * pdf(z), -12, 12, 40000)
check("MMC pin sigma_delta", math.sqrt(second) / 6, 0.02515308)
second = simpson(lambda b: (T + b) ** 2 / 0.2, 0.0, 0.2, 2000)
check("MMC uniform-size sigma_delta", math.sqrt(second) / 6, 0.05091751)
exact = simpson(
    lambda z: 2 * 0.5 * math.erfc(0.9 / (T + bonus(z)) / math.sqrt(2)) * pdf(z), -12, 12, 40000
)
check("MMC exact P_fail of |delta| > 0.15", exact, 3.809975e-3)
check("MMC normal-approx P_fail", 2 * tail(0.15 / 0.05030616), 2.866134e-3, rel=2e-6)
check("RFS P_fail of |delta| > 0.15", 2 * tail(4.5), 6.795346e-6)

sp = T / 6
# Rayleigh survival by integrating the bivariate normal density over r > R (polar form)
check(
    "RFS reject",
    simpson(lambda r: r / sp**2 * math.exp(-r * r / (2 * sp * sp)), T / 2, T / 2 + 12 * sp),
    0.01110900,
)
rej = simpson(
    lambda z: math.exp(-(((T + bonus(z)) / 2) ** 2) / (2 * sp * sp)) * pdf(z), -12, 12, 40000
)
check("MMC reject, normal size", rej, 2.620943e-4)
rej = simpson(lambda b: math.exp(-(((T + b) / 2) ** 2) / (2 * sp * sp)) / 0.2, 0.0, 0.2, 4000)
check("MMC reject, uniform size", rej, 1.127897e-3)
sp2 = T / 3
rej = simpson(
    lambda z: math.exp(-(((T + bonus(z)) / 2) ** 2) / (2 * sp2 * sp2)) * pdf(z), -12, 12, 40000
)
check("MMC reject, cp 0.5", rej, 0.08953001)
check("RFS reject, cp 0.5", math.exp(-1.125), 0.3246525)
check("perpendicularity angle", math.atan(0.1 / 40), 0.002499995)
check("perpendicularity exact extreme", 100 * math.sin(math.atan(0.0025)), 0.2499992)


def main() -> int:
    bad = 0
    for label, computed, expected, tolerance in CHECKS:
        ok = abs(computed - expected) <= tolerance
        bad += 0 if ok else 1
        if not ok:
            print(f"MISMATCH {label}: computed {computed!r}, test constant {expected!r}")
    print(f"{len(CHECKS) - bad} of {len(CHECKS)} golden values confirmed independently")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
