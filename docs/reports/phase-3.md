# Phase 3 report — 2D nonlinear vector loops

2026-11-12. Maintainer instruction: "continue with phase 3, and choose relative angles".

## Done

- `detecttol.core.loop`: an open chain of 2D vectors, each with a length [mm] and a **relative** angle [rad]; lengths and angles can be toleranced or fixed.
  - `Y = constant + Σ L_j cos(Θ_j − α)`, `Θ_j = φ_1 + … + φ_j`.
  - Analytic sensitivities: `∂Y/∂L_j = cos(Θ_j − α)`, `∂Y/∂φ_k = −Σ_{j≥k} L_j sin(Θ_j − α)`.
  - Central finite-difference sensitivities with `h = max(1e-6, 1e-4·t)`, returned beside the analytic ones.
  - Linearised worst case / RSS / P_fail / Cpk; Monte Carlo on the exact function.
  - Two warnings when the linear model is visibly wrong: `ZERO_SENSITIVITY`, `LINEARISATION_SUSPECT`.
- `analyze()` was refactored so the 1D engine and the loop engine share one code path (`analyze_linearised`). The 111 earlier tests pass unchanged.
- 22 new tests covering all five required items.
- **Phases 0 and 2 gate, now met:** the first CI run (commit `f49a296`) finished green on all 9 jobs — pip route on Ubuntu, macOS, Windows × Python 3.11/3.12, and the conda route on the three OSes.

### Not done

- **3D loops.** The phase title says 2D/3D; only 2D exists (decision D25).
- **No YAML, CLI or report support for loops** — Python API only (decision D26, root.md §8).
- Closed loops and kinematic adjustment between mating parts.

## Test results

Windows 11, conda env (Python 3.12.16). Real output:

```
src\detecttol\core\analyze.py          67      0     24      0   100%
src\detecttol\core\linear.py           44      0     12      0   100%
src\detecttol\core\loop.py            183      0     42      0   100%
src\detecttol\core\models.py           89      0     20      0   100%
src\detecttol\core\montecarlo.py       65      0     18      0   100%
src\detecttol\core\results.py          92      0      0      0   100%
TOTAL                                 750      3    158      3    99%
133 passed in 11.73s
ruff check: Found 2 errors (2 fixed, 0 remaining).
mypy: Success: no issues found in 7 source files
```

- The two ruff findings were auto-fixable style items in the new test file; a formatter pass reformatted one file.
- All 22 loop tests passed on their first run. No expected value was changed.
- CI for the Phase 3 commit: see the last section of this report.

### Required tests

| Required by root.md | Test | Result |
|---|---|---|
| 1D chain as a loop reproduces golden case A exactly | `test_1d_chain_reproduces_golden_case_a_exactly` | Whole `StackResult` **bit-identical** to the 1D engine, including the 20 000 Monte Carlo samples |
| Tilted pin: ∂/∂θ = L·cos θ = 100 mm/rad at 0; MC vs direct sampling of L·sin θ | `test_tilted_pin_sensitivity_and_linearised_result`, `test_tilted_pin_monte_carlo_matches_direct_sampling_of_l_sin_theta` | Sensitivity 100.0; every one of 200 000 samples within 1e-12 mm of the direct sample |
| A 2D triangle/angle case with a closed form | `test_wedge_height_with_angle_tolerance`, two bracket tests | Pass |
| Analytic vs FD within 1e-6 relative | `test_analytic_and_fd_sensitivities_agree_on_the_bracket`, plus a hypothesis test on random loops | Observed relative errors 5e-11 … 1.4e-9 |
| Linear-vs-MC consistency, and a documented divergence | `test_linear_and_monte_carlo_agree_for_small_tolerances`, `test_large_tolerance_divergence_…`, `test_zero_sensitivity_is_reported_not_hidden` | Pass (numbers below) |

## End-to-end runs inspected by hand

N = 200 000, seed 1. "Linear" = linearised closed form; "MC" = exact function.

