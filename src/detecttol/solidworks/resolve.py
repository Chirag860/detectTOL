"""SolidWorks read-out -> faces of the STEP geometry copy -> resolved dimensions.

Each :class:`~detecttol.solidworks.model.SwFace` is matched to exactly one planar
face of the same part in the :class:`~detecttol.cad.step_reader.StepModel` built
from the STEP copy SolidWorks wrote: same outward normal, centroid within
``centroid_tol`` and area within ``area_rel_tol``. Anything else is an error that
names the face, never a guess.

A cylindrical face (:class:`~detecttol.solidworks.model.SwCylinder`) cannot be
matched by centroid: the STEP copy splits a full cylinder into two half faces.
It is matched to the one round feature of the same part with the same radius
and axis line (:func:`match_cylinder`), using the centroid's position along the
axis only to tell apart equal coaxial cylinders.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from detecttol.cad.annotations import ResolvedDimension
from detecttol.cad.pmi import FaceRef
from detecttol.cad.round import (
    ResolvedDiameter,
    ResolvedPosition,
    RoundFeature,
    coaxial,
    round_features,
)
from detecttol.cad.step_reader import FaceInfo, StepModel
from detecttol.gdt.models import Flatness
from detecttol.solidworks.model import (
    SwAssemblyData,
    SwCylinder,
    SwDiameter,
    SwDimension,
    SwFace,
    SwPosition,
)
from detecttol.standards.lookup import look_up

#: Centroid match tolerance [mm]; SolidWorks centroids come from its tessellation.
CENTROID_TOL_MM = 1e-3
#: Relative area match tolerance.
AREA_REL_TOL = 1e-3
#: Normals match when n1 . n2 >= 1 - NORMAL_TOL.
NORMAL_TOL = 1e-6
#: A SolidWorks nominal must agree with the distance measured on the STEP copy [mm].
NOMINAL_TOL_MM = 1e-4
#: Two dimensions on the same face pair agree when their deviations differ less [mm].
SAME_TOL_MM = 1e-9
#: Radius and axis-line match for cylinders [mm].
CYLINDER_TOL_MM = 1e-5


class SolidWorksResolveError(ValueError):
    """A SolidWorks face or dimension cannot be tied to the STEP geometry."""


@dataclass(frozen=True)
class ResolvedSolidWorks:
    """The read-out tied to the STEP geometry.

    Attributes:
        dimensions: one per toleranced face pair (duplicates merged).
        flatness: flatness callouts with the face they sit on.
        notes: what was skipped or merged, and why.
    """

    dimensions: tuple[ResolvedDimension, ...]
    flatness: tuple[tuple[Flatness, FaceRef], ...]
    notes: tuple[str, ...]
    diameters: tuple[ResolvedDiameter, ...] = ()
    positions: tuple[ResolvedPosition, ...] = ()


def _dot(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return math.fsum(x * y for x, y in zip(a, b, strict=True))


def match_face(
    model: StepModel,
    face: SwFace,
    *,
    centroid_tol: float = CENTROID_TOL_MM,
    area_rel_tol: float = AREA_REL_TOL,
) -> tuple[FaceRef, FaceInfo]:
    """The one planar STEP face that is ``face``.

    Raises:
        SolidWorksResolveError: the part is not in the STEP copy, or zero or
            several faces match.
    """
    parts = [p for p in model.parts if p.name == face.part]
    if len(parts) != 1:
        raise SolidWorksResolveError(
            f"part '{face.part}': {len(parts)} parts of that name in the STEP geometry"
            " (a part used more than once is not supported yet)"
        )
    hits = [
        f
        for f in parts[0].faces
        if f.normal is not None
        and _dot(f.normal, face.normal) >= 1.0 - NORMAL_TOL
        and math.dist(f.centroid, face.centroid) <= centroid_tol
        and abs(f.area - face.area) <= area_rel_tol * max(face.area, 1e-12)
    ]
    where = (
        f"face of '{face.part}' with normal {tuple(round(v, 6) for v in face.normal)},"
        f" centroid {tuple(round(v, 6) for v in face.centroid)} mm, area {face.area:.6g} mm^2"
    )
    if not hits:
        raise SolidWorksResolveError(f"{where}: no matching face in the STEP geometry")
    if len(hits) > 1:
        raise SolidWorksResolveError(
            f"{where}: {len(hits)} matching faces in the STEP geometry ({[f.index for f in hits]})"
        )
    return FaceRef(part=face.part, face_index=hits[0].index), hits[0]


def match_cylinder(model: StepModel, cyl: SwCylinder) -> RoundFeature:
    """The one round feature of ``model`` that is the SolidWorks face ``cyl``.

    Raises:
        SolidWorksResolveError: no or several matching features.
    """
    parts = [p for p in model.parts if p.name == cyl.part]
    if len(parts) != 1:
        raise SolidWorksResolveError(
            f"part '{cyl.part}': {len(parts)} parts of that name in the STEP geometry"
        )
    hits = [
        f
        for f in round_features(parts[0])
        if abs(f.radius - cyl.radius) <= CYLINDER_TOL_MM
        and coaxial(f.axis_point, f.axis, cyl.axis_point, cyl.axis, CYLINDER_TOL_MM)
    ]
    if len(hits) > 1:
        along = [
            f
            for f in hits
            if f.axial_range[0] - CYLINDER_TOL_MM
            <= sum((c - a) * u for c, a, u in zip(cyl.centroid, f.axis_point, f.axis, strict=True))
            <= f.axial_range[1] + CYLINDER_TOL_MM
        ]
        hits = along or hits
    where = (
        f"cylinder of '{cyl.part}' (radius {cyl.radius:.6g} mm, axis through"
        f" {tuple(round(v, 6) for v in cyl.axis_point)})"
    )
    if not hits:
        raise SolidWorksResolveError(f"{where}: no matching face in the STEP geometry")
    if len(hits) > 1:
        raise SolidWorksResolveError(
            f"{where}: {len(hits)} matching round features ({[f.face for f in hits]})"
        )
    return hits[0]


def _feature_of(model: StepModel, name: str, faces: tuple[SwCylinder, ...]) -> RoundFeature:
    features = {match_cylinder(model, c) for c in faces}
    if len(features) != 1:
        raise SolidWorksResolveError(f"{name}: its faces are {len(features)} different cylinders")
    return features.pop()


def _resolve_diameter(
    model: StepModel, dia: SwDiameter, notes: list[str]
) -> ResolvedDiameter | None:
    feature = _feature_of(model, dia.name, dia.faces)
    if abs(feature.diameter - dia.nominal) > NOMINAL_TOL_MM:
        raise SolidWorksResolveError(
            f"{dia.name}: SolidWorks says dia {dia.nominal:.9g} mm but the face is"
            f" dia {feature.diameter:.9g} mm in the STEP geometry"
        )
    if dia.internal is not None and dia.internal != feature.internal:
        raise SolidWorksResolveError(
            f"{dia.name}: SolidWorks calls it a {'hole' if dia.internal else 'boss'} but the"
            f" STEP geometry shows a {feature.kind}"
        )
    source = f"SolidWorks DimXpert {dia.name} ({dia.document})"
    table_source: str | None = None
    verified = True
    nominal = round(feature.diameter, 9)
    if dia.fit_code and dia.fit_code[0].isupper() != feature.internal:
        wanted = "upper-case (hole)" if feature.internal else "lower-case (shaft)"
        notes.append(
            f"{dia.name}: fit {dia.fit_code} on a {feature.kind}; a {feature.kind} needs a"
            f" {wanted} class; treated as missing"
        )
        return None
    if dia.fit_code:
        try:
            found = look_up(nominal, dia.fit_code, None)
        except ValueError as exc:
            notes.append(f"{dia.name}: fit {dia.fit_code}: {exc}; treated as missing")
            return None
        upper, lower = found.upper_tol, found.lower_tol
        table_source, verified = found.source, found.verified
        if dia.fit_from == "display":
            source += "; fit code read from the dimension's display"
    elif dia.upper is not None and dia.lower is not None:
        upper, lower = dia.upper, dia.lower
    else:
        notes.append(f"{dia.name}: no plus/minus tolerance and no fit code; treated as missing")
        return None
    if upper < lower:
        raise SolidWorksResolveError(f"{dia.name}: upper {upper} < lower {lower}")
    return ResolvedDiameter(
        id=f"{dia.part}:{dia.name.split('@')[0]}",
        part=dia.part,
        face=feature.face,
        nominal=nominal,
        upper_tol=upper,
        lower_tol=lower,
        internal=feature.internal,
        fit_code=dia.fit_code,
        tolerance_source=table_source,
        tolerance_verified=verified,
        cad_source=source,
    )


def _resolve_position(
    model: StepModel,
    pos: SwPosition,
    datum_faces: dict[tuple[str, str], FaceRef],
    notes: list[str],
) -> ResolvedPosition:
    feature = _feature_of(model, pos.name, pos.faces)
    refs = []
    for label in pos.datums:
        ref = datum_faces.get((pos.part, label))
        if ref is None:
            notes.append(f"{pos.part}: {pos.name} refers to datum {label}, not found on a plane")
            continue
        refs.append(ref)
    note = None
    if pos.found_in == "frame":
        note = (
            "material condition / datums read from the tolerance frame's text, not from"
            " DimXpert's own data; check them in the model"
        )
        notes.append(f"{pos.part}: {pos.name}: {note}")
    return ResolvedPosition(
        id=f"{pos.part}:{pos.name.split('@')[0]}",
        part=pos.part,
        face=feature.face,
        tolerance=pos.value,
        material_condition=pos.material_condition,  # type: ignore[arg-type]
        datums=tuple(refs),
        cad_source=f"SolidWorks DimXpert {pos.name}",
        note=note,
    )


def _source_text(dim: SwDimension) -> str:
    where = "DimXpert" if dim.source == "dimxpert" else "drawing"
    return f"SolidWorks {where} {dim.name} ({dim.document})"


def _resolve_dimension(
    model: StepModel, dim: SwDimension, notes: list[str]
) -> ResolvedDimension | None:
    (ref_a, face_a), (ref_b, face_b) = (match_face(model, f) for f in dim.faces)
    assert face_a.normal is not None and face_b.normal is not None
    if abs(_dot(face_a.normal, face_b.normal)) < 1.0 - NORMAL_TOL:
        raise SolidWorksResolveError(f"{dim.name}: its two faces are not parallel")
    delta = tuple(b - a for a, b in zip(face_a.centroid, face_b.centroid, strict=True))
    signed = _dot(delta, face_a.normal)  # type: ignore[arg-type]
    distance = abs(signed)
    if abs(distance - dim.nominal) > NOMINAL_TOL_MM:
        raise SolidWorksResolveError(
            f"{dim.name}: SolidWorks says {dim.nominal:.9g} mm but the faces are"
            f" {distance:.9g} mm apart in the STEP geometry"
        )
    source = _source_text(dim)
    table_source: str | None = None
    verified = True
    if dim.upper is not None and dim.lower is not None:
        upper, lower = dim.upper, dim.lower
    elif dim.fit_code:
        found = look_up(round(distance, 9), dim.fit_code, None)
        upper, lower = found.upper_tol, found.lower_tol
        table_source, verified = found.source, found.verified
    else:
        notes.append(f"{dim.name}: no plus/minus tolerance and no fit code; treated as missing")
        return None
    if upper < lower:
        raise SolidWorksResolveError(f"{dim.name}: upper {upper} < lower {lower}")
    sign = 1.0 if signed >= 0 else -1.0
    return ResolvedDimension(
        id=f"{dim.part}:{dim.name.split('@')[0]}",
        nominal=round(distance, 9),
        upper_tol=upper,
        lower_tol=lower,
        distribution="normal",
        cp=1.0,
        from_face=ref_a,
        to_face=ref_b,
        direction=(sign * face_a.normal[0], sign * face_a.normal[1], sign * face_a.normal[2]),
        tolerance_source=table_source,
        tolerance_verified=verified,
        cad_source=source,
        is_size=dim.is_size,
    )


def resolve(data: SwAssemblyData, model: StepModel) -> ResolvedSolidWorks:
    """Tie every dimension and flatness of ``data`` to faces of ``model``.

    Two dimensions on the same face pair (e.g. DimXpert and a drawing) are merged
    when their tolerances agree and refused when they differ.

    Raises:
        SolidWorksResolveError: unmatched face, inconsistent nominal or
            conflicting tolerances.
    """
    notes = list(data.notes)
    by_pair: dict[tuple[str, frozenset[int]], ResolvedDimension] = {}
    for dim in data.dimensions:
        resolved = _resolve_dimension(model, dim, notes)
        if resolved is None:
            continue
        key = (
            resolved.from_face.part,
            frozenset((resolved.from_face.face_index, resolved.to_face.face_index)),
        )
        other = by_pair.get(key)
        if other is None:
            by_pair[key] = resolved
            continue
        same = (
            abs(other.upper_tol - resolved.upper_tol) <= SAME_TOL_MM
            and abs(other.lower_tol - resolved.lower_tol) <= SAME_TOL_MM
        )
        if not same:
            raise SolidWorksResolveError(
                f"two different tolerances on the same faces of '{resolved.from_face.part}':"
                f" {other.cad_source}: {other.upper_tol:+g}/{other.lower_tol:+g};"
                f" {resolved.cad_source}: {resolved.upper_tol:+g}/{resolved.lower_tol:+g}"
            )
        notes.append(f"{resolved.cad_source} repeats {other.cad_source}; used once")
    flatness: list[tuple[Flatness, FaceRef]] = []
    for flat in data.flatness:
        ref, _face = match_face(model, flat.face)
        callout = Flatness(id=f"{flat.part}:{flat.name.split('@')[0]}", tolerance=flat.value)
        flatness.append((callout, ref))
    diameters: dict[tuple[str, int], ResolvedDiameter] = {}
    for dia in data.diameters:
        resolved_dia = _resolve_diameter(model, dia, notes)
        if resolved_dia is None:
            continue
        key = (resolved_dia.part, resolved_dia.face)
        other_dia = diameters.get(key)
        if other_dia is None:
            diameters[key] = resolved_dia
        elif (
            abs(other_dia.upper_tol - resolved_dia.upper_tol) > SAME_TOL_MM
            or abs(other_dia.lower_tol - resolved_dia.lower_tol) > SAME_TOL_MM
        ):
            raise SolidWorksResolveError(
                f"two different tolerances on the diameter of {key[0]}:{key[1]}:"
                f" {other_dia.cad_source} and {resolved_dia.cad_source}"
            )
    datum_faces = {
        (datum.part, datum.label): match_face(model, datum.face)[0] for datum in data.datums
    }
    positions = [_resolve_position(model, pos, datum_faces, notes) for pos in data.positions]
    return ResolvedSolidWorks(
        dimensions=tuple(by_pair.values()),
        flatness=tuple(flatness),
        notes=tuple(notes),
        diameters=tuple(diameters.values()),
        positions=tuple(positions),
    )
