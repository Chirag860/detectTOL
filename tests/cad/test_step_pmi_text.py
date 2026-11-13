"""Text-level PMI parser (no pythonocc needed)."""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from detecttol.cad.step_pmi_text import StepTextError, degrees, parse_pmi_text, read_pmi_text
from detecttol.cad.step_text import count_pmi_entities

HEAD = "ISO-10303-21;\nHEADER;\nENDSEC;\nDATA;\n"
TAIL = "ENDSEC;\nEND-ISO-10303-21;\n"

# Units: #1 millimetre, #2 radian, #3 degree (= pi/180 rad), #5 inch (= 25.4 mm).
UNITS = """
#1=(LENGTH_UNIT() NAMED_UNIT(*) SI_UNIT(.MILLI.,.METRE.));
#2=(NAMED_UNIT(*) PLANE_ANGLE_UNIT() SI_UNIT($,.RADIAN.));
#3=(CONVERSION_BASED_UNIT('DEGREE',#4) NAMED_UNIT(#9) PLANE_ANGLE_UNIT());
#4=PLANE_ANGLE_MEASURE_WITH_UNIT(PLANE_ANGLE_MEASURE(0.0174532925199433),#2);
#5=(CONVERSION_BASED_UNIT('INCH',#6) LENGTH_UNIT() NAMED_UNIT(#9));
#6=LENGTH_MEASURE_WITH_UNIT(LENGTH_MEASURE(25.4),#1);
"""

SNIPPET = (
    HEAD
    + UNITS
    + """
#10=DATUM('',$,#90,.F.,'A');
#11=DATUM('',$,#90,.F.,'B');
#12=DATUM('',$,#90,.F.,'C');
#13=DATUM_REFERENCE_COMPARTMENT('',$,#90,.F.,#10,$);
#14=DATUM_REFERENCE_COMPARTMENT('',$,#90,.F.,#11,$);
#15=DATUM_REFERENCE_ELEMENT('',$,#90,.F.,#11,$);
#16=DATUM_REFERENCE_ELEMENT('',$,#90,.F.,#12,$);
#17=DATUM_REFERENCE_COMPARTMENT('',$,#90,.F.,(#15,#16),$);
#18=DATUM_SYSTEM('',$,#90,.F.,(#13,#14));
#19=DATUM_SYSTEM('',$,#90,.F.,(#13,#17));
#20=DATUM_REFERENCE(2,#11);
#21=DATUM_REFERENCE(1,#10);

#30=(LENGTH_MEASURE_WITH_UNIT() MEASURE_REPRESENTATION_ITEM()
MEASURE_WITH_UNIT(LENGTH_MEASURE(0.2),#1) REPRESENTATION_ITEM(''));
#31=LENGTH_MEASURE_WITH_UNIT(LENGTH_MEASURE(0.01),#5);
#32=LENGTH_MEASURE_WITH_UNIT(LENGTH_MEASURE(0.75),#1);

#40=FLATNESS_TOLERANCE('Flatness.1','',#30,#91);
#41=(GEOMETRIC_TOLERANCE('Position.1','',#32,#91)
GEOMETRIC_TOLERANCE_WITH_DATUM_REFERENCE((#18))
GEOMETRIC_TOLERANCE_WITH_MODIFIERS((.MAXIMUM_MATERIAL_REQUIREMENT.))
POSITION_TOLERANCE());
#42=PERPENDICULARITY_TOLERANCE('Perp; with ''quote''','',#31,#91,(#19));
#43=(GEOMETRIC_TOLERANCE('Profile.1','',#30,#91)
GEOMETRIC_TOLERANCE_WITH_DATUM_REFERENCE((#20,#21))
SURFACE_PROFILE_TOLERANCE()
UNEQUALLY_DISPOSED_GEOMETRIC_TOLERANCE(#31));
#44=(GEOMETRIC_TOLERANCE('Position.2','',#32,#91)
MODIFIED_GEOMETRIC_TOLERANCE(.LEAST_MATERIAL_REQUIREMENT.)
POSITION_TOLERANCE());

#50=DIMENSIONAL_SIZE(#91,'diameter');
#51=DIMENSIONAL_LOCATION('linear distance',$,#91,#92);
#52=ANGULAR_LOCATION('angle',$,#91,#92,.EQUAL.);
#53=DIMENSIONAL_SIZE(#91,'curve length');
#54=DIMENSIONAL_SIZE(#91,'diameter');
#55=DIMENSIONAL_LOCATION('linear distance',$,#91,#92);

#60=(LENGTH_MEASURE_WITH_UNIT() MEASURE_REPRESENTATION_ITEM()
MEASURE_WITH_UNIT(LENGTH_MEASURE(35.),#1) REPRESENTATION_ITEM('nominal value'));
#61=LENGTH_MEASURE_WITH_UNIT(LENGTH_MEASURE(-0.2),#1);
#62=LENGTH_MEASURE_WITH_UNIT(LENGTH_MEASURE(0.),#1);
#63=(LENGTH_MEASURE_WITH_UNIT() MEASURE_REPRESENTATION_ITEM()
MEASURE_WITH_UNIT(LENGTH_MEASURE(2.),#5) REPRESENTATION_ITEM('nominal value'));
#64=(LENGTH_MEASURE_WITH_UNIT() MEASURE_REPRESENTATION_ITEM()
MEASURE_WITH_UNIT(LENGTH_MEASURE(2.01),#5) REPRESENTATION_ITEM('upper limit'));
#65=(LENGTH_MEASURE_WITH_UNIT() MEASURE_REPRESENTATION_ITEM()
MEASURE_WITH_UNIT(LENGTH_MEASURE(1.99),#5) REPRESENTATION_ITEM('lower limit'));
#66=(MEASURE_REPRESENTATION_ITEM() MEASURE_WITH_UNIT(PLANE_ANGLE_MEASURE(60.0),#3)
PLANE_ANGLE_MEASURE_WITH_UNIT() REPRESENTATION_ITEM('nominal value'));
#67=PLANE_ANGLE_MEASURE_WITH_UNIT(PLANE_ANGLE_MEASURE(-0.5),#3);
#68=PLANE_ANGLE_MEASURE_WITH_UNIT(PLANE_ANGLE_MEASURE(0.5),#3);
#69=(LENGTH_MEASURE_WITH_UNIT() MEASURE_REPRESENTATION_ITEM()
MEASURE_WITH_UNIT(LENGTH_MEASURE(12.5),#1) REPRESENTATION_ITEM('nominal value'));
#70=DESCRIPTIVE_REPRESENTATION_ITEM('dimension value','35 0/-0.2');

#71=SHAPE_DIMENSION_REPRESENTATION('',(#60,#70),#99);
#72=SHAPE_DIMENSION_REPRESENTATION('',(#63,#64,#65),#99);
#73=SHAPE_DIMENSION_REPRESENTATION('',(#66),#99);
#74=SHAPE_DIMENSION_REPRESENTATION('',(#69),#99);
#75=SHAPE_DIMENSION_REPRESENTATION('',(#69),#99);
#76=DIMENSIONAL_CHARACTERISTIC_REPRESENTATION(#50,#71);
#77=DIMENSIONAL_CHARACTERISTIC_REPRESENTATION(#51,#72);
#78=DIMENSIONAL_CHARACTERISTIC_REPRESENTATION(#52,#73);
#79=DIMENSIONAL_CHARACTERISTIC_REPRESENTATION(#53,#74);
#80=DIMENSIONAL_CHARACTERISTIC_REPRESENTATION(#54,#75);

#81=TOLERANCE_VALUE(#61,#62);
#82=PLUS_MINUS_TOLERANCE(#81,#50);
#83=TOLERANCE_VALUE(#67,#68);
#84=PLUS_MINUS_TOLERANCE(#83,#52);
#85=LIMITS_AND_FITS('H','','7',$);
#86=PLUS_MINUS_TOLERANCE(#85,#54);
/* #87=FLATNESS_TOLERANCE('commented','',#30,#91); */
"""
    + TAIL
)


