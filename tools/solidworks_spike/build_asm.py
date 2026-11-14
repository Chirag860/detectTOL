# ruff: noqa
# Step 1 feasibility spike (docs/reports/phase-app-1.md). Not product code; needs SOLIDWORKS + pywin32.
"""Assembly Tolerance_Test.SLDASM: Frame fixed, Block_A/B/C in a row, coincident mates.

Faces are found on each component's bodies by outward normal and position (assembly
coordinates), then mated: end faces in a chain, bottoms on the frame base, fronts flush.
At the end the gap between Block_C's +X face and the frame's inner +X-side face is measured.
"""

from __future__ import annotations

import sys
from pathlib import Path

from swlib import MM, SW_DOC_ASSEMBLY, connect, new_doc, save_as, typed

FOLDER = Path(sys.argv[1])
MATE_COINCIDENT, ALIGN_CLOSEST = 0, 2


def faces_of(comp):
    out = []
    result = comp.GetBodies3(0)  # 0 = solid bodies; assembly context; returns (bodies, info)
    bodies = result[0] if isinstance(result, tuple) and len(result) == 2 and isinstance(result[0], tuple) else result
    for body in bodies or ():
        for f in typed(body, "IBody2").GetFaces() or ():
            face = typed(f, "IFace2")
            box = [v / MM for v in face.GetBox()]
            out.append((face, tuple(round(v, 6) + 0.0 for v in face.Normal), box))
    return out


def pick(comp, normal, where):
    """Face of ``comp`` with outward ``normal``; ``where(box)`` breaks ties."""
    cands = [(f, box) for f, n, box in faces_of(comp) if n == normal and where(box)]
    if len(cands) != 1:
        raise RuntimeError(f"{comp.Name2}: {len(cands)} faces match normal {normal}")
    return cands[0]


def mate(asm, doc, face1, face2, label):
    doc.ClearSelection2(True)
    ok1 = typed(face1, "IEntity").Select4(False, None)
    ok2 = typed(face2, "IEntity").Select4(True, None)
    result = asm.AddMate5(MATE_COINCIDENT, ALIGN_CLOSEST, False, 0, 0, 0, 0, 0, 0, 0, 0, False, False, 0, 0)
    mate_obj, err = result if isinstance(result, tuple) else (result, None)
    print(f"  mate {label}: select {ok1}/{ok2} -> {'ok' if mate_obj is not None else 'FAILED'} (err {err})")
    if mate_obj is None:
        raise RuntimeError(f"mate {label} failed")
    doc.ClearSelection2(True)


def main() -> None:
    sw = connect(visible=True)
    doc = new_doc(sw, SW_DOC_ASSEMBLY)
    asm = typed(doc._oleobj_, "IAssemblyDoc")
    centres = {"Frame": (50, 0, 10), "Block_A": (12.5, 2.5, 10), "Block_B": (42.5, 2.5, 10), "Block_C": (79.5, 2.5, 10)}
    comps = {}
    for name, (x, y, z) in centres.items():
        path = str(FOLDER / f"{name}.SLDPRT")
        sw.OpenDoc6(path, 1, 1, "", 0, 0)  # part must be loaded before AddComponent5
        comp = asm.AddComponent5(path, 0, "", False, "", x * MM, y * MM, z * MM)
        if comp is None:
            raise RuntimeError(f"AddComponent5 failed for {path}")
        comps[name] = typed(comp, "IComponent2")
        print("added", comps[name].Name2)
    sw.ActivateDoc3(doc.GetTitle(), False, 0, 0)
    doc.ClearSelection2(True)
    typed(comps["Frame"], "IComponent2").Select4(False, None, False)
    asm.FixComponent()
    doc.ClearSelection2(True)

    fr = comps["Frame"]
    inner_left, _ = pick(fr, (1.0, 0.0, 0.0), lambda b: abs(b[0]) < 1e-6 and b[4] > 0)  # x = 0 wall face
    inner_right, ir_box = pick(fr, (-1.0, 0.0, 0.0), lambda b: abs(b[0] - 100) < 1e-6)
    base_top, _ = pick(fr, (0.0, 1.0, 0.0), lambda b: abs(b[1]) < 1e-6 and b[0] > -1)
    front, _ = pick(fr, (0.0, 0.0, -1.0), lambda b: True)

    previous = inner_left
    for name in ("Block_A", "Block_B", "Block_C"):
        c = comps[name]
        left, _ = pick(c, (-1.0, 0.0, 0.0), lambda b: True)
        bottom, _ = pick(c, (0.0, -1.0, 0.0), lambda b: True)
        cfront, _ = pick(c, (0.0, 0.0, -1.0), lambda b: True)
        mate(asm, doc, left, previous, f"{name} left <-> previous")
        mate(asm, doc, bottom, base_top, f"{name} bottom <-> frame base")
        mate(asm, doc, cfront, front, f"{name} front <-> frame front")
        previous, _ = pick(c, (1.0, 0.0, 0.0), lambda b: True)
    doc.EditRebuild3()

    c_right_box = pick(comps["Block_C"], (1.0, 0.0, 0.0), lambda b: True)[1]
    ir_box = pick(fr, (-1.0, 0.0, 0.0), lambda b: abs(b[0] - 100) < 1e-6)[1]
    print(f"gap Block_C +X face (x = {c_right_box[0]:.6f}) to frame inner face (x = {ir_box[0]:.6f}):"
          f" {ir_box[0] - c_right_box[0]:.6f} mm")
    out = str(FOLDER / "Tolerance_Test.SLDASM")
    save_as(doc, out)
    print("saved", out)


if __name__ == "__main__":
    main()
