"""Semantic PMI of the NIST MBE PMI test files (STEP AP242).

Expected values come from two sources that do not involve the OCCT reader:

1. For CTC-01, every dimension and geometric-tolerance value below was read by
   hand from the text of the STEP file (entity ids are given in the docstrings).
2. For all files, the OCCT-free entity counter ``count_pmi_entities``.

NIST publishes drawings of the test cases but no plain "number of PMI items"
table that could be located in Phase R/5, so root.md's "documented counts" are
replaced by these independent counts (see docs/reports/phase-5.md).

Known reader limitations are NOT asserted here (that would freeze a defect into
the suite); they are listed per file in the phase report.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

pytest.importorskip("OCC", reason="pythonocc-core is not installed")

from detecttol.cad.mapping import (
    check_planar_datums,
    dimension_to_contributor,
    geomtol_to_callout,
    geomtol_to_orientation,
    unsupported_items,
)
from detecttol.cad.step_reader import StepModel, read_step
from detecttol.cad.step_text import count_pmi_entities
from detecttol.gdt import Flatness, Position

CTC = {
    1: "nist_ctc_01_asme1_ap242-e1.stp",
    2: "nist_ctc_02_asme1_ap242-e2.stp",
    3: "nist_ctc_03_asme1_ap242-e2.stp",
    4: "nist_ctc_04_asme1_ap242-e1.stp",
    5: "nist_ctc_05_asme1_ap242-e1.stp",
}

#: OCCT geometric-tolerance type name -> STEP entity name.
ENTITY_OF_KIND = {
    "Angularity": "ANGULARITY_TOLERANCE",
    "CircularRunout": "CIRCULAR_RUNOUT_TOLERANCE",
    "CircularityOrRoundness": "ROUNDNESS_TOLERANCE",
    "Concentricity": "CONCENTRICITY_TOLERANCE",
    "Cylindricity": "CYLINDRICITY_TOLERANCE",
    "Flatness": "FLATNESS_TOLERANCE",
    "Parallelism": "PARALLELISM_TOLERANCE",
    "Perpendicularity": "PERPENDICULARITY_TOLERANCE",
    "Position": "POSITION_TOLERANCE",
    "ProfileOfLine": "LINE_PROFILE_TOLERANCE",
    "ProfileOfSurface": "SURFACE_PROFILE_TOLERANCE",
    "Straightness": "STRAIGHTNESS_TOLERANCE",
    "Symmetry": "SYMMETRY_TOLERANCE",
    "TotalRunout": "TOTAL_RUNOUT_TOLERANCE",
}


@pytest.fixture(scope="module")
def models(nist_dir: Path) -> dict[int, StepModel]:
    return {n: read_step(nist_dir / name) for n, name in CTC.items()}


@pytest.fixture(scope="module")
def ctc01(models: dict[int, StepModel]) -> StepModel:
    return models[1]


def test_ctc01_dimensions_match_the_file_text(ctc01: StepModel) -> None:
    """The 8 dimensions that carry a value in nist_ctc_01 (hand-read from the text):

    | entity | kind            | nominal (#)  | lower (#)      | upper (#)     |
    | #33    | angle           | 60 (#30)     | -0.5 (#32)     | +0.5 (#31)    |
    | #120   | diameter        | 35 (#70)     | -0.2 (#72)     | 0 (#71)       |
    | #121   | diameter        | 35 (#73)     | 0 (#75)        | +0.2 (#74)    |
    | #122   | diameter        | 20           | -0.1 (#78)     | +0.05 (#77)   |
    | #123   | diameter        | 20 (#79)     | -0.05 (#81)    | +0.1 (#80)    |
    | #124   | diameter, limits| 35 (#84)     | 34.8 (#86)     | 35.2 (#85)    |
    | #125   | diameter, limits| 35 (#87)     | 34.8 (#89)     | 35.2 (#88)    |
    | #128   | diameter        | 25 (#91)     | -0.15 (#93)    | +0.15 (#92)   |

    The other 4 dimension entities of the file (#24, #25, #126, #127) have no
    DIMENSIONAL_CHARACTERISTIC_REPRESENTATION, i.e. no value.
    """
    got = sorted(
        (
            d.kind,
            d.value,
            round(d.lower_tol or 0.0, 9),
            round(d.upper_tol or 0.0, 9),
            d.tolerance_form,
        )
        for d in ctc01.dimensions
    )
    expected = sorted(
        [
            ("Location_Angular", 60.0, -0.5, 0.5, "plus_minus"),
            ("Size_Diameter", 35.0, -0.2, 0.0, "plus_minus"),
            ("Size_Diameter", 35.0, 0.0, 0.2, "plus_minus"),
            ("Size_Diameter", 20.0, -0.1, 0.05, "plus_minus"),
            ("Size_Diameter", 20.0, -0.05, 0.1, "plus_minus"),
            ("Size_Diameter", 35.0, -0.2, 0.2, "range"),
            ("Size_Diameter", 35.0, -0.2, 0.2, "range"),
            ("Size_Diameter", 25.0, -0.15, 0.15, "plus_minus"),
        ]
    )
    assert len(got) == 8
    for g, e in zip(got, expected, strict=True):
        assert g[0] == e[0] and g[4] == e[4]
        # abs 1e-9: the range limits are computed as 35.2 - 35 (float rounding 3e-15).
        assert g[1:4] == pytest.approx(e[1:4], abs=1e-9)
    assert all(d.targets for d in ctc01.dimensions)


def test_ctc01_geometric_tolerances_match_the_file_text(ctc01: StepModel) -> None:
    """The 6 geometric tolerances of nist_ctc_01 (hand-read from the text):

    | entity | name                         | magnitude (#) | datums  |
    | #21    | Position.1                   | 0.75 (#95)    | A, B, C |
    | #22    | Position.2                   | 0.75 (#96)    | A, B, C |
    | #26    | Position surfacic profile.3  | 1.25 (#90)    | A, B, C |
    | #27    | Position surfacic profile.2  | 0.5 (#94)     | A       |
    | #56    | Perpendicularity.1           | 1.5 (#83)     | A       |
    | #57    | Flatness.1                   | 0.2 (#82)     | none    |

    No tolerance in this file has a material modifier.
    """
    got = {
        g.name: (g.kind, g.value, g.datums, g.material_modifier) for g in ctc01.geometric_tolerances
    }
    assert got == {
        "Position.1": ("Position", 0.75, ("A", "B", "C"), None),
        "Position.2": ("Position", 0.75, ("A", "B", "C"), None),
        "Position surfacic profile.3": ("ProfileOfSurface", 1.25, ("A", "B", "C"), None),
        "Position surfacic profile.2": ("ProfileOfSurface", 0.5, ("A",), None),
        "Perpendicularity.1": ("Perpendicularity", 1.5, ("A",), None),
        "Flatness.1": ("Flatness", 0.2, (), None),
    }
    assert all(g.targets for g in ctc01.geometric_tolerances)
    assert [d.name for d in ctc01.datums] == ["A", "B", "C"]


def test_ctc01_pmi_targets_point_at_real_faces(ctc01: StepModel) -> None:
    """Every target is a face of the model; the flatness and datum A sit on the
    same planar face (the drawing puts datum feature A on the flat face that
    carries the flatness tolerance)."""
    faces = {(p.name, f.index): f for p in ctc01.parts for f in p.faces}
    for item in (*ctc01.dimensions, *ctc01.geometric_tolerances, *ctc01.datums):
        for ref in item.targets:
            assert (ref.part, ref.face_index) in faces
    flatness = next(g for g in ctc01.geometric_tolerances if g.kind == "Flatness")
    datum_a = next(d for d in ctc01.datums if d.name == "A")
    assert len(flatness.targets) == 1 and flatness.targets[0] in datum_a.targets
    assert faces[(flatness.targets[0].part, flatness.targets[0].face_index)].is_planar
    # Diameters point at cylindrical faces.
    for d in ctc01.dimensions:
        if d.kind == "Size_Diameter":
            assert {faces[(r.part, r.face_index)].surface for r in d.targets} == {"cylinder"}


def test_ctc01_maps_onto_the_phase_4_models(ctc01: StepModel) -> None:
    """Mapping of real PMI: hole 35 +0.2/-0 -> contributor (mean 35.1, t 0.1);
    flatness 0.2 -> +/-0.1; position 0.75 RFS with frame A|B|C; perpendicularity
    1.5 over a caller-supplied 30 mm -> atan(1.5/30) = 0.04995840 rad.
    The two surface profiles and the angle are reported as unsupported."""
    hole = next(
        d
        for d in ctc01.dimensions
        if d.value == 35.0 and d.upper_tol == 0.2 and d.tolerance_form == "plus_minus"
    )
    c = dimension_to_contributor(hole, cid="hole_35", sensitivity=1.0)
    assert c.mean == pytest.approx(35.1) and c.half_range == pytest.approx(0.1)

    by_kind = {g.name: g for g in ctc01.geometric_tolerances}
    flat = geomtol_to_callout(by_kind["Flatness.1"], cid="flat")
    assert isinstance(flat, Flatness)
    assert flat.to_contributor().half_range == pytest.approx(0.1)
    pos = geomtol_to_callout(by_kind["Position.1"], cid="pos")
    assert isinstance(pos, Position)
    assert (pos.material_condition, pos.datums.labels()) == ("RFS", ("A", "B", "C"))
    assert pos.to_contributor().sigma == pytest.approx(0.75 / 6)
    perp = geomtol_to_orientation(by_kind["Perpendicularity.1"], cid="perp", feature_length=30.0)
    assert perp.angle_half_range() == pytest.approx(0.04995840, rel=1e-6)
    check_planar_datums(ctc01, by_kind["Perpendicularity.1"])  # datum A is planar

    report = unsupported_items(ctc01)
    assert sum("ProfileOfSurface" in line for line in report) == 2
    assert sum("angular" in line for line in report) == 1
    assert len(report) == 3


@pytest.mark.parametrize("number", sorted(CTC))
def test_reader_never_exceeds_or_contradicts_the_file(
    number: int, models: dict[int, StepModel], nist_dir: Path
) -> None:
    """Invariants against the OCCT-free count, for every CTC file:

    - no geometric tolerance is invented: count and per-type counts are <= the file's;
    - every datum letter exists in the file;
    - every value is a finite positive number, every type is recognised;
    - MMC / LMC modifier counts are <= the file's.
    """
    model = models[number]
    text = count_pmi_entities(nist_dir / CTC[number])
    assert len(model.geometric_tolerances) <= text.geometric_tolerances
    kinds = Counter(g.kind for g in model.geometric_tolerances)
    for kind, count in kinds.items():
        assert kind in ENTITY_OF_KIND, f"unrecognised tolerance type {kind}"
        assert count <= text.geometric_tolerance_types.get(ENTITY_OF_KIND[kind], 0), kind
    assert {d.name for d in model.datums} <= set(text.datum_names)
    for g in model.geometric_tolerances:
        assert g.value == g.value and g.value > 0.0
        assert g.material_modifier in (None, "M", "L")
    modifiers = Counter(g.material_modifier for g in model.geometric_tolerances)
    assert modifiers["M"] <= text.mmc_modifiers and modifiers["L"] <= text.lmc_modifiers
    assert len(model.parts) >= 1 and all(p.faces for p in model.parts)


@pytest.mark.parametrize("number", [1, 2, 5])
def test_geometric_tolerances_are_complete_where_the_reader_copes(
    number: int, models: dict[int, StepModel], nist_dir: Path
) -> None:
    """CTC-01, -02 and -05: the reader returns exactly as many geometric
    tolerances of each type, and exactly the same MMC/LMC modifier counts and
    datum letters, as the file contains. (CTC-03 and -04 each lose one
    tolerance inside OCCT; see the phase report.)"""
    model = models[number]
    text = count_pmi_entities(nist_dir / CTC[number])
    assert len(model.geometric_tolerances) == text.geometric_tolerances
    kinds = Counter(ENTITY_OF_KIND[g.kind] for g in model.geometric_tolerances)
    for entity, count in kinds.items():
        assert count == text.geometric_tolerance_types[entity], entity
    modifiers = Counter(g.material_modifier for g in model.geometric_tolerances)
    assert (modifiers["M"], modifiers["L"]) == (text.mmc_modifiers, text.lmc_modifiers)
    assert sorted(d.name for d in model.datums) == sorted(set(text.datum_names))


def test_ctc02_material_modifiers(models: dict[int, StepModel], nist_dir: Path) -> None:
    """nist_ctc_02 has one tolerance at MMC and three at LMC (counted in the text:
    .MAXIMUM_MATERIAL_REQUIREMENT. x1, .LEAST_MATERIAL_REQUIREMENT. x3)."""
    text = count_pmi_entities(nist_dir / CTC[2])
    assert (text.mmc_modifiers, text.lmc_modifiers) == (1, 3)
    modifiers = Counter(g.material_modifier for g in models[2].geometric_tolerances)
    assert (modifiers["M"], modifiers["L"], modifiers[None]) == (1, 3, 18)
