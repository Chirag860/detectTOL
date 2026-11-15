"""Against a real SOLIDWORKS 2026 (only with DETECTTOL_SOLIDWORKS=1; see pyproject markers).

Reads examples/solidworks (built and checked in Step 1, docs/reports/phase-app-1.md)
and expects exactly what was entered there.
"""

from __future__ import annotations

import os

import pytest
from typer.testing import CliRunner

pytest.importorskip("OCC", reason="pythonocc-core is not installed")
pytest.importorskip("win32com", reason="pywin32 is not installed")

from detecttol.cli.main import app
from detecttol.solidworks.reader import read_solidworks
from tests.conftest import EXAMPLES

pytestmark = [
    pytest.mark.solidworks,
    pytest.mark.skipif(
        os.environ.get("DETECTTOL_SOLIDWORKS") != "1",
        reason="set DETECTTOL_SOLIDWORKS=1 on a PC with SOLIDWORKS 2026 to run",
    ),
]

FOLDER = EXAMPLES / "solidworks"


def test_reader_returns_what_was_entered(tmp_path) -> None:  # type: ignore[no-untyped-def]
    r = read_solidworks(
        FOLDER / "Tolerance_Test.SLDASM", tmp_path / "g.step", [FOLDER / "Block_C.SLDDRW"]
    )
    assert r.step_path.is_file()
    assert sorted(r.data.parts) == ["Block_A", "Block_B", "Block_C", "Frame"]
    got = {(d.source, d.part): (d.nominal, d.upper, d.lower) for d in r.data.dimensions}
    assert got == {
        ("dimxpert", "Frame"): (100.0, 0.2, -0.2),
        ("dimxpert", "Block_A"): (25.0, 0.1, -0.1),
        ("dimxpert", "Block_B"): (35.0, 0.05, -0.05),
        ("dimxpert", "Block_C"): (39.0, 0.1, 0.0),
        ("drawing", "Block_C"): pytest.approx((39.0, 0.1, 0.0), abs=1e-12),
    }
    (flat,) = r.data.flatness
    assert (flat.part, flat.value) == ("Block_B", pytest.approx(0.02, abs=1e-12))
    assert flat.face.centroid == pytest.approx((60.0, 2.5, 10.0), abs=1e-5)


def test_analyze_cad_end_to_end() -> None:
    """IS: worst case [0.54, 1.36] (see tests/solidworks/test_resolve.py)."""
    out = CliRunner().invoke(
        app,
        ["analyze-cad", str(FOLDER / "Tolerance_Test.SLDASM"), "-d", str(FOLDER / "Block_C.SLDDRW"),
         "--from", "Block_C:2", "--to", "Frame:4", "--standard", "is", "--samples", "2000"],
    )  # fmt: skip
    assert out.exit_code == 0, out.output
    assert "Range: [0.54, 1.36]" in out.output
    assert "chain Block_C -> Block_B -> Block_A -> Frame" in out.output


FITS = FOLDER / "fits"


def test_diameters_fits_and_positions_are_read(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """examples/solidworks/fits (docs/reports/phase-dia-1.md): fits made through the API
    sit on the display dimension only; position datums / MMC only in the frame text."""
    fit = read_solidworks(FITS / "Fit_Test.SLDASM", tmp_path / "f.step")
    got = {d.part: (d.nominal, d.fit_code, d.fit_from, d.internal) for d in fit.data.diameters}
    assert got == {
        "Housing": (pytest.approx(20.0, abs=1e-9), "H7", "display", True),
        "Shaft": (pytest.approx(20.0, abs=1e-9), "g6", "display", False),
    }
    pin = read_solidworks(FITS / "Pin_Test.SLDASM", tmp_path / "p.step")
    dias = {d.part: (d.upper, d.lower) for d in pin.data.diameters}
    assert dias == {"Plate_1": (0.05, -0.05), "Plate_2": (0.05, -0.05), "Pin": (0.0, -0.02)}
    for pos in pin.data.positions:
        assert (pos.value, pos.datums, pos.found_in) == (
            pytest.approx(0.1, abs=1e-12), ("A", "B", "C"), "frame")  # fmt: skip
    assert sorted((d.part, d.label) for d in pin.data.datums) == sorted(
        (p, label) for p in ("Plate_1", "Plate_2") for label in "ABC")  # fmt: skip


def test_fit_cad_end_to_end() -> None:
    out = CliRunner().invoke(
        app, ["fit-cad", str(FITS / "Fit_Test.SLDASM"), "--hole", "Housing:0", "--shaft", "Shaft:0",
              "--samples", "2000"],
    )  # fmt: skip
    assert out.exit_code == 0, out.output
    assert "fit: clearance fit; clearance from 0.007 to 0.041 mm" in out.output
