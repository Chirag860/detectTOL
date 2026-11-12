"""Closed-form linear stack math (spec Section 3.2). Pure functions, mm in / mm out."""

from __future__ import annotations

import math
from collections.abc import Sequence

from scipy.stats import norm

from detecttol.core.models import Contributor

#: Contribution sets must sum to 100 % within this absolute tolerance [percent].
CONTRIBUTION_SUM_TOL_PCT = 1e-9


def stack_mean(contributors: Sequence[Contributor], constant: float = 0.0) -> float:
    """Mean of the requirement [mm]: ``mu_Y = constant + sum(a_i * mu_i)``."""
    return constant + math.fsum(c.sensitivity * c.mean for c in contributors)


def worst_case_half_range(contributors: Sequence[Contributor]) -> float:
    """Worst-case half-range [mm]: ``W = sum(|a_i| * t_i)``."""
    return math.fsum(abs(c.sensitivity) * c.half_range for c in contributors)


def rss_sigma(contributors: Sequence[Contributor]) -> float:
    """Standard deviation of Y [mm]: ``sigma_Y = sqrt(sum(a_i^2 * sigma_i^2))``.

    Assumes statistically independent contributors.
    """
    return math.sqrt(math.fsum((c.sensitivity * c.sigma) ** 2 for c in contributors))


def modified_rss_half_range(contributors: Sequence[Contributor], k: float) -> float:
    """Bender modified-RSS half-range [mm]: ``k * sqrt(sum((a_i * t_i)^2))``.

    Uses the tolerance half-ranges directly; ``cp`` and ``distribution`` are ignored.
    Source: Bender (1962), k = 1.5.
    """
    return k * math.sqrt(math.fsum((c.sensitivity * c.half_range) ** 2 for c in contributors))


def _percentages(weights: Sequence[float]) -> list[float] | None:
    """Normalise non-negative weights to percentages; ``None`` if they sum to 0."""
    total = math.fsum(weights)
    if total == 0.0:
        return None
    pct = [100.0 * w / total for w in weights]
    if abs(math.fsum(pct) - 100.0) > CONTRIBUTION_SUM_TOL_PCT:  # pragma: no cover
        raise AssertionError("contribution percentages do not sum to 100 %")
    return pct


def worst_case_contributions(contributors: Sequence[Contributor]) -> list[float] | None:
    """Worst-case contribution of each contributor [%]: ``|a_i| t_i / sum(|a_j| t_j)``.

    Returns ``None`` when every half-range is zero (no variation to apportion).
    """
    return _percentages([abs(c.sensitivity) * c.half_range for c in contributors])


def rss_contributions(contributors: Sequence[Contributor]) -> list[float] | None:
    """RSS contribution of each contributor [%]: ``a_i^2 sigma_i^2 / sum(a_j^2 sigma_j^2)``.

    Returns ``None`` when the total variance is zero.
    """
    return _percentages([(c.sensitivity * c.sigma) ** 2 for c in contributors])


def normal_p_fail(mean: float, sigma: float, lsl: float | None, usl: float | None) -> float:
    """Probability that a normal Y falls outside the spec (fraction in [0, 1]).

    ``P_fail = Phi((LSL - mu)/sigma) + (1 - Phi((USL - mu)/sigma))``; a missing
    limit contributes 0. The upper tail uses the survival function so that
    ppb-level values keep their precision. Requires ``sigma > 0``.
    """
    if sigma <= 0.0:
        raise ValueError("sigma must be > 0")
    p = 0.0
    if lsl is not None:
        p += float(norm.cdf((lsl - mean) / sigma))
    if usl is not None:
        p += float(norm.sf((usl - mean) / sigma))
    return p


def capability(
    mean: float, sigma: float, lsl: float | None, usl: float | None
) -> tuple[float | None, float | None, float]:
    """Capability indices ``(Cpl, Cpu, Cpk)`` (dimensionless).

    ``Cpl = (mu - LSL)/(3 sigma)``, ``Cpu = (USL - mu)/(3 sigma)``,
    ``Cpk = min`` of the ones that exist. Requires ``sigma > 0`` and at least
    one limit.
    """
    if sigma <= 0.0:
        raise ValueError("sigma must be > 0")
    cpl = None if lsl is None else (mean - lsl) / (3.0 * sigma)
    cpu = None if usl is None else (usl - mean) / (3.0 * sigma)
    existing = [v for v in (cpl, cpu) if v is not None]
    if not existing:
        raise ValueError("at least one of lsl / usl is required")
    return cpl, cpu, min(existing)


def within_spec(value: float, lsl: float | None, usl: float | None, abs_tol: float = 0.0) -> bool:
    """True if ``LSL - abs_tol <= value <= USL + abs_tol`` (missing limits are not checked).

    ``abs_tol`` [mm] absorbs floating-point rounding when a computed limit lands
    exactly on a spec limit.
    """
    return (lsl is None or value >= lsl - abs_tol) and (usl is None or value <= usl + abs_tol)
