"""Stacks straight from a CAD model: combining a part's dimensions, missing ones, STEP PMI.

Geometry: examples/step/plate_stack.step (golden case A). HOUSING faces along z:
bottom 4 (z = 0), slot floor 8 (z = 10), slot ceiling 6 (z = 60), top 2 (z = 70).
Plates 16.6 thick, PLATE_1 bottom 4 / top 5, the requirement is PLATE_3 top (5) ->
HOUSING ceiling (6) along +z, nominal 0.2. The chain enters HOUSING at the floor
(8) and leaves at the ceiling (6).
"""

from __future__ import annotations

import dataclasses
import math

import pytest
from typer.testing import CliRunner

pytest.importorskip("OCC", reason="pythonocc-core is not installed")

from detecttol.cad.annotations import ResolvedDimension
from detecttol.cad.cad_stack import (
    CadInput,
    CadStackError,
    build_cad_stack,
    parse_face,
    pmi_dimensions,
    read_cad,
)
from detecttol.cad.pmi import FaceRef, PmiDimension
from detecttol.cad.step_reader import read_step
from detecttol.cli.main import app
from tests.conftest import EXAMPLES

STEP = EXAMPLES / "step" / "plate_stack.step"
EXACT = {"rel": 1e-12, "abs": 1e-12}
SEVEN_SF = {"rel": 1e-6}
FROM, TO = FaceRef("PLATE_3", 5), FaceRef("HOUSING", 6)


@pytest.fixture(scope="module")
def model():  # type: ignore[no-untyped-def]
    return read_step(STEP)


def dim(part: str, a: int, b: int, nominal: float, t: float, did: str) -> ResolvedDimension:
    return ResolvedDimension(
        id=did, nominal=nominal, upper_tol=t, lower_tol=-t, distribution="normal", cp=1.0,
        from_face=FaceRef(part, a), to_face=FaceRef(part, b), direction=(0.0, 0.0, 1.0),
        cad_source=f"test {did}",
    )  # fmt: skip


def plates() -> list[ResolvedDimension]:
    return [dim(f"PLATE_{k}", 4, 5, 16.6, 0.05, f"plate_{k}") for k in (1, 2, 3)]


def cad(model, dims, flatness=()) -> CadInput:  # type: ignore[no-untyped-def]
    return CadInput(model, tuple(dims), tuple(flatness), (), "test")


def test_two_housing_dimensions_are_combined(model) -> None:  # type: ignore[no-untyped-def]
    """HOUSING has bottom->floor 10 +/-0.05 and bottom->ceiling 60 +/-0.08, no floor->ceiling.

    Path floor(8) -> bottom(4) -> ceiling(6): -10 then +60 (sensitivities -1, +1).
    Y = 60 - 10 - 3*16.6 = 0.2
    W = 0.08 + 0.05 + 3*0.05 = 0.28 -> [-0.08, 0.48]
    (3 sigma)^2 = 0.08^2 + 0.05^2 + 3*0.05^2 = 0.0164 -> sigma = sqrt(0.0164)/3 = 0.04268749
    """
    dims = [
        dim("HOUSING", 4, 8, 10.0, 0.05, "floor"),
        dim("HOUSING", 4, 6, 60.0, 0.08, "ceiling"),
        *plates(),
    ]
    built = build_cad_stack(cad(model, dims), FROM, TO)
    r = built.analyze()
    by_id = {c.id: c for c in built.stack.contributors}
    assert (by_id["floor"].sensitivity, by_id["ceiling"].sensitivity) == (-1.0, 1.0)
    assert r.mean == pytest.approx(0.2, abs=1e-9)
    assert r.worst_case is not None and r.rss is not None
    assert r.worst_case.half_range == pytest.approx(0.28, **EXACT)
    assert r.rss.sigma == pytest.approx(math.sqrt(0.0164) / 3, **EXACT)
    assert r.rss.sigma == pytest.approx(0.04268749, **SEVEN_SF)
    assert "TOLERANCE_FROM_CAD" in [w.code for w in r.warnings]


def test_two_ways_to_combine_are_refused(model) -> None:  # type: ignore[no-untyped-def]
    dims = [
        dim("HOUSING", 4, 8, 10.0, 0.05, "b_floor"), dim("HOUSING", 4, 6, 60.0, 0.05, "b_ceiling"),
        dim("HOUSING", 2, 8, 60.0, 0.05, "t_floor"), dim("HOUSING", 2, 6, 10.0, 0.05, "t_ceiling"),
        *plates(),
    ]  # fmt: skip
    with pytest.raises(CadStackError, match="2 ways to combine its dimensions"):
        build_cad_stack(cad(model, dims), FROM, TO)


