"""Validation rules of spec Section 4: every rejection names the field."""

from __future__ import annotations

import copy
from typing import Any

import pytest

from detecttol.io import StackInputError, parse_stack


def valid_doc() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "units": "mm",
        "name": "plate_stack_in_slot",
        "requirement": {"description": "gap", "lsl": 0.0, "usl": None},
        "contributors": [
            {
                "id": "slot_depth",
                "nominal": 50.00,
                "upper_tol": 0.10,
                "lower_tol": -0.10,
                "sensitivity": 1,
                "distribution": "normal",
                "cp": 1.0,
            },
            {
                "id": "plate_1",
                "nominal": 16.60,
                "upper_tol": 0.05,
                "lower_tol": -0.05,
                "sensitivity": -1,
            },
        ],
        "analysis": {
            "methods": ["worst_case", "rss", "monte_carlo"],
            "monte_carlo": {"n": 1000, "seed": 42},
        },
    }


def errors_for(doc: Any) -> list[str]:
    with pytest.raises(StackInputError) as info:
        parse_stack(doc)
    return info.value.errors


def test_valid_document_is_accepted() -> None:
    stack = parse_stack(valid_doc())
    assert stack.contributors[1].distribution == "normal"  # default
    assert stack.contributors[1].cp == 1.0  # default
    assert stack.contributors[0].sensitivity == 1.0  # YAML integer accepted as a number


def test_analysis_block_is_optional() -> None:
    doc = valid_doc()
    del doc["analysis"]
    assert parse_stack(doc).analysis.methods == ["worst_case", "rss"]


def test_missing_units_rejected() -> None:
    doc = valid_doc()
    del doc["units"]
    (msg,) = errors_for(doc)
    assert msg.startswith("units:")


@pytest.mark.parametrize("units", ["inch", "m", "MM", "", 1])
def test_unknown_units_rejected(units: Any) -> None:
    doc = valid_doc()
    doc["units"] = units
    (msg,) = errors_for(doc)
    assert msg.startswith("units:")


def test_upper_tol_below_lower_tol_rejected() -> None:
    doc = valid_doc()
    doc["contributors"][1]["upper_tol"] = -0.2
    (msg,) = errors_for(doc)
    assert msg.startswith("contributors[1]:")
    assert "upper_tol" in msg and "lower_tol" in msg and "plate_1" in msg


def test_equal_tolerances_are_allowed() -> None:
    doc = valid_doc()
    doc["contributors"][1]["upper_tol"] = 0.0
    doc["contributors"][1]["lower_tol"] = 0.0
    assert parse_stack(doc).contributors[1].half_range == 0.0


def test_unknown_distribution_rejected() -> None:
    doc = valid_doc()
    doc["contributors"][0]["distribution"] = "lognormal"
    (msg,) = errors_for(doc)
    assert msg.startswith("contributors[0].distribution:")


def test_duplicate_ids_rejected() -> None:
    doc = valid_doc()
    doc["contributors"][1]["id"] = "slot_depth"
    (msg,) = errors_for(doc)
    assert "contributors" in msg and "duplicate id" in msg and "slot_depth" in msg


@pytest.mark.parametrize("cp", [0.0, -1.0])
def test_non_positive_cp_rejected(cp: float) -> None:
    doc = valid_doc()
    doc["contributors"][0]["cp"] = cp
    (msg,) = errors_for(doc)
    assert msg.startswith("contributors[0].cp:")


def test_requirement_without_limits_rejected() -> None:
    doc = valid_doc()
    doc["requirement"] = {"description": "gap", "lsl": None, "usl": None}
    (msg,) = errors_for(doc)
    assert msg.startswith("requirement:")
    assert "lsl" in msg and "usl" in msg


def test_usl_below_lsl_rejected() -> None:
    doc = valid_doc()
    doc["requirement"] = {"lsl": 1.0, "usl": 0.5}
    (msg,) = errors_for(doc)
    assert msg.startswith("requirement:") and "usl" in msg


def test_monte_carlo_requires_explicit_seed() -> None:
    doc = valid_doc()
    del doc["analysis"]["monte_carlo"]["seed"]
    (msg,) = errors_for(doc)
    assert msg.startswith("analysis.monte_carlo.seed:")

    doc = valid_doc()
    del doc["analysis"]["monte_carlo"]
    (msg,) = errors_for(doc)
    assert msg.startswith("analysis:") and "seed" in msg


@pytest.mark.parametrize(
    ("path", "value", "prefix"),
    [
        (("schema_version",), 2, "schema_version:"),
        (("name",), "", "name:"),
        (("contributors",), [], "contributors:"),
        (("contributors", 0, "nominal"), "fifty", "contributors[0].nominal:"),
        (("contributors", 0, "nominal"), float("nan"), "contributors[0].nominal:"),
        (("contributors", 0, "upper_tol"), float("inf"), "contributors[0].upper_tol:"),
        (("contributors", 0, "sensitivity"), None, "contributors[0].sensitivity:"),
        (("contributors", 0, "id"), "", "contributors[0].id:"),
        (("analysis", "methods"), ["rss", "magic"], "analysis.methods[1]:"),
        (("analysis", "methods"), ["rss", "rss"], "analysis:"),
        (("analysis", "methods"), [], "analysis.methods:"),
        (("analysis", "monte_carlo", "n"), 1, "analysis.monte_carlo.n:"),
        (("analysis", "monte_carlo", "n"), 1000.5, "analysis.monte_carlo.n:"),
        (("analysis", "monte_carlo", "seed"), -1, "analysis.monte_carlo.seed:"),
        (("analysis", "modified_rss_k"), 0.5, "analysis.modified_rss_k:"),
    ],
)
def test_other_invalid_values_name_the_field(
    path: tuple[Any, ...], value: Any, prefix: str
) -> None:
    doc = copy.deepcopy(valid_doc())
    target: Any = doc
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    msgs = errors_for(doc)
    assert any(m.startswith(prefix) for m in msgs), msgs


def test_unknown_field_rejected() -> None:
    doc = valid_doc()
    doc["contributors"][0]["tolerance"] = 0.1
    (msg,) = errors_for(doc)
    assert msg.startswith("contributors[0].tolerance:")


def test_missing_contributor_field_rejected() -> None:
    doc = valid_doc()
    del doc["contributors"][1]["lower_tol"]
    (msg,) = errors_for(doc)
    assert msg.startswith("contributors[1].lower_tol:")


def test_several_errors_are_all_reported() -> None:
    doc = valid_doc()
    del doc["units"]
    doc["contributors"][0]["cp"] = 0
    msgs = errors_for(doc)
    assert len(msgs) == 2


@pytest.mark.parametrize("doc", [None, [], "text", 3])
def test_non_mapping_document_rejected(doc: Any) -> None:
    (msg,) = errors_for(doc)
    assert "mapping" in msg
