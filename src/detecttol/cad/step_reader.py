"""Read a STEP file (AP203/AP214/AP242): assembly, faces and semantic PMI.

This is the only module family that imports OCCT (``pythonocc-core``).
All lengths are millimetres as delivered by OCCT (which converts the file's
length unit to mm on import); angles of angular dimensions are in the unit
OCCT reports (degrees for the files tested) and are passed through unchanged.

What is read, and how (verified with pythonocc-core 8.0.1.2, see
docs/reports/phase-5.md):

- Assembly tree, part names and placements: ``XCAFDoc_ShapeTool``.
- Faces of every part instance, in ``TopExp_Explorer`` order (the face index),
  with surface type, area, centroid and - for planes - the outward normal.
- Dimensions: ``XCAFDoc_Dimension`` objects (value, +/- tolerance or range).
- Geometric tolerances: the Python class ``XCAFDoc_GeomTolerance`` exposes no
  methods in this binding, so type, value and material modifier are read from
  the attribute's child labels (tags 1, 3 and 4 of the OCCT data layout).
- Datums: ``XCAFDoc_Datum`` objects (name), de-duplicated by name.
- The faces each PMI item points to (``XCAFDoc_DimTolTool.GetRefShapeLabel``).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from OCC.Core import XCAFDimTolObjects
from OCC.Core.BRepAdaptor import BRepAdaptor_Surface
from OCC.Core.BRepGProp import brepgprop
from OCC.Core.GeomAbs import (
    GeomAbs_Cone,
    GeomAbs_Cylinder,
    GeomAbs_Plane,
    GeomAbs_Sphere,
    GeomAbs_Torus,
)
from OCC.Core.GProp import GProp_GProps
from OCC.Core.IFSelect import IFSelect_RetDone
from OCC.Core.STEPCAFControl import STEPCAFControl_Reader
from OCC.Core.TCollection import TCollection_AsciiString
from OCC.Core.TDataStd import TDataStd_Integer, TDataStd_Name, TDataStd_Real
from OCC.Core.TDF import TDF_AttributeIterator, TDF_Label, TDF_LabelSequence
from OCC.Core.TDocStd import TDocStd_Document
from OCC.Core.TopAbs import TopAbs_FACE, TopAbs_REVERSED
from OCC.Core.TopExp import TopExp_Explorer
from OCC.Core.TopLoc import TopLoc_Location
from OCC.Core.TopoDS import topods
from OCC.Core.XCAFDoc import XCAFDoc_Datum, XCAFDoc_Dimension, XCAFDoc_DocumentTool

from detecttol.cad._occt import silence_occt
from detecttol.cad.pmi import FaceRef, PmiDatum, PmiDimension, PmiGeomTolerance
from detecttol.cad.step_pmi_text import StepTextError, TextPmi, read_pmi_text

Vec3 = tuple[float, float, float]

_SURFACE_NAMES = {
    GeomAbs_Plane: "plane",
    GeomAbs_Cylinder: "cylinder",
    GeomAbs_Cone: "cone",
    GeomAbs_Sphere: "sphere",
    GeomAbs_Torus: "torus",
}

# OCCT stores a geometric tolerance object in child labels of its attribute
# label (XCAFDoc_GeomTolerance.cxx): tag 1 = type, 3 = value, 4 = material
# requirement modifier.
_GT_TAG_TYPE = 1
_GT_TAG_VALUE = 3
_GT_TAG_MATERIAL = 4


def _enum_names(prefix: str) -> dict[int, str]:
    out: dict[int, str] = {}
    for name in dir(XCAFDimTolObjects):
        if name.startswith(prefix):
            value = getattr(XCAFDimTolObjects, name)
            if isinstance(value, int):
                out[value] = name[len(prefix) :]
    return out


_DIMENSION_TYPES = _enum_names("XCAFDimTolObjects_DimensionType_")
_GEOMTOL_TYPES = _enum_names("XCAFDimTolObjects_GeomToleranceType_")
_MATERIAL_MODIFIERS = _enum_names("XCAFDimTolObjects_GeomToleranceMatReqModif_")


#: OCCT dimension type of a graphical annotation that carries no semantic value.
PRESENTATION_ONLY = "DimensionPresentation"


class StepReadError(Exception):
    """The STEP file is missing, unreadable or contains no shape."""


@dataclass(frozen=True)
class FaceInfo:
    """One face of a part instance, in assembly (global) coordinates.

    Attributes:
        index: 0-based position in ``TopExp_Explorer`` order within the part.
        surface: ``plane``, ``cylinder``, ``cone``, ``sphere``, ``torus`` or ``other``.
        area: face area [mm^2].
        centroid: area centroid [mm].
        normal: outward unit normal for a plane, else ``None``.
    """

    index: int
    surface: str
    area: float
    centroid: Vec3
    normal: Vec3 | None

    @property
    def is_planar(self) -> bool:
        return self.surface == "plane"


@dataclass(frozen=True)
class PartInstance:
    """A leaf part placed in the assembly.

    Attributes:
        name: name of the part definition (prototype).
        instance_name: name of this occurrence in its parent assembly
            (equals ``name`` for a file with a single free part).
        path: names from the root assembly down to this occurrence.
        translation: translation part of the placement [mm].
        rotation: 3x3 rotation matrix of the placement, row-major.
        faces: all faces of the placed part.
    """

    name: str
    instance_name: str
    path: tuple[str, ...]
    translation: Vec3
    rotation: tuple[Vec3, Vec3, Vec3]
    faces: tuple[FaceInfo, ...]

    def planar_faces(self) -> tuple[FaceInfo, ...]:
        return tuple(f for f in self.faces if f.is_planar)


@dataclass(frozen=True)
class StepModel:
    """Everything read from one STEP file.

    ``n_dimension_labels`` / ``n_datum_labels`` are the raw XCAF label counts.
    OCCT creates extra labels (dimension labels without data, one datum label
    per datum *reference*), so they are larger than the number of PMI items;
    ``dimensions`` holds only labels that carry data and ``datums`` is
    de-duplicated by name.

    ``pmi_source`` is ``text+xcaf`` when the PMI values come from the file text
    (complete, correctly signed, converted to mm / rad) with face links matched
    in from XCAF, or ``xcaf`` when the text could not be interpreted and the
    XCAF values are returned as they are (see ``notes``).
    """

    path: str
    parts: tuple[PartInstance, ...]
    dimensions: tuple[PmiDimension, ...]
    geometric_tolerances: tuple[PmiGeomTolerance, ...]
    datums: tuple[PmiDatum, ...]
    n_dimension_labels: int = 0
    n_datum_labels: int = 0
    notes: tuple[str, ...] = field(default_factory=tuple)
    pmi_source: str = "xcaf"

    def part(self, name: str) -> PartInstance:
        """The unique part instance whose definition or instance name is ``name``."""
        hits = [p for p in self.parts if name in (p.name, p.instance_name)]
        if len(hits) != 1:
            raise KeyError(
                f"part '{name}': expected exactly one match, found {len(hits)}"
                f" (parts: {sorted({p.name for p in self.parts})})"
            )
        return hits[0]


# --------------------------------------------------------------------------- #
# label helpers (TDF_Label.FindAttribute does not fill its argument in this
# binding, so attributes are found by iterating and down-casting by type name)
# --------------------------------------------------------------------------- #


def _attributes(label: TDF_Label) -> list[Any]:
    out = []
    it = TDF_AttributeIterator(label)
    while it.More():
        out.append(it.Value())
        it.Next()
    return out


def _find(label: TDF_Label, cls: Any) -> Any | None:
    wanted = cls.__name__
    for attr in _attributes(label):
        if attr.DynamicType().Name() == wanted:
            return cls.DownCast(attr)
    return None


def _name(label: TDF_Label) -> str:
    attr = _find(label, TDataStd_Name)
    return "" if attr is None else str(TCollection_AsciiString(attr.Get()).ToCString())


def _child_int(label: TDF_Label, tag: int) -> int | None:
    child = label.FindChild(tag, False)
    if child.IsNull():
        return None
    attr = _find(child, TDataStd_Integer)
    return None if attr is None else int(attr.Get())


def _child_real(label: TDF_Label, tag: int) -> float | None:
    child = label.FindChild(tag, False)
    if child.IsNull():
        return None
    attr = _find(child, TDataStd_Real)
    return None if attr is None else float(attr.Get())


def _labels(fill: Any) -> list[TDF_Label]:
    seq = TDF_LabelSequence()
    fill(seq)
    return [seq.Value(i) for i in range(1, seq.Length() + 1)]


# --------------------------------------------------------------------------- #
# geometry
# --------------------------------------------------------------------------- #


def _faces_of(shape: Any) -> list[Any]:
    out = []
    explorer = TopExp_Explorer(shape, TopAbs_FACE)
    while explorer.More():
        out.append(topods.Face(explorer.Current()))
        explorer.Next()
    return out


def _face_info(index: int, face: Any) -> FaceInfo:
    props = GProp_GProps()
    brepgprop.SurfaceProperties(face, props)
    c = props.CentreOfMass()
    adaptor = BRepAdaptor_Surface(face, True)
    surface = _SURFACE_NAMES.get(adaptor.GetType(), "other")
    normal: Vec3 | None = None
    if surface == "plane":
        d = adaptor.Plane().Axis().Direction()
        sign = -1.0 if face.Orientation() == TopAbs_REVERSED else 1.0
        normal = (sign * d.X(), sign * d.Y(), sign * d.Z())
    return FaceInfo(
        index=index,
        surface=surface,
        area=float(props.Mass()),
        centroid=(c.X(), c.Y(), c.Z()),
        normal=normal,
    )


def _placement(location: TopLoc_Location) -> tuple[Vec3, tuple[Vec3, Vec3, Vec3]]:
    trsf = location.Transformation()
    t = trsf.TranslationPart()
    rows = tuple((trsf.Value(r, 1), trsf.Value(r, 2), trsf.Value(r, 3)) for r in (1, 2, 3))
    return (t.X(), t.Y(), t.Z()), (rows[0], rows[1], rows[2])


class _Collector:
    """Walks the XCAF assembly tree and remembers prototype faces for PMI lookup."""

    def __init__(self, shape_tool: Any) -> None:
        self.shape_tool = shape_tool
        self.parts: list[PartInstance] = []
        # (definition label, name, faces of the un-placed definition) for PMI
        # lookup with IsSame; keyed by label because names need not be unique.
        self.prototypes: list[tuple[TDF_Label, str, list[Any]]] = []
        self.n_faceless = 0

    def walk(self, label: TDF_Label, location: TopLoc_Location, path: tuple[str, ...]) -> None:
        tool = self.shape_tool
        instance_name = _name(label)
        definition = label
        if tool.IsReference(label):
            referred = TDF_Label()
            tool.GetReferredShape(label, referred)
            location = location.Multiplied(tool.GetLocation(label))
            definition = referred
        name = _name(definition) or instance_name
        here = (*path, instance_name or name)
        if tool.IsAssembly(definition):
            for child in _labels(lambda s: tool.GetComponents(definition, s, False)):
                self.walk(child, location, here)
            return
        shape = tool.GetShape(definition)
        if shape.IsNull():
            return
        definition_faces = _faces_of(shape)
        if not definition_faces:
            # Wireframe / annotation geometry stored beside the solid: not a part.
            self.n_faceless += 1
            return
        if not any(known.IsEqual(definition) for known, _n, _f in self.prototypes):
            self.prototypes.append((definition, name, definition_faces))
        placed = shape.Moved(location)
        translation, rotation = _placement(location)
        self.parts.append(
            PartInstance(
                name=name,
                instance_name=instance_name or name,
                path=here,
                translation=translation,
                rotation=rotation,
                faces=tuple(_face_info(i, f) for i, f in enumerate(_faces_of(placed))),
            )
        )

    def face_refs(self, labels: list[TDF_Label]) -> tuple[FaceRef, ...]:
        """Map sub-shape labels to (part definition, face index); non-faces are skipped."""
        out: list[FaceRef] = []
        for label in labels:
            shape = self.shape_tool.GetShape(label)
            if shape.IsNull() or shape.ShapeType() != TopAbs_FACE:
                continue
            for _label, part, faces in self.prototypes:
                hit = next((i for i, f in enumerate(faces) if f.IsSame(shape)), None)
                if hit is not None:
                    out.append(FaceRef(part=part, face_index=hit))
                    break
        return tuple(out)


# --------------------------------------------------------------------------- #
# PMI
# --------------------------------------------------------------------------- #


def _targets(
    dimtol: Any, collector: _Collector, label: TDF_Label
) -> tuple[tuple[FaceRef, ...], int]:
    first, second = TDF_LabelSequence(), TDF_LabelSequence()
    dimtol.GetRefShapeLabel(label, first, second)
    a = collector.face_refs([first.Value(i) for i in range(1, first.Length() + 1)])
    b = collector.face_refs([second.Value(i) for i in range(1, second.Length() + 1)])
    return (*a, *b), len(a)


def _read_dimension(dimtol: Any, collector: _Collector, label: TDF_Label) -> PmiDimension | None:
    if not label.HasChild():
        return None  # OCCT placeholder label without any dimension data
    obj = XCAFDoc_Dimension.Set(label).GetObject()
    value = float(obj.GetValue())
    upper: float | None = None
    lower: float | None = None
    if obj.IsDimWithPlusMinusTolerance():
        form = "plus_minus"
        # OCCT returns the lower deviation as a magnitude: a file value of -0.2
        # comes back as 0.2 (checked against the text of NIST CTC-01). The sign
        # is therefore restored here. Limitation: a dimension whose lower
        # deviation is positive in the file (e.g. +0.2/+0.1) cannot be told
        # apart and would be read as +0.2/-0.1.
        upper = float(obj.GetUpperTolValue())
        lower = -abs(float(obj.GetLowerTolValue()))
    elif obj.IsDimWithRange():
        form = "range"
        upper = float(obj.GetUpperBound()) - value
        lower = float(obj.GetLowerBound()) - value
    elif obj.IsDimWithClassOfTolerance():
        form = "class"
    else:
        form = "none"
    targets, n_first = _targets(dimtol, collector, label)
    return PmiDimension(
        name=_name(label),
        kind=_DIMENSION_TYPES.get(int(obj.GetType()), f"type_{int(obj.GetType())}"),
        value=value,
        upper_tol=upper,
        lower_tol=lower,
        tolerance_form=form,
        targets=targets,
        n_first=n_first,
    )


def _datum_name(label: TDF_Label) -> str:
    name = XCAFDoc_Datum.Set(label).GetObject().GetName()
    return "" if name is None else str(name.ToCString())


def _read_geomtol(dimtol: Any, collector: _Collector, label: TDF_Label) -> PmiGeomTolerance:
    type_code = _child_int(label, _GT_TAG_TYPE)
    value = _child_real(label, _GT_TAG_VALUE)
    material_code = _child_int(label, _GT_TAG_MATERIAL)
    material = None
    if material_code is not None:
        material = _MATERIAL_MODIFIERS.get(material_code)
        if material == "None":
            material = None
    datum_labels = TDF_LabelSequence()
    dimtol.GetDatumWithObjectOfTolerLabels(label, datum_labels)
    datums = tuple(_datum_name(datum_labels.Value(i)) for i in range(1, datum_labels.Length() + 1))
    targets, _n = _targets(dimtol, collector, label)
    kind = "unknown" if type_code is None else _GEOMTOL_TYPES.get(type_code, f"type_{type_code}")
    return PmiGeomTolerance(
        name=_name(label),
        kind=kind,
        value=math.nan if value is None else value,
        material_modifier=material,
        datums=datums,
        targets=targets,
    )


def read_step(path: str | Path) -> StepModel:
    """Read a STEP file: parts, faces and semantic PMI.

    Args:
        path: ``.step`` / ``.stp`` file. Lengths are returned in millimetres.

    Raises:
        StepReadError: the file does not exist, cannot be parsed, or holds no shape.
    """
    p = Path(path)
    if not p.is_file():
        raise StepReadError(f"STEP file not found: {p}")
    silence_occt()
    document = TDocStd_Document("detecttol-step")
    reader = STEPCAFControl_Reader()
    reader.SetNameMode(True)
    reader.SetGDTMode(True)
    if reader.ReadFile(str(p)) != IFSelect_RetDone:
        raise StepReadError(f"not a readable STEP file: {p}")
    if not reader.Transfer(document):
        raise StepReadError(f"STEP file could not be transferred: {p}")

    shape_tool = XCAFDoc_DocumentTool.ShapeTool(document.Main())
    dimtol = XCAFDoc_DocumentTool.DimTolTool(document.Main())
    collector = _Collector(shape_tool)
    for free in _labels(shape_tool.GetFreeShapes):
        collector.walk(free, TopLoc_Location(), ())
    if not collector.parts:
        raise StepReadError(f"STEP file contains no shape: {p}")

    dimension_labels = _labels(dimtol.GetDimensionLabels)
    with_data = [
        d for d in (_read_dimension(dimtol, collector, lab) for lab in dimension_labels) if d
    ]
    # "DimensionPresentation" labels are graphical annotations without a value.
    dimensions = [d for d in with_data if d.kind != PRESENTATION_ONLY]
    geomtols = [
        _read_geomtol(dimtol, collector, lab) for lab in _labels(dimtol.GetGeomToleranceLabels)
    ]
    datum_labels = _labels(dimtol.GetDatumLabels)
    datums: dict[str, set[FaceRef]] = {}
    for lab in datum_labels:
        targets, _n = _targets(dimtol, collector, lab)
        datums.setdefault(_datum_name(lab), set()).update(targets)

    notes = []
    if collector.n_faceless:
        notes.append(
            f"{collector.n_faceless} shape(s) without faces (wireframe or annotation"
            " geometry) were skipped"
        )
    names = [name for _l, name, _f in collector.prototypes]
    duplicated = sorted({n for n in names if names.count(n) > 1})
    if duplicated:
        notes.append(
            f"part definitions share the name(s) {duplicated}; PMI face references"
            " to those parts are ambiguous by name"
        )
    if len(dimension_labels) != len(dimensions):
        notes.append(
            f"{len(dimension_labels)} XCAF dimension labels: {len(dimensions)} with a"
            f" value, {len(with_data) - len(dimensions)} presentation-only,"
            f" {len(dimension_labels) - len(with_data)} without data"
        )
    xcaf_datums = {
        n: tuple(sorted(t, key=lambda r: (r.part, r.face_index))) for n, t in datums.items()
    }
    source = "xcaf"
    final_dimensions: list[PmiDimension] = dimensions
    final_geomtols: list[PmiGeomTolerance] = geomtols
    final_datums = [PmiDatum(name=n, targets=t) for n, t in sorted(xcaf_datums.items())]
    try:
        text_pmi: TextPmi | None = read_pmi_text(p)
    except (StepTextError, OSError, RecursionError) as exc:
        text_pmi = None
        notes.append(f"PMI could not be read from the file text ({exc}); XCAF values are used")
    if text_pmi is not None:
        source = "text+xcaf"
        final_geomtols = _merge_geomtols(list(text_pmi.geometric_tolerances), geomtols)
        final_dimensions = _merge_dimensions(list(text_pmi.dimensions), dimensions)
        final_datums = [
            PmiDatum(name=n, targets=xcaf_datums.get(n, ())) for n in text_pmi.datum_names
        ]
        unlinked_gt = sum(1 for g in final_geomtols if not g.targets)
        unlinked_dim = sum(1 for d in final_dimensions if not d.targets)
        unlinked_datum = sum(1 for d in final_datums if not d.targets)
        if unlinked_gt or unlinked_dim or unlinked_datum:
            notes.append(
                f"no face link for {unlinked_gt} of {len(final_geomtols)} geometric tolerances,"
                f" {unlinked_dim} of {len(final_dimensions)} dimensions and {unlinked_datum} of"
                f" {len(final_datums)} datums (OCCT did not transfer them or links them to"
                " non-face geometry)"
            )
    return StepModel(
        path=str(p),
        parts=tuple(collector.parts),
        dimensions=tuple(final_dimensions),
        geometric_tolerances=tuple(final_geomtols),
        datums=tuple(final_datums),
        n_dimension_labels=len(dimension_labels),
        n_datum_labels=len(datum_labels),
        notes=tuple(notes),
        pmi_source=source,
    )


#: Tolerance for "same value" when matching text PMI with XCAF PMI [mm or rad].
_MATCH_TOL = 1e-9


def _close(a: float | None, b: float | None) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return abs(a - b) <= _MATCH_TOL


def _merge_geomtols(
    text: list[PmiGeomTolerance], xcaf: list[PmiGeomTolerance]
) -> list[PmiGeomTolerance]:
    """Text items (authoritative values) with face links taken from XCAF items.

    A text item takes the targets of the first unused XCAF item with the same
    type and value, preferring one with the same name.
    """
    pool = list(xcaf)
    out = []
    for item in text:
        same = [x for x in pool if x.kind == item.kind and _close(x.value, item.value)]
        named = [x for x in same if x.name == item.name]
        hit = (named or same or [None])[0]
        if hit is not None:
            pool.remove(hit)
            item = PmiGeomTolerance(
                name=item.name,
                kind=item.kind,
                value=item.value,
                material_modifier=item.material_modifier,
                datums=item.datums,
                targets=hit.targets,
            )
        out.append(item)
    return out


def _merge_dimensions(text: list[PmiDimension], xcaf: list[PmiDimension]) -> list[PmiDimension]:
    """Text dimensions with face links from XCAF dimensions of the same value.

    XCAF reports angles in degrees and the lower deviation as a magnitude, so
    values are compared in both angle units and tolerances by magnitude.
    """
    pool = list(xcaf)
    out = []
    for item in text:

        def same_value(x: PmiDimension, item: PmiDimension = item) -> bool:
            if _close(x.value, item.value):
                return True
            return item.unit == "rad" and _close(math.radians(x.value), item.value)

        def same_tolerance(x: PmiDimension, item: PmiDimension = item) -> bool:
            if item.upper_tol is None or x.upper_tol is None or x.lower_tol is None:
                return True
            scale = math.pi / 180.0 if item.unit == "rad" else 1.0
            return _close(abs(x.upper_tol) * scale, abs(item.upper_tol)) and _close(
                abs(x.lower_tol) * scale, abs(item.lower_tol or 0.0)
            )

        family = item.kind.split("_")[0]
        candidates = [x for x in pool if x.kind.split("_")[0] == family and same_value(x)]
        exact = [x for x in candidates if x.kind == item.kind and same_tolerance(x)]
        hit = (exact or [x for x in candidates if same_tolerance(x)] or [None])[0]
        if hit is not None:
            pool.remove(hit)
            item = PmiDimension(
                name=item.name,
                kind=item.kind,
                value=item.value,
                upper_tol=item.upper_tol,
                lower_tol=item.lower_tol,
                tolerance_form=item.tolerance_form,
                targets=hit.targets,
                n_first=hit.n_first,
                unit=item.unit,
            )
        out.append(item)
    return out
