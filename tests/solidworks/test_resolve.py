"""SolidWorks read-out -> STEP faces -> stack, with a hand-made read-out (no SolidWorks needed).

The read-out below is what SOLIDWORKS 2026 returned for examples/solidworks
(tools/solidworks_spike/readout_2026-11-14.json), in assembly coordinates:
Frame inner faces x = 0 / 100, Block_A 0..25, Block_B 25..60, Block_C 60..99; every end
face is 20 x 5 = 100 mm^2 with centroid (x, 2.5, 10).
Geometry: examples/solidworks/Tolerance_Test_geometry_AP203_noPMI.step.

Requirement: Block_C +X face (Block_C:2) -> Frame inner face at x = 100 (Frame:4), along +X.
Y = 100 - 25 - 35 - 39 = 1 (nominal).
"""

from __future__ import annotations

import dataclasses
import math

import pytest

pytest.importorskip("OCC", reason="pythonocc-core is not installed")

from detecttol.cad.cad_stack import CadInput, CadStackError, build_cad_stack
from detecttol.cad.pmi import FaceRef
from detecttol.cad.step_reader import read_step
from detecttol.solidworks.model import SwAssemblyData, SwDimension, SwFace, SwFlatness
from detecttol.solidworks.reader import tess_centroid
from detecttol.solidworks.resolve import SolidWorksResolveError, match_face, resolve
from tests.conftest import EXAMPLES

GEOMETRY = EXAMPLES / "solidworks" / "Tolerance_Test_geometry_AP203_noPMI.step"
EXACT = {"rel": 1e-12, "abs": 1e-12}
SEVEN_SF = {"rel": 1e-6}
FROM, TO = FaceRef("Block_C", 2), FaceRef("Frame", 4)


def face(part: str, x: float, nx: float) -> SwFace:
    return SwFace(part=part, normal=(nx, 0.0, 0.0), centroid=(x, 2.5, 10.0), area=100.0)


def width(
    part: str,
    lo: float,
    hi: float,
    upper: float | None,
    lower: float | None,
    fit: str | None = None,
    source: str = "dimxpert",
    inner: bool = False,
) -> SwDimension:
    n = -1.0 if not inner else 1.0
    return SwDimension(
        name=f"Width2@Width1({hi - lo:g})", part=part, source=source, nominal=hi - lo,  # type: ignore[arg-type]
        upper=upper, lower=lower, fit_code=fit,
        faces=(face(part, hi, -n), face(part, lo, n)), document=f"{part}.SLDPRT",
        is_size=source == "dimxpert",
    )  # fmt: skip


def readout(**changes) -> SwAssemblyData:  # type: ignore[no-untyped-def]
    dims = {
        "Frame": width("Frame", 0, 100, 0.2, -0.2, inner=True),
        "Block_A": width("Block_A", 0, 25, 0.1, -0.1),
        "Block_B": width("Block_B", 25, 60, 0.05, -0.05),
        "Block_C": width("Block_C", 60, 99, 0.1, 0.0),
    }
    dims.update(changes)
    return SwAssemblyData(
        assembly="Tolerance_Test.SLDASM",
        parts=("Frame", "Block_A", "Block_B", "Block_C"),
        dimensions=tuple(d for d in dims.values() if d is not None),
        flatness=(SwFlatness("Flatness1@Plane1", "Block_B", 0.02, face("Block_B", 60, 1.0)),),
        solidworks_revision="34.4.1",
    )


@pytest.fixture(scope="module")
def model():  # type: ignore[no-untyped-def]
    return read_step(GEOMETRY)


def build(model, data, **kw):  # type: ignore[no-untyped-def]
    r = resolve(data, model)
    return build_cad_stack(
        CadInput(model, r.dimensions, r.flatness, r.notes, "SolidWorks test"), FROM, TO, **kw
    )


def test_step1_values_under_asme(model) -> None:  # type: ignore[no-untyped-def]
    """Block_C 39 +0.1/-0 has mean 39.05, t 0.05. mean Y = 100 - 25 - 35 - 39.05 = 0.95
    W = 0.2 + 0.1 + 0.05 + 0.05 = 0.4 -> [0.55, 1.35]
    sigma^2 = (0.2/3)^2 + (0.1/3)^2 + (0.05/3)^2 + (0.05/3)^2 = 0.055/9 -> sigma = 0.07817360
    Flatness on Block_B's +X face is inside Block_B's size under ASME: adds nothing."""
    built = build(model, readout(), standard="asme")
    r = built.analyze()
    assert built.chain.path == ("Block_C", "Block_B", "Block_A", "Frame")
    assert r.mean == pytest.approx(0.95, abs=1e-9)
    assert r.worst_case is not None and r.rss is not None
    assert (r.worst_case.lower, r.worst_case.upper) == pytest.approx((0.55, 1.35), abs=1e-9)
    assert r.rss.sigma == pytest.approx(math.sqrt(0.055) / 3, **EXACT)
    assert r.rss.sigma == pytest.approx(0.07817360, **SEVEN_SF)
    cad = next(w for w in r.warnings if w.code == "TOLERANCE_FROM_CAD")
    assert "Block_A:Width2: SolidWorks DimXpert Width2@Width1(25) (Block_A.SLDPRT)" in cad.message


