"""3D vector loops through YAML, reports and the CLI."""

from __future__ import annotations

import json
import math
from typing import Any

import jsonschema
import pytest
from typer.testing import CliRunner

from detecttol.cli.main import app
from detecttol.core.loop import LoopVariable, VectorLoop
from detecttol.core.loop3d import VectorLoop3D, analyze_loop3d
from detecttol.io import StackInputError, load_loop, parse_loop
from detecttol.report import build_loop_report, load_committed_schema, to_json, to_markdown
from tests.conftest import EXAMPLES

runner = CliRunner()
POST = EXAMPLES / "tilted_post_3d.yaml"
SEVEN_SF = {"rel": 1e-6}


def doc(**loop_extra: Any) -> dict[str, Any]:
    loop: dict[str, Any] = {
        "vectors": [
            {
                "length": 30,
                "angle": 0,
                "roll": {"id": "roll", "nominal": 10.0, "upper_tol": 0.5, "lower_tol": -0.5},
            },
            {
                "length": {"id": "post", "nominal": 40.0, "upper_tol": 0.05, "lower_tol": -0.05},
                "angle": 90,
            },
        ]
    }
    loop.update(loop_extra)
    return {
        "schema_version": 2,
        "units": "mm",
        "angle_units": "deg",
        "name": "post",
        "requirement": {"lsl": 6.5, "usl": 7.4},
        "loop": loop,
    }


def test_example_is_a_3d_loop_in_radians() -> None:
    """roll 10 +/-0.5 deg -> 0.1745329 +/-0.008726646 rad; yaw 90 deg -> pi/2."""
    loaded = load_loop(POST)
    assert isinstance(loaded.loop, VectorLoop3D) and loaded.angle_units == "deg"
    first, second = loaded.loop.vectors
    assert isinstance(first.roll, LoopVariable)
    assert first.roll.nominal == pytest.approx(0.1745329, **SEVEN_SF)
    assert first.roll.upper_tol == pytest.approx(0.008726646, **SEVEN_SF)
    assert second.yaw == pytest.approx(math.pi / 2, rel=1e-12)
    assert (first.length, first.yaw, first.pitch, second.pitch, second.roll) == (30.0, 0, 0, 0, 0)
    assert loaded.loop.measure_direction == (0.0, 0.0, 1.0)


def test_example_matches_the_hand_derived_roll_case() -> None:
    """Same case as tests/core/test_loop3d.py (n = z): Y = 40 sin(10 deg) = 6.945927,
    W = 0.3524452, sigma = 0.1146241."""
    r = analyze_loop3d(load_loop(POST).loop).result  # type: ignore[arg-type]
    assert r.worst_case is not None and r.rss is not None
    assert r.mean == pytest.approx(6.945927, **SEVEN_SF)
    assert r.worst_case.half_range == pytest.approx(0.3524452, **SEVEN_SF)
    assert r.rss.sigma == pytest.approx(0.1146241, **SEVEN_SF)


def test_a_file_without_pitch_roll_or_direction_stays_2d() -> None:
    d = doc()
    del d["loop"]["vectors"][0]["roll"]
    d["loop"]["vectors"][0]["angle"] = {"id": "a", "nominal": 0, "upper_tol": 1, "lower_tol": -1}
    assert isinstance(parse_loop(d).loop, VectorLoop)


def test_measure_angle_gives_an_in_plane_direction_for_a_3d_loop() -> None:
    """measure_angle 90 deg with a 3D loop -> direction (cos 90, sin 90, 0) = (0, 1, 0);
    then Y = 40 cos(10 deg) = 39.39231."""
    loop = parse_loop(doc(measure_angle=90)).loop
    assert isinstance(loop, VectorLoop3D)
    assert loop.measure_direction == pytest.approx((0.0, 1.0, 0.0), abs=1e-15)
    assert analyze_loop3d(loop).result.mean == pytest.approx(39.39231, **SEVEN_SF)


