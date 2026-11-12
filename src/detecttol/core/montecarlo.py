"""Seeded, vectorised Monte Carlo for linear stacks (spec Section 3.3)."""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np
import numpy.typing as npt
from scipy.special import ndtr, ndtri

from detecttol.core.models import Contributor
from detecttol.core.results import Histogram, MonteCarloResult, Percentiles

FloatArray = npt.NDArray[np.float64]

#: z for a two-sided 95 % interval (Phi^-1(0.975)).
Z_95_TWO_SIDED = 1.959964
#: Relative std difference (N/2 vs N) above which a convergence warning is raised.
CONVERGENCE_REL_TOL = 0.01
#: Number of equal-width histogram bins stored in the result.
HISTOGRAM_BINS = 60


def sample_contributor(c: Contributor, n: int, rng: np.random.Generator) -> FloatArray:
    """Draw ``n`` samples [mm] of one contributor from its distribution.

    - normal:           N(mean, sigma0), sigma0 = t/(3 cp); unbounded.
    - uniform:          U[mean - t, mean + t].
    - truncated_normal: N(mean, sigma0) restricted to mean +/- t, sampled by
      inverse CDF so that exactly one uniform draw is used per sample.
    - zero half-range:  the constant ``mean`` (no random draw is consumed).
    """
    mu, t = c.mean, c.half_range
    if t == 0.0:
        return np.full(n, mu, dtype=np.float64)
    if c.distribution == "uniform":
        return rng.uniform(mu - t, mu + t, n)
    sigma0 = t / (3.0 * c.cp)
    if c.distribution == "normal":
        return rng.normal(mu, sigma0, n)
    k = 3.0 * c.cp
    p_lo = float(ndtr(-k))
    u = rng.uniform(0.0, 1.0, n)
    z = np.asarray(ndtri(p_lo + u * (1.0 - 2.0 * p_lo)), dtype=np.float64)
    # Guard the open-interval edge cases of the inverse CDF.
    return np.clip(mu + sigma0 * z, mu - t, mu + t)


def sample_stack(
    contributors: Sequence[Contributor], constant: float, n: int, seed: int
) -> FloatArray:
    """Sample Y = constant + sum(a_i x_i) [mm]; shape ``(n,)``.

    Contributors are sampled in list order from one ``default_rng(seed)``, so the
    same seed and the same input give bit-identical output.
    """
    rng = np.random.default_rng(seed)
    y = np.full(n, constant, dtype=np.float64)
    for c in contributors:
        y += c.sensitivity * sample_contributor(c, n, rng)
    return y


def wilson_interval(x: int, n: int, z: float = Z_95_TWO_SIDED) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion ``x/n`` (fractions).

    ``centre = (p + z^2/2n)/(1 + z^2/n)``,
    ``half = z*sqrt(p(1-p)/n + z^2/4n^2)/(1 + z^2/n)``. Source: NIST e-Handbook 7.2.4.1.
    """
    if n <= 0 or not 0 <= x <= n:
        raise ValueError("need n > 0 and 0 <= x <= n")
    p = x / n
    denom = 1.0 + z * z / n
    centre = (p + z * z / (2.0 * n)) / denom
    half = z * math.sqrt(p * (1.0 - p) / n + z * z / (4.0 * n * n)) / denom
    # At x = 0 the centre equals the half-width, so the lower limit is exactly 0;
    # by symmetry the upper limit is exactly 1 at x = n. Floating-point evaluation
    # leaves ~1e-19 residue there, so set those two limits analytically.
    lower = 0.0 if x == 0 else max(0.0, centre - half)
    upper = 1.0 if x == n else min(1.0, centre + half)
    return lower, upper


def zero_failure_upper_bound(n: int, confidence: float = 0.95) -> float:
    """Exact one-sided upper bound on p when 0 failures are seen in ``n`` trials.

    Solves ``(1 - p)^n = 1 - confidence`` -> ``p = 1 - (1 - confidence)^(1/n)``;
    about ``3/n`` at 95 % (rule of three).
    """
    if n <= 0:
        raise ValueError("need n > 0")
    return -math.expm1(math.log(1.0 - confidence) / n)


def summarise(y: FloatArray, lsl: float | None, usl: float | None, seed: int) -> MonteCarloResult:
    """Reduce a sample of Y [mm] to the reported Monte Carlo statistics."""
    n = int(y.size)
    std = float(np.std(y, ddof=1))
    std_half = float(np.std(y[: n // 2], ddof=1)) if n // 2 >= 2 else std
    rel = None if std == 0.0 else abs(std_half - std) / std

    fail = np.zeros(n, dtype=np.bool_)
    if lsl is not None:
        fail |= y < lsl
    if usl is not None:
        fail |= y > usl
    n_fail = int(np.count_nonzero(fail))
    lo, hi = wilson_interval(n_fail, n)

    q = np.percentile(y, [0.135, 2.5, 50.0, 97.5, 99.865])
    y_min, y_max = float(np.min(y)), float(np.max(y))
    if y_min == y_max:
        counts = np.array([n], dtype=np.int64)
        edges = np.array([y_min, y_max], dtype=np.float64)
    else:
        counts, edges = np.histogram(y, bins=HISTOGRAM_BINS, range=(y_min, y_max))

    return MonteCarloResult(
        n=n,
        seed=seed,
        mean=float(np.mean(y)),
        std=std,
        min=y_min,
        max=y_max,
        percentiles=Percentiles(
            p0_135=float(q[0]),
            p2_5=float(q[1]),
            p50=float(q[2]),
            p97_5=float(q[3]),
            p99_865=float(q[4]),
        ),
        n_fail=n_fail,
        fraction_fail=n_fail / n,
        fraction_fail_ppm=1e6 * n_fail / n,
        wilson_lower=lo,
        wilson_upper=hi,
        zero_failure_upper_bound=zero_failure_upper_bound(n) if n_fail == 0 else None,
        std_half=std_half,
        convergence_rel_diff=rel,
        converged=rel is None or rel <= CONVERGENCE_REL_TOL,
        histogram=Histogram(edges=[float(e) for e in edges], counts=[int(v) for v in counts]),
    )
