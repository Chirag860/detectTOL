# ruff: noqa
# Step 1 feasibility spike (docs/reports/phase-app-1.md). Not product code; needs SOLIDWORKS + pywin32.
"""Turn the SolidWorks read-out into a schema-v3 stack file (what Step 2 will automate)."""
import json, sys, yaml
from detecttol.cad.step_reader import read_step

d = json.load(open(sys.argv[1])); step = sys.argv[2]; out = sys.argv[3]
model = read_step(step)
def sel(part, sw):
    for p in model.parts:
        if p.name != part: continue
        for f in p.faces:
            if f.is_planar and max(abs(a - b) for a, b in zip(f.centroid, sw["centre_mm"])) < 1e-6 and sum(a * b for a, b in zip(f.normal, sw["normal"])) > 1 - 1e-9:
                return {"part": part, "face": f.index, "centroid": [round(v, 9) for v in f.centroid], "normal": [round(v, 9) + 0.0 for v in f.normal]}
    raise KeyError(part)
anns = []
for c in d["components"]:
    part = c["part_file"].rsplit(".", 1)[0]
    for a in c["annotations"]:
        if a["type"] != "Width": continue
        f0, f1 = (sel(part, f) for f in a["faces"])
        anns.append({"id": f"{part}_width", "kind": "dimension", "from": f0, "to": f1,
                     "upper_tol": a["upper_mm"], "lower_tol": a["lower_mm"], "nominal": a["nominal_mm"]})
frame = next(c for c in d["components"] if c["part_file"].startswith("Frame"))["annotations"][0]["faces"]
blockc = next(c for c in d["components"] if c["part_file"].startswith("Block_C"))["annotations"][0]["faces"]
req_from = sel("Block_C", next(f for f in blockc if f["normal"][0] > 0))
req_to = sel("Frame", next(f for f in frame if f["normal"][0] < 0))
doc = {"schema_version": 3, "units": "mm", "name": "solidworks_tolerance_test", "standard": "is",
       "step_file": step, "requirement": {"description": "gap Block_C to frame inner wall (tolerances read from SolidWorks DimXpert)",
       "from": req_from, "to": req_to, "lsl": 0.0}, "annotations": anns,
       "analysis": {"methods": ["worst_case", "rss", "monte_carlo"], "monte_carlo": {"n": 100000, "seed": 42}}}
yaml.safe_dump(doc, open(out, "w"), sort_keys=False)
print("wrote", out, "with", len(anns), "dimensions read from SolidWorks")
