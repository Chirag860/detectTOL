"""Report rendering: JSON schema conformance and snapshots of golden case A.

Snapshots live in tests/report/snapshots/. To regenerate after an intended
change, run pytest with DETECTTOL_UPDATE_SNAPSHOTS=1 and review the diff.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import jsonschema
import pytest

from detecttol import analyze
from detecttol.io import load_stack
from detecttol.report import (
    Report,
    build_report,
    generate_json_schema,
    load_committed_schema,
    render_histogram_png,
    to_html,
    to_json,
    to_markdown,
    utc_timestamp,
)
from detecttol.report.render import fmt, sorted_contributors
from tests.conftest import EXAMPLES, LINEAR_EXAMPLES, contributor, make_stack

SNAPSHOTS = Path(__file__).parent / "snapshots"
FIXED_TIME = "2026-01-01T00:00:00Z"
FIXED_VERSION = "0.0.0-test"
UPDATE = os.environ.get("DETECTTOL_UPDATE_SNAPSHOTS") == "1"


def report_for(example: str) -> Report:
    result = analyze(load_stack(EXAMPLES / example))
    return build_report(
        result, version=FIXED_VERSION, generated_at=FIXED_TIME, input_file=f"examples/{example}"
    )


@pytest.fixture(scope="module")
def report_a() -> Report:
    return report_for("golden_case_a.yaml")


def _snapshot(name: str, text: str) -> str:
    path = SNAPSHOTS / name
    if UPDATE:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
    return path.read_text(encoding="utf-8")


def _assert_close(actual: Any, expected: Any, where: str = "$") -> None:
    """Recursive equality; floats compared with rel=1e-9, abs=1e-12.

    Monte Carlo statistics may differ in the last bits between platforms
    (summation order in numpy), so the JSON snapshot is not compared as text.
    """
    if isinstance(expected, dict):
        assert isinstance(actual, dict), where
        assert actual.keys() == expected.keys(), where
        for key in expected:
            _assert_close(actual[key], expected[key], f"{where}.{key}")
    elif isinstance(expected, list):
        assert isinstance(actual, list) and len(actual) == len(expected), where
        for i, (a, e) in enumerate(zip(actual, expected, strict=True)):
            _assert_close(a, e, f"{where}[{i}]")
    elif isinstance(expected, float):
        assert actual == pytest.approx(expected, rel=1e-9, abs=1e-12), where
    else:
        assert actual == expected, where


def test_committed_schema_matches_the_model() -> None:
    """The committed JSON Schema file must be regenerated when the model changes."""
    assert load_committed_schema() == generate_json_schema()


@pytest.mark.parametrize("example", [p.name for p in LINEAR_EXAMPLES])
def test_json_output_validates_against_committed_schema(example: str) -> None:
    schema = load_committed_schema()
    jsonschema.Draft202012Validator.check_schema(schema)
    document = json.loads(to_json(report_for(example)))
    jsonschema.validate(document, schema, cls=jsonschema.Draft202012Validator)
    assert document["schema_version"] == 1


def test_schema_rejects_a_broken_document(report_a: Report) -> None:
    schema = load_committed_schema()
    document = json.loads(to_json(report_a))
    del document["result"]["mean"]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(document, schema, cls=jsonschema.Draft202012Validator)
    document = json.loads(to_json(report_a))
    document["schema_version"] = 2
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(document, schema, cls=jsonschema.Draft202012Validator)


def test_json_snapshot_golden_case_a(report_a: Report) -> None:
    text = to_json(report_a)
    expected = json.loads(_snapshot("golden_case_a.json", text))
    _assert_close(json.loads(text), expected)


def test_json_round_trips_through_the_model(report_a: Report) -> None:
    assert Report.model_validate_json(to_json(report_a)) == report_a


def test_markdown_snapshot_golden_case_a(report_a: Report) -> None:
    text = to_markdown(report_a, histogram_ref="plate_stack_in_slot_histogram.png")
    assert text == _snapshot("golden_case_a.md", text)


def test_markdown_contains_every_required_section(report_a: Report) -> None:
    """Spec Phase 2: input summary, results per method, sorted contribution table,
    warnings, tool version, seed and timestamp."""
    text = to_markdown(report_a)
    for needle in (
        "## Input summary",
        "### Worst case",
        "### RSS (statistical)",
        "### Monte Carlo",
        "## Contributions (sorted, largest first)",
        "## Warnings",
        "WORST_CASE_FAILS_SPEC",
        "MC_ZERO_FAILURES",
        f"detecttol {FIXED_VERSION}",
        "seed 42",
        f"generated {FIXED_TIME}",
        "Not 0 ppm",
    ):
        assert needle in text, needle
    assert "![Monte Carlo histogram]" not in text  # no image reference unless given


def test_contribution_table_is_sorted_descending() -> None:
    """Input order is deliberately ascending; the table must come out descending."""
    stack = make_stack(
        [
            contributor("small", 5.0, 0.01, -0.01, 1.0),
            contributor("medium", 5.0, 0.05, -0.05, 1.0),
            contributor("large", 5.0, 0.20, -0.20, -1.0),
        ],
        lsl=0.0,
    )
    result = analyze(stack)
    assert [c.id for c in sorted_contributors(result)] == ["large", "medium", "small"]
    report = build_report(result, version=FIXED_VERSION, generated_at=FIXED_TIME)
    table = to_markdown(report).split("## Contributions")[1]
    assert table.index("large") < table.index("medium") < table.index("small")


def test_markdown_for_warning_free_stack_and_modified_rss() -> None:
    stack = make_stack([contributor("d", 10.0, 0.1, -0.1, 1.0)], lsl=9.0, usl=11.0, k=1.0)
    text = to_markdown(build_report(analyze(stack), version=FIXED_VERSION, generated_at=FIXED_TIME))
    assert "None." in text.split("## Warnings")[1]
    assert "### Modified RSS (Bender, k = 1)" in text
    assert "seed n/a" in text and "Input file: n/a" in text
    assert "### Monte Carlo" not in text


def test_html_report_is_self_contained_and_escaped() -> None:
    stack = make_stack(
        [contributor("<b>bolt</b>", 10.0, 0.3, -0.3, 1.0, "uniform")],
        lsl=9.85,
        usl=10.24,
        n=2000,
        k=1.5,
    )
    result = analyze(stack)
    report = build_report(result, version=FIXED_VERSION, generated_at=FIXED_TIME)
    png = render_histogram_png(result)
    assert png is not None and png.startswith(b"\x89PNG")
    html = to_html(report, png)
    assert html.startswith("<!doctype html>")
    assert "data:image/png;base64," in html
    assert "&lt;b&gt;bolt&lt;/b&gt;" in html and "<b>bolt</b>" not in html
    assert "RSS_EXCEEDS_WORST_CASE" in html and "Modified RSS" in html
    assert FIXED_TIME in html and FIXED_VERSION in html
    # No histogram supplied -> no image tag.
    assert "<img" not in to_html(report)


def test_html_zero_failure_wording(report_a: Report) -> None:
    html = to_html(report_a, render_histogram_png(report_a.result))
    assert "Not 0 ppm" in html and '<span class="bad">NO</span>' in html


def test_histogram_absent_without_monte_carlo_and_ok_for_constant_output() -> None:
    no_mc = analyze(make_stack([contributor("d", 10.0, 0.1, -0.1, 1.0)], usl=11.0))
    assert render_histogram_png(no_mc) is None
    constant = analyze(make_stack([contributor("d", 10.0, 0.0, 0.0, 1.0)], usl=11.0, n=50))
    png = render_histogram_png(constant)
    assert png is not None and png.startswith(b"\x89PNG")


def test_fmt_and_timestamp_helpers() -> None:
    assert fmt(None) == "n/a"
    assert fmt(0.0) == "0" and fmt(-0.0) == "0"
    assert fmt(0.132287566) == "0.132288"
    assert fmt(2.872356e-06) == "2.87236e-06"
    assert utc_timestamp(0) == "1970-01-01T00:00:00Z"
    assert len(utc_timestamp()) == 20 and utc_timestamp().endswith("Z")
