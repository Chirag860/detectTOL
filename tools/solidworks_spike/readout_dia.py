# ruff: noqa
# Diameter feasibility spike (docs/reports/phase-dia-1.md). Not product code; needs SOLIDWORKS + pywin32.
"""Read diameters, fits, datums and positions from an assembly; match the round faces to STEP.

    python readout_dia.py <assembly.SLDASM> <out.json>

For every component: each DimXpert diameter (109), position (201) and datum (150) with its
faces. A cylindrical face is given by axis point, axis direction and radius (ISurface
CylinderParams), plus tessellated centroid and area, all in assembly coordinates [mm].
The fit code is taken from the annotation's display dimension (DimXpert's own
LimitsAndFitsCode stays empty when the fit is set through the API).
Then a STEP copy is exported (AP214) and every face is matched to a STEP face by surface
type, centroid (1e-3 mm) and area (0.1 %).
"""

from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from detecttol.cad.step_reader import read_step  # noqa: E402
from detecttol.solidworks.reader import tess_centroid  # noqa: E402
from swlib import MM, connect, typed  # noqa: E402

ASM, OUT = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
ANN_DIAMETER, ANN_POSITION, ANN_DATUM, ANN_WIDTH, ANN_DIST = 109, 201, 150, 112, 101
MCM = {0: "unknown", 1: "LMC", 2: "MMC", 3: "none", 4: "RFS"}


def apply(t, p):
    return [t[0] * p[0] + t[3] * p[1] + t[6] * p[2] + t[9], t[1] * p[0] + t[4] * p[1] + t[7] * p[2] + t[10],
            t[2] * p[0] + t[5] * p[1] + t[8] * p[2] + t[11]]


def rotate(t, v):
    return [t[0] * v[0] + t[3] * v[1] + t[6] * v[2], t[1] * v[0] + t[4] * v[1] + t[7] * v[2],
            t[2] * v[0] + t[5] * v[1] + t[8] * v[2]]


def face_info(raw, t):
    f = typed(raw, "IFace2")
    s = typed(f.GetSurface(), "ISurface")
    c_m, a_m2 = tess_centroid([float(v) for v in f.GetTessTriangles(True)])
    info = {"centroid": [v / MM for v in apply(t, c_m)], "area": a_m2 / MM / MM}
    if s.IsCylinder():
        p = [float(v) for v in s.CylinderParams]  # origin xyz, axis xyz, radius [m]
        info |= {"surface": "cylinder", "axis_point": [v / MM for v in apply(t, p[0:3])],
                 "axis": rotate(t, p[3:6]), "radius": p[6] / MM, "reversed": bool(f.FaceInSurfaceSense()) is False}
    elif s.IsPlane():
        info |= {"surface": "plane", "normal": rotate(t, [float(v) for v in f.Normal])}
    else:
        info |= {"surface": "other"}
    return info


def display_fit(a):
    disp = typed(typed(a.GetDisplayEntity(), "IAnnotation").GetSpecificAnnotation(), "IDisplayDimension")
    tol = typed(typed(disp.GetDimension2(0), "IDimension").Tolerance, "IDimensionTolerance")
    return {"tol_type": tol.Type, "hole_fit": tol.GetHoleFitValue(), "shaft_fit": tol.GetShaftFitValue()}