def test_geometric_tolerances_from_text() -> None:
    """Hand reading of the snippet:

    #40 Flatness.1   0.2 mm, no datum, no modifier
    #41 Position.1   0.75 mm at MMC, datum system #18 -> compartments A, B
    #42 Perpendicularity, 0.01 inch = 0.254 mm, system #19 -> A, then the common
        datum B-C (compartment #17 with two elements); name contains ';' and a quote
    #43 Profile.1    0.2 mm (the 0.01 inch of UNEQUALLY_DISPOSED is the displacement,
        not the magnitude); old-style DATUM_REFERENCE list, ordered by precedence: A, B
    #44 Position.2   0.75 mm at LMC, no datum
    The commented-out #87 is ignored.
    """
    pmi = parse_pmi_text(SNIPPET)
    got = [
        (g.name, g.kind, round(g.value, 9), g.material_modifier, g.datums)
        for g in pmi.geometric_tolerances
    ]
    assert got == [
        ("Flatness.1", "Flatness", 0.2, None, ()),
        ("Position.1", "Position", 0.75, "M", ("A", "B")),
        ("Perp; with 'quote'", "Perpendicularity", 0.254, None, ("A", "B-C")),
        ("Profile.1", "ProfileOfSurface", 0.2, None, ("A", "B")),
        ("Position.2", "Position", 0.75, "L", ()),
    ]
    assert all(g.targets == () for g in pmi.geometric_tolerances)
    assert pmi.datum_names == ("A", "B", "C")


