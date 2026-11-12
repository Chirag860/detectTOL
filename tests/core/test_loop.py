"""Phase 3: 2D vector loops with relative angles.

Conventions under test (docs/ASSUMPTIONS.md A12-A15):

    Theta_j = phi_1 + ... + phi_j            (relative angles, CCW, first from +x)
    Y       = constant + sum_j L_j cos(Theta_j - alpha)
    dY/dL_j   =  cos(Theta_j - alpha)
    dY/dphi_k = -sum_{j >= k} L_j sin(Theta_j - alpha)

Every expected number is derived in the test's docstring and was re-derived
independently by a reviewer subagent that saw only the spec and the case
definitions (docs/reports/phase-3.md).

Tolerance policy:
    SEVEN_SF (rel 1e-6) where the docstring states a rounded 7-figure value.
    EXACT (rel 1e-12, abs 1e-12 mm) where code and hand formula are the same few
    float operations; the abs term covers values that are analytically zero but
    evaluate to ~1e-15 because pi/2 is not exactly representable.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import ValidationError
from scipy.stats import norm

from detecttol import analyze
from detecttol.core.loop import (
    LoopResult,
    LoopVariable,
    LoopVector,
    VectorLoop,
    analytic_sensitivities,
    analyze_loop,
    fd_step,
    finite_difference_sensitivities,
    loop_value,
    sample_loop,
)
from detecttol.core.models import AnalysisConfig, MonteCarloConfig, Requirement
from tests.conftest import case_a_contributors, make_stack

EXACT = {"rel": 1e-12, "abs": 1e-12}
SEVEN_SF = {"rel": 1e-6}
HALF_PI = math.pi / 2.0


def var(vid: str, nominal: float, t: float, **kw: Any) -> LoopVariable:
    return LoopVariable(id=vid, nominal=nominal, upper_tol=t, lower_tol=-t, **kw)


def make_loop(
    vectors: list[LoopVector],
    *,
    alpha: float = 0.0,
    lsl: float | None = None,
    usl: float | None = None,
    constant: float = 0.0,
    n: int | None = None,
    seed: int = 1,
) -> VectorLoop:
    if n is None:
        analysis = AnalysisConfig()
    else:
        analysis = AnalysisConfig(
            methods=["worst_case", "rss", "monte_carlo"],
            monte_carlo=MonteCarloConfig(n=n, seed=seed),
        )
    return VectorLoop(
        name="test_stack",
        vectors=vectors,
        measure_angle=alpha,
        requirement=Requirement(lsl=lsl, usl=usl, constant=constant),
        analysis=analysis,
    )


def sens(result: LoopResult) -> list[float]:
    return [v.sensitivity_analytic for v in result.variables]


# --------------------------------------------------------------------------- #
# Required test 1: a pure 1D chain reproduces golden case A exactly
# --------------------------------------------------------------------------- #


def case_a_loop(n: int | None = None, seed: int = 42) -> VectorLoop:
    return make_loop(
        [
            LoopVector(length=var("slot_depth", 50.00, 0.10), angle=0.0),
            LoopVector(length=var("plate_1", 16.60, 0.05), angle=math.pi),
            LoopVector(length=var("plate_2", 16.60, 0.05), angle=0.0),
            LoopVector(length=var("plate_3", 16.60, 0.05), angle=0.0),
        ],
        lsl=0.0,
        n=n,
        seed=seed,
    )


def test_1d_chain_reproduces_golden_case_a_exactly() -> None:
    """Golden case A as a vector loop, alpha = 0.

    Relative angles (0, pi, 0, 0) -> Theta = (0, pi, pi, pi).
    dY/dL_j = cos(Theta_j) = (+1, -1, -1, -1): the 1D sensitivities.
    Hence mu_Y = 50 - 3*16.6 = 0.20, WC = 0.25, 3 sigma = sqrt(0.0175) = 0.1322876,
    RSS contributions 57.142857 / 14.285714 %, P_fail = Phi(-4.535574) = 2.872356e-6.

    cos(0) = 1 and cos(pi) = -1 are exact in floating point and the loop sums its
    terms the same way as the 1D engine, so the whole result - including the
    Monte Carlo sample - must be bit-identical to the 1D analysis.
    """
    loop_res = analyze_loop(case_a_loop(n=20_000))
    lin_res = analyze(make_stack(case_a_contributors(), lsl=0.0, n=20_000, seed=42))

    assert sens(loop_res) == [1.0, -1.0, -1.0, -1.0]
    assert loop_res.result == lin_res  # every field, bit for bit

    r = loop_res.result
    assert r.rss is not None and r.worst_case is not None
    assert r.mean == pytest.approx(0.20, **EXACT)
    assert r.worst_case.half_range == pytest.approx(0.25, **EXACT)
    assert r.rss.three_sigma == pytest.approx(0.1322876, **SEVEN_SF)
    assert r.rss.p_fail == pytest.approx(float(norm.cdf(-0.20 / (math.sqrt(0.0175) / 3))), rel=1e-9)
    assert 2.5e-6 < r.rss.p_fail < 3.3e-6
    assert loop_res.loop_warnings == []
    assert [(v.kind, v.unit, v.vector_index) for v in loop_res.variables] == [
        ("length", "mm", 0),
        ("length", "mm", 1),
        ("length", "mm", 2),
        ("length", "mm", 3),
    ]


# --------------------------------------------------------------------------- #
# Required test 2: tilted pin
# --------------------------------------------------------------------------- #


def pin_loop(t: float = 0.03, n: int | None = None, seed: int = 1) -> VectorLoop:
    return make_loop(
        [LoopVector(length=100.0, angle=var("theta", 0.0, t))],
        alpha=HALF_PI,
        usl=95.0,
        n=n,
        seed=seed,
    )


def test_tilted_pin_sensitivity_and_linearised_result() -> None:
    """Pin of length L = 100 at angle theta from the reference axis; alpha = pi/2.

    Y = L cos(theta - pi/2) = L sin(theta)            (lateral tip offset)
    dY/dtheta = L cos(theta) = 100 mm/rad at theta = 0
    theta = 0 +/-0.03 rad, normal cp = 1 -> sigma_theta = 0.01 rad
    mean_Y = 0;  WC half = 100 * 0.03 = 3.0;  sigma_Y = 100 * 0.01 = 1.0
    """
    res = analyze_loop(pin_loop())
    assert sens(res) == pytest.approx([100.0], **EXACT)
    (v,) = res.variables
    assert (v.kind, v.unit) == ("angle", "rad")
    r = res.result
    assert r.worst_case is not None and r.rss is not None
    assert r.mean == pytest.approx(0.0, abs=1e-12)
    assert r.worst_case.half_range == pytest.approx(3.0, **EXACT)
    assert r.rss.sigma == pytest.approx(1.0, **EXACT)
    assert r.contributors[0].sensitivity == pytest.approx(100.0, **EXACT)
    assert r.contributors[0].sigma == pytest.approx(0.01, **EXACT)


def test_tilted_pin_monte_carlo_matches_direct_sampling_of_l_sin_theta() -> None:
    """The Monte Carlo sample equals a direct sampling of L*sin(theta), per sample.

    Direct: theta_i ~ N(0, 0.01) from default_rng(seed), y_i = 100 sin(theta_i).
    The loop computes 100 cos(theta_i - pi/2); the two differ only by the
    rounding of pi/2 (about 6e-15 mm here), so abs = 1e-12 mm per sample.

    Exact moments for theta ~ N(0, s^2), s = 0.01:
        E[Y] = 0;  Var[Y] = L^2 (1 - exp(-2 s^2))/2 = 0.9999000067 -> std 0.9999500
    N = 200 000 -> relative SE of the std = 0.16 %; allow 1 % (6 SE).
    """
    n, seed = 200_000, 7
    y = sample_loop(pin_loop(n=n, seed=seed), n, seed)
    rng = np.random.default_rng(seed)
    direct = 100.0 * np.sin(rng.normal(0.0, 0.03 / 3.0, n))
    assert np.allclose(y, direct, rtol=0.0, atol=1e-12)
    assert float(np.std(y, ddof=1)) == pytest.approx(0.9999500, rel=0.01)
    assert float(np.mean(y)) == pytest.approx(0.0, abs=5 * 1.0 / math.sqrt(n))


def test_tilted_pin_off_zero_with_length_tolerance() -> None:
    """Pin with L = 100 +/-0.2 mm and theta = 0.3 +/-0.006 rad (normal, cp = 1).

    dY/dL     = sin(0.3)       = 0.2955202
    dY/dtheta = 100 cos(0.3)   = 95.53365 mm/rad
    mean_Y    = 100 sin(0.3)   = 29.55202
    WC half   = 0.2955202*0.2 + 95.53365*0.006 = 0.05910404 + 0.5732019 = 0.6323059
    3 sigma_Y = sqrt(0.05910404^2 + 0.5732019^2) = 0.5762410;  sigma_Y = 0.1920803
    RSS contrib = 1.052025 % (L), 98.94798 % (theta)
    """
    loop = make_loop(
        [LoopVector(length=var("L", 100.0, 0.2), angle=var("theta", 0.3, 0.006))],
        alpha=HALF_PI,
        usl=31.0,
    )
    res = analyze_loop(loop)
    assert sens(res) == pytest.approx([0.2955202, 95.53365], **SEVEN_SF)
    assert sens(res) == pytest.approx([math.sin(0.3), 100 * math.cos(0.3)], **EXACT)
    r = res.result
    assert r.worst_case is not None and r.rss is not None
    assert r.mean == pytest.approx(29.55202, **SEVEN_SF)
    assert r.worst_case.half_range == pytest.approx(0.6323059, **SEVEN_SF)
    assert r.rss.three_sigma == pytest.approx(0.5762410, **SEVEN_SF)
    assert r.rss.sigma == pytest.approx(0.1920803, **SEVEN_SF)
    assert [c.rss_contribution_pct for c in r.contributors] == pytest.approx(
        [1.052025, 98.94798], **SEVEN_SF
    )
    assert [v.kind for v in res.variables] == ["length", "angle"]


def test_asymmetric_angle_tolerance_uses_the_midpoint() -> None:
    """theta = 0.294 +0.012/-0.000 rad -> mean 0.300, t = 0.006: same as the case above."""
    loop = make_loop(
        [
            LoopVector(
                length=var("L", 100.0, 0.2),
                angle=LoopVariable(id="theta", nominal=0.294, upper_tol=0.012, lower_tol=0.0),
            )
        ],
        alpha=HALF_PI,
        usl=31.0,
    )
    res = analyze_loop(loop)
    assert res.result.contributors[1].mean == pytest.approx(0.3, **EXACT)
    assert res.result.contributors[1].half_range == pytest.approx(0.006, **EXACT)
    assert res.result.mean == pytest.approx(29.55202, **SEVEN_SF)
    assert sens(res) == pytest.approx([0.2955202, 95.53365], **SEVEN_SF)


# --------------------------------------------------------------------------- #
# Required test 3: 2D triangle / angle cases with closed-form answers
# --------------------------------------------------------------------------- #


def test_wedge_height_with_angle_tolerance() -> None:
    """Height of a wedge: incline L = 80 +/-0.1 mm at theta = 15 deg +/-0.5 deg.

    In radians: theta = pi/12 = 0.2617994, t = pi/360 = 0.008726646.
    alpha = pi/2 -> Y = L sin(theta).

    mean_Y    = 80 sin(15 deg) = 20.70552
    dY/dL     = sin(15 deg)    = 0.2588190
    dY/dtheta = 80 cos(15 deg) = 77.27407 mm/rad
    WC half   = 0.2588190*0.1 + 77.27407*0.008726646 = 0.02588190 + 0.6743434 = 0.7002253
              -> range [20.00530, 21.40575]
    3 sigma_Y = sqrt(0.02588190^2 + 0.6743434^2) = 0.6748399;  sigma_Y = 0.2249466
    RSS contrib = 0.1470926 % (L), 99.85291 % (theta)
    Spec LSL = 20.0, USL = 21.4:
        worst case exceeds USL by 0.0057 mm -> does not meet spec
        z_L = -3.136404, z_U = +3.087294 -> P_fail = 8.551665e-4 + 1.009939e-3 = 1.865106e-3
        Cpl = 0.70552/0.67484 = 1.045468;  Cpu = 0.69448/0.67484 = 1.029098;  Cpk = Cpu
    """
    loop = make_loop(
        [
            LoopVector(
                length=var("L", 80.0, 0.1),
                angle=var("theta", math.radians(15.0), math.radians(0.5)),
            )
        ],
        alpha=HALF_PI,
        lsl=20.0,
        usl=21.4,
    )
    res = analyze_loop(loop)
    r = res.result
    assert r.worst_case is not None and r.rss is not None
    assert r.contributors[1].nominal == pytest.approx(0.2617994, **SEVEN_SF)
    assert r.contributors[1].half_range == pytest.approx(0.008726646, **SEVEN_SF)
    assert r.mean == pytest.approx(20.70552, **SEVEN_SF)
    assert sens(res) == pytest.approx([0.2588190, 77.27407], **SEVEN_SF)
    assert r.worst_case.half_range == pytest.approx(0.7002253, **SEVEN_SF)
    assert r.worst_case.lower == pytest.approx(20.00530, **SEVEN_SF)
    assert r.worst_case.upper == pytest.approx(21.40575, **SEVEN_SF)
    assert r.worst_case.meets_spec is False
    assert r.rss.three_sigma == pytest.approx(0.6748399, **SEVEN_SF)
    assert r.rss.sigma == pytest.approx(0.2249466, **SEVEN_SF)
    assert [c.rss_contribution_pct for c in r.contributors] == pytest.approx(
        [0.1470926, 99.85291], **SEVEN_SF
    )
    assert r.rss.p_fail == pytest.approx(1.865106e-3, **SEVEN_SF)
    assert r.rss.cpl == pytest.approx(1.045468, **SEVEN_SF)
    assert r.rss.cpu == pytest.approx(1.029098, **SEVEN_SF)
    assert r.rss.cpk == pytest.approx(1.029098, **SEVEN_SF)


def bracket(alpha: float, n: int | None = None) -> VectorLoop:
    return make_loop(
        [
            LoopVector(length=var("a", 60.0, 0.1), angle=var("phi1", math.pi / 6, 0.004)),
            LoopVector(length=var("b", 40.0, 0.1), angle=var("phi2", -HALF_PI, 0.004)),
        ],
        alpha=alpha,
        usl=100.0,
        n=n,
    )


def test_two_link_bracket_x_distance_shows_relative_angle_coupling() -> None:
    """Two-link bracket, alpha = 0 (x-distance).

    a = 60 +/-0.1 at phi_1 = pi/6 +/-0.004; b = 40 +/-0.1 at phi_2 = -pi/2 +/-0.004.
    Theta_1 = 30 deg, Theta_2 = 30 - 90 = -60 deg.

    mean_Y     = 60 cos(30) + 40 cos(-60) = 51.96152 + 20 = 71.96152
    dY/da      = cos(30 deg)  = 0.8660254
    dY/dphi_1  = -(60 sin(30) + 40 sin(-60)) = -(30 - 34.64102) = +4.641016
                 (phi_1 rotates BOTH vectors; with absolute angles it would be
                  -60 sin(30) = -30: the conventions are not interchangeable)
    dY/db      = cos(-60 deg) = 0.5
    dY/dphi_2  = -40 sin(-60) = +34.64102
    WC half    = 0.08660254 + 0.01856406 + 0.05 + 0.1385641 = 0.2937307
    sigma_Y    = 0.05729517
    RSS contrib = 25.38533 %, 1.166454 %, 8.461776 %, 64.98644 %
    """
    res = analyze_loop(bracket(0.0))
    r = res.result
    assert r.worst_case is not None and r.rss is not None
    assert r.mean == pytest.approx(71.96152, **SEVEN_SF)
    assert sens(res) == pytest.approx([0.8660254, 4.641016, 0.5, 34.64102], **SEVEN_SF)
    assert sens(res)[1] != pytest.approx(-30.0, rel=0.5)  # not the absolute-angle value
    assert r.worst_case.half_range == pytest.approx(0.2937307, **SEVEN_SF)
    assert r.rss.sigma == pytest.approx(0.05729517, **SEVEN_SF)
    assert [c.rss_contribution_pct for c in r.contributors] == pytest.approx(
        [25.38533, 1.166454, 8.461776, 64.98644], **SEVEN_SF
    )
    assert [c.id for c in r.contributors] == ["a", "phi1", "b", "phi2"]


def test_two_link_bracket_y_distance() -> None:
    """Same bracket, alpha = pi/2 (y-distance).

    mean_Y     = 60 sin(30) + 40 sin(-60) = 30 - 34.64102 = -4.641016
    dY/da      = sin(30 deg)  = 0.5
    dY/dphi_1  = 60 cos(30) + 40 cos(-60) = 71.96152
    dY/db      = sin(-60 deg) = -0.8660254
    dY/dphi_2  = 40 cos(-60)  = 20.0
    WC half    = 0.05 + 0.2878461 + 0.08660254 + 0.08 = 0.5044486
    sigma_Y    = 0.1050161
    RSS contrib = 2.518755 %, 83.47697 %, 7.556266 %, 6.448013 %

    Cross-check: rotating the whole chain by phi_1 gives
    dY_x/dphi_1 = -Y_y and dY_y/dphi_1 = +Y_x.
    """
    res_y = analyze_loop(bracket(HALF_PI))
    res_x = analyze_loop(bracket(0.0))
    r = res_y.result
    assert r.worst_case is not None and r.rss is not None
    assert r.mean == pytest.approx(-4.641016, **SEVEN_SF)
    assert sens(res_y) == pytest.approx([0.5, 71.96152, -0.8660254, 20.0], **SEVEN_SF)
    assert r.worst_case.half_range == pytest.approx(0.5044486, **SEVEN_SF)
    assert r.rss.sigma == pytest.approx(0.1050161, **SEVEN_SF)
    assert [c.rss_contribution_pct for c in r.contributors] == pytest.approx(
        [2.518755, 83.47697, 7.556266, 6.448013], **SEVEN_SF
    )
    assert sens(res_x)[1] == pytest.approx(-res_y.result.mean, **EXACT)
    assert sens(res_y)[1] == pytest.approx(res_x.result.mean, **EXACT)


def test_constant_term_and_loop_value() -> None:
    """Y = constant + sum L cos(Theta - alpha): 3-4-5 triangle check.

    Vectors 3 (along +x) then 4 (relative +90 deg, i.e. along +y).
    x-projection = 3, y-projection = 4, projection on the 53.130102 deg
    direction of the resultant (atan2(4, 3)) = 5. With constant 0.5 -> 3.5.
    """
    assert loop_value([3.0, 4.0], [0.0, HALF_PI], 0.0) == pytest.approx(3.0, **EXACT)
    assert loop_value([3.0, 4.0], [0.0, HALF_PI], HALF_PI) == pytest.approx(4.0, **EXACT)
    assert loop_value([3.0, 4.0], [0.0, HALF_PI], math.atan2(4.0, 3.0)) == pytest.approx(
        5.0, **EXACT
    )
    assert loop_value([3.0, 4.0], [0.0, HALF_PI], 0.0, 0.5) == pytest.approx(3.5, **EXACT)
    loop = make_loop(
        [LoopVector(length=var("p", 3.0, 0.01), angle=0.0), LoopVector(length=4.0, angle=HALF_PI)],
        usl=4.0,
        constant=0.5,
    )
    res = analyze_loop(loop)
    assert res.result.mean == pytest.approx(3.5, **EXACT)
    assert res.result.constant == 0.5


# --------------------------------------------------------------------------- #
# Required test 4: analytic vs finite-difference sensitivities
# --------------------------------------------------------------------------- #


def test_fd_step_rule() -> None:
    """h = max(1e-6, 1e-4 t): t = 0.1 -> 1e-5; t = 0.004 -> floor 1e-6; t = 0 -> 1e-6."""
    assert fd_step(0.1) == pytest.approx(1e-5, rel=1e-12)
    assert fd_step(0.004) == 1e-6
    assert fd_step(0.0) == 1e-6


def test_analytic_and_fd_sensitivities_agree_on_the_bracket() -> None:
    """Bracket, alpha = 0: all four agree to 1e-6 relative.

    Y is linear in the lengths (no truncation error) and the angle steps are
    1e-6 rad (truncation ~ h^2/6 = 1.7e-13 relative), so the error is round-off,
    about eps*|Y|/h = 2.2e-16 * 72 / 1e-6 = 1.6e-8 absolute at worst.
    """
    loop = bracket(0.0)
    analytic = analytic_sensitivities(loop)
    fd = finite_difference_sensitivities(loop)
    for a, f in zip(analytic, fd, strict=True):
        assert f == pytest.approx(a, rel=1e-6)
    res = analyze_loop(loop)
    assert [v.sensitivity_fd for v in res.variables] == fd
    assert [v.fd_step for v in res.variables] == pytest.approx([1e-5, 1e-6, 1e-5, 1e-6])


finite = {"allow_nan": False, "allow_infinity": False}


@st.composite
def loops(draw: st.DrawFn) -> VectorLoop:
    n = draw(st.integers(min_value=1, max_value=4))
    vectors = []
    for j in range(n):
        length = draw(st.floats(min_value=1.0, max_value=100.0, **finite))
        angle = draw(st.floats(min_value=-math.pi, max_value=math.pi, **finite))
        t_len = draw(st.floats(min_value=1e-3, max_value=0.5, **finite))
        t_ang = draw(st.floats(min_value=1e-4, max_value=0.05, **finite))
        vectors.append(
            LoopVector(length=var(f"L{j}", length, t_len), angle=var(f"phi{j}", angle, t_ang))
        )
    alpha = draw(st.floats(min_value=-math.pi, max_value=math.pi, **finite))
    return make_loop(vectors, alpha=alpha, usl=1e6)


@given(loops())
def test_analytic_and_fd_sensitivities_agree_for_random_loops(loop: VectorLoop) -> None:
    """Analytic vs central finite difference: rel 1e-6 plus abs 1e-6 (spec edit E8).

    The absolute term is needed because a sensitivity can be (near) zero, where a
    relative error is undefined. Its size: round-off is about eps*|Y|/h; with
    |Y| <= 400 mm and h >= 1e-6 that is at most 9e-8, so 1e-6 leaves a 10x margin.
    Truncation for an angle is h^2/6 * |dY/dphi| with h <= 5e-6: below 5e-12 relative.
    """
    analytic = analytic_sensitivities(loop)
    fd = finite_difference_sensitivities(loop)
    assert len(analytic) == 2 * len(loop.vectors)
    for a, f in zip(analytic, fd, strict=True):
        assert abs(f - a) <= 1e-6 * abs(a) + 1e-6


# --------------------------------------------------------------------------- #
# Required test 5: linear-vs-MC consistency, and a documented divergence
# --------------------------------------------------------------------------- #


def test_linear_and_monte_carlo_agree_for_small_tolerances() -> None:
    """Small tolerances (pin, L = 100 +/-0.2, theta = 0.3 +/-0.006): linear ~ exact.

    Exact std of L sin(theta) = 0.1920800 vs linearised 0.1920803: they differ by
    1.7e-6 relative, about 940 times below the Monte Carlo sampling error at
    N = 200 000 (relative SE of the std = 1/sqrt(2N) = 0.158 %).
    Required: |std_MC - sigma_lin|/sigma_lin within sampling error (5 SE = 0.79 %),
    mean within 5 SE of Y(mu), and no linearisation warning.
    """
    loop = make_loop(
        [LoopVector(length=var("L", 100.0, 0.2), angle=var("theta", 0.3, 0.006))],
        alpha=HALF_PI,
        usl=31.0,
        n=200_000,
    )
    res = analyze_loop(loop)
    mc = res.result.monte_carlo
    assert mc is not None and res.result.rss is not None
    assert res.mc_std_rel_se == pytest.approx(1 / math.sqrt(2 * 199_999), rel=1e-12)
    assert res.mc_std_rel_diff is not None and abs(res.mc_std_rel_diff) < 5 * res.mc_std_rel_se
    assert mc.std == pytest.approx(0.1920803, rel=5 * res.mc_std_rel_se)
    assert res.mc_mean_shift is not None and res.mc_mean_se is not None
    assert abs(res.mc_mean_shift) < 5 * res.mc_mean_se
    assert res.mc_std_rel_diff == pytest.approx(
        (mc.std - res.result.rss.sigma) / 0.1920803, rel=1e-5
    )
    assert res.loop_warnings == []


def test_large_tolerance_divergence_proves_monte_carlo_uses_the_exact_function() -> None:
    """Documented divergence: pin, theta = 0 +/-0.9 rad (sigma_theta = 0.3 rad).

    Linearised: sigma_Y = 100 * 0.3 = 30.0.
    Exact:      std = 100 sqrt((1 - exp(-2*0.09))/2) = 100 sqrt(0.08236489) = 28.69928.
    The linear value is 4.5 % too high: about 30 Monte Carlo standard errors at
    N = 200 000. If Monte Carlo used the linearised function it would return 30.
    Also |Y| <= 100 always (the linear model has no such bound).
    """
    res = analyze_loop(pin_loop(t=0.9, n=200_000))
    mc = res.result.monte_carlo
    assert mc is not None and res.result.rss is not None
    assert res.result.rss.sigma == pytest.approx(30.0, **EXACT)
    assert mc.std == pytest.approx(28.69928, rel=0.01)  # exact value, 6 SE
    assert mc.std < 0.97 * res.result.rss.sigma  # clearly not the linear value
    assert res.mc_std_rel_diff == pytest.approx(-0.0434, abs=0.008)
    assert mc.min >= -100.0 and mc.max <= 100.0
    assert [w.code for w in res.loop_warnings] == ["LINEARISATION_SUSPECT"]


def test_zero_sensitivity_is_reported_not_hidden() -> None:
    """Pin measured along its own axis: Y = 100 cos(theta), theta = 0 +/-0.03 rad.

    Linearised: dY/dtheta = -100 sin(0) = 0 -> WC half = 0, sigma_Y = 0.
    Exact (s = 0.01): mean = 100 exp(-s^2/2) = 99.99500 (shift -0.004999875),
        std = 100 (1 - exp(-s^2))/sqrt(2) = 0.007070714,
        one-at-a-time excursion = 100 (1 - cos 0.03) = 0.04499663.
    The linear model is blind here; both loop warnings must fire and the 1D
    ZERO_VARIATION warning explains the missing P_fail/Cpk.
    """
    loop = make_loop([LoopVector(length=100.0, angle=var("theta", 0.0, 0.03))], lsl=99.9, n=200_000)
    res = analyze_loop(loop)
    r = res.result
    assert r.worst_case is not None and r.rss is not None and r.monte_carlo is not None
    assert sens(res) == pytest.approx([0.0], abs=1e-12)
    assert r.worst_case.half_range == 0.0 and r.rss.sigma == 0.0
    assert r.rss.p_fail is None and r.rss.cpk is None
    (v,) = res.variables
    assert v.linear_effect == 0.0
    assert v.exact_effect == pytest.approx(0.04499663, **SEVEN_SF)
    assert r.monte_carlo.std == pytest.approx(0.007070714, rel=0.02)
    assert r.monte_carlo.mean == pytest.approx(99.99500, abs=5 * 0.00707 / math.sqrt(200_000))
    assert res.mc_mean_shift == pytest.approx(-0.004999875, abs=5 * 0.00707 / math.sqrt(200_000))
    assert res.mc_std_rel_diff is None
    assert r.monte_carlo.max <= 100.0
    assert [w.code for w in res.loop_warnings] == ["ZERO_SENSITIVITY", "LINEARISATION_SUSPECT"]
    assert "ZERO_VARIATION" in [w.code for w in r.warnings]


# --------------------------------------------------------------------------- #
# Determinism, distributions, validation
# --------------------------------------------------------------------------- #


@settings(max_examples=10, deadline=None)
@given(loops(), st.integers(min_value=0, max_value=2**32 - 1))
def test_same_seed_gives_bit_identical_samples(loop: VectorLoop, seed: int) -> None:
    assert np.array_equal(sample_loop(loop, 500, seed), sample_loop(loop, 500, seed))


def test_without_monte_carlo_the_comparison_fields_are_empty() -> None:
    res = analyze_loop(bracket(0.0))
    assert res.result.monte_carlo is None
    assert res.mc_std_rel_diff is None and res.mc_std_rel_se is None
    assert res.mc_mean_shift is None and res.mc_mean_se is None


def test_uniform_angle_uses_the_uniform_sigma_and_stays_bounded() -> None:
    """theta uniform on 0.3 +/-0.006 rad: sigma_theta = 0.006/sqrt(3) = 0.003464102;
    sigma_Y = 100 cos(0.3) * 0.003464102 = 0.3309382 (L fixed).
    Samples of Y stay inside [100 sin(0.294), 100 sin(0.306)] = [28.97829, 30.12468].
    """
    loop = make_loop(
        [LoopVector(length=100.0, angle=var("theta", 0.3, 0.006, distribution="uniform"))],
        alpha=HALF_PI,
        usl=31.0,
        n=50_000,
    )
    res = analyze_loop(loop)
    r = res.result
    assert r.rss is not None and r.monte_carlo is not None
    assert r.contributors[0].sigma == pytest.approx(0.003464102, **SEVEN_SF)
    assert r.rss.sigma == pytest.approx(0.3309382, **SEVEN_SF)
    assert r.monte_carlo.min >= 28.97829 - 1e-5 and r.monte_carlo.max <= 30.12468 + 1e-5
    assert "NON_NORMAL_INPUT" in [w.code for w in r.warnings]


def test_duplicate_variable_ids_rejected() -> None:
    with pytest.raises(ValidationError, match="duplicate variable id"):
        make_loop(
            [
                LoopVector(length=var("x", 10.0, 0.1), angle=0.0),
                LoopVector(length=var("x", 10.0, 0.1), angle=0.0),
            ],
            usl=1.0,
        )


def test_loop_without_any_toleranced_variable_rejected() -> None:
    with pytest.raises(ValidationError, match="at least one length or angle"):
        make_loop([LoopVector(length=10.0, angle=0.0)], usl=1.0)


def test_variable_with_upper_below_lower_rejected() -> None:
    with pytest.raises(ValidationError, match="upper_tol"):
        LoopVariable(id="x", nominal=1.0, upper_tol=-0.1, lower_tol=0.1)


def test_empty_chain_and_unknown_fields_rejected() -> None:
    with pytest.raises(ValidationError):
        make_loop([], usl=1.0)
    with pytest.raises(ValidationError):
        LoopVector.model_validate({"length": 1.0, "angle": 0.0, "angle_deg": 30})
