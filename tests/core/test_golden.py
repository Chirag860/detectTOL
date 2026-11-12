"""Hand-derived golden cases for the linear 1D engine.

Every expected number is derived step by step in the test's docstring. The
derivations were re-done independently by a reviewer subagent that saw only the
spec and the case definitions (see docs/reports/phase-1.md).

Tolerance policy for closed-form values:
    rel=1e-12 - the code and the hand formula are the same handful of float
    operations, so only rounding of the last few bits may differ.
Where the docstring states a rounded 7-significant-figure value, the comparison
uses rel=1e-6 (half a unit in the 7th figure is at most 5e-7 relative).
"""

from __future__ import annotations

import math

import pytest
from scipy.stats import norm

from detecttol import Stack, analyze
from tests.conftest import case_a_contributors, contributor, make_stack

EXACT = {"rel": 1e-12, "abs": 1e-15}
SEVEN_SF = {"rel": 1e-6}


def test_golden_case_a(case_a: Stack) -> None:
    """Golden case A (root.md, Phase 1).

    Slot depth 50.00 +/-0.10 (a = +1); three plates 16.60 +/-0.05 (a = -1);
    normal, cp = 1; LSL = 0.

    mu_Y        = 50.00 - 3 * 16.60 = 0.20
    WC half     = 0.10 + 3 * 0.05 = 0.25          -> range [-0.05, 0.45]
    (3 sigma)^2 = 0.10^2 + 3 * 0.05^2 = 0.0175    (cp = 1 -> 3 sigma_i = t_i)
    3 sigma_Y   = sqrt(0.0175) = 0.1322876
    sigma_Y     = 0.1322876 / 3 = 0.04409586
    RSS range   = 0.20 -/+ 0.1322876 = [0.0677124, 0.3322876]
    WC contrib  = 0.10/0.25 = 40 %, each plate 0.05/0.25 = 20 %
    RSS contrib = 0.01/0.0175 = 57.142857 %, each plate 0.0025/0.0175 = 14.285714 %
    z           = (0 - 0.20)/0.04409586 = -4.535574
    P_fail      = Phi(-4.535574) = 2.872356e-6 (about 2.9 ppm)
    Cpl         = 0.20 / 0.1322876 = 1.511858
    """
    r = analyze(case_a)

    assert r.mean == pytest.approx(0.20, **EXACT)

    assert r.worst_case is not None
    assert r.worst_case.half_range == pytest.approx(0.25, **EXACT)
    assert r.worst_case.lower == pytest.approx(-0.05, **EXACT)
    assert r.worst_case.upper == pytest.approx(0.45, **EXACT)
    assert r.worst_case.meets_spec is False

    assert r.rss is not None
    assert r.rss.three_sigma == pytest.approx(math.sqrt(0.0175), **EXACT)
    assert r.rss.three_sigma == pytest.approx(0.1322876, **SEVEN_SF)
    assert r.rss.sigma == pytest.approx(0.04409586, **SEVEN_SF)
    assert r.rss.lower == pytest.approx(0.0677124, **SEVEN_SF)
    assert r.rss.upper == pytest.approx(0.3322876, **SEVEN_SF)

    wc = [c.wc_contribution_pct for c in r.contributors]
    assert wc == pytest.approx([40.0, 20.0, 20.0, 20.0], **EXACT)
    rss = [c.rss_contribution_pct for c in r.contributors]
    assert rss == pytest.approx([100 * 0.01 / 0.0175] + [100 * 0.0025 / 0.0175] * 3, **EXACT)
    assert rss == pytest.approx([57.142857, 14.285714, 14.285714, 14.285714], abs=5e-7)

    # Expected P_fail computed with scipy from the hand-derived sigma (spec instruction).
    sigma_y = math.sqrt(0.0175) / 3.0
    expected_p = float(norm.cdf(-0.20 / sigma_y))
    assert r.rss.p_fail == pytest.approx(expected_p, rel=1e-9)
    assert r.rss.p_fail == pytest.approx(2.872356e-6, **SEVEN_SF)
    assert 2.5e-6 < r.rss.p_fail < 3.3e-6  # sanity band required by the spec
    assert r.rss.p_fail_ppm == pytest.approx(1e6 * expected_p, rel=1e-9)

    assert r.rss.cpl == pytest.approx(1.511858, **SEVEN_SF)
    assert r.rss.cpu is None
    assert r.rss.cpk == pytest.approx(1.511858, **SEVEN_SF)

    assert "WORST_CASE_FAILS_SPEC" in [w.code for w in r.warnings]


