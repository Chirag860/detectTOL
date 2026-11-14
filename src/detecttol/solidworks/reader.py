"""Read an assembly's tolerances through a locally installed SolidWorks (COM).

Needs Windows, a licensed SolidWorks and ``pywin32`` (``conda install pywin32``).
Tested with SOLIDWORKS 2026 (revision 34.4). The files are opened **read-only**
and never saved; documents that were already open stay open; SolidWorks is shut
down again only if this module started it. The one global setting touched (the
STEP application protocol, for the geometry copy) is restored afterwards.

Units as SolidWorks reports them (docs/reports/phase-app-1.md): geometry in
metres, DimXpert sizes and their tolerances in millimetres, DimXpert geometric
tolerance values in micrometres, drawing dimensions in metres.
"""

from __future__ import annotations

import contextlib
import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from detecttol.solidworks.model import SwAssemblyData, SwDimension, SwFace, SwFlatness, Vec3

M_TO_MM = 1000.0
UM_TO_MM = 0.001

_SLDWORKS_TLB = ("{83A33D31-27C5-11CE-BFD4-00400513BB57}", 0, 34, 0)
_DIMXPERT_TLB = ("{582D0D5B-FF58-42CD-8968-A8A001A52454}", 0, 34, 0)

DOC_PART, DOC_ASSEMBLY, DOC_DRAWING = 1, 2, 3
OPEN_SILENT_READONLY = 1 | 2
SAVEAS_SILENT_COPY = 1 | 2
PREF_STEP_AP = 75
ANNOT_DISTANCE_BETWEEN, ANNOT_WIDTH, ANNOT_FLATNESS = 101, 112, 215
DX_TOL_ISO_FITS = (3, 4)
TOL_NONE, TOL_BILAT, TOL_SYMMETRIC = 0, 2, 4


class SolidWorksError(RuntimeError):
    """SolidWorks is not available, a file does not open, or a call fails."""


@dataclass(frozen=True)
class SolidWorksReadout:
    """Result of :func:`read_solidworks`."""

    data: SwAssemblyData
    step_path: Path


class _Com:
    """Typed COM wrappers, generated on first use from SolidWorks' type libraries."""

    def __init__(self) -> None:
        try:
            import win32com.client
            from win32com.client import gencache
        except ImportError as exc:  # pragma: no cover - depends on the machine
            raise SolidWorksError(
                "pywin32 is not installed (conda install pywin32); it is needed to read"
                " SolidWorks files"
            ) from exc
        try:
            self.sw_mod = gencache.EnsureModule(*_SLDWORKS_TLB)
            self.dx_mod = gencache.EnsureModule(*_DIMXPERT_TLB)
        except Exception as exc:  # pragma: no cover - depends on the machine
            raise SolidWorksError(
                "SolidWorks 2026 type libraries not found; is SOLIDWORKS 2026 installed?"
            ) from exc
        self.client = win32com.client

    def typed(self, obj: Any, interface: str) -> Any:
        for mod in (self.dx_mod, self.sw_mod):
            cls = getattr(mod, interface, None)
            if cls is not None:
                return cls(obj._oleobj_ if hasattr(obj, "_oleobj_") else obj)
        raise KeyError(interface)


def _apply(t: Sequence[float], p: Sequence[float]) -> Vec3:
    return (
        t[0] * p[0] + t[3] * p[1] + t[6] * p[2] + t[9],
        t[1] * p[0] + t[4] * p[1] + t[7] * p[2] + t[10],
        t[2] * p[0] + t[5] * p[1] + t[8] * p[2] + t[11],
    )


def _rotate(t: Sequence[float], v: Sequence[float]) -> Vec3:
    return (
        t[0] * v[0] + t[3] * v[1] + t[6] * v[2],
        t[1] * v[0] + t[4] * v[1] + t[7] * v[2],
        t[2] * v[0] + t[5] * v[1] + t[8] * v[2],
    )


IDENTITY: tuple[float, ...] = (1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0)


def tess_centroid(tri: Sequence[float]) -> tuple[Vec3, float]:
    """Area centroid and area of a triangle soup ``[x1, y1, z1, x2, ...]`` (any unit)."""
    cx = cy = cz = total = 0.0
    for i in range(0, len(tri) - 8, 9):
        a, b, c = tri[i : i + 3], tri[i + 3 : i + 6], tri[i + 6 : i + 9]
        u = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
        v = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
        cross = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
        area = 0.5 * math.sqrt(cross[0] ** 2 + cross[1] ** 2 + cross[2] ** 2)
        cx += area * (a[0] + b[0] + c[0]) / 3
        cy += area * (a[1] + b[1] + c[1]) / 3
        cz += area * (a[2] + b[2] + c[2]) / 3
        total += area
    if total == 0.0:
        raise SolidWorksError("face tessellation has no area")
    return (cx / total, cy / total, cz / total), total


