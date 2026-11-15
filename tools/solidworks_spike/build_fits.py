# ruff: noqa
# Diameter feasibility spike (docs/reports/phase-dia-1.md). Not product code; needs SOLIDWORKS + pywin32.
"""Build the diameter test parts with DimXpert diameters, fit codes, datums and position.

Geometry (mm): sketches on the Front plane (XY), extruded along +Z.
  Housing   40 x 40 x 20, hole dia 20 at (20, 20) through        -> dia 20 H7
  Shaft     dia 20 at (0, 0), length 40                           -> dia 20 g6
  Plate_1/2 60 x 20 x 10, hole dia 6.2 at (30, 10)                -> dia 6.2 +/-0.05,
            datums A (z = 0 face), B (x = 0 face), C (y = 0 face), position dia 0.1 (M) |A|B|C|
  Pin       dia 6 at (0, 0), length 20                            -> dia 6 +0/-0.02
Every value is read back through the DimXpert API and printed.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pythoncom
from win32com.client import VARIANT

from swlib import MM, SW_DOC_PART, connect, dimxpert_part, extrude_blind, new_doc, save_as, select_point, typed

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
ONLY = set(sys.argv[2:])
PREF_DIA_TOLTYPE, PREF_DIA_UP, PREF_DIA_LO = 421, 151, 152
PREF_POS_VALUE, PREF_POS_MMC = 140, 431
DX_BILATERAL = 0
GTOL_POSITION = 9
SW_TOL_FIT = 7
ANN_DIAMETER, ANN_POSITION, ANN_DATUM = 109, 201, 150


def arr_l(v):
    return VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_I4, v)


def arr_d(v):
    return VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, v)


def set_dia_default(doc, upper: float, lower: float) -> None:
    ext = typed(doc.Extension, "IModelDocExtension")
    ok = [
        ext.SetUserPreferenceInteger(PREF_DIA_TOLTYPE, 0, DX_BILATERAL),
        ext.SetUserPreferenceDouble(PREF_DIA_UP, 0, upper * MM),
        ext.SetUserPreferenceDouble(PREF_DIA_LO, 0, lower * MM),
    ]
    if not all(ok):
        raise RuntimeError(f"could not set DimXpert diameter defaults: {ok}")


def dim_option(dxp, text_point):
    opt = typed(dxp.GetDimOption(), "IDimXpertDimensionOption")
    opt.TextPosition = arr_d([v * MM for v in text_point])
    opt.FeatureSelectorOptions = arr_l([-1])
    return opt


def diameter(doc, dxp, face_point, text_point, fit: str | None = None):
    # InsertSizeDimension returns False for a diameter even when it creates it (seen on
    # SW 2026), so success is judged by the annotation count.
    before = dxp.GetAnnotationCount()
    if not select_point(doc, "FACE", *face_point, append=False):
        raise RuntimeError(f"cylindrical face not found at {face_point}")
    ret = dxp.InsertSizeDimension(dim_option(dxp, text_point))
    doc.ClearSelection2(True)
    if dxp.GetAnnotationCount() <= before:
        raise RuntimeError(f"InsertSizeDimension created nothing at {face_point} (returned {ret})")
    ann = _last(dxp, ANN_DIAMETER)
    if fit:
        disp = typed(typed(ann.GetDisplayEntity(), "IAnnotation").GetSpecificAnnotation(), "IDisplayDimension")
        dim = typed(disp.GetDimension2(0), "IDimension")
        tol = typed(dim.Tolerance, "IDimensionTolerance")
        tol.Type = SW_TOL_FIT
        hole, shaft = (fit, "") if fit[0].isupper() else ("", fit)
        if not tol.SetFitValues(hole, shaft):
            raise RuntimeError(f"SetFitValues({fit}) failed")
        doc.EditRebuild3()
    return ann


def _last(dxp, kind: int):
    found = [typed(a, "IDimXpertAnnotation") for a in dxp.GetAnnotations() or ()]
    found = [a for a in found if a.Type == kind]
    if not found:
        raise RuntimeError(f"no annotation of type {kind}")
    return found[-1]


def datum(doc, dxp, face_point, text_point) -> None:
    if not select_point(doc, "FACE", *face_point, append=False):
        raise RuntimeError(f"datum face not found at {face_point}")
    ok = dxp.InsertDatum(dim_option(dxp, text_point))
    doc.ClearSelection2(True)
    if not ok:
        raise RuntimeError(f"InsertDatum failed at {face_point}")


def position(doc, dxp, face_point, value: float, datums=("A", "B", "C")):
    if not select_point(doc, "FACE", *face_point, append=False):
        raise RuntimeError(f"hole face not found at {face_point}")
    raw = dxp.InsertGtol(GTOL_POSITION)
    doc.ClearSelection2(True)
    if raw is None:
        raise RuntimeError("InsertGtol(position) returned None")
    ann = typed(raw, "IDimXpertAnnotation")
    gtol = typed(typed(ann.GetDisplayEntity(), "IAnnotation").GetSpecificAnnotation(), "IGtol")
    # Only the value reaches DimXpert through the API (SW 2026): the datum letters show in
    # the frame but are not linked, and MMC cannot be set (SetFrameSymbols2 has no effect).
    if not gtol.SetFrameValues2(1, f"{value:g}", "", *datums):
        raise RuntimeError("SetFrameValues2 failed")
    doc.EditRebuild3()
    return ann


def _cyl(feature):
    """(radius mm, centre mm, axis) of a DimXpert cylinder feature, if it is one."""
    try:
        cyl = typed(feature, "IDimXpertCylinderFeature")
        res = cyl.GetNominalCylinder(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    except Exception as exc:  # noqa: BLE001
        return f"(no cylinder: {exc.__class__.__name__})"
    ok, r, x, y, z, i, j, k = res if len(res) == 8 else (True, *res)
    return f"R {r:g} at ({x:g}, {y:g}, {z:g}) axis ({i:g}, {j:g}, {k:g}) inner={cyl.Inner}"


def _display_fit(a):
    """(tolerance type, hole fit, shaft fit) of the annotation's display dimension."""
    disp = typed(typed(a.GetDisplayEntity(), "IAnnotation").GetSpecificAnnotation(), "IDisplayDimension")
    tol = typed(typed(disp.GetDimension2(0), "IDimension").Tolerance, "IDimensionTolerance")
    return (tol.Type, tol.GetHoleFitValue(), tol.GetShaftFitValue())


