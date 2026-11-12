"""Property-based tests (hypothesis) required by root.md, Phase 1."""

from __future__ import annotations

from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from detecttol import analyze
from tests.conftest import contributor, make_stack

finite = {"allow_nan": False, "allow_infinity": False}
nominals = st.floats(min_value=-1000.0, max_value=1000.0, **finite)
tolerances = st.floats(min_value=1e-4, max_value=5.0, **finite)
sensitivities = st.floats(min_value=0.01, max_value=10.0, **finite).flatmap(
    lambda v: st.sampled_from([v, -v])
)
distributions = st.sampled_from(["normal", "uniform", "truncated_normal"])


@st.composite
def contributors(
    draw: st.DrawFn,
    *,
    dists: st.SearchStrategy[str] = distributions,
    cps: st.SearchStrategy[float] = st.floats(min_value=0.3, max_value=3.0, **finite),
    min_size: int = 1,
    max_size: int = 8,
) -> list[dict[str, Any]]:
    n = draw(st.integers(min_value=min_size, max_value=max_size))
    out = []
    for i in range(n):
        upper = draw(tolerances)
        lower = -draw(tolerances) if draw(st.booleans()) else upper - draw(tolerances)
        out.append(
            contributor(
                f"c{i}", draw(nominals), upper, lower, draw(sensitivities), draw(dists), draw(cps)
            )
        )
    return out


@given(
    contributors(
        dists=st.sampled_from(["normal", "truncated_normal"]),
        cps=st.floats(min_value=1.0, max_value=3.0, **finite),
    )
)
def test_worst_case_bounds_rss_for_capable_normal_stacks(cs: list[dict[str, Any]]) -> None:
    """WC half-range >= RSS 3-sigma half-range when every contributor is normal or
    truncated_normal with cp >= 1 (3 sigma_i <= t_i and the 2-norm <= the 1-norm).

    Compared with an absolute slack of 1e-12 * WC, not strict >=: for a single
    contributor with cp = 1 the two are mathematically equal.
    """
    r = analyze(make_stack(cs, lsl=0.0))
    assert r.worst_case is not None and r.rss is not None
    assert r.rss.three_sigma <= r.worst_case.half_range * (1 + 1e-12)
    assert "RSS_EXCEEDS_WORST_CASE" not in [w.code for w in r.warnings]


def test_worst_case_bound_does_not_hold_for_uniform_or_low_cp() -> None:
    """Counter-examples (Phase R audit, item 16): the bound is NOT universal.

    One uniform contributor: 3 sigma = 3 t/sqrt(3) = 1.732 t > t.
    One normal contributor with cp = 0.5: 3 sigma = t/0.5 = 2 t > t.
    Both must raise the RSS_EXCEEDS_WORST_CASE warning.
    """
    for dist, cp, ratio in (("uniform", 1.0, 3**0.5), ("normal", 0.5, 2.0)):
        r = analyze(make_stack([contributor("d", 10.0, 0.2, -0.2, 1.0, dist, cp)], lsl=0.0))
        assert r.worst_case is not None and r.rss is not None
        assert r.rss.three_sigma / r.worst_case.half_range == pytest.approx(ratio, rel=1e-12)
        assert "RSS_EXCEEDS_WORST_CASE" in [w.code for w in r.warnings]


@given(contributors())
def test_contributions_sum_to_100(cs: list[dict[str, Any]]) -> None:
    """Each contribution set sums to 100 % within 1e-9 (percentage points)."""
    r = analyze(make_stack(cs, lsl=0.0))
    wc = [c.wc_contribution_pct for c in r.contributors]
    rss = [c.rss_contribution_pct for c in r.contributors]
    assert all(v is not None and v >= 0.0 for v in wc + rss)
    assert sum(v for v in wc if v is not None) == pytest.approx(100.0, abs=1e-9)
    assert sum(v for v in rss if v is not None) == pytest.approx(100.0, abs=1e-9)


