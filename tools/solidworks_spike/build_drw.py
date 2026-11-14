# ruff: noqa
# Step 1 feasibility spike (docs/reports/phase-app-1.md). Not product code; needs SOLIDWORKS + pywin32.
"""Block_C.SLDDRW: front view, the 39 mm length dimensioned with +0.10/-0.00."""

from __future__ import annotations

import sys
from pathlib import Path

from swlib import MM, SW_DOC_DRAWING, SW_TOL_BILAT, connect, new_doc, save_as, typed

FOLDER = Path(sys.argv[1])
VIEW_EDGE = 1


def main() -> None:
    sw = connect(visible=True)
    part = str(FOLDER / "Block_C.SLDPRT")
    sw.OpenDoc6(part, 1, 1, "", 0, 0)
    doc = new_doc(sw, SW_DOC_DRAWING)
    drw = typed(doc._oleobj_, "IDrawingDoc")
    view = drw.CreateDrawViewFromModelView3(part, "*Front", 0.15, 0.12, 0)
    if view is None:
        raise RuntimeError("could not create the front view")
    view = typed(view, "IView")
    print("view", view.GetName2(), "scale", view.ScaleDecimal)
    raw = view.GetVisibleEntities2(None, VIEW_EDGE)
    edges = []
    for e in raw or ():
        edge = typed(e, "IEdge")
        s = typed(edge.GetStartVertex(), "IVertex").GetPoint()
        t = typed(edge.GetEndVertex(), "IVertex").GetPoint()
        s_mm, t_mm = [v / MM for v in s], [v / MM for v in t]
        edges.append((edge, s_mm, t_mm))
    # the two edges of the end faces seen in the front view: constant x (0 or 39), running along y
    ends = [
        (edge, s[0])
        for edge, s, t in edges
        if abs(s[0] - t[0]) < 1e-6 and abs(s[1] - t[1]) > 1e-6 and abs(s[0]) < 1e-6 or abs(s[0] - 39) < 1e-6 and abs(s[0] - t[0]) < 1e-6 and abs(s[1] - t[1]) > 1e-6
    ]
    print("visible edges:", len(edges), "end edges at x =", sorted(round(x, 6) for _, x in ends))
    if len(ends) != 2:
        raise RuntimeError("expected two end edges")
    doc.ClearSelection2(True)
    print("select:", view.SelectEntity(ends[0][0], False), view.SelectEntity(ends[1][0], True))
    dd = doc.AddDimension2(0.15, 0.16, 0)
    if dd is None:
        raise RuntimeError("AddDimension2 failed")
    dim = typed(typed(dd, "IDisplayDimension").GetDimension2(0), "IDimension")
    tol = typed(dim.Tolerance, "IDimensionTolerance")
    tol.Type = SW_TOL_BILAT
    print("SetValues:", tol.SetValues(0.0, 0.10 * MM))  # SetValues2 returns False on drawing dimensions
    doc.EditRebuild3()
    print(f"dimension {dim.FullName}: value {dim.SystemValue / MM:g} mm, tol type {tol.Type},"
          f" max {tol.GetMaxValue() / MM:+g}, min {tol.GetMinValue() / MM:+g}")
    out = str(FOLDER / "Block_C.SLDDRW")
    save_as(doc, out)
    print("saved", out)


if __name__ == "__main__":
    main()