class _Reader:
    def __init__(self, com: _Com) -> None:
        self.com = com
        self.notes: list[str] = []
        self.opened: list[str] = []
        try:
            raw = com.client.GetActiveObject("SldWorks.Application")
            self.started_by_us = False
        except Exception:
            try:
                raw = com.client.Dispatch("SldWorks.Application")
            except Exception as exc:  # pragma: no cover - depends on the machine
                raise SolidWorksError("SolidWorks could not be started; is it installed?") from exc
            self.started_by_us = True
        self.sw = com.typed(raw, "ISldWorks")
        if self.started_by_us:
            self.sw.Visible = False

    # -- helpers ---------------------------------------------------------------------------

    def _open(self, path: Path, doc_type: int) -> Any:
        existing = self.sw.GetOpenDocumentByName(str(path))
        if existing is not None:
            return self.com.typed(existing, "IModelDoc2")
        result = self.sw.OpenDoc6(str(path), doc_type, OPEN_SILENT_READONLY, "", 0, 0)
        doc, err = (result[0], result[1]) if isinstance(result, tuple) else (result, None)
        if doc is None:
            raise SolidWorksError(f"SolidWorks could not open {path} (error code {err})")
        self.opened.append(str(path))
        return self.com.typed(doc, "IModelDoc2")

    def face(self, raw_face: Any, part: str, transform: Sequence[float]) -> SwFace:
        f = self.com.typed(raw_face, "IFace2")
        tri = f.GetTessTriangles(True)
        if not tri:
            raise SolidWorksError(f"no tessellation for a face of '{part}'")
        centroid_m, area_m2 = tess_centroid([float(v) for v in tri])
        normal = _rotate(transform, [float(v) for v in f.Normal])
        length = math.sqrt(sum(c * c for c in normal))
        centroid = _apply(transform, centroid_m)
        return SwFace(
            part=part,
            normal=(normal[0] / length, normal[1] / length, normal[2] / length),
            centroid=(centroid[0] * M_TO_MM, centroid[1] * M_TO_MM, centroid[2] * M_TO_MM),
            area=area_m2 * M_TO_MM * M_TO_MM,
        )

    def _feature_faces(self, feature: Any, part: str, t: Sequence[float]) -> list[SwFace]:
        if feature is None:
            return []
        faces = self.com.typed(feature, "IDimXpertFeature").GetFaces() or ()
        return [self.face(f, part, t) for f in faces]

    # -- DimXpert ---------------------------------------------------------------------------

    def dimxpert(
        self, model: Any, part: str, t: Sequence[float], document: str
    ) -> tuple[list[SwDimension], list[SwFlatness]]:
        config = model.ConfigurationManager.ActiveConfiguration.Name
        manager = model.Extension.DimXpertManager(config, False)  # False: never create a schema
        if manager is None:
            return [], []
        part_x = self.com.typed(
            self.com.typed(manager, "IDimXpertManager").DimXpertPart, "IDimXpertPart"
        )
        dims: list[SwDimension] = []
        flats: list[SwFlatness] = []
        for raw in part_x.GetAnnotations() or ():
            ann = self.com.typed(raw, "IDimXpertAnnotation")
            kind, name = int(ann.Type), str(ann.Name)
            if kind in (ANNOT_WIDTH, ANNOT_DISTANCE_BETWEEN):
                tol = self.com.typed(raw, "IDimXpertDimensionTolerance")
                if kind == ANNOT_WIDTH:
                    faces = self._feature_faces(ann.Feature, part, t)
                else:
                    dist = self.com.typed(raw, "IDimXpertDistanceBetweenDimTol")
                    faces = self._feature_faces(
                        dist.GetOriginFeature(), part, t
                    ) + self._feature_faces(dist.GetFeature(), part, t)
                if len(faces) != 2:
                    self.notes.append(
                        f"{part}: DimXpert {name} has {len(faces)} faces, not 2; not used"
                    )
                    continue
                fit = str(tol.LimitsAndFitsCode or "").strip() or None
                if int(tol.DimensionType) in DX_TOL_ISO_FITS and fit:
                    upper = lower = None
                else:
                    _ok, plus, minus = tol.GetPlusAndMinusTolerance(0.0, 0.0)
                    upper, lower, fit = float(plus), float(minus), None
                dims.append(
                    SwDimension(
                        name=name,
                        part=part,
                        source="dimxpert",
                        nominal=float(tol.GetNominalValue()),
                        upper=upper,
                        lower=lower,
                        fit_code=fit,
                        faces=(faces[0], faces[1]),
                        document=document,
                        is_size=kind == ANNOT_WIDTH,
                    )
                )
            elif kind == ANNOT_FLATNESS:
                faces = self._feature_faces(ann.Feature, part, t)
                value = float(self.com.typed(raw, "IDimXpertTolerance").Tolerance) * UM_TO_MM
                if len(faces) != 1:
                    self.notes.append(
                        f"{part}: DimXpert {name} is on {len(faces)} faces (a feature of size);"
                        " only flatness of one face is used"
                    )
                    continue
                flats.append(SwFlatness(name=name, part=part, value=value, face=faces[0]))
            else:
                self.notes.append(f"{part}: DimXpert {name} (type {kind}) is not used yet")
        return dims, flats

    # -- drawings ---------------------------------------------------------------------------

    def drawing(self, path: Path, transforms: dict[str, Sequence[float]]) -> list[SwDimension]:
        doc = self._open(path, DOC_DRAWING)
        drw = self.com.typed(doc, "IDrawingDoc")
        dims: list[SwDimension] = []
        view = drw.GetFirstView()
        view = (
            self.com.typed(view, "IView").GetNextView() if view is not None else None
        )  # skip sheet
        while view is not None:
            view = self.com.typed(view, "IView")
            part = Path(str(view.GetReferencedModelName() or "")).stem
            dd = view.GetFirstDisplayDimension5()
            while dd is not None:
                dd = self.com.typed(dd, "IDisplayDimension")
                rec = self._drawing_dimension(dd, part, transforms, path.name)
                if rec is not None:
                    dims.append(rec)
                dd = dd.GetNext5()
            view = view.GetNextView()
        return dims

    def _drawing_dimension(
        self, dd: Any, part: str, transforms: dict[str, Sequence[float]], document: str
    ) -> SwDimension | None:
        dim = self.com.typed(dd.GetDimension2(0), "IDimension")
        name = str(dim.FullName)
        if part not in transforms:
            self.notes.append(f"{document}: {name} is on '{part}', which is not in the assembly")
            return None
        tol = self.com.typed(dim.Tolerance, "IDimensionTolerance")
        tol_type = int(tol.Type)
        if tol_type not in (TOL_NONE, TOL_BILAT, TOL_SYMMETRIC):
            self.notes.append(f"{document}: {name} has tolerance type {tol_type}; not used yet")
            return None
        entities = self.com.typed(dd.GetAnnotation(), "IAnnotation").GetAttachedEntities3() or ()
        adjacent: list[list[Any]] = []
        for e in entities:
            try:
                edge = self.com.typed(e, "IEdge")
                adjacent.append(list(edge.GetTwoAdjacentFaces2() or ()))
            except Exception:
                self.notes.append(f"{document}: {name} is not attached to two edges; not used")
                return None
        if len(adjacent) != 2:
            self.notes.append(
                f"{document}: {name} is attached to {len(adjacent)} entities; not used"
            )
            return None
        t = transforms[part]
        sets = [[self.face(f, part, t) for f in pair] for pair in adjacent]
        # the dimensioned faces are the adjacent faces the two edges do not share
        shared = [f for f in sets[0] if any(_same(f, g) for g in sets[1])]
        own = [[f for f in faces if not any(_same(f, s) for s in shared)] for faces in sets]
        if len(own[0]) != 1 or len(own[1]) != 1:
            self.notes.append(
                f"{document}: {name}: cannot tell which faces it dimensions; not used"
            )
            return None
        value = float(dim.SystemValue) * M_TO_MM
        upper = lower = None
        if tol_type in (TOL_BILAT, TOL_SYMMETRIC):
            upper = float(tol.GetMaxValue()) * M_TO_MM
            lower = float(tol.GetMinValue()) * M_TO_MM
        return SwDimension(
            name=name,
            part=part,
            source="drawing",
            nominal=value,
            upper=upper,
            lower=lower,
            fit_code=None,
            faces=(own[0][0], own[1][0]),
            document=document,
        )

    # -- assembly ---------------------------------------------------------------------------

    def assembly(self, path: Path, drawings: Iterable[Path], step_path: Path) -> SwAssemblyData:
        doc = self._open(path, DOC_ASSEMBLY)
        asm = self.com.typed(doc, "IAssemblyDoc")
        dims: list[SwDimension] = []
        flats: list[SwFlatness] = []
        transforms: dict[str, Sequence[float]] = {}
        parts: list[str] = []
        for raw in asm.GetComponents(False) or ():
            comp = self.com.typed(raw, "IComponent2")
            if comp.IsSuppressed():
                self.notes.append(f"{comp.Name2}: suppressed; ignored")
                continue
            model = comp.GetModelDoc2()
            if model is None:
                self.notes.append(f"{comp.Name2}: not loaded (lightweight?); ignored")
                continue
            model = self.com.typed(model, "IModelDoc2")
            if int(model.GetType()) != DOC_PART:
                continue  # sub-assembly node; its parts are listed too
            part = Path(str(model.GetPathName())).stem
            if part in transforms:
                raise SolidWorksError(
                    f"part '{part}' is used more than once in the assembly; not supported yet"
                )
            t = [float(v) for v in self.com.typed(comp.Transform2, "IMathTransform").ArrayData]
            if abs(t[12] - 1.0) > 1e-12:
                raise SolidWorksError(f"component {comp.Name2} is scaled; not supported")
            transforms[part] = t
            parts.append(part)
            d, f = self.dimxpert(model, part, t, Path(str(model.GetPathName())).name)
            dims += d
            flats += f
        for drawing in drawings:
            dims += self.drawing(Path(drawing), transforms)
        self._export_step(doc, step_path)
        return SwAssemblyData(
            assembly=str(path),
            parts=tuple(parts),
            dimensions=tuple(dims),
            flatness=tuple(flats),
            notes=tuple(self.notes),
            solidworks_revision=str(self.sw.RevisionNumber()),
        )

    def _export_step(self, doc: Any, step_path: Path) -> None:
        previous = self.sw.GetUserPreferenceIntegerValue(PREF_STEP_AP)
        try:
            self.sw.SetUserPreferenceIntegerValue(PREF_STEP_AP, 214)
            ok, err, warn = doc.Extension.SaveAs3(
                str(step_path), 0, SAVEAS_SILENT_COPY, None, None, 0, 0
            )
        finally:
            self.sw.SetUserPreferenceIntegerValue(PREF_STEP_AP, previous)
        if not ok or not step_path.is_file():
            raise SolidWorksError(f"STEP geometry export failed (errors {err}, warnings {warn})")

    def close(self) -> None:
        for name in reversed(self.opened):
            try:
                doc = self.sw.GetOpenDocumentByName(name)
                if doc is not None:
                    self.sw.CloseDoc(self.com.typed(doc, "IModelDoc2").GetTitle())
            except Exception:  # pragma: no cover - best effort
                pass
        if self.started_by_us:
            with contextlib.suppress(Exception):  # best effort
                self.sw.ExitApp()


