"""PMI -> contributor / GD&T model mapping (no STEP file needed)."""

from __future__ import annotations

from typing import Any

import pytest

pytest.importorskip("OCC", reason="pythonocc-core is not installed")

from detecttol.cad.mapping import (
    PmiMappingError,
    check_planar_datums,
    datum_frame,
    dimension_to_contributor,
    geomtol_to_callout,
    geomtol_to_orientation,
    unsupported_items,
)
from detecttol.cad.step_reader import (
    FaceInfo,
    FaceRef,
    PartInstance,
    PmiDatum,
    PmiDimension,
    PmiGeomTolerance,
    StepModel,
)
from detecttol.gdt import Flatness, Orientation, Parallelism, Position


def dim(**kw: Any) -> PmiDimension:
    base: dict[str, Any] = {
        "name": "d1",
        "kind": "Size_Diameter",
        "value": 35.0,
        "upper_tol": 0.2,
        "lower_tol": -0.0,
        "tolerance_form": "plus_minus",
        "targets": (),
        "n_first": 0,
    }
    base.update(kw)
    return PmiDimension(**base)


def gt(kind: str, value: float = 0.2, **kw: Any) -> PmiGeomTolerance:
    base: dict[str, Any] = {
        "name": f"{kind}.1",
        "kind": kind,
        "value": value,
        "material_modifier": None,
        "datums": (),
        "targets": (),
    }
    base.update(kw)
    return PmiGeomTolerance(**base)


def test_dimension_becomes_a_contributor() -> None:
    """Diameter 35 +0.2/-0: contributor nominal 35, mean 35.1, half-range 0.1, a = -1."""
    c = dimension_to_contributor(dim(), cid="hole", sensitivity=-1.0, cp=1.33)
    assert (c.id, c.nominal, c.upper_tol, c.lower_tol) == ("hole", 35.0, 0.2, 0.0)
    assert (c.sensitivity, c.cp, c.distribution) == (-1.0, 1.33, "normal")
    assert c.mean == pytest.approx(35.1) and c.half_range == pytest.approx(0.1)


def test_range_dimension_maps_like_plus_minus() -> None:
    """Limits 34.8 .. 35.2 around 35 -> +0.2 / -0.2."""
    c = dimension_to_contributor(
        dim(upper_tol=0.2, lower_tol=-0.2, tolerance_form="range"), cid="d", sensitivity=1.0
    )
    assert (c.upper_tol, c.lower_tol) == (0.2, -0.2)


def test_unmappable_dimensions_are_rejected_by_name() -> None:
    with pytest.raises(PmiMappingError, match="angular"):
        dimension_to_contributor(dim(kind="Location_Angular"), cid="a", sensitivity=1.0)
    with pytest.raises(PmiMappingError, match=r"no usable tolerance .*class"):
        dimension_to_contributor(
            dim(upper_tol=None, lower_tol=None, tolerance_form="class"), cid="a", sensitivity=1.0
        )
    with pytest.raises(PmiMappingError, match=r"no usable tolerance .*none"):
        dimension_to_contributor(
            dim(upper_tol=None, lower_tol=None, tolerance_form="none"), cid="a", sensitivity=1.0
        )


def test_flatness_parallelism_and_position_callouts() -> None:
    flat = geomtol_to_callout(gt("Flatness", 0.2), cid="f", sensitivity=-1.0)
    assert isinstance(flat, Flatness) and (flat.tolerance, flat.sensitivity) == (0.2, -1.0)

    par = geomtol_to_callout(gt("Parallelism", 0.06, datums=("A",)), cid="p")
    assert isinstance(par, Parallelism) and par.datums.labels() == ("A",)

    pos = geomtol_to_callout(gt("Position", 0.75, datums=("A", "B", "C")), cid="pos", cp=1.5)
    assert isinstance(pos, Position)
    assert (pos.tolerance, pos.material_condition, pos.cp) == (0.75, "RFS", 1.5)
    assert pos.datums.labels() == ("A", "B", "C")


@pytest.mark.parametrize(("modifier", "condition"), [("M", "MMC"), ("L", "LMC")])
def test_material_modifier_maps_to_condition(modifier: str, condition: str) -> None:
    item = gt("Position", 0.5, datums=("A",), material_modifier=modifier)
    pos = geomtol_to_callout(item, cid="pos", feature="hole", size_contributor="hole_dia")
    assert isinstance(pos, Position)
    assert (pos.material_condition, pos.feature, pos.size_contributor) == (
        condition,
        "hole",
        "hole_dia",
    )
    # Without the feature information the callout cannot be built.
    with pytest.raises(PmiMappingError, match="feature and size_contributor"):
        geomtol_to_callout(item, cid="pos")


