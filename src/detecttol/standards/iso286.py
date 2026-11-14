"""ISO code system for tolerances on linear sizes: IS 919 = ISO 286 (subset).

Supported, and nothing else:

- Standard tolerance grades IT5 to IT18 for basic sizes up to 500 mm.
- Tolerance classes whose limits need only the IT value:

  - ``H`` (hole):  upper deviation ES = +IT, lower EI = 0
  - ``h`` (shaft): upper es = 0, lower ei = -IT
  - ``JS`` / ``js``: +/- IT/2

  Upper-case letters are holes (internal features), lower-case are shafts.

Every other letter (e.g. ``g6``, ``k6``, ``P7``) needs the fundamental
deviation tables (ISO 286-1 Tables 2 and 3). No readable copy was available,
so they are refused with an explanation instead of being guessed.

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

MIN_GRADE = 5
MAX_GRADE = 18
#: True while the IT table above has not been compared with a printed copy.
TABLE_VERIFIED = False

_BOUNDARY_TOL = 1e-9
_CLASS_RE = re.compile(r"^([A-Za-z]{1,2})(\d{1,2})$")
_SUPPORTED = ("H", "h", "JS", "js")


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
            " Only H, h, JS and js are supported: the others need ISO 286-1 Tables 2-3"
            " (IS 919 Part 1), of which no verified copy was available. Give upper_tol /"
            " lower_tol from your copy of IS 919 (Part 2) / ISO 286-2 instead."
        )
    return letter, grade


def class_limits(nominal: float, tolerance_class: str) -> ClassLimits:
    """Limit deviations [mm] of an H, h, JS or js tolerance class.

    Args:
        nominal: basic size [mm], 0 < size <= 500.
        tolerance_class: e.g. ``H7`` (hole) or ``h6`` (shaft).

    Raises:
        ToleranceClassError: see :func:`parse_class` and :func:`it_value_um`.
    """
    letter, grade = parse_class(tolerance_class)
    it_um = it_value_um(nominal, grade)
    it = it_um / 1000.0
    if letter == "H":
        upper, lower = it, 0.0
    elif letter == "h":
        upper, lower = 0.0, -it
    else:
        upper, lower = it / 2.0, -it / 2.0
    kind = "hole" if letter[0].isupper() else "shaft"
    status = "" if TABLE_VERIFIED else "; IT table not yet verified"
    source = (
        f"IS 919 / ISO 286 {letter}{grade} {kind} ({step_text(nominal)}):"
        f" IT{grade} = {it_um} um -> {upper:+g}/{lower:+g}{status}"
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
