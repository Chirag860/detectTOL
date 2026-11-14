"""Drawing standards and tolerance tables (no CAD dependency).

- :data:`STANDARD_LABELS`: which rule set a drawing follows.

  - ``asme``: ASME Y14.5-2018. Rule #1, the envelope principle, is the default:
    the size limits of a regular feature of size also limit its form.
  - ``iso``: ISO GPS. ISO 8015:2011 makes the *independency* principle the
    default: size and form are separate requirements unless the size carries
    the envelope requirement (symbol (E), ISO 14405-1).
  - ``is``: Indian Standards (BIS). The same rules as ``iso``: IS 12160:2015 is
    ISO 8015:2011 and IS 8000 (Part 1):2019 is ISO 1101:2017, both identical
    under dual numbering. Kept separate only so the report names the IS numbers.

- :mod:`detecttol.standards.general`: general tolerances for linear dimensions,
  IS 2102 (Part 1):1993 = ISO 2768-1:1989, classes f / m / c / v.
- :mod:`detecttol.standards.iso286`: ISO code system for tolerances on linear
  sizes, IS 919 = ISO 286. Hole classes H and JS, shaft classes h and js.

See docs/ASSUMPTIONS.md A29-A32 for sources and known weaknesses.
"""

from __future__ import annotations

from detecttol.core.models import DrawingStandard

#: Human-readable name of each drawing standard, as printed in reports.
STANDARD_LABELS: dict[DrawingStandard, str] = {
    "asme": "ASME Y14.5-2018 (envelope principle, Rule #1)",
    "iso": "ISO GPS: ISO 8015:2011 (independency principle)",
    "is": "Indian Standards: IS 12160:2015 = ISO 8015:2011 (independency principle)",
}


def envelope_by_default(standard: DrawingStandard) -> bool:
    """True if size limits also control form unless the drawing says otherwise.

    ASME Y14.5 Rule #1: yes. ISO 8015 / IS 12160 independency: no; only a size
    marked with the envelope requirement (E) controls form.
    """
    return standard == "asme"


def standard_label(standard: DrawingStandard | None) -> str:
    """Report text for a drawing standard; ``None`` means the input did not say."""
    if standard is None:
        return "not stated"
    return STANDARD_LABELS[standard]


__all__ = ["STANDARD_LABELS", "DrawingStandard", "envelope_by_default", "standard_label"]
