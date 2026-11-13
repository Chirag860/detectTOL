# Phase 5 report — STEP AP242 reader

> **Superseded in part (2026-11-13).** The human-check columns, the review items and (for phases 4 and 5) several conventions and gate statements below were revised under the maintainer's delegation. Read `verification-2026-11-13.md` first.

2026-11-13. Environment for everything below: Windows 11, conda env, Python 3.12.16, **pythonocc-core 8.0.1.2** (OCCT 8.0.1).

## Done

- `detecttol.cad.step_reader.read_step(path) -> StepModel`
  - assembly tree, part names, placements (translation + rotation);
  - every face of every part in assembly coordinates: index, surface type, area, centroid, outward normal for planes;
  - semantic PMI: dimensions, geometric tolerances, datums, each with the faces it points to.
- `detecttol.cad.mapping`: PMI → `Contributor`, `Flatness`, `Parallelism`, `Position`, `Orientation`; anything outside the Phase 4 subset raises an error that names the item.
- `detecttol.cad.annotations`: the YAML annotation fallback (part name + face index + centroid/normal fingerprint), with measured nominal distances.
- `detecttol.cad.step_text`: an OCCT-free count of PMI entities in the file text, used as the independent check.
- `detecttol.cad.synthetic`: writes box assemblies with known dimensions.
- CLI: `detecttol faces model.step` lists planar faces as ready-to-paste selectors.
- 59 tests (2 run without pythonocc; the other 57 are skipped where it is not installed).

## The API check the spec asked for ("verify before designing")

Done first, by experiment. What I found in this binding:

