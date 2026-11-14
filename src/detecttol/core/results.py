"""Result models returned by :func:`detecttol.core.analyze.analyze`.

All lengths are millimetres. Fractions are in [0, 1]; ``*_ppm`` values are
parts per million (fraction * 1e6); ``*_pct`` values are percent.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

_FROZEN = ConfigDict(extra="forbid", frozen=True)

WarningCode = Literal[
    "WORST_CASE_FAILS_SPEC",
    "RSS_EXCEEDS_WORST_CASE",
    "MODIFIED_RSS_EXCEEDS_WORST_CASE",
    "NON_NORMAL_INPUT",
    "ZERO_VARIATION",
    "MC_NOT_CONVERGED",
    "MC_ZERO_FAILURES",
    "STANDARD_ASSUMED",
    "TOLERANCE_FROM_TABLE",
    "TABLE_NOT_VERIFIED",
    "TOLERANCE_FROM_CAD",
]


class AnalysisWarning(BaseModel):
    """A non-fatal condition the engineer must know about."""

    model_config = _FROZEN

    code: WarningCode
    message: str


class ContributorSummary(BaseModel):
    """Derived per-contributor quantities (spec Section 3.1).

    ``wc_contribution_pct`` / ``rss_contribution_pct`` are ``None`` when the
    stack has no variation at all (every half-range is zero).
    """

    model_config = _FROZEN

    id: str
    nominal: float
    upper_tol: float
    lower_tol: float
    sensitivity: float
    distribution: str
    cp: float
    mean: float
    half_range: float
    sigma: float
    wc_contribution_pct: float | None
    rss_contribution_pct: float | None


class WorstCaseResult(BaseModel):
    """Worst case: Y in [mean - half_range, mean + half_range] [mm]."""

    model_config = _FROZEN

    half_range: float
    lower: float
    upper: float
    meets_spec: bool


class RssResult(BaseModel):
    """Statistical (RSS) result [mm].

    ``p_fail``, ``p_fail_ppm``, ``cpl``, ``cpu`` and ``cpk`` assume a normal Y and
    are ``None`` when ``sigma == 0`` (see ``meets_spec_at_mean`` instead).
    ``cpl``/``cpu`` are ``None`` when the corresponding limit is absent.
    """

    model_config = _FROZEN

    sigma: float
    three_sigma: float
    lower: float
    upper: float
    p_fail: float | None
    p_fail_ppm: float | None
    cpl: float | None
    cpu: float | None
    cpk: float | None
    meets_spec_at_mean: bool


class ModifiedRssResult(BaseModel):
    """Bender modified RSS: half_range = k * sqrt(sum (a_i t_i)^2) [mm]."""

    model_config = _FROZEN

    k: float
    half_range: float
    lower: float
    upper: float


class Percentiles(BaseModel):
    """Monte Carlo percentiles of Y [mm] (numpy linear interpolation)."""

    model_config = _FROZEN

    p0_135: float
    p2_5: float
    p50: float
    p97_5: float
    p99_865: float


class Histogram(BaseModel):
    """Equal-width histogram of the Monte Carlo sample of Y.

    ``edges`` has ``len(counts) + 1`` entries [mm].
    """

    model_config = _FROZEN

    edges: list[float]
    counts: list[int]


class MonteCarloResult(BaseModel):
    """Monte Carlo result.

    Attributes:
        n, seed: sample size and RNG seed used.
        mean, std, min, max: sample statistics of Y [mm]; ``std`` uses ddof=1.
        n_fail: number of samples outside the spec (Y < LSL or Y > USL).
        fraction_fail / fraction_fail_ppm: n_fail / n.
        wilson_lower / wilson_upper: Wilson two-sided 95 % interval on the fraction.
        zero_failure_upper_bound: exact one-sided 95 % upper bound
            ``1 - 0.05**(1/n)`` (about 3/n); only set when ``n_fail == 0``.
        std_half: std of the first n//2 samples [mm].
        convergence_rel_diff: ``|std_half - std| / std`` (``None`` if std == 0).
        converged: ``convergence_rel_diff <= 0.01`` (True if std == 0).
    """

    model_config = _FROZEN

    n: int
    seed: int
    mean: float
    std: float
    min: float
    max: float
    percentiles: Percentiles
    n_fail: int
    fraction_fail: float
    fraction_fail_ppm: float
    wilson_lower: float
    wilson_upper: float
    zero_failure_upper_bound: float | None
    std_half: float
    convergence_rel_diff: float | None
    converged: bool
    histogram: Histogram


class StackResult(BaseModel):
    """Full analysis result for one stack.

    ``standard`` is the drawing standard named by the input (``asme``, ``iso``,
    ``is``) or ``None`` if it named none.
    """

    model_config = _FROZEN

    name: str
    units: str
    standard: Literal["asme", "iso", "is"] | None = None
    description: str
    lsl: float | None
    usl: float | None
    constant: float
    mean: float
    contributors: list[ContributorSummary]
    worst_case: WorstCaseResult | None
    rss: RssResult | None
    modified_rss: ModifiedRssResult | None
    monte_carlo: MonteCarloResult | None
    warnings: list[AnalysisWarning]
