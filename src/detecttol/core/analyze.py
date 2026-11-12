"""Top-level analysis entry point: ``analyze(stack) -> StackResult``."""

from __future__ import annotations

import logging

from detecttol.core import linear, montecarlo
from detecttol.core.models import Stack
from detecttol.core.results import (
    AnalysisWarning,
    ContributorSummary,
    ModifiedRssResult,
    MonteCarloResult,
    RssResult,
    StackResult,
    WorstCaseResult,
)

logger = logging.getLogger(__name__)

#: Absolute slack [mm] when comparing a statistical half-range with worst case,
#: so that exact ties (e.g. a single normal contributor, cp = 1) do not warn.
_EXCEEDS_ABS_TOL_MM = 1e-12
#: Absolute slack [mm] for "worst-case limit lands exactly on a spec limit".
#: Float rounding in the sums is ~1e-14 mm; 1e-9 mm (one picometre) is far below
#: any physical resolution and far above that rounding.
_SPEC_ABS_TOL_MM = 1e-9


def analyze(stack: Stack) -> StackResult:
    """Analyse a linear tolerance stack ``Y = constant + sum(a_i x_i)``.

    Runs the methods listed in ``stack.analysis.methods``:

    - ``worst_case``: ``mu_Y +/- sum(|a_i| t_i)``
    - ``rss``: ``sigma_Y = sqrt(sum(a_i^2 sigma_i^2))``, ``mu_Y +/- 3 sigma_Y``,
      normal-theory P_fail and Cpk
    - ``monte_carlo``: seeded sampling with a Wilson 95 % interval

    All lengths in the result are millimetres. Non-fatal conditions are returned
    in ``StackResult.warnings`` (and logged), never printed.
    """
    req = stack.requirement
    contributors = stack.contributors
    methods = stack.analysis.methods
    warnings: list[AnalysisWarning] = []

    def warn(code: str, message: str) -> None:
        warnings.append(AnalysisWarning.model_validate({"code": code, "message": message}))
        logger.warning("%s: %s", code, message)

    mean = linear.stack_mean(contributors, req.constant)
    wc_half = linear.worst_case_half_range(contributors)
    sigma = linear.rss_sigma(contributors)
    wc_pct = linear.worst_case_contributions(contributors)
    rss_pct = linear.rss_contributions(contributors)

    summaries = [
        ContributorSummary(
            id=c.id,
            nominal=c.nominal,
            upper_tol=c.upper_tol,
            lower_tol=c.lower_tol,
            sensitivity=c.sensitivity,
            distribution=c.distribution,
            cp=c.cp,
            mean=c.mean,
            half_range=c.half_range,
            sigma=c.sigma,
            wc_contribution_pct=None if wc_pct is None else wc_pct[i],
            rss_contribution_pct=None if rss_pct is None else rss_pct[i],
        )
        for i, c in enumerate(contributors)
    ]

    if wc_half == 0.0:
        warn(
            "ZERO_VARIATION",
            "Every contributor has zero tolerance: there is no variation. Contributions,"
            " P_fail and Cpk are not computed; pass/fail is judged from the mean alone.",
        )

    worst_case: WorstCaseResult | None = None
    if "worst_case" in methods:
        lower, upper = mean - wc_half, mean + wc_half
        meets = linear.within_spec(
            lower, req.lsl, req.usl, _SPEC_ABS_TOL_MM
        ) and linear.within_spec(upper, req.lsl, req.usl, _SPEC_ABS_TOL_MM)
        worst_case = WorstCaseResult(half_range=wc_half, lower=lower, upper=upper, meets_spec=meets)
        if not meets:
            warn(
                "WORST_CASE_FAILS_SPEC",
                f"Worst-case range [{lower:.6g}, {upper:.6g}] mm is not inside the spec.",
            )

    rss: RssResult | None = None
    if "rss" in methods:
        if sigma > 0.0:
            p_fail: float | None = linear.normal_p_fail(mean, sigma, req.lsl, req.usl)
            cpl, cpu, cpk = linear.capability(mean, sigma, req.lsl, req.usl)
            cpk_out: float | None = cpk
        else:
            p_fail, cpl, cpu, cpk_out = None, None, None, None
        rss = RssResult(
            sigma=sigma,
            three_sigma=3.0 * sigma,
            lower=mean - 3.0 * sigma,
            upper=mean + 3.0 * sigma,
            p_fail=p_fail,
            p_fail_ppm=None if p_fail is None else 1e6 * p_fail,
            cpl=cpl,
            cpu=cpu,
            cpk=cpk_out,
            meets_spec_at_mean=linear.within_spec(mean, req.lsl, req.usl),
        )
        if 3.0 * sigma > wc_half + _EXCEEDS_ABS_TOL_MM:
            warn(
                "RSS_EXCEEDS_WORST_CASE",
                f"RSS 3-sigma half-range ({3.0 * sigma:.6g} mm) exceeds the worst-case"
                f" half-range ({wc_half:.6g} mm). This happens with uniform contributors or"
                " cp < 1; the mean +/- 3 sigma interval then includes values that the"
                " tolerances do not allow.",
            )
        non_normal = [c.id for c in contributors if c.distribution != "normal" and c.half_range > 0]
        if non_normal:
            warn(
                "NON_NORMAL_INPUT",
                "P_fail and Cpk assume a normal output, but these contributors are not"
                f" normal: {', '.join(non_normal)}. Treat the analytic P_fail as approximate"
                " and prefer the Monte Carlo result.",
            )

    modified_rss: ModifiedRssResult | None = None
    k = stack.analysis.modified_rss_k
    if k is not None:
        half = linear.modified_rss_half_range(contributors, k)
        modified_rss = ModifiedRssResult(k=k, half_range=half, lower=mean - half, upper=mean + half)
        if half > wc_half + _EXCEEDS_ABS_TOL_MM:
            warn(
                "MODIFIED_RSS_EXCEEDS_WORST_CASE",
                f"Modified RSS half-range ({half:.6g} mm, k = {k:g}) exceeds the worst-case"
                f" half-range ({wc_half:.6g} mm); it is not capped.",
            )

    monte_carlo: MonteCarloResult | None = None
    if "monte_carlo" in methods:
        mc_cfg = stack.analysis.monte_carlo
        if mc_cfg is None:  # pragma: no cover - guaranteed by AnalysisConfig validation
            raise ValueError("analysis.monte_carlo is required for the monte_carlo method")
        y = montecarlo.sample_stack(contributors, req.constant, mc_cfg.n, mc_cfg.seed)
        monte_carlo = montecarlo.summarise(y, req.lsl, req.usl, mc_cfg.seed)
        if not monte_carlo.converged:
            warn(
                "MC_NOT_CONVERGED",
                f"Monte Carlo std at N/2 ({monte_carlo.std_half:.6g} mm) and at N"
                f" ({monte_carlo.std:.6g} mm) differ by more than"
                f" {100 * montecarlo.CONVERGENCE_REL_TOL:g} %; increase n.",
            )
        if monte_carlo.zero_failure_upper_bound is not None:
            warn(
                "MC_ZERO_FAILURES",
                f"0 failures in {monte_carlo.n} samples. This is not 0 ppm: the one-sided"
                " 95 % upper bound on the failure rate is"
                f" {1e6 * monte_carlo.zero_failure_upper_bound:.4g} ppm.",
            )

    return StackResult(
        name=stack.name,
        units=stack.units,
        description=req.description,
        lsl=req.lsl,
        usl=req.usl,
        constant=req.constant,
        mean=mean,
        contributors=summaries,
        worst_case=worst_case,
        rss=rss,
        modified_rss=modified_rss,
        monte_carlo=monte_carlo,
        warnings=warnings,
    )