@given(contributors())
def test_flipping_sensitivities_negates_mean_keeps_sigma(cs: list[dict[str, Any]]) -> None:
    """a_i -> -a_i for all i (constant = 0): mu_Y -> -mu_Y; sigma_Y and WC unchanged.

    Exact in floating point: negation is exact and the sums are order-preserving.
    """
    flipped = [{**c, "sensitivity": -c["sensitivity"]} for c in cs]
    r1 = analyze(make_stack(cs, lsl=0.0))
    r2 = analyze(make_stack(flipped, lsl=0.0))
    assert r1.rss is not None and r2.rss is not None
    assert r1.worst_case is not None and r2.worst_case is not None
    assert r2.mean == pytest.approx(-r1.mean, rel=1e-12, abs=1e-12)
    assert r2.rss.sigma == pytest.approx(r1.rss.sigma, rel=1e-12)
    assert r2.worst_case.half_range == pytest.approx(r1.worst_case.half_range, rel=1e-12)


@given(contributors(), st.floats(min_value=0.01, max_value=100.0, **finite))
def test_scaling_tolerances_scales_sigma_and_worst_case(cs: list[dict[str, Any]], k: float) -> None:
    """Multiplying every upper_tol and lower_tol by k > 0 scales sigma_Y and the
    WC half-range by k (t_i and sigma_i are linear in the tolerances).

    rel = 1e-9: the scaled tolerances are re-rounded floats, so a few ulp of
    difference per term is expected.
    """
    scaled = [{**c, "upper_tol": k * c["upper_tol"], "lower_tol": k * c["lower_tol"]} for c in cs]
    r1 = analyze(make_stack(cs, lsl=0.0))
    r2 = analyze(make_stack(scaled, lsl=0.0))
    assert r1.rss is not None and r2.rss is not None
    assert r1.worst_case is not None and r2.worst_case is not None
    assert r2.rss.sigma == pytest.approx(k * r1.rss.sigma, rel=1e-9)
    assert r2.worst_case.half_range == pytest.approx(k * r1.worst_case.half_range, rel=1e-9)


@given(nominals, tolerances, st.sampled_from([1.0, -1.0]))
def test_single_normal_contributor_wc_equals_rss(nominal: float, t: float, a: float) -> None:
    """One contributor, normal, cp = 1, |a| = 1: WC half-range = t and RSS 3 sigma = t."""
    r = analyze(make_stack([contributor("d", nominal, t, -t, a)], lsl=0.0))
    assert r.worst_case is not None and r.rss is not None
    assert r.worst_case.half_range == pytest.approx(t, rel=1e-12)
    assert r.rss.three_sigma == pytest.approx(t, rel=1e-12)


@settings(max_examples=8, deadline=None)
@given(
    contributors(
        dists=st.just("normal"),
        cps=st.floats(min_value=0.5, max_value=2.0, **finite),
        max_size=5,
    ),
    st.integers(min_value=0, max_value=2**32 - 1),
)
def test_monte_carlo_std_matches_rss_for_linear_normal_stacks(
    cs: list[dict[str, Any]], seed: int
) -> None:
    """MC std is within 2 % of RSS sigma for linear normal stacks at N = 200 000.

    Relative SE of a normal sample std = 1/sqrt(2N) = 0.158 %, so 2 % is about
    12.6 SE: a failure means a real defect, not sampling noise.
    """
    r = analyze(make_stack(cs, lsl=0.0, n=200_000, seed=seed))
    assert r.rss is not None and r.monte_carlo is not None
    assert r.monte_carlo.std == pytest.approx(r.rss.sigma, rel=0.02)


@settings(max_examples=15, deadline=None)
@given(contributors(max_size=4), st.integers(min_value=0, max_value=2**32 - 1))
def test_same_seed_gives_identical_result(cs: list[dict[str, Any]], seed: int) -> None:
    """Same seed and input -> bit-identical Monte Carlo result (model equality)."""
    stack = make_stack(cs, lsl=0.0, n=2_000, seed=seed)
    assert analyze(stack).monte_carlo == analyze(stack).monte_carlo
