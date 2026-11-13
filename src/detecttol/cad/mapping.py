"""Map PMI read from STEP onto the contributor and GD&T models (spec Phase 5).

Only the Phase 4 subset is mapped. Everything else raises
:class:`PmiMappingError` naming the item, so nothing is dropped silently.
The stack direction (sensitivity) is not in the PMI; the caller supplies it.
"""

from __future__ import annotations

from detecttol.cad.step_reader import PmiDimension, PmiGeomTolerance, StepModel
from detecttol.core.models import Contributor, Distribution
from detecttol.gdt.models import (
    DatumReferenceFrame,
    FeatureType,
    Flatness,
    MaterialCondition,
    Orientation,
    Parallelism,
    Position,
)

#: OCCT geometric-tolerance kinds that have a Phase 4 model.
SUPPORTED_GEOMTOL_KINDS = frozenset(
    {"Flatness", "Parallelism", "Position", "Perpendicularity", "Angularity"}
)
_ANGULAR_DIMENSION_KINDS = frozenset({"Location_Angular", "Size_Angular"})
_MATERIAL: dict[str | None, MaterialCondition] = {None: "RFS", "M": "MMC", "L": "LMC"}


class PmiMappingError(ValueError):
    """A PMI item cannot be expressed in the supported model subset."""


def dimension_to_contributor(
    dimension: PmiDimension,
    *,
    cid: str,
    sensitivity: float,
    distribution: Distribution = "normal",
    cp: float = 1.0,
) -> Contributor:
    """A toleranced linear dimension [mm] as a stack :class:`Contributor`.

    Args:
        dimension: a dimension with a ``plus_minus`` or ``range`` tolerance.
        cid: contributor id.
        sensitivity: a_i = dY/dx_i of this dimension in the stack (+1 / -1 in 1D).
        distribution, cp: as for any contributor.

    Raises:
        PmiMappingError: angular dimension, no tolerance, or an ISO tolerance
            class (which this tool does not convert to limits).
    """
    label = dimension.name or dimension.kind
    if dimension.kind in _ANGULAR_DIMENSION_KINDS:
        raise PmiMappingError(f"dimension '{label}': angular dimensions are not stack contributors")
    if dimension.upper_tol is None or dimension.lower_tol is None:
        raise PmiMappingError(
            f"dimension '{label}': no usable tolerance (form '{dimension.tolerance_form}')"
        )
    return Contributor(
        id=cid,
        nominal=float(dimension.value),
        upper_tol=float(dimension.upper_tol),
        lower_tol=float(dimension.lower_tol),
        sensitivity=float(sensitivity),
        distribution=distribution,
        cp=float(cp),
    )


def datum_frame(tolerance: PmiGeomTolerance) -> DatumReferenceFrame | None:
    """Datum reference frame of a tolerance (``None`` if it references no datum).

    Raises:
        PmiMappingError: more than three datum references, or labels the
            planar-datum model cannot hold.
    """
    names = tolerance.datums
    if not names:
        return None
    if len(names) > 3:
        raise PmiMappingError(
            f"geometric tolerance '{tolerance.name}': {len(names)} datum references"
            " (at most primary/secondary/tertiary are supported)"
        )
    try:
        return DatumReferenceFrame(
            primary=names[0],
            secondary=names[1] if len(names) > 1 else None,
            tertiary=names[2] if len(names) > 2 else None,
        )
    except ValueError as exc:
        raise PmiMappingError(f"geometric tolerance '{tolerance.name}': {exc}") from exc


def check_planar_datums(model: StepModel, tolerance: PmiGeomTolerance) -> None:
    """Require every datum referenced by ``tolerance`` to sit on planar faces only.

    Raises:
        PmiMappingError: a datum is unknown, has no face, or sits on a
            non-planar face (only planar datum features are supported).
    """
    by_name = {d.name: d for d in model.datums}
    faces = {(p.name, f.index): f for p in model.parts for f in p.faces}
    for name in tolerance.datums:
        datum = by_name.get(name)
        if datum is None or not datum.targets:
            raise PmiMappingError(
                f"geometric tolerance '{tolerance.name}': datum '{name}' has no face in the model"
            )
        for ref in datum.targets:
            face = faces.get((ref.part, ref.face_index))
            if face is None or not face.is_planar:
                kind = "missing" if face is None else face.surface
                raise PmiMappingError(
                    f"geometric tolerance '{tolerance.name}': datum '{name}' is on a"
                    f" {kind} face; only planar datum features are supported"
                )


