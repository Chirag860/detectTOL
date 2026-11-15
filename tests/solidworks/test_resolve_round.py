"""Diameters, fits, datums and positions from a hand-made SolidWorks read-out (no SolidWorks).

The values are what SOLIDWORKS 2026 returned for examples/solidworks/fits
(docs/reports/phase-dia-1.md; tools/solidworks_spike/readout_dia_*.json): cylinder axes
and radii exact, centroids from SolidWorks' tessellation (a little off the axis).
Geometry: the STEP copies SolidWorks wrote, examples/solidworks/fits/*_geometry_AP214.step,
where every full cylinder is two half faces.
"""

from __future__ import annotations

import dataclasses

import pytest

pytest.importorskip("OCC", reason="pythonocc-core is not installed")

from detecttol.cad.cad_stack import CadInput, build_cad_stack, build_fit_check
from detecttol.cad.pmi import FaceRef
from detecttol.cad.step_reader import read_step
from detecttol.solidworks.model import (
    SwAssemblyData,
    SwCylinder,
    SwDatum,
    SwDiameter,
    SwFace,
    SwPosition,
)
from detecttol.solidworks.resolve import SolidWorksResolveError, match_cylinder, resolve
from tests.conftest import EXAMPLES

FITS = EXAMPLES / "solidworks" / "fits"
EXACT = {"rel": 1e-12, "abs": 1e-12}
DOWN = (0.0, 0.0, -1.0)


def cyl(
    part: str, z_top: float, radius: float, cz: float, x: float = 20.0, y: float = 20.0
) -> SwCylinder:
    return SwCylinder(part, (x, y, z_top), DOWN, radius, (x + 0.0007, y, cz))


def sw_dia(
    part: str,
    nominal: float,
    c: SwCylinder,
    *,
    upper: float | None = None,
    lower: float | None = None,
    fit: str | None = None,
    fit_from: str | None = None,
    internal: bool | None = None,
) -> SwDiameter:
    return SwDiameter(
        f"Diameter1@F({nominal:g})",
        part,
        nominal,
        upper,
        lower,
        fit,
        fit_from,
        internal,
        (c,),
        f"{part}.SLDPRT",
    )


def fit_readout() -> SwAssemblyData:
    return SwAssemblyData(
        assembly="Fit_Test.SLDASM",
        parts=("Housing", "Shaft"),
        diameters=(
            sw_dia(
                "Housing",
                20.0,
                cyl("Housing", 20.0, 10.0, 10.0),
                fit="H7",
                fit_from="display",
                internal=True,
            ),
            sw_dia(
                "Shaft",
                20.0,
                cyl("Shaft", 40.0, 10.0, 20.0),
                fit="g6",
                fit_from="display",
                internal=False,
            ),
        ),
    )


def plate(part: str, z0: float) -> tuple[SwDiameter, list[SwDatum], SwPosition]:
    hole = cyl(part, z0 + 10.0, 3.1, z0 + 5.0, 30.0, 10.0)
    datums = [
        SwDatum("Datum10", part, "A", SwFace(part, DOWN, (29.999974, 10.0, z0), 1170.116576)),
        SwDatum(
            "Datum11", part, "B", SwFace(part, (-1.0, 0.0, 0.0), (0.0, 10.0, z0 + 5.0), 199.999991)
        ),
        SwDatum(
            "Datum12",
            part,
            "C",
            SwFace(part, (0.0, -1.0, 0.0), (29.999999, 0.0, z0 + 5.0), 599.999973),
        ),
    ]
    position = SwPosition(
        "Position1@Simple Hole1", part, 0.1, "RFS", ("A", "B", "C"), "frame", (hole,)
    )
    return sw_dia(part, 6.2, hole, upper=0.05, lower=-0.05, internal=True), datums, position


def pin_readout(condition: str = "RFS") -> SwAssemblyData:
    d1, s1, p1 = plate("Plate_1", 0.0)
    d2, s2, p2 = plate("Plate_2", 10.0)
    pin = sw_dia(
        "Pin",
        6.0,
        SwCylinder("Pin", (30.0, 10.0, 20.0), DOWN, 3.0, (30.0, 10.0, 10.0)),
        upper=0.0,
        lower=-0.02,
        internal=False,
    )
    positions = tuple(dataclasses.replace(p, material_condition=condition) for p in (p1, p2))
    return SwAssemblyData(
        assembly="Pin_Test.SLDASM",
        parts=("Plate_1", "Plate_2", "Pin"),
        diameters=(d1, d2, pin),
        datums=(*s1, *s2),
        positions=positions,
    )


