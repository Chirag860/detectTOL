"""Load and validate stack definitions from YAML.

Two document kinds are accepted:

- ``schema_version: 1`` - a linear 1D stack with ``contributors`` (spec Section 4).
- ``schema_version: 2`` - a 2D vector loop with a ``loop`` section. Lengths are
  millimetres; angles are given in the unit named by the required
  ``angle_units`` field (``deg`` or ``rad``) and converted to radians here, at
  input. Angles are **relative**: counter-clockwise from the previous vector's
  direction, the first one from the global +x axis.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Literal, TypeVar

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from detecttol.core.loop import LoopVariable, LoopVector, VectorLoop
from detecttol.core.loop3d import LoopVector3D, VectorLoop3D
from detecttol.core.models import AnalysisConfig, FiniteFloat, Requirement, Stack
from detecttol.standards.lookup import check_general_class, expand_contributor

AngleUnit = Literal["deg", "rad"]

_STRICT = ConfigDict(strict=True, extra="forbid", frozen=True)
_M = TypeVar("_M", bound=BaseModel)


class StackInputError(ValueError):
    """The input file is missing, unreadable or fails validation.

    ``errors`` holds one message per problem; each message starts with the
    dotted path of the offending field, e.g. ``contributors[1].cp: ...``.
    """

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("; ".join(errors))


class LoopVectorSpec(BaseModel):
    """One vector as written in the file: length [mm], relative angle [angle_units]."""

    model_config = _STRICT

    length: LoopVariable | FiniteFloat
    angle: LoopVariable | FiniteFloat
    pitch: LoopVariable | FiniteFloat | None = None
    roll: LoopVariable | FiniteFloat | None = None


class LoopSpec(BaseModel):
    """The ``loop`` section of a schema-version-2 file.

    A loop is 3D when any vector has ``pitch`` or ``roll`` or when
    ``measure_direction`` is given; ``angle`` is then the yaw (see
    :mod:`detecttol.core.loop3d` for the rotation convention). Otherwise it is 2D.

    Attributes:
        measure_angle: absolute measurement direction in the xy-plane
            [angle_units]; 0 = global +x.
        measure_direction: ``[x, y, z]`` measurement direction (any non-zero
            length); alternative to ``measure_angle`` for 3D loops.
        vectors: the chain, in order.
    """

    model_config = _STRICT

    measure_angle: FiniteFloat = 0.0
    measure_direction: Annotated[list[FiniteFloat], Field(min_length=3, max_length=3)] | None = None
    vectors: Annotated[list[LoopVectorSpec], Field(min_length=1)]


class LoopDocument(BaseModel):
    """A schema-version-2 input file (2D vector loop), before unit conversion."""

    model_config = _STRICT

    schema_version: Literal[2]
    units: Literal["mm"]
    angle_units: AngleUnit
    name: Annotated[str, Field(min_length=1)]
    requirement: Requirement
    loop: LoopSpec
    analysis: AnalysisConfig = AnalysisConfig()


@dataclass(frozen=True)
class LoopInput:
    """A validated vector loop (radians internally) plus the file's angle unit.

    Attributes:
        loop: the loop with every angle converted to radians.
        angle_units: unit the angles were written in (``deg`` or ``rad``); used
            only to display angles in reports the way the user entered them.
    """

    loop: VectorLoop | VectorLoop3D
    angle_units: AngleUnit


def _format_loc(loc: tuple[int | str, ...]) -> str:
    out = ""
    for part in loc:
        if isinstance(part, int):
            out += f"[{part}]"
        else:
            # Pydantic adds the tried union branch to the path (e.g. "float",
            # "LoopVariable", "function-after[...]"); those are not field names.
            if part in _UNION_BRANCH_LABELS or not part.isidentifier():
                continue
            out += f".{part}" if out else str(part)
    return out or "(root)"


_UNION_BRANCH_LABELS = frozenset({"LoopVariable", "float"})


def _is_union_noise(err: Any) -> bool:
    """True for the error of the union branch the user clearly did not mean.

    A length/angle is either a mapping (toleranced variable) or a number (fixed).
    Pydantic reports one error per branch; keep only the branch that matches the
    kind of value actually written.
    """
    kind = str(err["type"])
    wrote_mapping = isinstance(err.get("input"), dict)
    if kind in ("float_type", "float_parsing") and wrote_mapping:
        return True
    return kind in ("model_type", "model_attributes_type") and not wrote_mapping


def _validate(model: type[_M], data: Any) -> _M:
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        messages: list[str] = []
        errors = [e for e in exc.errors() if not _is_union_noise(e)] or list(exc.errors())
        for err in errors:
            loc = _format_loc(tuple(err["loc"]))
            msg = str(err["msg"]).removeprefix("Value error, ")
            line = f"{loc}: {msg}"
            if line not in messages:
                messages.append(line)
        raise StackInputError(messages) from exc


def _require_mapping(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise StackInputError(["(root): the document must be a mapping of fields"])
    return data


def _expand_classes(data: dict[str, Any]) -> dict[str, Any]:
    """Replace ``tolerance_class`` entries by looked-up deviations.

    ``general_tolerance`` (f/m/c/v) is a document-level setting used only here.
    """
    out = dict(data)
    errors: list[str] = []
    try:
        general_class = check_general_class(out.pop("general_tolerance", None))
    except ValueError as exc:
        raise StackInputError([f"general_tolerance: {exc}"]) from exc
    contributors = out.get("contributors")
    if isinstance(contributors, list):
        expanded: list[Any] = []
        for i, item in enumerate(contributors):
            if not isinstance(item, dict):
                expanded.append(item)
                continue
            try:
                expanded.append(expand_contributor(item, general_class))
            except ValueError as exc:
                errors.append(f"contributors[{i}].{exc}")
                expanded.append(item)
        out["contributors"] = expanded
    if errors:
        raise StackInputError(errors)
    return out


def parse_stack(data: Any) -> Stack:
    """Validate already-parsed data (a mapping) into a linear :class:`Stack`.

    A contributor may give ``tolerance_class`` (an ISO 286 class such as
    ``H7``, or ``general`` with a top-level ``general_tolerance: f|m|c|v``)
    instead of ``upper_tol`` / ``lower_tol``; see :mod:`detecttol.standards`.

    Raises:
        StackInputError: with one field-named message per validation problem.
    """
    return _validate(Stack, _expand_classes(_require_mapping(data)))


def _angle_factor(angle_units: AngleUnit) -> float:
    """Multiplier that converts a value in ``angle_units`` to radians."""
    return math.pi / 180.0 if angle_units == "deg" else 1.0


def _convert_angle(value: LoopVariable | float, factor: float) -> LoopVariable | float:
    if isinstance(value, LoopVariable):
        return LoopVariable(
            id=value.id,
            nominal=value.nominal * factor,
            upper_tol=value.upper_tol * factor,
            lower_tol=value.lower_tol * factor,
            distribution=value.distribution,
            cp=value.cp,
        )
    return float(value) * factor


def _as_length(value: LoopVariable | float) -> LoopVariable | float:
    return value if isinstance(value, LoopVariable) else float(value)


def parse_loop(data: Any) -> LoopInput:
    """Validate already-parsed data (a mapping) into a vector loop.

    Angles (nominals, tolerances, fixed angles and ``measure_angle``) are
    converted from ``angle_units`` to radians. Lengths stay in millimetres.

    Raises:
        StackInputError: with one field-named message per validation problem.
    """
    doc = _validate(LoopDocument, _require_mapping(data))
    factor = _angle_factor(doc.angle_units)
    spec = doc.loop
    is_3d = spec.measure_direction is not None or any(
        v.pitch is not None or v.roll is not None for v in spec.vectors
    )
    if spec.measure_direction is not None and spec.measure_angle != 0.0:
        raise StackInputError(
            ["loop.measure_direction: give measure_angle or measure_direction, not both"]
        )
    payload: dict[str, Any] = {
        "name": doc.name,
        "requirement": doc.requirement,
        "analysis": doc.analysis,
    }
    loop: VectorLoop | VectorLoop3D
    try:
        if is_3d:
            angle = float(spec.measure_angle) * factor
            direction = (
                (math.cos(angle), math.sin(angle), 0.0)
                if spec.measure_direction is None
                else tuple(float(c) for c in spec.measure_direction)
            )
            payload["vectors"] = [
                LoopVector3D(
                    length=_as_length(v.length),
                    yaw=_convert_angle(v.angle, factor),
                    pitch=_convert_angle(0.0 if v.pitch is None else v.pitch, factor),
                    roll=_convert_angle(0.0 if v.roll is None else v.roll, factor),
                )
                for v in spec.vectors
            ]
            payload["measure_direction"] = direction
            loop = VectorLoop3D.model_validate(payload)
        else:
            payload["vectors"] = [
                LoopVector(length=_as_length(v.length), angle=_convert_angle(v.angle, factor))
                for v in spec.vectors
            ]
            payload["measure_angle"] = float(spec.measure_angle) * factor
            loop = VectorLoop.model_validate(payload)
    except ValidationError as exc:
        messages = []
        for err in exc.errors():
            msg = str(err["msg"]).removeprefix("Value error, ")
            known = msg.startswith(("vectors", "measure_direction"))
            messages.append(f"loop.{msg}" if known else f"loop: {msg}")
        raise StackInputError(messages) from exc
    return LoopInput(loop=loop, angle_units=doc.angle_units)


def parse_input(data: Any) -> Stack | LoopInput:
    """Validate a document of either kind; a ``loop`` section selects the loop format."""
    mapping = _require_mapping(data)
    if "loop" in mapping:
        return parse_loop(mapping)
    return parse_stack(mapping)


def _read_yaml(path: str | Path) -> Any:
    p = Path(path)
    if not p.is_file():
        raise StackInputError([f"file not found: {p}"])
    try:
        return yaml.safe_load(p.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise StackInputError([f"{p}: not valid YAML ({exc})"]) from exc


def load_stack(path: str | Path) -> Stack:
    """Read a linear-stack YAML file and return the validated :class:`Stack`.

    All dimensions in the file must be millimetres (``units: mm``).

    Raises:
        StackInputError: file not found, not valid YAML, or failing validation.
    """
    return parse_stack(_read_yaml(path))


def load_loop(path: str | Path) -> LoopInput:
    """Read a vector-loop YAML file (``schema_version: 2``).

    Raises:
        StackInputError: file not found, not valid YAML, or failing validation.
    """
    return parse_loop(_read_yaml(path))


def load_input(path: str | Path) -> Stack | LoopInput:
    """Read a YAML file of either kind (linear stack or vector loop).

    Raises:
        StackInputError: file not found, not valid YAML, or failing validation.
    """
    return parse_input(_read_yaml(path))
