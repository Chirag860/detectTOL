"""Report generation: JSON, Markdown, HTML and the Monte Carlo histogram."""

from detecttol.report.histogram import render_histogram_png
from detecttol.report.model import (
    Report,
    build_report,
    generate_json_schema,
    load_committed_schema,
    utc_timestamp,
)
from detecttol.report.render import to_html, to_json, to_markdown

__all__ = [
    "Report",
    "build_report",
    "generate_json_schema",
    "load_committed_schema",
    "render_histogram_png",
    "to_html",
    "to_json",
    "to_markdown",
    "utc_timestamp",
]
