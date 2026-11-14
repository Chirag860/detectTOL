# App plan, Step 2 report: one engine, two ways in (SolidWorks and STEP)

2026-11-14. Windows 11, SOLIDWORKS 2026 (rev 34.4.1), conda env, Python 3.12, pythonocc-core 8.0.1.2, pywin32.

## Done

- **`detecttol.solidworks`** (new):
  - `model.py`: plain records, no COM and no OCCT.
  - `reader.py`: the COM reader (`read_solidworks`).
  - `resolve.py`: SolidWorks faces → STEP faces → `ResolvedDimension`.

  The reader opens files read-only and never saves. It uses typed COM wrappers, reads the assembly and optional drawings, and writes the STEP geometry copy into a temporary folder. It closes only the documents it opened, and shuts SolidWorks down only if it started it. It restores the STEP setting it changes.
- **What is read** (A36):
  - DimXpert *Width* and *DistanceBetween*, with ± values or a fit code (→ IS 919 / ISO 286);
  - DimXpert flatness on one face;
  - drawing linear dimensions between two edges.

  Duplicates with the same tolerance are merged; duplicates that conflict are refused. Anything not used becomes a note, never dropped silently.
- **`detecttol.cad.cad_stack`** (new): one entry point for `.SLDASM` and `.step`. STEP semantic PMI linear dimensions go through `pmi_dimensions`.
- **Chain builder**:
  - Dimensions inside a part are combined when there's no direct one, e.g. bottom→floor + bottom→ceiling for floor→ceiling. If two combinations exist, the builder refuses and lists both.
  - A missing dimension goes to a `fill_missing` hook. Today that's the general class (`--general`); later it's the app's table.
- **Flatness on the chain** becomes GD&T under the chosen standard. The rules are from the reviewer findings below.
- **CLI**:
  - `detecttol faces model.SLDASM [-d drawing.SLDDRW]` lists faces with the tolerances found on each.
  - `detecttol analyze-cad model.SLDASM|model.step --from PART:FACE --to PART:FACE [--standard] [--general] [--lsl/--usl]` analyses a stack. No YAML anywhere.
- **Reports**: new `TOLERANCE_FROM_CAD` note, listing every tolerance's CAD origin (file, annotation name).
- **Packaging**: optional extra `detecttol[solidworks]` (pywin32, Windows only); pytest marker `solidworks`. The live tests run only with `DETECTTOL_SOLIDWORKS=1`.
- **Docs**: README section "Straight from SolidWorks (no YAML)", ASSUMPTIONS A33–A38, DECISIONS D65–D68.

## End-to-end on the real files

`detecttol analyze-cad examples/solidworks/Tolerance_Test.SLDASM -d examples/solidworks/Block_C.SLDDRW --from Block_C:2 --to Frame:4 --standard is`

- **Chain:** Block_C → Block_B → Block_A → Frame, nominal 1 mm. The drawing's 39 mm repeats the DimXpert one; it was noticed and used once.
- **Result:** mean 0.95, worst case **[0.54, 1.36]**, σ 0.0782446. Under IS, Block_B's flatness 0.02 adds ±0.01. Under ASME it's inside Block_B's width: [0.55, 1.35], the Step 1 result.
- **Time:** about 12 s for reading plus the STEP copy, with SolidWorks hidden.

## Test results

Real output of the final run:

```
410 passed, 2 skipped in 18.10s                    (the 2 skipped = live SolidWorks tests)
DETECTTOL_SOLIDWORKS=1 tests/solidworks/test_live.py: 2 passed in 22.26s
ruff check: All checks passed!   ruff format --check: 108 files already formatted
mypy (core, strict): Success: no issues found in 8 source files
coverage TOTAL 90 %; cad_stack 83 %, chain 95 %, solidworks/resolve 94 %, solidworks/model 100 %
```

- 18 new tests run without SolidWorks:
  - `tests/cad/test_cad_stack.py`: 11 tests;
  - `tests/solidworks/test_resolve.py`: 7 tests, using the Step 1 read-out as data;
  - plus 2 live tests.
