# Tolerance stack report: wedge_height

height of the wedge tip above the base

## Input summary

- Units: mm
- LSL: 20
- USL: 21.4
- Constant term: 0
- Input file: examples/wedge_height.yaml

| Contributor | Unit | Nominal | Upper tol | Lower tol | Sensitivity | Distribution | Cp | Mean | Half-range t | Sigma |
|---|---|---|---|---|---|---|---|---|---|---|
| L | mm | 80 | 0.1 | -0.1 | 0.258819 | normal | 1 | 80 | 0.1 | 0.0333333 |
| theta | deg | 15 | 0.5 | -0.5 | 1.34869 | normal | 1 | 15 | 0.5 | 0.166667 |

## Results

- Mean of Y: 20.7055 mm
- Vector loop: worst case, RSS, predicted failure and Cpk below are LINEARISED about the means. Monte Carlo uses the exact geometry.

### Worst case

- Half-range: 0.700225
- Range: [20.0053, 21.4057]
- Meets spec: NO

### RSS (statistical)

- Sigma: 0.224947
- 3-sigma half-range: 0.67484
- Mean +/- 3 sigma: [20.0307, 21.3804]
- Predicted failure (normal assumption): 0.00186511 = 1865.11 ppm
- Cpl: 1.04547
- Cpu: 1.0291
- Cpk: 1.0291

### Monte Carlo

- Samples N: 100000
- Seed: 2
- Mean: 20.7049
- Std: 0.225545
- Min / max: 19.7711 / 21.6956
- Percentiles 0.135 / 2.5 / 50 / 97.5 / 99.865: 20.0318 / 20.2592 / 20.7061 / 21.1454 / 21.3773
- Outside spec: 184 of 100000 = 1840 ppm
- Wilson interval (two-sided 95 %): [1592.83, 2125.44] ppm
- Convergence (std at N/2 vs N): 0.225275 vs 0.225545, converged

![Monte Carlo histogram](wedge_height_histogram.png)

## Vector loop

- Angle convention: relative (counter-clockwise from the previous vector; first vector from global +x)
- Angles shown in: deg (sensitivities of angles in mm/deg)
- Measurement direction: 90 deg
- Monte Carlo std vs linearised sigma: 0.266 % (sampling error about 0.224 %)
- Monte Carlo mean minus Y at the means: -0.000657136 mm (standard error 0.000713235 mm)

| Variable | Kind | Unit | Vector | Sensitivity (analytic) | Sensitivity (finite diff.) | Linear effect [mm] | Exact effect [mm] |
|---|---|---|---|---|---|---|---|
| L | length | mm | 1 | 0.258819 | 0.258819 | 0.0258819 | 0.0258819 |
| theta | angle | deg | 1 | 1.34869 | 1.34869 | 0.674343 | 0.675123 |

## Contributions (sorted, largest first)

| Contributor | RSS % | Worst case % |
|---|---|---|
| theta | 99.85 | 96.30 |
| L | 0.15 | 3.70 |

## Warnings

- **WORST_CASE_FAILS_SPEC**: Worst-case range [20.0053, 21.4057] mm is not inside the spec.

---

detecttol 0.0.0-test | report schema v2 | seed 2 | generated 2026-01-01T00:00:00Z
