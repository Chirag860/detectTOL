# ruff: noqa
# Step 1 feasibility spike (docs/reports/phase-app-1.md). Not product code; needs SOLIDWORKS + pywin32.
"""Match every SolidWorks DimXpert face (assembly coords) to a STEP face of the geometry copy."""
import json, math, sys
from detecttol.cad.step_reader import read_step

d = json.load(open(sys.argv[1]))
model = read_step(sys.argv[2])
faces = [(p.name, f) for p in model.parts for f in p.faces if f.is_planar]
ok = miss = 0
for c in d["components"]:
    part = c["part_file"].rsplit(".", 1)[0]
    for a in c["annotations"]:
        for sw in a["faces"]:
            hits = [(name, f.index) for name, f in faces
                    if name == part and max(abs(x - y) for x, y in zip(f.centroid, sw["centre_mm"])) < 1e-6
                    and sum(x * y for x, y in zip(f.normal, sw["normal"])) > 1 - 1e-9]
            ok += len(hits) == 1; miss += len(hits) != 1
            print(f"{a['name']:24} {part:8} centre {sw['centre_mm']} normal {sw['normal']} -> {hits}")
print(f"matched {ok}, unmatched/ambiguous {miss}")
