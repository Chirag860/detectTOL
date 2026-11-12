# R4 — Feasibility note

Phase R, 2026-11-12. Labels [S]/[D]/[I]/[K] as in `domain-notes.md`.

## 1. Can pythonocc-core read AP242 semantic PMI?

**Status: NOT VERIFIED BY EXECUTION.** No throwaway script was run. This machine has only CPython 3.14 from python.org, no conda/mamba/micromamba, and pythonocc-core is distributed through conda-forge, not pip. Installing a conda distribution is a download-and-install I did not do without the maintainer's go-ahead (question Q1 in the phase report).

**Update 2026-11-12 (after Miniforge was installed) — binding check executed, still no real file read.**
Environment: Windows 11, conda env from `environment.yml`, Python 3.12.16, pythonocc-core 8.0.1.2. Result of introspecting the bindings:

- `STEPCAFControl_Reader.SetGDTMode(True)` works; `XCAFDoc_DocumentTool.DimTolTool(...)` returns a tool; `GetDimensionLabels`, `GetGeomToleranceLabels`, `GetDatumLabels`, `GetRefShapeLabel` exist.
- `XCAFDoc_Dimension` and `XCAFDoc_Datum` expose `GetObject` / `SetObject`.
- **`XCAFDoc_GeomTolerance` exposes no public methods at all** (no `GetObject`). If that holds on a real file, geometric tolerances (flatness, position, …) cannot be read through this class in this build, and Phase 5 needs another route. This is a red flag, not yet a conclusion: no AP242 file has been read.
- Importing `OCC` only works when the conda env is properly activated (its `Library\bin` on PATH). Calling the env's `python.exe` directly crashed matplotlib/numpy with a Windows delay-load error (0xc06d007f). Use `conda activate` or `conda run`.

What the documentation and trackers say:

- conda-forge `pythonocc-core`: latest **8.0.1.2**; version history 7.4.0 … 7.9.3, 8.0.1, 8.0.1.1, 8.0.1.2; platform map lists win-64, linux-64, osx-64, osx-arm64, linux-aarch64; license LGPL-3.0-or-later. [S1] Which Python versions (3.11–3.14) have builds: not visible in what I read — UNSURE.
- OCCT exposes the path the spec plans: `STEPCAFControl_Reader` with GD&T mode on, then `XCAFDoc_DocumentTool::DimTolTool`, `GetDimensionLabels` / `GetGeomToleranceLabels` / `GetDatumLabels`, `XCAFDoc_Dimension::GetObject()`, `GetRefShapeLabel` for the target shapes. [S2, S3]
- **Known problem 1 (OCCT itself).** A 2026 forum report: with OCCT 7.8.0 and 7.9, reading AP242 files exported by Siemens NX and by NIST returns tolerance type, name and datums but **not the tolerance magnitude** (null handle). Files written by OCCT's own writer round-trip correctly. OCCT staff reply: "probably fixed", try master or 8.0.0rc3+. No ticket or patch linked. [S4]
- **Known problem 2 (Python bindings).** CadQuery/OCP issue #153 (open since 2024-08): in Python, `label.FindAttribute(XCAFDoc_Dimension.GetID_s(), attr)` reports success but `attr.GetObject()` then fails; the same code works in C++. Workaround posted: iterate with `TDF_AttributeIterator` and match the GUID. [S5] This is OCP (pybind11), **not** pythonocc (SWIG) — whether pythonocc has the same defect is UNSURE.
- One third-party project reports frequent crashes with XCAF PMI extraction through pythonocc-core and switched to parsing the STEP text. Single anecdote, low authority. [S6]

Conclusion [I]:

- The API exists; reliability on real NX/NIST files is doubtful below OCCT 8.0 and unproven at 8.0.
- Pin `pythonocc-core >= 8.0.1` in `environment.yml` if the Phase 5 check passes there. An LGPL dependency is compatible with an Apache-2.0 library that only imports it, but the maintainer should confirm that reading.
- The first task of Phase 5 must be a go/no-go script on 2–3 NIST files that prints, per PMI item: type, value, unit, datum refs, referenced face count. No design before that.

