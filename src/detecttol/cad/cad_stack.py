"""A tolerance stack straight from a CAD file, with no annotation YAML.

Two ways in, one result:

- **SolidWorks** ``.SLDASM`` (+ optional ``.SLDDRW``): tolerances read through the
  installed SolidWorks (:mod:`detecttol.solidworks`), geometry from the STEP copy
  it writes into a temporary folder.
- **STEP** ``.step`` / ``.stp``: geometry and semantic PMI from the file itself
  (dimension reading from PMI is unverified outside NIST CTC-01, docs/reports/phase-5.md).

The user names the two requirement faces (``PART:FACE`` as listed by
``detecttol faces``). The chain is built as in Phase 6; a dimension the CAD file
does not tolerance gets the drawing's general tolerance (IS 2102 / ISO 2768-1)
when one is given, otherwise the tool stops and names it. Flatness on a face of
the chain is converted under the chosen drawing standard (ASME: contained in the
size; ISO / IS: adds +/- t/2 unless the envelope requirement applies).
"""

from __future__ import annotations

import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from detecttol.cad.annotations import ResolvedDimension
from detecttol.cad.chain import Chain, ChainLink, MissingDimension, build_chain
from detecttol.cad.mapping import _ANGULAR_DIMENSION_KINDS
from detecttol.cad.pmi import FaceRef
from detecttol.cad.step_reader import StepModel, read_step
from detecttol.core.analyze import analyze
from detecttol.core.models import AnalysisConfig, DrawingStandard, Requirement, Stack
from detecttol.core.results import StackResult
from detecttol.gdt.analyze import GdtStack, analyze_gdt
from detecttol.gdt.models import Flatness
from detecttol.standards import general
from detecttol.standards.general import GeneralClass

SOLIDWORKS_SUFFIXES = (".sldasm",)
STEP_SUFFIXES = (".step", ".stp")
PMI_NOMINAL_TOL_MM = 1e-4


class CadStackError(ValueError):
    """The CAD file cannot be turned into a stack; the message says why."""


@dataclass(frozen=True)
class CadInput:
    """What a CAD file provides: geometry, toleranced dimensions, flatness callouts."""

    model: StepModel
    dimensions: tuple[ResolvedDimension, ...]
    flatness: tuple[tuple[Flatness, FaceRef], ...]
    notes: tuple[str, ...]
    origin: str


@dataclass(frozen=True)
class CadStack:
    """A stack built from a CAD file.

    Attributes:
        stack: the 1D stack (contributors with their sources).
        gdt: the same stack with flatness callouts, or ``None`` if there are none.
        chain: how it was built.
        cad: the CAD input it was built from.
        notes: how the chain used the model (e.g. combined dimensions).
    """

    stack: Stack
    gdt: GdtStack | None
    chain: Chain
    cad: CadInput
    notes: tuple[str, ...] = ()

    def analyze(self) -> StackResult:
        """Worst case / RSS / Monte Carlo as configured (with GD&T if any)."""
        return analyze_gdt(self.gdt) if self.gdt is not None else analyze(self.stack)


def pmi_dimensions(model: StepModel) -> tuple[list[ResolvedDimension], list[str]]:
    """Linear PMI dimensions between two parallel planar faces of one part."""
    dims: list[ResolvedDimension] = []
    notes: list[str] = []
    faces = {(p.name, f.index): f for p in model.parts for f in p.faces}
    for i, pmi in enumerate(model.dimensions):
        label = pmi.name or f"{pmi.kind}#{i}"
        if pmi.kind in _ANGULAR_DIMENSION_KINDS:
            continue
        if len(pmi.targets) != 2 or pmi.targets[0].part != pmi.targets[1].part:
            notes.append(f"STEP PMI {label}: not between two faces of one part; not used")
            continue
        fa, fb = (faces.get((t.part, t.face_index)) for t in pmi.targets)
        if fa is None or fb is None or fa.normal is None or fb.normal is None:
            notes.append(f"STEP PMI {label}: a target face is missing or not planar; not used")
            continue
        dot = sum(a * b for a, b in zip(fa.normal, fb.normal, strict=True))
        if abs(dot) < 1.0 - 1e-9:
            notes.append(f"STEP PMI {label}: faces not parallel; not used")
            continue
        signed = sum(
            (b - a) * n for a, b, n in zip(fa.centroid, fb.centroid, fa.normal, strict=True)
        )
        if abs(abs(signed) - pmi.value) > PMI_NOMINAL_TOL_MM:
            notes.append(
                f"STEP PMI {label}: value {pmi.value:g} but faces {abs(signed):.9g} mm"
                " apart; not used"
            )
            continue
        if pmi.upper_tol is None or pmi.lower_tol is None:
            notes.append(f"STEP PMI {label}: no usable tolerance (form {pmi.tolerance_form})")
            continue
        sign = 1.0 if signed >= 0 else -1.0
        dims.append(
            ResolvedDimension(
                id=f"{pmi.targets[0].part}:{label}",
                nominal=round(abs(signed), 9),
                upper_tol=float(pmi.upper_tol),
                lower_tol=float(pmi.lower_tol),
                distribution="normal",
                cp=1.0,
                from_face=pmi.targets[0],
                to_face=pmi.targets[1],
                direction=(sign * fa.normal[0], sign * fa.normal[1], sign * fa.normal[2]),
                cad_source=f"STEP PMI {label} (PMI dimension reading is unverified)",
                is_size=pmi.kind.startswith("Size"),
            )
        )
    return dims, notes