def _same(a: SwFace, b: SwFace) -> bool:
    return math.dist(a.centroid, b.centroid) < 1e-6 and abs(a.area - b.area) < 1e-6


def read_solidworks(
    assembly: str | Path, step_path: str | Path, drawings: Sequence[str | Path] = ()
) -> SolidWorksReadout:
    """Read an assembly (and optional drawings) and write its STEP geometry to ``step_path``.

    Raises:
        SolidWorksError: pywin32 or SolidWorks missing, a file does not open, an
            unsupported construct (a part used twice, a scaled component), or a
            failed STEP export.
    """
    path = Path(assembly).resolve()
    if not path.is_file():
        raise SolidWorksError(f"file not found: {path}")
    if path.suffix.lower() != ".sldasm":
        raise SolidWorksError(f"{path.name}: expected a SolidWorks assembly (.SLDASM)")
    com = _Com()
    import pythoncom  # part of pywin32; COM must be initialised in every thread that uses it

    pythoncom.CoInitialize()
    try:
        reader = _Reader(com)
        try:
            data = reader.assembly(path, [Path(d).resolve() for d in drawings], Path(step_path))
        finally:
            reader.close()
    finally:
        pythoncom.CoUninitialize()
    return SolidWorksReadout(data=data, step_path=Path(step_path))
