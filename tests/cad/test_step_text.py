"""OCCT-free PMI entity counter. Runs everywhere (no pythonocc needed)."""

from __future__ import annotations

from pathlib import Path

from detecttol.cad.step_text import count_pmi_entities

SNIPPET = """ISO-10303-21;
HEADER;
FILE_NAME('x','',(''),(''),'','','');
ENDSEC;
DATA;
#1=DATUM('',$,#90,.F.,'A');
#2=DATUM('',$,#90,.F.,'B');
#3=DATUM_FEATURE('Simple Datum.1','',#90,.T.);
#4=DATUM_SYSTEM('',$,#90,.F.,(#5));
#10=DIMENSIONAL_SIZE(#91,'diameter');
#11=DIMENSIONAL_LOCATION('linear distance',$,#91,#92);
#12=ANGULAR_LOCATION('angle',$,#91,#92,.EQUAL.);
#13=DIMENSIONAL_CHARACTERISTIC_REPRESENTATION(#10,#50);
#14=DIMENSIONAL_CHARACTERISTIC_REPRESENTATION(#12,#51);
#15=PLUS_MINUS_TOLERANCE(#60,#10);
#20=FLATNESS_TOLERANCE('Flatness.1','',#70,#91);
#21=(
GEOMETRIC_TOLERANCE('Position.1','',#71,#91)
GEOMETRIC_TOLERANCE_WITH_DATUM_REFERENCE((#4))
POSITION_TOLERANCE()
);
#24=(
GEOMETRIC_TOLERANCE('Position.2','',#71,#91)
GEOMETRIC_TOLERANCE_WITH_MODIFIERS((.MAXIMUM_MATERIAL_REQUIREMENT.))
POSITION_TOLERANCE()
);
#25=MODIFIED_GEOMETRIC_TOLERANCE('Position.3','',#71,#91,.LEAST_MATERIAL_REQUIREMENT.);
#22=(
GEOMETRIC_TOLERANCE('Profile.1','',#72,#91)
SURFACE_PROFILE_TOLERANCE()
UNEQUALLY_DISPOSED_GEOMETRIC_TOLERANCE(#73)
);
/* #23=FLATNESS_TOLERANCE('commented out','',#70,#91); */
#30=TOLERANCE_ZONE('',$,#91,.F.,(#20),#31);
ENDSEC;
END-ISO-10303-21;
"""


def test_counts_on_a_hand_written_snippet(tmp_path: Path) -> None:
    """Hand count of the snippet above:

    - dimension entities: #10, #11, #12 -> 3 (PLUS_MINUS_TOLERANCE is not one)
    - dimensions with a value: #13, #14 -> 2
    - geometric tolerances: #20, #21, #22, #24, #25 -> 5 (a complex instance counts
      once; the commented-out #23 and TOLERANCE_ZONE do not count)
    - types: FLATNESS 1, POSITION 2 (#21, #24), MODIFIED_GEOMETRIC 1 (#25),
      SURFACE_PROFILE 1, UNEQUALLY_DISPOSED 1 (the last two are the same instance #22)
    - modifiers: one MMC (#24), one LMC (#25)
    - datums: A, B (DATUM_FEATURE and DATUM_SYSTEM are not datums)
    """
    path = tmp_path / "snippet.stp"
    path.write_text(SNIPPET, encoding="utf-8")
    counts = count_pmi_entities(path)
    assert counts.dimensions == 3
    assert counts.dimensions_with_value == 2
    assert counts.geometric_tolerances == 5
    assert (counts.mmc_modifiers, counts.lmc_modifiers) == (1, 1)
    assert counts.geometric_tolerance_types == {
        "FLATNESS_TOLERANCE": 1,
        "MODIFIED_GEOMETRIC_TOLERANCE": 1,
        "POSITION_TOLERANCE": 2,
        "SURFACE_PROFILE_TOLERANCE": 1,
        "UNEQUALLY_DISPOSED_GEOMETRIC_TOLERANCE": 1,
    }
    assert counts.datum_names == ("A", "B")


def test_file_without_pmi(tmp_path: Path) -> None:
    path = tmp_path / "plain.stp"
    path.write_text("ISO-10303-21;\nDATA;\n#1=CARTESIAN_POINT('',(0.,0.,0.));\nENDSEC;\n", "utf-8")
    counts = count_pmi_entities(path)
    assert (counts.dimensions, counts.dimensions_with_value, counts.geometric_tolerances) == (
        0,
        0,
        0,
    )
    assert counts.datum_names == () and counts.geometric_tolerance_types == {}
