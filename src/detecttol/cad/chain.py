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

Round features (holes and pins, :mod:`detecttol.cad.round`) take part too:

- a **pin in a hole** of another part, with its axis perpendicular to ``d``, is a
  contact like a planar one; it adds the pin's float across the axis
  (:func:`~detecttol.cad.round.float_contributor`, docs/ASSUMPTIONS.md A39);
- inside a part, the axis of a round feature is a node like a face; a **position**
  tolerance links it to the datum plane that locates it along ``d``.

The axis of a round feature is named by its lowest STEP face index.

Supported: planar faces perpendicular to ``d``, round features with their axis
perpendicular to ``d``, translation-only stacks.
Reported, not solved: no path, several paths, other non-planar contacts.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

from detecttol.cad.annotations import ResolvedDimension
from detecttol.cad.pmi import FaceRef
from detecttol.cad.round import (
    ResolvedDiameter,
    ResolvedPosition,
    RoundFeature,
    RoundFeatureError,
    coaxial,
    float_contributor,
    position_dimension,
    round_features,
)
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
#: A pin locates a part in a hole only when the nominal diametral clearance is at most
#: this fraction of the hole diameter (A42); a looser coaxial pair is reported, not used.
LOCATING_CLEARANCE_REL = 0.05


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
class CoaxialContact:
    """A pin of one part inside a hole of another, on the same axis.

    ``part_*`` are indices into ``StepModel.parts``; ``hole`` / ``pin`` are the
    two round features.
    """

    part_hole: int
    hole: RoundFeature
    part_pin: int
    pin: RoundFeature


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
    filled: tuple[MissingDimension, ...] = ()
    filled_diameters: tuple[ResolvedDiameter, ...] = ()
    notes: tuple[str, ...] = ()

    def contributors(self) -> list[Contributor]:
        return [link.contributor for link in self.links]


@dataclass(frozen=True)
class MissingDimension:
    """A dimension the chain needs but no annotation supplies.

    Attributes:
        part: part name.
        from_face / to_face: face indices inside the part, in chain order.
        nominal: distance between the two faces measured on the model [mm].
    """

    part: str
    from_face: int
    to_face: int
    nominal: float


#: Called for each missing dimension; returns its tolerance or ``None`` to refuse.
FillMissing = Callable[[MissingDimension], ResolvedDimension | None]
#: Called for a round feature in the chain without a toleranced diameter.
FillDiameter = Callable[[RoundFeature], ResolvedDiameter | None]


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
                        if _coaxial_faces(fa, fb):
                            continue  # a pin in a hole: see find_coaxial_contacts
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


def _locating(hole_radius: float, pin_radius: float, tol: float) -> bool:
    """A pin fits the hole closely enough to locate a part (A42)."""
    gap = 2.0 * (hole_radius - pin_radius)
    return -2.0 * tol <= gap <= LOCATING_CLEARANCE_REL * 2.0 * hole_radius


def _coaxial_faces(a: FaceInfo, b: FaceInfo) -> bool:
    """A pin face and a hole face of a locating pin-in-hole pair."""
    ca, cb = a.cylinder, b.cylinder
    if ca is None or cb is None or ca.internal == cb.internal:
        return False
    hole, pin = (ca, cb) if ca.internal else (cb, ca)
    return coaxial(ca.axis_point, ca.axis, cb.axis_point, cb.axis) and _locating(
        hole.radius, pin.radius, CONTACT_TOL_MM
    )


def find_coaxial_contacts(model: StepModel, tol: float = CONTACT_TOL_MM) -> list[CoaxialContact]:
    """Pins inside holes of other parts: coaxial round features, one internal and
    one external, the pin not larger than the hole and not looser than
    :data:`LOCATING_CLEARANCE_REL` (nominally), overlapping along the axis."""
    features = [(i, f) for i, part in enumerate(model.parts) for f in round_features(part)]
    out: list[CoaxialContact] = []
    for i, hole in features:
        if not hole.internal:
            continue
        for j, pin in features:
            if j == i or pin.internal or not _locating(hole.radius, pin.radius, tol):
                continue
            if not coaxial(hole.axis_point, hole.axis, pin.axis_point, pin.axis, tol):
                continue
            offset = (
                pin.axis_point[0] - hole.axis_point[0],
                pin.axis_point[1] - hole.axis_point[1],
                pin.axis_point[2] - hole.axis_point[2],
            )
            shift = _dot(offset, hole.axis)
            sense = 1.0 if _dot(pin.axis, hole.axis) > 0 else -1.0
            lo, hi = sorted(
                (sense * pin.axial_range[0] + shift, sense * pin.axial_range[1] + shift)
            )
            if lo < hole.axial_range[1] - tol and hi > hole.axial_range[0] + tol:
                out.append(CoaxialContact(i, hole, j, pin))
    return out


