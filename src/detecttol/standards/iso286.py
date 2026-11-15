"""ISO code system for tolerances on linear sizes: IS 919 = ISO 286 (subset).

Supported, and nothing else:

- Standard tolerance grades IT5 to IT18 for basic sizes up to 500 mm.
- Tolerance classes whose limits need only the IT value:

  - ``H`` (hole):  upper deviation ES = +IT, lower EI = 0
  - ``h`` (shaft): upper es = 0, lower ei = -IT
  - ``JS`` / ``js``: +/- IT/2

- With a fundamental deviation (ISO 286-1 Tables 2 and 3):

  - shafts ``c d e f g``: upper deviation es from the table, ei = es - IT;
  - shafts ``k m n p r s``: lower deviation ei from the table, es = ei + IT
    (``k``: the table value for grades 4 to 7, 0 for every other grade);
  - holes ``C D E F G``: EI = -es of the shaft with the same letter (the
    standard's rule for A to H), ES = EI + IT.

  Upper-case letters are holes (internal features), lower-case are shafts.

Holes K to ZC are refused: their deviations need the correction term Delta,
and the only table at hand was inconsistent there (see below). Other letters
(a, b, cd, ef, fg, j, t to zc) are refused too.

The fundamental deviations were extracted by script (not typed) from Roymech,
*ISO Shaft Fundamental Deviations 0 to 500 mm*
(https://www.roymech.co.uk/Useful_Tables/ISO_Tolerances/ISO_SHAFT_LIM_1.html,
retrieved 2026-11-14). Its hole table gave exactly ``EI = -es`` for C to H at
every size step, which checks the extraction, not the source. They are not
checked against ISO 286-1 or IS 919, so they are flagged like the IT values
(docs/ASSUMPTIONS.md A32, A40).

Values of IT5 to IT11 [micrometres] are a transcription of ISO 286-1 Table 1
(= IS 919 (Part 1) Table 1). They could **not** be checked against a clean
copy: the BIS scan's table did not survive OCR. Grades IT12 to IT18 follow from
them by the standard's rule that each fifth grade is ten times larger
(IT12 = 10 IT7, ..., IT17 = 100 IT7, IT18 = 100 IT8), which reproduces Table 1
exactly. Every tolerance taken from here is therefore flagged as not verified
(docs/ASSUMPTIONS.md A32) until a human compares the 91 values with a printed
copy.

Basic size steps follow ISO 286-1: "above a up to and including b"; the first
step is "up to and including 3 mm". IT14 to IT18 are not used for basic sizes
up to and including 1 mm (Table 1, note 3).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: Upper bound (inclusive) of each basic size step up to 500 mm [mm].
SIZE_STEPS: tuple[float, ...] = (
    3.0, 6.0, 10.0, 18.0, 30.0, 50.0, 80.0, 120.0, 180.0, 250.0, 315.0, 400.0, 500.0,
)  # fmt: skip

#: IT5, IT6, IT7, IT8, IT9, IT10, IT11 [um] per size step (same order as SIZE_STEPS).
_IT5_TO_IT11: tuple[tuple[int, ...], ...] = (
    (4, 6, 10, 14, 25, 40, 60),  # up to 3
    (5, 8, 12, 18, 30, 48, 75),  # 3-6
    (6, 9, 15, 22, 36, 58, 90),  # 6-10
    (8, 11, 18, 27, 43, 70, 110),  # 10-18
    (9, 13, 21, 33, 52, 84, 130),  # 18-30
    (11, 16, 25, 39, 62, 100, 160),  # 30-50
    (13, 19, 30, 46, 74, 120, 190),  # 50-80
    (15, 22, 35, 54, 87, 140, 220),  # 80-120
    (18, 25, 40, 63, 100, 160, 250),  # 120-180
    (20, 29, 46, 72, 115, 185, 290),  # 180-250
    (23, 32, 52, 81, 130, 210, 320),  # 250-315
    (25, 36, 57, 89, 140, 230, 360),  # 315-400
    (27, 40, 63, 97, 155, 250, 400),  # 400-500
)


# --------------------------------------------------------------------------- #
# fundamental deviations (ISO 286-1 Tables 2 and 3), a subset
# --------------------------------------------------------------------------- #

#: Upper bound (inclusive) of each size step of the fundamental deviation table [mm].
# fmt: off
DEVIATION_STEPS: tuple[float, ...] = (3.0, 6.0, 10.0, 14.0, 18.0, 24.0, 30.0, 40.0, 50.0, 65.0, 80.0, 100.0, 120.0, 140.0, 160.0, 180.0, 200.0, 225.0, 250.0, 280.0, 315.0, 355.0, 400.0, 450.0, 500.0)

#: Shaft upper deviation es [um] per DEVIATION_STEPS, letters c to g.
_SHAFT_ES_UM: dict[str, tuple[int, ...]] = {
    "c": (-60, -70, -80, -95, -95, -110, -110, -120, -130, -140, -150, -170, -180, -200, -210, -230, -240, -260, -280, -300, -330, -360, -400, -440, -480),
    "d": (-20, -30, -40, -50, -50, -65, -65, -80, -80, -100, -100, -120, -120, -145, -145, -145, -170, -170, -170, -190, -190, -210, -210, -230, -230),
    "e": (-14, -20, -25, -32, -32, -40, -40, -50, -50, -60, -60, -72, -72, -85, -85, -85, -100, -100, -100, -110, -110, -125, -125, -135, -135),
    "f": (-6, -10, -13, -16, -16, -20, -20, -25, -25, -30, -30, -36, -36, -43, -43, -43, -50, -50, -50, -56, -56, -62, -62, -68, -68),
    "g": (-2, -4, -5, -6, -6, -7, -7, -9, -9, -10, -10, -12, -12, -14, -14, -14, -15, -15, -15, -17, -17, -18, -18, -20, -20),
}

#: Shaft lower deviation ei [um] per DEVIATION_STEPS. ``k47`` is k for grades 4 to 7;
#: k of every other grade is 0.
_SHAFT_EI_UM: dict[str, tuple[int, ...]] = {
    "k47": (0, 1, 1, 1, 1, 2, 2, 2, 2, 2, 2, 3, 3, 3, 3, 3, 4, 4, 4, 4, 4, 4, 4, 5, 5),
    "m": (2, 4, 6, 7, 7, 8, 8, 9, 9, 11, 11, 13, 13, 15, 15, 15, 17, 17, 17, 20, 20, 21, 21, 23, 23),
    "n": (4, 8, 10, 12, 12, 15, 15, 17, 17, 20, 20, 23, 23, 27, 27, 27, 31, 31, 31, 34, 34, 37, 37, 40, 40),
    "p": (6, 12, 15, 18, 18, 22, 22, 26, 26, 32, 32, 37, 37, 43, 43, 43, 50, 50, 50, 56, 56, 62, 62, 68, 68),
    "r": (10, 15, 19, 23, 23, 28, 28, 34, 34, 41, 43, 51, 54, 63, 65, 68, 77, 80, 84, 94, 98, 108, 114, 126, 132),
    "s": (14, 19, 23, 28, 28, 35, 35, 43, 43, 53, 59, 71, 79, 92, 100, 108, 122, 130, 140, 158, 170, 190, 208, 232, 252),
}
# fmt: on

MIN_GRADE = 5
MAX_GRADE = 18
#: True while the IT table above has not been compared with a printed copy.
TABLE_VERIFIED = False

_BOUNDARY_TOL = 1e-9
_CLASS_RE = re.compile(r"^([A-Za-z]{1,2})(\d{1,2})$")
_IT_ONLY = ("H", "h", "JS", "js")
_HOLES_FROM_SHAFT_ES = ("C", "D", "E", "F", "G")
_SUPPORTED = (
    *_IT_ONLY,
    *_HOLES_FROM_SHAFT_ES,
    "c",
    "d",
    "e",
    "f",
    "g",
    "k",
    "m",
    "n",
    "p",
    "r",
    "s",
)


class ToleranceClassError(ValueError):
    """A tolerance class is malformed, unsupported or outside the table."""


def step_index(nominal: float) -> int:
    """Index of the basic size step containing ``nominal`` [mm]."""
    if not nominal > 0.0:
        raise ToleranceClassError(f"basic size must be > 0 mm, got {nominal:g}")
    for i, upper in enumerate(SIZE_STEPS):
        if nominal <= upper + _BOUNDARY_TOL:
            return i
    raise ToleranceClassError(
        f"basic size {nominal:g} mm is above 500 mm; only sizes up to 500 mm are supported"
    )


def deviation_step_index(nominal: float) -> int:
    """Index of the size step of the fundamental deviation table containing ``nominal``."""
    step_index(nominal)  # same range checks
    for i, upper in enumerate(DEVIATION_STEPS):
        if nominal <= upper + _BOUNDARY_TOL:
            return i
    raise ToleranceClassError(f"basic size {nominal:g} mm is above 500 mm")  # pragma: no cover


def deviation_step_text(nominal: float) -> str:
    i = deviation_step_index(nominal)
    if i == 0:
        return "up to 3 mm"
    return f"above {DEVIATION_STEPS[i - 1]:g} up to {DEVIATION_STEPS[i]:g} mm"


def fundamental_deviation_um(nominal: float, letter: str, grade: int) -> tuple[str, int]:
    """``("es" | "ei" | "EI", value [um])`` for a letter with a table deviation."""
    i = deviation_step_index(nominal)
    if letter in _SHAFT_ES_UM:
        return "es", _SHAFT_ES_UM[letter][i]
    if letter in _HOLES_FROM_SHAFT_ES:
        return "EI", -_SHAFT_ES_UM[letter.lower()][i]
    if letter == "k":
        return "ei", _SHAFT_EI_UM["k47"][i] if 4 <= grade <= 7 else 0
    if letter in _SHAFT_EI_UM:
        return "ei", _SHAFT_EI_UM[letter][i]
    raise ToleranceClassError(f"no fundamental deviation for '{letter}'")  # pragma: no cover


def step_text(nominal: float) -> str:
    """The basic size step as printed in ISO 286, e.g. ``above 18 up to 30 mm``."""
    i = step_index(nominal)
    if i == 0:
        return "up to 3 mm"
    return f"above {SIZE_STEPS[i - 1]:g} up to {SIZE_STEPS[i]:g} mm"


def it_value_um(nominal: float, grade: int) -> int:
    """Standard tolerance ITn [micrometres] for basic size ``nominal`` [mm].

    IT5-IT11 from the transcribed Table 1; IT12-IT18 as 10x / 100x of IT7-IT11.

    Raises:
        ToleranceClassError: grade outside 5-18, size outside (0, 500] mm, or
            IT14-IT18 for a size up to 1 mm.
    """
    if not MIN_GRADE <= grade <= MAX_GRADE:
        raise ToleranceClassError(
            f"IT{grade} is not supported (supported: IT{MIN_GRADE} to IT{MAX_GRADE})"
        )
    row = _IT5_TO_IT11[step_index(nominal)]
    if grade >= 14 and nominal <= 1.0 + _BOUNDARY_TOL:
        raise ToleranceClassError(
            f"IT{grade} shall not be used for basic sizes up to 1 mm (ISO 286-1 Table 1, note 3)"
        )
    if grade <= 11:
        return row[grade - MIN_GRADE]
    if grade <= 16:
        return 10 * row[grade - 5 - MIN_GRADE]
    return 100 * row[grade - 10 - MIN_GRADE]


@dataclass(frozen=True)
class ClassLimits:
    """Limit deviations of one tolerance class at one basic size.

    Attributes:
        tolerance_class: as written, e.g. ``H7``.
        nominal: basic size [mm].
        upper_tol / lower_tol: signed deviations [mm].
        it_um: the IT value used [micrometres].
        source: one-line description for a report.
        verified: False while the IT table is unverified.
    """

    tolerance_class: str
    nominal: float
    upper_tol: float
    lower_tol: float
    it_um: int
    source: str
    verified: bool


def parse_class(text: str) -> tuple[str, int]:
    """Split ``H7`` into ``("H", 7)``; refuse letters this module cannot compute."""
    match = _CLASS_RE.match(text.strip())
    if match is None:
        raise ToleranceClassError(
            f"'{text}' is not an ISO 286 tolerance class (expected e.g. H7, h6, JS9, js8)"
        )
    letter, grade = match.group(1), int(match.group(2))
    if letter not in _SUPPORTED:
        raise ToleranceClassError(
            f"tolerance class '{text}': fundamental deviation '{letter}' is not available."
            " Supported: holes H, JS, C, D, E, F, G and shafts h, js, c, d, e, f, g, k, m, n,"
            " p, r, s (IS 919 / ISO 286). Give upper_tol / lower_tol from your copy of"
            " IS 919 (Part 2) / ISO 286-2 instead."
        )
    return letter, grade


def class_limits(nominal: float, tolerance_class: str) -> ClassLimits:
    """Limit deviations [mm] of a supported tolerance class (see the module notes).

    Args:
        nominal: basic size [mm], 0 < size <= 500.
        tolerance_class: e.g. ``H7`` (hole) or ``h6`` (shaft).

    Raises:
        ToleranceClassError: see :func:`parse_class` and :func:`it_value_um`.
    """
    letter, grade = parse_class(tolerance_class)
    it_um = it_value_um(nominal, grade)
    kind = "hole" if letter[0].isupper() else "shaft"
    deviation = ""
    if letter == "H":
        upper_um, lower_um = it_um, 0
    elif letter == "h":
        upper_um, lower_um = 0, -it_um
    elif letter in ("JS", "js"):
        upper_um, lower_um = it_um / 2.0, -it_um / 2.0
    else:
        which, value = fundamental_deviation_um(nominal, letter, grade)
        if which == "ei":
            upper_um, lower_um = value + it_um, value
        elif which == "es":
            upper_um, lower_um = value, value - it_um
        else:  # EI of a hole C..G
            upper_um, lower_um = value + it_um, value
        deviation = f", {which} = {value:+d} um ({deviation_step_text(nominal)})"
    upper, lower = round(upper_um / 1000.0, 6), round(lower_um / 1000.0, 6)
    status = "" if TABLE_VERIFIED else "; table not yet verified"
    source = (
        f"IS 919 / ISO 286 {letter}{grade} {kind} ({step_text(nominal)}):"
        f" IT{grade} = {it_um} um{deviation} -> {upper:+g}/{lower:+g}{status}"
    )
    return ClassLimits(
        tolerance_class=f"{letter}{grade}",
        nominal=nominal,
        upper_tol=upper,
        lower_tol=lower,
        it_um=it_um,
        source=source,
        verified=TABLE_VERIFIED,
    )
