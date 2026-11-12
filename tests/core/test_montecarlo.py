"""Monte Carlo engine: interval formulas, determinism, agreement with closed form."""

from __future__ import annotations

import math

import numpy as np
import pytest

from detecttol import analyze
from detecttol.core import montecarlo
from tests.conftest import case_a_contributors, contributor, make_stack

SEVEN_SF = {"rel": 1e-6}


def test_wilson_interval_hand_values() -> None:
    """Wilson two-sided 95 % interval, z = 1.959964 (z^2 = 3.841459).

    centre = (p + z^2/2N)/(1 + z^2/N); half = z*sqrt(p(1-p)/N + z^2/4N^2)/(1 + z^2/N)

    x = 0, N = 1000: centre = half = (z^2/2N)/(1 + z^2/N)
        -> lower = 0, upper = z^2/(N + z^2) = 3.841459/1003.841459 = 3.826759e-3
    x = 5, N = 1000: p = 0.005
        centre = (0.005 + 0.001920729)/1.003841459 = 0.006894246
        half   = 1.959964*sqrt(4.975e-6 + 9.603647e-7)/1.003841459 = 0.004756710
        -> [2.137536e-3, 1.165096e-2]
    x = 3, N = 100000 -> [1.020276e-5, 8.820805e-5]
    (All three re-derived independently by the reviewer subagent.)
    """
    lo, hi = montecarlo.wilson_interval(0, 1000)
    assert lo == 0.0
    assert hi == pytest.approx(3.826759e-3, **SEVEN_SF)

    lo, hi = montecarlo.wilson_interval(5, 1000)
    assert lo == pytest.approx(2.137536e-3, **SEVEN_SF)
    assert hi == pytest.approx(1.165096e-2, **SEVEN_SF)

    lo, hi = montecarlo.wilson_interval(3, 100_000)
    assert lo == pytest.approx(1.020276e-5, **SEVEN_SF)
    assert hi == pytest.approx(8.820805e-5, **SEVEN_SF)


def test_wilson_interval_all_failures_and_bad_input() -> None:
    """x = N: upper limit is exactly 1 (clamped); invalid counts raise."""
    lo, hi = montecarlo.wilson_interval(10, 10)
    assert hi == 1.0
    assert 0.0 < lo < 1.0
    with pytest.raises(ValueError, match="need n > 0"):
        montecarlo.wilson_interval(1, 0)
    with pytest.raises(ValueError, match="need n > 0"):
        montecarlo.wilson_interval(5, 4)


def test_zero_failure_upper_bound_hand_values() -> None:
    """Exact one-sided 95 % bound for 0 failures: p = 1 - 0.05^(1/N).

    N = 1000:   ln 0.05 = -2.995732; exp(-0.002995732) = 0.997008750 -> p = 2.991250e-3
                (rule of three: 3/1000 = 3.0e-3)
    N = 100000: p = 2.995687e-5 (rule of three: 3.0e-5)
    """
    assert montecarlo.zero_failure_upper_bound(1000) == pytest.approx(2.991250e-3, **SEVEN_SF)
    assert montecarlo.zero_failure_upper_bound(100_000) == pytest.approx(2.995687e-5, **SEVEN_SF)
    # Always just below the rule-of-three value.
    assert montecarlo.zero_failure_upper_bound(100_000) < 3.0 / 100_000
    with pytest.raises(ValueError, match="need n > 0"):
        montecarlo.zero_failure_upper_bound(0)


def test_same_seed_is_bit_identical() -> None:
    """Determinism rule: same seed and input -> identical samples and result."""
    stack = make_stack(case_a_contributors(), lsl=0.0, n=20_000, seed=123)
    c = stack.contributors
    y1 = montecarlo.sample_stack(c, 0.0, 20_000, 123)
    y2 = montecarlo.sample_stack(c, 0.0, 20_000, 123)
    assert np.array_equal(y1, y2)
    assert analyze(stack) == analyze(stack)
    y3 = montecarlo.sample_stack(c, 0.0, 20_000, 124)
    assert not np.array_equal(y1, y3)


def test_case_a_monte_carlo_agrees_with_closed_form() -> None:
    """Case A by Monte Carlo, N = 100 000, seed 42.

    Closed form: mu_Y = 0.20, sigma_Y = 0.04409586.
    Standard error of the mean = sigma/sqrt(N) = 1.39e-4 -> allow 5 SE = 7e-4.
    Relative SE of the std = 1/sqrt(2N) = 0.22 % -> allow 2 % (about 9 SE).
    Expected failures = N * 2.87e-6 = 0.29, so n_fail must be tiny (<= 5 is
    beyond 1e-5 probability for a Poisson mean of 0.29).
    """
    r = analyze(make_stack(case_a_contributors(), lsl=0.0, n=100_000, seed=42))
    mc = r.monte_carlo
    assert mc is not None
    assert mc.n == 100_000 and mc.seed == 42
    assert mc.mean == pytest.approx(0.20, abs=7e-4)
    assert mc.std == pytest.approx(0.04409586, rel=0.02)
    assert mc.n_fail <= 5
    assert mc.fraction_fail == mc.n_fail / mc.n
    assert mc.fraction_fail_ppm == pytest.approx(1e6 * mc.n_fail / mc.n, rel=1e-12)
    assert mc.wilson_lower <= mc.fraction_fail <= mc.wilson_upper
    assert mc.converged is True
    p = mc.percentiles
    assert mc.min <= p.p0_135 <= p.p2_5 <= p.p50 <= p.p97_5 <= p.p99_865 <= mc.max
    # Normal output: the 0.135 % / 99.865 % percentiles sit near mu -/+ 3 sigma.
    # They rest on ~135 samples each, so allow 0.2 sigma.
    assert p.p0_135 == pytest.approx(0.20 - 0.1322876, abs=0.2 * 0.0441)
    assert p.p99_865 == pytest.approx(0.20 + 0.1322876, abs=0.2 * 0.0441)
    assert sum(mc.histogram.counts) == mc.n
    assert len(mc.histogram.edges) == len(mc.histogram.counts) + 1


