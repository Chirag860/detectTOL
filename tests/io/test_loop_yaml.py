"""Vector-loop YAML (schema_version 2): unit conversion at input and validation."""

from __future__ import annotations

import copy
import math
from pathlib import Path
from typing import Any

import pytest

from detecttol import Stack
from detecttol.core.loop import LoopVariable, analyze_loop
from detecttol.io import (
    LoopInput,
    StackInputError,
    load_input,
    load_loop,
    load_stack,
    parse_input,
    parse_loop,
)
from tests.conftest import EXAMPLES, LOOP_EXAMPLES, analyze_any_loop

EXACT = {"rel": 1e-12, "abs": 1e-15}


def wedge_doc(angle_units: str = "deg") -> dict[str, Any]:
    """Wedge of tests/core/test_loop.py: L = 80 +/-0.1 mm, theta = 15 +/-0.5 deg, alpha = 90 deg."""
    k = 1.0 if angle_units == "deg" else math.pi / 180.0
    return {
        "schema_version": 2,
        "units": "mm",
        "angle_units": angle_units,
        "name": "wedge_height",
        "requirement": {"lsl": 20.0, "usl": 21.4},
        "loop": {
            "measure_angle": 90.0 * k,
            "vectors": [
                {
                    "length": {"id": "L", "nominal": 80.0, "upper_tol": 0.1, "lower_tol": -0.1},
                    "angle": {
                        "id": "theta",
                        "nominal": 15.0 * k,
                        "upper_tol": 0.5 * k,
                        "lower_tol": -0.5 * k,
                    },
                }
            ],
        },
    }


def errors_for(doc: Any) -> list[str]:
    with pytest.raises(StackInputError) as info:
        parse_input(doc)
    return info.value.errors


def test_degrees_are_converted_to_radians_at_input() -> None:
    """15 deg = pi/12 = 0.2617994 rad; 0.5 deg = pi/360 = 0.008726646 rad;
    90 deg = pi/2. Lengths are not touched."""
    loaded = parse_loop(wedge_doc("deg"))
    assert loaded.angle_units == "deg"
    loop = loaded.loop
    assert loop.measure_angle == pytest.approx(math.pi / 2, **EXACT)
    vec = loop.vectors[0]
    assert isinstance(vec.angle, LoopVariable) and isinstance(vec.length, LoopVariable)
    assert vec.angle.nominal == pytest.approx(math.pi / 12, **EXACT)
    assert vec.angle.nominal == pytest.approx(0.2617994, rel=1e-6)
    assert vec.angle.upper_tol == pytest.approx(math.pi / 360, **EXACT)
    assert vec.angle.upper_tol == pytest.approx(0.008726646, rel=1e-6)
    assert vec.angle.lower_tol == pytest.approx(-math.pi / 360, **EXACT)
    assert (vec.length.nominal, vec.length.upper_tol, vec.length.lower_tol) == (80.0, 0.1, -0.1)


def test_radian_input_is_left_unchanged() -> None:
    loaded = parse_loop(wedge_doc("rad"))
    assert loaded.angle_units == "rad"
    vec = loaded.loop.vectors[0]
    assert isinstance(vec.angle, LoopVariable)
    assert vec.angle.nominal == 15.0 * math.pi / 180.0
    assert loaded.loop.measure_angle == 90.0 * math.pi / 180.0


def test_degree_and_radian_files_give_the_same_analysis() -> None:
    """Same physical loop in both units -> same result (hand values: wedge test,
    mean 20.70552, WC half-range 0.7002253, sigma 0.2249466)."""
    deg = analyze_loop(parse_loop(wedge_doc("deg")).loop).result
    rad = analyze_loop(parse_loop(wedge_doc("rad")).loop).result
    assert deg.rss is not None and rad.rss is not None and deg.worst_case is not None
    assert deg.mean == pytest.approx(20.70552, rel=1e-6)
    assert deg.worst_case.half_range == pytest.approx(0.7002253, rel=1e-6)
    assert deg.rss.sigma == pytest.approx(0.2249466, rel=1e-6)
    assert rad.mean == pytest.approx(deg.mean, rel=1e-12)
    assert rad.rss.sigma == pytest.approx(deg.rss.sigma, rel=1e-12)


