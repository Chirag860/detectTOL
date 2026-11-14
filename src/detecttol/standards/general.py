"""General tolerances for linear dimensions: IS 2102 (Part 1):1993 = ISO 2768-1:1989.

Table 1 of the standard, "Permissible deviations for linear dimensions except
for broken edges". A dimension without an individual tolerance gets a
symmetric deviation ``+/- d`` that depends on its nominal size and on the
general tolerance class written near the title block (e.g. "IS 2102-m").

Size ranges [mm]: 0.5 up to 3 (incl.), over 3 up to 6, over 6 up to 30,
over 30 up to 120, over 120 up to 400, over 400 up to 1000, over 1000 up to
2000, over 2000 up to 4000. Below 0.5 mm the standard requires the deviation
to be written next to the dimension, so it is refused here; above 4000 mm the
table has no value.

Source of the values: the text layer of the BIS scan of IS 2102 (Part 1):1993
(law.resource.org), compared value by value with ISO 2768-1 as recalled by the
implementer; all 30 values agree. Not yet compared with a printed copy by a
human (docs/ASSUMPTIONS.md A31).
"""

from __future__ import annotations

from typing import Literal

GeneralClass = Literal["f", "m", "c", "v"]

#: Upper bound (inclusive) of each size range [mm]; the first range starts at 0.5.
_UPPER_BOUNDS: tuple[float, ...] = (3.0, 6.0, 30.0, 120.0, 400.0, 1000.0, 2000.0, 4000.0)
_LOWEST_SIZE = 0.5

#: Permissible deviation +/- d [mm] per class and size range; ``None`` = no value.
_TABLE: dict[GeneralClass, tuple[float | None, ...]] = {
    "f": (0.05, 0.05, 0.1, 0.15, 0.2, 0.3, 0.5, None),
    "m": (0.1, 0.1, 0.2, 0.3, 0.5, 0.8, 1.2, 2.0),
    "c": (0.2, 0.3, 0.5, 0.8, 1.2, 2.0, 3.0, 4.0),
    "v": (None, 0.5, 1.0, 1.5, 2.5, 4.0, 6.0, 8.0),
}

_CLASS_NAMES: dict[GeneralClass, str] = {
    "f": "fine",
    "m": "medium",
    "c": "coarse",
    "v": "very coarse",
}

#: Sizes within this distance of a range boundary count as the boundary [mm]
#: (nominals measured on a CAD model are rounded to 1e-9 mm).
_BOUNDARY_TOL = 1e-9


class GeneralToleranceError(ValueError):
    """A general tolerance cannot be looked up for this size and class."""


def _range_index(nominal: float) -> int:
    if nominal < _LOWEST_SIZE - _BOUNDARY_TOL:
        raise GeneralToleranceError(
            f"nominal {nominal:g} mm is below 0.5 mm: IS 2102 / ISO 2768-1 requires the"
            " deviation to be written next to such a dimension; give upper_tol / lower_tol"
        )
    for i, upper in enumerate(_UPPER_BOUNDS):
        if nominal <= upper + _BOUNDARY_TOL:
            return i
    raise GeneralToleranceError(
        f"nominal {nominal:g} mm is above 4000 mm, the end of IS 2102 / ISO 2768-1 Table 1"
    )


def range_text(nominal: float) -> str:
    """The size range a nominal falls in, as printed in the standard."""
    i = _range_index(nominal)
    if i == 0:
        return "0.5 up to 3 mm"
    return f"over {_UPPER_BOUNDS[i - 1]:g} up to {_UPPER_BOUNDS[i]:g} mm"


def general_deviation(nominal: float, tolerance_class: GeneralClass) -> float:
    """Permissible deviation ``d`` [mm] for a linear dimension: tolerance ``+/- d``.

    Args:
        nominal: nominal size [mm], 0.5 to 4000.
        tolerance_class: ``f``, ``m``, ``c`` or ``v``.

    Raises:
        GeneralToleranceError: size outside the table, unknown class, or a cell
            without a value (class f over 2000 mm, class v up to 3 mm).
    """
    if tolerance_class not in _TABLE:
        raise GeneralToleranceError(
            f"unknown general tolerance class '{tolerance_class}' (use f, m, c or v)"
        )
    value = _TABLE[tolerance_class][_range_index(nominal)]
    if value is None:
        raise GeneralToleranceError(
            f"IS 2102 / ISO 2768-1 class {tolerance_class} ({_CLASS_NAMES[tolerance_class]})"
            f" gives no value for {range_text(nominal)}; give upper_tol / lower_tol"
        )
    return value


def describe(nominal: float, tolerance_class: GeneralClass) -> str:
    """Source text for a report, e.g. ``IS 2102-m / ISO 2768-m (over 6 up to 30 mm): +/-0.2``."""
    d = general_deviation(nominal, tolerance_class)
    return (
        f"IS 2102-{tolerance_class} / ISO 2768-{tolerance_class} ({range_text(nominal)}): +/-{d:g}"
    )