def geomtol_to_callout(
    tolerance: PmiGeomTolerance,
    *,
    cid: str,
    sensitivity: float = 1.0,
    cp: float = 1.0,
    feature: FeatureType | None = None,
    size_contributor: str | None = None,
    within_size: bool | None = None,
) -> Flatness | Parallelism | Position:
    """Flatness, parallelism or position PMI as a Phase 4 callout.

    Args:
        tolerance: the PMI item.
        cid: callout id.
        sensitivity: direction factor of the deviation in the stack.
        cp: process capability.
        feature, size_contributor: required for a position tolerance with an
            MMC or LMC modifier (see :class:`detecttol.gdt.Position`).
        within_size: for flatness / parallelism, whether the tolerance is a
            refinement inside a size dimension of the stack (envelope rule) and
            therefore adds nothing. Flatness defaults to ``True``; for
            parallelism the caller must decide (not in the PMI).

    Raises:
        PmiMappingError: any other tolerance type, or missing/invalid data.
    """
    kind = tolerance.kind
    if kind not in ("Flatness", "Parallelism", "Position"):
        raise PmiMappingError(
            f"geometric tolerance '{tolerance.name}' of type {kind} is not supported"
            f" here (supported: {sorted(SUPPORTED_GEOMTOL_KINDS)})"
        )
    if tolerance.material_modifier not in _MATERIAL:
        raise PmiMappingError(
            f"geometric tolerance '{tolerance.name}': unsupported material modifier"
            f" '{tolerance.material_modifier}'"
        )
    frame = datum_frame(tolerance)
    try:
        if kind == "Flatness":
            return Flatness(
                id=cid,
                tolerance=float(tolerance.value),
                sensitivity=sensitivity,
                cp=cp,
                within_size=True if within_size is None else within_size,
            )
        if frame is None:
            raise PmiMappingError(
                f"geometric tolerance '{tolerance.name}': {kind} needs a datum reference"
            )
        if kind == "Parallelism":
            if within_size is None:
                raise PmiMappingError(
                    f"geometric tolerance '{tolerance.name}': say whether this parallelism is"
                    " inside a size dimension of the stack (within_size=True) or not"
                )
            return Parallelism(
                id=cid,
                within_size=within_size,
                tolerance=float(tolerance.value),
                sensitivity=sensitivity,
                cp=cp,
                datums=frame,
            )
        return Position(
            id=cid,
            tolerance=float(tolerance.value),
            sensitivity=sensitivity,
            cp=cp,
            datums=frame,
            material_condition=_MATERIAL[tolerance.material_modifier],
            feature=feature,
            size_contributor=size_contributor,
        )
    except PmiMappingError:
        raise
    except ValueError as exc:
        raise PmiMappingError(f"geometric tolerance '{tolerance.name}': {exc}") from exc


def geomtol_to_orientation(
    tolerance: PmiGeomTolerance, *, cid: str, feature_length: float, cp: float = 1.0
) -> Orientation:
    """Perpendicularity or angularity PMI as a Phase 4 :class:`Orientation`.

    Args:
        tolerance: the PMI item.
        cid: callout id.
        feature_length: length of the toleranced feature [mm]; not in the PMI.
        cp: process capability.

    Raises:
        PmiMappingError: other tolerance types, or no datum reference.
    """
    kinds = {"Perpendicularity": "perpendicularity", "Angularity": "angularity"}
    if tolerance.kind not in kinds:
        raise PmiMappingError(
            f"geometric tolerance '{tolerance.name}' of type {tolerance.kind} is not an"
            " orientation tolerance"
        )
    frame = datum_frame(tolerance)
    if frame is None:
        raise PmiMappingError(
            f"geometric tolerance '{tolerance.name}': {tolerance.kind} needs a datum reference"
        )
    try:
        return Orientation.model_validate(
            {
                "kind": kinds[tolerance.kind],
                "id": cid,
                "tolerance": float(tolerance.value),
                "feature_length": float(feature_length),
                "datums": frame,
                "cp": float(cp),
            }
        )
    except ValueError as exc:
        raise PmiMappingError(f"geometric tolerance '{tolerance.name}': {exc}") from exc


def unsupported_items(model: StepModel) -> list[str]:
    """One line per PMI item that has no Phase 4 model (for reporting)."""
    out = []
    for tolerance in model.geometric_tolerances:
        if tolerance.kind not in SUPPORTED_GEOMTOL_KINDS:
            out.append(f"geometric tolerance '{tolerance.name}': type {tolerance.kind}")
    for dimension in model.dimensions:
        if dimension.kind in _ANGULAR_DIMENSION_KINDS:
            out.append(f"dimension '{dimension.name}': angular")
        elif dimension.upper_tol is None:
            out.append(
                f"dimension '{dimension.name}': no tolerance (form '{dimension.tolerance_form}')"
            )
    return out
