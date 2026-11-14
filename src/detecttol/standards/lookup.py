"""One entry point for tolerances written as a class instead of numbers.

``tolerance_class`` in an input file is either

- ``general``: the general tolerance of the document (``general_tolerance:
  f|m|c|v``, IS 2102 (Part 1) = ISO 2768-1), or
- an ISO 286 / IS 919 class such as ``H7``, ``h6``, ``JS9`` or ``js8``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from detecttol.standards import general, iso286

GENERAL_CLASSES = ("f", "m", "c", "v")

#: Keys only the loaders may set on a contributor.
RESERVED_KEYS = ("tolerance_source", "tolerance_verified")


@dataclass(frozen=True)
class LookedUp:
    """Signed deviations [mm] taken from a standard's table, with their source."""

    upper_tol: float
    lower_tol: float
    source: str
    verified: bool


def check_general_class(value: Any) -> general.GeneralClass | None:
    """Validate a document-level ``general_tolerance`` value (``None`` allowed)."""
    if value is None:
        return None
    if value not in GENERAL_CLASSES:
        raise ValueError(f"must be one of f, m, c, v (IS 2102 / ISO 2768-1), got {value!r}")
    result: general.GeneralClass = value
    return result


def look_up(
    nominal: float, tolerance_class: str, general_class: general.GeneralClass | None
) -> LookedUp:
    """Deviations for ``tolerance_class`` at size ``nominal`` [mm].

    Raises:
        ValueError: unknown or unsupported class, size outside the table, or
            ``general`` without a document-level ``general_tolerance``.
    """
    if tolerance_class == "general":
        if general_class is None:
            raise ValueError(
                "tolerance_class 'general' needs general_tolerance: f, m, c or v at the top"
                " of the file (the class from the drawing's IS 2102 / ISO 2768 note)"
            )
        d = general.general_deviation(nominal, general_class)
        return LookedUp(d, -d, general.describe(nominal, general_class), True)
    limits = iso286.class_limits(nominal, tolerance_class)
    return LookedUp(limits.upper_tol, limits.lower_tol, limits.source, limits.verified)


def expand_contributor(
    item: dict[str, Any], general_class: general.GeneralClass | None, nominal_key: str = "nominal"
) -> dict[str, Any]:
    """Copy of an input mapping with ``tolerance_class`` replaced by deviations.

    Raises:
        ValueError: message without a location prefix; the caller adds it.
    """
    for key in RESERVED_KEYS:
        if key in item:
            raise ValueError(f"{key}: set by detectTOL, not in the input file")
    if "tolerance_class" not in item:
        return item
    out = dict(item)
    tolerance_class = out.pop("tolerance_class")
    if not isinstance(tolerance_class, str):
        raise ValueError("tolerance_class: must be a string such as H7, h6 or general")
    if "upper_tol" in out or "lower_tol" in out:
        raise ValueError("tolerance_class: give either tolerance_class or upper_tol / lower_tol")
    nominal = out.get(nominal_key)
    if isinstance(nominal, bool) or not isinstance(nominal, int | float):
        raise ValueError(f"tolerance_class: needs a numeric {nominal_key} (the basic size)")
    if nominal <= 0:
        raise ValueError(f"tolerance_class: the basic size must be > 0 mm, got {nominal:g}")
    try:
        found = look_up(float(nominal), tolerance_class, general_class)
    except ValueError as exc:
        raise ValueError(f"tolerance_class: {exc}") from exc
    out["upper_tol"] = found.upper_tol
    out["lower_tol"] = found.lower_tol
    out["tolerance_source"] = found.source
    out["tolerance_verified"] = found.verified
    return out
