"""Vector-loop reports (schema version 2) and the CLI on loop files."""

from __future__ import annotations

import json
import math
from pathlib import Path

import jsonschema
import pytest
from typer.testing import CliRunner

from detecttol.cli.main import app
from detecttol.core.loop import LoopVariable, LoopVector, VectorLoop, analyze_loop
from detecttol.core.models import AnalysisConfig, MonteCarloConfig, Requirement
from detecttol.io import load_loop
from detecttol.report import (
    LoopReport,
    build_loop_report,
    generate_json_schema,
    load_committed_schema,
    render_histogram_png,
    to_html,
    to_json,
    to_markdown,
)
from tests.conftest import EXAMPLES, LOOP_EXAMPLES
from tests.report.test_report import FIXED_TIME, FIXED_VERSION, _assert_close, _snapshot

runner = CliRunner()
WEDGE = EXAMPLES / "wedge_height.yaml"
V2 = jsonschema.Draft202012Validator


def loop_report_for(path: Path) -> LoopReport:
    loaded = load_loop(path)
    return build_loop_report(
        analyze_loop(loaded.loop),
        measure_angle=loaded.loop.measure_angle,
        angle_units=loaded.angle_units,
        version=FIXED_VERSION,
        generated_at=FIXED_TIME,
        input_file=f"examples/{path.name}",
    )


@pytest.fixture(scope="module")
def wedge_report() -> LoopReport:
    return loop_report_for(WEDGE)


def test_committed_v2_schema_matches_the_model() -> None:
    assert load_committed_schema(2) == generate_json_schema(2)
    assert load_committed_schema(1) == generate_json_schema(1)  # v1 untouched


@pytest.mark.parametrize("path", LOOP_EXAMPLES, ids=lambda p: p.name)
def test_loop_json_validates_against_v2_schema_only(path: Path) -> None:
    document = json.loads(to_json(loop_report_for(path)))
    V2.check_schema(load_committed_schema(2))
    jsonschema.validate(document, load_committed_schema(2), cls=V2)
    assert document["schema_version"] == 2
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(document, load_committed_schema(1), cls=V2)


def test_json_keeps_radians_and_records_the_input_unit(wedge_report: LoopReport) -> None:
    """JSON is in internal units: theta nominal pi/12 = 0.2617994 rad,
    half-range pi/360 = 0.008726646 rad, sensitivity 80 cos(15 deg) = 77.27407 mm/rad,
    measurement direction pi/2. `angle_units` only records what the file used."""
    doc = json.loads(to_json(wedge_report))
    theta = doc["result"]["contributors"][1]
    assert theta["id"] == "theta"
    assert theta["nominal"] == pytest.approx(0.2617994, rel=1e-6)
    assert theta["half_range"] == pytest.approx(0.008726646, rel=1e-6)
    assert theta["sensitivity"] == pytest.approx(77.27407, rel=1e-6)
    assert doc["loop"]["angle_units"] == "deg"
    assert doc["loop"]["measure_angle"] == pytest.approx(math.pi / 2, rel=1e-12)
    variable = doc["loop"]["variables"][1]
    assert (variable["kind"], variable["unit"], variable["vector_index"]) == ("angle", "rad", 0)
    assert variable["sensitivity_fd"] == pytest.approx(77.27407, rel=1e-6)
    assert LoopReport.model_validate_json(to_json(wedge_report)) == wedge_report


def test_markdown_shows_angles_in_the_input_unit(wedge_report: LoopReport) -> None:
    """Display conversion for a `deg` file (f = 180/pi):

    theta nominal 15, tolerances +0.5 / -0.5, mean 15, half-range 0.5,
    sigma = 0.5/3 = 0.166667 deg,
    sensitivity = 77.27407 mm/rad * pi/180 = 1.348687 mm/deg -> shown as 1.34869.
    The length row is unchanged: sensitivity sin(15 deg) = 0.258819.
    The numbers that matter (WC 0.700225, sigma 0.224947) do not depend on the unit.
    """
    text = to_markdown(wedge_report)
    assert "| theta | deg | 15 | 0.5 | -0.5 | 1.34869 | normal | 1 | 15 | 0.5 | 0.166667 |" in text
    assert "| L | mm | 80 | 0.1 | -0.1 | 0.258819 | normal | 1 | 80 | 0.1 | 0.0333333 |" in text
    assert "| theta | angle | deg | 1 | 1.34869 | 1.34869 | 0.674343 | 0.675123 |" in text
    assert "- Measurement direction: 90 deg" in text
    assert "- Half-range: 0.700225" in text and "- Sigma: 0.224947" in text
    assert "LINEARISED" in text and "relative (counter-clockwise" in text
    assert "report schema v2" in text
    assert "WORST_CASE_FAILS_SPEC" in text