def test_golden_case_a_modified_rss() -> None:
    """Bender k = 1.5 on case A.

    half-range = 1.5 * sqrt(0.0175) = 1.5 * 0.1322876 = 0.1984313
    range      = 0.20 -/+ 0.1984313 = [0.0015687, 0.3984313]
    0.1984313 < WC half-range 0.25 -> no warning.
    """
    r = analyze(make_stack(case_a_contributors(), lsl=0.0, k=1.5))
    assert r.modified_rss is not None
    assert r.modified_rss.half_range == pytest.approx(0.1984313, **SEVEN_SF)
    # The lower limit is a difference of two nearly equal numbers (0.2000 - 0.1984),
    # and mu_Y = 50 - 3*16.6 itself carries ~1e-14 mm of rounding, so an absolute
    # tolerance is the right check here: 1e-12 mm.
    assert r.modified_rss.lower == pytest.approx(0.0015687, abs=5e-8)
    assert r.modified_rss.lower == pytest.approx(0.20 - 1.5 * math.sqrt(0.0175), abs=1e-12)
    assert r.modified_rss.upper == pytest.approx(0.3984313, **SEVEN_SF)
    assert "MODIFIED_RSS_EXCEEDS_WORST_CASE" not in [w.code for w in r.warnings]


def test_golden_case_b_asymmetric() -> None:
    """Golden case B: asymmetric tolerances (midpoint re-centring), two-sided spec.

    Housing 30.00 +0.20/-0.00 (a = +1): mu = 30.00 + 0.20/2 = 30.10, t = 0.10
    Insert  29.80 +0.00/-0.10 (a = -1): mu = 29.80 - 0.10/2 = 29.75, t = 0.05
    LSL = 0.10, USL = 0.50; normal, cp = 1.

    mu_Y        = 30.10 - 29.75 = 0.35
    WC half     = 0.10 + 0.05 = 0.15              -> range [0.20, 0.50] (meets spec)
    (3 sigma)^2 = 0.10^2 + 0.05^2 = 0.0125
    3 sigma_Y   = sqrt(0.0125) = 0.1118034;  sigma_Y = 0.03726780
    RSS range   = [0.2381966, 0.4618034]
    WC contrib  = 0.10/0.15 = 66.666667 %, 33.333333 %
    RSS contrib = 0.01/0.0125 = 80 %, 20 %
    z_L = (0.10 - 0.35)/0.03726780 = -6.708204;  z_U = (0.50 - 0.35)/0.03726780 = 4.024922
    P_fail = Phi(-6.708204) + (1 - Phi(4.024922)) = 9.85e-12 + 2.849706e-5 = 2.849707e-5
    Cpl = 0.25/0.1118034 = 2.236068;  Cpu = 0.15/0.1118034 = 1.341641;  Cpk = 1.341641
    Bender k = 1.5: 1.5 * 0.1118034 = 0.1677051 > 0.15 -> warning.
    """
    stack = make_stack(
        [
            contributor("housing", 30.00, 0.20, 0.00, 1.0),
            contributor("insert", 29.80, 0.00, -0.10, -1.0),
        ],
        lsl=0.10,
        usl=0.50,
        k=1.5,
    )
    r = analyze(stack)

    housing, insert = r.contributors
    assert housing.mean == pytest.approx(30.10, **EXACT)
    assert housing.half_range == pytest.approx(0.10, **EXACT)
    assert insert.mean == pytest.approx(29.75, **EXACT)
    assert insert.half_range == pytest.approx(0.05, **EXACT)

    assert r.mean == pytest.approx(0.35, **EXACT)
    assert r.worst_case is not None
    assert r.worst_case.half_range == pytest.approx(0.15, **EXACT)
    assert r.worst_case.lower == pytest.approx(0.20, **EXACT)
    assert r.worst_case.upper == pytest.approx(0.50, **EXACT)
    # Upper limit lands exactly on USL: must count as meeting the spec.
    assert r.worst_case.meets_spec is True

    assert r.rss is not None
    assert r.rss.three_sigma == pytest.approx(0.1118034, **SEVEN_SF)
    assert r.rss.sigma == pytest.approx(0.03726780, **SEVEN_SF)
    assert r.rss.lower == pytest.approx(0.2381966, **SEVEN_SF)
    assert r.rss.upper == pytest.approx(0.4618034, **SEVEN_SF)
    assert [c.wc_contribution_pct for c in r.contributors] == pytest.approx(
        [200.0 / 3.0, 100.0 / 3.0], **EXACT
    )
    assert [c.rss_contribution_pct for c in r.contributors] == pytest.approx([80.0, 20.0], **EXACT)

    sigma_y = math.sqrt(0.0125) / 3.0
    expected_p = float(norm.cdf((0.10 - 0.35) / sigma_y)) + float(norm.sf((0.50 - 0.35) / sigma_y))
    assert r.rss.p_fail == pytest.approx(expected_p, rel=1e-9)
    assert r.rss.p_fail == pytest.approx(2.849707e-5, **SEVEN_SF)
    assert r.rss.cpl == pytest.approx(2.236068, **SEVEN_SF)
    assert r.rss.cpu == pytest.approx(1.341641, **SEVEN_SF)
    assert r.rss.cpk == pytest.approx(1.341641, **SEVEN_SF)

    assert r.modified_rss is not None
    assert r.modified_rss.half_range == pytest.approx(0.1677051, **SEVEN_SF)
    codes = [w.code for w in r.warnings]
    assert "MODIFIED_RSS_EXCEEDS_WORST_CASE" in codes
    assert "WORST_CASE_FAILS_SPEC" not in codes