def pmi_flatness(model: StepModel) -> list[tuple[Flatness, FaceRef]]:
    """Flatness PMI on exactly one face."""
    out = []
    for i, gt in enumerate(model.geometric_tolerances):
        if gt.kind == "Flatness" and len(gt.targets) == 1:
            out.append(
                (
                    Flatness(id=f"{gt.targets[0].part}:{gt.name or i}", tolerance=gt.value),
                    gt.targets[0],
                )
            )
    return out


def read_cad(
    path: str | Path, drawings: Sequence[str | Path] = (), workdir: str | Path | None = None
) -> CadInput:
    """Geometry and tolerances of a SolidWorks assembly or a STEP file.

    Raises:
        CadStackError: unknown file type, or the reader failed (message included).
    """
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix in STEP_SUFFIXES:
        if drawings:
            raise CadStackError("drawings can only be read together with a SolidWorks assembly")
        model = read_step(p)
        dims, notes = pmi_dimensions(model)
        return CadInput(model, tuple(dims), tuple(pmi_flatness(model)), tuple(notes), "STEP PMI")
    if suffix in SOLIDWORKS_SUFFIXES:
        from detecttol.solidworks.reader import SolidWorksError, read_solidworks
        from detecttol.solidworks.resolve import SolidWorksResolveError, resolve

        folder = Path(workdir) if workdir else Path(tempfile.mkdtemp(prefix="detecttol_"))
        step = folder / f"{p.stem}_geometry.step"
        try:
            readout = read_solidworks(p, step, drawings)
            model = read_step(step)
            resolved = resolve(readout.data, model)
        except (SolidWorksError, SolidWorksResolveError) as exc:
            raise CadStackError(str(exc)) from exc
        origin = f"SolidWorks {readout.data.solidworks_revision}"
        return CadInput(model, resolved.dimensions, resolved.flatness, resolved.notes, origin)
    raise CadStackError(f"{p.name}: expected .SLDASM, .step or .stp")


def parse_face(text: str) -> FaceRef:
    """``PART:FACE`` -> :class:`FaceRef` (the face index as listed by ``detecttol faces``)."""
    part, sep, index = text.rpartition(":")
    if not sep or not part or not index.isdigit():
        raise CadStackError(f"'{text}': expected PART:FACE, e.g. Block_C:2")
    return FaceRef(part=part, face_index=int(index))