def test_orientation_mapping() -> None:
    perp = geomtol_to_orientation(
        gt("Perpendicularity", 1.5, datums=("A",)), cid="perp", feature_length=40.0
    )
    assert isinstance(perp, Orientation)
    assert (perp.kind, perp.tolerance, perp.feature_length) == ("perpendicularity", 1.5, 40.0)
    ang = geomtol_to_orientation(gt("Angularity", 0.1, datums=("B",)), cid="a", feature_length=10.0)
    assert ang.kind == "angularity"
    with pytest.raises(PmiMappingError, match="not an orientation tolerance"):
        geomtol_to_orientation(gt("Flatness"), cid="x", feature_length=1.0)
    with pytest.raises(PmiMappingError, match="needs a datum reference"):
        geomtol_to_orientation(gt("Perpendicularity"), cid="x", feature_length=1.0)
    with pytest.raises(PmiMappingError):
        geomtol_to_orientation(gt("Perpendicularity", datums=("A",)), cid="x", feature_length=0.0)


def test_unsupported_tolerances_are_rejected_by_name() -> None:
    with pytest.raises(PmiMappingError, match=r"ProfileOfSurface\.1.*ProfileOfSurface is not"):
        geomtol_to_callout(gt("ProfileOfSurface", 0.5, datums=("A",)), cid="x")
    with pytest.raises(PmiMappingError, match="Parallelism needs a datum"):
        geomtol_to_callout(gt("Parallelism"), cid="x")
    with pytest.raises(PmiMappingError, match="Position needs a datum"):
        geomtol_to_callout(gt("Position"), cid="x")
    with pytest.raises(PmiMappingError, match="unsupported material modifier"):
        geomtol_to_callout(gt("Position", datums=("A",), material_modifier="F"), cid="x")
    with pytest.raises(PmiMappingError):  # zero-width zone
        geomtol_to_callout(gt("Flatness", 0.0), cid="x")


def test_datum_frame_limits() -> None:
    assert datum_frame(gt("Flatness")) is None
    assert datum_frame(gt("Position", datums=("A", "B"))).labels() == ("A", "B")  # type: ignore[union-attr]
    with pytest.raises(PmiMappingError, match="4 datum references"):
        datum_frame(gt("Position", datums=("A", "B", "C", "D")))
    with pytest.raises(PmiMappingError, match="distinct"):
        datum_frame(gt("Position", datums=("A", "A")))
    with pytest.raises(PmiMappingError):
        datum_frame(gt("Position", datums=("A-B",)))  # common datum: not supported


def _model(surface: str) -> StepModel:
    face = FaceInfo(
        index=0,
        surface=surface,
        area=1.0,
        centroid=(0.0, 0.0, 0.0),
        normal=(0.0, 0.0, 1.0) if surface == "plane" else None,
    )
    part = PartInstance(
        name="P",
        instance_name="P",
        path=("P",),
        translation=(0.0, 0.0, 0.0),
        rotation=((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
        faces=(face,),
    )
    return StepModel(
        path="x",
        parts=(part,),
        dimensions=(
            dim(),
            dim(kind="Size_Angular"),
            dim(upper_tol=None, lower_tol=None, tolerance_form="none"),
        ),
        geometric_tolerances=(gt("Flatness"), gt("ProfileOfSurface")),
        datums=(PmiDatum(name="A", targets=(FaceRef("P", 0),)), PmiDatum(name="B", targets=())),
    )


def test_planar_datum_check() -> None:
    check_planar_datums(_model("plane"), gt("Position", datums=("A",)))
    with pytest.raises(PmiMappingError, match="datum 'A' is on a cylinder face"):
        check_planar_datums(_model("cylinder"), gt("Position", datums=("A",)))
    with pytest.raises(PmiMappingError, match="datum 'B' has no face"):
        check_planar_datums(_model("plane"), gt("Position", datums=("B",)))
    with pytest.raises(PmiMappingError, match="datum 'Z' has no face"):
        check_planar_datums(_model("plane"), gt("Position", datums=("Z",)))


def test_unsupported_items_report() -> None:
    lines = unsupported_items(_model("plane"))
    assert lines == [
        "geometric tolerance 'ProfileOfSurface.1': type ProfileOfSurface",
        "dimension 'd1': angular",
        "dimension 'd1': no tolerance (form 'none')",
    ]
