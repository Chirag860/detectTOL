"""Direct tests of the closed-form helpers, including their error paths."""

from __future__ import annotations

import pytest

from detecttol.core import linear


def test_normal_p_fail_hand_values() -> None:
    """Standard normal reference points (mu = 0, sigma = 1).

    Phi(-3) = 0.001349898 -> two-sided +/-3: 0.002699796; one-sided: 0.001349898.
    A missing limit contributes nothing.
    """
    assert linear.normal_p_fail(0.0, 1.0, -3.0, 3.0) == pytest.approx(0.002699796, rel=1e-6)
    assert linear.normal_p_fail(0.0, 1.0, -3.0, None) == pytest.approx(0.001349898, rel=1e-6)
    assert linear.normal_p_fail(0.0, 1.0, None, 3.0) == pytest.approx(0.001349898, rel=1e-6)


def test_upper_tail_keeps_precision_far_out() -> None:
    """1 - Phi(8) = 6.220961e-16: below double-precision resolution of 1 - cdf,
    so the survival function must be used (a naive 1 - cdf returns 0 or 1.1e-16)."""
    assert linear.normal_p_fail(0.0, 1.0, None, 8.0) == pytest.approx(6.220961e-16, rel=1e-6)


def test_capability_hand_values() -> None:
    """mu = 10, sigma = 0.5, LSL = 8, USL = 13:
    Cpl = 2/1.5 = 1.333333, Cpu = 3/1.5 = 2.0, Cpk = 1.333333."""
    cpl, cpu, cpk = linear.capability(10.0, 0.5, 8.0, 13.0)
    assert cpl == pytest.approx(4.0 / 3.0, rel=1e-12)
    assert cpu == pytest.approx(2.0, rel=1e-12)
    assert cpk == pytest.approx(4.0 / 3.0, rel=1e-12)


def test_sigma_must_be_positive() -> None:
    with pytest.raises(ValueError, match="sigma must be > 0"):
        linear.normal_p_fail(0.0, 0.0, -1.0, 1.0)
    with pytest.raises(ValueError, match="sigma must be > 0"):
        linear.capability(0.0, 0.0, -1.0, 1.0)


def test_capability_needs_a_limit() -> None:
    with pytest.raises(ValueError, match="at least one of lsl / usl"):
        linear.capability(0.0, 1.0, None, None)


def test_within_spec_with_and_without_tolerance() -> None:
    assert linear.within_spec(1.0, 1.0, 2.0)
    assert not linear.within_spec(1.0 - 1e-12, 1.0, 2.0)
    assert linear.within_spec(1.0 - 1e-12, 1.0, 2.0, abs_tol=1e-9)
    assert not linear.within_spec(2.1, None, 2.0)
    assert linear.within_spec(-1e9, None, 2.0)