def readback(dxp) -> list[str]:
    lines = []
    for raw in dxp.GetAnnotations() or ():
        a = typed(raw, "IDimXpertAnnotation")
        feat = typed(a.Feature, "IDimXpertFeature")
        faces = feat.GetFaces() or ()
        kinds = [typed(f, "IFace2").GetSurface() for f in faces]
        surf = ["cyl" if typed(s, "ISurface").IsCylinder() else "plane" if typed(s, "ISurface").IsPlane() else "?" for s in kinds]
        head = f"  {a.Name}: type {a.Type} feature {feat.Name} (type {feat.Type}) faces {surf}"
        if a.Type in (ANN_DIAMETER, 112, 101):
            t = typed(raw, "IDimXpertDimensionTolerance")
            _ok, plus, minus = t.GetPlusAndMinusTolerance(0.0, 0.0)
            lines.append(f"{head}\n      nominal {t.GetNominalValue() / MM if t.GetNominalValue() < 1 else t.GetNominalValue():g}"
                         f" {plus:+g}/{minus:+g} fit '{t.LimitsAndFitsCode}' display-fit {_display_fit(a)}")
            if feat.Type == 2:
                lines.append(f"      {_cyl(feat)}")
        elif a.Type == ANN_POSITION:
            p = typed(raw, "IDimXpertPositionTolerance")
            g = typed(raw, "IDimXpertTolerance")
            prim = [typed(d, "IDimXpertDatum").Identifier for d in (g.GetPrimaryDatums() or ())]
            sec = [typed(d, "IDimXpertDatum").Identifier for d in (g.GetSecondaryDatums() or ())]
            ter = [typed(d, "IDimXpertDatum").Identifier for d in (g.GetTertiaryDatums() or ())]
            frame = typed(typed(a.GetDisplayEntity(), "IAnnotation").GetSpecificAnnotation(), "IGtol")
            lines.append(f"{head}\n      value(raw) {g.Tolerance:g} modifier {p.Modifier} zone {p.ZoneType} datums {prim}|{sec}|{ter}"
                         f"\n      display frame {frame.GetFrameValues(1)} symbols {frame.GetFrameSymbols3(1)}")
            if feat.Type == 2:
                lines.append(f"      {_cyl(feat)}")
        elif a.Type == ANN_DATUM:
            d = typed(raw, "IDimXpertDatum")
            lines.append(f"{head}\n      datum {d.Identifier}")
        else:
            lines.append(head)
    return lines


