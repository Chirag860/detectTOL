"""Phase 4: GD&T subset. Hand-derived cases for every supported type.

Conventions under test (docs/ASSUMPTIONS.md A17-A22; all NEED HUMAN REVIEW):

    flatness / parallelism, zone t   -> contributor 0 +/- t/2
    position RFS, zone diameter T    -> contributor 0 +/- T/2, normal, sigma = T/(6 cp)
    position MMC/LMC                 -> zone T + B, B = |size - MMC (LMC) size|
                                        delta = (T + B)/(6 cp) * z
    perpendicularity / angularity    -> angle +/- atan(t / feature_length)

Every number is derived in the docstring and was re-derived by an independent
reviewer subagent (docs/reports/phase-4.md). SEVEN_SF = rel 1e-6.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pytest
from pydantic import ValidationError
from scipy.stats import norm

from detecttol import analyze
from detecttol.core.loop import LoopVector, VectorLoop, analyze_loop
from detecttol.core.models import Requirement
from detecttol.gdt import (
    DatumReferenceFrame,
    Flatness,
    GdtStack,
    Orientation,
    Parallelism,
    PlanarDatum,
    Position,
    analyze_gdt,
    sample_gdt_stack,
)
from tests.conftest import contributor, make_stack

EXACT = {"rel": 1e-12, "abs": 1e-15}
SEVEN_SF = {"rel": 1e-6}
A = DatumReferenceFrame(primary="A")
DATUMS = [PlanarDatum(label="A"), PlanarDatum(label="B"), PlanarDatum(label="C")]


def block_stack(**kw: Any) -> Any:
    return make_stack(
        [contributor("block", 20.0, 0.1, -0.1, 1.0), contributor("spacer", 5.0, 0.05, -0.05, 1.0)],
        usl=25.2,
        **kw,
    )


def test_flatness_adds_a_half_zone_contributor() -> None:
    """Y = block + spacer + flatness deviation; block 20 +/-0.1, spacer 5 +/-0.05,
    flatness 0.04 on the block top -> contributor 0 +/-0.02 (sigma 0.006666667).

    mean_Y = 25.0;  W = 0.1 + 0.05 + 0.02 = 0.17
    (3 sigma)^2 = 0.1^2 + 0.05^2 + 0.02^2 = 0.0129 -> 3 sigma = 0.1135782, sigma = 0.03785939
    RSS % = 0.01/0.0129 = 77.51938, 0.0025/0.0129 = 19.37984, 0.0004/0.0129 = 3.100775
    WC %  = 58.82353, 29.41176, 11.76471
    USL 25.2: z = 0.2/0.03785939 = 5.282705 -> P_fail = 6.364498e-8; Cpu = 1.760902
    """
    callout = Flatness(id="flat_top", tolerance=0.04)
    c = callout.to_contributor()
    assert (c.nominal, c.upper_tol, c.lower_tol, c.sensitivity) == (0.0, 0.02, -0.02, 1.0)
    assert c.sigma == pytest.approx(0.02 / 3, **EXACT)

    r = analyze_gdt(GdtStack(stack=block_stack(), callouts=[callout]))
    assert r.worst_case is not None and r.rss is not None
    assert r.mean == pytest.approx(25.0, **EXACT)
    assert r.worst_case.half_range == pytest.approx(0.17, **EXACT)
    assert r.rss.three_sigma == pytest.approx(0.1135782, **SEVEN_SF)
    assert r.rss.sigma == pytest.approx(0.03785939, **SEVEN_SF)
    assert [x.rss_contribution_pct for x in r.contributors] == pytest.approx(
        [77.51938, 19.37984, 3.100775], **SEVEN_SF
    )
    assert [x.wc_contribution_pct for x in r.contributors] == pytest.approx(
        [58.82353, 29.41176, 11.76471], **SEVEN_SF
    )
    assert r.rss.p_fail == pytest.approx(6.364498e-8, **SEVEN_SF)
    assert r.rss.p_fail == pytest.approx(float(norm.sf(0.2 / (math.sqrt(0.0129) / 3))), rel=1e-9)
    assert r.rss.cpu == pytest.approx(1.760902, **SEVEN_SF)
    assert [x.id for x in r.contributors] == ["block", "spacer", "flat_top"]


def test_parallelism_uses_the_same_conversion() -> None:
    """Parallelism 0.06 to datum A -> contributor 0 +/-0.03 (sigma 0.01).
    W = 0.18; sigma = sqrt(0.1^2 + 0.05^2 + 0.03^2)/3 = sqrt(0.0134)/3 = 0.03858612;
    Cpu = 0.2/0.1157584 = 1.727737; P_fail = 1.090493e-7."""
    callout = Parallelism(id="par", tolerance=0.06, datums=A)
    r = analyze_gdt(GdtStack(stack=block_stack(), datums=DATUMS, callouts=[callout]))
    assert r.worst_case is not None and r.rss is not None
    assert r.worst_case.half_range == pytest.approx(0.18, **EXACT)
    assert r.rss.sigma == pytest.approx(0.03858612, **SEVEN_SF)
    assert r.rss.cpu == pytest.approx(1.727737, **SEVEN_SF)
    assert r.rss.p_fail == pytest.approx(1.090493e-7, **SEVEN_SF)


def test_flatness_distribution_and_sensitivity_are_respected() -> None:
    """Flatness 0.06 uniform, a = -2: contributor 0 +/-0.03, sigma = 0.03/sqrt(3) = 0.01732051."""
    c = Flatness(id="f", tolerance=0.06, sensitivity=-2.0, distribution="uniform").to_contributor()
    assert c.sensitivity == -2.0 and c.distribution == "uniform"
    assert c.sigma == pytest.approx(0.01732051, **SEVEN_SF)


def misalignment(mc: int | None = None) -> GdtStack:
    """Y = pos1 - pos2 with a fixed (zero-tolerance) reference dimension of 0."""
    stack = make_stack([contributor("ref", 0.0, 0.0, 0.0, 1.0)], lsl=-0.2, usl=0.2, n=mc, seed=4)
    frame = DatumReferenceFrame(primary="A", secondary="B", tertiary="C")
    return GdtStack(
        stack=stack,
        datums=DATUMS,
        callouts=[
            Position(id="pos1", tolerance=0.2, datums=frame),
            Position(id="pos2", tolerance=0.3, datums=frame, sensitivity=-1.0),
        ],
    )


def test_position_rfs_is_a_normal_with_half_the_zone_at_three_sigma() -> None:
    """Two holes, position 0.2 and 0.3 (diametral zones, RFS), Y = pos1 - pos2.

    pos1: 0 +/-0.1, sigma 0.03333333;  pos2: 0 +/-0.15, sigma 0.05
    mean_Y = 0;  W = 0.25;  sigma = sqrt(0.1^2 + 0.15^2)/3 = sqrt(0.0325)/3 = 0.06009252
    Spec +/-0.2: z = 3.328201 -> P_fail = 2 Phi(-3.328201) = 8.740872e-4; Cpk = 1.109400
    Monte Carlo (N = 200 000): std within 2 % (12 SE), failure fraction within
    5 SE of 8.74e-4 (SE = sqrt(p/N) = 6.6e-5).
    """
    r = analyze_gdt(misalignment(mc=200_000))
    assert r.worst_case is not None and r.rss is not None and r.monte_carlo is not None
    assert r.mean == pytest.approx(0.0, abs=1e-15)
    assert r.worst_case.half_range == pytest.approx(0.25, **EXACT)
    assert r.rss.sigma == pytest.approx(0.06009252, **SEVEN_SF)
    assert r.rss.p_fail == pytest.approx(8.740872e-4, **SEVEN_SF)
    assert r.rss.cpk == pytest.approx(1.109400, **SEVEN_SF)
    assert r.contributors[1].sigma == pytest.approx(0.2 / 6, **EXACT)
    assert r.contributors[2].sigma == pytest.approx(0.3 / 6, **EXACT)
    assert r.monte_carlo.std == pytest.approx(0.06009252, rel=0.02)
    assert r.monte_carlo.fraction_fail == pytest.approx(8.740872e-4, abs=5 * 6.6e-5)


def bonus_stack(
    condition: str, feature: str = "hole", mc: int | None = None, cp: float = 1.0
) -> GdtStack:
    """Y = positional deviation only (the size has sensitivity 0), spec +/-0.15.
    Hole 10.0 +0.2/-0.0 or pin 8.0 +0.0/-0.1."""
    if feature == "hole":
        size = contributor("size", 10.0, 0.2, 0.0, 0.0)
        tol = 0.2
    else:
        size = contributor("size", 8.0, 0.0, -0.1, 0.0)
        tol = 0.1
    stack = make_stack([size], lsl=-0.15, usl=0.15, n=mc, seed=9)
    kw: dict[str, Any] = {}
    if condition != "RFS":
        kw = {"feature": feature, "size_contributor": "size"}
    return GdtStack(
        stack=stack,
        datums=DATUMS,
        callouts=[
            Position(id="pos", tolerance=tol, datums=A, material_condition=condition, cp=cp, **kw)
        ],
    )


def test_position_mmc_hole_reference_size_sigma_and_worst_case() -> None:
    """Hole 10.0 +0.2/-0.0: mu_s = 10.1, t_s = 0.1, sigma_s = 0.03333333.
    MMC size (smallest hole) = 10.0. Position T = 0.2 at MMC.

    Worst-case half-range = (T + size range)/2 = (0.2 + 0.2)/2 = 0.2
    B = |s - 10.0|, s - 10.0 ~ N(0.1, 0.03333333^2) (fold at -3 sigma):
        E[B]   = 0.1 (1 - 2 Phi(-3)) + 2 sigma_s phi(3) = 0.09973002 + 0.00029546 = 0.1000255
        E[B^2] = 0.1^2 + sigma_s^2 = 0.01111111
        E[(T+B)^2] = 0.04 + 2*0.2*0.1000255 + 0.01111111 = 0.09112130
    sigma_delta = sqrt(0.09112130)/6 = 0.05031051
        (0.05030770 if the fold is ignored; RFS would be 0.2/6 = 0.03333333)
    """
    gdt = bonus_stack("MMC")
    pos = gdt.callouts[0]
    assert isinstance(pos, Position)
    size = gdt.size_of(pos)
    assert size is not None
    assert pos.reference_size(size) == pytest.approx(10.0, **EXACT)
    assert pos.bonus_sigma(size) == pytest.approx(0.05031051, **SEVEN_SF)
    c = pos.to_contributor(size)
    assert c.half_range == pytest.approx(0.2, **EXACT)
    assert c.sigma == pytest.approx(0.05031051, **SEVEN_SF)

    r = analyze_gdt(gdt)
    assert r.worst_case is not None and r.rss is not None
    assert r.worst_case.half_range == pytest.approx(0.2, **EXACT)
    assert r.rss.sigma == pytest.approx(0.05031051, **SEVEN_SF)
    # Normal approximation with that sigma: 2 Phi(-0.15/0.05031051) = 2.868546e-3.
    assert r.rss.p_fail == pytest.approx(2.868546e-3, rel=1e-5)


def test_bonus_tolerance_raises_the_failure_rate_of_a_fixed_positional_limit() -> None:
    """The bonus-tolerance comparison of spec Phase 4 (edit E9, question Q12).

    Same hole and position callout, positional requirement +/-0.15, N = 400 000:
      RFS: sigma 0.03333333 -> P_fail = 2 Phi(-4.5) = 6.795346e-6
      MMC: exact mixture P_fail = E_s[2 Phi(-0.9/(0.2 + B))] = 3.814847e-3
           (the normal approximation, 2.868546e-3, is 25 % too low: heavier tails)
    The bonus enlarges the zone and the model lets the deviation fill it, so
    against a FIXED limit the failure rate goes UP (about 560x), not down.
    Monte Carlo tolerance for MMC: SE = sqrt(p/N) = 9.8e-5 -> 5 SE.
    """
    rfs = analyze_gdt(bonus_stack("RFS", mc=400_000))
    mmc = analyze_gdt(bonus_stack("MMC", mc=400_000))
    assert rfs.rss is not None and mmc.rss is not None
    assert rfs.monte_carlo is not None and mmc.monte_carlo is not None
    assert rfs.rss.p_fail == pytest.approx(6.795346e-6, **SEVEN_SF)
    assert mmc.monte_carlo.fraction_fail == pytest.approx(3.814847e-3, abs=5 * 9.8e-5)
    assert mmc.monte_carlo.std == pytest.approx(0.05031051, rel=0.02)
    assert rfs.monte_carlo.std == pytest.approx(0.2 / 6, rel=0.02)
    # Direction of the effect, with a wide margin (expected ratio ~560).
    assert mmc.monte_carlo.fraction_fail > 50 * max(rfs.monte_carlo.fraction_fail, 1e-5)
    assert mmc.monte_carlo.std > 1.3 * rfs.monte_carlo.std
    # RFS expects 400000 * 6.8e-6 = 2.7 failures: fewer than 15 is certain (p < 1e-6).
    assert rfs.monte_carlo.n_fail < 15


def test_position_lmc_hole_measures_the_bonus_from_the_largest_size() -> None:
    """LMC size of the hole = 10.2. B = |s - 10.2| with 10.2 - s ~ N(0.1, sigma_s^2):
    the same folded normal as at MMC, so sigma_delta = 0.05031051 again.
    The bonus now grows with SMALLER distance to 10.2, i.e. big holes get the big zone."""
    gdt = bonus_stack("LMC", mc=50_000)
    pos = gdt.callouts[0]
    assert isinstance(pos, Position)
    size = gdt.size_of(pos)
    assert size is not None
    assert pos.reference_size(size) == pytest.approx(10.2, **EXACT)
    assert pos.bonus_sigma(size) == pytest.approx(0.05031051, **SEVEN_SF)
    assert analyze_gdt(gdt).monte_carlo is not None


def test_position_mmc_pin_uses_the_largest_size() -> None:
    """Pin 8.0 +0.0/-0.1: mu_s = 7.95, t_s = 0.05, sigma_s = 0.01666667; MMC = 8.0.
    Position T = 0.1 at MMC: E[B] = 0.05001274;
    E[(T+B)^2] = 0.01 + 0.2*0.05001274 + (0.0025 + 0.000277778) = 0.02278033
    sigma_delta = sqrt(0.02278033)/6 = 0.02515525;  WC half-range = (0.1 + 0.1)/2 = 0.1.
    LMC of the pin = 7.9 (smallest)."""
    gdt = bonus_stack("MMC", feature="pin")
    pos = gdt.callouts[0]
    assert isinstance(pos, Position)
    size = gdt.size_of(pos)
    assert size is not None
    assert pos.reference_size(size) == pytest.approx(8.0, **EXACT)
    assert pos.bonus_sigma(size) == pytest.approx(0.02515525, **SEVEN_SF)
    assert pos.to_contributor(size).half_range == pytest.approx(0.1, **EXACT)
    lmc = bonus_stack("LMC", feature="pin").callouts[0]
    assert isinstance(lmc, Position)
    assert lmc.reference_size(size) == pytest.approx(7.9, **EXACT)


def test_bonus_sigma_for_a_bounded_size_distribution_and_cp() -> None:
    """Uniform size 10.0 +0.2/-0.0: s - 10.0 uniform on [0, 0.2], never negative.
    E[B] = 0.1; E[B^2] = 0.1^2 + 0.1^2/3 = 0.01333333
    E[(T+B)^2] = 0.04 + 0.04 + 0.01333333 = 0.09333333 -> sqrt = 0.3055050
    cp = 1: sigma = 0.3055050/6 = 0.05091751;  cp = 2: 0.02545875."""
    size = make_stack([contributor("size", 10.0, 0.2, 0.0, 0.0, "uniform")], usl=1.0).contributors[
        0
    ]
    for cp, expected in ((1.0, 0.05091751), (2.0, 0.02545875)):
        pos = Position(
            id="p",
            tolerance=0.2,
            datums=A,
            material_condition="MMC",
            feature="hole",
            size_contributor="size",
            cp=cp,
        )
        assert pos.bonus_sigma(size) == pytest.approx(expected, **SEVEN_SF)


def test_monte_carlo_bonus_uses_the_same_size_samples() -> None:
    """Reproduce the sampler by hand: size first, then z; delta = (T + |s - 10|)/6 * z."""
    gdt = bonus_stack("MMC", mc=1000)
    y = sample_gdt_stack(gdt, 1000, 9)
    rng = np.random.default_rng(9)
    s = rng.normal(10.1, 0.1 / 3.0, 1000)
    z = rng.standard_normal(1000)
    assert np.allclose(y, (0.2 + np.abs(s - 10.0)) / 6.0 * z, rtol=0, atol=1e-15)


def test_stack_without_callouts_equals_the_plain_engine() -> None:
    stack = block_stack(n=5000, seed=3)
    assert analyze_gdt(GdtStack(stack=stack)) == analyze(stack)


def test_perpendicularity_becomes_an_angle_tolerance_in_a_loop() -> None:
    """Wall = one vector of length 100 at 90 deg; perpendicularity 0.1 over a
    40 mm feature -> angle +/- atan(0.1/40) = 0.002499995 rad.

    Y = x of the tip = 100 cos(90 deg + d) = -100 sin d: dY/dangle = -100 mm/rad
    W = 100 * 0.002499995 = 0.2499995;  sigma = W/3 = 0.08333316
    Exact extreme = 100 sin(atan(0.0025)) = 0.25/sqrt(1 + 0.0025^2) = 0.2499992.
    """
    callout = Orientation(
        kind="perpendicularity", id="perp", tolerance=0.1, feature_length=40.0, datums=A
    )
    assert callout.angle_half_range() == pytest.approx(0.002499995, **SEVEN_SF)
    variable = callout.to_loop_variable(math.pi / 2)
    assert variable.nominal == math.pi / 2
    assert variable.upper_tol == -variable.lower_tol == callout.angle_half_range()
    loop = VectorLoop(
        name="wall",
        vectors=[LoopVector(length=100.0, angle=variable)],
        requirement=Requirement(lsl=-0.3, usl=0.3),
    )
    res = analyze_loop(loop)
    r = res.result
    assert r.worst_case is not None and r.rss is not None
    assert res.variables[0].sensitivity_analytic == pytest.approx(-100.0, **EXACT)
    assert r.worst_case.half_range == pytest.approx(0.2499995, **SEVEN_SF)
    assert r.rss.sigma == pytest.approx(0.08333316, **SEVEN_SF)
    assert res.variables[0].exact_effect == pytest.approx(0.2499992, **SEVEN_SF)
    assert r.mean == pytest.approx(0.0, abs=1e-12)


def test_angularity_uses_the_same_formula() -> None:
    """Angularity 0.05 over 20 mm: atan(0.0025) = 0.002499995 rad as well."""
    callout = Orientation(
        kind="angularity", id="ang", tolerance=0.05, feature_length=20.0, datums=A, cp=1.5
    )
    assert callout.angle_half_range() == pytest.approx(math.atan(0.0025), **EXACT)
    assert callout.to_loop_variable(0.5).cp == 1.5


# ---------------------------------------------------------------- validation


def test_datum_reference_frame_rules() -> None:
    assert DatumReferenceFrame(primary="A", secondary="B", tertiary="C").labels() == ("A", "B", "C")
    assert DatumReferenceFrame(primary="A").labels() == ("A",)
    with pytest.raises(ValidationError, match="without a secondary"):
        DatumReferenceFrame(primary="A", tertiary="C")
    with pytest.raises(ValidationError, match="distinct"):
        DatumReferenceFrame(primary="A", secondary="A")
    for bad in ("a", "A1", "", "ABC"):
        with pytest.raises(ValidationError):
            DatumReferenceFrame(primary=bad)


def test_callout_validation() -> None:
    with pytest.raises(ValidationError):
        Flatness(id="f", tolerance=0.0)
    with pytest.raises(ValidationError):
        Flatness.model_validate({"id": "f", "tolerance": 0.1, "datums": {"primary": "A"}})
    with pytest.raises(ValidationError):
        Parallelism.model_validate({"id": "p", "tolerance": 0.1})  # datum required
    with pytest.raises(ValidationError, match="feature and size_contributor are required"):
        Position(id="p", tolerance=0.1, datums=A, material_condition="MMC")
    with pytest.raises(ValidationError):
        Position.model_validate(
            {"id": "p", "tolerance": 0.1, "datums": {"primary": "A"}, "material_condition": "MMB"}
        )
    with pytest.raises(ValidationError):
        Orientation(kind="perpendicularity", id="o", tolerance=0.1, feature_length=0.0, datums=A)
    rfs = Position(id="p", tolerance=0.1, datums=A)
    with pytest.raises(ValueError, match="only defined for MMC / LMC"):
        rfs.reference_size(block_stack().contributors[0])
    mmc = Position(
        id="p",
        tolerance=0.1,
        datums=A,
        material_condition="MMC",
        feature="hole",
        size_contributor="s",
    )
    with pytest.raises(ValueError, match="size contributor is required"):
        mmc.to_contributor(None)


def test_gdt_stack_validation() -> None:
    stack = block_stack()
    with pytest.raises(ValidationError, match="undeclared datum"):
        GdtStack(stack=stack, callouts=[Parallelism(id="p", tolerance=0.1, datums=A)])
    with pytest.raises(ValidationError, match="duplicate label"):
        GdtStack(stack=stack, datums=[PlanarDatum(label="A"), PlanarDatum(label="A")])
    with pytest.raises(ValidationError, match="not unique"):
        GdtStack(stack=stack, callouts=[Flatness(id="block", tolerance=0.1)])
    with pytest.raises(ValidationError, match="not unique"):
        GdtStack(
            stack=stack,
            callouts=[Flatness(id="f", tolerance=0.1), Flatness(id="f", tolerance=0.2)],
        )
    with pytest.raises(ValidationError, match="is not a contributor"):
        GdtStack(
            stack=stack,
            datums=DATUMS,
            callouts=[
                Position(
                    id="p",
                    tolerance=0.1,
                    datums=A,
                    material_condition="MMC",
                    feature="hole",
                    size_contributor="nope",
                )
            ],
        )
