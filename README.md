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

## Read before trusting a number

- Every modelling assumption is in [docs/ASSUMPTIONS.md](docs/ASSUMPTIONS.md).
- Provisional design decisions awaiting maintainer review are in [docs/DECISIONS.md](docs/DECISIONS.md).
- Units are millimetres. Any other unit is rejected.

## License

Apache-2.0.
