"""Count PMI entities directly in the text of a STEP (ISO 10303-21) file.

This does not use OCCT. It is an independent cross-check of what the OCCT-based
reader returns, and a diagnostic for files whose PMI the reader cannot handle.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

DIMENSION_ENTITIES = frozenset(
    {
        "DIMENSIONAL_SIZE",
        "DIMENSIONAL_LOCATION",
        "ANGULAR_SIZE",
        "ANGULAR_LOCATION",
        "DIMENSIONAL_SIZE_WITH_PATH",
        "DIMENSIONAL_LOCATION_WITH_PATH",
        "DIRECTED_DIMENSIONAL_LOCATION",
    }
)

_INSTANCE = re.compile(r"\s*#\d+\s*=\s*(.*)", re.S)
_TYPE = re.compile(r"([A-Z][A-Z_0-9]*)\s*\(")
_DATUM_NAME = re.compile(r"DATUM\s*\(.*?,\s*'([^']*)'\s*\)\s*$", re.S)


@dataclass(frozen=True)
class StepTextCounts:
    """PMI entity counts found in the file text.

    Attributes:
        dimensions: instances of a dimensional size/location entity.
        dimensions_with_value: ``DIMENSIONAL_CHARACTERISTIC_REPRESENTATION``
            instances, i.e. dimensions that carry a semantic value. Dimension
            entities without one are reference or presentation-only.
        geometric_tolerances: instances whose type list contains a
            ``*_TOLERANCE`` geometric-tolerance entity.
        geometric_tolerance_types: count per specific tolerance entity name.
        datum_names: identification letters of the ``DATUM`` entities.
        mmc_modifiers / lmc_modifiers: geometric-tolerance instances carrying a
            maximum / least material requirement modifier.
    """

    dimensions: int
    dimensions_with_value: int
    geometric_tolerances: int
    geometric_tolerance_types: dict[str, int]
    datum_names: tuple[str, ...]
    mmc_modifiers: int = 0
    lmc_modifiers: int = 0


def _strip_strings_and_comments(text: str) -> str:
    """Remove ``/* */`` comments; string contents are kept (they hold datum letters)."""
    return re.sub(r"/\*.*?\*/", "", text, flags=re.S)


def count_pmi_entities(path: str | Path) -> StepTextCounts:
    """Count dimension, geometric-tolerance and datum entities in a STEP file.

    An instance is ``#id = TYPE(...);`` or a complex instance
    ``#id = (TYPE_A(...) TYPE_B(...) ...);``; a complex instance is counted
    once. ``PLUS_MINUS_TOLERANCE`` is a dimension tolerance, not a geometric one.
    """
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    _header, _sep, data = text.partition("DATA;")
    data = _strip_strings_and_comments(data)
    dimensions = 0
    with_value = 0
    geomtols = 0
    mmc = 0
    lmc = 0
    types_count: dict[str, int] = {}
    datum_names: list[str] = []
    for statement in data.split(";"):
        match = _INSTANCE.match(statement)
        if not match:
            continue
        body = match.group(1).strip()
        if body.startswith("("):
            types = set(_TYPE.findall(body))
        else:
            head = re.match(r"([A-Z][A-Z_0-9]*)", body)
            types = {head.group(1)} if head else set()
        if types & DIMENSION_ENTITIES:
            dimensions += 1
        if "DIMENSIONAL_CHARACTERISTIC_REPRESENTATION" in types:
            with_value += 1
        specific = {
            t
            for t in types
            if t.endswith("_TOLERANCE") and t not in ("PLUS_MINUS_TOLERANCE", "GEOMETRIC_TOLERANCE")
        }
        if specific or "GEOMETRIC_TOLERANCE" in types:
            geomtols += 1
            if ".MAXIMUM_MATERIAL_REQUIREMENT." in body:
                mmc += 1
            if ".LEAST_MATERIAL_REQUIREMENT." in body:
                lmc += 1
            for t in specific or {"GEOMETRIC_TOLERANCE"}:
                types_count[t] = types_count.get(t, 0) + 1
        if types == {"DATUM"}:
            name = _DATUM_NAME.search(body)
            datum_names.append(name.group(1) if name else "")
    return StepTextCounts(
        dimensions=dimensions,
        dimensions_with_value=with_value,
        geometric_tolerances=geomtols,
        geometric_tolerance_types=dict(sorted(types_count.items())),
        datum_names=tuple(sorted(datum_names)),
        mmc_modifiers=mmc,
        lmc_modifiers=lmc,
    )
