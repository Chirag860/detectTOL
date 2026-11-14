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
from detecttol.core.models import AnalysisConfig, MonteCarloConfig
from detecttol.core.results import StackResult
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
from detecttol.standards.lookup import check_general_class, look_up

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


def _cad_modules() -> Any:
    """Import the CAD stack builder (needs pythonocc-core), or exit with a clear message."""
    try:
        from detecttol.cad import cad_stack
    except ImportError as exc:
        typer.echo(
            "error: reading CAD files needs pythonocc-core (install the conda environment)",
            err=True,
        )
        raise typer.Exit(EXIT_INPUT_ERROR) from exc
    return cad_stack


@app.command()
def faces(
    cad_file: Annotated[
        Path, typer.Argument(help="STEP file (.step / .stp) or SolidWorks assembly (.SLDASM).")
    ],
    drawing: Annotated[
        list[Path] | None,
        typer.Option("--drawing", "-d", help="SolidWorks drawing (.SLDDRW) to read too."),
    ] = None,
) -> None:
    """List the planar faces of a model, with the tolerances found on each.

    Each entry gives part name, face index, centroid [mm] and outward normal; use
    `PART:FACE` with `detecttol analyze-cad`, or copy the entry into an annotation
    file. A SolidWorks assembly is read through the installed SolidWorks
    (read-only; about 20 s). Needs pythonocc-core (conda-forge).
    """
    cad_stack = _cad_modules()
    from detecttol.cad.annotations import face_table
    from detecttol.cad.step_reader import StepReadError

    try:
        cad = cad_stack.read_cad(cad_file, drawing or ())
    except (cad_stack.CadStackError, StepReadError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(EXIT_INPUT_ERROR) from exc
    model = cad.model
    on_face: dict[tuple[str, int], list[str]] = {}
    for dim in cad.dimensions:
        text = f"{dim.id} {dim.nominal:g} {dim.upper_tol:+g}/{dim.lower_tol:+g}"
        for ref in (dim.from_face, dim.to_face):
            on_face.setdefault((ref.part, ref.face_index), []).append(text)
    for callout, ref in cad.flatness:
        on_face.setdefault((ref.part, ref.face_index), []).append(
            f"{callout.id} flatness {callout.tolerance:g}"
        )
    lines = [
        f"# {cad_file.as_posix()}",
        f"# parts: {len(model.parts)}; semantic PMI: {len(model.dimensions)} dimensions,"
        f" {len(model.geometric_tolerances)} geometric tolerances, {len(model.datums)} datums",
        f"# usable tolerances from {cad.origin}:"
        f" {len(cad.dimensions)} dimensions, {len(cad.flatness)} flatness",
    ]
    lines += [f"# note: {note}" for note in (*model.notes, *cad.notes)]
    lines.append("faces:")
    for row in face_table(model):
        found = on_face.get((row["part"], row["face"]), [])
        tail = f"; {'; '.join(found)}" if found else ""
        lines.append(
            f"  - {{part: {json.dumps(row['part'])}, face: {row['face']},"
            f" centroid: {row['centroid']}, normal: {row['normal']}}}"
            f"  # area {row['area']} mm^2{tail}"
        )
    typer.echo("\n".join(lines))


@app.command("analyze-cad")
def analyze_cad(
    cad_file: Annotated[
        Path, typer.Argument(help="SolidWorks assembly (.SLDASM) or STEP file (.step / .stp).")
    ],
    face_from: Annotated[str, typer.Option("--from", help="First face, PART:FACE.")],
    face_to: Annotated[str, typer.Option("--to", help="Second face, PART:FACE.")],
    drawing: Annotated[
        list[Path] | None,
        typer.Option("--drawing", "-d", help="SolidWorks drawing (.SLDDRW) to read too."),
    ] = None,
    lsl: Annotated[
        float | None, typer.Option(help="Lower spec limit [mm]; default 0 (gap >= 0).")
    ] = None,
    usl: Annotated[float | None, typer.Option(help="Upper spec limit [mm].")] = None,
    standard: Annotated[str | None, typer.Option(help="Drawing standard: asme, iso or is.")] = None,
    general_class: Annotated[
        str | None,
        typer.Option(
            "--general", "-g", help="General tolerance class f/m/c/v for untoleranced dimensions."
        ),
    ] = None,
    samples: Annotated[int, typer.Option(help="Monte Carlo samples.")] = 100_000,
    seed: Annotated[int, typer.Option(help="Monte Carlo seed.")] = 42,
    fmt: Annotated[
        OutputFormat, typer.Option("--format", "-f", help="Report format.")
    ] = OutputFormat.md,
    out: Annotated[
        Path | None,
        typer.Option("--out", "-o", help="Output directory. Without it the report goes to stdout."),
    ] = None,
) -> None:
    """Analyse the gap between two faces of a CAD model, tolerances read from the model.

    Example: `detecttol analyze-cad Tolerance_Test.SLDASM --from Block_C:2 --to Frame:4
    --standard is --general m`. Face numbers come from `detecttol faces`.
    """
    cad_stack = _cad_modules()
    from detecttol.cad.step_reader import StepReadError

    if standard not in (None, "asme", "iso", "is"):
        typer.echo(f"error: --standard must be asme, iso or is, got {standard!r}", err=True)
        raise typer.Exit(EXIT_INPUT_ERROR)
    try:
        general_checked = check_general_class(general_class)
        cad = cad_stack.read_cad(cad_file, drawing or ())
        built = cad_stack.build_cad_stack(
            cad,
            cad_stack.parse_face(face_from),
            cad_stack.parse_face(face_to),
            lsl=0.0 if lsl is None and usl is None else lsl,
            usl=usl,
            standard=standard,  # type: ignore[arg-type]
            general_class=general_checked,
            name=_safe_name(cad_file.stem),
            description=f"distance {face_from} -> {face_to}",
            analysis=AnalysisConfig(
                methods=["worst_case", "rss", "monte_carlo"],
                monte_carlo=MonteCarloConfig(n=samples, seed=seed),
            ),
        )
    except (cad_stack.CadStackError, StepReadError, ValueError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(EXIT_INPUT_ERROR) from exc
    for note in (*built.cad.notes, *built.notes):
        typer.echo(f"note: {note}", err=True)
    result = built.analyze()
    report = build_report(
        result,
        version=detecttol.__version__,
        generated_at=_timestamp(),
        input_file=cad_file.as_posix(),
    )
    _write(report, result, built.stack.name, fmt, out)


@app.command()
def limits(
    size: Annotated[float, typer.Argument(help="Basic (nominal) size in mm.")],
    tolerance_class: Annotated[
        str, typer.Argument(help="ISO 286 class (H7, h6, JS9, js8) or 'general'.")
    ],
    general_class: Annotated[
        str | None,
        typer.Option("--general", "-g", help="General tolerance class f, m, c or v (IS 2102)."),
    ] = None,
) -> None:
    """Print the limit deviations of a tolerance class at one size.

    Examples: `detecttol limits 25 H7`, `detecttol limits 25 general --general m`.
    """
    try:
        found = look_up(size, tolerance_class, check_general_class(general_class))
    except ValueError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(EXIT_INPUT_ERROR) from exc
    typer.echo(
        f"{size:g} {tolerance_class}: upper {found.upper_tol:+g} mm, lower {found.lower_tol:+g} mm"
    )
    typer.echo(f"source: {found.source}")
    if not found.verified:
        typer.echo("warning: this table has not yet been checked against a printed copy")


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
    _write(report, result, name, fmt, out)


def _write(
    report: AnyReport, result: StackResult, name: str, fmt: OutputFormat, out: Path | None
) -> None:
    """Render ``report`` in ``fmt`` to stdout or ``out/<name>.<fmt>``."""
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