def test_markdown_for_a_radian_file_shows_radians() -> None:
    """Same wedge entered in radians: theta shown as 0.261799 rad, sensitivity 77.2741 mm/rad."""
    loop = VectorLoop(
        name="wedge_rad",
        vectors=[
            LoopVector(
                length=LoopVariable(id="L", nominal=80.0, upper_tol=0.1, lower_tol=-0.1),
                angle=LoopVariable(
                    id="theta",
                    nominal=math.pi / 12,
                    upper_tol=math.pi / 360,
                    lower_tol=-math.pi / 360,
                ),
            )
        ],
        measure_angle=math.pi / 2,
        requirement=Requirement(lsl=20.0, usl=21.4),
    )
    report = build_loop_report(
        analyze_loop(loop),
        measure_angle=loop.measure_angle,
        angle_units="rad",
        version=FIXED_VERSION,
        generated_at=FIXED_TIME,
    )
    text = to_markdown(report)
    assert "| theta | rad | 0.261799 | 0.00872665 | -0.00872665 | 77.2741 |" in text
    assert "- Measurement direction: 1.5708 rad" in text
    assert "Monte Carlo std vs linearised" not in text  # no Monte Carlo requested


def test_loop_warnings_are_listed_with_the_other_warnings() -> None:
    """Pin measured along its own axis (Y = 100 cos theta): both loop warnings
    must appear in the Warnings section of the Markdown and HTML reports."""
    loop = VectorLoop(
        name="pin <axis>",
        vectors=[
            LoopVector(
                length=100.0,
                angle=LoopVariable(id="theta", nominal=0.0, upper_tol=0.03, lower_tol=-0.03),
            )
        ],
        requirement=Requirement(lsl=99.9),
        analysis=AnalysisConfig(
            methods=["worst_case", "rss", "monte_carlo"],
            monte_carlo=MonteCarloConfig(n=20_000, seed=1),
        ),
    )
    result = analyze_loop(loop)
    report = build_loop_report(
        result, measure_angle=0.0, angle_units="rad", version=FIXED_VERSION, generated_at=FIXED_TIME
    )
    warnings_md = to_markdown(report).split("## Warnings")[1]
    for code in ("ZERO_VARIATION", "ZERO_SENSITIVITY", "LINEARISATION_SUSPECT"):
        assert f"**{code}**" in warnings_md
    html = to_html(report, render_histogram_png(result.result))
    assert "<h2>Vector loop</h2>" in html and "ZERO_SENSITIVITY" in html
    assert "pin &lt;axis&gt;" in html and "data:image/png;base64," in html
    assert "<th>Unit</th>" in html


def test_loop_snapshots_wedge(wedge_report: LoopReport) -> None:
    md = to_markdown(wedge_report, histogram_ref="wedge_height_histogram.png")
    assert md == _snapshot("wedge_height.md", md)
    text = to_json(wedge_report)
    _assert_close(json.loads(text), json.loads(_snapshot("wedge_height.json", text)))


def test_linear_reports_have_no_loop_section() -> None:
    result = runner.invoke(app, ["analyze", str(EXAMPLES / "golden_case_a.yaml")])
    assert result.exit_code == 0
    assert "## Vector loop" not in result.stdout and "| Unit |" not in result.stdout
    assert "report schema v1" in result.stdout


def test_cli_markdown_and_json_for_a_loop_file() -> None:
    md = runner.invoke(app, ["analyze", str(WEDGE)])
    assert md.exit_code == 0, md.output
    assert md.stdout.startswith("# Tolerance stack report: wedge_height")
    assert "## Vector loop" in md.stdout and "| theta | deg | 15 |" in md.stdout

    js = runner.invoke(app, ["analyze", str(WEDGE), "--format", "json"])
    assert js.exit_code == 0, js.output
    document = json.loads(js.stdout)
    jsonschema.validate(document, load_committed_schema(2), cls=V2)
    assert document["result"]["mean"] == pytest.approx(20.70552, rel=1e-6)


@pytest.mark.parametrize("fmt", ["md", "html", "json"])
def test_cli_out_directory_for_a_loop_file(tmp_path: Path, fmt: str) -> None:
    result = runner.invoke(app, ["analyze", str(WEDGE), "--format", fmt, "--out", str(tmp_path)])
    assert result.exit_code == 0, result.output
    text = (tmp_path / f"wedge_height.{fmt}").read_text(encoding="utf-8")
    assert "wedge_height" in text
    assert (tmp_path / "wedge_height_histogram.png").exists() is (fmt == "md")


def test_cli_reports_loop_input_errors_with_field_names(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        WEDGE.read_text(encoding="utf-8").replace("angle_units: deg\n", ""), encoding="utf-8"
    )
    result = runner.invoke(app, ["analyze", str(bad)])
    assert result.exit_code == 2
    assert "error: angle_units:" in result.stderr
