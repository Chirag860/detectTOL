"""App logic without a browser: open, pick, table, overrides, verdict, project file, meshes.

Model: examples/solidworks/Tolerance_Test_geometry_AP203_noPMI.step (no tolerances in
the file). Requirement Block_C:2 (x = 99, +X) -> Frame:4 (x = 100, -X): nominal 1 mm.
IS 2102-m: Frame 100 and Block_C 39 / Block_B 35 (over 30 up to 120) +/-0.3,
Block_A 25 (over 6 up to 30) +/-0.2.
"""

from __future__ import annotations

import pytest

pytest.importorskip("OCC", reason="pythonocc-core is not installed")

from detecttol.app.state import AppState, verdict
from detecttol.cad.cad_stack import CadStackError
from detecttol.cad.mesh import bounds, mesh_model, to_stl
from detecttol.cad.step_reader import read_step
from tests.conftest import EXAMPLES

GEOMETRY = EXAMPLES / "solidworks" / "Tolerance_Test_geometry_AP203_noPMI.step"
EXACT = {"rel": 1e-12, "abs": 1e-12}


@pytest.fixture
def state() -> AppState:
    s = AppState(samples=2000)
    s.open(GEOMETRY)
    s.pick("Block_C:2")
    s.pick("Frame:4")
    return s


def test_pick_order_and_chain(state: AppState) -> None:
    assert (state.face_from.part, state.face_to.part) == ("Block_C", "Frame")  # type: ignore[union-attr]
    assert state.picking == "from" and state.error is None
    assert state.built is not None and state.built.chain.path == (
        "Block_C",
        "Block_B",
        "Block_A",
        "Frame",
    )
    rows = state.rows()
    assert [(r.part, r.upper, r.lower, r.kind) for r in rows] == [
        ("Block_C", 0.3, -0.3, "table"),
        ("Block_B", 0.3, -0.3, "table"),
        ("Block_A", 0.2, -0.2, "table"),
        ("Frame", 0.3, -0.3, "table"),
    ]
    assert all(r.key is not None for r in rows)


def test_analysis_and_verdict(state: AppState) -> None:
    """W = 0.3 + 0.3 + 0.2 + 0.3 = 1.1 -> [-0.1, 2.1]: fails in the worst case."""
    r = state.analyze()
    assert r.worst_case is not None
    assert (r.worst_case.lower, r.worst_case.upper) == pytest.approx((-0.1, 2.1), abs=1e-9)
    v = verdict(r)
    assert v.level == "risk" and "-0.1 mm" in v.headline
    assert "<html" in state.report_html().lower()


def test_user_override_replaces_the_general_value(state: AppState) -> None:
    """Block_A typed as +0.05/-0.05: W = 0.3 + 0.3 + 0.05 + 0.3 = 0.95 -> [0.05, 1.95],
    always fits."""
    state.set_override(("Block_A", 0, 2), 0.05, -0.05)
    row = next(r for r in state.rows() if r.part == "Block_A")
    assert (row.upper, row.lower, row.kind) == (0.05, -0.05, "user")
    r = state.analyze()
    assert r.worst_case is not None and r.worst_case.half_range == pytest.approx(0.95, **EXACT)
    assert verdict(r).level == "ok"


def test_without_a_general_class_rows_need_values(state: AppState) -> None:
    state.general_class = None
    state.refresh()
    assert state.built is not None and len(state.built.needs_value) == 4
    assert {r.kind for r in state.rows()} == {"missing"}
    with pytest.raises(CadStackError, match="enter a tolerance first"):
        state.analyze()
    for key in [r.key for r in state.rows()]:
        assert key is not None
        state.set_override(key, 0.1, -0.1)
    assert state.built is not None and not state.built.needs_value
    r = state.analyze()
    assert r.worst_case is not None and r.worst_case.half_range == pytest.approx(0.4, **EXACT)


def test_nominal_failure_and_errors(state: AppState) -> None:
    state.lsl = 2.0  # nominal gap is 1
    state.refresh()
    assert verdict(state.analyze()).level == "fail"
    state.pick("Block_C:2")
    state.pick("Block_C:2")  # same face twice
    assert state.built is None and state.error is not None
    with pytest.raises(CadStackError, match=r"open a \.SLDASM, \.step or \.stp"):
        state.open("drawing.SLDDRW")


def test_project_round_trip(state: AppState, tmp_path) -> None:  # type: ignore[no-untyped-def]
    state.set_override(("Block_A", 0, 2), 0.05, -0.05)
    state.standard = "asme"
    path = tmp_path / "p.dtol"
    state.save(path)
    again = AppState.load(path)
    assert again.face_from == state.face_from and again.face_to == state.face_to
    assert again.overrides == {("Block_A", 0, 2): (0.05, -0.05)}
    assert again.standard == "asme" and again.built is not None
    bad = tmp_path / "x.dtol"
    bad.write_text("{}", encoding="utf-8")
    with pytest.raises(CadStackError, match="not a detectTOL project"):
        AppState.load(bad)


def test_meshes_cover_every_face_and_keep_indices() -> None:
    """Each face mesh keeps the reader's part name and face index; Block_C:2 lies in x = 99."""
    model = read_step(GEOMETRY)
    meshes = mesh_model(GEOMETRY)
    assert {m.key for m in meshes} == {f"{p.name}:{f.index}" for p in model.parts for f in p.faces}
    c2 = next(m for m in meshes if m.key == "Block_C:2")
    assert all(v[0] == pytest.approx(99.0, abs=1e-9) for v in c2.vertices)
    assert len(to_stl(c2)) == 84 + 50 * len(c2.triangles)
    lo, hi = bounds(meshes)
    assert lo == pytest.approx((-5.0, -5.0, 0.0)) and hi == pytest.approx((105.0, 5.0, 20.0))


def test_flatness_row_shows_what_it_really_adds() -> None:
    """SolidWorks read-out of the Step 1 model (see tests/solidworks/test_resolve.py): flatness
    0.02 on Block_B's +X face adds +/-0.01 under IS and nothing under ASME (inside its width)."""
    from detecttol.cad.cad_stack import CadInput
    from detecttol.solidworks.resolve import resolve
    from tests.solidworks.test_resolve import readout

    model = read_step(GEOMETRY)
    r = resolve(readout(), model)
    for standard, expected in (("is", 0.01), ("asme", 0.0)):
        s = AppState(standard=standard, samples=2000)  # type: ignore[arg-type]
        s.cad = CadInput(model, r.dimensions, r.flatness, r.notes, "SolidWorks test")
        s.pick("Block_C:2")
        s.pick("Frame:4")
        (flat,) = [row for row in s.rows() if row.kind == "gdt"]
        assert flat.upper == pytest.approx(expected, abs=1e-12)
        assert ("adds nothing" in flat.source) == (expected == 0.0)