| Case | Linear σ_Y | MC std | Difference | Verdict |
|---|---|---|---|---|
| Pin, θ = 0 ± 0.03 rad | 1.0 | 0.998733 | −0.13 % (0.8 SE) | Consistent |
| Pin, L = 100 ± 0.2, θ = 0.3 ± 0.006 | 0.192080 | 0.191576 | −0.26 % (1.7 SE) | Consistent |
| Wedge, L = 80 ± 0.1, θ = 15° ± 0.5° | 0.224947 | 0.224367 | −0.26 % (1.6 SE) | Consistent |
| Bracket, x-distance | 0.0572952 | 0.0572434 | −0.09 % (0.6 SE) | Consistent |
| Pin, θ = 0 ± 0.9 rad | 30.0 | 28.6556 | **−4.5 % (28 SE)** | Diverges, flagged. Exact value 28.6993 |
| Pin along its axis, Y = 100·cos θ | **0** | 0.00710618 | linear model blind | Flagged twice. Exact 0.00707071; mean 99.99501 vs exact 99.99500 |

- The three "consistent" rows share seed 1, so their similar −0.26 % offsets are the same random draws, not a bias: the exact-vs-linear gap for the second row is 1.7e-6.
- A sign error in an angle sensitivity would show in the bracket cross-check (`∂Y_x/∂φ_1 = −Y_y`), which is tested.

## Golden values and who verified them

"Reviewer" = separate subagent given the conventions and the case definitions only — no code, none of my numbers. Human verification is pending for every row.

| Case | Values | Me | Reviewer | Human |
|---|---|---|---|---|
| General formulas | ∂Y/∂L_j = cos(Θ_j − α); ∂Y/∂φ_k = −Σ_{j≥k} L_j sin(Θ_j − α) | ✔ | ✔ | pending |
| 1D chain (case A) | Θ = (0, π, π, π); sensitivities (+1, −1, −1, −1); μ_Y 0.20; WC 0.25; 3σ 0.1322876; P_fail 2.872356e-6 | ✔ | ✔ | pending |
| Tilted pin, θ = 0 ± 0.03 | ∂Y/∂θ 100; WC 3.0; σ 1.0; exact std 0.9999500 | ✔ | ✔ | pending |
| Pin off zero | ∂Y/∂L 0.2955202; ∂Y/∂θ 95.53365; mean 29.55202; WC 0.6323059; 3σ 0.5762410; σ 0.1920803; RSS 1.052025 / 98.94798 % | ✔ | ✔ | pending |
| Wedge | θ 0.2617994 rad, t 0.008726646 rad; mean 20.70552; sens 0.2588190 / 77.27407; WC 0.7002253 → [20.00530, 21.40575]; 3σ 0.6748399; RSS 0.1470926 / 99.85291 %; P_fail 1.865106e-3; Cpl 1.045468; Cpu 1.029098 | ✔ | ✔ | pending |
| Bracket, α = 0 | mean 71.96152; sens 0.8660254 / 4.641016 / 0.5 / 34.64102; WC 0.2937307; σ 0.05729517; RSS 25.38533 / 1.166454 / 8.461776 / 64.98644 % | ✔ | ✔ | pending |
| Bracket, α = π/2 | mean −4.641016; sens 0.5 / 71.96152 / −0.8660254 / 20.0; WC 0.5044486; σ 0.1050161; RSS 2.518755 / 83.47697 / 7.556266 / 6.448013 % | ✔ | ✔ | pending |
| Zero sensitivity | linear 0; exact mean 99.99500, std 0.007070714; excursion 0.04499663 | ✔ | ✔ | pending |
| Large tolerance | linear 30.0; exact 28.69928 | ✔ | ✔ | pending |
| Small-tolerance gap | exact std 0.1920800 vs linear 0.1920803 (1.7e-6) | reviewer's closed form; I did not derive it independently | ✔ | pending |
| Uniform angle | σ_θ 0.003464102; σ_Y 0.3309382; bounds [28.97829, 30.12468] | ✔ | not sent | pending |

Two rows are weaker than the rest and are marked so: one rests on the reviewer alone, one on me alone.

## Reviewer subagent findings and resolutions

