"""Read semantic PMI directly from the text of a STEP (ISO 10303-21) file.

No OCCT. This is the authoritative source for PMI *values* in detectTOL:
OCCT's XCAF transfer drops some geometric tolerances and strips the sign of
lower deviations (docs/reports/phase-5.md), while the file text has everything.
What the text cannot give cheaply is the link from a PMI item to OCCT's faces;
that link is taken from XCAF and matched onto these items by the STEP reader.

Read here:

- dimensions that carry a value (``DIMENSIONAL_CHARACTERISTIC_REPRESENTATION``):
  kind, nominal, +/- tolerance (``TOLERANCE_VALUE``, signed), limits
  (``upper limit`` / ``lower limit`` items) or an ISO class (``LIMITS_AND_FITS``);
- geometric tolerances: type, magnitude, MMC/LMC modifier, datum references;
- datums: identification letters.

Units are converted to millimetres and radians using the file's own unit
definitions (SI prefixes and ``CONVERSION_BASED_UNIT`` chains such as INCH or
DEGREE). A unit that cannot be resolved raises :class:`StepTextError`.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from detecttol.cad.pmi import PmiDimension, PmiGeomTolerance


class StepTextError(ValueError):
    """The STEP text could not be interpreted (malformed entity or unknown unit)."""


@dataclass(frozen=True)
class Ref:
    """Reference to another instance (``#123``)."""

    id: int


@dataclass(frozen=True)
class Enum:
    """Enumeration value without the dots (``.METRE.`` -> ``METRE``)."""

    name: str


@dataclass(frozen=True)
class Typed:
    """Typed parameter or (part of) an instance: ``NAME(args)``."""

    name: str
    args: tuple[Any, ...]


@dataclass(frozen=True)
class TextPmi:
    """Semantic PMI found in the file text (targets are always empty here)."""

    dimensions: tuple[PmiDimension, ...]
    geometric_tolerances: tuple[PmiGeomTolerance, ...]
    datum_names: tuple[str, ...]


_STATEMENT_END = re.compile(r"'(?:[^']|'')*'|;")
_INSTANCE = re.compile(r"\s*#(\d+)\s*=\s*", re.S)
_TOKEN = re.compile(
    r"\s*(?:(?P<str>'(?:[^']|'')*')|(?P<ref>#\d+)|(?P<enum>\.[A-Za-z0-9_]+\.)"
    r"|(?P<num>[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)|(?P<name>[A-Za-z_][A-Za-z0-9_]*)"
    r"|(?P<sym>[()$*,]))",
    re.S,
)

_GENERIC_TOLERANCE_TYPES = frozenset(
    {
        "GEOMETRIC_TOLERANCE",
        "MODIFIED_GEOMETRIC_TOLERANCE",
        "UNEQUALLY_DISPOSED_GEOMETRIC_TOLERANCE",
    }
)
#: STEP entity -> type name used throughout detectTOL (same words as OCCT's).
KIND_OF_ENTITY = {
    "ANGULARITY_TOLERANCE": "Angularity",
    "CIRCULAR_RUNOUT_TOLERANCE": "CircularRunout",
    "COAXIALITY_TOLERANCE": "Coaxiality",
    "CONCENTRICITY_TOLERANCE": "Concentricity",
    "CYLINDRICITY_TOLERANCE": "Cylindricity",
    "FLATNESS_TOLERANCE": "Flatness",
    "LINE_PROFILE_TOLERANCE": "ProfileOfLine",
    "PARALLELISM_TOLERANCE": "Parallelism",
    "PERPENDICULARITY_TOLERANCE": "Perpendicularity",
    "POSITION_TOLERANCE": "Position",
    "ROUNDNESS_TOLERANCE": "CircularityOrRoundness",
    "STRAIGHTNESS_TOLERANCE": "Straightness",
    "SURFACE_PROFILE_TOLERANCE": "ProfileOfSurface",
    "SYMMETRY_TOLERANCE": "Symmetry",
    "TOTAL_RUNOUT_TOLERANCE": "TotalRunout",
}
_DIMENSION_BASE = {
    "DIMENSIONAL_SIZE": "Size",
    "DIMENSIONAL_SIZE_WITH_PATH": "Size",
    "DIMENSIONAL_LOCATION": "Location",
    "DIMENSIONAL_LOCATION_WITH_PATH": "Location",
    "DIRECTED_DIMENSIONAL_LOCATION": "Location",
    "ANGULAR_SIZE": "Size_Angular",
    "ANGULAR_LOCATION": "Location_Angular",
}
_SI_PREFIX = {
    None: 1.0,
    "EXA": 1e18,
    "PETA": 1e15,
    "TERA": 1e12,
    "GIGA": 1e9,
    "MEGA": 1e6,
    "KILO": 1e3,
    "HECTO": 1e2,
    "DECA": 1e1,
    "DECI": 1e-1,
    "CENTI": 1e-2,
    "MILLI": 1e-3,
    "MICRO": 1e-6,
    "NANO": 1e-9,
    "PICO": 1e-12,
}


def _parse_args(text: str, pos: int) -> tuple[tuple[Any, ...], int]:
    """Parse a parenthesised argument list starting at ``text[pos] == '('``."""
    assert text[pos] == "("
    pos += 1
    out: list[Any] = []
    while True:
        match = _TOKEN.match(text, pos)
        if not match:
            raise StepTextError(f"cannot parse near: {text[pos : pos + 40]!r}")
        pos = match.end()
        if match.group("str") is not None:
            out.append(match.group("str")[1:-1].replace("''", "'"))
        elif match.group("ref") is not None:
            out.append(Ref(int(match.group("ref")[1:])))
        elif match.group("enum") is not None:
            out.append(Enum(match.group("enum")[1:-1].upper()))
        elif match.group("num") is not None:
            out.append(float(match.group("num")))
        elif match.group("name") is not None:
            name = match.group("name").upper()
            nxt = _TOKEN.match(text, pos)
            if nxt and nxt.group("sym") == "(":
                args, pos = _parse_args(text, nxt.end() - 1)
                out.append(Typed(name, args))
            else:
                out.append(Typed(name, ()))
        else:
            sym = match.group("sym")
            if sym == "(":
                inner, pos = _parse_args(text, pos - 1)
                out.append(inner)
            elif sym == ")":
                return tuple(out), pos
            elif sym in "$*":
                out.append(None)
            # ',' separates arguments: nothing to do


class StepText:
    """Index of the instances of a STEP file, parsed on demand."""

    def __init__(self, text: str) -> None:
        _header, sep, data = text.partition("DATA;")
        if not sep:
            raise StepTextError("no DATA section found")
        data = re.sub(r"/\*.*?\*/", "", data, flags=re.S)
        self._raw: dict[int, str] = {}
        start = 0
        for match in _STATEMENT_END.finditer(data):
            if match.group() != ";":
                continue
            statement = data[start : match.start()]
            start = match.end()
            head = _INSTANCE.match(statement)
            if head:
                self._raw[int(head.group(1))] = statement[head.end() :].strip()
        self._parsed: dict[int, dict[str, tuple[Any, ...]]] = {}

    def ids_containing(self, needle: str) -> list[int]:
        """Ids of instances whose text contains ``needle`` (cheap pre-filter)."""
        return [i for i, body in self._raw.items() if needle in body]

    def has(self, ref: Ref) -> bool:
        """True if the referenced instance exists in the file."""
        return ref.id in self._raw

    def get(self, ref: Ref | int) -> dict[str, tuple[Any, ...]]:
        """Instance as ``{TYPE: args}``; a complex instance has several types."""
        key = ref.id if isinstance(ref, Ref) else ref
        cached = self._parsed.get(key)
        if cached is not None:
            return cached
        body = self._raw.get(key)
        if body is None:
            raise StepTextError(f"unresolved reference #{key}")
        parts: tuple[Any, ...]
        if body.startswith("("):
            parts, _end = _parse_args(body, 0)
        else:
            parts, _end = _parse_args("(" + body + ")", 0)
        record = {p.name: p.args for p in parts if isinstance(p, Typed)}
        self._parsed[key] = record
        return record


def _walk(value: Any) -> Any:
    """Yield every atom of a nested argument structure."""
    if isinstance(value, tuple):
        for item in value:
            yield from _walk(item)
    elif isinstance(value, Typed):
        yield value
        yield from _walk(value.args)
    else:
        yield value


def _strings(args: tuple[Any, ...]) -> list[str]:
    return [a for a in args if isinstance(a, str)]


def _unit_factor(step: StepText, ref: Ref, depth: int = 0) -> float:
    """Factor from the unit ``ref`` to the base unit (metre or radian)."""
    if depth > 8:
        raise StepTextError(f"unit definition #{ref.id} is recursive")
    unit = step.get(ref)
    if "SI_UNIT" in unit:
        prefix, name = (*unit["SI_UNIT"], None, None)[:2]
        prefix_name = prefix.name if isinstance(prefix, Enum) else None
        if not isinstance(name, Enum) or name.name not in ("METRE", "RADIAN"):
            raise StepTextError(f"unit #{ref.id}: unsupported SI unit {name}")
        if prefix_name not in _SI_PREFIX:
            raise StepTextError(f"unit #{ref.id}: unknown SI prefix {prefix_name}")
        return _SI_PREFIX[prefix_name]
    if "CONVERSION_BASED_UNIT" in unit:
        inner = next((a for a in unit["CONVERSION_BASED_UNIT"] if isinstance(a, Ref)), None)
        if inner is None:
            raise StepTextError(f"unit #{ref.id}: conversion factor missing")
        value, factor = _raw_measure(step, inner, depth + 1)
        return value * factor
    raise StepTextError(f"unit #{ref.id}: not an SI or conversion-based unit")


def _raw_measure(step: StepText, ref: Ref, depth: int = 0) -> tuple[float, float]:
    """``(value, factor to base unit)`` of a measure-with-unit instance."""
    record = step.get(ref)
    for args in record.values():
        typed = next(
            (a for a in args if isinstance(a, Typed) and a.name.endswith("_MEASURE") and a.args),
            None,
        )
        unit = next((a for a in args if isinstance(a, Ref)), None)
        if typed is not None and unit is not None and isinstance(typed.args[0], float):
            return typed.args[0], _unit_factor(step, unit, depth)
    raise StepTextError(f"#{ref.id} is not a measure with unit")


def _is_angle(step: StepText, ref: Ref) -> bool:
    return any(
        isinstance(a, Typed) and a.name == "PLANE_ANGLE_MEASURE"
        for args in step.get(ref).values()
        for a in args
    )


def _measure(step: StepText, ref: Ref) -> float:
    """Measure value in millimetres (lengths) or radians (plane angles)."""
    value, factor = _raw_measure(step, ref)
    return value * factor if _is_angle(step, ref) else value * factor * 1000.0


def _datum_label(step: StepText, ref: Ref, depth: int = 0) -> str:
    """Datum letter(s) reached from a datum reference; common datums as ``A-B``."""
    if depth > 6:
        raise StepTextError(f"datum reference #{ref.id} is recursive")
    record = step.get(ref)
    if set(record) == {"DATUM"}:
        strings = _strings(record["DATUM"])
        return strings[-1] if strings else ""
    for key in ("DATUM_REFERENCE_COMPARTMENT", "DATUM_REFERENCE_ELEMENT", "DATUM_REFERENCE"):
        if key in record:
            refs = [a for a in _walk(record[key]) if isinstance(a, Ref)]
            labels = []
            for candidate in refs:
                if not step.has(candidate):
                    continue  # e.g. the owning shape, irrelevant for the label
                target = step.get(candidate)
                if set(target) & {
                    "DATUM",
                    "DATUM_REFERENCE_ELEMENT",
                    "DATUM_REFERENCE_COMPARTMENT",
                }:
                    labels.append(_datum_label(step, candidate, depth + 1))
            return "-".join(x for x in labels if x)
    return ""


def _datums_of(step: StepText, refs: list[Ref]) -> tuple[str, ...]:
    out: list[str] = []
    old_style: list[tuple[float, str]] = []
    for ref in refs:
        record = step.get(ref)
        if "DATUM_SYSTEM" in record:
            lists = [a for a in record["DATUM_SYSTEM"] if isinstance(a, tuple)]
            for constituent in lists[-1] if lists else ():
                if isinstance(constituent, Ref):
                    out.append(_datum_label(step, constituent))
        elif "DATUM_REFERENCE" in record:
            args = record["DATUM_REFERENCE"]
            precedence = next((a for a in args if isinstance(a, float)), 0.0)
            old_style.append((precedence, _datum_label(step, ref)))
        else:
            out.append(_datum_label(step, ref))
    out.extend(label for _p, label in sorted(old_style))
    return tuple(x for x in out if x)


def _geometric_tolerances(step: StepText) -> list[PmiGeomTolerance]:
    found = []
    for key in step.ids_containing("_TOLERANCE"):
        record = step.get(key)
        types = set(record)
        specific = {
            t for t in types if t.endswith("_TOLERANCE") and t != "PLUS_MINUS_TOLERANCE"
        } - _GENERIC_TOLERANCE_TYPES
        if not specific and not (types & _GENERIC_TOLERANCE_TYPES):
            continue
        base = record.get("GEOMETRIC_TOLERANCE") or next(
            (record[t] for t in sorted(types) if t.endswith("_TOLERANCE") and len(record[t]) >= 4),
            None,
        )
        if base is None or len(base) < 4 or not isinstance(base[2], Ref):
            raise StepTextError(f"geometric tolerance #{key}: unexpected attribute layout")
        name = base[0] if isinstance(base[0], str) else ""
        datum_refs: list[Ref] = []
        if "GEOMETRIC_TOLERANCE_WITH_DATUM_REFERENCE" in record:
            datum_refs = [
                a
                for a in _walk(record["GEOMETRIC_TOLERANCE_WITH_DATUM_REFERENCE"])
                if isinstance(a, Ref)
            ]
        else:
            for arg in base[4:]:
                if isinstance(arg, tuple) and arg and all(isinstance(a, Ref) for a in arg):
                    datum_refs = list(arg)
                    break
        enums = {a.name for args in record.values() for a in _walk(args) if isinstance(a, Enum)}
        modifier = None
        if "MAXIMUM_MATERIAL_REQUIREMENT" in enums:
            modifier = "M"
        elif "LEAST_MATERIAL_REQUIREMENT" in enums:
            modifier = "L"
        entity = sorted(specific)[0] if specific else "GEOMETRIC_TOLERANCE"
        found.append(
            (
                key,
                PmiGeomTolerance(
                    name=name,
                    kind=KIND_OF_ENTITY.get(entity, entity),
                    value=_measure(step, base[2]),
                    material_modifier=modifier,
                    datums=_datums_of(step, datum_refs),
                    targets=(),
                ),
            )
        )
    return [item for _key, item in sorted(found, key=lambda pair: pair[0])]


def _camel(name: str) -> str:
    return "".join(word.capitalize() for word in re.split(r"[^A-Za-z0-9]+", name) if word)


def _dimension_kind(record: dict[str, tuple[Any, ...]]) -> str:
    for entity, base in _DIMENSION_BASE.items():
        if entity in record:
            if base.endswith("Angular"):
                return base
            strings = _strings(record[entity])
            return f"{base}_{_camel(strings[0])}" if strings else base
    return "Unknown"


def _item_name(record: dict[str, tuple[Any, ...]]) -> str:
    if "REPRESENTATION_ITEM" in record:
        strings = _strings(record["REPRESENTATION_ITEM"])
        return strings[0].lower() if strings else ""
    for args in record.values():
        strings = _strings(args)
        if strings:
            return strings[0].lower()
    return ""


def _dimensions(step: StepText) -> list[PmiDimension]:
    tolerance_of: dict[int, Ref] = {}
    for key in step.ids_containing("PLUS_MINUS_TOLERANCE"):
        args = step.get(key).get("PLUS_MINUS_TOLERANCE")
        if args and len(args) >= 2 and isinstance(args[0], Ref) and isinstance(args[1], Ref):
            tolerance_of[args[1].id] = args[0]

    found = []
    for key in step.ids_containing("DIMENSIONAL_CHARACTERISTIC_REPRESENTATION"):
        args = step.get(key).get("DIMENSIONAL_CHARACTERISTIC_REPRESENTATION")
        if not args or not isinstance(args[0], Ref) or not isinstance(args[1], Ref):
            continue
        dimension_ref, representation_ref = args[0], args[1]
        dimension = step.get(dimension_ref)
        kind = _dimension_kind(dimension)
        representation = step.get(representation_ref)
        items = next((a for a in next(iter(representation.values())) if isinstance(a, tuple)), ())
        values: dict[str, float] = {}
        unnamed: list[float] = []
        for item in items:
            if not isinstance(item, Ref):
                continue
            try:
                value = _measure(step, item)
            except StepTextError:
                continue  # descriptive item (text), not a measure
            label = _item_name(step.get(item))
            if label in ("nominal value", "upper limit", "lower limit"):
                values[label] = value
            else:
                unnamed.append(value)
        nominal = values.get("nominal value", unnamed[0] if unnamed else None)
        if nominal is None:
            continue
        upper: float | None = None
        lower: float | None = None
        form = "none"
        tolerance_ref = tolerance_of.get(dimension_ref.id)
        if tolerance_ref is not None:
            tolerance = step.get(tolerance_ref)
            if "TOLERANCE_VALUE" in tolerance:
                bounds = [a for a in tolerance["TOLERANCE_VALUE"] if isinstance(a, Ref)]
                lower, upper = _measure(step, bounds[0]), _measure(step, bounds[1])
                form = "plus_minus"
            elif "LIMITS_AND_FITS" in tolerance:
                form = "class"
        if form == "none" and "upper limit" in values and "lower limit" in values:
            upper = values["upper limit"] - nominal
            lower = values["lower limit"] - nominal
            form = "range"
        name_strings = [
            s
            for entity in _DIMENSION_BASE
            if entity in dimension
            for s in _strings(dimension[entity])
        ]
        found.append(
            (
                dimension_ref.id,
                PmiDimension(
                    name=name_strings[0] if name_strings else "",
                    kind=kind,
                    value=nominal,
                    upper_tol=upper,
                    lower_tol=lower,
                    tolerance_form=form,
                    targets=(),
                    n_first=0,
                    unit="rad" if kind.endswith("Angular") else "mm",
                ),
            )
        )
    return [item for _key, item in sorted(found, key=lambda pair: pair[0])]


def parse_pmi_text(text: str) -> TextPmi:
    """Semantic PMI of a STEP file given as text.

    Raises:
        StepTextError: malformed instance, unresolved reference or unknown unit.
    """
    step = StepText(text)
    datum_names = []
    for key in step.ids_containing("DATUM"):
        record = step.get(key)
        if set(record) == {"DATUM"}:
            strings = _strings(record["DATUM"])
            datum_names.append(strings[-1] if strings else "")
    return TextPmi(
        dimensions=tuple(_dimensions(step)),
        geometric_tolerances=tuple(_geometric_tolerances(step)),
        datum_names=tuple(sorted(set(datum_names))),
    )


def read_pmi_text(path: str | Path) -> TextPmi:
    """Semantic PMI of a STEP file, read from its text (lengths mm, angles rad).

    Raises:
        StepTextError: the file cannot be interpreted.
        OSError: the file cannot be read.
    """
    return parse_pmi_text(Path(path).read_text(encoding="utf-8", errors="replace"))


def degrees(value: float) -> float:
    """Radians -> degrees (helper for display)."""
    return value * 180.0 / math.pi
