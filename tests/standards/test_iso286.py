"""ISO 286 / IS 919 subset: IT grades and H / h / JS / js limits.

Hand derivations use the formulae of IS 919 (Part 1):1993 = ISO 286-1:1988,
annex A, which were readable in the BIS scan:

- standard tolerance factor  i = 0.45 * D^(1/3) + 0.001 * D  [um], D = geometric
  mean of the size step [mm] (A.3.2.2); for the first step D = sqrt(1*3) (A.2);
- Table 7: IT5..IT11 = 7i, 10i, 16i, 25i, 40i, 64i, 100i;
- Table 8 (sizes up to 500 mm): round to multiples of 1 up to 100 um, of 5
  above 100 up to 200, of 10 above 200 up to 500;
- IT12 and above: ten times the grade five steps finer (A.3.2.2, A.3.4).

The standard warns that Table 1 sometimes departs from these formulae and that
Table 1 governs. The rows 18-30 and 80-120 are ones where formula and table agree,
so their values can be derived here by hand; the table itself still awaits a
check against a printed copy (TABLE_VERIFIED is False).
"""

from __future__ import annotations

import math

import pytest

from detecttol.standards import iso286
from detecttol.standards.iso286 import ToleranceClassError, class_limits, it_value_um

EXACT = {"rel": 1e-12, "abs": 1e-15}


def _formula_um(lo: float, hi: float, grade: int) -> int:
    """Annex A derivation for IT5..IT11 (see module docstring)."""
    d = math.sqrt(3.0) if lo == 0 else math.sqrt(lo * hi)
    i = 0.45 * d ** (1 / 3) + 0.001 * d
    value = {5: 7, 6: 10, 7: 16, 8: 25, 9: 40, 10: 64, 11: 100}[grade] * i
    step = 1 if value <= 100 else 5 if value <= 200 else 10
    return round(value / step) * step


def test_it_grades_18_to_30_from_the_annex_formulae() -> None:
    """Basic size step above 18 up to 30 mm.

    D = sqrt(18*30) = 23.23790; D^(1/3) = 2.853715; i = 0.45*2.853715 + 0.0232379
      = 1.307411 um
    IT5 = 7i = 9.152 -> 9      IT6 = 10i = 13.07 -> 13     IT7 = 16i = 20.92 -> 21
    IT8 = 25i = 32.69 -> 33    IT9 = 40i = 52.30 -> 52     IT10 = 64i = 83.67 -> 84
    IT11 = 100i = 130.74 -> (multiple of 5) 130
    IT12..IT16 = 10 x IT7..IT11 = 210, 330, 520, 840, 1300; IT17 = 2100, IT18 = 3300
    """
    expected = {5: 9, 6: 13, 7: 21, 8: 33, 9: 52, 10: 84, 11: 130,
                12: 210, 13: 330, 14: 520, 15: 840, 16: 1300, 17: 2100, 18: 3300}  # fmt: skip
    for grade, value in expected.items():
        assert it_value_um(25.0, grade) == value, grade
    for grade in range(5, 12):
        assert _formula_um(18, 30, grade) == expected[grade]


def test_it_grades_80_to_120_from_the_annex_formulae() -> None:
    """Basic size step above 80 up to 120 mm.

    D = sqrt(80*120) = 97.97959; D^(1/3) = 4.610116; i = 2.074552 + 0.0979796 = 2.172532
    IT5 = 15.21 -> 15   IT6 = 21.73 -> 22   IT7 = 34.76 -> 35   IT8 = 54.31 -> 54
    IT9 = 86.90 -> 87   IT10 = 139.04 -> (x5) 140   IT11 = 217.25 -> (x10) 220
    (corrected 2026-11-13 after the reviewer's re-derivation; rounded values unchanged)
    """
    expected = {5: 15, 6: 22, 7: 35, 8: 54, 9: 87, 10: 140, 11: 220}
    for grade, value in expected.items():
        assert it_value_um(100.0, grade) == value
        assert _formula_um(80, 120, grade) == value


