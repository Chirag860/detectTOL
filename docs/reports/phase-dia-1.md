# Diameter plan, Step 1 report: reading diameters, fits and positions from SolidWorks

2026-11-14. Windows 11, SOLIDWORKS 2026 (rev 34.4.1), conda env `detecttol`, pywin32.
Plan approved by the maintainer on 2026-11-14 ("Approve, Steps 1–4"): diameters (fit check, and a pin in a hole inside a chain). 3D stacks are a separate decision.

## Gate: the test files read correctly

**Partly met.** Diameters, ± tolerances, datums, position values and round faces read back exactly. Two things could not be **written** through the API, so they still need one check by hand in SolidWorks (below):
- the fit code inside DimXpert;
- the position's MMC and datum links.

## Test files (`examples/solidworks/fits/`, built by script)

| Part | Feature | Entered |
|---|---|---|
| Housing | 40 × 40 × 20 block, bore Ø20 | Ø20 **H7** |
| Shaft | Ø20 × 40 | Ø20 **g6** |
| Plate_1, Plate_2 | 60 × 20 × 10 plate, hole Ø6.2 at (30, 10) | Ø6.2 ±0.05; datums A (z = 0), B (x = 0), C (y = 0); position Ø0.1 to A, B, C |
| Pin | Ø6 × 20 | Ø6 +0 / −0.02 |

| Assembly | Mates | Check |
|---|---|---|
| `Fit_Test.SLDASM` | shaft concentric with the bore, ends flush | — |
| `Pin_Test.SLDASM` | Plate_2 on Plate_1, pin concentric with both holes, y = 0 faces flush | Plate_2's x = 60 face is 0.000000 mm from Plate_1's at nominal |

Scripts: `tools/solidworks_spike/build_fits.py`, `build_fit_asm.py`. The read-out is `readout_dia.py`, saved as `readout_dia_Fit_Test.json` and `readout_dia_Pin_Test.json`.

## What was read back

| Item | Entered | Read through the API | Verdict |
|---|---|---|---|
| Shaft diameter (DimXpert type 109, feature *Boss*, type 2) | Ø20 g6 | nominal 20; DimXpert fit code `''`, limits ±0.127 (the default); **display dimension: fit type, shaft `g6`** | fit only on the display; see finding 2 |
| Housing bore (type 109, feature *Simple Hole*, type 7) | Ø20 H7 | nominal 20; DimXpert fit `''`, ±0.127; **display: hole `H7`** | as above |
| Plate hole diameters | Ø6.2 ±0.05 | 6.2, +0.05 / −0.05 | exact |
| Pin diameter | Ø6 +0 / −0.02 | 6, +0 / −0.02 | exact |
| Datums A, B, C (type 150) | 3 faces per plate | identifiers A, B, C, each on the right face | exact |
| Position (type 201) | Ø0.1 (M) to A, B, C | value raw 100 (= **0.1 mm**, in µm as for flatness), on the hole's face; modifier **none**; DimXpert datum lists **empty**; display frame `0.1 | A | B | C` | value right; MMC and datums missing (finding 3) |
| Round faces (ISurface CylinderParams, then the component transform) | bore R10, shaft R10, holes R3.1, pin R3 | R10, R10, R3.1, R3; axis (0, 0, −1) through (20, 20) and (30, 10) | exact |

Read time with SolidWorks already running: 7.2 s (`Fit_Test`) and 23.3 s (`Pin_Test`).

## Findings

1. **Diameters can be read the same way as widths.** DimXpert type 109 gives nominal and ± tolerance, and its feature gives the round face. Holes come as *Simple Hole* features, bosses as *Cylinder* features. `InsertSizeDimension` returns `False` for a diameter even when it creates it; this only affects our test-file script.
2. **Fit codes set through the API reach only the display dimension.** DimXpert's own `LimitsAndFitsCode` stays empty and its limits keep the default ±0.127. The fit survives saving and reopening.
   - **Consequence:** the reader must read the fit from the display dimension. detectTOL then computes the limits from the IS 919 / ISO 286 table, never from SolidWorks' numbers.
   - The current reader (app plan, Step 2) reads only `LimitsAndFitsCode`, so it would miss these fits. This will be fixed in Step 2.
   - **Unknown:** whether a fit chosen **by hand** in SolidWorks fills DimXpert's fit code and limits. That needs the hand check.