def test_fixed_values_and_yaml_integers_are_accepted() -> None:
    """`angle: 0`, `measure_angle: 90` and `length: 100` written as YAML integers.

    Pin of length 100 along +x measured along +y with theta = 0 +/-1 deg:
    dY/dtheta = 100 mm/rad; WC half-range = 100 * pi/180 = 1.745329 mm.
    """
    doc = {
        "schema_version": 2,
        "units": "mm",
        "angle_units": "deg",
        "name": "pin",
        "requirement": {"usl": 5},
        "loop": {
            "measure_angle": 90,
            "vectors": [
                {
                    "length": 100,
                    "angle": {"id": "theta", "nominal": 0, "upper_tol": 1, "lower_tol": -1},
                },
                {
                    "length": {"id": "ext", "nominal": 5, "upper_tol": 0.1, "lower_tol": -0.1},
                    "angle": 0,
                },
            ],
        },
    }
    loop = parse_loop(doc).loop
    assert loop.vectors[0].length == 100.0 and loop.vectors[1].angle == 0.0
    res = analyze_loop(loop)
    # theta rotates both vectors: -(100 + 5) sin(Theta - pi/2) = 105 at Theta = 0.
    assert res.variables[0].sensitivity_analytic == pytest.approx(105.0, rel=1e-12)
    assert res.result.worst_case is not None
    assert res.result.worst_case.half_range == pytest.approx(
        105 * math.pi / 180, rel=1e-9, abs=1e-9
    )


@pytest.mark.parametrize("path", LOOP_EXAMPLES, ids=lambda p: p.name)
def test_every_loop_example_loads_and_analyses(path: Path) -> None:
    loaded = load_input(path)
    assert isinstance(loaded, LoopInput)
    assert load_loop(path) == loaded
    res = analyze_any_loop(loaded.loop)
    assert res.result.monte_carlo is not None and res.variables


def test_load_input_dispatches_on_the_loop_section() -> None:
    assert isinstance(load_input(EXAMPLES / "golden_case_a.yaml"), Stack)
    assert isinstance(load_input(EXAMPLES / "wedge_height.yaml"), LoopInput)


def test_linear_loader_rejects_a_loop_file() -> None:
    with pytest.raises(StackInputError) as info:
        load_stack(EXAMPLES / "wedge_height.yaml")
    assert any(m.startswith("schema_version:") for m in info.value.errors)


def test_missing_angle_units_rejected() -> None:
    doc = wedge_doc()
    del doc["angle_units"]
    (msg,) = errors_for(doc)
    assert msg.startswith("angle_units:")


@pytest.mark.parametrize("unit", ["grad", "degrees", "DEG", "", 1])
def test_unknown_angle_units_rejected(unit: Any) -> None:
    doc = wedge_doc()
    doc["angle_units"] = unit
    (msg,) = errors_for(doc)
    assert msg.startswith("angle_units:")


def test_missing_or_wrong_length_units_rejected() -> None:
    doc = wedge_doc()
    del doc["units"]
    assert errors_for(doc)[0].startswith("units:")
    doc = wedge_doc()
    doc["units"] = "inch"
    assert errors_for(doc)[0].startswith("units:")


def test_loop_file_must_be_schema_version_2() -> None:
    doc = wedge_doc()
    doc["schema_version"] = 1
    (msg,) = errors_for(doc)
    assert msg.startswith("schema_version:")


@pytest.mark.parametrize(
    ("path", "value", "prefix"),
    [
        (("loop", "vectors"), [], "loop.vectors:"),
        (("loop", "vectors", 0, "angle", "cp"), 0, "loop.vectors[0].angle.cp:"),
        (("loop", "vectors", 0, "angle", "distribution"), "weibull", "loop.vectors[0].angle"),
        (("loop", "vectors", 0, "length", "nominal"), "long", "loop.vectors[0].length"),
        (("loop", "measure_angle"), "up", "loop.measure_angle:"),
        (("loop", "direction"), 1.0, "loop.direction:"),
        (("requirement",), {"lsl": None, "usl": None}, "requirement:"),
    ],
)
def test_invalid_values_name_the_field(path: tuple[Any, ...], value: Any, prefix: str) -> None:
    doc = copy.deepcopy(wedge_doc())
    target: Any = doc
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    msgs = errors_for(doc)
    assert any(m.startswith(prefix) for m in msgs), msgs


def test_upper_below_lower_names_the_variable() -> None:
    doc = wedge_doc()
    doc["loop"]["vectors"][0]["angle"]["upper_tol"] = -1.0
    msgs = errors_for(doc)
    assert any(m.startswith("loop.vectors[0].angle") and "theta" in m for m in msgs), msgs


def test_duplicate_ids_and_no_variables_rejected() -> None:
    doc = wedge_doc()
    doc["loop"]["vectors"][0]["angle"]["id"] = "L"
    (msg,) = errors_for(doc)
    assert msg.startswith("loop.vectors:") and "duplicate" in msg and "L" in msg

    doc = wedge_doc()
    doc["loop"]["vectors"] = [{"length": 80.0, "angle": 15.0}]
    (msg,) = errors_for(doc)
    assert msg.startswith("loop.vectors:") and "toleranced" in msg


def test_monte_carlo_seed_still_required() -> None:
    doc = wedge_doc()
    doc["analysis"] = {"methods": ["monte_carlo"], "monte_carlo": {"n": 100}}
    (msg,) = errors_for(doc)
    assert msg.startswith("analysis.monte_carlo.seed:")
