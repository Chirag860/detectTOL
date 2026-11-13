"""Command-line interface: ``detecttol analyze stack.yaml [--format md|html|json] [--out DIR]``."""

from __future__ import annotations

import contextlib
import json
import os
import re
import sys
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any

import typer
import yaml

import detecttol
from detecttol.core.analyze import analyze as run_analysis
from detecttol.core.loop import analyze_loop
from detecttol.core.loop3d import VectorLoop3D, analyze_loop3d
from detecttol.io import LoopInput, StackInputError, load_input
from detecttol.report import (
    AnyReport,
    build_loop_report,
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


def _load(path: Path) -> Any:
    """Load any input file; a STEP-based stack (``step_file:``) needs pythonocc-core."""
    try:
        peek = yaml.safe_load(path.read_text(encoding="utf-8")) if path.is_file() else None
    except (yaml.YAMLError, OSError, UnicodeDecodeError):
        peek = None
    if isinstance(peek, dict) and "step_file" in peek:
        try:
            # Imported here so that the rest of the CLI works without pythonocc-core.
            from detecttol.cad.step_stack import build_step_stack
        except ImportError as exc:
            raise StackInputError(
                [
                    "step_file: reading STEP files needs pythonocc-core"
                    " (install the conda environment)"
                ]
            ) from exc
        return build_step_stack(peek, path.parent).stack
    return load_input(path)


@app.command()
def faces(
    step_file: Annotated[Path, typer.Argument(help="STEP file (.step / .stp).")],
) -> None:
    """List the planar faces of a STEP model as annotation-file selectors (YAML).

    Each entry gives part name, face index, centroid [mm] and outward normal:
    copy the ones you need into an annotation file. Also prints how much
    semantic PMI the file contains. Needs pythonocc-core (conda-forge).
    """
    try:
        # Imported here so that the rest of the CLI works without pythonocc-core.
        from detecttol.cad.annotations import face_table
        from detecttol.cad.step_reader import StepReadError, read_step
    except ImportError as exc:
        typer.echo(
            "error: reading STEP files needs pythonocc-core (install the conda environment)",
            err=True,
        )
        raise typer.Exit(EXIT_INPUT_ERROR) from exc
    try:
        model = read_step(step_file)
    except StepReadError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(EXIT_INPUT_ERROR) from exc
    lines = [
        f"# {step_file.as_posix()}",
        f"# parts: {len(model.parts)}; semantic PMI: {len(model.dimensions)} dimensions,"
        f" {len(model.geometric_tolerances)} geometric tolerances, {len(model.datums)} datums",
    ]
    lines += [f"# note: {note}" for note in model.notes]
    lines.append("faces:")
    for row in face_table(model):
        lines.append(
            f"  - {{part: {json.dumps(row['part'])}, face: {row['face']},"
            f" centroid: {row['centroid']}, normal: {row['normal']}}}  # area {row['area']} mm^2"
        )
    typer.echo("\n".join(lines))


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
    """Analyse a tolerance stack or a 2D vector loop and write a report.

    The file is a linear stack (schema_version 1, `contributors`) or a vector
    loop (schema_version 2, `loop` and `angle_units`).

    With --out DIR the report is written to DIR/<name>.<format>; the Markdown
    format also writes DIR/<name>_histogram.png when Monte Carlo was run.
    Without --out the report is printed to stdout (Markdown then has no image).
    """
    try:
        loaded = _load(stack_file)
    except StackInputError as exc:
        for message in exc.errors:
            typer.echo(f"error: {message}", err=True)
        raise typer.Exit(EXIT_INPUT_ERROR) from exc

    report: AnyReport
    if isinstance(loaded, LoopInput):
        if isinstance(loaded.loop, VectorLoop3D):
            loop_result = analyze_loop3d(loaded.loop)
            direction: dict[str, Any] = {
                "measure_direction": [float(v) for v in loaded.loop.unit_direction()]
            }
        else:
            loop_result = analyze_loop(loaded.loop)
            direction = {"measure_angle": loaded.loop.measure_angle}
        result = loop_result.result
        report = build_loop_report(
            loop_result,
            **direction,
            angle_units=loaded.angle_units,
            version=detecttol.__version__,
            generated_at=_timestamp(),
            input_file=stack_file.as_posix(),
        )
        name = loaded.loop.name
    else:
        result = run_analysis(loaded)
        report = build_report(
            result,
            version=detecttol.__version__,
            generated_at=_timestamp(),
            input_file=stack_file.as_posix(),
        )
        name = loaded.name
    base = _safe_name(name)

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
