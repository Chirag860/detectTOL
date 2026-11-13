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

## Vector loops (Phase 3)

Derivations and reviewer check: `docs/reports/phase-3.md`. Status of each convention: `docs/DECISIONS.md` D22–D30.

| # | Assumption | Reason | Reference |
|---|---|---|---|
| A12 | Angles in a vector loop are **relative**: φ_j is the counter-clockwise angle from the previous vector's direction to vector j; φ_1 is measured from the global +x axis. Absolute direction Θ_j = φ_1 + … + φ_j. A change in one angle therefore rotates that vector and every vector after it. | Maintainer's choice (relative angles). Matches the usual vector-loop formulation. An angle toleranced from a datum on the drawing (absolute) must **not** be entered as relative: the sensitivities differ in sign and size (bracket test: +4.64 vs −30 mm/rad). | Maintainer decision 2026-11-12; Gao, Chase & Magleby (1998), abstract only. |
| A13 | The requirement is the projection of the open chain's resultant on a fixed measurement direction α, plus a constant: `Y = constant + Σ L_j cos(Θ_j − α)`. Positive Y points along α. α and the constant are exact (not toleranced). | Simplest sign rule that reproduces a 1D stack: vectors along +α add, vectors against it subtract. | Derived; `tests/core/test_loop.py`. |
| A14 | Worst case, RSS, contributions, P_fail and Cpk of a loop are **linearised**: sensitivities `a_i = ∂Y/∂x_i` at the means, `mean_Y = Y(μ)`. The second-order mean shift is ignored, the linear worst case is not a true bound, and a variable whose sensitivity is zero at the mean contributes nothing. Monte Carlo uses the exact Y. | Spec §3.4. The tool reports `ZERO_SENSITIVITY` and `LINEARISATION_SUSPECT` when the linear model is visibly wrong. | Spec §3.4; math-review.md item 22. |
| A15 | Lengths are millimetres and angles radians. An angle contributor's nominal, tolerances and sigma are in radians and its sensitivity in mm/rad. All variables are independent. Only open 2D chains: no closed loops, no kinematic adjustment between mating parts, no 3D. | Spec rule 5. Scope kept to what the Phase 3 closed-form tests cover. | root.md §0, Phase 3. |

## 3D vector loops

