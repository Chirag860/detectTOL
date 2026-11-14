# detectTOL

Free, scriptable, verifiable mechanical tolerance stack-up analysis.

**Status:** 1D linear stacks with a CLI (Phases 0–2 of `root.md`) and 2D vector loops with relative angles (Phase 3; try `detecttol analyze examples/wedge_height.yaml`). 3D loops are supported in YAML too (`examples/tilted_post_3d.yaml`). A GD&T subset (Phase 4) and a STEP AP242 reader (Phase 5) exist as Python APIs; stacks can be built from a STEP assembly with planar contacts (Phase 6, `examples/step/`).

**Read the limits first:** the GD&T conversions have not been reviewed against ASME Y14.5 (`docs/reports/phase-4.md`), and the STEP reader loses about one geometric tolerance in ten on the NIST test files (`docs/reports/phase-5.md`).

## What it does today

- Worst case, RSS and seeded Monte Carlo for a linear stack `Y = constant + Σ aᵢ·xᵢ`
- Normal, uniform and truncated-normal contributors; asymmetric tolerances
- Contribution of each tolerance, predicted failure rate (fraction and ppm), Cpk
- Markdown, HTML and JSON reports with a Monte Carlo histogram

## Install (development)

```bash
conda env create -f environment.yml
conda activate detecttol
pytest
```

The math and the CLI also work without conda (no CAD dependency):

```bash
pip install -e ".[dev]"
```

## Quick start

```bash
detecttol analyze examples/golden_case_a.yaml --format md
detecttol analyze examples/golden_case_a.yaml --format html --out out/
```

```python
from detecttol import analyze
from detecttol.io import load_stack

result = analyze(load_stack("examples/golden_case_a.yaml"))
print(result.rss.p_fail_ppm)
```

## Your own STEP file

Needs the conda environment (pythonocc-core). Works for assemblies whose parts
touch on flat faces, for a requirement measured along one straight direction.

1. List the flat faces of your model, and see what PMI it carries:

   ```bash
   detecttol faces my_assembly.step
   ```

2. Write a small YAML file next to it: copy `examples/step/plate_stack.yaml`,
   set `step_file`, paste the two faces of your requirement into `from` / `to`,
   and add one `dimension` entry (two faces + tolerances) for every part
   dimension in the chain. If you leave one out, the error message names the
   part, the two faces and the nominal it needs.

3. Analyse it:

   ```bash
   detecttol analyze my_stack.yaml --format html --out out
   ```

The tool finds which parts touch, builds the chain between your two faces and
works out each sign itself. It stops with an explanation if the parts do not
touch, if there are two possible chains, or if a contact is not flat.
Tolerances are **not** yet taken from PMI in the STEP file automatically.

## Install on Windows (for engineers)

Double-click `installer\install_detectTOL.bat`. It sets everything up (offering to
install Miniforge if you have no conda) and puts a **detectTOL** shortcut on your
Desktop. Then read the [user guide](docs/USER_GUIDE.md).

## The app (no command line needed after start)

```bash
detecttol app
```

Your browser opens at `http://127.0.0.1:8765` (this PC only; nothing is uploaded).

1. **Open a model**: browse to a folder, tick any drawings (`.SLDDRW`) to read too,
   and click the `.SLDASM` (read through SolidWorks, about 20 s) or `.step`.
2. **Choose the requirement**: click face 1 and face 2 in the 3D view, or pick them
   from the lists (each entry shows the tolerances found on that face). Set the
   limits, the drawing standard (IS / ISO / ASME) and the general tolerance class.
3. **Check the chain**: every dimension with where its tolerance comes from
   (DimXpert, drawing, IS 2102 general tolerance, or you). Yellow cells can be
   edited; a dimension with no tolerance at all must be filled before analysing.
4. **Analyse**: a plain-words verdict, worst case, RSS, Monte Carlo, the biggest
   contributors, the histogram, and a downloadable HTML report.

**Save project** writes `<model>.dtol` next to the model; open it from the same
folder browser later (the model is re-read, so CAD changes are picked up).
Needs the conda environment plus `conda install nicegui` (and `pywin32` for
SolidWorks).

## Straight from SolidWorks (no YAML)

On a Windows PC with SolidWorks installed (tested: SOLIDWORKS 2026), detectTOL
reads the tolerances you put in the model with **DimXpert** (and, optionally,
toleranced dimensions in a drawing). Your files are opened read-only and never
saved. Needs `conda install pywin32` in the detecttol environment once.

1. See the faces and the tolerances found on them:

   ```bash
   detecttol faces Tolerance_Test.SLDASM --drawing Block_C.SLDDRW
   ```

2. Analyse the gap between two faces (numbers from step 1):

   ```bash
   detecttol analyze-cad Tolerance_Test.SLDASM --drawing Block_C.SLDDRW --from Block_C:2 --to Frame:4 --standard is --general m
   ```

   `--general m` gives the IS 2102 / ISO 2768-m general tolerance to any
   dimension in the chain that has no tolerance in the model; without it the
   tool stops and tells you which one is missing. The default requirement is
   gap ≥ 0 (`--lsl 0`).

The same command works on a STEP file with semantic PMI (`.step`), for other CAD
tools. SolidWorks without the MBD add-in cannot export STEP with tolerances, so
for SolidWorks use the `.SLDASM` route. Example files: `examples/solidworks/`.
An app with a 3D view is planned (no command line needed).

## Indian (IS) and ISO drawings

Say which standard the drawing follows, at the top of any stack file:

```yaml
standard: is          # asme | iso | is   (is = Indian Standards; same rules as iso)
general_tolerance: m  # optional: the IS 2102 / ISO 2768 class from the title block
```

- **What changes:** IS and ISO drawings use the *independency principle*
  (IS 12160 = ISO 8015). A flatness on a sized face then **adds** ±t/2 to the
  stack, unless the size is marked Ⓔ (`envelope: true`). ASME's Rule #1 does
  the opposite. Plain ± stacks give the same numbers under every standard.
- **No standard given:** ASME is assumed, and the report warns you wherever
  that changed a result.
- **Tolerances by class:** instead of `upper_tol` / `lower_tol`, a contributor
  or STEP dimension can give `tolerance_class`:
  - `general`: the file's `general_tolerance` (IS 2102 (Part 1) = ISO 2768-1).
  - `H7`, `h6`, `JS9`, `js8`: IS 919 / ISO 286 classes H, h, JS, js, IT5–IT18,
    up to 500 mm. Other letters (g6, k6, P7, …) are not supported yet. **This
    table has not been checked against a printed copy**, so every report that
    uses it says so (`TABLE_NOT_VERIFIED`).
- Look up one class: `detecttol limits 25 H7` or `detecttol limits 25 general --general m`.
- Example: [examples/is_fit_and_general.yaml](examples/is_fit_and_general.yaml).

## Read before trusting a number

- Every modelling assumption is in [docs/ASSUMPTIONS.md](docs/ASSUMPTIONS.md).
- Provisional design decisions awaiting maintainer review are in [docs/DECISIONS.md](docs/DECISIONS.md).
- Units are millimetres. Any other unit is rejected.

## License

Apache-2.0.