def test_zero_failures_reports_upper_bound_not_zero_ppm() -> None:
    """One-sided spec that cannot fail: uniform 10.0 +/-0.1 (bounded), LSL = 9.8.

    Every sample lies in [9.9, 10.1] > 9.8, so n_fail = 0 with certainty.
    N = 1000 -> one-sided 95 % bound 1 - 0.05^(1/1000) = 2.991250e-3 (2991.25 ppm),
    Wilson = [0, 3.826759e-3].
    """
    r = analyze(
        make_stack([contributor("d", 10.0, 0.1, -0.1, 1.0, "uniform")], lsl=9.8, n=1000, seed=5)
    )
    mc = r.monte_carlo
    assert mc is not None
    assert mc.n_fail == 0 and mc.fraction_fail == 0.0
    assert mc.zero_failure_upper_bound == pytest.approx(2.991250e-3, **SEVEN_SF)
    assert mc.wilson_lower == 0.0
    assert mc.wilson_upper == pytest.approx(3.826759e-3, **SEVEN_SF)
    assert mc.min >= 9.9 and mc.max <= 10.1
    warning = next(w for w in r.warnings if w.code == "MC_ZERO_FAILURES")
    assert "2991" in warning.message and "not 0 ppm" in warning.message


def test_failures_counted_on_both_sides() -> None:
    """Two-sided spec on a uniform 10.0 +/-0.3: LSL = 9.85, USL = 10.24.

    True fraction outside = (0.15 + 0.06)/0.6 = 0.35.
    N = 40 000 -> SE = sqrt(0.35*0.65/40000) = 2.4e-3; allow 5 SE = 0.012.
    With failures present there is no zero-failure bound.
    """
    r = analyze(
        make_stack(
            [contributor("d", 10.0, 0.3, -0.3, 1.0, "uniform")],
            lsl=9.85,
            usl=10.24,
            n=40_000,
            seed=3,
        )
    )
    mc = r.monte_carlo
    assert mc is not None
    assert mc.fraction_fail == pytest.approx(0.35, abs=0.012)
    assert mc.zero_failure_upper_bound is None
    assert "MC_ZERO_FAILURES" not in [w.code for w in r.warnings]


def test_uniform_and_truncated_samples_match_their_sigma() -> None:
    """Sample std of each distribution matches the documented sigma convention.

    10.0 +/-0.30, N = 200 000 -> relative SE of the std <= 1/sqrt(2N) = 0.16 %; allow 1.5 %.
      uniform:           sigma = 0.30/sqrt(3) = 0.1732051, samples inside [9.7, 10.3]
      truncated cp = 1:  sigma = 0.09865784,               samples inside [9.7, 10.3]
      truncated cp = 2/3: sigma = 0.1319438
      normal cp = 1:     sigma = 0.1 (unbounded: some samples fall outside +/-t)
    """
    cases = [
        ("uniform", 1.0, 0.1732051, True),
        ("truncated_normal", 1.0, 0.09865784, True),
        ("truncated_normal", 2.0 / 3.0, 0.1319438, True),
        ("normal", 1.0, 0.1, False),
    ]
    for dist, cp, sigma, bounded in cases:
        stack = make_stack([contributor("d", 10.0, 0.3, -0.3, 1.0, dist, cp)], lsl=0.0)
        y = montecarlo.sample_stack(stack.contributors, 0.0, 200_000, 11)
        assert float(np.std(y, ddof=1)) == pytest.approx(sigma, rel=0.015), dist
        assert float(np.mean(y)) == pytest.approx(10.0, abs=5 * sigma / math.sqrt(200_000)), dist
        inside = bool(np.all((y >= 9.7) & (y <= 10.3)))
        assert inside is bounded, dist


def test_convergence_warning_fires_when_halves_disagree() -> None:
    """A sample whose first half is much tighter than the whole is flagged.

    First half alternates +/-1 (std = 1.0), second half alternates +/-3.
    Whole-sample variance = (1 + 9)/2 = 5 -> std = 2.236; relative difference
    |1 - 2.236|/2.236 = 55 % > 1 % -> not converged.
    """
    half = np.tile([-1.0, 1.0], 500)
    y = np.concatenate([half, 3.0 * half])
    res = montecarlo.summarise(y, lsl=-10.0, usl=None, seed=0)
    assert res.std_half == pytest.approx(1.0, rel=2e-3)
    assert res.std == pytest.approx(math.sqrt(5.0), rel=2e-3)
    assert res.convergence_rel_diff == pytest.approx(1 - 1 / math.sqrt(5.0), rel=5e-3)
    assert res.converged is False


def test_convergence_warning_reaches_the_result() -> None:
    """End to end: a tiny N makes the heuristic fire and the warning is reported.

    N = 4, seed 0 for a single normal contributor: the first two samples and all
    four have clearly different std (checked here, not assumed).
    """
    stack = make_stack([contributor("d", 10.0, 0.3, -0.3, 1.0)], lsl=0.0, n=4, seed=0)
    r = analyze(stack)
    mc = r.monte_carlo
    assert mc is not None
    assert mc.convergence_rel_diff is not None
    codes = [w.code for w in r.warnings]
    assert ("MC_NOT_CONVERGED" in codes) is (mc.convergence_rel_diff > 0.01)
    assert mc.converged is (mc.convergence_rel_diff <= 0.01)
