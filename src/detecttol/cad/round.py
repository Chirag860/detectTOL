"""Round features (holes and pins): diameters, fits, positions, pin float.

A **round feature** is one cylindrical surface of one part. STEP files usually
split a full cylinder into two half faces; they are grouped here by part, radius,
axis line, inside/outside and axial extent, and the group is named by its lowest
face index (its *representative* face, used as the chain's node for the axis).

Three things are built on top:

- **Fit check** (:func:`fit_stack`): clearance ``Y = D_hole - d_shaft`` [mm], a
  two-contributor linear stack; :func:`classify_fit` names it a clearance,
  transition or interference fit from the limit sizes.
- **Pin float** (:func:`float_contributor`): a part located by a pin in a hole
  can shift across the axis by up to half the clearance. Modelled as one
  contributor ``0 +/- c_max/2`` with ``c_max = D_max - d_min`` (the largest
  clearance), **uniform** (docs/ASSUMPTIONS.md A39).
- **Position as a chain dimension** (:func:`position_dimension`): the axis of a
  hole located from a datum plane by a basic dimension, with a position zone of
  diameter ``T`` (plus the MMC/LMC bonus) -> a dimension datum face -> axis with
  ``+/- (T + B)/2`` (:class:`detecttol.gdt.models.Position`).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

from detecttol.cad.annotations import ResolvedDimension
from detecttol.cad.pmi import FaceRef
from detecttol.cad.step_reader import FaceInfo, PartInstance, StepModel
from detecttol.core.models import AnalysisConfig, Contributor, Requirement, Stack
from detecttol.gdt.models import DatumReferenceFrame, Position

Vec3 = tuple[float, float, float]
MaterialCondition = Literal["RFS", "MMC", "LMC"]
FitKind = Literal["clearance", "transition", "interference"]

#: Same radius / coaxial / same axial range, for grouping half faces [mm].
GEOMETRY_TOL_MM = 1e-6
#: Axes are parallel when 1 - |a . b| is below this.
PARALLEL_TOL = 1e-9


class RoundFeatureError(ValueError):
    """A round feature, diameter or position cannot be used; the message says why."""


def _dot(a: Vec3, b: Vec3) -> float:
    return math.fsum(x * y for x, y in zip(a, b, strict=True))


def _unit(v: Vec3) -> Vec3:
    n = math.sqrt(_dot(v, v))
    return (v[0] / n, v[1] / n, v[2] / n)


def line_distance(point: Vec3, axis_point: Vec3, axis: Vec3) -> float:
    """Distance [mm] from ``point`` to the line through ``axis_point`` along ``axis``."""
    a = _unit(axis)
    w = (point[0] - axis_point[0], point[1] - axis_point[1], point[2] - axis_point[2])
    t = _dot(w, a)
    return math.sqrt(max(_dot(w, w) - t * t, 0.0))


def coaxial(p1: Vec3, a1: Vec3, p2: Vec3, a2: Vec3, tol: float = GEOMETRY_TOL_MM) -> bool:
    """Two axis lines coincide (parallel and through the same points)."""
    if 1.0 - abs(_dot(_unit(a1), _unit(a2))) > PARALLEL_TOL:
        return False
    return line_distance(p2, p1, a1) <= tol


def _axial_range(face: FaceInfo, point: Vec3, axis: Vec3) -> tuple[float, float]:
    """Extent of the face along the axis, from its bounding box corners.

    Exact for an axis parallel to a coordinate axis; a superset otherwise.
    """
    a = _unit(axis)
    values = [
        _dot((x - point[0], y - point[1], z - point[2]), a)
        for x in (face.bbox_min[0], face.bbox_max[0])
        for y in (face.bbox_min[1], face.bbox_max[1])
        for z in (face.bbox_min[2], face.bbox_max[2])
    ]
    if 1.0 - max(abs(c) for c in a) > PARALLEL_TOL:
        return min(values), max(values)
    # axis along x, y or z: the bounding box gives the exact range
    k = max(range(3), key=lambda i: abs(a[i]))
    lo = (face.bbox_min[k] - point[k]) * math.copysign(1.0, a[k])
    hi = (face.bbox_max[k] - point[k]) * math.copysign(1.0, a[k])
    return min(lo, hi), max(lo, hi)


@dataclass(frozen=True)
class RoundFeature:
    """One cylindrical surface of one part (all its STEP faces).

    Attributes:
        part: part name.
        faces: STEP face indices of the surface, ascending.
        axis_point / axis: the axis line (assembly coordinates).
        radius: [mm].
        internal: ``True`` for a hole, ``False`` for a pin or boss.
        axial_range: extent along ``axis`` measured from ``axis_point`` [mm].
    """

    part: str
    faces: tuple[int, ...]
    axis_point: Vec3
    axis: Vec3
    radius: float
    internal: bool
    axial_range: tuple[float, float]

    @property
    def face(self) -> int:
        """The representative face index (the lowest)."""
        return self.faces[0]

    @property
    def diameter(self) -> float:
        return 2.0 * self.radius

    @property
    def kind(self) -> str:
        return "hole" if self.internal else "pin"

    def describe(self) -> str:
        return f"{self.part}:{self.face} ({self.kind} dia {self.diameter:g})"


def round_features(part: PartInstance) -> list[RoundFeature]:
    """The round features of one placed part, half faces grouped.

    Faces are first bucketed by side (hole / pin), radius and axis line; inside a
    bucket they are sorted along the axis and merged while their ranges touch, so
    the order of the faces in the file does not matter.
    """
    buckets: list[list[FaceInfo]] = []
    for face in part.faces:
        c = face.cylinder
        if c is None:
            continue
        for bucket in buckets:
            g = bucket[0].cylinder
            assert g is not None
            if (
                g.internal == c.internal
                and abs(g.radius - c.radius) <= GEOMETRY_TOL_MM
                and coaxial(g.axis_point, g.axis, c.axis_point, c.axis)
            ):
                bucket.append(face)
                break
        else:
            buckets.append([face])
    out = []
    for bucket in buckets:
        first = bucket[0].cylinder
        assert first is not None
        # every range in the first face's frame (same axis point and sense)
        ranged = sorted(
            ((_axial_range(f, first.axis_point, first.axis), f) for f in bucket),
            key=lambda item: item[0][0],
        )
        groups: list[tuple[list[FaceInfo], float, float]] = []
        for (lo, hi), face in ranged:
            if groups and lo <= groups[-1][2] + GEOMETRY_TOL_MM:
                faces, g_lo, g_hi = groups[-1]
                groups[-1] = ([*faces, face], g_lo, max(g_hi, hi))
            else:
                groups.append(([face], lo, hi))
        for faces, lo, hi in groups:
            out.append(
                RoundFeature(
                    part=part.name,
                    faces=tuple(sorted(f.index for f in faces)),
                    axis_point=first.axis_point,
                    axis=_unit(first.axis),
                    radius=first.radius,
                    internal=first.internal,
                    axial_range=(lo, hi),
                )
            )
    out.sort(key=lambda f: f.face)
    return out


def find_round(model: StepModel, ref: FaceRef) -> RoundFeature:
    """The round feature that face ``ref`` belongs to.

    Raises:
        RoundFeatureError: unknown part, or the face is not cylindrical.
    """
    parts = [p for p in model.parts if ref.part in (p.name, p.instance_name)]
    if len(parts) != 1:
        raise RoundFeatureError(f"part '{ref.part}': {len(parts)} parts of that name")
    for feature in round_features(parts[0]):
        if ref.face_index in feature.faces:
            return feature
    raise RoundFeatureError(f"face {ref.part}:{ref.face_index} is not a cylindrical face")


# --------------------------------------------------------------------------- #
# diameters and positions bound to the model
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ResolvedDiameter:
    """A toleranced diameter bound to a round feature.

    Attributes:
        id: e.g. ``Shaft:Diameter1``.
        part: part name.
        face: the feature's representative face index.
        nominal: diameter [mm].
        upper_tol / lower_tol: signed deviations [mm].
        internal: hole (``True``) or pin.
        fit_code: ISO 286 class when the tolerance came from one, e.g. ``g6``.
        tolerance_source / tolerance_verified / cad_source: as for dimensions.
    """

    id: str
    part: str
    face: int
    nominal: float
    upper_tol: float
    lower_tol: float
    internal: bool
    fit_code: str | None = None
    tolerance_source: str | None = None
    tolerance_verified: bool = True
    cad_source: str | None = None

    @property
    def largest(self) -> float:
        return self.nominal + self.upper_tol

    @property
    def smallest(self) -> float:
        return self.nominal + self.lower_tol

    def to_contributor(self, sensitivity: float) -> Contributor:
        return Contributor(
            id=self.id,
            nominal=self.nominal,
            upper_tol=self.upper_tol,
            lower_tol=self.lower_tol,
            sensitivity=float(sensitivity),
            distribution="normal",
            cp=1.0,
            tolerance_source=self.tolerance_source,
            tolerance_verified=self.tolerance_verified,
            cad_source=self.cad_source,
        )


@dataclass(frozen=True)
class ResolvedPosition:
    """A position tolerance on a round feature, with its datum faces.

    Attributes:
        id: e.g. ``Plate_1:Position1``.
        part: part name.
        face: the feature's representative face index.
        tolerance: diameter of the position zone ``T`` [mm].
        material_condition: ``RFS``, ``MMC`` or ``LMC``.
        datums: the planar datum faces, primary first (only planar datums are used).
        cad_source: where it was read.
        note: how datums / material condition were found, when not straight
            from the CAD model's own data (e.g. read from the frame's text).
    """

    id: str
    part: str
    face: int
    tolerance: float
    material_condition: MaterialCondition
    datums: tuple[FaceRef, ...]
    cad_source: str | None = None
    note: str | None = None


# --------------------------------------------------------------------------- #
# fit check
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class FitLimits:
    """The limit clearances of a hole/shaft pair [mm] (negative = interference)."""

    min_clearance: float
    max_clearance: float
    kind: FitKind


def classify_fit(hole: ResolvedDiameter, shaft: ResolvedDiameter) -> FitLimits:
    """Clearance fit if the smallest hole is >= the largest shaft, interference
    fit if the largest hole is <= the smallest shaft, transition fit otherwise
    (ISO 286-1 definitions)."""
    lo = round(hole.smallest - shaft.largest, 12)
    hi = round(hole.largest - shaft.smallest, 12)
    kind: FitKind
    if lo >= 0.0:
        kind = "clearance"
    elif hi <= 0.0:
        kind = "interference"
    else:
        kind = "transition"
    return FitLimits(lo, hi, kind)


def fit_stack(
    hole: ResolvedDiameter,
    shaft: ResolvedDiameter,
    *,
    lsl: float | None = 0.0,
    usl: float | None = None,
    analysis: AnalysisConfig | None = None,
    name: str | None = None,
) -> Stack:
    """Stack for the clearance ``Y = D_hole - d_shaft`` [mm].

    Default requirement: clearance >= 0 (the shaft always goes in). For an
    interference fit give e.g. ``lsl=None, usl=0``.

    Raises:
        RoundFeatureError: ``hole`` is not a hole or ``shaft`` not a pin.
    """
    if not hole.internal:
        raise RoundFeatureError(f"{hole.id}: is a pin/boss, not a hole")
    if shaft.internal:
        raise RoundFeatureError(f"{shaft.id}: is a hole, not a pin/shaft")
    return Stack(
        schema_version=1,
        units="mm",
        name=name or f"Fit {hole.id} / {shaft.id}",
        requirement=Requirement(
            description=(
                f"Clearance between hole {hole.id} (dia {hole.nominal:g}) and shaft"
                f" {shaft.id} (dia {shaft.nominal:g}): hole diameter minus shaft diameter"
            ),
            lsl=lsl,
            usl=usl,
        ),
        contributors=[hole.to_contributor(1.0), shaft.to_contributor(-1.0)],
        analysis=analysis or AnalysisConfig(),
    )


# --------------------------------------------------------------------------- #
# pin float and position, for chains
# --------------------------------------------------------------------------- #


def float_contributor(
    hole: ResolvedDiameter, pin: ResolvedDiameter, sensitivity: float = 1.0
) -> Contributor:
    """Shift of a pin's axis inside a hole across the axis [mm] (A39).

    ``0 +/- (D_max - d_min)/2``, uniform: the axis may sit anywhere the largest
    clearance allows, with no preferred side. Worst case is exact. The
    statistical result is conservative only for a zero-mean scatter (the actual
    clearance is usually smaller than the largest one); if assembly pushes the
    parts to one side, the float is a bias and RSS / Monte Carlo can understate
    it: then use the worst case.

    Raises:
        RoundFeatureError: the largest hole is smaller than the smallest pin
            (the pin never fits; use the fit check).
    """
    c_max = round(hole.largest - pin.smallest, 12)
    if c_max < 0.0:
        raise RoundFeatureError(
            f"{pin.id} (dia {pin.nominal:g} {pin.upper_tol:+g}/{pin.lower_tol:+g}) never fits"
            f" in {hole.id} (dia {hole.nominal:g} {hole.upper_tol:+g}/{hole.lower_tol:+g})"
        )
    half = c_max / 2.0
    return Contributor(
        id=f"float {pin.id} in {hole.id}",
        nominal=0.0,
        upper_tol=half,
        lower_tol=-half,
        sensitivity=float(sensitivity),
        distribution="uniform",
        cp=1.0,
        tolerance_source=(
            f"pin float: (largest hole {hole.largest:g} - smallest pin {pin.smallest:g})/2,"
            " uniform (A39)"
        ),
        tolerance_verified=hole.tolerance_verified and pin.tolerance_verified,
        cad_source=f"{hole.cad_source or hole.id}; {pin.cad_source or pin.id}",
    )


def position_dimension(
    position: ResolvedPosition,
    datum: FaceRef,
    distance: float,
    direction: Vec3,
    size: ResolvedDiameter | None,
) -> ResolvedDimension:
    """The position as a dimension from ``datum`` to the feature's axis.

    The basic distance ``distance`` [mm] is exact; the axis may deviate by
    ``+/- T/2`` across it (RFS), or by ``+/- (T + B)/2`` with the MMC/LMC bonus,
    linearised as :meth:`detecttol.gdt.models.Position.to_contributor` does
    (same worst case; sigma from ``E[(T + B)^2]``).

    Raises:
        RoundFeatureError: MMC/LMC without a toleranced size.
    """
    if position.material_condition != "RFS" and size is None:
        raise RoundFeatureError(
            f"{position.id}: {position.material_condition} needs the hole's toleranced diameter"
        )
    feature = None if size is None else ("hole" if size.internal else "pin")
    callout = Position(
        id=position.id,
        tolerance=position.tolerance,
        datums=DatumReferenceFrame(primary="A"),  # labels do not enter the result
        material_condition=position.material_condition,
        feature=feature if position.material_condition != "RFS" else None,
        size_contributor=size.id if (size and position.material_condition != "RFS") else None,
    )
    contributor = callout.to_contributor(
        None if size is None or position.material_condition == "RFS" else size.to_contributor(0.0)
    )
    bonus = (
        "" if position.material_condition == "RFS" else f" + bonus at {position.material_condition}"
    )
    return ResolvedDimension(
        id=position.id,
        nominal=round(abs(distance), 9),
        upper_tol=contributor.upper_tol,
        lower_tol=contributor.lower_tol,
        distribution="normal",
        cp=contributor.cp,
        from_face=datum,
        to_face=FaceRef(part=position.part, face_index=position.face),
        direction=direction,
        tolerance_source=(
            f"position dia {position.tolerance:g}{bonus} -> +/-{contributor.upper_tol:g}"
            " across the axis"
        ),
        tolerance_verified=size.tolerance_verified if size is not None else True,
        cad_source=position.cad_source,
    )
