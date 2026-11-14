"""Build a 1D tolerance stack from a STEP assembly (spec Phase 6).

The user names two planar faces. The requirement is the distance from the first
to the second along a measurement direction ``d``:

    Y = (c_to - c_from) . d                                   [mm]

The assembly is walked from the part of the first face to the part of the second
through **planar contacts**: pairs of faces of different parts with opposite
normals, lying in the same plane within a tolerance, and overlapping. Inside
each part on the way the chain uses one dimension of that part, between the face
where the chain enters and the face where it leaves. Its nominal is measured on
the model, its sensitivity is +1 if it points along ``d`` and -1 if against, and
its tolerance comes from a dimension annotation on the same two faces.

Supported: planar faces perpendicular to ``d``, translation-only stacks.
Reported, not solved: no path, several paths, non-planar contacts.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from detecttol.cad.annotations import ResolvedDimension
from detecttol.cad.pmi import FaceRef
from detecttol.cad.step_reader import FaceInfo, PartInstance, StepModel
from detecttol.core.models import Contributor

Vec3 = tuple[float, float, float]

#: Default geometric tolerance for "same plane" and "touching" [mm] (root.md Phase 6).
CONTACT_TOL_MM = 1e-6
#: Two unit vectors are (anti)parallel when 1 - |a . b| is below this.
PARALLEL_TOL = 1e-9
#: Measured nominals are rounded to this many decimals [mm] (STEP text precision).
NOMINAL_DECIMALS = 9
#: At most this many alternative paths are listed in an error message.
_MAX_PATHS_LISTED = 8


class ChainError(ValueError):
    """The dimension chain cannot be built; the message says why and what was found."""


@dataclass(frozen=True)
class Contact:
    """A planar contact: ``face_a`` of ``part_a`` touches ``face_b`` of ``part_b``.

    ``part_*`` are indices into ``StepModel.parts``; ``normal`` is the outward
    normal of ``face_a`` (so ``face_b``'s normal is its opposite).
    """

    part_a: int
    face_a: int
    part_b: int
    face_b: int
    normal: Vec3


@dataclass(frozen=True)
class ChainLink:
    """One dimension of one part used by the chain.

    Attributes:
        part: part name.
        from_face / to_face: face indices inside the part, in chain order.
        signed_length: ``(c_to - c_from) . d`` [mm]; positive along the
            measurement direction.
        contributor: the resulting stack contributor (nominal ``|signed_length|``,
            sensitivity ``+1`` or ``-1``, tolerance from the annotation).
    """

    part: str
    from_face: int
    to_face: int
    signed_length: float
    contributor: Contributor


@dataclass(frozen=True)
class Chain:
    """A dimension chain between two faces.

    Attributes:
        direction: unit measurement direction ``d``.
        nominal: ``(c_to - c_from) . d`` measured on the model [mm].
        path: part names from the first face's part to the second's.
        links: the dimensions used, ordered like the annotations they came from.
        unsupported_contacts: descriptions of touching non-planar face pairs
            found in the assembly; they are not part of any chain.
    """

    direction: Vec3
    nominal: float
    path: tuple[str, ...]
    links: tuple[ChainLink, ...]
    unsupported_contacts: tuple[str, ...]

    def contributors(self) -> list[Contributor]:
        return [link.contributor for link in self.links]


def _dot(a: Vec3, b: Vec3) -> float:
    return math.fsum(x * y for x, y in zip(a, b, strict=True))


def _boxes_touch(a: FaceInfo, b: FaceInfo, tol: float, min_overlap: float) -> bool:
    """Bounding boxes overlap by more than ``min_overlap`` in at least two axes
    and are not separated by more than ``tol`` in any axis."""
    wide = 0
    for k in range(3):
        overlap = min(a.bbox_max[k], b.bbox_max[k]) - max(a.bbox_min[k], b.bbox_min[k])
        if overlap < -tol:
            return False
        if overlap > min_overlap:
            wide += 1
    return wide >= 2


def find_contacts(model: StepModel, tol: float = CONTACT_TOL_MM) -> tuple[list[Contact], list[str]]:
    """Planar contacts between different parts, and touching non-planar face pairs.

    A planar contact needs opposite normals (``n_a . n_b <= -1 + 1e-9``), the same
    plane (``|(c_b - c_a) . n_a| <= tol``) and overlapping extents. Overlap is
    judged on the faces' axis-aligned bounding boxes: exact for rectangular faces
    aligned with the axes, an approximation for other shapes.

    Returns:
        ``(contacts, unsupported)``; ``unsupported`` describes face pairs of
        different parts that touch but are not both planar.
    """
    contacts: list[Contact] = []
    unsupported: list[str] = []
    parts = model.parts
    for i, part_a in enumerate(parts):
        for j in range(i + 1, len(parts)):
            part_b = parts[j]
            for fa in part_a.faces:
                for fb in part_b.faces:
                    if not _boxes_touch(fa, fb, tol, tol):
                        continue
                    if fa.normal is None or fb.normal is None:
                        unsupported.append(
                            f"{part_a.name} face {fa.index} ({fa.surface}) touches"
                            f" {part_b.name} face {fb.index} ({fb.surface})"
                        )
                        continue
                    if _dot(fa.normal, fb.normal) > -1.0 + PARALLEL_TOL:
                        continue
                    delta = (
                        fb.centroid[0] - fa.centroid[0],
                        fb.centroid[1] - fa.centroid[1],
                        fb.centroid[2] - fa.centroid[2],
                    )
                    if abs(_dot(delta, fa.normal)) <= tol:
                        contacts.append(Contact(i, fa.index, j, fb.index, fa.normal))
    return contacts, unsupported


def _part_index(model: StepModel, ref: FaceRef) -> int:
    hits = [i for i, p in enumerate(model.parts) if ref.part in (p.name, p.instance_name)]
    if len(hits) != 1:
        raise ChainError(
            f"part '{ref.part}': expected exactly one part of that name, found {len(hits)}"
        )
    return hits[0]


def _face(model: StepModel, part: int, index: int, what: str) -> FaceInfo:
    faces = model.parts[part].faces
    if not 0 <= index < len(faces):
        raise ChainError(f"{what}: part '{model.parts[part].name}' has no face {index}")
    face = faces[index]
    if face.normal is None:
        raise ChainError(
            f"{what}: face {index} of '{model.parts[part].name}' is a {face.surface}, not a plane"
        )
    return face


def build_chain(
    model: StepModel,
    face_from: FaceRef,
    face_to: FaceRef,
    dimensions: list[ResolvedDimension],
    *,
    direction: Vec3 | None = None,
    tol: float = CONTACT_TOL_MM,
) -> Chain:
    """Dimension chain from ``face_from`` to ``face_to``.

    Args:
        model: the STEP model.
        face_from, face_to: the two planar faces of the requirement.
        dimensions: resolved dimension annotations (the tolerances).
        direction: measurement direction; default: the outward normal of
            ``face_from``. Both faces must be perpendicular to it.
        tol: contact tolerance [mm].

    Raises:
        ChainError: non-planar or non-perpendicular face, no path, several
            paths, or a chain dimension without a tolerance annotation.
    """
    start = _part_index(model, face_from)
    goal = _part_index(model, face_to)
    f_from = _face(model, start, face_from.face_index, "requirement.from")
    f_to = _face(model, goal, face_to.face_index, "requirement.to")
    assert f_from.normal is not None and f_to.normal is not None
    if direction is None:
        d = f_from.normal
    else:
        length = math.sqrt(_dot(direction, direction))
        if length == 0.0:
            raise ChainError("direction: must not be the zero vector")
        d = (direction[0] / length, direction[1] / length, direction[2] / length)
    for label, face in (("from", f_from), ("to", f_to)):
        assert face.normal is not None
        if 1.0 - abs(_dot(face.normal, d)) > PARALLEL_TOL:
            raise ChainError(
                f"requirement.{label}: the face is not perpendicular to the measurement"
                f" direction {tuple(round(c, 9) for c in d)}"
            )

    contacts, unsupported = find_contacts(model, tol)
    # Only contacts whose plane is perpendicular to d carry the stack along d.
    along = [c for c in contacts if 1.0 - abs(_dot(c.normal, d)) <= PARALLEL_TOL]
    neighbours: dict[int, list[tuple[int, int, int]]] = {}
    for c in along:
        neighbours.setdefault(c.part_a, []).append((c.part_b, c.face_a, c.face_b))
        neighbours.setdefault(c.part_b, []).append((c.part_a, c.face_b, c.face_a))

    # every simple path: list of (part, entry_face, exit_face) steps
    paths: list[list[tuple[int, int, int]]] = []

    def walk(
        part: int, entry: int, visited: tuple[int, ...], steps: list[tuple[int, int, int]]
    ) -> None:
        if part == goal:
            paths.append([*steps, (part, entry, face_to.face_index)])
            return
        for nxt, exit_face, next_entry in neighbours.get(part, []):
            if nxt in visited:
                continue
            walk(nxt, next_entry, (*visited, nxt), [*steps, (part, entry, exit_face)])

    walk(start, face_from.face_index, (start,), [])
    names = [p.name for p in model.parts]
    if not paths:
        reachable = sorted({names[n] for n, _a, _b in neighbours.get(start, [])})
        raise ChainError(
            f"no path of planar contacts from '{names[start]}' to '{names[goal]}' along"
            f" {tuple(round(c, 9) for c in d)}; '{names[start]}' touches {reachable or 'nothing'}"
            f" in that direction ({len(contacts)} planar contacts in the assembly,"
            f" {len(unsupported)} non-planar)"
        )
    if len(paths) > 1:
        listed = [
            " -> ".join(f"{names[p]}[{a}>{b}]" for p, a, b in path)
            for path in paths[:_MAX_PATHS_LISTED]
        ]
        raise ChainError(
            f"{len(paths)} possible paths from '{names[start]}' to '{names[goal]}'; the"
            " assembly is over-constrained along this direction and the tool cannot choose."
            " Paths (part[entry face>exit face]): " + "; ".join(listed)
        )

    def position(part: int, index: int) -> float:
        return _dot(model.parts[part].faces[index].centroid, d)

    order = {
        (dim.from_face.part, frozenset((dim.from_face.face_index, dim.to_face.face_index))): k
        for k, dim in enumerate(dimensions)
        if dim.from_face.part == dim.to_face.part
    }
    links: list[tuple[int, ChainLink]] = []
    for part, entry, exit_face in paths[0]:
        signed = round(position(part, exit_face) - position(part, entry), NOMINAL_DECIMALS)
        if entry == exit_face or signed == 0.0:
            continue
        part_obj: PartInstance = model.parts[part]
        key = (part_obj.name, frozenset((entry, exit_face)))
        if key not in order:
            raise ChainError(
                f"no tolerance for the dimension of '{part_obj.name}' between faces {entry}"
                f" and {exit_face} (nominal {abs(signed):.9g} mm): add a dimension annotation"
                " on these two faces"
            )
        dim = dimensions[order[key]]
        if abs(dim.nominal - abs(signed)) > 10 ** (-NOMINAL_DECIMALS + 2):
            raise ChainError(
                f"annotation '{dim.id}' measures {dim.nominal:.9g} mm but the chain needs"
                f" {abs(signed):.9g} mm between faces {entry} and {exit_face} of '{part_obj.name}'"
            )
        contributor = Contributor(
            id=dim.id,
            nominal=abs(signed),
            upper_tol=dim.upper_tol,
            lower_tol=dim.lower_tol,
            sensitivity=1.0 if signed > 0 else -1.0,
            distribution=dim.distribution,
            cp=dim.cp,
            tolerance_source=dim.tolerance_source,
            tolerance_verified=dim.tolerance_verified,
        )
        links.append((order[key], ChainLink(part_obj.name, entry, exit_face, signed, contributor)))

    nominal = round(_dot(f_to.centroid, d) - _dot(f_from.centroid, d), NOMINAL_DECIMALS)
    ordered = tuple(link for _k, link in sorted(links, key=lambda pair: pair[0]))
    total = math.fsum(link.signed_length for link in ordered)
    if abs(total - nominal) > max(tol * (len(ordered) + 1), 1e-9):
        raise ChainError(
            f"the chain does not close: links sum to {total:.9g} mm but the faces are"
            f" {nominal:.9g} mm apart (contacts are not exactly coincident)"
        )
    return Chain(
        direction=d,
        nominal=nominal,
        path=tuple(names[p] for p, _a, _b in paths[0]),
        links=ordered,
        unsupported_contacts=tuple(unsupported),
    )
