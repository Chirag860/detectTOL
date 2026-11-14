"""SolidWorks read-out -> faces of the STEP geometry copy -> resolved dimensions.

Each :class:`~detecttol.solidworks.model.SwFace` is matched to exactly one planar
face of the same part in the :class:`~detecttol.cad.step_reader.StepModel` built
from the STEP copy SolidWorks wrote: same outward normal, centroid within
``centroid_tol`` and area within ``area_rel_tol``. Anything else is an error that
names the face, never a guess.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from detecttol.cad.annotations import ResolvedDimension
from detecttol.cad.pmi import FaceRef
from detecttol.cad.step_reader import FaceInfo, StepModel
from detecttol.gdt.models import Flatness
from detecttol.solidworks.model import SwAssemblyData, SwDimension, SwFace
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
    return ResolvedSolidWorks(
        dimensions=tuple(by_pair.values()), flatness=tuple(flatness), notes=tuple(notes)
    )