def test_spec_example_asymmetric_single() -> None:
    """Spec Section 3.1 example: 10.0 +0.2/-0.0 -> mu = 10.1, t = 0.1.

    sigma (normal, cp = 1) = 0.1/3 = 0.03333333.
    """
    r = analyze(make_stack([contributor("d", 10.0, 0.2, 0.0, 1.0)], lsl=9.0))
    (c,) = r.contributors
    assert c.mean == pytest.approx(10.1, **EXACT)
    assert c.half_range == pytest.approx(0.1, **EXACT)
    assert c.sigma == pytest.approx(0.1 / 3.0, **EXACT)


def test_case_c_uniform_mix() -> None:
    """Case C: one uniform and one normal contributor.

    X1 = 20.0 +/-0.30 uniform (a = +1): sigma_1 = 0.30/sqrt(3) = 0.1732051
    X2 = 19.0 +/-0.10 normal cp = 1 (a = -1): sigma_2 = 0.10/3 = 0.03333333
    LSL = 0.5, USL = 1.6.

    mu_Y      = 20.0 - 19.0 = 1.0
    WC half   = 0.30 + 0.10 = 0.40                  -> range [0.6, 1.4] (meets spec)
    sigma_Y^2 = 0.09/3 + 0.01/9 = 0.03 + 0.00111111 = 0.03111111
    sigma_Y   = 0.1763834;  3 sigma_Y = 0.5291503  (> 0.40 -> warning)
    RSS contrib = 0.03/0.03111111 = 27/28 = 96.428571 %, 1/28 = 3.571429 %
    WC contrib  = 75 %, 25 %
    Normal-approximation P_fail = Phi(-2.834734) + (1 - Phi(3.401680)) = 2.628061e-3
    Cpl = 0.5/0.5291503 = 0.9449112; Cpu = 0.6/0.5291503 = 1.133893
    """
    stack = make_stack(
        [
            contributor("x1", 20.0, 0.30, -0.30, 1.0, "uniform"),
            contributor("x2", 19.0, 0.10, -0.10, -1.0),
        ],
        lsl=0.5,
        usl=1.6,
    )
    r = analyze(stack)
    x1, x2 = r.contributors
    assert x1.sigma == pytest.approx(0.1732051, **SEVEN_SF)
    assert x2.sigma == pytest.approx(0.03333333, **SEVEN_SF)
    assert r.mean == pytest.approx(1.0, **EXACT)
    assert r.worst_case is not None
    assert r.worst_case.half_range == pytest.approx(0.40, **EXACT)
    assert r.worst_case.meets_spec is True
    assert r.rss is not None
    assert r.rss.sigma == pytest.approx(0.1763834, **SEVEN_SF)
    assert r.rss.three_sigma == pytest.approx(0.5291503, **SEVEN_SF)
    assert [x1.rss_contribution_pct, x2.rss_contribution_pct] == pytest.approx(
        [2700.0 / 28.0, 100.0 / 28.0], **EXACT
    )
    assert [x1.wc_contribution_pct, x2.wc_contribution_pct] == pytest.approx([75.0, 25.0], **EXACT)
    assert r.rss.p_fail == pytest.approx(2.628061e-3, **SEVEN_SF)
    assert r.rss.cpl == pytest.approx(0.9449112, **SEVEN_SF)
    assert r.rss.cpu == pytest.approx(1.133893, **SEVEN_SF)
    codes = [w.code for w in r.warnings]
    assert "RSS_EXCEEDS_WORST_CASE" in codes
    assert "NON_NORMAL_INPUT" in codes


