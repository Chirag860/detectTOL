# ruff: noqa
# Step 1 feasibility spike (docs/reports/phase-app-1.md). Not product code; needs SOLIDWORKS + pywin32.
"""Step 1 feasibility read-out: what detectTOL can read from SolidWorks 2026 files.

Usage: python readout.py <folder> <out.json>
Reads Tolerance_Test.SLDASM (components, transforms, DimXpert annotations with their
faces in assembly coordinates, general-tolerance settings) and Block_C.SLDDRW
(dimensions, tolerances, attached model faces). Then matches every SolidWorks face to
a face of the STEP geometry copy with detecttol's reader. Nothing is written to the
SolidWorks files.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from swlib import MM, connect, typed

FOLDER, OUT = Path(sys.argv[1]), Path(sys.argv[2])
TYPES = {112: "Width", 101: "DistanceBetween", 215: "Flatness", 211: "Parallelism", 150: "Datum"}
PREFS = {"tolerance_method_637": 637, "general_class_408": 408, "width_toltype_426": 426}


def apply(transform, p):
    r, t = transform[0:9], transform[9:12]
    return [r[0] * p[0] + r[3] * p[1] + r[6] * p[2] + t[0],
            r[1] * p[0] + r[4] * p[1] + r[7] * p[2] + t[1],
            r[2] * p[0] + r[5] * p[1] + r[8] * p[2] + t[2]]


def rotate(transform, v):
    r = transform[0:9]
    return [r[0] * v[0] + r[3] * v[1] + r[6] * v[2],
            r[1] * v[0] + r[4] * v[1] + r[7] * v[2],
            r[2] * v[0] + r[5] * v[1] + r[8] * v[2]]


def face_record(face, transform):
    f = typed(face, "IFace2")
    box = f.GetBox()  # part coordinates, metres
    centre = [(box[i] + box[i + 3]) / 2 for i in range(3)]  # exact for axis-aligned rectangles
    return {
        "normal": [round(v, 9) + 0.0 for v in rotate(transform, list(f.Normal))],
        "centre_mm": [round(v / MM, 6) + 0.0 for v in apply(transform, centre)],
        "area_mm2": round(f.GetArea() / MM / MM, 6),
    }


def annotations(model, transform):
    config = model.ConfigurationManager.ActiveConfiguration.Name
    dxp = typed(typed(model.Extension.DimXpertManager(config, False), "IDimXpertManager").DimXpertPart, "IDimXpertPart")
    out = []
    for raw in dxp.GetAnnotations() or ():
        a = typed(raw, "IDimXpertAnnotation")
        rec = {"name": a.Name, "type": TYPES.get(a.Type, a.Type)}
        if a.Type in (112, 101):
            t = typed(raw, "IDimXpertDimensionTolerance")
            ok, plus, minus = t.GetPlusAndMinusTolerance(0.0, 0.0)
            rec.update(nominal_mm=t.GetNominalValue(), upper_mm=plus, lower_mm=minus,
                       tol_type=t.DimensionType, fit_code=t.LimitsAndFitsCode)
        elif a.Type >= 200:
            rec["value_raw"] = typed(raw, "IDimXpertTolerance").Tolerance
        rec["faces"] = [face_record(f, transform) for f in (typed(a.Feature, "IDimXpertFeature").GetFaces() or ())]
        out.append(rec)
    general = {}
    ext = typed(model.Extension, "IModelDocExtension")
    for label, idx in PREFS.items():
        general[label] = ext.GetUserPreferenceInteger(idx, 0)
    general["block_tolerance_toggle_424"] = ext.GetUserPreferenceToggle(424, 0)
    try:
        b = typed(dxp.GetBlockTolerances(), "IDimXpertBlockTolerances")
        general["block_type"], general["iso2768_part_type"] = b.Type, b.GetISO2768PartType()
    except Exception as exc:  # noqa: BLE001
        general["block_error"] = str(exc)[:120]
    return out, general


def drawing(sw, path):
    res = sw.OpenDoc6(str(path), 3, 1, "", 0, 0)
    doc = typed(res[0] if isinstance(res, tuple) else res, "IModelDoc2")
    dims = []
    view = typed(typed(doc._oleobj_, "IDrawingDoc").GetFirstView(), "IView").GetNextView()
    while view is not None:
        view = typed(view, "IView")
        dd = view.GetFirstDisplayDimension5()
        while dd is not None:
            dd = typed(dd, "IDisplayDimension")
            dim = typed(dd.GetDimension2(0), "IDimension")
            tol = typed(dim.Tolerance, "IDimensionTolerance")
            rec = {"view": view.GetName2(), "model": view.GetReferencedModelName(), "name": dim.FullName,
                   "value_mm": dim.SystemValue / MM, "tol_type": tol.Type,
                   "upper_mm": tol.GetMaxValue() / MM, "lower_mm": tol.GetMinValue() / MM}
            faces = []
            ents = typed(dd.GetAnnotation(), "IAnnotation").GetAttachedEntities3() or ()
            for e in ents:
                try:
                    edge = typed(e, "IEdge")
                    adj = edge.GetTwoAdjacentFaces2() or ()
                    faces.append([face_record(f, [1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0]) for f in adj])
                except Exception as exc:  # noqa: BLE001
                    faces.append(f"not an edge: {str(exc)[:60]}")
            rec["attached_edges_adjacent_faces"] = faces
            dims.append(rec)
            dd = dd.GetNext5()
        view = view.GetNextView()
    sw.CloseDoc(doc.GetTitle())
    return dims


def main() -> None:
    report: dict = {}
    t0 = time.perf_counter()
    sw = connect(visible=False)
    report["start_s"] = round(time.perf_counter() - t0, 1)
    t1 = time.perf_counter()
    res = sw.OpenDoc6(str(FOLDER / "Tolerance_Test.SLDASM"), 2, 1, "", 0, 0)
    asm_doc = typed(res[0] if isinstance(res, tuple) else res, "IModelDoc2")
    report["open_assembly_s"] = round(time.perf_counter() - t1, 1)
    comps = []
    for c in typed(asm_doc._oleobj_, "IAssemblyDoc").GetComponents(False) or ():
        comp = typed(c, "IComponent2")
        transform = list(typed(comp.Transform2, "IMathTransform").ArrayData)
        model = typed(comp.GetModelDoc2(), "IModelDoc2")
        anns, general = annotations(model, transform)
        comps.append({"component": comp.Name2, "part_file": Path(model.GetPathName()).name,
                      "translation_mm": [round(v / MM, 6) for v in transform[9:12]],
                      "annotations": anns, "general_tolerance_settings": general})
    report["components"] = comps
    report["read_assembly_s"] = round(time.perf_counter() - t1, 1)
    sw.CloseDoc(asm_doc.GetTitle())
    t2 = time.perf_counter()
    report["drawing"] = drawing(sw, FOLDER / "Block_C.SLDDRW")
    report["read_drawing_s"] = round(time.perf_counter() - t2, 1)
    report["total_s"] = round(time.perf_counter() - t0, 1)
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=1)[:9000])


if __name__ == "__main__":
    main()
