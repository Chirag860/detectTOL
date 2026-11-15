# Diameter plan, Step 3 report: holes, shafts and pins in the app

2026-11-15. Windows 11, SOLIDWORKS 2026 (rev 34.4.1), conda env `detecttol`. Branch `feat/diameters`.
Started on the maintainer's "Yes, start Step 3".

## Done

- **Two modes**, switched at the top of *2. Choose the requirement*:
  - **Gap between two faces** works as before. Pins and positions are now used automatically (Step 2).
  - **Fit check (hole + shaft)**:
    - click the hole and the shaft or pin in the 3D view, or pick them from two lists;
    - each list entry shows Ø and any diameter, fit or position tolerance found, e.g. `Housing:0  hole dia 20  [dia 20 H7 +0.021/+0]`;
    - either half-face of a cylinder selects the whole hole or shaft;
    - the limits become *smallest / largest clearance*.
- **3D view**: in fit mode the chosen hole is blue and the shaft orange (all their faces); everything else is grey.
- **Table**:
  - **fit mode**: two rows, hole +1 and shaft −1, with where each tolerance came from. A diameter without a tolerance is a yellow cell to fill in, or filled from the general class.
  - **gap mode**: pin-float rows ("hole 0 / pin 0", with the formula) and position rows. Diameters the chain needed but the model did not tolerance get their own editable rows.
  - A float row is white only when both diameters came from the model.
- **Verdict** in fit mode names the fit, e.g. *"Clearance fit, always meets the requirement: clearance 0.007 to 0.041 mm."*
- **Clicks that don't fit the mode** show a notice instead of an error. Example: a round face in gap mode gives *"Shaft:0 (pin dia 20) is round: a gap is measured between flat faces. Use the Fit check for a hole and a shaft."*
- **Project file** (`.dtol`) also stores the mode, hole and shaft.
- **Time limit**: reading a model gives up after 3 minutes with a message, instead of spinning for ever (see *Checked in the browser*).
- **Fix**: face names with underscores lost them in the face labels (`Plate_1 … Plate_2` was shown as italics); Markdown is now escaped.

## Checked in the browser (the app on this PC, driven like a user)

| Model | What I did | Result |
|---|---|---|
| `Fit_Test.SLDASM` (through SolidWorks) | Fit check: Housing bore, Shaft | Lists show H7 and g6 read from SolidWorks. Table +0.021/0 and −0.007/−0.020. Verdict *Clearance fit … 0.007 to 0.041 mm*; RSS 0.00276 ppm; contributors 61.8 % / 38.2 % |
| `Pin_Test.SLDASM` (through SolidWorks) | Gap: Plate_1:3 → Plate_2:3 (datum B faces) | Chain Plate_1 → Pin → Plate_2; positions ±0.05 from SolidWorks, floats ±0.135; worst case −0.37 mm; floats 36.5 % each, positions 13.5 % each (= 0.135/0.37 and 0.05/0.37) |
| `Pin_Test_geometry_AP214.step` (no tolerances) | Same faces, class m | Three diameter rows (IS 2102-m), floats ±0.25 = (6.4 − 5.9)/2, editable |
| `Fit_Test_geometry_AP214.step` | Clicked the shaft in gap mode, then in fit mode | Notice in gap mode; in fit mode the shaft is chosen, orange, rest grey |

**One hang:** the first time `Pin_Test.SLDASM` was opened, SolidWorks (started by the app) opened the assembly and then stopped responding to the read for more than 3 minutes. There was no dialog. I stopped that SolidWorks process (it held only the read-only test assembly) and couldn't reproduce the hang: cold reads from the command line, from a worker thread and from the app all took 10–40 s. That is why the 3-minute time limit was added. **Cause unknown**; it may be linked to the stray SolidWorks processes left by the hand-check session.

## Test results

```
469 passed, 4 skipped in 24.23s     (the 4 skipped = live SolidWorks tests; they passed in Step 2)
ruff check / format: clean (98 files)
mypy (core, strict): Success: no issues found in 8 source files
```

New: `tests/app/test_state_fit.py`. It covers:
- picking hole and shaft by either half-face;
- fit rows and their sources;
- typed fit values giving a clearance fit;
- missing diameters;
- refused clicks;
- the project round trip;
- the pin chain with diameter rows in gap mode.

The page code (`app/ui.py`) has no automated test; it was checked in the browser as above.

## Known limitations / open risks

- A hole hidden inside its part can't be seen to click in 3D. Pick it from the **Hole** list, which is always complete.
- A shaft or pin shows as "pin" in the labels (`Shaft:0 (pin dia 20)`); the word means "outside cylinder".
- The cause of the one SolidWorks hang is unknown (above).
- The user guide and screenshots are not updated yet: that is Step 4.

## Items needing your review

1. Try the Fit check on one of your own assemblies with a fit, and say what is unclear on the page.
2. The open Step 2 questions still stand: the pin-float model (A39), checking the fit letters against your IS 919 copy, and one fit and MMC position set by hand in SolidWorks.

## Next (Step 4 of the plan)

- User guide: *how to put diameters, fits and positions in DimXpert*, the Fit check, pins in a chain, with screenshots.
- README check, validation run on the examples (and your part, if you have one).