def test_case_d_cp_and_usl_only() -> None:
    """Case D: cp != 1 and a one-sided upper spec.

    P1 = 25.0 +/-0.12 normal cp = 2 (a = +1): sigma_1 = 0.12/(3*2) = 0.02
    P2 = 10.0 +/-0.06 normal cp = 1 (a = +1): sigma_2 = 0.06/3 = 0.02
    USL = 35.10 only.

    mu_Y      = 35.0
    WC half   = 0.18                                -> range [34.82, 35.18] (fails USL)
    sigma_Y   = sqrt(0.0004 + 0.0004) = sqrt(0.0008) = 0.02828427
    3 sigma_Y = 0.08485281
    RSS contrib = 50 %, 50 %;  WC contrib = 0.12/0.18 = 66.666667 %, 33.333333 %
    z_U = 0.10/0.02828427 = 3.535534;  P_fail = 1 - Phi(3.535534) = 2.034760e-4
    Cpu = 0.10/0.08485281 = 1.178511 (= Cpk); Cpl undefined.
    """
    stack = make_stack(
        [
            contributor("p1", 25.0, 0.12, -0.12, 1.0, cp=2.0),
            contributor("p2", 10.0, 0.06, -0.06, 1.0),
        ],
        usl=35.10,
    )
    r = analyze(stack)
    assert [c.sigma for c in r.contributors] == pytest.approx([0.02, 0.02], **EXACT)
    assert r.mean == pytest.approx(35.0, **EXACT)
    assert r.worst_case is not None
    assert r.worst_case.half_range == pytest.approx(0.18, **EXACT)
    assert r.worst_case.meets_spec is False
    assert r.rss is not None
    assert r.rss.sigma == pytest.approx(0.02828427, **SEVEN_SF)
    assert r.rss.three_sigma == pytest.approx(0.08485281, **SEVEN_SF)
    assert [c.rss_contribution_pct for c in r.contributors] == pytest.approx([50.0, 50.0], **EXACT)
    assert [c.wc_contribution_pct for c in r.contributors] == pytest.approx(
        [200.0 / 3.0, 100.0 / 3.0], **EXACT
    )
    expected_p = float(norm.sf(0.10 / math.sqrt(0.0008)))
    assert r.rss.p_fail == pytest.approx(expected_p, rel=1e-9)
    assert r.rss.p_fail == pytest.approx(2.034760e-4, **SEVEN_SF)
    assert r.rss.cpl is None
    assert r.rss.cpu == pytest.approx(1.178511, **SEVEN_SF)
    assert r.rss.cpk == pytest.approx(1.178511, **SEVEN_SF)


@pytest.mark.parametrize(
    ("cp", "factor", "sigma"),
    [
        # k = 3: phi(3) = 0.004431848, 2 Phi(3) - 1 = 0.9973002
        # factor = sqrt(1 - 6 * 0.004431848 / 0.9973002) = 0.9865784; sigma0 = 0.1
        (1.0, 0.9865784, 0.09865784),
        # k = 2: phi(2) = 0.05399097, 2 Phi(2) - 1 = 0.9544997
        # factor = sqrt(1 - 4 * 0.05399097 / 0.9544997) = 0.8796257; sigma0 = 0.15
        (2.0 / 3.0, 0.8796257, 0.1319438),
    ],
)
def test_case_e_truncated_normal_sigma(cp: float, factor: float, sigma: float) -> None:
    """Case E: single contributor 10.0 +/-0.30, truncated_normal.

    sigma0 = t/(3 cp); k = 3 cp; sigma = sigma0 * sqrt(1 - 2 k phi(k)/(2 Phi(k) - 1)).
    Numbers per parameter set are derived in the parametrize comments above.
    """
    r = analyze(
        make_stack([contributor("d", 10.0, 0.30, -0.30, 1.0, "truncated_normal", cp)], lsl=9.0)
    )
    (c,) = r.contributors
    sigma0 = 0.30 / (3.0 * cp)
    assert c.sigma / sigma0 == pytest.approx(factor, **SEVEN_SF)
    assert c.sigma == pytest.approx(sigma, **SEVEN_SF)