def test_fit_codes_from_the_display_become_table_limits() -> None:
    model = read_step(FITS / "Fit_Test_geometry_AP214.step")
    resolved = resolve(fit_readout(), model)
    got = {d.part: (d.upper_tol, d.lower_tol, d.fit_code, d.internal) for d in resolved.diameters}
    assert got == {"Housing": (0.021, 0.0, "H7", True), "Shaft": (-0.007, -0.02, "g6", False)}
    assert all(
        "read from the dimension's display" in (d.cad_source or "") for d in resolved.diameters
    )
    assert all(not d.tolerance_verified for d in resolved.diameters)  # table not yet verified
    by_part = {d.part: d for d in resolved.diameters}
    cad = CadInput(model, (), (), resolved.notes, "test", resolved.diameters)
    check = build_fit_check(
        cad, FaceRef("Housing", by_part["Housing"].face), FaceRef("Shaft", by_part["Shaft"].face)
    )
    assert (check.limits.kind, check.limits.min_clearance, check.limits.max_clearance) == (
        "clearance",
        pytest.approx(0.007, **EXACT),
        pytest.approx(0.041, **EXACT),
    )


def test_pin_test_end_to_end_without_solidworks() -> None:
    """Datum letters (from the frame text) -> faces; chain B1 -> hole -> pin -> hole -> B2;
    worst case +/-0.37 (tests/cad/test_round.py::test_pin_chain_rfs)."""
    model = read_step(FITS / "Pin_Test_geometry_AP214.step")
    resolved = resolve(pin_readout(), model)
    assert len(resolved.positions) == 2
    p1 = next(p for p in resolved.positions if p.part == "Plate_1")
    assert [model.part("Plate_1").faces[r.face_index].normal for r in p1.datums] == [
        (0.0, 0.0, -1.0),
        (-1.0, 0.0, 0.0),
        (0.0, -1.0, 0.0),
    ]
    assert any("tolerance frame's text" in n for n in resolved.notes)
    cad = CadInput(model, (), (), resolved.notes, "test", resolved.diameters, resolved.positions)
    b1 = p1.datums[1]
    b2 = next(p for p in resolved.positions if p.part == "Plate_2").datums[1]
    built = build_cad_stack(cad, b1, b2, lsl=-0.5, usl=0.5, standard="is")
    assert built.chain.path == ("Plate_1", "Pin", "Plate_2")
    result = built.analyze()
    assert (result.worst_case.lower, result.worst_case.upper) == (
        pytest.approx(-0.37, abs=1e-12),
        pytest.approx(0.37, abs=1e-12),
    )


def test_wrong_diameter_or_kind_is_refused() -> None:
    model = read_step(FITS / "Fit_Test_geometry_AP214.step")
    bad = fit_readout()
    housing = dataclasses.replace(bad.diameters[0], nominal=20.5)
    with pytest.raises(SolidWorksResolveError, match=r"dia 20.5 mm but the face is dia 20"):
        resolve(dataclasses.replace(bad, diameters=(housing,)), model)
    boss = dataclasses.replace(bad.diameters[0], internal=False)
    with pytest.raises(
        SolidWorksResolveError, match="calls it a boss but the STEP geometry shows a hole"
    ):
        resolve(dataclasses.replace(bad, diameters=(boss,)), model)


def test_unknown_fit_letter_becomes_missing_with_a_note() -> None:
    model = read_step(FITS / "Fit_Test_geometry_AP214.step")
    bad = fit_readout()
    housing = dataclasses.replace(bad.diameters[0], fit_code="K7")
    resolved = resolve(dataclasses.replace(bad, diameters=(housing,)), model)
    assert resolved.diameters == ()
    assert any("fit K7" in n and "treated as missing" in n for n in resolved.notes)


def test_match_cylinder_needs_the_right_axis() -> None:
    model = read_step(FITS / "Fit_Test_geometry_AP214.step")
    with pytest.raises(SolidWorksResolveError, match="no matching face"):
        match_cylinder(model, cyl("Housing", 20.0, 10.0, 10.0, x=21.0))


def test_fit_letter_must_match_hole_or_shaft() -> None:
    """A hole tagged g6 (a shaft class) would get -0.007/-0.020 instead of G6's
    +0.020/+0.007: refused, treated as missing, with a note."""
    model = read_step(FITS / "Fit_Test_geometry_AP214.step")
    bad = fit_readout()
    housing = dataclasses.replace(bad.diameters[0], fit_code="g6")
    resolved = resolve(dataclasses.replace(bad, diameters=(housing,)), model)
    assert resolved.diameters == ()
    assert any("fit g6 on a hole" in n for n in resolved.notes)
