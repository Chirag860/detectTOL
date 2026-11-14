# App plan, Step 3 report: the local browser app

2026-11-14. Windows 11, SOLIDWORKS 2026 (rev 34.4.1), conda env, Python 3.12, NiceGUI 4.0.0 (conda-forge), pythonocc-core 8.0.1.2.

## Done

- **`detecttol app`** opens a page at `http://127.0.0.1:8765`, on this PC only; nothing is uploaded. Four steps on one page:
  1. **Open a model.** A folder browser shows folders, `.SLDASM`, `.step`, `.stp` and `.dtol` files, plus checkboxes for the drawings in the folder. SolidWorks reading runs in the background with a progress message; notes (for example a duplicated drawing dimension) appear as pop-ups.
  2. **Choose the requirement.**
     - Click face 1 and face 2 in the **3D view**: every face is its own object named `PART:FACE`, face 1 blue, face 2 orange, chain parts in distinct colours, other parts grey.
     - Or pick them from **lists**, where each entry shows its direction, position and the tolerances found on it, e.g. `Block_C:2 faces +X at x = 99 [39 +0.1/+0]`.
     - Also set the limits, the drawing standard (IS / ISO / ASME) and the general tolerance class.
  3. **The chain** is a table of part, faces, nominal, upper, lower, sign and where the tolerance comes from:
     - **DimXpert**, **drawing** or **STEP PMI**: read from the model;
     - **IS 2102-m**: general tolerance, yellow, editable;
     - **you**: typed in the app;
     - **missing**: yellow and empty, must be filled before Analyse is enabled.

     Flatness rows say what they really add under the chosen standard. Notes about combined dimensions are shown.
  4. **Result:**
     - a plain-words verdict: *Always fits* / *Can fail in the worst case: the value can reach −0.1 mm, statistically about 1 in 28 million assemblies* / *Does not fit even at nominal size*;
     - RSS (ppm, Cpk) and Monte Carlo (with the "0 failures is not 0 risk" bound);
     - the biggest contributors as bars, and the histogram;
     - every warning, and **Download report (HTML)**.
- **Save project** writes `<model>.dtol` (JSON) next to the model. Opening it re-reads the model, so CAD changes are picked up.
- **New modules:**
  - `detecttol.cad.mesh`: OCCT face meshes, in the reader's exact face order (`step_reader.placed_part_faces`, factored out of `read_step`);
  - `detecttol.app.state`: all page logic, plain Python and tested;
  - `detecttol.app.ui`: the NiceGUI page, display and clicks only.
- **Engine additions:**
  - `build_cad_stack` takes `overrides`, your own values for dimensions with no CAD tolerance;
  - `placeholder_missing` lists them in `needs_value`, and `analyze()` refuses while any remain;
  - the SolidWorks reader initialises COM per thread, because the app reads in a worker thread.
- **Spec and packaging:**
  - root.md §1 non-goals and §2 stack revised as approved: a local app and SolidWorks via its API are now in scope, and parsing native formats ourselves stays out;
  - optional extras `detecttol[app]` (nicegui) and `detecttol[solidworks]` (pywin32);
  - DECISIONS D69–D71; README section "The app".

## Checked in the browser (Claude's browser pane, driving the real app)

| Step | Seen |
|---|---|
| Open `examples/solidworks/Tolerance_Test.SLDASM` with `Block_C.SLDDRW` | "4 parts; tolerances found (SolidWorks 34.4.1): 4 dimensions, 1 flatness"; pop-up "drawing RD1 … repeats DimXpert Width2@Width1(39); used once" |
| 3D view | 4 parts in distinct colours; a click on Block_C's top set face 1 = `Block_C:3`, normal +Y, the clicked face |
| Lists | Block_C:2 → Frame:4 picked; chain Block_C → Block_B → Block_A → Frame, nominal 1 mm, every row "DimXpert Width2@…", flatness row |
| Analyse (IS) | "Always fits: even in the worst case the value stays between 0.54 and 1.36 mm"; Cpk 4.047; same as the CLI and the hand value |
| STEP copy (no tolerances) + IS 2102-m | all rows yellow from the general class; "Can fail in the worst case: the value can reach −0.1 mm … about 1 in 28,096,580"; worst case [−0.1, 2.1], 0.0356 ppm, as the CLI |

## Test results

Real output of the final run:

```
418 passed, 2 skipped in 18.71s            (the 2 skipped = live SolidWorks tests)
DETECTTOL_SOLIDWORKS=1 tests/solidworks/test_live.py: 2 passed in 22.17s
ruff check: All checks passed!   ruff format --check: 115 files already formatted
mypy (core, strict): Success: no issues found in 8 source files
coverage: app/state 87 %, cad/mesh 95 %, app/ui 0 % (page tested by hand above), TOTAL 83 %
```

- 8 new tests in `tests/app/test_state.py`:
  - pick order and chain rows;
  - analysis and verdict: W 1.1 → [−0.1, 2.1], "risk";
  - your value replacing the general one: W 0.95 → "ok";
  - empty rows blocking analysis, then filled: W 0.4;
  - nominal failure and error paths;
  - project save and reopen;
  - meshes keeping the reader's face indices;
  - the flatness row: +/−0.01 under IS, nothing under ASME.
- No existing expected value changed. TOTAL coverage fell from 90 % to 83 % because the page module has no automated tests.

## Known limitations / open risks

- **The page has no automated test.** It was driven by hand in the browser (above). A NiceGUI `User` test would need the page restructured as a `main_file`; that's a later improvement.
- **Small faces are hard to click in 3D.** For example, the faces either side of a 1 mm gap in a 110 mm assembly are hidden from most angles. The lists are the reliable way to pick them; the view only rotates and zooms with the mouse, and there's no "section" or "hide part" yet.
- **The folder browser is a simple list**, not the Windows file dialog. NiceGUI's native-window mode would give a real dialog, but needs pywebview (Step 4 decision).
- **Large assemblies:** one 3D object per face. This is fine for tens of parts and untested for hundreds; meshes are generated each time a model is opened.
- **One analysis at a time per browser tab.** SolidWorks reading takes ~20 s and the page waits for it.
- The report download uses the browser's download folder. Save project writes next to the model, and fails visibly if that folder is read-only.

## Items needing your review

1. Run `detecttol app`, after `conda activate detecttol` and `cd` to the repo, and try one of **your own** assemblies. Tell me what's confusing, missing or wrong. This is the step that most needs an engineer's eyes.
2. D69 defaults (IS, class m, gap ≥ 0): OK for your work?
3. Still open from Step 1: ISO 2768-m saved on `Frame.SLDPRT`.

## Proposed next step (Step 4 of the plan)

One-click install for Windows:
- a Start-menu/desktop shortcut "detectTOL" that opens the app;
- a decision between a conda `constructor` installer and a one-time setup `.bat`;
- possibly a native window with a real file dialog (pywebview);
- `docs/USER_GUIDE.md` with screenshots, plus the DimXpert how-to.

**Waiting for your go-ahead.**