| Finding | Consequence |
|---|---|
| `TDF_Label.FindAttribute(guid, attr)` does not fill `attr` (the defect reported for OCP in issue #153 exists here too) | Attributes are found by iterating the label and down-casting; objects via `XCAFDoc_Dimension.Set(label)` / `XCAFDoc_Datum.Set(label)`, which return the existing attribute |
| `XCAFDoc_GeomTolerance` has **no methods at all** in Python | Type, value and material modifier are read from the attribute's child labels (tags 1, 3, 4). Verified against the file text, below |
| `DownCast` raises on a type mismatch instead of returning nothing | Type name is checked first |
| OCCT returns the lower ± deviation as a magnitude (file −0.2 → 0.2) | Sign restored (ASSUMPTIONS A24, with its limitation) |
| Writing a STEP file with PMI created from Python crashes OCCT (access violation in `STEPCAFControl_Writer.Transfer`) | Synthetic files carry geometry only (D49) |
| XCAF has more labels than PMI items: dimension labels without data, "DimensionPresentation" labels, one datum label per datum *reference* | Filtered / de-duplicated, with a note on the model |
| NIST files hold face-less shapes beside the solid | Skipped, with a note (A25) |

## Gate: which PMI is read correctly, and which is not

Checked on all 17 AP242 files of the NIST set. "In file" = counted in the STEP text without OCCT. Real output of the comparison script:

| file | parts | faces | geom. tol. read / in file | MMC+LMC read / in file | datums read / in file | dimensions read / with value in file | geom. tol. without face link |
|---|---|---|---|---|---|---|---|
| nist_ctc_01_ap242-e1 | 1 | 117 | 6 / 6 | 0+0 / 0+0 | ABC / ABC | 8 (8 toleranced) / 8 | 0 |
| nist_ctc_02_ap242-e2 | 3 | 637 | 22 / 22 | 1+3 / 1+3 | ABCDEFGHJK / ABCDEFGHJK | 8 (7 toleranced) / 7 | 0 |
| nist_ctc_03_ap242-e2 | 1 | 120 | 12 / 13 | 2+0 / 2+0 | ABCDE / ABCDEF | 9 (8 toleranced) / 9 | 0 |
| nist_ctc_04_ap242-e1 | 2 | 484 | 6 / 7 | 0+0 / 0+0 | ABCDEFGH / ABCDEFGH | 13 (7 toleranced) / 10 | 0 |
| nist_ctc_05_ap242-e1 | 1 | 156 | 10 / 10 | 0+0 / 0+0 | ABCD / ABCD | 8 (2 toleranced) / 6 | 1 |
| nist_ftc_06_ap242-e2 | 1 | 187 | 27 / 28 | 4+0 / 4+0 | ABCDEFGHJK / ABCDEFGHJK | 25 (19 toleranced) / 24 | 0 |
| nist_ftc_07_ap242-e2 | 2 | 306 | 25 / 27 | 4+0 / 4+0 | ABCDE / ABCDE | 27 (17 toleranced) / 17 | 0 |
| nist_ftc_08_ap242-e1-tg | 2 | 273 | 0 / 0 | 0+0 / 0+0 | / | 4 (0 toleranced) / 0 | 0 |
| nist_ftc_08_ap242-e2 | 1 | 247 | 23 / 33 | 5+0 / 13+0 | ABCDEFGHJKL / ABCDEFGHJKL | 8 (5 toleranced) / 10 | 0 |
| nist_ftc_09_ap242-e1 | 2 | 163 | 31 / 31 | 6+0 / 6+0 | ABCDEFGH / ABCDEFGH | 25 (21 toleranced) / 22 | 0 |
| nist_ftc_10_ap242-e2 | 2 | 282 | 35 / 40 | 2+1 / 2+1 | ABCDEFGHJKL / ABCDEFGHJKL | 36 (20 toleranced) / 26 | 0 |
| nist_ftc_11_ap242-e2 | 1 | 42 | 4 / 4 | 0+0 / 0+0 | AB / AB | 8 (4 toleranced) / 6 | 0 |
| nist_stc_06_ap242-e3 | 1 | 144 | 25 / 25 | 3+0 / 3+0 | ABCDEF / ABCDEF | 19 (16 toleranced) / 17 | 0 |
| nist_stc_07_ap242-e3 | 2 | 306 | 10 / 22 | 0+0 / 3+0 | ABC / ABCDE | 39 (36 toleranced) / 45 | 0 |
| nist_stc_08_ap242-e3 | 2 | 271 | 29 / 30 | 9+0 / 9+0 | ABCDEGHJ / ABCDEGHJ | 8 (7 toleranced) / 7 | 0 |
| nist_stc_09_ap242-e3 | 1 | 125 | 27 / 27 | 5+0 / 5+0 | ABCDEFGH / ABCDEFGH | 25 (20 toleranced) / 22 | 0 |
| nist_stc_10_ap242-e2 | 1 | 256 | 36 / 37 | 2+1 / 2+1 | ABCDEFGHJ / ABCDEFGHJ | 28 (18 toleranced) / 27 | 0 |

### What this means

**Read correctly**

- **Geometry and assembly structure**: every file loads; synthetic assemblies reproduce their dimensions to 1e-9 mm.
- **Geometric tolerances — type, value, material modifier, datum references, target faces**: 328 of the 362 in the 16 files that have PMI (90.6 %). Complete in 7 files (CTC-01, -02, -05, FTC-09, -11, STC-06, -09). Types never disagree with the file where a tolerance is read. MMC/LMC counts agree in 14 of 16 files.
- **Datum letters**: complete in 14 of 16 files.
- **CTC-01 in full**: all 8 dimension values with their tolerances and all 6 geometric tolerances match what I read by hand from the file text.

**Not read correctly**

- **Geometric tolerances lost inside OCCT**: 34 across 9 files. Worst: FTC-08 (23 of 33; 8 of its 13 position tolerances and 8 of its 13 MMC modifiers missing) and STC-07 (10 of 22; all 9 position tolerances and 3 MMC modifiers missing). One each in CTC-03, CTC-04, FTC-06, STC-08, STC-10; two in FTC-07; five in FTC-10. I did not find out why; this is the reader's main defect. It matches the kind of problem reported on the OCCT forum for NX/NIST files.
- **Datums**: F missing in CTC-03; D and E missing in STC-07.
- **Dimensions**: the count agrees with the file in only 2 of 16 files (CTC-01, CTC-03). In most files XCAF returns *more* dimension labels than the file has dimensions with a value (typically labels with no tolerance); in FTC-08 and STC-07 it returns fewer. **Outside CTC-01 I have not verified a single dimension value.** Treat dimension reading as unverified.
- **One geometric tolerance without a face link** (CTC-05).
- **Not interpreted at all**: tolerance zone shape (diametral vs width), projected zones, unequally-disposed profiles, datum modifiers and datum targets, composite tolerances, ISO tolerance classes (reported as form `class`, no limits), angular dimension units.

**Not supported by the Phase 4 models** (read, but `mapping` refuses them by name): profile of a surface / line, runout, circularity, cylindricity, straightness, concentricity, symmetry; angular dimensions.

### The spec's count test

root.md asks that "the number of PMI items read matches the documented counts for the test models". **This gate item is not met**: I found no count table from NIST, and against my own independent count the reader matches fully on only some files. The tests assert what is true — exact agreement for CTC-01/-02/-05, and for every CTC file that the reader never invents or mislabels a tolerance — and do not assert the known shortfalls, so the suite does not freeze a defect in place.

## Test results

Real output of the final run:

```
src\detecttol\cad\_occt.py             10      0      2      0   100%
src\detecttol\cad\annotations.py      157      1     40      1    99%
src\detecttol\cad\mapping.py           78      0     40      0   100%
src\detecttol\cad\step_reader.py      285      6     72      9    96%
src\detecttol\cad\step_text.py         56      0     20      0   100%
src\detecttol\cad\synthetic.py         52      2     12      2    94%
TOTAL                                1891     15    450     16    99%
274 passed in 24.08s
ruff check: All checks passed!
mypy: Success: no issues found in 8 source files
```

Without pythonocc (import blocked, to imitate the pip-only CI job):

```
SKIPPED [1] tests\cad\test_annotations.py:12: pythonocc-core is not installed
SKIPPED [1] tests\cad\test_cli_faces.py:11: pythonocc-core is not installed
SKIPPED [1] tests\cad\test_mapping.py:9: pythonocc-core is not installed
SKIPPED [1] tests\cad\test_nist.py:24: pythonocc-core is not installed
SKIPPED [1] tests\cad\test_step_reader.py:9: pythonocc-core is not installed
217 passed, 5 skipped in 13.78s
```

- mypy `--strict` covers `core/` only, as the spec requires; the `cad/` code is not type-checked (pythonocc ships no usable types).
- The NIST fixture downloaded the archive itself in one local run (SHA-256 `8fa78429…181911`, 13 976 599 bytes) and all 13 NIST tests passed.

### Defects found on the way

| Failure | Root cause | Fix |
|---|---|---|
| Four NIST tests: "parts" with zero faces | **Reader defect.** Face-less shapes stored beside the solid were reported as parts | Skipped with a note |
| FTC-09: none of 31 geometric tolerances linked to a face | **Reader defect**, found through the table, not by a test: part definitions were keyed by name, and several definitions are called `SOLID` | Keyed by label; all 31 now link |
| ± tolerances with the wrong sign | **Reader defect.** My first rule ("flip if lower > upper") was wrong for symmetric tolerances; OCCT returns a magnitude | Sign always restored; verified on six dimensions |
| Access violation writing synthetic PMI | OCCT / binding | Not worked around; synthetic PMI dropped |
| OCCT printing transfer statistics during tests | Library must not print | Message printers removed |

## Golden values and who verified them

| Value | Source | Me | Reviewer | Human |
|---|---|---|---|---|
| Synthetic assembly: areas, centroids, thicknesses 10 and 16.6, rotated-part faces | by construction, derived in test docstrings | ✔ | not required (Phase 5) | pending |
| CTC-01: 8 dimensions (60 ± 0.5; 35 +0/−0.2; 35 +0.2/−0; 20 +0.05/−0.1; 20 +0.1/−0.05; 35 limits 34.8–35.2 twice; 25 ± 0.15) | read by hand from the STEP text, entity ids in the test | ✔ | — | pending |
| CTC-01: 6 geometric tolerances (position 0.75 ×2, profile 1.25 and 0.5, perpendicularity 1.5, flatness 0.2) and datums A, B, C | read by hand from the STEP text | ✔ | — | pending |
| CTC-02: 1 MMC, 3 LMC | counted in the STEP text | ✔ | — | pending |
| perpendicularity 1.5 over 30 mm → atan(0.05) = 0.04995840 rad | hand | ✔ | — | pending |

Nothing was checked against the NIST drawings (the PDFs are in the archive; I could not render them here).

## Reviewer subagent findings and resolutions

Not required for Phase 5 (root.md rule 8).

## New assumptions added to ASSUMPTIONS.md

A23 (units and face index), A24 (lower-deviation sign), A25 (face-less shapes and presentation-only dimensions).

## Known limitations / open risks

- The reader loses about one geometric tolerance in ten on the NIST set, and far more on two files. **Do not rely on PMI from STEP without the annotation file as a cross-check.**
- Dimension reading is verified on one file only.
- Tested on one pythonocc version and, until CI reports, one operating system. The child-label layout used for geometric tolerances is an OCCT implementation detail and may change between versions.
- A24: a lower deviation that is positive in the file is misread.
- Mapping needs information that is not in the PMI: stack direction, feature length for orientation, hole/pin and the size contributor for MMC/LMC.
- Annotation file: dimensions between parallel planar faces only; no cylinders, no position tolerances.
- Face indices are OCCT traversal order; another exporter or CAD revision can reorder them. The fingerprint catches that, it does not repair it.
- The NIST tests need network access the first time; offline they are skipped, visibly.
- Decisions D45–D50 are mine and provisional.

## Items needing human review

1. Compare the CTC-01 values above with the NIST drawing `nist_ctc_01_asme1_rd.pdf`.
2. Decide whether a reader that drops ~10 % of geometric tolerances is acceptable as the primary route, or whether the annotation file should be the primary input (as the Phase R feasibility note suggested).
3. If you can supply NIST's expected PMI counts per model, the count test can be made the one the spec asks for.
4. The licence question for pythonocc (LGPL-3.0) is now live: `detecttol.cad` imports it.

## Proposed plan for Phase 6

Not started.

- Contact detection between planar faces of different parts (opposite normals, coincident planes, overlapping extents), contact graph, path search from face A to face B, projection on the measurement direction.
- Use the annotation file as the tolerance source; PMI only where it is complete.
- The 1e-6 mm contact tolerance of the spec should become a parameter.
- Golden case A rebuilt as a STEP assembly with `detecttol.cad.synthetic` must reproduce the YAML result.
- Needs from the maintainer first: the review items of Phase 4 (they decide what a "contributor" from CAD means) and item 2 above.

## CI for this phase

Commit `b92caf1` (3D loops, Phase 4, Phase 5 and these reports), GitHub Actions, queried from the GitHub API after the run completed:

```
sha=b92caf1 status=completed conclusion=success
conda (macos-latest): completed/success
conda (ubuntu-latest): completed/success
conda (windows-latest): completed/success
core-pip (macos-latest, 3.11): completed/success
core-pip (macos-latest, 3.12): completed/success
core-pip (ubuntu-latest, 3.11): completed/success
core-pip (ubuntu-latest, 3.12): completed/success
core-pip (windows-latest, 3.11): completed/success
core-pip (windows-latest, 3.12): completed/success
```

What this does and does not show:

- The three conda jobs have pythonocc, so the synthetic-STEP, mapping and annotation tests ran on Linux, macOS and Windows.
- **Not confirmed:** whether the 13 NIST tests ran or were skipped on CI. They skip (visibly) if the download fails, and a skip still gives a green job. I could not read the job logs without signing in. Locally on Windows they ran and passed.
- The six pip jobs skip the five pythonocc test modules by design.
