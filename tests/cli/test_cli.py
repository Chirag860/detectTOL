"""CLI: ``detecttol analyze stack.yaml [--format md|html|json] [--out DIR]``."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import jsonschema
import pytest
from typer.testing import CliRunner

import detecttol
from detecttol.cli.main import app
from detecttol.report import load_committed_schema
from tests.conftest import EXAMPLES

runner = CliRunner()
CASE_A = str(EXAMPLES / "golden_case_a.yaml")


def test_default_format_is_markdown_on_stdout() -> None:
    result = runner.invoke(app, ["analyze", CASE_A])
    assert result.exit_code == 0, result.output
    assert result.stdout.startswith("# Tolerance stack report: plate_stack_in_slot")
    assert "Half-range: 0.25" in result.stdout
    assert "Sigma: 0.0440959" in result.stdout
    assert re.search(r"generated \d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", result.stdout)
    assert f"detecttol {detecttol.__version__}" in result.stdout


def test_json_on_stdout_follows_schema() -> None:
    result = runner.invoke(app, ["analyze", CASE_A, "--format", "json"])
    assert result.exit_code == 0, result.output
    document = json.loads(result.stdout)
    jsonschema.validate(document, load_committed_schema(), cls=jsonschema.Draft202012Validator)
    assert document["tool"] == {"name": "detecttol", "version": detecttol.__version__}
    assert document["result"]["monte_carlo"]["seed"] == 42
    assert document["result"]["mean"] == pytest.approx(0.20, rel=1e-12)


def test_source_date_epoch_makes_the_timestamp_reproducible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1767225600")  # 2026-01-01T00:00:00Z
    first = runner.invoke(app, ["analyze", CASE_A, "--format", "json"])
    second = runner.invoke(app, ["analyze", CASE_A, "--format", "json"])
    assert first.exit_code == 0
    assert first.stdout == second.stdout
    assert json.loads(first.stdout)["generated_at"] == "2026-01-01T00:00:00Z"


@pytest.mark.parametrize("fmt", ["md", "html", "json"])
def test_out_directory_receives_the_report(tmp_path: Path, fmt: str) -> None:
    out = tmp_path / "nested" / "reports"
    result = runner.invoke(app, ["analyze", CASE_A, "--format", fmt, "--out", str(out)])
    assert result.exit_code == 0, result.output
    target = out / f"plate_stack_in_slot.{fmt}"
    assert target.is_file()
    assert "wrote" in result.stdout and target.name in result.stdout
    text = target.read_text(encoding="utf-8")
    histogram = out / "plate_stack_in_slot_histogram.png"
    if fmt == "md":
        assert histogram.read_bytes().startswith(b"\x89PNG")
        assert "![Monte Carlo histogram](plate_stack_in_slot_histogram.png)" in text
    else:
        assert not histogram.exists()
    if fmt == "html":
        assert "data:image/png;base64," in text
    if fmt == "json":
        assert json.loads(text)["schema_version"] == 1


def test_validation_error_exits_2_and_names_the_field(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        (EXAMPLES / "golden_case_a.yaml").read_text(encoding="utf-8").replace("cp: 1.0", "cp: 0"),
        encoding="utf-8",
    )
    result = runner.invoke(app, ["analyze", str(bad)])
    assert result.exit_code == 2
    assert "error: contributors[0].cp:" in result.stderr
    assert result.stdout == ""


def test_missing_file_exits_2() -> None:
    result = runner.invoke(app, ["analyze", "does_not_exist.yaml"])
    assert result.exit_code == 2
    assert "file not found" in result.stderr


def test_unknown_format_is_rejected() -> None:
    result = runner.invoke(app, ["analyze", CASE_A, "--format", "pdf"])
    assert result.exit_code != 0


def test_version_option() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.stdout.strip() == f"detecttol {detecttol.__version__}"


def test_python_dash_m_entry_point_runs_end_to_end() -> None:
    """Real subprocess (no test runner in between): stdout is valid UTF-8 JSON and
    stderr stays clean (library warnings are not printed)."""
    proc = subprocess.run(
        [sys.executable, "-m", "detecttol", "analyze", CASE_A, "--format", "json"],
        check=False,
        capture_output=True,
    )
    assert proc.returncode == 0, proc.stderr.decode()
    assert proc.stderr == b""
    document = json.loads(proc.stdout.decode("utf-8"))
    assert document["result"]["name"] == "plate_stack_in_slot"