def test_flatness_adds_under_is(model) -> None:  # type: ignore[no-untyped-def]
    """IS (independency): flatness 0.02 adds 0 +/- 0.01.
    W = 0.41 -> [0.54, 1.36]; sigma^2 = 0.055/9 + (0.01/3)^2 = 0.0551/9 -> sigma = 0.07824463"""
    r = build(model, readout(), standard="is").analyze()
    assert r.worst_case is not None and r.rss is not None
    assert (r.worst_case.lower, r.worst_case.upper) == pytest.approx((0.54, 1.36), abs=1e-9)
    assert r.rss.sigma == pytest.approx(math.sqrt(0.0551) / 3, **EXACT)
    assert r.rss.sigma == pytest.approx(0.07824463, **SEVEN_SF)


def test_fit_code_goes_through_iso286(model) -> None:  # type: ignore[no-untyped-def]
    """Block_A 25 h7: IT7 = 21 um (18-30) -> 0/-0.021, mean 24.9895, t 0.0105.
    mean Y = 100 - 24.9895 - 35 - 39.05 = 0.9605; W = 0.2 + 0.0105 + 0.05 + 0.05 = 0.3105"""
    r = build(model, readout(Block_A=width("Block_A", 0, 25, None, None, fit="h7"))).analyze()
    assert r.mean == pytest.approx(0.9605, abs=1e-9)
    assert r.worst_case is not None and r.worst_case.half_range == pytest.approx(0.3105, abs=1e-12)
    assert "TABLE_NOT_VERIFIED" in [w.code for w in r.warnings]


def test_missing_tolerance_uses_the_general_class(model) -> None:  # type: ignore[no-untyped-def]
    """Block_A without a tolerance; IS 2102-m for 25 mm (over 6 up to 30) = +/-0.2.
    W = 0.2 + 0.2 + 0.05 + 0.05 = 0.5"""
    data = readout(Block_A=width("Block_A", 0, 25, None, None))
    r = build(model, data, general_class="m").analyze()
    assert r.worst_case is not None and r.worst_case.half_range == pytest.approx(0.5, abs=1e-12)
    with pytest.raises(CadStackError, match="--general"):
        build(model, data)


def test_drawing_duplicate_is_merged_and_conflict_refused(model) -> None:  # type: ignore[no-untyped-def]
    same = width("Block_C", 60, 99, 0.1, 0.0, source="drawing")
    data = dataclasses.replace(readout(), dimensions=(*readout().dimensions, same))
    resolved = resolve(data, model)
    assert len(resolved.dimensions) == 4 and any("repeats" in n for n in resolved.notes)
    other = width("Block_C", 60, 99, 0.2, 0.0, source="drawing")
    data = dataclasses.replace(readout(), dimensions=(*readout().dimensions, other))
    with pytest.raises(SolidWorksResolveError, match="two different tolerances"):
        resolve(data, model)


def test_face_matching_errors(model) -> None:  # type: ignore[no-untyped-def]
    ref, info = match_face(model, face("Block_C", 99, 1.0))
    assert ref == FaceRef("Block_C", 2) and info.area == pytest.approx(100.0)
    with pytest.raises(SolidWorksResolveError, match="no matching face"):
        match_face(model, face("Block_C", 98, 1.0))
    with pytest.raises(SolidWorksResolveError, match="0 parts of that name"):
        match_face(model, face("Nope", 99, 1.0))
    wrong = dataclasses.replace(width("Block_A", 0, 25, 0.1, -0.1), nominal=24.0)
    with pytest.raises(
        SolidWorksResolveError, match="SolidWorks says 24 mm but the faces are 25 mm"
    ):
        resolve(readout(Block_A=wrong), model)


def test_tessellation_centroid() -> None:
    """Unit square z = 0 as two triangles: centroid (0.5, 0.5, 0), area 1; an L of three
    unit squares (cells (0,0), (1,0), (0,1)): centroid (5/6, 5/6), area 3."""
    sq = [0, 0, 0, 1, 0, 0, 1, 1, 0, 0, 0, 0, 1, 1, 0, 0, 1, 0]
    c, a = tess_centroid([float(v) for v in sq])
    assert c == pytest.approx((0.5, 0.5, 0.0), **EXACT) and a == pytest.approx(1.0, **EXACT)

    def shift(dx: float, dy: float) -> list[float]:
        return [v + (dx if i % 3 == 0 else dy if i % 3 == 1 else 0) for i, v in enumerate(sq)]

    c, a = tess_centroid([float(v) for v in sq + shift(1, 0) + shift(0, 1)])
    assert c == pytest.approx((5 / 6, 5 / 6, 0.0), **EXACT) and a == pytest.approx(3.0, **EXACT)
