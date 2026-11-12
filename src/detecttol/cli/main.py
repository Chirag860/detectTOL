"""Command-line interface: ``detecttol analyze stack.yaml [--format md|html|json] [--out DIR]``."""

from __future__ import annotations

import contextlib
import os
import re
import sys
from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer

import detecttol
from detecttol.core.analyze import analyze as run_analysis
from detecttol.io import StackInputError, load_stack
from detecttol.report import (
    build_report,
    render_histogram_png,
    to_html,
    to_json,
    to_markdown,
    utc_timestamp,
)

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Mechanical tolerance stack-up analysis (worst case, RSS, Monte Carlo).",
)

EXIT_INPUT_ERROR = 2


class OutputFormat(StrEnum):
    """Report format."""

    md = "md"
    html = "html"
    json = "json"


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"detecttol {detecttol.__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option("--version", callback=_version_callback, is_eager=True, help="Show version."),
    ] = False,
) -> None:
    """detecttol command group."""


def _safe_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", name) or "stack"


def _timestamp() -> str:
    """Now (UTC), or SOURCE_DATE_EPOCH if set, for reproducible reports."""
    epoch = os.environ.get("SOURCE_DATE_EPOCH")
    return utc_timestamp(float(epoch)) if epoch else utc_timestamp()


@app.command()
def analyze(
    stack_file: Annotated[Path, typer.Argument(help="YAML stack definition (units: mm).")],
    fmt: Annotated[
        OutputFormat, typer.Option("--format", "-f", help="Report format.")
    ] = OutputFormat.md,
    out: Annotated[
        Path | None,
        typer.Option("--out", "-o", help="Output directory. Without it the report goes to stdout."),
    ] = None,
) -> None:
    """Analyse a tolerance stack and write a report.

    With --out DIR the report is written to DIR/<name>.<format>; the Markdown
    format also writes DIR/<name>_histogram.png when Monte Carlo was run.
    Without --out the report is printed to stdout (Markdown then has no image).
    """
    try:
        stack = load_stack(stack_file)
    except StackInputError as exc:
        for message in exc.errors:
            typer.echo(f"error: {message}", err=True)
        raise typer.Exit(EXIT_INPUT_ERROR) from exc

    result = run_analysis(stack)
    report = build_report(
        result,
        version=detecttol.__version__,
        generated_at=_timestamp(),
        input_file=stack_file.as_posix(),
    )
    base = _safe_name(stack.name)

    if out is not None:
        out.mkdir(parents=True, exist_ok=True)

    if fmt is OutputFormat.json:
        text = to_json(report)
    elif fmt is OutputFormat.html:
        text = to_html(report, render_histogram_png(result))
    else:
        histogram_ref = None
        if out is not None:
            png = render_histogram_png(result)
            if png is not None:
                histogram_ref = f"{base}_histogram.png"
                (out / histogram_ref).write_bytes(png)
        text = to_markdown(report, histogram_ref)

    if out is None:
        reconfigure = getattr(sys.stdout, "reconfigure", None)
        if reconfigure is not None:
            with contextlib.suppress(Exception):
                reconfigure(encoding="utf-8")
        typer.echo(text, nl=False)
    else:
        target = out / f"{base}.{fmt.value}"
        target.write_text(text, encoding="utf-8", newline="\n")
        typer.echo(f"wrote {target.as_posix()}")
