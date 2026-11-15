"""App logic for holes and shafts, without a browser.

Models: SolidWorks' STEP exports in examples/solidworks/fits (no tolerances inside, each
cylinder split into two half faces).

Fit_Test: Housing bore dia 20 (faces 0 and 7), Shaft dia 20 (faces 0 and 1).
IS 2102-m for dia 20 (over 6 up to 30): +/-0.2, so the clearance is -0.4 .. 0.4
(transition fit). With the user's H7 (+0.021/0) and g6 (-0.007/-0.020): 0.007 .. 0.041
(clearance fit).
"""

from __future__ import annotations

import pytest

pytest.importorskip("OCC", reason="pythonocc-core is not installed")

from detecttol.app.state import AppState
from detecttol.cad.cad_stack import CadStackError
from tests.conftest import EXAMPLES

FITS = EXAMPLES / "solidworks" / "fits"
EXACT = {"rel": 1e-12, "abs": 1e-12}


@pytest.fixture
def fit_state() -> AppState:
    s = AppState(samples=2000)
    s.open(FITS / "Fit_Test_geometry_AP214.step")
    s.set_mode("fit")
    return s


def test_pick_hole_and_shaft_in_any_order(fit_state: AppState) -> None:
    fit_state.pick("Shaft:1")  # the second half face of the shaft
    fit_state.pick("Housing:7")
    assert (fit_state.hole.part, fit_state.hole.face_index) == ("Housing", 0)  # type: ignore[union-attr]
    assert (fit_state.shaft.part, fit_state.shaft.face_index) == ("Shaft", 0)  # type: ignore[union-attr]
    assert fit_state.fit is not None and fit_state.error is None
    assert fit_state.face_label(fit_state.hole) == "Housing:0 (hole dia 20)"
    lim = fit_state.fit.limits
    assert (lim.kind, lim.min_clearance, lim.max_clearance) == (
        "transition",
        pytest.approx(-0.4, **EXACT),
        pytest.approx(0.4, **EXACT),
    )
    rows = fit_state.rows()
    assert [(r.part, r.kind, r.sensitivity, r.key) for r in rows] == [
        ("Housing", "table", 1.0, ("Housing", 0, 0)),
        ("Shaft", "table", -1.0, ("Shaft", 0, 0)),
    ]
    fit_state.analyze()
    v = fit_state.verdict()
    assert v.level == "risk" and v.headline.startswith("Transition fit: can fail")


def test_typed_fit_values_give_a_clearance_fit(fit_state: AppState) -> None:
    fit_state.pick("Housing:0")
    fit_state.pick("Shaft:0")
    fit_state.set_override(("Housing", 0, 0), 0.021, 0.0)
    fit_state.set_override(("Shaft", 0, 0), -0.007, -0.020)
    assert [r.kind for r in fit_state.rows()] == ["user", "user"]
    result = fit_state.analyze()
    assert (result.worst_case.lower, result.worst_case.upper) == (
        pytest.approx(0.007, abs=1e-12),
        pytest.approx(0.041, abs=1e-12),
    )
    v = fit_state.verdict()
    assert v.level == "ok" and v.headline == (
        "Clearance fit, always meets the requirement: clearance 0.007 to 0.041 mm."
    )


def test_without_a_general_class_both_diameters_need_values(fit_state: AppState) -> None:
    fit_state.general_class = None
    fit_state.pick("Housing:0")
    fit_state.pick("Shaft:0")
    assert fit_state.needs_value == 2
    assert [r.kind for r in fit_state.rows()] == ["missing", "missing"]
    with pytest.raises(CadStackError, match="enter a tolerance first"):
        fit_state.analyze()


def test_clicks_that_do_not_fit_the_mode_are_refused(fit_state: AppState) -> None:
    flat = next(f.index for f in fit_state.cad.model.part("Housing").faces if f.normal)  # type: ignore[union-attr]
    with pytest.raises(CadStackError, match="not a hole or a shaft"):
        fit_state.pick(f"Housing:{flat}")
    fit_state.set_mode("gap")
    with pytest.raises(CadStackError, match="is round: a gap is measured between flat faces"):
        fit_state.pick("Housing:0")
    assert fit_state.face_from is None


def test_fit_project_round_trip(fit_state: AppState, tmp_path) -> None:  # type: ignore[no-untyped-def]
    fit_state.pick("Housing:0")
    fit_state.pick("Shaft:0")
    fit_state.set_override(("Shaft", 0, 0), -0.007, -0.020)
    target = tmp_path / "fit.dtol"
    fit_state.save(target)
    again = AppState.load(target)
    assert (again.mode, again.hole, again.shaft) == ("fit", fit_state.hole, fit_state.shaft)
    assert [r.kind for r in again.rows()] == ["table", "user"]


def test_gap_mode_follows_the_pin_and_lists_its_diameters() -> None:
    """Pin_Test: Plate_1 datum B (x = 0) -> Plate_2 x = 0 through hole, pin, hole. The
    STEP file has no tolerances: with class m the three diameters appear as editable rows
    (sign blank: they act through the float), next to the two pin floats."""
    s = AppState(samples=2000)
    s.open(FITS / "Pin_Test_geometry_AP214.step")
    b = {p: next(f.index for f in s.cad.model.part(p).faces if f.normal == (-1.0, 0.0, 0.0))  # type: ignore[union-attr]
         for p in ("Plate_1", "Plate_2")}  # fmt: skip
    s.pick(f"Plate_1:{b['Plate_1']}")
    s.pick(f"Plate_2:{b['Plate_2']}")
    assert s.error is None and s.built is not None
    assert s.built.chain.path == ("Plate_1", "Pin", "Plate_2")
    rows = s.rows()
    floats = [r for r in rows if r.id.startswith("float ")]
    diameters = [r for r in rows if "dia (" in r.faces]
    assert len(floats) == 2 and all(r.kind == "table" for r in floats)  # diameters from class m
    assert sorted(r.part for r in diameters) == ["Pin", "Plate_1", "Plate_2"]
    assert all(r.kind == "table" and r.sensitivity == 0.0 and r.key for r in diameters)