def test_dimensions_from_text() -> None:
    """Hand reading of the snippet:

    #50 diameter 35 mm, TOLERANCE_VALUE(lower -0.2, upper 0) -> +0 / -0.2 (signed)
    #51 linear distance 2 inch = 50.8 mm with limits 2.01 / 1.99 inch
        -> +0.254 / -0.254 mm, form "range"
    #52 angle 60 deg +/-0.5 deg -> 1.047198 rad +/- 0.008726646 rad
    #53 'curve length' 12.5 mm, no tolerance -> kind Size_CurveLength, form "none"
    #54 diameter 12.5 mm with an ISO class (H7) -> form "class", no limits
    #55 has no DIMENSIONAL_CHARACTERISTIC_REPRESENTATION -> not a valued dimension
    """
    pmi = parse_pmi_text(SNIPPET)
    by_kind = [(d.kind, d.unit, d.tolerance_form, d.name) for d in pmi.dimensions]
    assert by_kind == [
        ("Size_Diameter", "mm", "plus_minus", "diameter"),
        ("Location_LinearDistance", "mm", "range", "linear distance"),
        ("Location_Angular", "rad", "plus_minus", "angle"),
        ("Size_CurveLength", "mm", "none", "curve length"),
        ("Size_Diameter", "mm", "class", "diameter"),
    ]
    dia, dist, angle, curve, fit = pmi.dimensions
    assert (dia.value, dia.upper_tol, dia.lower_tol) == (35.0, 0.0, -0.2)
    assert dist.value == pytest.approx(50.8, rel=1e-12)
    assert dist.upper_tol == pytest.approx(0.254, rel=1e-9)
    assert dist.lower_tol == pytest.approx(-0.254, rel=1e-9)
    assert angle.value == pytest.approx(math.pi / 3, rel=1e-12)
    assert angle.upper_tol == pytest.approx(math.radians(0.5), rel=1e-12)
    assert angle.lower_tol == pytest.approx(-math.radians(0.5), rel=1e-12)
    assert degrees(angle.value) == pytest.approx(60.0, rel=1e-12)
    assert (curve.value, curve.upper_tol, curve.lower_tol) == (12.5, None, None)
    assert (fit.value, fit.upper_tol, fit.lower_tol) == (12.5, None, None)


def test_parser_agrees_with_the_independent_counter(tmp_path: Path) -> None:
    """Two separate implementations (tokenising parser vs regular-expression counter)
    must agree on the snippet: 5 tolerances, 5 valued dimensions, 1 MMC, 1 LMC."""
    path = tmp_path / "snippet.stp"
    path.write_text(SNIPPET, encoding="utf-8")
    pmi, counts = read_pmi_text(path), count_pmi_entities(path)
    assert len(pmi.geometric_tolerances) == counts.geometric_tolerances == 5
    assert len(pmi.dimensions) == counts.dimensions_with_value == 5
    assert counts.dimensions == 6
    assert (counts.mmc_modifiers, counts.lmc_modifiers) == (1, 1)
    assert pmi.datum_names == tuple(sorted(set(counts.datum_names)))


def test_metre_and_micrometre_units() -> None:
    """0.0002 m and 200 micrometre are both 0.2 mm."""
    text = (
        HEAD
        + """
#1=(LENGTH_UNIT() NAMED_UNIT(*) SI_UNIT($,.METRE.));
#2=(LENGTH_UNIT() NAMED_UNIT(*) SI_UNIT(.MICRO.,.METRE.));
#3=LENGTH_MEASURE_WITH_UNIT(LENGTH_MEASURE(0.0002),#1);
#4=LENGTH_MEASURE_WITH_UNIT(LENGTH_MEASURE(200.),#2);
#5=FLATNESS_TOLERANCE('a','',#3,#9);
#6=FLATNESS_TOLERANCE('b','',#4,#9);
"""
        + TAIL
    )
    values = [g.value for g in parse_pmi_text(text).geometric_tolerances]
    assert values == pytest.approx([0.2, 0.2], rel=1e-12)


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ("#1=FLATNESS_TOLERANCE('a','',#3,#9);", "unresolved reference #3"),
        (
            "#1=(LENGTH_UNIT() NAMED_UNIT(*) SI_UNIT(.MILLI.,.GRAM.));\n"
            "#3=LENGTH_MEASURE_WITH_UNIT(LENGTH_MEASURE(0.2),#1);\n"
            "#5=FLATNESS_TOLERANCE('a','',#3,#9);",
            "unsupported SI unit",
        ),
        (
            "#1=(CONTEXT_DEPENDENT_UNIT('PARSEC') LENGTH_UNIT() NAMED_UNIT(#8));\n"
            "#3=LENGTH_MEASURE_WITH_UNIT(LENGTH_MEASURE(0.2),#1);\n"
            "#5=FLATNESS_TOLERANCE('a','',#3,#9);",
            "not an SI or conversion-based unit",
        ),
        ("#5=FLATNESS_TOLERANCE('a','');", "unexpected attribute layout"),
        ("#5=FLATNESS_TOLERANCE('a','',#3,#9", "cannot parse"),  # missing ')'
    ],
)
def test_uninterpretable_files_raise(body: str, message: str) -> None:
    with pytest.raises(StepTextError, match=message):
        parse_pmi_text(HEAD + body + ";\n" + TAIL)


def test_file_without_data_section_or_pmi() -> None:
    with pytest.raises(StepTextError, match="no DATA section"):
        parse_pmi_text("ISO-10303-21;\nHEADER;\nENDSEC;\n")
    empty = parse_pmi_text(HEAD + "#1=CARTESIAN_POINT('',(0.,0.,0.));\n" + TAIL)
    assert empty.dimensions == () and empty.geometric_tolerances == () and empty.datum_names == ()
