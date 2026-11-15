# Diameter plan, Step 2 report: the engine (fit check, pin in a hole, IS 919 fit letters)

2026-11-14. Windows 11, SOLIDWORKS 2026 (rev 34.4.1), conda env `detecttol`. Branch `feat/diameters`.
Step 2 was started on the maintainer's "Yes, start Step 2", relayed from the parent session. The hand check from Step 1 was skipped; see *Items needing your review*.

## Done

- **Round features** (`src/detecttol/cad/round.py`): a hole or pin is one cylindrical surface of one part.
  - STEP's two half-faces are grouped into one feature (A42).
  - STEP faces now carry axis, radius and hole/pin (`FaceInfo.cylinder`).
  - The synthetic STEP writer can drill holes.
- **Fit check**:
  - clearance = hole Ø − shaft Ø, with worst case, RSS and Monte Carlo;
  - a plain verdict: *clearance / transition / interference fit, clearance from … to … mm*;
  - API: `build_fit_check`; CLI: `detecttol fit-cad … --hole PART:FACE --shaft PART:FACE`.
- **Pin in a hole inside a chain** (`cad/chain.py`):
  - a pin of one part in a hole of another is a contact when its axis is across the stack direction;
  - it adds the **float** `0 ± (D_max − d_min)/2`, uniform (A39);
  - inside a part, a hole's **position** links its datum plane to the hole axis: `± T/2`, or `± (T + B)/2` with the MMC/LMC bonus, reusing `gdt.models.Position` (A41).
- **Missing diameter tolerances** are filled like missing dimensions: your value, the general class (IS 2102), or an empty cell for the app's table (D79).
- **IS 919 / ISO 286 fit letters**:
  - shafts **c d e f g** and **k m n p r s**, holes **C D E F G** (plus H, h, JS, js as before);
  - extracted by script from a cited table, checked against that site's own hole table, flagged `TABLE_NOT_VERIFIED` (A40);
  - holes **K to ZC are refused**: the only source at hand is wrong there.
- **SolidWorks reader**:
  - DimXpert diameters, datums and positions;
  - fit codes from DimXpert or else the dimension's display, which also fixes the same gap for widths (D77);
  - MMC and datum letters from DimXpert or else the frame's text, with a note in the report (D78);
  - round faces matched to the STEP copy by part, radius and axis.
- **CLI**: `detecttol faces` lists holes and pins under `round:`, with Ø, axis, tolerance and position; `fit-cad` is new; `analyze-cad` uses pins and positions automatically.
- **Test files kept**: SolidWorks' STEP exports of the two test assemblies, `examples/solidworks/fits/*_geometry_AP214.step`, so the tests run without SolidWorks.
- **Docs**: ASSUMPTIONS A39–A43, DECISIONS D74–D79.

## Results on the SolidWorks test files (read live through SOLIDWORKS 2026)

| Case | detectTOL | By hand |
|---|---|---|
| `Fit_Test`: Ø20 H7 bore / Ø20 g6 shaft (fit codes read from the display) | H7 = +0.021/0, g6 = −0.007/−0.020; **clearance fit, 0.007 to 0.041 mm**; RSS 1–σ 0.004116 | 20.000 − 19.993 = 0.007; 20.021 − 19.980 = 0.041; σ = √(0.0035² + 0.002167²) = 0.004116 |
| `Pin_Test`: Plate_1 datum B → Plate_2 datum B through hole, pin, hole (datums A, B, C from the frame text; RFS) | chain Plate_1 → Pin → Plate_2; worst case **±0.37**; σ 0.112719 | 0.05 + 0.135 + 0.135 + 0.05 = 0.37; √(2·(0.05/3)² + 2·(0.135/√3)²) = 0.112719 |
| Same chain with MMC on both positions (synthetic) | worst case ±0.47 | bonus 0.1 each: 0.1 + 0.135 + 0.135 + 0.1 |

## Test results

Real output of the final run:

```
463 passed, 4 skipped in 30.16s     (the 4 skipped = live SolidWorks tests)
DETECTTOL_SOLIDWORKS=1 tests/solidworks/test_live.py: 4 passed in 88.24s
ruff check src tests: All checks passed!   ruff format: 97 files formatted
mypy (core, strict): Success: no issues found in 8 source files
```

New tests:
- `tests/cad/test_round.py`: grouping, fit kinds, float, position at RFS and MMC, pin chains, missing diameters, CLI.
- `tests/solidworks/test_resolve_round.py`: a hand-made SolidWorks read-out on the real STEP exports.
- 14 fit-letter golden values in `tests/standards/test_iso286.py`.
- 2 live tests.

## Reviewer subagent

An independent subagent:
- re-derived all 27 new golden values by hand and found **no disagreement**;
- parsed the source tables itself and found **0 mismatches** in 400 cells (all size-step boundaries included);
- confirmed the fit definitions, the position linearisation and the coaxial-contact geometry.

It reported 10 findings, all fixed, with regression tests where testable without SolidWorks:

| # | Finding | Fix |
|---|---|---|
| 1 (error) | A display showing hole *and* shaft fits on a feature of unknown kind, or a failed `GetPlusAndMinusTolerance`, gave a silent ±0 | Treated as missing, with a note (`reader._tolerance`) |
| 2 (error) | A fit letter of the wrong case (g6 on a hole) was accepted | Refused as missing, with a note; test |
| 3 | A stale DimXpert fit code could override real ± values | DimXpert's code is used only when its tolerance type is a fit |
| 4 | Positions of parts *off* the chain were converted (spurious errors / filled diameters) | Only parts on the path; test |
| 5 | A position with no datum across the stack was dropped silently | Note in the report; test |
| 6 | A pin in two bores of one part (clevis) gave "several paths" | One contact per part pair; the tighter float is used, with a note; test |
| 7 | A loose rod through a large opening counted as locating | Nominal clearance must be ≤ 5 % of the hole diameter (A42); test |
| 8 | A39 called the statistics conservative even for a biased (one-sided) float, where they are not | A39 and the docstring corrected: conservative only for zero-mean scatter; rely on worst case otherwise |
| 9 | Half faces listed out of axial order stayed as separate features | Faces sorted along the axis before merging; test |
| 10 | A datum modifier in the frame text (e.g. B Ⓜ) was read as MMC on the tolerance | Only the tolerance's own text sets MMC; datum modifiers are stripped and noted (datum shift not modelled) |

## Known limitations / open risks

- **Pin float model (A39):** uniform over the largest clearance. Worst case is exact. The statistics are conservative only when the pin can sit anywhere: if assembly pushes parts to one side, RSS and Monte Carlo can understate the shift, so rely on the worst case there.
- **A pin in two bores of one part** uses the tighter float and the first bore's position only (noted in the report).
- **Fit table (A40)** comes from a website, not from IS 919 itself. It is flagged in every report until checked.
- **Hand-made fits and positions** in SolidWorks are untested. If SolidWorks fills its own data, the reader uses it (expected); if not, the display and frame-text fallbacks apply.
- **Not modelled:**
  - holes K to ZC;
  - a pin pressed into one part and loose in the other: it works, as two floats, but the press fit's float should be zero (the fit check shows interference);
  - patterns of holes, composite positions, datum shift;
  - round requirement faces: the two requirement faces must still be flat.
- The app page (Step 3) does not show round features yet.

## Items needing your review

1. **A39 (pin float):** keep "uniform over the largest clearance", or model it another way (actual clearance per sample, or one-sided)?
2. **A40:** check the fit letters you use against your IS 919 (Part 1) copy. Ø20 g6 = −0.007/−0.020, Ø25 k6 = +0.015/+0.002 and Ø50 p6 = +0.042/+0.026 are quick checks.
3. When convenient, one part where you set a fit and an MMC position **by hand** in SolidWorks, to confirm the reader takes them from DimXpert directly.

## Next (Step 3 of the plan)

The app:
- round faces clickable, with Ø shown in the face lists;
- a **Fit check** mode: click a hole and a shaft, get the verdict;
- pin and position rows in the chain table.