def sketch_front(doc):
    doc.Extension.SelectByID2("Front Plane", "PLANE", 0, 0, 0, False, 0, None, 0)
    doc.SketchManager.InsertSketch(True)
    return doc.SketchManager


def circle(sk, cx, cy, d):
    sk.CreateCircleByRadius(cx * MM, cy * MM, 0, d / 2 * MM)


def make_housing(sw):
    doc = new_doc(sw, SW_DOC_PART)
    sk = sketch_front(doc)
    sk.CreateCornerRectangle(0, 0, 0, 40 * MM, 40 * MM, 0)
    circle(sk, 20, 20, 20)
    sk.InsertSketch(True)
    extrude_blind(doc, 20)
    doc.ClearSelection2(True)
    dxp = dimxpert_part(doc)
    diameter(doc, dxp, (20, 30, 10), (20, 50, 20), fit="H7")  # face point on the bore (y = 30)
    return doc, dxp


def make_shaft(sw):
    doc = new_doc(sw, SW_DOC_PART)
    sk = sketch_front(doc)
    circle(sk, 0, 0, 20)
    sk.InsertSketch(True)
    extrude_blind(doc, 40)
    doc.ClearSelection2(True)
    dxp = dimxpert_part(doc)
    diameter(doc, dxp, (0, 10, 20), (0, 25, 20), fit="g6")
    return doc, dxp


def make_plate(sw):
    doc = new_doc(sw, SW_DOC_PART)
    sk = sketch_front(doc)
    sk.CreateCornerRectangle(0, 0, 0, 60 * MM, 20 * MM, 0)
    circle(sk, 30, 10, 6.2)
    sk.InsertSketch(True)
    extrude_blind(doc, 10)
    doc.ClearSelection2(True)
    set_dia_default(doc, 0.05, -0.05)
    dxp = dimxpert_part(doc)
    datum(doc, dxp, (10, 5, 0), (10, -10, 0))     # A: z = 0
    datum(doc, dxp, (0, 5, 5), (-10, 5, 5))       # B: x = 0
    datum(doc, dxp, (10, 0, 5), (10, -10, 5))     # C: y = 0
    diameter(doc, dxp, (30, 13.1, 5), (30, 30, 5))
    position(doc, dxp, (30, 13.1, 5), 0.1)
    return doc, dxp


def make_pin(sw):
    doc = new_doc(sw, SW_DOC_PART)
    sk = sketch_front(doc)
    circle(sk, 0, 0, 6)
    sk.InsertSketch(True)
    extrude_blind(doc, 20)
    doc.ClearSelection2(True)
    set_dia_default(doc, 0.0, -0.02)
    dxp = dimxpert_part(doc)
    diameter(doc, dxp, (0, 3, 10), (0, 15, 10))
    return doc, dxp


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    sw = connect(visible=True)
    jobs = [
        ("Housing", lambda: make_housing(sw)),
        ("Shaft", lambda: make_shaft(sw)),
        ("Plate_1", lambda: make_plate(sw)),
        ("Plate_2", lambda: make_plate(sw)),
        ("Pin", lambda: make_pin(sw)),
    ]
    for name, build in jobs:
        if ONLY and name not in ONLY:
            continue
        doc, dxp = build()
        path = str(OUT / f"{name}.SLDPRT")
        save_as(doc, path)
        print(name, "->", path)
        print("\n".join(readback(dxp)))
        sw.CloseDoc(doc.GetTitle())


if __name__ == "__main__":
    main()
