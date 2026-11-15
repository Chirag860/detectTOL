# Diameter plan, Step 4 report: user guide and validation

2026-11-15. Windows 11, SOLIDWORKS 2026 (rev 34.4.1), conda env `detecttol`. Branch `feat/diameters`.
Started on the maintainer's "Yes, start Step 4". This is the last step of the diameter plan.

## Done

- **`docs/USER_GUIDE.md`**:
  - *Holes, shafts and pins*: how to put diameters, fit classes, datums and a position (with Ⓜ) in DimXpert, and which fit classes are supported;
  - *Fit check: a hole and a shaft*;
  - *Pins in holes (gap mode)*: what the float, position and diameter rows mean, and when to trust the worst case;
  - six new troubleshooting entries;
  - limits brought up to date;
  - three new screenshots, taken in the app on the SolidWorks test files: `docs/guides/img/app-5-fit.jpg`, `app-6-fit-result.jpg`, `app-7-pin-chain.jpg`.
- **README**: the app table mentions the Fit check (the usage section and limits were updated in Step 2).
- **App**: typing a hole or shaft name (either half-face, e.g. `Housing:0`) now chooses it, like the face lists already did. Found while taking the screenshots.
- **`validation/verify_diameters.py`**: an independent check (standard library only, no detectTOL imports), in the style of `verify_golden.py`; results below.
- DECISIONS D80: the 3-minute limit for reading a model.

## Validation

**Your own models:** the folder `Desktop\detectTOL_SW_test` holds a copy of the first test assembly (blocks in a frame), with no holes or fits. So validation used the diameter test files. A real part of yours with a fit is still the best next check.

### 1. Golden values, recomputed independently

16 of 16 agree: fit limits and kinds, the IS 919 spot values, pin float, positions at RFS and MMC, pin-chain worst case and σ, class-m float. The existing `verify_golden.py` still confirms 86 of 86.

### 2. The fit table against the ISO 286-1 formulae (plausibility)

The extracted table was compared with the standard's formulae for the fundamental deviations, evaluated at the geometric mean of each size step. The printed table is rounded by rules this script does not reproduce, so this is not a verification. It is an independent sign that the website's numbers are the ISO numbers.

| Letter | Largest difference table − formula | Verdict |
|---|---|---|
| d, e, f, g | 4.6, 2.8, 0.9, 1.0 µm | consistent (within rounding) |
| k (grades 4–7) | 0.7 µm | consistent |
| m | 0 except up to 3 mm | consistent; m up to 3 mm (table +2, formula 4) is a known departure in the printed table (m6 = +8/+2) |
| n | 2.0 µm; up to 3 mm the table has +4, the formula 6 | **needs your check** (I believe n6 up to 3 mm is +10/+4) |
| c | up to 40 mm the table is 8–15 µm larger than the formula | **needs your check** (I believe c11 at 10–18 mm is −95/−205) |
| p, r, s | not compared (their formulae are ranges) | **needs your check** |

### 3. The command line on the example files (real output)

| Command | Result | By hand |
|---|---|---|
| `fit-cad Fit_Test.SLDASM --hole Housing:0 --shaft Shaft:0` | *clearance fit; clearance from 0.007 to 0.041 mm*; σ 0.00411636 | 0.007 / 0.041; σ 0.0041164 |
| `analyze-cad Pin_Test.SLDASM --from Plate_1:3 --to Plate_2:3 --lsl -0.5 --usl 0.5` | chain Plate_1 → Pin → Plate_2; range [−0.37, 0.37]; σ 0.112719; notes say the datums came from the frame text | ±0.37; σ 0.1127189 |
| `fit-cad Fit_Test_geometry_AP214.step … --general m` | *transition fit; −0.4 to 0.4 mm* | ±0.2 each (IS 2102-m) |

### 4. The app

The app was driven like a user on both SolidWorks assemblies (see the Step 3 report and the screenshots in the guide). Pin_Test with limits ±0.5 gives *"Always fits: … between −0.37 and 0.37 mm"*.

RSS still predicts 9.17 ppm there, because it treats the total as normal and so has tails beyond the worst case. The guide now explains that the worst case is the answer then.

## Test results

```
469 passed, 4 skipped in 21.79s     (the 4 skipped = live SolidWorks tests; passed in Step 2)
ruff check / format: clean (100 files)
mypy (core, strict): Success: no issues found in 8 source files
validation/verify_diameters.py: all golden values agree; 6 table steps NEEDS HUMAN CHECK (c, n)
validation/verify_golden.py: 86 of 86 golden values confirmed independently
```

## The diameter plan, all four steps

| Step | Result |
|---|---|
| 1. Feasibility | SolidWorks gives diameters, fits, datums, positions and round faces. Fits and MMC set through the API land only in the display/frame; the reader handles both (phase-dia-1) |
| 2. Engine | Fit check, pins in chains, positions with MMC bonus, more fit letters (flagged); reviewer found 10 issues, all fixed (phase-dia-2) |
| 3. App | Fit check mode, clickable round faces, pin/position/diameter rows, 3-minute read limit (phase-dia-3) |
| 4. Guide and validation | This report |

## Items needing your review

1. **Fit letters:** check against your IS 919 copy, especially the values the script flags (c up to 40 mm, n up to 3 mm) and p, r, s. Quick checks: Ø20 g6 = −0.007/−0.020, Ø25 k6 = +0.015/+0.002, Ø50 p6 = +0.042/+0.026.
2. **Pin float model (A39):** keep "anywhere in the clearance", or model a pin pushed to one side?
3. **One real part** with a fit and an MMC position set by hand in SolidWorks. It confirms the reader takes them from DimXpert directly, and it is the real-model validation this plan still lacks.
4. **The branch is not committed:** everything is on `feat/diameters` in the working tree. Commit and a PR are your call.

## Not in this plan (later, if wanted)

- **3D stacks from CAD** (tilted parts, angles): a separate plan, as agreed.
- Holes K to ZC (need a trustworthy Δ table).
- Hole patterns, composite positions, datum shift; round requirement faces (e.g. the gap from a hole axis to a face).