def test_case_g_single_contributor_and_real_sensitivity() -> None:
    """Case G: single normal contributor 10.0 +/-0.2, cp = 1.

    a = +1:   WC half = 0.2; 3 sigma_Y = 3 * 0.2/3 = 0.2 (equal; no warning)
    a = -2.5: mu_Y = -25.0; WC half = 2.5 * 0.2 = 0.5; sigma_Y = 2.5 * 0.2/3 = 0.1666667
    """
    r = analyze(make_stack([contributor("d", 10.0, 0.2, -0.2, 1.0)], lsl=9.0))
    assert r.worst_case is not None and r.rss is not None
    assert r.worst_case.half_range == pytest.approx(0.2, **EXACT)
    assert r.rss.three_sigma == pytest.approx(0.2, **EXACT)
    assert "RSS_EXCEEDS_WORST_CASE" not in [w.code for w in r.warnings]

    r2 = analyze(make_stack([contributor("d", 10.0, 0.2, -0.2, -2.5)], usl=0.0))
    assert r2.worst_case is not None and r2.rss is not None
    assert r2.mean == pytest.approx(-25.0, **EXACT)
    assert r2.worst_case.half_range == pytest.approx(0.5, **EXACT)
    assert r2.rss.sigma == pytest.approx(0.5 / 3.0, **EXACT)


def test_case_h_constant_term() -> None:
    """Case H: case A with constant = +0.05.

    mu_Y = 0.25; WC range = [0.00, 0.50] -> lower limit lands exactly on LSL = 0,
    which must count as meeting the spec despite float rounding.
    z = -0.25/0.04409586 = -5.669467; P_fail = Phi(-5.669467) = 7.162118e-9.
    """
    r = analyze(make_stack(case_a_contributors(), lsl=0.0, constant=0.05))
    assert r.mean == pytest.approx(0.25, **EXACT)
    assert r.worst_case is not None and r.rss is not None
    assert r.worst_case.lower == pytest.approx(0.0, abs=1e-12)
    assert r.worst_case.upper == pytest.approx(0.50, **EXACT)
    assert r.worst_case.meets_spec is True
    assert r.rss.p_fail == pytest.approx(7.162118e-9, **SEVEN_SF)


def test_zero_variation_stack() -> None:
    """Every tolerance is zero: sigma_Y = 0.

    Per spec (E4): P_fail and Cpk are not computed; pass/fail comes from mu_Y.
    mu_Y = 10.0 - 4.0 = 6.0; LSL = 5 -> passes at the mean.
    """
    r = analyze(
        make_stack(
            [contributor("a", 10.0, 0.0, 0.0, 1.0), contributor("b", 4.0, 0.0, 0.0, -1.0)],
            lsl=5.0,
            n=100,
        )
    )
    assert r.mean == pytest.approx(6.0, **EXACT)
    assert r.rss is not None and r.worst_case is not None and r.monte_carlo is not None
    assert r.rss.sigma == 0.0
    assert r.rss.p_fail is None and r.rss.cpk is None and r.rss.cpl is None
    assert r.rss.meets_spec_at_mean is True
    assert r.worst_case.meets_spec is True
    assert all(c.wc_contribution_pct is None for c in r.contributors)
    assert all(c.rss_contribution_pct is None for c in r.contributors)
    assert r.monte_carlo.std == 0.0 and r.monte_carlo.converged is True
    assert r.monte_carlo.convergence_rel_diff is None
    assert r.monte_carlo.histogram.counts == [100]
    assert "ZERO_VARIATION" in [w.code for w in r.warnings]


def test_methods_are_optional() -> None:
    """Only the requested methods are run."""
    r = analyze(make_stack(case_a_contributors(), lsl=0.0, methods=["rss"]))
    assert r.worst_case is None and r.monte_carlo is None and r.modified_rss is None
    assert r.rss is not None
    r2 = analyze(make_stack(case_a_contributors(), lsl=0.0, methods=["worst_case"]))
    assert r2.rss is None and r2.worst_case is not None
