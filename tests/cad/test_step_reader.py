"""STEP reader on synthetic assemblies whose geometry is known by construction."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("OCC", reason="pythonocc-core is not installed")

from detecttol.cad.step_reader import StepModel, StepReadError, read_step
from detecttol.cad.synthetic import BoxPart, write_box_assembly

# OCCT writes and re-reads these coordinates as decimal text; observed error is
# zero, and 1e-9 mm is far below any tolerance of interest.
GEOM = {"abs": 1e-9}

PARTS = [
    BoxPart("BASE", (50.0, 30.0, 10.0)),
    BoxPart("PLATE", (50.0, 30.0, 16.6), origin=(0.0, 0.0, 10.0)),
    BoxPart("TURNED", (20.0, 10.0, 5.0), origin=(100.0, 0.0, 0.0), rotation_z_deg=90.0),
]


@pytest.fixture(scope="module")
def model(tmp_path_factory: pytest.TempPathFactory) -> StepModel:
    path = tmp_path_factory.mktemp("step") / "assembly.step"
    write_box_assembly(path, PARTS)
    return read_step(path)


def test_assembly_structure_names_and_placements(model: StepModel) -> None:
    assert [p.name for p in model.parts] == ["BASE", "PLATE", "TURNED"]
    assert [p.path for p in model.parts] == [
        ("ASSEMBLY", "BASE"),
        ("ASSEMBLY", "PLATE"),
        ("ASSEMBLY", "TURNED"),
    ]
    assert model.part("BASE").translation == pytest.approx((0.0, 0.0, 0.0), **GEOM)
    assert model.part("PLATE").translation == pytest.approx((0.0, 0.0, 10.0), **GEOM)
    assert model.part("TURNED").translation == pytest.approx((100.0, 0.0, 0.0), **GEOM)
    identity = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
    for row, expected in zip(model.part("PLATE").rotation, identity, strict=True):
        assert row == pytest.approx(expected, **GEOM)
    # Rotation by +90 deg about z: x -> y, y -> -x.
    turned = ((0.0, -1.0, 0.0), (1.0, 0.0, 0.0), (0.0, 0.0, 1.0))
    for row, expected in zip(model.part("TURNED").rotation, turned, strict=True):
        assert row == pytest.approx(expected, **GEOM)
    with pytest.raises(KeyError, match="expected exactly one match"):
        model.part("NOPE")


def test_every_box_has_six_planar_faces_with_exact_areas(model: StepModel) -> None:
    """Areas of a dx x dy x dz box: two each of dy*dz, dx*dz, dx*dy.

    BASE 50x30x10 -> 300, 300, 500, 500, 1500, 1500
    PLATE 50x30x16.6 -> 498, 498, 830, 830, 1500, 1500
    TURNED 20x10x5 -> 50, 50, 100, 100, 200, 200
    """
    expected = {
        "BASE": [300.0, 300.0, 500.0, 500.0, 1500.0, 1500.0],
        "PLATE": [498.0, 498.0, 830.0, 830.0, 1500.0, 1500.0],
        "TURNED": [50.0, 50.0, 100.0, 100.0, 200.0, 200.0],
    }
    for name, areas in expected.items():
        part = model.part(name)
        assert len(part.faces) == 6 and len(part.planar_faces()) == 6
        assert [f.index for f in part.faces] == [0, 1, 2, 3, 4, 5]
        assert sorted(f.area for f in part.faces) == pytest.approx(areas, rel=1e-12)
        for face in part.faces:
            assert face.surface == "plane" and face.normal is not None
            assert sum(c * c for c in face.normal) == pytest.approx(1.0, abs=1e-12)


def _face(model: StepModel, part: str, normal: tuple[float, float, float]):  # type: ignore[no-untyped-def]
    hits = [
        f
        for f in model.part(part).faces
        if f.normal is not None and f.normal == pytest.approx(normal, abs=1e-9)
    ]
    assert len(hits) == 1
    return hits[0]


def test_nominal_dimensions_are_exact(model: StepModel) -> None:
    """Distances between opposite faces equal the box sizes, in assembly coordinates.

    BASE: bottom z = 0, top z = 10 (thickness 10).
    PLATE (moved up by 10): bottom z = 10, top z = 26.6 (thickness 16.6);
    its bottom coincides with the BASE top, with opposite normals.
    Centroids: BASE top (25, 15, 10); PLATE top (25, 15, 26.6).
    """
    base_bottom = _face(model, "BASE", (0.0, 0.0, -1.0))
    base_top = _face(model, "BASE", (0.0, 0.0, 1.0))
    plate_bottom = _face(model, "PLATE", (0.0, 0.0, -1.0))
    plate_top = _face(model, "PLATE", (0.0, 0.0, 1.0))
    assert base_bottom.centroid == pytest.approx((25.0, 15.0, 0.0), **GEOM)
    assert base_top.centroid == pytest.approx((25.0, 15.0, 10.0), **GEOM)
    assert plate_bottom.centroid == pytest.approx((25.0, 15.0, 10.0), **GEOM)
    assert plate_top.centroid == pytest.approx((25.0, 15.0, 26.6), **GEOM)
    assert base_top.centroid[2] - base_bottom.centroid[2] == pytest.approx(10.0, **GEOM)
    assert plate_top.centroid[2] - plate_bottom.centroid[2] == pytest.approx(16.6, **GEOM)
    # x and y extents of the PLATE: 50 and 30.
    x0, x1 = _face(model, "PLATE", (-1.0, 0.0, 0.0)), _face(model, "PLATE", (1.0, 0.0, 0.0))
    y0, y1 = _face(model, "PLATE", (0.0, -1.0, 0.0)), _face(model, "PLATE", (0.0, 1.0, 0.0))
    assert x1.centroid[0] - x0.centroid[0] == pytest.approx(50.0, **GEOM)
    assert y1.centroid[1] - y0.centroid[1] == pytest.approx(30.0, **GEOM)


def test_rotated_part_faces_are_in_assembly_coordinates(model: StepModel) -> None:
    """TURNED: 20x10x5 box rotated +90 deg about z, then moved to x = 100.

    A point (x, y) of the box goes to (100 - y, x): the box occupies
    x in [90, 100], y in [0, 20], z in [0, 5].
    Its local -x face (x = 0) becomes the y = 0 face with normal (0, -1, 0) and
    centroid (95, 0, 2.5); its local +y face becomes x = 90, normal (-1, 0, 0).
    """
    assert _face(model, "TURNED", (0.0, -1.0, 0.0)).centroid == pytest.approx(
        (95.0, 0.0, 2.5), **GEOM
    )
    assert _face(model, "TURNED", (0.0, 1.0, 0.0)).centroid == pytest.approx(
        (95.0, 20.0, 2.5), **GEOM
    )
    assert _face(model, "TURNED", (-1.0, 0.0, 0.0)).centroid == pytest.approx(
        (90.0, 10.0, 2.5), **GEOM
    )
    assert _face(model, "TURNED", (1.0, 0.0, 0.0)).centroid == pytest.approx(
        (100.0, 10.0, 2.5), **GEOM
    )
    assert _face(model, "TURNED", (0.0, 0.0, 1.0)).centroid == pytest.approx(
        (95.0, 10.0, 5.0), **GEOM
    )


def test_synthetic_file_has_no_pmi(model: StepModel) -> None:
    assert model.dimensions == () and model.geometric_tolerances == () and model.datums == ()
    assert model.n_dimension_labels == 0 and model.n_datum_labels == 0


def test_single_part_file(tmp_path: Path) -> None:
    path = tmp_path / "one.step"
    write_box_assembly(path, [BoxPart("ONLY", (1.0, 2.0, 3.0))])
    (part,) = read_step(path).parts
    assert part.name == "ONLY"
    assert sorted(f.area for f in part.faces) == pytest.approx([2.0, 2.0, 3.0, 3.0, 6.0, 6.0])


def test_missing_file_gives_a_clear_error(tmp_path: Path) -> None:
    with pytest.raises(StepReadError, match="STEP file not found"):
        read_step(tmp_path / "missing.step")


def test_non_step_file_gives_a_clear_error(tmp_path: Path) -> None:
    bad = tmp_path / "not_step.step"
    bad.write_text("this is not a STEP file\n", encoding="utf-8")
    with pytest.raises(StepReadError, match="not a readable STEP file"):
        read_step(bad)
    empty = tmp_path / "empty.step"
    empty.write_text("", encoding="utf-8")
    with pytest.raises(StepReadError):
        read_step(empty)


def test_step_file_without_any_shape_gives_a_clear_error(tmp_path: Path) -> None:
    hollow = tmp_path / "hollow.step"
    hollow.write_text(
        "ISO-10303-21;\nHEADER;\nFILE_DESCRIPTION((''),'2;1');\n"
        "FILE_NAME('h','',(''),(''),'','','');\nFILE_SCHEMA(('AUTOMOTIVE_DESIGN'));\nENDSEC;\n"
        "DATA;\n#1=CARTESIAN_POINT('',(0.,0.,0.));\nENDSEC;\nEND-ISO-10303-21;\n",
        encoding="utf-8",
    )
    with pytest.raises(StepReadError):
        read_step(hollow)


def test_writer_rejects_bad_input(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="at least one part"):
        write_box_assembly(tmp_path / "x.step", [])
    with pytest.raises(ValueError, match="duplicate part names"):
        write_box_assembly(
            tmp_path / "x.step", [BoxPart("A", (1.0, 1.0, 1.0)), BoxPart("A", (1.0, 1.0, 1.0))]
        )
    with pytest.raises(ValueError, match="sizes must be > 0"):
        write_box_assembly(tmp_path / "x.step", [BoxPart("A", (1.0, 0.0, 1.0))])