def build_cad_stack(
    cad: CadInput,
    face_from: FaceRef,
    face_to: FaceRef,
    *,
    lsl: float | None = 0.0,
    usl: float | None = None,
    standard: DrawingStandard | None = None,
    general_class: GeneralClass | None = None,
    name: str = "cad_stack",
    description: str = "",
    analysis: AnalysisConfig | None = None,
) -> CadStack:
    """Build the stack between two faces of ``cad``.

    Raises:
        CadStackError: no path, ambiguity, a missing tolerance without a general
            class, or an invalid requirement.
    """
    from detecttol.cad.chain import ChainError

    if lsl is None and usl is None:
        raise CadStackError("give at least one of lsl / usl")

    def fill(missing: MissingDimension) -> ResolvedDimension | None:
        if general_class is None:
            return None
        try:
            d = general.general_deviation(missing.nominal, general_class)
        except general.GeneralToleranceError as exc:
            raise CadStackError(
                f"{missing.part} faces {missing.from_face}-{missing.to_face}: {exc}"
            ) from exc
        return ResolvedDimension(
            id=f"{missing.part}:general_{missing.from_face}_{missing.to_face}",
            nominal=missing.nominal,
            upper_tol=d,
            lower_tol=-d,
            distribution="normal",
            cp=1.0,
            from_face=FaceRef(missing.part, missing.from_face),
            to_face=FaceRef(missing.part, missing.to_face),
            direction=(0.0, 0.0, 0.0),
            tolerance_source=general.describe(missing.nominal, general_class)
            + " (no tolerance on these faces in the CAD model)",
        )

    try:
        chain = build_chain(cad.model, face_from, face_to, list(cad.dimensions), fill_missing=fill)
    except ChainError as exc:
        hint = "" if general_class else " (or give a general tolerance class, e.g. --general m)"
        raise CadStackError(f"chain: {exc}{hint}") from exc
    if not chain.links:
        raise CadStackError("chain: the two faces are in the same plane of the same part")
    note = (
        f"from {cad.origin}: chain {' -> '.join(chain.path)};"
        f" measured nominal {chain.nominal:.9g} mm"
    )
    stack = Stack(
        schema_version=1,
        units="mm",
        name=name,
        standard=standard,
        requirement=Requirement(
            description=f"{description} [{note}]" if description else f"[{note}]",
            lsl=lsl,
            usl=usl,
        ),
        contributors=chain.contributors(),
        analysis=analysis or AnalysisConfig(),
    )
    contact, in_size, combined = _chain_faces(chain, cad.dimensions)
    contact |= {(face_from.part, face_from.face_index), (face_to.part, face_to.face_index)}
    callouts: list[Flatness] = []
    for callout, ref in cad.flatness:
        key = (ref.part, ref.face_index)
        if key not in contact:
            continue  # not touched by the chain (an intermediate datum face cancels out)
        if key not in in_size and "within_size" not in callout.model_fields_set:
            # Only a face of a size dimension in the chain may be "inside the size"
            # (ASME Rule #1); a location distance or a combined dimension is not.
            callout = callout.model_copy(update={"within_size": False})
        callouts.append(callout)
    gdt = GdtStack(stack=stack, callouts=callouts, standard=standard) if callouts else None
    notes = tuple(combined)
    return CadStack(stack=stack, gdt=gdt, chain=chain, cad=cad, notes=notes)


def _chain_faces(
    chain: Chain, dimensions: Sequence[ResolvedDimension]
) -> tuple[set[tuple[str, int]], set[tuple[str, int]], list[str]]:
    """Contact faces of the chain, faces inside a size dimension of it, and combine notes.

    Per part, the contact faces are the entry and exit faces: the link end faces
    that occur an odd number of times (a face shared by two combined dimensions is
    an intermediate datum, not a contact). A face counts as inside a size only
    when its part uses exactly one dimension and that dimension is a size.
    """
    by_id = {d.id: d for d in dimensions}
    per_part: dict[str, list[ChainLink]] = {}
    for link in chain.links:
        per_part.setdefault(link.part, []).append(link)
    contact: set[tuple[str, int]] = set()
    in_size: set[tuple[str, int]] = set()
    notes: list[str] = []
    for part, links in per_part.items():
        count: dict[int, int] = {}
        for link in links:
            for face in (link.from_face, link.to_face):
                count[face] = count.get(face, 0) + 1
        ends = sorted(f for f, n in count.items() if n % 2 == 1)
        contact |= {(part, f) for f in ends}
        if len(links) == 1:
            dim = by_id.get(links[0].contributor.id)
            if dim is not None and dim.is_size:
                in_size |= {(part, links[0].from_face), (part, links[0].to_face)}
        else:
            via = sorted(f for f, n in count.items() if n % 2 == 0)
            notes.append(
                f"'{part}' faces {ends[0]}->{ends[-1]}: no direct dimension; combined from"
                f" {len(links)} dimensions ({', '.join(link.contributor.id for link in links)})"
                f" via face(s) {via}. Their tolerances add up and are treated as independent;"
                " dimension these two faces directly to tighten the stack."
            )
    return contact, in_size, notes
