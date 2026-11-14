"""Drawing standard (asme / iso / is) and tolerance classes in YAML input.

GD&T cases reuse the block stack of tests/gdt/test_gdt.py: block 20 +/-0.1 and
spacer 5 +/-0.05 (both +1, normal, cp 1), plus flatness 0.04 on the block top.

- Contained in the size (ASME default; ISO/IS with envelope (E)): the flatness
  adds nothing. W = 0.1 + 0.05 = 0.15; (3 sigma)^2 = 0.01 + 0.0025 = 0.0125,
  sigma = sqrt(0.0125)/3 = 0.03726780.
- Not contained (ISO/IS default, independency): it adds 0 +/- 0.02.
  W = 0.17; (3 sigma)^2 = 0.0129, sigma = sqrt(0.0129)/3 = 0.03785939.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from detecttol import analyze
from detecttol.cli.main import app
from detecttol.core.models import Stack
from detecttol.gdt import (
    DatumReferenceFrame,
    Flatness,
    GdtStack,
    Parallelism,
    PlanarDatum,
    analyze_gdt,
)
from detecttol.io import StackInputError
from detecttol.io.yaml_loader import parse_stack
from detecttol.report import build_report, to_markdown
from tests.conftest import contributor, make_stack

EXACT = {"rel": 1e-12, "abs": 1e-15}
SEVEN_SF = {"rel": 1e-6}
A = DatumReferenceFrame(primary="A")
runner = CliRunner()


def block_stack(standard: str | None = None) -> Any:
    stack = make_stack(
        [contributor("block", 20.0, 0.1, -0.1, 1.0), contributor("spacer", 5.0, 0.05, -0.05, 1.0)],
        usl=25.2,
    )
    return Stack.model_validate({**stack.model_dump(), "standard": standard})


def _wc_sigma(gdt: GdtStack) -> tuple[float, float]:
    r = analyze_gdt(gdt)
    assert r.worst_case is not None and r.rss is not None
    return r.worst_case.half_range, r.rss.sigma


@pytest.mark.parametrize("standard", ["iso", "is"])
def test_iso_and_is_add_flatness_by_default(standard: str) -> None:
    gdt = GdtStack(
        stack=block_stack(), callouts=[Flatness(id="f", tolerance=0.04)], standard=standard
    )  # type: ignore[arg-type]
    half, sigma = _wc_sigma(gdt)
    assert half == pytest.approx(0.17, **EXACT)
    assert sigma == pytest.approx(0.03785939, **SEVEN_SF)
    assert analyze_gdt(gdt).standard == standard


def test_asme_contains_flatness_by_default() -> None:
    gdt = GdtStack(
        stack=block_stack(), callouts=[Flatness(id="f", tolerance=0.04)], standard="asme"
    )
    half, sigma = _wc_sigma(gdt)
    assert half == pytest.approx(0.15, **EXACT)
    assert sigma == pytest.approx(0.03726780, **SEVEN_SF)
    assert "STANDARD_ASSUMED" not in [w.code for w in analyze_gdt(gdt).warnings]


def test_envelope_restores_containment_under_iso() -> None:
    callout = Flatness(id="f", tolerance=0.04, envelope=True)
    half, sigma = _wc_sigma(GdtStack(stack=block_stack(), callouts=[callout], standard="is"))
    assert half == pytest.approx(0.15, **EXACT)
    assert sigma == pytest.approx(0.03726780, **SEVEN_SF)


def test_within_size_false_adds_under_every_standard() -> None:
    for standard in ("asme", "iso", "is"):
        callout = Flatness(id="f", tolerance=0.04, within_size=False)
        half, _ = _wc_sigma(GdtStack(stack=block_stack(), callouts=[callout], standard=standard))  # type: ignore[arg-type]
        assert half == pytest.approx(0.17, **EXACT)


def test_within_size_true_without_envelope_is_refused_under_iso() -> None:
    with pytest.raises(ValidationError, match="envelope requirement"):
        GdtStack(
            stack=block_stack(),
            callouts=[Flatness(id="f", tolerance=0.04, within_size=True)],
            standard="iso",
        )
    with pytest.raises(ValidationError, match="envelope requirement"):
        GdtStack(
            stack=block_stack(),
            datums=[PlanarDatum(label="A")],
            callouts=[Parallelism(id="p", tolerance=0.04, datums=A, within_size=True)],
            standard="is",
        )


def test_parallelism_under_iso() -> None:
    """within_size=True + envelope: contained (W 0.15); within_size=False: +/-0.02 (W 0.17)."""
    datums = [PlanarDatum(label="A")]
    inside = Parallelism(id="p", tolerance=0.04, datums=A, within_size=True, envelope=True)
    outside = Parallelism(id="p", tolerance=0.04, datums=A, within_size=False)
    for callout, expected in ((inside, 0.15), (outside, 0.17)):
        gdt = GdtStack(stack=block_stack(), datums=datums, callouts=[callout], standard="iso")
        assert _wc_sigma(gdt)[0] == pytest.approx(expected, **EXACT)


def test_unstated_standard_assumes_asme_and_says_so() -> None:
    gdt = GdtStack(stack=block_stack(), callouts=[Flatness(id="f", tolerance=0.04)])
    r = analyze_gdt(gdt)
    assert r.worst_case is not None and r.worst_case.half_range == pytest.approx(0.15, **EXACT)
    assert r.standard is None
    assert r.warnings[0].code == "STANDARD_ASSUMED" and "f" in r.warnings[0].message
    # nothing depends on the standard -> no warning
    plain = GdtStack(
        stack=block_stack(), callouts=[Flatness(id="f", tolerance=0.04, within_size=False)]
    )
    assert "STANDARD_ASSUMED" not in [w.code for w in analyze_gdt(plain).warnings]


def test_standard_taken_from_the_stack_and_conflict_refused() -> None:
    gdt = GdtStack(stack=block_stack(standard="is"), callouts=[Flatness(id="f", tolerance=0.04)])
    assert gdt.effective_standard == "is"
    assert _wc_sigma(gdt)[0] == pytest.approx(0.17, **EXACT)
    with pytest.raises(ValidationError, match=r"differs from stack.standard"):
        GdtStack(stack=block_stack(standard="is"), standard="asme")


# --- YAML input: standard, tolerance_class -------------------------------------


def _doc(contributors: list[dict[str, Any]], **top: Any) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "units": "mm",
        "name": "t",
        "requirement": {"lsl": 0.0},
        "contributors": contributors,
        **top,
    }


def test_h7_h7_fit_from_classes() -> None:
    """Clearance Y = hole - shaft, hole 25 H7 (+0.021/0), shaft 25 h7 (0/-0.021).

    Means 25.0105 and 24.9895 -> mean Y = 0.021; W = 0.0105 + 0.0105 = 0.021
    -> worst-case range [0, 0.042], the textbook H7/h7 clearance.
    """
    stack = parse_stack(
        _doc(
            [
                {"id": "hole", "nominal": 25.0, "tolerance_class": "H7", "sensitivity": 1.0},
                {"id": "shaft", "nominal": 25.0, "tolerance_class": "h7", "sensitivity": -1.0},
            ],
            standard="is",
        )
    )
    r = analyze(stack)
    assert r.standard == "is"
    assert r.mean == pytest.approx(0.021, abs=1e-12)
    assert r.worst_case is not None
    assert (r.worst_case.lower, r.worst_case.upper) == pytest.approx((0.0, 0.042), abs=1e-12)
    codes = [w.code for w in r.warnings]
    assert "TOLERANCE_FROM_TABLE" in codes and "TABLE_NOT_VERIFIED" in codes
    text = to_markdown(build_report(r, version="0", generated_at="2026-01-01T00:00:00Z"))
    assert "- Drawing standard: Indian Standards: IS 12160:2015 = ISO 8015:2011" in text
    assert "hole: IS 919 / ISO 286 H7 hole (above 18 up to 30 mm)" in text


def test_general_tolerance_golden_case_a_geometry() -> None:
    """Golden case A geometry with IS 2102-m instead of the drawing tolerances.

    slot 50 -> over 30 up to 120 -> +/-0.3; plates 16.6 -> over 6 up to 30 -> +/-0.2.
    mean = 50 - 3*16.6 = 0.2; W = 0.3 + 3*0.2 = 0.9 -> [-0.7, 1.1]
    (3 sigma)^2 = 0.09 + 3*0.04 = 0.21 -> sigma = sqrt(0.21)/3 = 0.1527525
    """
    plates = [
        {"id": f"plate_{k}", "nominal": 16.6, "tolerance_class": "general", "sensitivity": -1.0}
        for k in (1, 2, 3)
    ]
    slot = {"id": "slot", "nominal": 50.0, "tolerance_class": "general", "sensitivity": 1.0}
    r = analyze(parse_stack(_doc([slot, *plates], general_tolerance="m")))
    assert r.worst_case is not None and r.rss is not None
    assert r.worst_case.half_range == pytest.approx(0.9, **EXACT)
    assert r.rss.sigma == pytest.approx(0.1527525, **SEVEN_SF)
    assert "TABLE_NOT_VERIFIED" not in [w.code for w in r.warnings]
    assert r.standard is None


@pytest.mark.parametrize(
    ("contributors", "top", "message"),
    [
        (
            [{"id": "a", "nominal": 10.0, "tolerance_class": "general", "sensitivity": 1.0}],
            {},
            "contributors[0].tolerance_class: tolerance_class 'general' needs general_tolerance",
        ),
        (
            [{"id": "a", "nominal": 10.0, "tolerance_class": "H7", "upper_tol": 0.1,
              "sensitivity": 1.0}],
            {},
            "contributors[0].tolerance_class: give either tolerance_class or upper_tol",
        ),
        (
            [{"id": "a", "nominal": 10.0, "upper_tol": 0.1, "lower_tol": -0.1,
              "tolerance_source": "made up", "sensitivity": 1.0}],
            {},
            "contributors[0].tolerance_source: set by detectTOL",
        ),
        (
            [{"id": "a", "nominal": -10.0, "tolerance_class": "H7", "sensitivity": 1.0}],
            {},
            "basic size must be > 0",
        ),
        (
            [{"id": "a", "nominal": 10.0, "tolerance_class": "g6", "sensitivity": 1.0}],
            {},
            "fundamental deviation 'g' is not available",
        ),
        (
            [{"id": "a", "nominal": 10.0, "upper_tol": 0.1, "lower_tol": -0.1,
              "sensitivity": 1.0}],
            {"general_tolerance": "x"},
            "general_tolerance: must be one of f, m, c, v",
        ),
        (
            [{"id": "a", "nominal": 10.0, "upper_tol": 0.1, "lower_tol": -0.1,
              "sensitivity": 1.0}],
            {"standard": "din"},
            "standard:",
        ),
    ],
)  # fmt: skip
def test_yaml_errors(contributors: list[dict[str, Any]], top: dict[str, Any], message: str) -> None:
    with pytest.raises(StackInputError) as info:
        parse_stack(_doc(contributors, **top))
    assert any(message in e for e in info.value.errors), info.value.errors


def test_report_has_no_standard_line_when_not_stated() -> None:
    r = analyze(block_stack())
    text = to_markdown(build_report(r, version="0", generated_at="2026-01-01T00:00:00Z"))
    assert "Drawing standard" not in text


def test_cli_limits() -> None:
    ok = runner.invoke(app, ["limits", "25", "H7"])
    assert ok.exit_code == 0
    assert "upper +0.021 mm, lower +0 mm" in ok.output and "not yet been checked" in ok.output
    gen = runner.invoke(app, ["limits", "25", "general", "--general", "m"])
    assert (
        gen.exit_code == 0 and "+/-0.2" in gen.output and "not yet been checked" not in gen.output
    )
    bad = runner.invoke(app, ["limits", "25", "g6"])
    assert bad.exit_code == 2