def test_missing_dimension_takes_the_general_class(model) -> None:  # type: ignore[no-untyped-def]
    """No HOUSING dimension; IS 2102-m for 50 mm (over 30 up to 120) = +/-0.3.

    W = 0.3 + 3*0.05 = 0.45; (3 sigma)^2 = 0.09 + 0.0075 = 0.0975 -> sigma = 0.1040833
    """
    built = build_cad_stack(cad(model, plates()), FROM, TO, general_class="m", standard="is")
    r = built.analyze()
    filled = [c for c in built.stack.contributors if c.id.startswith("HOUSING:general")]
    assert len(filled) == 1 and (filled[0].upper_tol, filled[0].lower_tol) == (0.3, -0.3)
    assert filled[0].tolerance_source is not None and "IS 2102-m" in filled[0].tolerance_source
    assert built.chain.filled[0].nominal == pytest.approx(50.0, abs=1e-9)
    assert r.worst_case is not None and r.rss is not None
    assert r.worst_case.half_range == pytest.approx(0.45, **EXACT)
    assert r.rss.sigma == pytest.approx(0.1040833, **SEVEN_SF)
    assert r.standard == "is"


def test_missing_dimension_without_a_class_is_named(model) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(
        CadStackError, match=r"no tolerance for the dimension of 'HOUSING'.*--general"
    ):
        build_cad_stack(cad(model, plates()), FROM, TO)


def test_requirement_needs_a_limit(model) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(CadStackError, match="at least one of lsl / usl"):
        build_cad_stack(cad(model, plates()), FROM, TO, lsl=None, usl=None)


def test_parse_face() -> None:
    assert parse_face("Block_C:2") == FaceRef("Block_C", 2)
    assert parse_face("a:b:7") == FaceRef("a:b", 7)
    for bad in ("Block_C", "Block_C:x", ":3"):
        with pytest.raises(CadStackError, match="expected PART:FACE"):
            parse_face(bad)


def test_step_pmi_dimensions_build_golden_case_a(model) -> None:  # type: ignore[no-untyped-def]
    """Fake PMI injected into the model (OCCT cannot write PMI files): slot 50 +/-0.1 and
    three plates 16.6 +/-0.05 give golden case A (mean 0.2, W 0.25, sigma 0.0440959)."""
    pmi = (
        PmiDimension("slot", "Location_LinearDistance", 50.0, 0.1, -0.1, "plus_minus",
                     (FaceRef("HOUSING", 8), FaceRef("HOUSING", 6)), 1),
        *(PmiDimension(f"p{k}", "Size_LinearDistance", 16.6, 0.05, -0.05, "plus_minus",
                       (FaceRef(f"PLATE_{k}", 4), FaceRef(f"PLATE_{k}", 5)), 1) for k in (1, 2, 3)),
        PmiDimension("wrong", "Size_LinearDistance", 12.0, 0.1, -0.1, "plus_minus",
                     (FaceRef("HOUSING", 8), FaceRef("HOUSING", 6)), 1),
        PmiDimension("angle", "Location_Angular", 1.0, 0.1, -0.1, "plus_minus", (), 0, "rad"),
    )  # fmt: skip
    with_pmi = dataclasses.replace(model, dimensions=pmi)
    dims, notes = pmi_dimensions(with_pmi)
    assert sorted(d.id for d in dims) == ["HOUSING:slot", "PLATE_1:p1", "PLATE_2:p2", "PLATE_3:p3"]
    assert any("wrong" in n and "apart" in n for n in notes)
    r = build_cad_stack(cad(with_pmi, dims), FROM, TO).analyze()
    assert r.worst_case is not None and r.rss is not None
    assert r.mean == pytest.approx(0.2, abs=1e-9)
    assert r.worst_case.half_range == pytest.approx(0.25, **EXACT)
    # root.md golden case A: 3 sigma = sqrt(0.1^2 + 3*0.05^2) = sqrt(0.0175)
    assert r.rss.sigma == pytest.approx(math.sqrt(0.0175) / 3, **EXACT)


