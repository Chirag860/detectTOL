"""A tolerance stack defined on a STEP assembly (spec Phase 6): YAML -> Stack.

File format (``schema_version: 3``)::

    schema_version: 3
    units: mm
    name: plate_stack_from_step
    step_file: plate_stack.step          # relative to this YAML file
    requirement:
      description: gap between top plate and slot ceiling
      from: {part: PLATE_3, face: 5, centroid: [30, 15, 59.8], normal: [0, 0, 1]}
      to:   {part: HOUSING, face: 9, centroid: [30, 15, 60], normal: [0, 0, -1]}
      lsl: 0.0
      usl: null
    annotations:                         # the tolerances, as in an annotation file
      - {id: slot_depth, kind: dimension, from: {...}, to: {...}, upper_tol: 0.1, lower_tol: -0.1}
    analysis:
      methods: [worst_case, rss, monte_carlo]
      monte_carlo: {n: 100000, seed: 42}
    contact_tolerance: 1.0e-6            # optional [mm]

The requirement value is the distance from ``from`` to ``to`` along the outward
normal of the ``from`` face, or along ``requirement.direction: [x, y, z]`` if
given. Use ``detecttol faces model.step`` to list the face
selectors of a model.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from detecttol.cad.annotations import (
    Annotation,
    AnnotationError,
    AnnotationFile,
    FaceSelector,
    _loc,
    _match,
    resolve_annotations,
)
from detecttol.cad.chain import CONTACT_TOL_MM, Chain, ChainError, build_chain
from detecttol.cad.step_reader import StepModel, StepReadError, read_step
from detecttol.core.models import AnalysisConfig, FiniteFloat, Requirement, Stack
from detecttol.io.yaml_loader import StackInputError

_STRICT = ConfigDict(strict=True, extra="forbid", frozen=True, populate_by_name=True)


class StepRequirement(BaseModel):
    """The requirement: distance from one planar face to another, with spec limits."""

    model_config = _STRICT

    description: str = ""
    from_face: FaceSelector = Field(alias="from")
    to_face: FaceSelector = Field(alias="to")
    direction: Annotated[list[FiniteFloat], Field(min_length=3, max_length=3)] | None = None
    lsl: FiniteFloat | None = None
    usl: FiniteFloat | None = None


class StepStackDocument(BaseModel):
    """A ``schema_version: 3`` input file."""

    model_config = _STRICT

    schema_version: Literal[3]
    units: Literal["mm"]
    name: Annotated[str, Field(min_length=1)]
    step_file: Annotated[str, Field(min_length=1)]
    requirement: StepRequirement
    annotations: Annotated[list[Annotation], Field(min_length=1)]
    analysis: AnalysisConfig = AnalysisConfig()
    contact_tolerance: Annotated[float, Field(gt=0.0, allow_inf_nan=False)] = CONTACT_TOL_MM


@dataclass(frozen=True)
class StepStack:
    """A stack built from a STEP assembly.

    Attributes:
        stack: the equivalent 1D stack, ready for :func:`detecttol.analyze`.
        chain: how it was built (path, links, measured nominal).
        model: the STEP model it was built from.
    """

    stack: Stack
    chain: Chain
    model: StepModel


def _describe(description: str, chain: Chain) -> str:
    """User description plus how the stack was derived from the model."""
    direction = ", ".join(f"{c:g}" for c in chain.direction)
    note = (
        f"from STEP: chain {' -> '.join(chain.path)}; measured nominal"
        f" {chain.nominal:.9g} mm along ({direction})"
    )
    if chain.unsupported_contacts:
        note += f"; {len(chain.unsupported_contacts)} non-planar contact(s) ignored"
    return f"{description} [{note}]" if description else f"[{note}]"


def is_step_stack(data: Any) -> bool:
    """True if parsed YAML data is a STEP-based stack definition."""
    return isinstance(data, dict) and "step_file" in data


def build_step_stack(data: Any, base_dir: str | Path = ".") -> StepStack:
    """Validate a ``schema_version: 3`` document and build its stack.

    Args:
        data: parsed YAML mapping.
        base_dir: folder against which ``step_file`` is resolved.

    Raises:
        StackInputError: validation problem, unreadable STEP file, annotation
            that does not match the model, or a chain that cannot be built. Each
            message starts with the field or item concerned.
    """
    if not isinstance(data, dict):
        raise StackInputError(["(root): the document must be a mapping of fields"])
    try:
        doc = StepStackDocument.model_validate(data)
    except ValidationError as exc:
        raise StackInputError(
            [
                f"{_loc(tuple(e['loc']))}: {str(e['msg']).removeprefix('Value error, ')}"
                for e in exc.errors()
            ]
        ) from exc
    if doc.requirement.lsl is None and doc.requirement.usl is None:
        raise StackInputError(["requirement: at least one of lsl / usl must be given"])
    path = Path(base_dir) / doc.step_file
    try:
        model = read_step(path)
    except StepReadError as exc:
        raise StackInputError([f"step_file: {exc}"]) from exc
    try:
        resolved = resolve_annotations(
            model,
            AnnotationFile(schema_version=1, units="mm", annotations=list(doc.annotations)),
        )
        ref_from, _f = _match(model, doc.requirement.from_face, "requirement.from", 1e-6)
        ref_to, _t = _match(model, doc.requirement.to_face, "requirement.to", 1e-6)
    except AnnotationError as exc:
        raise StackInputError(exc.errors) from exc
    try:
        chain = build_chain(
            model,
            ref_from,
            ref_to,
            list(resolved.dimensions),
            direction=None
            if doc.requirement.direction is None
            else (
                doc.requirement.direction[0],
                doc.requirement.direction[1],
                doc.requirement.direction[2],
            ),
            tol=doc.contact_tolerance,
        )
    except ChainError as exc:
        raise StackInputError([f"chain: {exc}"]) from exc
    if not chain.links:
        raise StackInputError(["chain: the two faces are in the same plane of the same part"])
    try:
        stack = Stack(
            schema_version=1,
            units="mm",
            name=doc.name,
            requirement=Requirement(
                description=_describe(doc.requirement.description, chain),
                lsl=doc.requirement.lsl,
                usl=doc.requirement.usl,
            ),
            contributors=chain.contributors(),
            analysis=doc.analysis,
        )
    except ValidationError as exc:
        raise StackInputError([str(e["msg"]) for e in exc.errors()]) from exc
    return StepStack(stack=stack, chain=chain, model=model)


def load_step_stack(path: str | Path) -> StepStack:
    """Read a ``schema_version: 3`` YAML file and build its stack.

    Raises:
        StackInputError: see :func:`build_step_stack`; also file not found or
            invalid YAML.
    """
    p = Path(path)
    if not p.is_file():
        raise StackInputError([f"file not found: {p}"])
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise StackInputError([f"{p}: not valid YAML ({exc})"]) from exc
    return build_step_stack(data, p.parent)
