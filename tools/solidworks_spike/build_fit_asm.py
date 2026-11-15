# ruff: noqa
# Diameter feasibility spike (docs/reports/phase-dia-1.md). Not product code; needs SOLIDWORKS + pywin32.
"""Assemblies for the diameter test parts (build_fits.py).

Fit_Test.SLDASM: Housing fixed; Shaft concentric with the bore, its z = 0 end flush with
    the housing's z = 0 face.
Pin_Test.SLDASM: Plate_1 fixed; Plate_2 on top of it (z = 10); Pin concentric with both
    holes, its z = 0 end flush with Plate_1's z = 0 face; the plates' y = 0 faces flush.
    The requirement to check later: Plate_2's x = 60 face against Plate_1's (nominal 0).
"""

from __future__ import annotations

import sys
from pathlib import Path

from build_asm import faces_of
from swlib import MM, SW_DOC_ASSEMBLY, connect, new_doc, save_as, typed

FOLDER = Path(sys.argv[1])
COINCIDENT, CONCENTRIC = 0, 1
ALIGNED, ANTI, CLOSEST = 0, 1, 2


def cylinder(comp):
    cands = [f for f, _n, _b in faces_of(comp) if typed(f.GetSurface(), "ISurface").IsCylinder()]
    if len(cands) != 1:
        raise RuntimeError(f"{comp.Name2}: {len(cands)} cylindrical faces")
    return cands[0]


def plane(comp, normal, where=lambda b: True):
    cands = [f for f, n, b in faces_of(comp) if n == normal and where(b)]
    if len(cands) != 1:
        raise RuntimeError(f"{comp.Name2}: {len(cands)} faces with normal {normal}")
    return cands[0]


def mate(asm, doc, kind, align, f1, f2, label):
    doc.ClearSelection2(True)
    typed(f1, "IEntity").Select4(False, None)
    typed(f2, "IEntity").Select4(True, None)
    result = asm.AddMate5(kind, align, False, 0, 0, 0, 0, 0, 0, 0, 0, False, False, 0, 0)
    obj, err = result if isinstance(result, tuple) else (result, None)
    print(f"  mate {label}: {'ok' if obj is not None else 'FAILED'} (err {err})")
    if obj is None:
        raise RuntimeError(f"mate {label} failed")
    doc.ClearSelection2(True)


def add(sw, asm, name, at):
    path = str(FOLDER / f"{name}.SLDPRT")
    sw.OpenDoc6(path, 1, 1, "", 0, 0)
    comp = asm.AddComponent5(path, 0, "", False, "", *(v * MM for v in at))
    if comp is None:
        raise RuntimeError(f"AddComponent5 failed for {path}")
    return typed(comp, "IComponent2")


def fix(asm, doc, comp):
    doc.ClearSelection2(True)
    comp.Select4(False, None, False)
    asm.FixComponent()
    doc.ClearSelection2(True)


def fit_test(sw):
    doc = new_doc(sw, SW_DOC_ASSEMBLY)
    asm = typed(doc._oleobj_, "IAssemblyDoc")
    housing = add(sw, asm, "Housing", (20, 20, 10))
    shaft = add(sw, asm, "Shaft", (20, 20, 60))
    sw.ActivateDoc3(doc.GetTitle(), False, 0, 0)
    fix(asm, doc, housing)
    mate(asm, doc, CONCENTRIC, CLOSEST, cylinder(shaft), cylinder(housing), "shaft in bore")
    mate(asm, doc, COINCIDENT, ALIGNED, plane(shaft, (0.0, 0.0, -1.0)), plane(housing, (0.0, 0.0, -1.0)), "ends flush")
    doc.EditRebuild3()
    save_as(doc, str(FOLDER / "Fit_Test.SLDASM"))
    print("saved Fit_Test.SLDASM")
    sw.CloseDoc(doc.GetTitle())


def pin_test(sw):
    doc = new_doc(sw, SW_DOC_ASSEMBLY)
    asm = typed(doc._oleobj_, "IAssemblyDoc")
    p1 = add(sw, asm, "Plate_1", (30, 10, 5))
    p2 = add(sw, asm, "Plate_2", (30, 10, 25))
    pin = add(sw, asm, "Pin", (30, 10, 60))
    sw.ActivateDoc3(doc.GetTitle(), False, 0, 0)
    fix(asm, doc, p1)
    mate(asm, doc, COINCIDENT, ANTI, plane(p2, (0.0, 0.0, -1.0)), plane(p1, (0.0, 0.0, 1.0)), "Plate_2 on Plate_1")
    mate(asm, doc, CONCENTRIC, CLOSEST, cylinder(pin), cylinder(p1), "pin in Plate_1")
    mate(asm, doc, CONCENTRIC, CLOSEST, cylinder(pin), cylinder(p2), "pin in Plate_2")
    mate(asm, doc, COINCIDENT, ALIGNED, plane(pin, (0.0, 0.0, -1.0)), plane(p1, (0.0, 0.0, -1.0)), "pin end flush")
    mate(asm, doc, COINCIDENT, ALIGNED, plane(p2, (0.0, -1.0, 0.0)), plane(p1, (0.0, -1.0, 0.0)), "y = 0 faces flush")
    doc.EditRebuild3()
    x1 = [b for f, n, b in faces_of(p1) if n == (1.0, 0.0, 0.0)][0][0]
    x2 = [b for f, n, b in faces_of(p2) if n == (1.0, 0.0, 0.0)][0][0]
    print(f"Plate_2 x = 60 face at {x2:.6f}, Plate_1 at {x1:.6f}: offset {x2 - x1:.6f} mm")
    save_as(doc, str(FOLDER / "Pin_Test.SLDASM"))
    print("saved Pin_Test.SLDASM")
    sw.CloseDoc(doc.GetTitle())


def main() -> None:
    sw = connect(visible=True)
    fit_test(sw)
    pin_test(sw)


if __name__ == "__main__":
    main()