def _carries(face: FaceInfo, d: Vec3) -> bool:
    """A plane perpendicular to ``d``, or a cylinder whose axis is."""
    if face.normal is not None:
        return 1.0 - abs(_dot(face.normal, d)) <= PARALLEL_TOL
    if face.cylinder is not None:
        return abs(_dot(face.cylinder.axis, d)) <= PARALLEL_TOL
    return False


def _station(face: FaceInfo, d: Vec3) -> float:
    """Where a node sits along ``d`` [mm]: the plane, or the axis of a cylinder."""
    if face.cylinder is not None:
        return _dot(face.cylinder.axis_point, d)
    return _dot(face.centroid, d)


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
    fill_missing: FillMissing | None = None,
    diameters: list[ResolvedDiameter] | None = None,
    positions: list[ResolvedPosition] | None = None,
    fill_diameter: FillDiameter | None = None,
) -> Chain:
    """Dimension chain from ``face_from`` to ``face_to``.

    Inside each part the chain needs the distance between its entry and exit
    faces. It uses, in this order: a dimension on exactly those two faces; else
    the one combination of the part's dimensions that leads from one to the other
    (e.g. A->B and B->C for A->C; each becomes a contributor); else
    ``fill_missing``.

    Args:
        model: the STEP model.
        face_from, face_to: the two planar faces of the requirement.
        dimensions: resolved dimension annotations (the tolerances).
        direction: measurement direction; default: the outward normal of
            ``face_from``. Both faces must be perpendicular to it.
        tol: contact tolerance [mm].
        fill_missing: supplies a tolerance for a dimension no annotation covers
            (e.g. a general tolerance); ``None`` or a ``None`` result refuses.
        diameters: toleranced diameters of round features (for the pin float
            and the MMC/LMC bonus).
        positions: position tolerances of round features (datum plane -> axis).
        fill_diameter: supplies a diameter tolerance that a round feature in the
            chain lacks; ``None`` or a ``None`` result refuses.

    Raises:
        ChainError: non-planar or non-perpendicular face, no path, several
            paths, several ways to combine a part's dimensions, or a chain
            dimension without a tolerance.
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
    Join = tuple[CoaxialContact, ...] | None
    neighbours: dict[int, list[tuple[int, int, int, Join]]] = {}
    for c in along:
        neighbours.setdefault(c.part_a, []).append((c.part_b, c.face_a, c.face_b, None))
        neighbours.setdefault(c.part_b, []).append((c.part_a, c.face_b, c.face_a, None))
    # A pin in a hole carries the stack across its axis (axis perpendicular to d). A
    # pin in two bores of one part (a clevis) is one contact between the two parts.
    pairs: dict[tuple[int, int], list[CoaxialContact]] = {}
    for cc in find_coaxial_contacts(model, tol):
        if abs(_dot(cc.hole.axis, d)) <= PARALLEL_TOL:
            pairs.setdefault((cc.part_hole, cc.part_pin), []).append(cc)
    for (part_hole, part_pin), group in pairs.items():
        group.sort(key=lambda cc: (cc.hole.face, cc.pin.face))
        h, p = group[0].hole.face, group[0].pin.face
        neighbours.setdefault(part_hole, []).append((part_pin, h, p, tuple(group)))
        neighbours.setdefault(part_pin, []).append((part_hole, p, h, tuple(group)))

    # every simple path: (part, entry_face, exit_face) steps, and the contacts between
    paths: list[tuple[list[tuple[int, int, int]], list[Join]]] = []

    def walk(
        part: int,
        entry: int,
        visited: tuple[int, ...],
        steps: list[tuple[int, int, int]],
        joins: list[Join],
    ) -> None:
        if part == goal:
            paths.append(([*steps, (part, entry, face_to.face_index)], joins))
            return
        for nxt, exit_face, next_entry, coax in neighbours.get(part, []):
            if nxt in visited:
                continue
            walk(
                nxt,
                next_entry,
                (*visited, nxt),
                [*steps, (part, entry, exit_face)],
                [*joins, coax],
            )

    walk(start, face_from.face_index, (start,), [], [])
    names = [p.name for p in model.parts]
    if not paths:
        reachable = sorted({names[n] for n, _a, _b, _c in neighbours.get(start, [])})
        raise ChainError(
            f"no path of planar contacts from '{names[start]}' to '{names[goal]}' along"
            f" {tuple(round(c, 9) for c in d)}; '{names[start]}' touches {reachable or 'nothing'}"
            f" in that direction ({len(contacts)} planar contacts in the assembly,"
            f" {len(unsupported)} other touching face pairs)"
        )
    if len(paths) > 1:
        listed = [
            " -> ".join(f"{names[p]}[{a}>{b}]" for p, a, b in path)
            for path, _joins in paths[:_MAX_PATHS_LISTED]
        ]
        raise ChainError(
            f"{len(paths)} possible paths from '{names[start]}' to '{names[goal]}'; the"
            " assembly is over-constrained along this direction and the tool cannot choose."
            " Paths (part[entry face>exit face]): " + "; ".join(listed)
        )

    def position(part: int, index: int) -> float:
        return _station(model.parts[part].faces[index], d)

    sizes = {(dia.part, dia.face): dia for dia in diameters or []}
    filled_sizes: list[ResolvedDiameter] = []

    def size_of(feature: RoundFeature, why: str) -> ResolvedDiameter:
        found = sizes.get((feature.part, feature.face))
        if found is None and fill_diameter is not None:
            found = fill_diameter(feature)
            if found is not None:
                sizes[(feature.part, feature.face)] = found
                filled_sizes.append(found)
        if found is None:
            raise ChainError(
                f"no tolerance for the diameter of {feature.describe()} ({why}): add a"
                " diameter annotation to it"
            )
        return found

    # positions -> dimensions from the datum plane that locates the axis along d,
    # for the parts on the path only
    steps, joins = paths[0]
    on_path = {names[p] for p, _a, _b in steps}
    notes: list[str] = []
    dimensions = list(dimensions)
    for pos in positions or []:
        if pos.part not in on_path:
            continue
        pos_part = _part_index(model, FaceRef(part=pos.part, face_index=pos.face))
        part_faces = model.parts[pos_part].faces
        if part_faces[pos.face].cylinder is None or not _carries(part_faces[pos.face], d):
            continue
        datums = [
            ref
            for ref in pos.datums
            if ref.part == pos.part
            and part_faces[ref.face_index].normal is not None
            and _carries(part_faces[ref.face_index], d)
        ]
        if not datums:
            notes.append(
                f"{pos.id}: no datum plane of it is perpendicular to the measuring direction;"
                " the position is not used for this stack"
            )
            continue
        feature = next(f for f in round_features(model.parts[pos_part]) if pos.face in f.faces)
        size = None
        if pos.material_condition != "RFS":
            size = size_of(feature, f"{pos.id} at {pos.material_condition}")
        datum = datums[0]
        distance = position(pos_part, pos.face) - position(pos_part, datum.face_index)
        sign = 1.0 if distance >= 0 else -1.0
        towards = (sign * d[0], sign * d[1], sign * d[2])
        try:
            dimensions.append(position_dimension(pos, datum, distance, towards, size))
        except RoundFeatureError as exc:
            raise ChainError(str(exc)) from exc

    order = {
        (dim.from_face.part, frozenset((dim.from_face.face_index, dim.to_face.face_index))): k
        for k, dim in enumerate(dimensions)
        if dim.from_face.part == dim.to_face.part
    }
    links: list[tuple[int, ChainLink]] = []
    filled: list[MissingDimension] = []

    def link(k: int, dim: ResolvedDimension, part: int, a: int, b: int) -> tuple[int, ChainLink]:
        signed = round(position(part, b) - position(part, a), NOMINAL_DECIMALS)
        name = model.parts[part].name
        if abs(dim.nominal - abs(signed)) > 10 ** (-NOMINAL_DECIMALS + 2):
            raise ChainError(
                f"annotation '{dim.id}' measures {dim.nominal:.9g} mm but the chain needs"
                f" {abs(signed):.9g} mm between faces {a} and {b} of '{name}'"
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
            cad_source=dim.cad_source,
        )
        return k, ChainLink(name, a, b, signed, contributor)

    for part, entry, exit_face in steps:
        signed = round(position(part, exit_face) - position(part, entry), NOMINAL_DECIMALS)
        if entry == exit_face or signed == 0.0:
            continue
        part_obj: PartInstance = model.parts[part]
        key = (part_obj.name, frozenset((entry, exit_face)))
        if key in order:
            k = order[key]
            links.append(link(k, dimensions[k], part, entry, exit_face))
            continue
        combined = _dimension_paths(model, part, entry, exit_face, dimensions, d)
        if len(combined) == 1:
            for k, a, b in combined[0]:
                links.append(link(k, dimensions[k], part, a, b))
            continue
        if len(combined) > 1:
            listed = [
                " + ".join(f"{dimensions[k].id}[{a}>{b}]" for k, a, b in path)
                for path in combined[:_MAX_PATHS_LISTED]
            ]
            raise ChainError(
                f"'{part_obj.name}' between faces {entry} and {exit_face}: {len(combined)} ways"
                " to combine its dimensions, the tool cannot choose: " + "; ".join(listed)
            )
        missing = MissingDimension(part_obj.name, entry, exit_face, abs(signed))
        dim = fill_missing(missing) if fill_missing is not None else None
        if dim is None:
            raise ChainError(
                f"no tolerance for the dimension of '{part_obj.name}' between faces {entry}"
                f" and {exit_face} (nominal {abs(signed):.9g} mm): add a dimension annotation"
                " on these two faces"
            )
        filled.append(missing)
        links.append(link(len(dimensions) + len(filled), dim, part, entry, exit_face))

    for group in joins:
        if group is None:
            continue
        floats = []
        for coax in group:
            hole = size_of(coax.hole, "pin float")
            pin = size_of(coax.pin, "pin float")
            try:
                floats.append(float_contributor(hole, pin))
            except RoundFeatureError as exc:
                raise ChainError(str(exc)) from exc
        # in two bores the tighter one decides how far the pin can move
        contributor = min(floats, key=lambda c: c.upper_tol)
        first = group[0]
        if len(group) > 1:
            notes.append(
                f"{first.pin.part} sits in {len(group)} coaxial holes of {first.hole.part};"
                f" the tightest float is used ({contributor.id})"
            )
        k = len(dimensions) + len(filled) + 1 + len(links)
        name = f"{first.pin.part} in {first.hole.part}"
        links.append((k, ChainLink(name, first.hole.face, first.pin.face, 0.0, contributor)))

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
        path=tuple(names[p] for p, _a, _b in steps),
        links=ordered,
        unsupported_contacts=tuple(unsupported),
        filled=tuple(filled),
        filled_diameters=tuple(filled_sizes),
        notes=tuple(notes),
    )


def _dimension_paths(
    model: StepModel,
    part: int,
    entry: int,
    exit_face: int,
    dimensions: list[ResolvedDimension],
    d: Vec3,
) -> list[list[tuple[int, int, int]]]:
    """Ways to reach ``exit_face`` from ``entry`` with dimensions of one part.

    A graph whose nodes are the part's faces and whose edges are its dimensions
    between two faces perpendicular to ``d``. Returns every simple path as a list of
    ``(dimension index, from face, to face)``.
    """
    name = model.parts[part].name
    faces = model.parts[part].faces
    edges: dict[int, list[tuple[int, int]]] = {}
    for k, dim in enumerate(dimensions):
        if dim.from_face.part != name or dim.to_face.part != name:
            continue
        a, b = dim.from_face.face_index, dim.to_face.face_index
        if not (_carries(faces[a], d) and _carries(faces[b], d)):
            continue
        edges.setdefault(a, []).append((k, b))
        edges.setdefault(b, []).append((k, a))
    found: list[list[tuple[int, int, int]]] = []

    def walk(face: int, seen: frozenset[int], steps: list[tuple[int, int, int]]) -> None:
        if len(found) > _MAX_PATHS_LISTED:
            return
        if face == exit_face:
            found.append(steps)
            return
        for k, nxt in edges.get(face, []):
            if nxt not in seen:
                walk(nxt, seen | {nxt}, [*steps, (k, face, nxt)])

    walk(entry, frozenset({entry}), [])
    return found