- `solidworks/reader.py` shows 18 % in the coverage above because the COM code only runs in the live tests. Those exercise it fully, but coverage was measured without them.
- Two existing outputs changed:
  - the JSON schemas, for one new warning code;
  - the `faces` header gained a second line. The original first line is unchanged, because an existing test checks it.

## Golden values and who verified them

| Value | Me | Reviewer subagent |
|---|---|---|
| Combined housing: sensitivities −1/+1, mean 0.2, W 0.28, σ √0.0164/3 = 0.04268749 | ✔ | ✔ |
| Two combinations → refused | ✔ | ✔ (exactly 2 paths) |
| Housing from IS 2102-m: ±0.3, W 0.45, σ 0.1040833 | ✔ | ✔ |
| Fake PMI = golden case A: 0.2, 0.25, √0.0175/3 | ✔ | ✔ |
| All dimensions IS 2102-m: W 0.9 | ✔ | ✔ |
| SolidWorks ASME: 0.95, [0.55, 1.35], √0.055/3 = 0.07817360 | ✔ | ✔ |
| SolidWorks IS + flatness: [0.54, 1.36], √0.0551/3 = 0.07824463 | ✔ | ✔ |
| Block_A 25 h7: mean 0.9605, W 0.3105 | ✔ | ✔ |
| Block_A from IS 2102-m: W 0.5 | ✔ | ✔ |
| Tessellation centroids (square, L-shape) | ✔ | ✔ |
| Flatness after the reviewer fixes: datum face not added (W 0.28); combined location 0.29; direct size ASME 0.25 / IS 0.26 | ✔ | added after the review, so not reviewed |

**One test value corrected, and why:** golden case A's σ is written in root.md to 6 significant figures (0.0440959), but I had first compared it at 1e-6 relative (7 figures). The test now uses the exact hand expression √0.0175/3. The number itself is unchanged.

## Reviewer subagent findings and resolutions

1. All 13 values agree.
2. **A flatness on an intermediate datum face** of combined dimensions would have been added, but physically it cancels. **Fixed**: only the entry and exit faces of each part count as contacts. Covered by a test.
3. **The ASME "inside the size" exemption** must apply only to a real feature of size. **Fixed**: dimensions now carry `is_size` (DimXpert Width, PMI Size). A flatness on any other contact face, including one reached by combined dimensions, is added under every standard. Covered by a test.
4. **Combined dimensions treated as independent:** this is conservative, and is now stated in A37. The tool also prints a note when it combines: "dimension these two faces directly to tighten".
5. **Two combinations are refused rather than offered.** Kept as is: the tool never chooses (root.md rule). The app (Step 3) can show both and let you pick.

## Known limitations / open risks

- **Rotated components:** the transform order is only tested with identity rotations (A34, UNSURE). A test assembly with a rotated part is needed before relying on it.
- **Assembly structure:**
  - a part used twice is refused;
  - sub-assemblies are read part by part, but not tested;
  - lightweight or suppressed components are skipped with a note.
- **Not read yet:**
  - DimXpert position, profile and parallelism with datums;
  - sketch/feature dimensions;
  - drawing dimensions with limit or fit tolerances;
  - ISO 2768 class stored in the part (D68).
- **STEP PMI route:** works on injected PMI. Real PMI dimension reading is still unverified (phase 5).
- **Choosing faces:** the CLI picks faces by index (`PART:FACE` from `detecttol faces`). The app replaces this with clicking.

## Items needing your review

1. Try `detecttol faces` and `analyze-cad` on one of **your own** SolidWorks assemblies, with DimXpert tolerances on its parts. Tell me what's missing or wrong. Real models will show things the test model can't.
2. D66: the default requirement is gap ≥ 0 when no limit is given. OK?
3. Still open from Step 1: ISO 2768-m saved on `Frame.SLDPRT`.

## Proposed next step (Step 3 of the plan)

The local browser app (NiceGUI):
1. open an `.SLDASM` or `.step`;
2. 3D view, then click two faces;
3. the chain table, with sources and missing values pre-filled from the general class, all editable;
4. Analyse, then a plain-words verdict and a downloadable report.

It also covers saving and opening projects, and the root.md edits for the GUI non-goal. **Waiting for your go-ahead.**
