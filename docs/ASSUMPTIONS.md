# Modelling assumptions

Every assumption the math relies on, with its reason and a reference. Approved by the maintainer on 2026-11-12 (Phase R gate). Derivations: `docs/research/math-review.md`.

| # | Assumption | Reason | Reference |
|---|---|---|---|
| A1 | An asymmetric tolerance is re-centred on its midpoint: `μ = nominal + (U+L)/2`, `t = (U−L)/2`. The process is assumed centred on that midpoint, not on the nominal. | Gives an equal-bilateral tolerance, which every stack formula needs. A process that targets the nominal instead is not modelled. | Algebra; Scholz (1995) §2 notes asymmetric intervals are rarely treated in the literature. |
| A2 | Normal contributor: `σ = t/(3·cp)`. | Follows from `Cp = (USL − LSL)/(6σ)` with `USL − LSL = 2t`. cp = 1 means 0.27 % of parts are out of tolerance. | NIST/SEMATECH e-Handbook §6.1.6. https://www.itl.nist.gov/div898/handbook/pmc/section1/pmc16.htm |
| A3 | Uniform contributor over `[μ−t, μ+t]`: `σ = t/√3`. | Variance of a uniform distribution is (width)²/12. | Definition; Scholz (1995) Table 1 (factor 1.732). |
| A4 | Truncated-normal contributor: underlying normal with `σ0 = t/(3·cp)`, truncated at `μ ± t`; `σ = σ0·√(1 − 2kφ(k)/(2Φ(k) − 1))`, `k = 3·cp`. | Models parts that are inspected and rejected outside tolerance. k = 3 → 0.986578·σ0. | Derived in math-review.md item 5; verified by reviewer subagent. |
| A5 | Contributors are statistically independent. | Required for `σ_Y² = Σ aᵢ²σᵢ²`. Parts from one lot may be correlated; that makes RSS optimistic. | Scholz (1995) §4.1. |
| A6 | Analytic P_fail, Cpk/Cpu/Cpl and "μ_Y ± 3σ_Y = 99.73 %" assume Y is normal. Exact only for linear stacks with all-normal inputs. | Central limit theorem; fails with few contributors, one dominant contributor, or non-normal inputs. | Scholz (1995) §4.2; NIST e-Handbook §6.1.6. |
| A7 | Worst case uses the tolerance limits `μ_Y ± Σ|aᵢ|tᵢ`. Samples from an unbounded `normal` contributor can fall outside it in Monte Carlo. | Worst case is a statement about tolerance limits, not about the sampling distribution. | Scholz (1995) §3. |
| A8 | Monte Carlo failure fraction: Wilson interval, two-sided 95 % (z = 1.959964). With zero failures: exact one-sided 95 % upper bound `1 − 0.05^(1/N)` (≈ 3/N). | The two bounds are different confidence statements and are labelled as such. | NIST e-Handbook §7.2.4.1; Hanley & Lippman-Hand, JAMA 249:1743 (1983). |
| A9 | The Monte Carlo convergence check (std at N/2 vs N, warn above 1 %) is a heuristic, not a proof of convergence. It does not test the failure fraction; the Wilson interval does. | No authoritative source found for the criterion; at N = 100 000 the threshold is about 4.5 standard deviations. | math-review.md item 19. |
| A10 | Modified (Bender) RSS: `half-range = k·√(Σ(aᵢtᵢ)²)`; uses `tᵢ` directly and ignores cp and distribution. | Empirical inflation factor, k = 1.5. Can exceed worst case for few contributors; a warning is reported. | Bender (1962) as cited by Scholz (1995) §4.2. Primary not read. |
| A11 | Units are millimetres and radians internally. Finite-difference step `h = max(1e-6, 1e-4·t)` is in the contributor's own unit. | Spec rule; step is near the unscaled optimum ε^(1/3) for central differences. | root.md §0, §3.4; math-review.md item 23. |

## Not yet decided

Open questions Q1–Q15 in `docs/reports/phase-R.md`. In particular: zero-tolerance contributors (Q4), Bender cap-or-warn (Q5), vector-loop angle and sign conventions (Q8), position-tolerance distribution (Q9), and every GD&T convention of Phase 4 (no ASME Y14.5-2018 reference has been verified).
