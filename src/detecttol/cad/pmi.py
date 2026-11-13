"""PMI data classes shared by the STEP readers. No OCCT import here."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FaceRef:
    """A PMI target: face ``face_index`` of the part definition ``part``."""

    part: str
    face_index: int


@dataclass(frozen=True)
class PmiDimension:
    """A semantic dimension.

    Attributes:
        name: annotation name from the file (may be empty).
        kind: dimension type, e.g. ``Size_Diameter``, ``Location_LinearDistance``,
            ``Location_Angular``.
        value: nominal value, in ``unit``.
        upper_tol / lower_tol: signed deviations from ``value`` (``upper >= lower``),
            or ``None`` if the dimension carries no tolerance.
        tolerance_form: ``plus_minus``, ``range``, ``class`` (ISO fit class, not
            converted to limits) or ``none``.
        targets: referenced faces (first group then second group); empty when
            the face link could not be recovered.
        n_first: how many of ``targets`` belong to the first group.
        unit: ``mm`` for lengths, ``rad`` for angular dimensions.
    """

    name: str
    kind: str
    value: float
    upper_tol: float | None
    lower_tol: float | None
    tolerance_form: str
    targets: tuple[FaceRef, ...]
    n_first: int
    unit: str = "mm"


@dataclass(frozen=True)
class PmiGeomTolerance:
    """A semantic geometric tolerance.

    Attributes:
        name: annotation name from the file.
        kind: type name, e.g. ``Flatness``, ``Position``, ``ProfileOfSurface``.
        value: tolerance zone size [mm].
        material_modifier: ``None`` (RFS), ``M`` (MMC) or ``L`` (LMC).
        datums: referenced datum names in precedence order; a common datum is
            written ``A-B``.
        targets: toleranced faces; empty when the face link could not be recovered.
    """

    name: str
    kind: str
    value: float
    material_modifier: str | None
    datums: tuple[str, ...]
    targets: tuple[FaceRef, ...]


@dataclass(frozen=True)
class PmiDatum:
    """A datum: its letter and the faces it is attached to."""

    name: str
    targets: tuple[FaceRef, ...]
