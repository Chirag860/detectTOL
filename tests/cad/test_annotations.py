"""YAML annotation fallback: tolerances attached to faces by part, index and fingerprint."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
import yaml

pytest.importorskip("OCC", reason="pythonocc-core is not installed")

from detecttol import analyze
from detecttol.cad.annotations import (
    AnnotationError,
    face_table,
    load_annotations,
    parse_annotations,
    resolve_annotations,
)
from detecttol.cad.step_reader import StepModel, read_step
from detecttol.cad.synthetic import BoxPart, write_box_assembly
from detecttol.core.models import Requirement, Stack

BASE_BOTTOM = {"part": "BASE", "face": 4, "centroid": [25, 15, 0], "normal": [0, 0, -1]}
BASE_TOP = {"part": "BASE", "face": 5, "centroid": [25, 15, 10], "normal": [0, 0, 1]}
PLATE_BOTTOM = {"part": "PLATE", "face": 4, "centroid": [25, 15, 10], "normal": [0, 0, -1]}
PLATE_TOP = {"part": "PLATE", "face": 5, "centroid": [25.0, 15.0, 26.6], "normal": [0, 0, 1]}
PLATE_SIDE = {"part": "PLATE", "face": 1, "centroid": [50, 15, 18.3], "normal": [1, 0, 0]}


@pytest.fixture(scope="module")
def model(tmp_path_factory: pytest.TempPathFactory) -> StepModel:
    path = tmp_path_factory.mktemp("ann") / "stack.step"
    write_box_assembly(
        path,
        [
            BoxPart("BASE", (50.0, 30.0, 10.0)),
            BoxPart("PLATE", (50.0, 30.0, 16.6), origin=(0.0, 0.0, 10.0)),
        ],
    )
    return read_step(path)


def doc() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "units": "mm",
        "annotations": [
            {
                "id": "plate_thickness",
                "kind": "dimension",
                "from": PLATE_BOTTOM,
                "to": PLATE_TOP,
                "upper_tol": 0.05,
                "lower_tol": -0.05,
            },
            {
                "id": "base_thickness",
                "kind": "dimension",
                "from": BASE_TOP,
                "to": BASE_BOTTOM,
                "nominal": 10.0,
                "upper_tol": 0.1,
                "lower_tol": -0.1,
                "distribution": "uniform",
                "cp": 1.0,
            },
            {"id": "top_flatness", "kind": "flatness", "on": PLATE_TOP, "tolerance": 0.04},
            {"id": "A", "kind": "datum", "on": BASE_BOTTOM},
        ],
    }


def errors(model: StepModel, document: dict[str, Any]) -> list[str]:
    with pytest.raises(AnnotationError) as info:
        resolve_annotations(model, parse_annotations(document))
    return info.value.errors


def test_annotations_resolve_to_exact_nominal_dimensions(model: StepModel) -> None:
    """PLATE is a 16.6 mm box on a 10 mm BASE: the measured distances must be
    exactly 16.6 and 10.0. Direction: from the PLATE bottom (normal -z) the top
    lies along +z; from the BASE top (normal +z) the bottom lies along -z."""
    resolved = resolve_annotations(model, parse_annotations(doc()))
    plate, base = resolved.dimensions
    assert plate.id == "plate_thickness"
    assert plate.nominal == pytest.approx(16.6, abs=1e-9)
    assert (plate.upper_tol, plate.lower_tol) == (0.05, -0.05)
    assert plate.direction == pytest.approx((0.0, 0.0, 1.0), abs=1e-12)
    assert (plate.from_face.part, plate.from_face.face_index) == ("PLATE", 4)
    assert (plate.to_face.part, plate.to_face.face_index) == ("PLATE", 5)
    assert base.nominal == pytest.approx(10.0, abs=1e-9)
    assert base.direction == pytest.approx((0.0, 0.0, -1.0), abs=1e-12)
    assert base.distribution == "uniform"

    ((flatness, flat_ref),) = resolved.flatness
    assert (flatness.id, flatness.tolerance) == ("top_flatness", 0.04)
    assert (flat_ref.part, flat_ref.face_index) == ("PLATE", 5)
    ((datum, datum_ref),) = resolved.datums
    assert datum.label == "A" and (datum_ref.part, datum_ref.face_index) == ("BASE", 4)


def test_resolved_dimensions_feed_the_stack_engine(model: StepModel) -> None:
    """Height of the stack = base + plate: mean 26.6, worst case 0.1 + 0.05 = 0.15."""
    resolved = resolve_annotations(model, parse_annotations(doc()))
    stack = Stack(
        schema_version=1,
        units="mm",
        name="height",
        requirement=Requirement(usl=26.8),
        contributors=[d.to_contributor(1.0) for d in resolved.dimensions],
    )
    result = analyze(stack)
    assert result.worst_case is not None
    assert result.mean == pytest.approx(26.6, abs=1e-9)
    assert result.worst_case.half_range == pytest.approx(0.15, abs=1e-12)


def test_face_table_round_trips_as_selectors(model: StepModel) -> None:
    """Every row of face_table() is a selector that resolves to its own face."""
    rows = face_table(model)
    assert len(rows) == 12
    assert {
        "part": "PLATE",
        "face": 5,
        "centroid": [25.0, 15.0, 26.6],
        "normal": [0.0, 0.0, 1.0],
        "area": 1500.0,
    } in rows
    annotations = [
        {
            "id": chr(ord("A") + i),
            "kind": "datum",
            "on": {k: r[k] for k in ("part", "face", "centroid", "normal")},
        }
        for i, r in enumerate(rows)
    ]
    resolved = resolve_annotations(
        model, parse_annotations({"schema_version": 1, "units": "mm", "annotations": annotations})
    )
    assert [(ref.part, ref.face_index) for _d, ref in resolved.datums] == [
        (r["part"], r["face"]) for r in rows
    ]


def test_fingerprint_mismatch_is_rejected(model: StepModel) -> None:
    """A stale file (geometry changed by 0.1 mm) must not bind to the face."""
    d = doc()
    d["annotations"][0]["to"] = {**PLATE_TOP, "centroid": [25.0, 15.0, 26.7]}
    (msg,) = errors(model, d)
    assert msg.startswith("annotations[0].to.centroid:") and "does not match" in msg

    d = doc()
    d["annotations"][0]["from"] = {**PLATE_BOTTOM, "normal": [0, 0, 1]}
    (msg,) = errors(model, d)
    assert msg.startswith("annotations[0].from.normal:")

    d = doc()  # right fingerprint, wrong index
    d["annotations"][2]["on"] = {**PLATE_TOP, "face": 4}
    (msg,) = errors(model, d)
    assert msg.startswith("annotations[2].on.")


def test_a_small_fingerprint_difference_is_tolerated(model: StepModel) -> None:
    """Within the default 1e-6 mm centroid tolerance; outside a tightened one."""
    d = doc()
    d["annotations"][0]["to"] = {**PLATE_TOP, "centroid": [25.0, 15.0, 26.6 + 5e-7]}
    parsed = parse_annotations(d)
    assert resolve_annotations(model, parsed).dimensions[0].nominal == pytest.approx(16.6, abs=1e-9)
    with pytest.raises(AnnotationError):
        resolve_annotations(model, parsed, centroid_tol=1e-8)
    d["annotations"][0]["to"] = {**PLATE_TOP, "normal": [0, 0, 3]}  # un-normalised is fine
    resolve_annotations(model, parse_annotations(d))


def test_model_mismatches_name_the_field(model: StepModel) -> None:
    d = doc()
    d["annotations"][0]["from"] = {**PLATE_BOTTOM, "part": "LID"}
    assert errors(model, d)[0].startswith("annotations[0].from.part:")

    d = doc()
    d["annotations"][0]["from"] = {**PLATE_BOTTOM, "face": 6}
    assert errors(model, d)[0].startswith("annotations[0].from.face:")

    d = doc()
    d["annotations"][0]["to"] = PLATE_SIDE
    (msg,) = errors(model, d)
    assert msg.startswith("annotations[0]:") and "not parallel" in msg

    d = doc()
    d["annotations"][1]["nominal"] = 10.5
    (msg,) = errors(model, d)
    assert msg.startswith("annotations[1].nominal:") and "measures 10.0" in msg

    d = doc()
    d["annotations"][3]["on"] = {**BASE_BOTTOM, "normal": [0, 0, 0]}
    assert errors(model, d)[0].startswith("annotations[3].on.normal:")


@pytest.mark.parametrize(
    ("mutate", "prefix"),
    [
        (lambda d: d.pop("units"), "units:"),
        (lambda d: d.update(units="inch"), "units:"),
        (lambda d: d.update(schema_version=2), "schema_version:"),
        (lambda d: d.update(annotations=[]), "annotations:"),
        (lambda d: d["annotations"][0].update(kind="roundness"), "annotations[0]"),
        (lambda d: d["annotations"][0].pop("to"), "annotations[0].to:"),
        (lambda d: d["annotations"][0].update(upper_tol="big"), "annotations[0].upper_tol:"),
        (lambda d: d["annotations"][0]["from"].update(face=-1), "annotations[0].from.face:"),
        (
            lambda d: d["annotations"][0]["from"].update(centroid=[1, 2]),
            "annotations[0].from.centroid:",
        ),
        (lambda d: d["annotations"][2].update(tolerance=0), "annotations[2].tolerance:"),
        (lambda d: d["annotations"][3].update(id="datum_a"), "annotations[3].id:"),
        (lambda d: d["annotations"][0].update(extra=1), "annotations[0].extra:"),
        (lambda d: d["annotations"][1].update(id="plate_thickness"), "annotations:"),
        (lambda d: d["annotations"][0].update(upper_tol=-0.2), "annotations[0]:"),
    ],
)
def test_invalid_files_name_the_field(mutate: Any, prefix: str) -> None:
    d = copy.deepcopy(doc())
    mutate(d)
    with pytest.raises(AnnotationError) as info:
        parse_annotations(d)
    assert any(m.startswith(prefix) for m in info.value.errors), info.value.errors


def test_non_mapping_and_file_errors(tmp_path: Path) -> None:
    with pytest.raises(AnnotationError, match="mapping"):
        parse_annotations([1, 2])
    with pytest.raises(AnnotationError, match="file not found"):
        load_annotations(tmp_path / "missing.yaml")
    bad = tmp_path / "bad.yaml"
    bad.write_text("a: [1\n", encoding="utf-8")
    with pytest.raises(AnnotationError, match="not valid YAML"):
        load_annotations(bad)
    good = tmp_path / "good.yaml"
    good.write_text(yaml.safe_dump(doc()), encoding="utf-8")
    assert len(load_annotations(good).annotations) == 4
