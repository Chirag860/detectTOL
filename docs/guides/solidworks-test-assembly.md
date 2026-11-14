# Making the SolidWorks test files (Step 1 of the app plan)

These files let detectTOL check that it reads your tolerances correctly from SolidWorks. It takes about 20 minutes. The model is the same as `tolerance_stack_test.step`: three blocks in a frame, so the results can be compared.

> Menu names are for SOLIDWORKS 2026. If one is called slightly differently on your screen, tell me what you see.

## 1. Make a folder

`C:\Users\DELL\Desktop\detectTOL_SW_test` — save every file below into it.

## 2. The four parts (units: mm)

**Before you start each part**, set millimetres: Tools → Options → Document Properties → Units → **MMGS**.

| Part file name | Shape (simple extruded box) | Size along X |
|---|---|---|
| `Frame.SLDPRT` | U-shape or box with a rectangular opening, opening **100** wide along X, walls 5 thick, 20 deep (Y), 5 high (Z) — any simple frame is fine | opening 100 |
| `Block_A.SLDPRT` | box | **25** |
| `Block_B.SLDPRT` | box | **35** |
| `Block_C.SLDPRT` | box | **39** |

Blocks: make them 20 (Y) × 5 (Z) so they fit the opening.

## 3. Add tolerances with DimXpert (in each part)

1. Open the part. In the CommandManager, open the **MBD Dimension** tab (if missing: right-click a tab → MBD Dimension). The same tools are under Tools → MBD Dimension.
2. Click **Size Dimension**, then click **one end face** of the block along X (for the frame: one **inner** face of the opening). SolidWorks recognises a *Width* and highlights the opposite face; accept it. Place the dimension.
3. In the left PropertyManager, under **Tolerance**, pick **Bilateral** and enter:

| Part | Dimension | Upper | Lower |
|---|---|---|---|
| Frame | opening 100 | +0.20 | −0.20 |
| Block_A | 25 | +0.10 | −0.10 |
| Block_B | 35 | +0.05 | −0.05 |
| Block_C | 39 | +0.10 | −0.00 |

   (Different values on purpose, so a mix-up would show.)
4. Only on **Block_B**: also add a **flatness 0.02** on its right end face: MBD Dimension tab → **Geometric Tolerance** → Flatness → click the face → 0.02.
5. Only on **Frame**: set the general tolerance: Tools → Options → **Document Properties → DimXpert** → Block tolerance / General tolerance: **ISO 2768**, class **m (medium)**.
6. Save the part.

## 4. The assembly

1. New assembly `Tolerance_Test.SLDASM`. Insert Frame first (fixed), then Block_A, Block_B, Block_C.
2. Mates (all **Coincident**):
   - Block_A left face ↔ Frame inner left face
   - Block_B left face ↔ Block_A right face
   - Block_C left face ↔ Block_B right face
   - plus bottom faces coincident and front faces coincident, so the blocks sit level.
3. The gap between Block_C's right face and the frame's inner right face should be **1 mm** (100 − 25 − 35 − 39). Measure it with Tools → Evaluate → Measure.
4. Save.

## 5. One drawing

1. File → Make Drawing from Part, for **Block_C**. Put in a front view.
2. **Smart Dimension** between the two end edges (the 39 mm length).
3. In the PropertyManager → Tolerance/Precision → **Bilateral**: +0.10 / −0.00.
4. Save as `Block_C.SLDDRW`.

## 6. Optional: a STEP AP242 copy

With the assembly open: File → Save As → type **STEP AP242 (*.step)** → **Options…** → tick **Export 3D PMI** if it is there (if it is greyed out or missing, write that down — it tells us whether the MBD add-in is needed). Save as `Tolerance_Test.step`.

## 7. Tell me

Reply with the folder path and anything that did not match these steps. Then I run the read-out script; SolidWorks will open and close by itself while it runs — leave it alone until it finishes.
