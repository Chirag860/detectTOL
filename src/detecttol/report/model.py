"""Versioned report documents (the JSON output of the CLI).

- Schema version 1 (:class:`Report`): linear 1D stack.
- Schema version 2 (:class:`LoopReport`): 2D vector loop. Same ``result`` block
  as version 1 plus a ``loop`` block. **All angles in the JSON are radians**
  (and angle sensitivities mm/rad), whatever unit the input file used.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime
from importlib import resources
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from detecttol.core.loop import LoopResult, LoopWarning, VariableDetail
from detecttol.core.results import StackResult

REPORT_SCHEMA_VERSION = 1
LOOP_REPORT_SCHEMA_VERSION = 2
SCHEMA_RESOURCES = {1: "report-v1.schema.json", 2: "report-v2.schema.json"}

_FROZEN = ConfigDict(extra="forbid", frozen=True)


class ToolInfo(BaseModel):
    """Which tool produced the report."""

    model_config = _FROZEN

    name: Literal["detecttol"] = "detecttol"
    version: str


class Report(BaseModel):
    """A complete analysis report.

    Attributes:
        schema_version: version of this JSON layout (currently 1).
        tool: tool name and version.
        generated_at: UTC timestamp, ISO 8601 (``YYYY-MM-DDTHH:MM:SSZ``).
        input_file: path of the analysed file as given by the user, or ``None``.
        result: the analysis result; all lengths in millimetres.
    """

    model_config = _FROZEN

    schema_version: Literal[1] = 1
    tool: ToolInfo
    generated_at: str
    input_file: str | None
    result: StackResult


class LoopDetails(BaseModel):
    """Vector-loop specific part of a version-2 report.

    Attributes:
        angle_units: unit the *input file* used for angles (``deg`` or ``rad``).
            Informational: every angle in this JSON document is in radians.
        measure_angle: absolute measurement direction [rad], 0 = global +x
            (2D loops; ``None`` for a 3D loop).
        measure_direction: unit measurement direction ``[x, y, z]`` (3D loops;
            ``None`` for a 2D loop).
        variables: per-variable sensitivities (analytic and finite-difference),
            same order as ``result.contributors``.
        mc_std_rel_diff: ``(std_MC - sigma_linear)/sigma_linear`` or ``None``.
        mc_std_rel_se: approximate relative standard error of the Monte Carlo std.
        mc_mean_shift: ``mean_MC - Y(mu)`` [mm].
        mc_mean_se: standard error of the Monte Carlo mean [mm].
        warnings: linearisation warnings.
    """

    model_config = _FROZEN

    angle_units: Literal["deg", "rad"]
    measure_angle: float | None
    measure_direction: list[float] | None = None
    variables: list[VariableDetail]
    mc_std_rel_diff: float | None
    mc_std_rel_se: float | None
    mc_mean_shift: float | None
    mc_mean_se: float | None
    warnings: list[LoopWarning]


class LoopReport(BaseModel):
    """A complete analysis report for a 2D vector loop (schema version 2).

    ``result`` holds the linearised worst case / RSS and the exact Monte Carlo;
    for an angle contributor its nominal, tolerances and sigma are radians and
    its sensitivity mm/rad.
    """

    model_config = _FROZEN

    schema_version: Literal[2] = 2
    tool: ToolInfo
    generated_at: str
    input_file: str | None
    result: StackResult
    loop: LoopDetails


AnyReport = Report | LoopReport


def utc_timestamp(epoch_seconds: float | None = None) -> str:
    """ISO 8601 UTC timestamp to the second; ``now`` if no epoch is given."""
    dt = datetime.now(UTC) if epoch_seconds is None else datetime.fromtimestamp(epoch_seconds, UTC)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def build_report(
    result: StackResult, *, version: str, generated_at: str, input_file: str | None = None
) -> Report:
    """Wrap a linear-stack result with tool version, timestamp and input path."""
    return Report(
        tool=ToolInfo(version=version),
        generated_at=generated_at,
        input_file=input_file,
        result=result,
    )


def build_loop_report(
    loop_result: LoopResult,
    *,
    measure_angle: float | None = None,
    measure_direction: Sequence[float] | None = None,
    angle_units: Literal["deg", "rad"],
    version: str,
    generated_at: str,
    input_file: str | None = None,
) -> LoopReport:
    """Wrap a vector-loop result.

    Args:
        loop_result: output of :func:`detecttol.core.loop.analyze_loop`.
        measure_angle: absolute measurement direction [rad] of a 2D loop.
        measure_direction: unit measurement direction of a 3D loop. Exactly one
            of the two must be given.
        angle_units: unit the input used for angles (display only).
        version, generated_at, input_file: as for :func:`build_report`.
    """
    if (measure_angle is None) == (measure_direction is None):
        raise ValueError("give exactly one of measure_angle / measure_direction")
    return LoopReport(
        tool=ToolInfo(version=version),
        generated_at=generated_at,
        input_file=input_file,
        result=loop_result.result,
        loop=LoopDetails(
            angle_units=angle_units,
            measure_angle=measure_angle,
            measure_direction=None if measure_direction is None else list(measure_direction),
            variables=loop_result.variables,
            mc_std_rel_diff=loop_result.mc_std_rel_diff,
            mc_std_rel_se=loop_result.mc_std_rel_se,
            mc_mean_shift=loop_result.mc_mean_shift,
            mc_mean_se=loop_result.mc_mean_se,
            warnings=loop_result.loop_warnings,
        ),
    )


def generate_json_schema(version: int = 1) -> dict[str, Any]:
    """JSON Schema (draft 2020-12) of the report model for ``version`` (1 or 2)."""
    models: dict[int, type[BaseModel]] = {1: Report, 2: LoopReport}
    schema = models[version].model_json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["title"] = f"detecttol report v{version}"
    return schema


def load_committed_schema(version: int = 1) -> dict[str, Any]:
    """The JSON Schema file shipped with the package for ``version`` (1 or 2)."""
    text = (
        resources.files("detecttol.report")
        .joinpath("schema", SCHEMA_RESOURCES[version])
        .read_text("utf-8")
    )
    loaded: dict[str, Any] = json.loads(text)
    return loaded
