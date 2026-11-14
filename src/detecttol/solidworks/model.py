"""What was read from SolidWorks, as plain records (no COM, no OCCT).

All lengths are millimetres and every face is in **assembly** coordinates: the
reader converts SolidWorks' units (metres for geometry, mm for DimXpert sizes, um
for DimXpert geometric tolerances) and applies each component's transform.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Vec3 = tuple[float, float, float]
DimensionSource = Literal["dimxpert", "drawing"]


@dataclass(frozen=True)
class SwFace:
    """A planar face of one part, in assembly coordinates.

    Attributes:
        part: part name (the part file name without extension).
        normal: outward unit normal.
        centroid: area centroid [mm].
        area: face area [mm^2].
    """

    part: str
    normal: Vec3
    centroid: Vec3
    area: float


@dataclass(frozen=True)
class SwDimension:
    """A toleranced distance between two parallel planar faces of one part.

    Attributes:
        name: SolidWorks name, e.g. ``Width2@Width1(25)`` or ``RD1@Drawing View1``.
        part: part name.
        source: ``dimxpert`` (on the part) or ``drawing`` (in a .SLDDRW).
        nominal: nominal value as SolidWorks reports it [mm].
        upper / lower: signed deviations [mm]; ``None`` when SolidWorks gives no
            usable plus/minus tolerance (then ``fit_code`` or a general
            tolerance must supply one).
        fit_code: ISO fit class such as ``H7`` when the tolerance is a fit.
        faces: the two faces.
        document: file the dimension was read from.
        is_size: a feature of size (DimXpert *Width*); ``False`` for location
            distances and drawing dimensions, whose kind is not known.
    """

    name: str
    part: str
    source: DimensionSource
    nominal: float
    upper: float | None
    lower: float | None
    fit_code: str | None
    faces: tuple[SwFace, SwFace]
    document: str
    is_size: bool = False


@dataclass(frozen=True)
class SwFlatness:
    """A DimXpert flatness on one planar face.

    Attributes:
        name: SolidWorks name.
        part: part name.
        value: zone width [mm].
        face: the toleranced face.
    """

    name: str
    part: str
    value: float
    face: SwFace


@dataclass(frozen=True)
class SwAssemblyData:
    """Everything read from one assembly (and optional drawings).

    Attributes:
        assembly: path of the .SLDASM.
        parts: part names, one per component.
        dimensions / flatness: what was found.
        notes: what was seen but not used, and why (never dropped silently).
        solidworks_revision: e.g. ``34.4.1``.
    """

    assembly: str
    parts: tuple[str, ...]
    dimensions: tuple[SwDimension, ...] = ()
    flatness: tuple[SwFlatness, ...] = ()
    notes: tuple[str, ...] = field(default_factory=tuple)
    solidworks_revision: str = ""