def annotations(model, part, t):
    config = model.ConfigurationManager.ActiveConfiguration.Name
    manager = typed(model.Extension.DimXpertManager(config, False), "IDimXpertManager")
    dxp = typed(manager.DimXpertPart, "IDimXpertPart")
    out = []
    for raw in dxp.GetAnnotations() or ():
        a = typed(raw, "IDimXpertAnnotation")
        feat = typed(a.Feature, "IDimXpertFeature")
        entry = {"part": part, "name": a.Name, "type": a.Type, "feature": feat.Name, "feature_type": feat.Type,
                 "faces": [face_info(f, t) for f in feat.GetFaces() or ()]}
        if a.Type in (ANN_DIAMETER, ANN_WIDTH, ANN_DIST):
            d = typed(raw, "IDimXpertDimensionTolerance")
            _ok, plus, minus = d.GetPlusAndMinusTolerance(0.0, 0.0)
            entry |= {"nominal": d.GetNominalValue(), "plus": plus, "minus": minus,
                      "fit_code_dimxpert": d.LimitsAndFitsCode, "display": display_fit(a)}
        elif a.Type == ANN_POSITION:
            g = typed(raw, "IDimXpertTolerance")
            p = typed(raw, "IDimXpertPositionTolerance")
            frame = typed(typed(a.GetDisplayEntity(), "IAnnotation").GetSpecificAnnotation(), "IGtol")
            entry |= {"value_um": g.Tolerance, "material_condition": MCM.get(p.Modifier, p.Modifier),
                      "datums": [[typed(d, "IDimXpertDatum").Identifier for d in (getter() or ())]
                                 for getter in (g.GetPrimaryDatums, g.GetSecondaryDatums, g.GetTertiaryDatums)],
                      "display_frame": list(frame.GetFrameValues(1)), "display_symbols": list(frame.GetFrameSymbols3(1))}
        elif a.Type == ANN_DATUM:
            entry |= {"datum": typed(raw, "IDimXpertDatum").Identifier}
        out.append(entry)
    return out


def match(face, step_faces):
    hits = []
    for name, f in step_faces:
        if f.surface != face["surface"]:
            continue
        d = math.dist(f.centroid, face["centroid"])
        if d <= 1e-3 and abs(f.area - face["area"]) <= 1e-3 * max(f.area, 1e-9):
            hits.append(name)
    return hits


def main() -> None:
    sw = connect(visible=False)
    t0 = time.perf_counter()
    res = sw.OpenDoc6(str(ASM), 2, 3, "", 0, 0)  # 3 = silent + read-only
    doc = typed(res[0] if isinstance(res, tuple) else res, "IModelDoc2")
    asm = typed(doc, "IAssemblyDoc")
    items, transforms = [], {}
    for raw in asm.GetComponents(False) or ():
        comp = typed(raw, "IComponent2")
        model = typed(comp.GetModelDoc2(), "IModelDoc2")
        part = Path(str(model.GetPathName())).stem
        t = [float(v) for v in typed(comp.Transform2, "IMathTransform").ArrayData]
        transforms[part] = t
        items += annotations(model, part, t)
    step = OUT.with_suffix(".step")
    prev = sw.GetUserPreferenceIntegerValue(75)
    sw.SetUserPreferenceIntegerValue(75, 214)
    ok = doc.Extension.SaveAs3(str(step), 0, 1 | 2, None, None, 0, 0)
    sw.SetUserPreferenceIntegerValue(75, prev)
    elapsed = time.perf_counter() - t0
    model = read_step(step)
    step_faces = [(f"{inst.name}:{f.index}", f) for inst in model.parts for f in inst.faces]
    for it in items:
        for f in it["faces"]:
            f["step_match"] = match(f, step_faces)
    OUT.write_text(json.dumps({"assembly": ASM.name, "solidworks": sw.RevisionNumber(), "read_s": round(elapsed, 1),
                               "items": items}, indent=1))
    sw.CloseDoc(doc.GetTitle())
    for it in items:
        faces = "; ".join(
            f"{f['surface']} " + (f"R{f['radius']:g} axis {[round(v, 3) + 0.0 for v in f['axis']]} at {[round(v, 3) + 0.0 for v in f['axis_point']]}"
                                  if f["surface"] == "cylinder" else f"n {[round(v, 3) + 0.0 for v in f['normal']]}")
            + f" -> {f['step_match']}" for f in it["faces"])
        extra = {k: it[k] for k in ("nominal", "plus", "minus", "fit_code_dimxpert", "display", "value_um",
                                    "material_condition", "datums", "display_frame", "datum") if k in it}
        print(f"{it['part']:8} {it['name']:32} {extra}\n{'':10}{faces}")
    print(f"read {elapsed:.1f} s; step {step.name} ({ok})")


if __name__ == "__main__":
    main()
