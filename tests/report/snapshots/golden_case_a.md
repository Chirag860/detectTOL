# Tolerance stack report: plate_stack_in_slot

gap between top plate and slot ceiling

## Input summary

- Units: mm
- LSL: 0
- USL: n/a
- Constant term: 0
- Input file: examples/golden_case_a.yaml

| Contributor | Nominal | Upper tol | Lower tol | Sensitivity | Distribution | Cp | Mean | Half-range t | Sigma |
|---|---|---|---|---|---|---|---|---|---|
| slot_depth | 50 | 0.1 | -0.1 | 1 | normal | 1 | 50 | 0.1 | 0.0333333 |
| plate_1 | 16.6 | 0.05 | -0.05 | -1 | normal | 1 | 16.6 | 0.05 | 0.0166667 |
| plate_2 | 16.6 | 0.05 | -0.05 | -1 | normal | 1 | 16.6 | 0.05 | 0.0166667 |
| plate_3 | 16.6 | 0.05 | -0.05 | -1 | normal | 1 | 16.6 | 0.05 | 0.0166667 |

## Results

- Mean of Y: 0.2 mm

### Worst case

- Half-range: 0.25
- Range: [-0.05, 0.45]
- Meets spec: NO

### RSS (statistical)

- Sigma: 0.0440959
- 3-sigma half-range: 0.132288
- Mean +/- 3 sigma: [0.0677124, 0.332288]
- Predicted failure (normal assumption): 2.87236e-06 = 2.87236 ppm
- Cpl: 1.51186
- Cpu: n/a
- Cpk: 1.51186

### Monte Carlo

- Samples N: 100000
- Seed: 42
- Mean: 0.199786
- Std: 0.0442297
- Min / max: 0.00704677 / 0.38876
- Percentiles 0.135 / 2.5 / 50 / 97.5 / 99.865: 0.0692605 / 0.112857 / 0.199862 / 0.286609 / 0.334234
- Outside spec: 0 of 100000 observed. Not 0 ppm: failure rate < 29.9569 ppm (one-sided 95 % upper bound)
- Wilson interval (two-sided 95 %): [0, 38.4131] ppm
- Convergence (std at N/2 vs N): 0.0442219 vs 0.0442297, converged

![Monte Carlo histogram](plate_stack_in_slot_histogram.png)

## Contributions (sorted, largest first)

| Contributor | RSS % | Worst case % |
|---|---|---|
| slot_depth | 57.14 | 40.00 |
| plate_1 | 14.29 | 20.00 |
| plate_2 | 14.29 | 20.00 |
| plate_3 | 14.29 | 20.00 |

## Warnings

- **WORST_CASE_FAILS_SPEC**: Worst-case range [-0.05, 0.45] mm is not inside the spec.
- **MC_ZERO_FAILURES**: 0 failures in 100000 samples. This is not 0 ppm: the one-sided 95 % upper bound on the failure rate is 29.96 ppm.

---

detecttol 0.0.0-test | report schema v1 | seed 42 | generated 2026-01-01T00:00:00Z
