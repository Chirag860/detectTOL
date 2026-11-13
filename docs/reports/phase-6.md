# Phase 6 report — building stack chains from CAD

2026-11-13. Windows 11, conda env, Python 3.12.16, pythonocc-core 8.0.1.2.

## Done

- `detecttol.cad.chain`
  - `find_contacts(model, tol)`: planar contacts between different parts (opposite normals, same plane within `tol`, overlapping extents), plus a list of touching face pairs that are not both planar.
  - `build_chain(model, face_from, face_to, dimensions, direction=None, tol=1e-6)`: the dimension chain between two named faces, projected on the measurement direction. Sensitivities (+1 / −1) come from the geometry; nominals are measured on the model.
- `detecttol.cad.step_stack`: a `schema_version: 3` YAML file that names a STEP file, the two faces of the requirement, the tolerances (annotation entries) and the analysis.
- `detecttol analyze file.yaml` accepts that file directly and writes the usual report; the description records the chain that was found.
- Three synthetic assemblies with committed STEP files in `examples/step/` (regenerate with `python examples/step/generate.py`).
- Reported instead of guessed: no path, several paths (all listed), non-planar contacts, a chain dimension without a tolerance, a requirement face that is not perpendicular to the measurement direction.
- The contact tolerance is a parameter (`contact_tolerance`, default 1e-6 mm as in the spec).

## Gate: end-to-end STEP → report for at least 3 synthetic assemblies

Met. Real output of `detecttol analyze examples/step/<file>.yaml`:

| Assembly | Chain found | Mean | Worst case | Sigma | Predicted failure | Expected by hand |
|---|---|---|---|---|---|---|
| plate_stack (golden case A) | PLATE_3 → PLATE_2 → PLATE_1 → HOUSING | 0.2 | [−0.05, 0.45] | 0.0440959 | 2.87236 ppm | same as the YAML golden case |
| stacked_blocks | BASE → PLATE | 26.6 | [26.45, 26.75] | 0.0372678 | 0.0802511 ppm | 26.6; ±0.15; √0.0125/3 = 0.0372678 |
| step_height | TOWER_A → BASE → TOWER_B | 0.5 | [0.4, 0.6] | 0.0235702 | 22.0905 ppm | 0.5; ±0.1; √(2·0.05²)/3 = 0.0235702 |

**"Golden case A rebuilt as an actual STEP assembly must give identical results to the YAML version": met.** `test_golden_case_a_from_step_is_identical_to_the_yaml_version` compares the complete result object, Monte Carlo statistics included, for equality; only the description differs.

## Test results

Real output of the final run:

```
src\detecttol\cad\chain.py             142      5     58      6    94%
src\detecttol\cad\step_stack.py         83      2     10      0    98%
TOTAL                                 2549     51    694     41    97%
333 passed in 25.37s
mypy: Success: no issues found in 8 source files
```

Without pythonocc (import blocked): `250 passed, 6 skipped`.

- 28 new tests; all passed on their first run.
- Lint: two over-long lines were reported by that run and shortened afterwards; the final `ruff check` line is in the CI section.

## Golden values and who verified them

| Value | Me | Reviewer | Independent script |
|---|---|---|---|
| Plate stack = golden case A | ✔ | (case A: ✔ in Phase 1) | ✔ (case A values) |
| Stacked blocks: 26.6, ±0.15, σ 0.03726780, Cpk 1.788854 | ✔ | not sent | σ equals case B's (√0.0125/3), which is ✔ |
| Step height: 0.5, ±0.1, σ 0.02357023, Cpk 1.414214 | ✔ | not sent | not covered |
| Contacts of the plate stack: 3 vertical + 6 lateral = 9 | ✔ (by construction) | — | — |

Phase 6 is not a "math phase" in root.md's rule 8, so no reviewer subagent was required. The two rows marked "not sent" rest on my derivation alone.

## New assumptions added to ASSUMPTIONS.md

A27 (what a contact is; overlap judged on bounding boxes), A28 (chain rules: only contacts perpendicular to the measurement direction; nominals rounded to 1e-9 mm; contributor order follows the annotation order).

## Known limitations / open risks

- **Planar contacts only**, and only stacks along one straight direction. No tilt, no clearance fits, no pins in holes.
- **Overlap is judged on axis-aligned bounding boxes.** Exact for rectangular faces aligned with the axes (everything tested). For L-shaped or rotated faces it can report a contact where the faces only share a bounding box.
- **One path only.** Over-constrained assemblies (two parallel load paths) are refused; the user cannot yet pick a path.
- **Tolerances come from the annotation entries**, matched by the exact two faces of the chain. PMI read from the STEP file is not yet used to supply them automatically, and GD&T callouts are not added to these stacks.
- Tested only on synthetic assemblies of boxes, one slotted box and one cylinder. **No real CAD assembly has been run.**
- A part name must be unique in the assembly.

## Items needing human review

1. Run it on one of your own assemblies (see README, "Your own STEP file") and tell me where it breaks.
2. Decide how an over-constrained assembly should be handled: pick a path by name, or analyse each path.

## Proposed plan for Phase 7

- `validation/`: cases with reference results that **you** supply (hand calculation, textbook example or TolAnalyst output). I cannot fabricate these; the folder currently holds only the independent recomputation script.
- Docs: theory page, GD&T conventions, limitations, contributing.
- Release to PyPI needs your account and a decision on the pythonocc licence question.

## CI for this phase

CI_PHASE6_RESULT