def test_read_cad_rejects_unknown_files(tmp_path) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(CadStackError, match=r"expected \.SLDASM, \.step or \.stp"):
        read_cad(tmp_path / "x.iges")
    with pytest.raises(CadStackError, match="drawings can only be read"):
        read_cad(STEP, ["a.SLDDRW"])


def test_cli_analyze_cad_on_a_step_file(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """No PMI in the file, so --general m fills every dimension: slot +/-0.3, plates +/-0.2,
    W = 0.3 + 3*0.2 = 0.9 (same as tests/standards: IS 2102-m golden geometry)."""
    runner = CliRunner()
    ok = runner.invoke(
        app,
        ["analyze-cad", str(STEP), "--from", "PLATE_3:5", "--to", "HOUSING:6", "--general", "m",
         "--standard", "is", "--format", "json", "--samples", "2000"],
    )  # fmt: skip
    assert ok.exit_code == 0, ok.output
    assert '"half_range": 0.9' in ok.output and '"standard": "is"' in ok.output
    missing = runner.invoke(
        app, ["analyze-cad", str(STEP), "--from", "PLATE_3:5", "--to", "HOUSING:6"]
    )
    assert missing.exit_code == 2 and "--general" in missing.output
    bad = runner.invoke(app, ["analyze-cad", str(STEP), "--from", "PLATE_3", "--to", "HOUSING:6"])
    assert bad.exit_code == 2 and "PART:FACE" in bad.output
    faces = runner.invoke(app, ["faces", str(STEP)])
    assert faces.exit_code == 0 and "usable tolerances from STEP PMI: 0 dimensions" in faces.output


def test_flatness_on_an_intermediate_datum_face_is_not_added(model) -> None:  # type: ignore[no-untyped-def]
    """Combined HOUSING floor(8) <- bottom(4) -> ceiling(6). The bottom face is only the
    datum both dimensions start from; its flatness cancels out (reviewer finding 3).
    Under IS a flatness 0.02 there must leave W at 0.28 (test above)."""
    from detecttol.gdt.models import Flatness

    dims = [
        dim("HOUSING", 4, 8, 10.0, 0.05, "floor"),
        dim("HOUSING", 4, 6, 60.0, 0.08, "ceiling"),
        *plates(),
    ]
    flat = [(Flatness(id="bottom_flat", tolerance=0.02), FaceRef("HOUSING", 4))]
    built = build_cad_stack(cad(model, dims, flat), FROM, TO, standard="is")
    assert built.gdt is None
    r = built.analyze()
    assert r.worst_case is not None and r.worst_case.half_range == pytest.approx(0.28, **EXACT)
    assert any("combined from 2 dimensions" in n and "via face(s) [4]" in n for n in built.notes)


def test_asme_exemption_only_for_a_size_dimension(model) -> None:  # type: ignore[no-untyped-def]
    """Flatness 0.02 on the floor (a contact face). Reviewer finding 4:
    - floor reached by combined location dimensions: not inside a size, so it adds
      0 +/- 0.01 even under ASME -> W = 0.28 + 0.01 = 0.29;
    - direct floor->ceiling dimension flagged as a size (slot width 50 +/-0.1): under ASME
      the flatness is inside the size -> W = 0.1 + 0.15 = 0.25 (golden case A); under IS it
      adds -> W = 0.26."""
    from detecttol.gdt.models import Flatness

    flat = [(Flatness(id="floor_flat", tolerance=0.02), FaceRef("HOUSING", 8))]
    combined = [
        dim("HOUSING", 4, 8, 10.0, 0.05, "floor"),
        dim("HOUSING", 4, 6, 60.0, 0.08, "ceiling"),
        *plates(),
    ]
    r = build_cad_stack(cad(model, combined, flat), FROM, TO, standard="asme").analyze()
    assert r.worst_case is not None and r.worst_case.half_range == pytest.approx(0.29, **EXACT)
    slot = dataclasses.replace(dim("HOUSING", 8, 6, 50.0, 0.1, "slot"), is_size=True)
    for standard, expected in (("asme", 0.25), ("is", 0.26)):
        r = build_cad_stack(
            cad(model, [slot, *plates()], flat), FROM, TO, standard=standard
        ).analyze()  # type: ignore[arg-type]
        assert r.worst_case is not None and r.worst_case.half_range == pytest.approx(
            expected, **EXACT
        )
