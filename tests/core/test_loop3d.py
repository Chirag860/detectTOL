"""3D vector loops.

Conventions under test (docs/ASSUMPTIONS.md A16):

    M_j = Rz(yaw_j) Ry(pitch_j) Rx(roll_j);  R_j = R_{j-1} M_j;  d_j = R_j e_x
    Y   = constant + n . sum_j L_j d_j
    single vector: d = (cos psi cos beta, sin psi cos beta, -sin beta)

Every expected number is derived in the docstring and was re-derived by an
independent reviewer subagent (docs/reports/phase-3.md, 3D addendum).
SEVEN_SF = rel 1e-6 for rounded 7-figure values; EXACT = rel 1e-12 / abs 1e-12.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from detecttol.core.loop import LoopVariable, LoopVector, VectorLoop, analyze_loop
from detecttol.core.loop3d import (
    LoopVector3D,
    VectorLoop3D,
    analytic_sensitivities_3d,
    analyze_loop3d,
    finite_difference_sensitivities_3d,
    loop3d_value,
    rot_x,
    rot_y,
    rot_z,
    sample_loop3d,
)
from detecttol.core.models import AnalysisConfig, MonteCarloConfig, Requirement

EXACT = {"rel": 1e-12, "abs": 1e-12}
SEVEN_SF = {"rel": 1e-6}
DEG = math.pi / 180.0
X, Y, Z = (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)


def var(vid: str, nominal: float, t: float, **kw: Any) -> LoopVariable:
    return LoopVariable(id=vid, nominal=nominal, upper_tol=t, lower_tol=-t, **kw)


def make(
    vectors: list[LoopVector3D],
    n: tuple[float, float, float],
    *,
    usl: float = 1e6,
    mc: int | None = None,
    seed: int = 1,
) -> VectorLoop3D:
    analysis = (
        AnalysisConfig()
        if mc is None
        else AnalysisConfig(
            methods=["worst_case", "rss", "monte_carlo"],
            monte_carlo=MonteCarloConfig(n=mc, seed=seed),
        )
    )
    return VectorLoop3D(
        name="t3d",
        vectors=vectors,
        measure_direction=n,
        requirement=Requirement(usl=usl),
        analysis=analysis,
    )


def sens(loop: VectorLoop3D) -> list[float]:
    return [v.sensitivity_analytic for v in analyze_loop3d(loop).variables]


def test_rotation_matrices_follow_the_right_hand_rule() -> None:
    """Rz(90) e_x = e_y; Ry(90) e_x = -e_z (positive pitch tilts towards -z);
    Rx(90) e_y = e_z."""
    assert rot_z(90 * DEG) @ np.array(X) == pytest.approx(np.array(Y), abs=1e-15)
    assert rot_y(90 * DEG) @ np.array(X) == pytest.approx(-np.array(Z), abs=1e-15)
    assert rot_x(90 * DEG) @ np.array(Y) == pytest.approx(np.array(Z), abs=1e-15)


def single(n: tuple[float, float, float]) -> VectorLoop3D:
    return make(
        [
            LoopVector3D(
                length=var("L", 50.0, 0.1),
                yaw=var("yaw", 30 * DEG, 0.2 * DEG),
                pitch=var("pitch", 20 * DEG, 0.2 * DEG),
            )
        ],
        n,
    )


@pytest.mark.parametrize(
    ("n", "mean", "sensitivities", "wc", "sigma"),
    [
        (X, 40.68988, [0.8137977, -23.49232, -14.80991], 0.2150797, 0.04218975),
        (Y, 23.49232, [0.4698463, 40.68988, -8.550504], 0.2188660, 0.05085075),
        (Z, -17.10101, [-0.3420201, 0.0, -46.98463], 0.1982093, 0.05584520),
    ],
)
def test_single_vector_yaw_and_pitch(
    n: tuple[float, float, float], mean: float, sensitivities: list[float], wc: float, sigma: float
) -> None:
    """One vector, L = 50 +/-0.1, yaw 30 +/-0.2 deg, pitch 20 +/-0.2 deg.

    d = (cos30 cos20, sin30 cos20, -sin20) = (0.8137977, 0.4698463, -0.3420201)
    P = 50 d = (40.68988, 23.49232, -17.10101)
    dP/dL    = d
    dP/dyaw  = 50 (-sin30 cos20, cos30 cos20, 0)        = (-23.49232, 40.68988, 0)
    dP/dpitch= 50 (-cos30 sin20, -sin30 sin20, -cos20)  = (-14.80991, -8.550504, -46.98463)
    t_L = 0.1; t_angle = 0.2 deg = 0.003490659 rad; sigma = t/3.
    x: W = 0.08137977 + 23.49232*0.003490659 + 14.80991*0.003490659 = 0.2150797
       sigma = sqrt(0.02712659^2 + 0.02733455^2 + 0.01723218^2) = 0.04218975
    y: W = 0.2188660, sigma = 0.05085075;   z: W = 0.1982093, sigma = 0.05584520
    """
    res = analyze_loop3d(single(n))
    r = res.result
    assert r.worst_case is not None and r.rss is not None
    assert r.mean == pytest.approx(mean, **SEVEN_SF)
    assert [v.sensitivity_analytic for v in res.variables] == pytest.approx(
        sensitivities, rel=1e-6, abs=1e-12
    )
    assert r.worst_case.half_range == pytest.approx(wc, **SEVEN_SF)
    assert r.rss.sigma == pytest.approx(sigma, **SEVEN_SF)
    assert [v.kind for v in res.variables] == ["length", "angle", "pitch"]
    assert [v.unit for v in res.variables] == ["mm", "rad", "rad"]


def roll_case(n: tuple[float, float, float], mc: int | None = None) -> VectorLoop3D:
    return make(
        [
            LoopVector3D(length=30.0, roll=var("roll", 10 * DEG, 0.5 * DEG)),
            LoopVector3D(length=var("L2", 40.0, 0.05), yaw=90 * DEG),
        ],
        n,
        mc=mc,
    )


def test_roll_moves_only_the_downstream_vector() -> None:
    """Vector 1 (30 mm along x) rolls by rho = 10 +/-0.5 deg; vector 2 (40 +/-0.05)
    is yawed 90 deg from it.

    R_1 = Rx(rho) -> d_1 = e_x (unchanged by its own roll)
    d_2 = Rx(rho) Rz(90) e_x = Rx(rho) e_y = (0, cos rho, sin rho)
    P(rho) = (30, L2 cos rho, L2 sin rho)
    n = z: Y = 40 sin10 = 6.945927; dY/droll = 40 cos10 = 39.39231; dY/dL2 = sin10 = 0.1736482
           W = 39.39231*0.008726646 + 0.1736482*0.05 = 0.3524452; sigma = 0.1146241
    n = y: Y = 40 cos10 = 39.39231; dY/droll = -6.945927; dY/dL2 = 0.9848078
           W = 0.1098550; sigma = 0.02603150
    n = x: Y = 30 exactly, roll sensitivity 0, dY/dL2 = 0.
    """
    rz = analyze_loop3d(roll_case(Z))
    assert rz.result.worst_case is not None and rz.result.rss is not None
    assert rz.result.mean == pytest.approx(6.945927, **SEVEN_SF)
    assert [v.sensitivity_analytic for v in rz.variables] == pytest.approx(
        [39.39231, 0.1736482], **SEVEN_SF
    )
    assert rz.result.worst_case.half_range == pytest.approx(0.3524452, **SEVEN_SF)
    assert rz.result.rss.sigma == pytest.approx(0.1146241, **SEVEN_SF)
    assert [v.kind for v in rz.variables] == ["roll", "length"]

    ry = analyze_loop3d(roll_case(Y))
    assert ry.result.worst_case is not None and ry.result.rss is not None
    assert ry.result.mean == pytest.approx(39.39231, **SEVEN_SF)
    assert [v.sensitivity_analytic for v in ry.variables] == pytest.approx(
        [-6.945927, 0.9848078], **SEVEN_SF
    )
    assert ry.result.worst_case.half_range == pytest.approx(0.1098550, **SEVEN_SF)
    assert ry.result.rss.sigma == pytest.approx(0.02603150, **SEVEN_SF)

    rx = analyze_loop3d(roll_case(X))
    assert rx.result.mean == pytest.approx(30.0, **EXACT)
    assert [v.sensitivity_analytic for v in rx.variables] == pytest.approx([0.0, 0.0], abs=1e-12)


def test_box_diagonal_3_4_12() -> None:
    """Vectors 3 (along x), 4 (yaw 90 -> along y), 12 (pitch -90 -> along +z,
    because negative pitch tilts up).  P = (3, 4, 12), |P| = 13.

    Y = 13 for n = (3,4,12)/13 (an un-normalised n = (3,4,12) must give the same),
    12 for n = z, 3 for n = x.
    With yaw_2 as a variable: dP/dyaw_2 = e_z x (4 e_y + 12 e_z) = (-4, 0, 0).
    """
    table = [[3.0, 0.0, 0.0, 0.0], [4.0, 90 * DEG, 0.0, 0.0], [12.0, 0.0, -90 * DEG, 0.0]]
    assert loop3d_value(table, np.array([3.0, 4.0, 12.0]) / 13.0) == pytest.approx(13.0, **EXACT)
    assert loop3d_value(table, np.array(Z)) == pytest.approx(12.0, **EXACT)
    assert loop3d_value(table, np.array(X)) == pytest.approx(3.0, **EXACT)
    assert loop3d_value(table, np.array(X), 0.5) == pytest.approx(3.5, **EXACT)

    def box(n: tuple[float, float, float]) -> VectorLoop3D:
        return make(
            [
                LoopVector3D(length=3.0),
                LoopVector3D(length=4.0, yaw=var("yaw2", 90 * DEG, 0.1 * DEG)),
                LoopVector3D(length=12.0, pitch=-90 * DEG),
            ],
            n,
        )

    assert analyze_loop3d(box((3.0, 4.0, 12.0))).result.mean == pytest.approx(13.0, **EXACT)
    assert sens(box(X)) == pytest.approx([-4.0], **EXACT)
    assert sens(box(Y)) == pytest.approx([0.0], abs=1e-12)
    assert sens(box(Z)) == pytest.approx([0.0], abs=1e-12)


def test_planar_3d_loop_reduces_to_the_2d_loop() -> None:
    """Bracket of the 2D tests (a = 60 at 30 deg, b = 40 at -90 deg relative),
    yaw only, n = +x: mean 71.96152; sensitivities 0.8660254, 4.641016, 0.5, 34.64102.
    The 3D engine must agree with the independent 2D engine to rounding."""
    spec = [("a", 60.0, "phi1", math.pi / 6), ("b", 40.0, "phi2", -math.pi / 2)]
    loop3 = make(
        [
            LoopVector3D(length=var(lid, length, 0.1), yaw=var(aid, angle, 0.004))
            for lid, length, aid, angle in spec
        ],
        X,
        mc=5000,
    )
    loop2 = VectorLoop(
        name="t3d",
        vectors=[
            LoopVector(length=var(lid, length, 0.1), angle=var(aid, angle, 0.004))
            for lid, length, aid, angle in spec
        ],
        requirement=Requirement(usl=1e6),
        analysis=loop3.analysis,
    )
    r3, r2 = analyze_loop3d(loop3), analyze_loop(loop2)
    assert r3.result.mean == pytest.approx(71.96152, **SEVEN_SF)
    assert [v.sensitivity_analytic for v in r3.variables] == pytest.approx(
        [0.8660254, 4.641016, 0.5, 34.64102], **SEVEN_SF
    )
    assert [v.sensitivity_analytic for v in r3.variables] == pytest.approx(
        [v.sensitivity_analytic for v in r2.variables], **EXACT
    )
    assert r3.result.rss is not None and r2.result.rss is not None
    assert r3.result.rss.sigma == pytest.approx(r2.result.rss.sigma, **EXACT)
    # Same seed, same sampling order -> the same Monte Carlo sample, to rounding.
    assert np.allclose(sample_loop3d(loop3, 5000, 1), _sample_2d(loop2), rtol=0, atol=1e-10)


def _sample_2d(loop: VectorLoop) -> np.ndarray[Any, Any]:
    from detecttol.core.loop import sample_loop

    return sample_loop(loop, 5000, 1)


finite = {"allow_nan": False, "allow_infinity": False}
angles = st.floats(min_value=-math.pi, max_value=math.pi, **finite)


@st.composite
def loops3d(draw: st.DrawFn) -> VectorLoop3D:
    count = draw(st.integers(min_value=1, max_value=3))
    vectors = []
    for j in range(count):
        vectors.append(
            LoopVector3D(
                length=var(f"L{j}", draw(st.floats(min_value=1.0, max_value=100.0, **finite)), 0.1),
                yaw=var(f"yaw{j}", draw(angles), 0.01),
                pitch=var(f"pitch{j}", draw(angles), 0.01),
                roll=var(f"roll{j}", draw(angles), 0.01),
            )
        )
    n = draw(
        st.tuples(
            st.floats(min_value=-1, max_value=1, **finite),
            st.floats(min_value=-1, max_value=1, **finite),
            st.floats(min_value=-1, max_value=1, **finite),
        ).filter(lambda v: math.sqrt(sum(c * c for c in v)) > 0.1)
    )
    return make(vectors, n)


@given(loops3d())
def test_analytic_and_fd_sensitivities_agree_for_random_3d_loops(loop: VectorLoop3D) -> None:
    """Analytic vs central finite difference: rel 1e-6 plus abs 1e-6.

    Round-off is about eps*|Y|/h <= 2.2e-16 * 300 / 1e-6 = 7e-8; the absolute term
    also covers sensitivities that are (near) zero, e.g. the roll of the last vector.
    """
    analytic = analytic_sensitivities_3d(loop)
    fd = finite_difference_sensitivities_3d(loop)
    assert len(analytic) == 4 * len(loop.vectors)
    for a, f in zip(analytic, fd, strict=True):
        assert abs(f - a) <= 1e-6 * abs(a) + 1e-6
    # The roll of the last vector never moves anything.
    assert analytic[-1] == pytest.approx(0.0, abs=1e-9)


def test_monte_carlo_uses_the_exact_3d_function() -> None:
    """Roll case, n = z: Y = L2 sin(rho). Direct sampling in the same order
    (roll first, then L2) must match per sample (abs 1e-10 mm: matrix products
    add a few ulp). Linear and Monte Carlo std agree within 5 standard errors."""
    n_samples, seed = 100_000, 3
    loop = roll_case(Z, mc=n_samples)
    y = sample_loop3d(loop, n_samples, seed)
    rng = np.random.default_rng(seed)
    rho = rng.normal(10 * DEG, 0.5 * DEG / 3.0, n_samples)
    length = rng.normal(40.0, 0.05 / 3.0, n_samples)
    assert np.allclose(y, length * np.sin(rho), rtol=0, atol=1e-10)
    res = analyze_loop3d(loop)
    assert res.mc_std_rel_diff is not None and res.mc_std_rel_se is not None
    assert abs(res.mc_std_rel_diff) < 5 * res.mc_std_rel_se
    assert res.loop_warnings == []


@settings(max_examples=10, deadline=None)
@given(loops3d(), st.integers(min_value=0, max_value=2**32 - 1))
def test_same_seed_gives_identical_3d_samples(loop: VectorLoop3D, seed: int) -> None:
    assert np.array_equal(sample_loop3d(loop, 300, seed), sample_loop3d(loop, 300, seed))


def test_validation() -> None:
    with pytest.raises(ValidationError, match="zero vector"):
        make([LoopVector3D(length=var("L", 1.0, 0.1))], (0.0, 0.0, 0.0))
    with pytest.raises(ValidationError, match="duplicate variable id"):
        make([LoopVector3D(length=var("L", 1.0, 0.1), yaw=var("L", 0.0, 0.1))], X)
    with pytest.raises(ValidationError, match="at least one length or angle"):
        make([LoopVector3D(length=1.0)], X)
    with pytest.raises(ValidationError):
        make([], X)
