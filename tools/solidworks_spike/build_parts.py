# ruff: noqa
# Step 1 feasibility spike (docs/reports/phase-app-1.md). Not product code; needs SOLIDWORKS + pywin32.
"""Build the four test parts with DimXpert tolerances (docs/guides/solidworks-test-assembly.md).

Geometry (mm): sketch on the Front plane (XY), extruded 20 along +Z.
  Block_A 25 x 5, Block_B 35 x 5, Block_C 39 x 5 (X x Y)
  Frame: U profile, base y = -5..0 from x = -5..105, walls x = -5..0 and 100..105 up to y = 5;
         inner opening x = 0..100.
DimXpert (set through the document defaults, then inserted):
  Frame width 100 +0.20/-0.20 (inner faces), Block_A 25 +/-0.10, Block_B 35 +/-0.05 plus
  flatness 0.02 on its +X face, Block_C 39 +0.10/-0.00.
Every value is read back through the DimXpert API and printed.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pythoncom
from win32com.client import VARIANT

from swlib import MM, SW_DOC_PART, connect, dimxpert_part, extrude_blind, new_doc, save_as, select_point, typed

OUT = Path(sys.argv[1])
PREF_WIDTH_TOLTYPE, PREF_WIDTH_UP, PREF_WIDTH_LO = 426, 161, 162
DX_BILATERAL = 0
GTOL_FLATNESS = 1


def arr_l(v):
    return VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_I4, v)


def arr_d(v):
    return VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, v)


def set_width_default(doc, upper: float, lower: float) -> None:
    ext = typed(doc.Extension, "IModelDocExtension")
    ok = [
        ext.SetUserPreferenceInteger(PREF_WIDTH_TOLTYPE, 0, DX_BILATERAL),
        ext.SetUserPreferenceDouble(PREF_WIDTH_UP, 0, upper * MM),
        ext.SetUserPreferenceDouble(PREF_WIDTH_LO, 0, lower * MM),
    ]
    if not all(ok):
        raise RuntimeError(f"could not set DimXpert width defaults: {ok}")


def width(doc, dxp, edge_point, text_point) -> None:
    if not select_point(doc, "EDGE", *edge_point, append=False):
        raise RuntimeError(f"edge not found at {edge_point}")
    opt = typed(dxp.GetDimOption(), "IDimXpertDimensionOption")
    opt.TextPosition = arr_d([v * MM for v in text_point])
    opt.FeatureSelectorOptions = arr_l([-1])
    dxp.InsertSizeDimension(opt)
    doc.ClearSelection2(True)


def flatness(doc, dxp, face_point, value: float) -> None:
    if not select_point(doc, "FACE", *face_point, append=False):
        raise RuntimeError(f"face not found at {face_point}")
    ann = typed(dxp.InsertGtol(GTOL_FLATNESS), "IDimXpertAnnotation")
    gtol = typed(typed(ann.GetDisplayEntity(), "IAnnotation").GetSpecificAnnotation(), "IGtol")
    if not gtol.SetFrameValues2(1, f"{value:g}", "", "", "", ""):
        raise RuntimeError("SetFrameValues2 failed")
    doc.ClearSelection2(True)
    doc.EditRebuild3()


def readback(dxp) -> list[str]:
    lines = []
    for raw in dxp.GetAnnotations() or ():
        a = typed(raw, "IDimXpertAnnotation")
        faces = typed(a.Feature, "IDimXpertFeature").GetFaces() or ()
        normals = [tuple(round(v, 3) + 0.0 for v in typed(f, "IFace2").Normal) for f in faces]
        if a.Type == 112:
            t = typed(raw, "IDimXpertDimensionTolerance")
            _ok, plus, minus = t.GetPlusAndMinusTolerance(0.0, 0.0)
            lines.append(f"  {a.Name}: width {t.GetNominalValue():g} {plus:+g}/{minus:+g}  faces {normals}")
        else:
            g = typed(raw, "IDimXpertTolerance")
            lines.append(f"  {a.Name}: type {a.Type} value(raw) {g.Tolerance:g}  faces {normals}")
    return lines


def make_block(sw, name: str, length: float, upper: float, lower: float, flat: float | None = None):
    doc = new_doc(sw, SW_DOC_PART)
    doc.Extension.SelectByID2("Front Plane", "PLANE", 0, 0, 0, False, 0, None, 0)
    doc.SketchManager.InsertSketch(True)
    doc.SketchManager.CreateCornerRectangle(0, 0, 0, length * MM, 5 * MM, 0)
    doc.SketchManager.InsertSketch(True)
    extrude_blind(doc, 20)
    doc.ClearSelection2(True)
    set_width_default(doc, upper, lower)
    dxp = dimxpert_part(doc)
    if flat is not None:  # before the width, so it attaches to the single face
        flatness(doc, dxp, (length, 2.5, 10), flat)
    width(doc, dxp, (length / 2, 5, 0), (length / 2, 15, 0))
    return doc, dxp


def make_frame(sw):
    doc = new_doc(sw, SW_DOC_PART)
    doc.Extension.SelectByID2("Front Plane", "PLANE", 0, 0, 0, False, 0, None, 0)
    sk = doc.SketchManager
    sk.InsertSketch(True)
    pts = [(-5, -5), (105, -5), (105, 5), (100, 5), (100, 0), (0, 0), (0, 5), (-5, 5), (-5, -5)]
    for (x1, y1), (x2, y2) in zip(pts, pts[1:], strict=False):
        sk.CreateLine(x1 * MM, y1 * MM, 0, x2 * MM, y2 * MM, 0)
    sk.InsertSketch(True)
    extrude_blind(doc, 20)
    doc.ClearSelection2(True)
    set_width_default(doc, 0.20, -0.20)
    dxp = dimxpert_part(doc)
    width(doc, dxp, (50, 0, 0), (50, 15, 0))  # edge at the bottom of the opening -> inner width
    return doc, dxp


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    sw = connect(visible=True)
    jobs = [
        ("Frame", lambda: make_frame(sw)),
        ("Block_A", lambda: make_block(sw, "Block_A", 25, 0.10, -0.10)),
        ("Block_B", lambda: make_block(sw, "Block_B", 35, 0.05, -0.05, flat=0.02)),
        ("Block_C", lambda: make_block(sw, "Block_C", 39, 0.10, 0.0)),
    ]
    for name, build in jobs:
        doc, dxp = build()
        path = str(OUT / f"{name}.SLDPRT")
        save_as(doc, path)
        print(name, "->", path)
        print("\n".join(readback(dxp)))
        sw.CloseDoc(doc.GetTitle())


if __name__ == "__main__":
    main()