def test_transcribed_departures_from_the_formulae_are_the_documented_ones() -> None:
    """Table 1 departs from the annex formulae in places (its note 1 says so).

    This pins the 20 cells of the transcription where it does, so that an edit
    of the table is noticed. It does not prove the transcription right; that
    needs a printed copy (docs/ASSUMPTIONS.md A32).
    """
    departures = []
    for index, hi in enumerate(iso286.SIZE_STEPS):
        lo = 0.0 if index == 0 else iso286.SIZE_STEPS[index - 1]
        mid = hi if index == 0 else (lo + hi) / 2
        for grade in range(5, 12):
            if it_value_um(mid, grade) != _formula_um(lo, hi, grade):
                departures.append((hi, grade))
    assert departures == [
        (3.0, 6), (3.0, 7), (3.0, 9), (3.0, 10), (3.0, 11),
        (6.0, 6), (6.0, 9), (6.0, 10), (6.0, 11),
        (10.0, 7), (10.0, 10),
        (18.0, 7), (18.0, 10),
        (50.0, 11), (80.0, 11),
        (400.0, 6), (400.0, 11),
        (500.0, 6), (500.0, 7), (500.0, 11),
    ]  # fmt: skip
    assert iso286.TABLE_VERIFIED is False


def test_h_h_js_limits_at_25_mm() -> None:
    """IT7 = 21 um, IT6 = 13 um, IT8 = 33 um at 25 mm (derived above).

    H7: ES = +0.021, EI = 0          h6: es = 0, ei = -0.013
    JS7: +/- 0.0105                  js8: +/- 0.0165
    """
    h7 = class_limits(25.0, "H7")
    assert (h7.upper_tol, h7.lower_tol) == pytest.approx((0.021, 0.0), **EXACT)
    assert "hole" in h7.source and "above 18 up to 30 mm" in h7.source
    assert h7.verified is False
    h6 = class_limits(25.0, "h6")
    assert (h6.upper_tol, h6.lower_tol) == pytest.approx((0.0, -0.013), **EXACT)
    assert "shaft" in h6.source
    js7 = class_limits(25.0, "JS7")
    assert (js7.upper_tol, js7.lower_tol) == pytest.approx((0.0105, -0.0105), **EXACT)
    js8 = class_limits(25.0, "js8")
    assert (js8.upper_tol, js8.lower_tol) == pytest.approx((0.0165, -0.0165), **EXACT)


def test_size_step_boundaries_are_up_to_and_including() -> None:
    """ISO 286 steps are "above a up to and including b".

    30 belongs to 18-30 (IT7 = 21); 30.001 to 30-50 (IT7 = 25 in the table).
    3 belongs to the first step (IT7 = 10); 500 is the last supported size.
    """
    assert it_value_um(30.0, 7) == 21
    assert it_value_um(30.001, 7) == 25
    assert it_value_um(3.0, 7) == 10
    assert it_value_um(500.0, 7) == 63
    assert iso286.step_text(30.0) == "above 18 up to 30 mm"
    assert iso286.step_text(2.0) == "up to 3 mm"


@pytest.mark.parametrize(
    ("size", "cls", "message"),
    [
        (25.0, "g6", "fundamental deviation 'g' is not available"),
        (25.0, "P7", "fundamental deviation 'P' is not available"),
        (25.0, "H", "not an ISO 286 tolerance class"),
        (25.0, "7H", "not an ISO 286 tolerance class"),
        (25.0, "H4", "IT4 is not supported"),
        (25.0, "H19", "IT19 is not supported"),
        (500.5, "H7", "above 500 mm"),
        (0.0, "H7", "must be > 0"),
        (1.0, "H14", "shall not be used for basic sizes up to 1 mm"),
    ],
)
def test_refused_classes(size: float, cls: str, message: str) -> None:
    with pytest.raises(ToleranceClassError, match=message):
        class_limits(size, cls)


def test_it14_is_allowed_just_above_1_mm() -> None:
    """IT14 = 10 x IT9 = 250 um in the first step (table IT9 = 25)."""
    assert it_value_um(1.5, 14) == 250