def test_direction_is_normalised() -> None:
    loop = parse_loop(doc(measure_direction=[0, 0, 5])).loop
    assert isinstance(loop, VectorLoop3D)
    assert list(loop.unit_direction()) == [0.0, 0.0, 1.0]


@pytest.mark.parametrize(
    ("extra", "prefix"),
    [
        ({"measure_direction": [0, 0, 1], "measure_angle": 30}, "loop.measure_direction:"),
        ({"measure_direction": [0, 0, 0]}, "loop.measure_direction:"),
        ({"measure_direction": [0, 1]}, "loop.measure_direction:"),
        ({"measure_direction": [0, 1, "up"]}, "loop.measure_direction"),
    ],
)
def test_bad_direction_names_the_field(extra: dict[str, Any], prefix: str) -> None:
    with pytest.raises(StackInputError) as info:
        parse_loop(doc(**extra))
    assert any(m.startswith(prefix) for m in info.value.errors), info.value.errors


def test_bad_pitch_names_the_field() -> None:
    d = doc()
    d["loop"]["vectors"][1]["pitch"] = {"id": "p", "nominal": 0, "upper_tol": -1, "lower_tol": 1}
    with pytest.raises(StackInputError) as info:
        parse_loop(d)
    assert any(m.startswith("loop.vectors[1].pitch") for m in info.value.errors), info.value.errors


def test_report_for_a_3d_loop() -> None:
    """Display in degrees: roll sensitivity 39.39231 mm/rad * pi/180 = 0.6875255 mm/deg
    -> shown as 0.687526; sigma 0.5/3 = 0.166667 deg. JSON keeps radians (39.39231)."""
    loaded = load_loop(POST)
    assert isinstance(loaded.loop, VectorLoop3D)
    report = build_loop_report(
        analyze_loop3d(loaded.loop),
        measure_direction=[float(v) for v in loaded.loop.unit_direction()],
        angle_units="deg",
        version="0.0.0-test",
        generated_at="2026-01-01T00:00:00Z",
    )
    md = to_markdown(report)
    assert "| roll | deg | 10 | 0.5 | -0.5 | 0.687526 | normal | 1 | 10 | 0.5 | 0.166667 |" in md
    assert "| roll | roll | deg | 1 | 0.687526 | 0.687526 |" in md
    assert "- Measurement direction: (0, 0, 1) unit vector" in md
    assert "relative, 3D" in md and "positive tilts towards -z" in md
    document = json.loads(to_json(report))
    jsonschema.validate(document, load_committed_schema(2), cls=jsonschema.Draft202012Validator)
    assert document["loop"]["measure_angle"] is None
    assert document["loop"]["measure_direction"] == [0.0, 0.0, 1.0]
    assert document["loop"]["variables"][0]["kind"] == "roll"
    assert document["loop"]["variables"][0]["sensitivity_analytic"] == pytest.approx(
        39.39231, **SEVEN_SF
    )


def test_report_needs_exactly_one_direction_form() -> None:
    result = analyze_loop3d(load_loop(POST).loop)  # type: ignore[arg-type]
    common = {"angle_units": "deg", "version": "x", "generated_at": "t"}
    with pytest.raises(ValueError, match="exactly one"):
        build_loop_report(result, **common)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="exactly one"):
        build_loop_report(  # type: ignore[arg-type]
            result, measure_angle=0.0, measure_direction=[0.0, 0.0, 1.0], **common
        )


def test_cli_runs_the_3d_example() -> None:
    md = runner.invoke(app, ["analyze", str(POST)])
    assert md.exit_code == 0, md.output
    assert "## Vector loop" in md.stdout and "unit vector" in md.stdout
    js = runner.invoke(app, ["analyze", str(POST), "--format", "json"])
    assert js.exit_code == 0, js.output
    document = json.loads(js.stdout)
    assert document["schema_version"] == 2
    assert document["result"]["mean"] == pytest.approx(6.945927, **SEVEN_SF)