Fallback if PMI is not reliable:

1. The YAML annotation file already in the Phase 5 spec (tolerances attached to faces by part name + face index + centroid/normal fingerprint) becomes the primary input; STEP supplies geometry only.
2. Optional later: read the PMI entities directly from the STEP text (Part 21) for the small subset of Phase 4. More work, no OCCT dependency for PMI. Not proposed for v0.1.

Operating systems: conda-forge lists builds for Windows, Linux and macOS (Intel and ARM) [S1]. Runtime behaviour per OS: not tested.

## 2. Public AP242 test files with PMI

- NIST MBE PMI Validation and Conformance Testing project: test cases (CTC = combined, FTC = fully-toleranced), CAD models, STEP files and reports are free to download. Each test case is available as STEP AP242. [S7]
- License: the data.nist.gov record is public and points to the NIST open license. [S7] That license lets users use, modify and redistribute NIST data provided NIST is acknowledged and modified versions are marked with the date and nature of changes; provided "AS IS". [S8]
- So redistribution appears permitted with attribution. [I] I still recommend downloading in a test fixture (cached, checksum-pinned) rather than committing: smaller repo, and no question about files that were authored in commercial CAD systems.
- Caveats stated by NIST: the project concluded in 2015; the FTC and CTC "are not intended to represent best practice in how to apply GD&T". [S7] They are parser test data, not validation cases for stack results.
- Expected PMI counts per model (needed for the Phase 5 "counts match" test): not looked up this phase. They must come from NIST's test-case definition documents, never from our own reader's output.

## 3. Is the name `detecttol` free?

- **PyPI:** `https://pypi.org/pypi/detecttol/json` returned HTTP 404 on 2026-11-12 → no project of that name. [S9]
- **GitHub:** repository search for `detecttol` returned 0 repositories on 2026-11-12. [S10] I did not check whether a GitHub user/organisation is named `detecttol`.
- Nothing was registered.

## 4. Other feasibility flags for later phases [I]

- **Phase 6 contact tolerance 1e-6 mm.** STEP files from real CAD systems carry their own modelling precision, often coarser than 1e-6 mm. Fine for synthetic OCCT-generated assemblies; make it a parameter before using real files. Not verified against a source.
- **Phase 0 CI on three OSes with conda** takes minutes per job; keep `core/` tests in a separate pip-only job so math CI stays fast and proves the "core never imports OCCT" rule.
- **No git repository yet** in this folder; Phase 0 creates it.

## Sources

1. anaconda.org API, conda-forge/pythonocc-core. https://api.anaconda.org/package/conda-forge/pythonocc-core
2. OCCT reference manual, `XCAFDoc_DimTolTool`. https://dev.opencascade.org/doc/refman/html/class_x_c_a_f_doc___dim_tol_tool.html
3. OCCT forum, "Extracting Dimension Data From Step File". https://dev.opencascade.org/content/extracting-dimension-data-step-file
4. OCCT forum, "Issue reading geometric tolerance values from NX/NIST-generated STEP AP242 files in OCCT 7.9". https://occt3d.com/dev/content/issue-reading-geometric-tolerance-values-nxnist-generated-step-ap242-files-occt-79/index.html
5. CadQuery/OCP issue #153. https://github.com/CadQuery/OCP/issues/153
6. Eryxon "PMI Extraction System" page (anecdote). https://9c69d5fe-eryxon-flow-website.luke-f5c.workers.dev/features/pmi-extraction
7. NIST MBE PMI Validation and Conformance Testing project. https://www.nist.gov/el/systems-integration-division-73400/mbe-pmi-validation-and-conformance-testing-project ; dataset record https://catalog.data.gov/dataset/nist-cad-models-and-step-files-with-pmi
8. NIST open license. https://www.nist.gov/open/license
9. PyPI JSON API. https://pypi.org/pypi/detecttol/json
10. GitHub repository search API. https://api.github.com/search/repositories?q=detecttol
