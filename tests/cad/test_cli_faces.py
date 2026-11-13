"""``detecttol faces model.step``: selectors that can be pasted into an annotation file."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

pytest.importorskip("OCC", reason="pythonocc-core is not installed")

from detecttol.cad.annotations import parse_annotations, resolve_annotations
from detecttol.cad.step_reader import read_step
from detecttol.cad.synthetic import BoxPart, write_box_assembly
from detecttol.cli.main import app

runner = CliRunner()


def test_faces_command_output_is_yaml_that_resolves(tmp_path: Path) -> None:
    """A 2 x 3 x 4 box has 6 planar faces; the printed selectors are valid YAML and
    each one binds back to the face it describes. Top face: centroid (1, 1.5, 4)."""
    step = tmp_path / "box.step"
    write_box_assembly(step, [BoxPart("BOX", (2.0, 3.0, 4.0))])
    result = runner.invoke(app, ["faces", str(step)])
    assert result.exit_code == 0, result.output
    assert "semantic PMI: 0 dimensions, 0 geometric tolerances, 0 datums" in result.stdout
    rows = yaml.safe_load(result.stdout)["faces"]
    assert len(rows) == 6
    assert {
        "part": "BOX",
        "face": 5,
        "centroid": [1.0, 1.5, 4.0],
        "normal": [0.0, 0.0, 1.0],
    } in rows
    doc = {
        "schema_version": 1,
        "units": "mm",
        "annotations": [
            {"id": chr(ord("A") + i), "kind": "datum", "on": row} for i, row in enumerate(rows)
        ],
    }
    resolved = resolve_annotations(read_step(step), parse_annotations(doc))
    assert [ref.face_index for _d, ref in resolved.datums] == [0, 1, 2, 3, 4, 5]


def test_faces_command_reports_bad_files(tmp_path: Path) -> None:
    result = runner.invoke(app, ["faces", str(tmp_path / "missing.step")])
    assert result.exit_code == 2 and "STEP file not found" in result.stderr
    bad = tmp_path / "bad.step"
    bad.write_text("nope", encoding="utf-8")
    result = runner.invoke(app, ["faces", str(bad)])
    assert result.exit_code == 2 and "not a readable STEP file" in result.stderr
