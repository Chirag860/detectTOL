"""YAML annotation file: attach tolerances to faces of a STEP model (spec Phase 5).

The fallback for STEP files without usable semantic PMI. A face is identified
by a stable triple and all three parts are checked:

- ``part``: part name,
- ``face``: 0-based face index within the part (``TopExp_Explorer`` order),
- a fingerprint: the face's centroid [mm] and outward normal, in assembly
  coordinates. If the geometry changed since the file was written, the
  fingerprint no longer matches and the annotation is rejected instead of
  silently landing on another face.

Example::

    schema_version: 1
    units: mm
    annotations:
      - id: plate_thickness
        kind: dimension
        from: {part: PLATE, face: 4, centroid: [25, 15, 10], normal: [0, 0, -1]}
        to:   {part: PLATE, face: 5, centroid: [25, 15, 26.6], normal: [0, 0, 1]}
        upper_tol: 0.05
        lower_tol: -0.05
      - id: top_flatness
        kind: flatness
        on: {part: PLATE, face: 5, centroid: [25, 15, 26.6], normal: [0, 0, 1]}
        tolerance: 0.04
      - id: A
        kind: datum
        on: {part: BASE, face: 4, centroid: [25, 15, 0], normal: [0, 0, -1]}
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from detecttol.cad.step_reader import FaceInfo, FaceRef, StepModel
from detecttol.core.models import Contributor, Distribution, FiniteFloat
from detecttol.gdt.models import DatumLabel, Flatness, PlanarDatum

_STRICT = ConfigDict(strict=True, extra="forbid", frozen=True, populate_by_name=True)

#: Default fingerprint tolerance on each centroid coordinate [mm].
CENTROID_TOL_MM = 1e-6
#: A fingerprint normal must agree with the face normal to within this (1 - cos).
NORMAL_TOL = 1e-9
#: Two faces count as parallel when |n1 . n2| >= 1 - PARALLEL_TOL.
PARALLEL_TOL = 1e-9
#: A stated nominal must equal the measured distance to within this [mm].
NOMINAL_TOL_MM = 1e-6

Triple = Annotated[list[FiniteFloat], Field(min_length=3, max_length=3)]


class AnnotationError(ValueError):
    """The annotation file is invalid or does not match the STEP model.

    ``errors`` holds one message per problem, each starting with the field path.
    """

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("; ".join(errors))


class FaceSelector(BaseModel):
    """Identifies one planar face: part name, face index and geometric fingerprint."""

    model_config = _STRICT

    part: Annotated[str, Field(min_length=1)]
    face: Annotated[int, Field(ge=0)]
    centroid: Triple
    normal: Triple


class DimensionAnnotation(BaseModel):
    """A toleranced distance between two parallel planar faces.

    ``nominal`` is optional; the distance is always measured on the model and a
    stated nominal must agree with it.
    """

    model_config = _STRICT

    id: Annotated[str, Field(min_length=1)]
    kind: Literal["dimension"]
    from_face: FaceSelector = Field(alias="from")
    to_face: FaceSelector = Field(alias="to")
    upper_tol: FiniteFloat
    lower_tol: FiniteFloat
    nominal: FiniteFloat | None = None
    distribution: Distribution = "normal"
    cp: Annotated[float, Field(gt=0.0, allow_inf_nan=False)] = 1.0


class FlatnessAnnotation(BaseModel):
    """Flatness of one planar face, zone width ``tolerance`` [mm]."""

    model_config = _STRICT

    id: Annotated[str, Field(min_length=1)]
    kind: Literal["flatness"]
    on: FaceSelector
    tolerance: Annotated[float, Field(gt=0.0, allow_inf_nan=False)]
    cp: Annotated[float, Field(gt=0.0, allow_inf_nan=False)] = 1.0


class DatumAnnotation(BaseModel):
    """A planar datum feature; ``id`` is the datum letter."""

    model_config = _STRICT

    id: DatumLabel
    kind: Literal["datum"]
    on: FaceSelector


Annotation = Annotated[
    DimensionAnnotation | FlatnessAnnotation | DatumAnnotation, Field(discriminator="kind")
]


class AnnotationFile(BaseModel):
    """The whole annotation document. All lengths are millimetres."""

    model_config = _STRICT

    schema_version: Literal[1]
    units: Literal["mm"]
    annotations: Annotated[list[Annotation], Field(min_length=1)]


@dataclass(frozen=True)
class ResolvedDimension:
    """A dimension annotation bound to two faces of the model.

    Attributes:
        id: annotation id.
        nominal: measured distance between the two planes [mm] (>= 0).
        upper_tol / lower_tol: signed deviations [mm].
        distribution, cp: as given.
        from_face / to_face: the two faces.
        direction: unit normal of ``from_face``'s plane pointing towards
            ``to_face`` (assembly coordinates).
    """

    id: str
    nominal: float
    upper_tol: float
    lower_tol: float
    distribution: Distribution
    cp: float
    from_face: FaceRef
    to_face: FaceRef
    direction: tuple[float, float, float]

    def to_contributor(self, sensitivity: float) -> Contributor:
        """This dimension as a stack contributor with the given sensitivity."""
        return Contributor(
            id=self.id,
            nominal=self.nominal,
            upper_tol=self.upper_tol,
            lower_tol=self.lower_tol,
            sensitivity=float(sensitivity),
            distribution=self.distribution,
            cp=self.cp,
        )


@dataclass(frozen=True)
class ResolvedAnnotations:
    """Annotations bound to a STEP model."""

    dimensions: tuple[ResolvedDimension, ...]
    flatness: tuple[tuple[Flatness, FaceRef], ...]
    datums: tuple[tuple[PlanarDatum, FaceRef], ...]


def _loc(parts: tuple[int | str, ...]) -> str:
    out = ""
    for part in parts:
        if isinstance(part, int):
            out += f"[{part}]"
        elif part.isidentifier() and part not in ("dimension", "flatness", "datum"):
            out += f".{part}" if out else part
    return out or "(root)"


def parse_annotations(data: Any) -> AnnotationFile:
    """Validate parsed YAML data.

    Raises:
        AnnotationError: one field-named message per problem.
    """
    if not isinstance(data, dict):
        raise AnnotationError(["(root): the document must be a mapping of fields"])
    try:
        doc = AnnotationFile.model_validate(data)
    except ValidationError as exc:
        raise AnnotationError(
            [
                f"{_loc(tuple(e['loc']))}: {str(e['msg']).removeprefix('Value error, ')}"
                for e in exc.errors()
            ]
        ) from exc
    ids = [a.id for a in doc.annotations]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        raise AnnotationError([f"annotations: duplicate id(s) {dupes}"])
    for i, a in enumerate(doc.annotations):
        if isinstance(a, DimensionAnnotation) and a.upper_tol < a.lower_tol:
            raise AnnotationError(
                [
                    f"annotations[{i}]: upper_tol ({a.upper_tol}) must be >="
                    f" lower_tol ({a.lower_tol})"
                ]
            )
    return doc


def load_annotations(path: str | Path) -> AnnotationFile:
    """Read and validate an annotation YAML file.

    Raises:
        AnnotationError: file not found, invalid YAML or failing validation.
    """
    p = Path(path)
    if not p.is_file():
        raise AnnotationError([f"file not found: {p}"])
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise AnnotationError([f"{p}: not valid YAML ({exc})"]) from exc
    return parse_annotations(data)


def _match(
    model: StepModel, selector: FaceSelector, where: str, centroid_tol: float
) -> tuple[FaceRef, FaceInfo]:
    try:
        part = model.part(selector.part)
    except KeyError as exc:
        raise AnnotationError([f"{where}.part: {exc.args[0]}"]) from exc
    if selector.face >= len(part.faces):
        raise AnnotationError(
            [f"{where}.face: part '{part.name}' has {len(part.faces)} faces, index {selector.face}"]
        )
    face = part.faces[selector.face]
    if not face.is_planar or face.normal is None:
        raise AnnotationError(
            [
                f"{where}.face: face {selector.face} of '{part.name}' is a {face.surface},"
                " not a plane"
            ]
        )
    if any(
        abs(a - b) > centroid_tol for a, b in zip(selector.centroid, face.centroid, strict=True)
    ):
        raise AnnotationError(
            [
                f"{where}.centroid: fingerprint {list(selector.centroid)} does not match face"
                f" {selector.face} of '{part.name}'"
                f" (centroid {[round(c, 9) for c in face.centroid]})"
            ]
        )
    length = math.sqrt(math.fsum(c * c for c in selector.normal))
    if length == 0.0:
        raise AnnotationError([f"{where}.normal: must not be the zero vector"])
    cosine = math.fsum(a * b for a, b in zip(selector.normal, face.normal, strict=True)) / length
    if 1.0 - cosine > NORMAL_TOL:
        raise AnnotationError(
            [
                f"{where}.normal: fingerprint {list(selector.normal)} does not match face"
                f" {selector.face} of '{part.name}' (normal {[round(c, 9) for c in face.normal]})"
            ]
        )
    return FaceRef(part=part.name, face_index=face.index), face


def resolve_annotations(
    model: StepModel, doc: AnnotationFile, centroid_tol: float = CENTROID_TOL_MM
) -> ResolvedAnnotations:
    """Bind every annotation to faces of ``model`` and measure the dimensions.

    Args:
        model: the STEP model.
        doc: the validated annotation file.
        centroid_tol: allowed difference per centroid coordinate [mm].

    Raises:
        AnnotationError: unknown part, face index out of range, non-planar face,
            fingerprint mismatch, non-parallel faces, or a stated nominal that
            differs from the measured distance.
    """
    dimensions: list[ResolvedDimension] = []
    flatness: list[tuple[Flatness, FaceRef]] = []
    datums: list[tuple[PlanarDatum, FaceRef]] = []
    for i, annotation in enumerate(doc.annotations):
        where = f"annotations[{i}]"
        if isinstance(annotation, DimensionAnnotation):
            ref_a, face_a = _match(model, annotation.from_face, f"{where}.from", centroid_tol)
            ref_b, face_b = _match(model, annotation.to_face, f"{where}.to", centroid_tol)
            assert face_a.normal is not None and face_b.normal is not None
            dot = math.fsum(a * b for a, b in zip(face_a.normal, face_b.normal, strict=True))
            if abs(dot) < 1.0 - PARALLEL_TOL:
                raise AnnotationError(
                    [f"{where}: the two faces are not parallel (n1 . n2 = {dot:.9f})"]
                )
            delta = [b - a for a, b in zip(face_a.centroid, face_b.centroid, strict=True)]
            signed = math.fsum(d * n for d, n in zip(delta, face_a.normal, strict=True))
            distance = abs(signed)
            if (
                annotation.nominal is not None
                and abs(annotation.nominal - distance) > NOMINAL_TOL_MM
            ):
                raise AnnotationError(
                    [
                        f"{where}.nominal: stated {annotation.nominal} mm but the model"
                        f" measures {distance:.9f} mm"
                    ]
                )
            sign = 1.0 if signed >= 0 else -1.0
            dimensions.append(
                ResolvedDimension(
                    id=annotation.id,
                    nominal=distance,
                    upper_tol=annotation.upper_tol,
                    lower_tol=annotation.lower_tol,
                    distribution=annotation.distribution,
                    cp=annotation.cp,
                    from_face=ref_a,
                    to_face=ref_b,
                    direction=(
                        sign * face_a.normal[0],
                        sign * face_a.normal[1],
                        sign * face_a.normal[2],
                    ),
                )
            )
        elif isinstance(annotation, FlatnessAnnotation):
            ref, _face = _match(model, annotation.on, f"{where}.on", centroid_tol)
            flatness.append(
                (Flatness(id=annotation.id, tolerance=annotation.tolerance, cp=annotation.cp), ref)
            )
        else:
            ref, _face = _match(model, annotation.on, f"{where}.on", centroid_tol)
            datums.append((PlanarDatum(label=annotation.id), ref))
    return ResolvedAnnotations(
        dimensions=tuple(dimensions), flatness=tuple(flatness), datums=tuple(datums)
    )


def face_table(model: StepModel) -> list[dict[str, Any]]:
    """Selectors for every planar face of the model, ready to paste into a file.

    Each entry is ``{"part", "face", "centroid", "normal", "area"}``; centroid
    and normal are rounded to 9 decimals.
    """
    rows = []
    for part in model.parts:
        for face in part.planar_faces():
            assert face.normal is not None
            rows.append(
                {
                    "part": part.name,
                    "face": face.index,
                    "centroid": [round(c, 9) + 0.0 for c in face.centroid],
                    "normal": [round(c, 9) + 0.0 for c in face.normal],
                    "area": round(face.area, 6),
                }
            )
    return rows
