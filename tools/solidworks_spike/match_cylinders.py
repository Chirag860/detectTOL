# ruff: noqa
# Diameter feasibility spike (docs/reports/phase-dia-1.md). Not product code.
"""Match SolidWorks cylindrical faces (readout_dia.py JSON) to STEP faces by axis and radius.

STEP splits each full cylinder into two half faces, so centroid matching cannot work. Every
STEP cylinder is reduced to (axis line, radius, axial range); a SolidWorks face matches all
STEP faces with the same radius (1e-6 mm), a coincident axis line (1e-6 mm, 1e-9 rad) and
an axial range inside the SolidWorks face's own range.
    python match_cylinders.py <readout.json> <file.step>
"""
import json, math, sys
from OCC.Core.BRepAdaptor import BRepAdaptor_Surface
from OCC.Core.GeomAbs import GeomAbs_Cylinder
from OCC.Core.STEPControl import STEPControl_Reader
from OCC.Core.TopAbs import TopAbs_FACE
from OCC.Core.TopExp import TopExp_Explorer
from OCC.Core.TopoDS import topods

data = json.load(open(sys.argv[1]))
r = STEPControl_Reader(); r.ReadFile(sys.argv[2]); r.TransferRoots(); shape = r.OneShape()
cyls = []
exp = TopExp_Explorer(shape, TopAbs_FACE)
i = 0
while exp.More():
    s = BRepAdaptor_Surface(topods.Face(exp.Current()))
    if s.GetType() == GeomAbs_Cylinder:
        c = s.Cylinder(); loc, d = c.Location(), c.Axis().Direction()
        v1, v2 = s.FirstVParameter(), s.LastVParameter()
        cyls.append({"i": i, "p": (loc.X(), loc.Y(), loc.Z()), "d": (d.X(), d.Y(), d.Z()), "r": c.Radius()})
    i += 1; exp.Next()

def line_dist(p, d, q):
    w = [q[k] - p[k] for k in range(3)]
    t = sum(w[k] * d[k] for k in range(3))
    return math.sqrt(max(sum(x * x for x in w) - t * t, 0.0))

for it in data["items"]:
    for f in it["faces"]:
        if f["surface"] != "cylinder": continue
        a = f["axis"]; n = math.sqrt(sum(x * x for x in a)); a = [x / n for x in a]
        hits = [c["i"] for c in cyls
                if abs(c["r"] - f["radius"]) <= 1e-6
                and abs(abs(sum(c["d"][k] * a[k] for k in range(3))) - 1) <= 1e-9
                and line_dist(f["axis_point"], a, c["p"]) <= 1e-6]
        print(f"{it['part']:8} {it['name']:30} R{f['radius']:g} -> STEP cylinder faces {hits}")
print(f"{len(cyls)} cylindrical STEP faces in total")