| # | Assumption | Reason | Reference |
|---|---|---|---|
| A16 | In a 3D loop every vector has three **relative** angles. The frame of vector j is the previous frame rotated by yaw ψ (about z), then pitch β (about the new y), then roll ρ (about the vector's own axis): `R_j = R_{j−1}·Rz(ψ)·Ry(β)·Rx(ρ)`, right-handed. The vector points along local x. For a single vector: direction = (cos ψ cos β, sin ψ cos β, −sin β), so **positive pitch tilts towards −z**. Roll never moves its own vector, only later ones. `Y = constant + n̂ · Σ L_j R_j e_x`. | A 3D chain needs a complete frame per vector; yaw-pitch-roll about the moving axes is one standard choice and reduces to the 2D convention (A12) when pitch = roll = 0. The pitch sign surprises people who expect "positive = up". | Implementer's choice (D37, provisional). Derivations: `tests/core/test_loop3d.py`. |

## GD&T conversions (Phase 4)

**Every row here NEEDS HUMAN REVIEW against ASME Y14.5-2018 by a qualified person.** The standard is paywalled and was not consulted. The section numbers in the last column are from memory of the 2018 edition's chapter layout and are **not verified**.

| # | Convention | Reason and known weakness | ASME Y14.5-2018 (unverified) |
|---|---|---|---|
| A17 | **Flatness / parallelism**, zone width t → one extra contributor `0 ± t/2` along the stack direction (normal by default). | Spec text. Weakness: under the envelope principle (Rule #1) form error of a feature of size is already inside its size limits, so adding flatness on top of size double-counts; that is conservative. Form error is also one-sided against a mating surface, not symmetric. (Question Q13, still open.) | Form: Section 8; Orientation: Section 9; Rule #1: 5.8.1 |
| A18 | **Position, RFS**, diametral zone T → along one stack direction, a contributor `0 ± T/2`, normal, σ = T/(6·cp). | Maintainer's choice ("normal, 3 sigma", Q9). Consistent in 2D with an isotropic bivariate normal of σ = T/6 per axis. Weakness: the radial deviation is then Rayleigh, and exp(−4.5) = 1.1 % of parts lie outside the cylindrical zone at cp = 1 (against 0.27 % in 1D). | Position: Section 10 |
| A19 | **Position at MMC / LMC**: bonus `B = |actual size − MMC size|` (LMC callout: `|actual size − LMC size|`); zone `T + B`; deviation `δ = (T + B)/(6·cp)·z`, z ~ N(0,1). Hole: MMC = smallest size, LMC = largest. Pin: the opposite. | Spec text (edit E9). Weaknesses: (a) the absolute value gives a "bonus" to a part beyond its size limit, which is really a reject (effect here: σ 0.0503105 vs 0.0503077); (b) it assumes the process fills whatever zone is allowed — a conservative convention, not a process model; (c) the bonus is legitimate because clearance grows with it, so position at MMC should be judged together with size in the functional requirement; against a *fixed* positional limit the failure rate goes up, not down (test `test_bonus_tolerance_raises_…`, question Q12). | Position / material condition modifiers: Section 10 |
| A20 | Linearised values for MMC/LMC position: worst-case half-range `(T + size range)/2`; σ = √E[(T+B)²]/(6·cp). The output is a scale mixture of normals, so the normal-theory P_fail is approximate (25 % low in the test case); Monte Carlo is exact for the model. | Needed so that worst case and RSS have a number. The report does **not** yet warn about this non-normality. | — |
| A21 | **Perpendicularity / angularity**, zone width t over feature length Lf → angular tolerance `± atan(t/Lf)` rad on a loop vector; the translational effect at a point follows from the loop geometry. | Spec text. Weakness: assumes the whole zone is used by tilt (no form error) and that the vector really extends as far as modelled; projected to a longer vector it gives more than t. | Orientation: Section 9 |
| A22 | **Datums**: primary / secondary / tertiary **planar** datum features only. Labels and precedence are validated; the frame is *not* used to compute directions — the user supplies each sensitivity. No datum targets, no material modifiers on datums, no common datums (A-B), no non-planar datum features. | Smallest model that lets callouts be checked for consistency. | Datum reference frames: Section 7 |

## STEP input (Phase 5)

| # | Assumption | Reason | Reference |
|---|---|---|---|
| A23 | Lengths from a STEP file are millimetres as delivered by OCCT. Face index = position in OCCT's `TopExp_Explorer` order within a part; it is stable for one file but not guaranteed across CAD re-exports, which is why annotation files also carry a centroid/normal fingerprint. | OCCT converts the file's length unit on import. | `docs/reports/phase-5.md` |
| A24 | OCCT returns the lower deviation of a ± tolerance as a magnitude; the reader restores the minus sign. A dimension whose lower deviation is positive in the file (e.g. +0.2/+0.1) cannot be distinguished and would be read as +0.2/−0.1. | Checked against the text of NIST CTC-01 (six ± dimensions). | `tests/cad/test_nist.py` |
| A25 | Shapes without any face (wireframe or annotation geometry stored beside the solid) are not parts and are skipped, with a note. Dimension labels of type "DimensionPresentation" are graphical annotations without a value and are not returned as dimensions. | Observed in every NIST file. | `docs/reports/phase-5.md` |

## Not yet decided

Open questions Q1–Q15 in `docs/reports/phase-R.md`. In particular: zero-tolerance contributors (Q4), Bender cap-or-warn (Q5), vector-loop angle and sign conventions (Q8), position-tolerance distribution (Q9), and every GD&T convention of Phase 4 (no ASME Y14.5-2018 reference has been verified).
