# SolidWorks feasibility spike (Step 1 of the app plan)

Throwaway scripts that proved detectTOL can read tolerances from SolidWorks 2026 through
its COM API. **Not product code** — Step 2 rewrites this properly in `src/detecttol/solidworks/`.
Results: `docs/reports/phase-app-1.md`.

Needs Windows, SOLIDWORKS (tested: 2026, rev 34.4.1) and `pywin32` in the conda env.
Run from this folder (the scripts import `swlib` from here):

| Script | Does |
|---|---|
| `build_parts.py <folder>` | Frame, Block_A/B/C with DimXpert widths (+ flatness on Block_B), read back |
| `build_asm.py <folder>` | `Tolerance_Test.SLDASM`, 9 coincident mates |
| `build_drw.py <folder>` | `Block_C.SLDDRW`, 39 mm dimension +0.10/-0.00 |
| `export_step.py <asm> <out.step> <AP>` | STEP export (AP 242 falls back to AP203 without MBD) |
| `readout.py <folder> <out.json>` | everything detectTOL would read (saved: `readout_2026-11-14.json`) |
| `match_faces.py <json> <step>` | SolidWorks faces → STEP faces (centroid + normal) |
| `to_stack.py <json> <step> <out.yaml>` | schema-v3 stack from the read-out, no hand-typed tolerances |

The generated files are in `examples/solidworks/`.