3. **MMC and datum links of a position can't be set through the API.** The value reaches DimXpert. The datum letters appear in the frame but are not linked to the datums. `SetFrameSymbols2` has no effect, with numeric or text arguments.
   - **Consequence for the reader:** read MMC and datums from DimXpert when they are there. Otherwise fall back to the frame's text (letters → datum features by identifier) and say so in the report.
   - **Unknown:** whether a position made **by hand** links them properly (expected, since that's how DimXpert is meant to be used). That needs the hand check.
4. **STEP splits every full cylinder into two half-faces.** Matching by centroid can't work for round faces.
   - Matching by **part + radius + axis line** works: each SolidWorks round face maps to exactly its own two STEP half-faces (`match_cylinders.py`).
   - The part is needed because a shaft and its bore share axis and nominal radius, and so do the two plate holes. Within one part, two coaxial bores of the same size (for example two bearing seats) also need the axial range.
   - Step 2 adds axis and radius to the STEP reader's face data (`FaceInfo`).
5. **Flat faces still need their normal checked when matching.** Plate_2's datum A face (z = 10) sits on Plate_1's top face: same centroid and area, opposite normals. The product matcher already compares normals; this case gets a test.
6. Once, opening the assembly with SolidWorks hidden returned nothing; the next try worked. The reader already reports this as an error. Step 2 will add one retry.

## Recommendation for Step 2

Read these sources:

| Source | Read | Use |
|---|---|---|
| DimXpert diameter (109) | nominal, ± tolerance, fit (DimXpert or display) | hole/shaft size; fit limits from IS 919 |
| DimXpert position (201) | value, MMC/LMC, datums (DimXpert, else frame text) | hole location for a pin in a chain, with MMC bonus |
| DimXpert datum (150) | identifier, face | link position to faces |
| Round faces | axis, radius, inner/outer | the clickable "hole" and "shaft" in the app; matched to STEP by axis and radius |

Reference values for Step 2 tests. These are **to be checked** against the IS 919 / ISO 286 table and by the reviewer subagent, not used as they are:
- Ø20 H7 = +0.021 / 0, Ø20 g6 = −0.007 / −0.020, so the clearance should be 0.007 to 0.041 mm.
- Pin test: hole at MMC 6.15, pin at MMC 6.0. Floating fastener (ASME Y14.5 appendix): a position of 0.15 per part always assembles. 0.1 is entered, so it always assembles.

## Needs your check (the gate): about 5 minutes in SolidWorks

1. **Position with MMC and datums.**
   - Open `examples/solidworks/fits/Plate_1.SLDPRT`. In the DimXpertManager tab (the ⊕ icon above the feature tree), double-click **Position1**.
   - In the frame: keep 0.1, add the **Ø** symbol and the **Ⓜ** (MMC) modifier, and choose datums **A, B, C** from the list.
   - OK, then save.
2. **A fit chosen by hand.**
   - Open `examples/solidworks/fits/Shaft.SLDPRT` and click the Ø20 dimension.
   - In the PropertyManager under *Tolerance/Precision*, choose **Fit**, shaft class **g6**. Choose it again even though it shows already.
   - OK, then save.
3. Tell me **"done"**. I'll read both files again and report whether DimXpert itself now holds MMC, the datums, the fit code and the g6 limits.

If a step is unclear or SolidWorks shows something else, a screenshot is enough.

## Not done in this step

- No product code changed; the spike scripts in `tools/solidworks_spike/` are not product code.
- No drawing (`.SLDDRW`) with diameters yet. Drawing dimensions already work for widths; diameters go through the same route in Step 2.
