"""Versioned report document (the JSON output of the CLI)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from importlib import resources
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from detecttol.core.results import StackResult

REPORT_SCHEMA_VERSION = 1
SCHEMA_RESOURCE = "report-v1.schema.json"


class ToolInfo(BaseModel):
    """Which tool produced the report."""

    model_config = ConfigDict(extra="forbid", frozen=True)

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

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    tool: ToolInfo
    generated_at: str
    input_file: str | None
    result: StackResult


def utc_timestamp(epoch_seconds: float | None = None) -> str:
    """ISO 8601 UTC timestamp to the second; ``now`` if no epoch is given."""
    dt = datetime.now(UTC) if epoch_seconds is None else datetime.fromtimestamp(epoch_seconds, UTC)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def build_report(
    result: StackResult, *, version: str, generated_at: str, input_file: str | None = None
) -> Report:
    """Wrap an analysis result with tool version, timestamp and input path."""
    return Report(
        tool=ToolInfo(version=version),
        generated_at=generated_at,
        input_file=input_file,
        result=result,
    )


def generate_json_schema() -> dict[str, Any]:
    """JSON Schema (draft 2020-12) of :class:`Report`, generated from the model."""
    schema = Report.model_json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["title"] = "detecttol report v1"
    return schema


def load_committed_schema() -> dict[str, Any]:
    """The JSON Schema file shipped with the package."""
    text = (
        resources.files("detecttol.report").joinpath("schema", SCHEMA_RESOURCE).read_text("utf-8")
    )
    loaded: dict[str, Any] = json.loads(text)
    return loaded