- **Numbers:** agreed with every value I had derived; no disagreement to resolve.
- **Wedge worst case exceeds the USL by 0.0057 mm** — I had not noticed. Now asserted in the test (`meets_spec is False`).
- **Zero or near-zero sensitivity gives σ = 0 and no P_fail/Cpk.** Resolved by the `ZERO_SENSITIVITY` and `LINEARISATION_SUSPECT` warnings plus the existing `ZERO_VARIATION`; the linear numbers themselves stay as the spec defines them.
- **`Y(μ)` ignores the second-order mean shift** (−0.0050 mm in the cos case). Reported as `mc_mean_shift`; not corrected (D29).
- **The linear worst case is not a true bound.** Documented (A14). Not fixed: evaluating corners would not be a general fix either, as the reviewer notes.
- **Relative angles are a usability risk:** an angle toleranced from a datum, entered as relative, gives a wrong sensitivity (+4.64 vs −30 mm/rad in the bracket). Documented in A12 and in the module docstring. This is the main thing for the maintainer to weigh.
- **Degrees vs radians:** the API takes radians only; the wedge test converts explicitly. A future YAML format must carry an explicit angle unit.
- **α and the constant are fixed:** stated as a limitation (D30).
- Points already settled in Phase 1 (signed `lower_tol`, one-sided Cpk, cp ignored for uniform, MC zero-failure reporting): no action.

## New assumptions added to ASSUMPTIONS.md

A12 (relative angles), A13 (projection and sign), A14 (linearisation limits), A15 (units, independence, open 2D chains only).

## Known limitations / open risks

- **2D only**, Python API only (see "Not done").
- Decisions D23–D30 are mine and provisional.
- Linearised worst case and RSS are approximations; for large angular tolerances or zero sensitivities only Monte Carlo is right, and P_fail from the normal formula is unreliable there.
- `LINEARISATION_SUSPECT` uses the normal-theory standard error of the std; for strongly non-normal Y the 5 SE threshold is approximate.
- The finite-difference step is absolute, not scaled to the variable. Fine for mm and rad of ordinary size; a stack with |Y| above about 10 m could miss the 1e-6 agreement.
- The bit-identical match with the 1D engine was observed on Windows; on another platform `cos(π)` should still be exactly −1, but that is only proven once CI runs this commit.

## Items needing human review

1. Hand-check at least the wedge and the bracket rows above.
2. Confirm or change D23–D30, in particular D25 (3D) and D26 (input format).
3. Proposed YAML for loops, **not implemented** — needs approval as a schema change:

```yaml
schema_version: 2
units: mm
angle_units: deg          # required when any vector is present; deg or rad
name: wedge_height
requirement: {lsl: 20.0, usl: 21.4}
loop:
  measure_angle: 90
  vectors:
    - length: {id: L, nominal: 80.0, upper_tol: 0.1, lower_tol: -0.1}
      angle:  {id: theta, nominal: 15.0, upper_tol: 0.5, lower_tol: -0.5}
```

## Proposed plan for Phase 4

Not started. Blocked on three GD&T questions that only the maintainer or a GD&T reference can answer: Q9 (position-tolerance distribution: disk-uniform σ = T/4 vs 1D σ = T/6), Q12 (what the bonus-tolerance test should assert), Q13 (flatness on top of size under the envelope principle). No ASME Y14.5-2018 section reference has been verified.

## CI for this phase

Commit `55148ab` (Phase 3 code, tests and docs), GitHub Actions, queried from the GitHub API after the run completed:

```
sha=55148ab status=completed conclusion=success
core-pip (ubuntu-latest, 3.11): completed/success
core-pip (ubuntu-latest, 3.12): completed/success
core-pip (windows-latest, 3.11): completed/success
core-pip (windows-latest, 3.12): completed/success
core-pip (macos-latest, 3.11): completed/success
core-pip (macos-latest, 3.12): completed/success
conda (ubuntu-latest): completed/success
conda (windows-latest): completed/success
conda (macos-latest): completed/success
```

This also settles the open risk above: the bit-identical match between the loop engine and the 1D engine holds on Linux and macOS, not only on Windows.
