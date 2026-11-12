# Phase R report

2026-11-12. Research only: no library code, no edits to root.md, no git repo created.
Detail: `docs/research/domain-notes.md`, `docs/research/math-review.md`, `docs/research/feasibility.md`.

## Done

- R1 domain notes, R2 math audit (27 items), R3 gap list (below), R4 feasibility note, this report.
- 24 of ~25 searches/fetches used.
- Section 3 is mostly sound. Golden case A reproduces exactly.
- Found **2 errors**, **4 underspecified items** that block implementation, and 9 caveats.
- **Not done:** R4 asked for throwaway scripts against pythonocc. None was run — no conda on this machine (Q1).
- **Weak:** the commercial-tools section of the domain notes is background knowledge, not verified against vendor documentation.

## Test results

No code, so no pytest/coverage/ruff/mypy output. The only executed check was a stdlib script (`math.erfc`) for the numbers below.

## Golden values and who verified them

| Value | Me | Reviewer subagent | Human |
|---|---|---|---|
| Case A: μ_Y = 0.20; WC ±0.25 → [−0.05, 0.45] | ✔ | ✔ | pending |
| Case A: 3σ_Y = 0.1322876, σ_Y = 0.04409586, RSS range [0.0677124, 0.3322876] | ✔ | ✔ | pending |
| Case A: WC contrib 40/20/20/20 %; RSS 57.142857 / 14.285714 % | ✔ | ✔ | pending |
| Case A: z = −4.535574, P_fail = 2.872356e-6 (2.87 ppm), Cpl = 1.511858 | ✔ | ✔ | pending |
| 10.0 +0.2/−0.0 → μ 10.1, t 0.1 | ✔ | ✔ | pending |
| Truncated-normal σ factor: k=3 → 0.986578, k=2 → 0.879626 | ✔ | ✔ | pending |
| Wilson 95 %, N=1e5: x=0 → [0, 3.84131e-5]; x=3 → [1.02028e-5, 8.82080e-5] | ✔ | ✔ | pending |
| Exact one-sided 95 % bound, x=0, N=1e5: 2.995687e-5 (3/N = 3.0e-5) | ✔ | ✔ | pending |
| Uniform disk of diameter T: σ_x = T/4 (vs T/6 for the 1D convention) | ✔ | ✔ | pending |
| Y = 100·cos θ, θ~N(0, 0.01²): mean 99.995000, σ 7.0707e-3; linearised σ = 0 | ✔ | ✔ | pending |

## Reviewer subagent findings and resolutions

The reviewer received Section 3 and a list of questions only — none of my values or reasoning.

- **Agreement on every number** in the table above. No disagreement to resolve.
- Independently confirmed both counter-examples to the "WC ≥ RSS always" property, and that `1.5·RSS` exceeds worst case for n ≤ 2 equal contributors.
- Extra points it raised, all adopted into this report:
  - One dominant contributor also makes `1.5·RSS > WC` (t = 1, 0.1, 0.1, 0.1 → 1.522 vs 1.3).
  - n = 3 equal uniform contributors gives *exact equality* of RSS 3σ and WC — a float-rounding trap for a `≥` property test.
  - Wilson's upper limit at x = 0 has ~97.85 % one-sided coverage, so the report would jump from 30 ppm (rule of three) to a 38.4 ppm Wilson limit for the same data.
  - Finite differences: with a large tolerance (t = 10 → h = 1e-3) truncation error can exceed 1e-6 relative; a large |f| with a small derivative gives ~1e-4 relative round-off.
  - A zero or near-zero sensitivity should be flagged in the linear results.
- One reviewer point I did **not** adopt as stated: "one-sided specs are not handled in P_fail". The spec does say "with one-sided specs supported"; the real gap is only Cpk (edit E4).

## Gate outcome

- 2026-11-12: maintainer approved E1–E9 ("Approve all"). E1–E8 applied to root.md as worded. `docs/ASSUMPTIONS.md` created.
- E9: the LMC bonus formula was corrected. The wrong test expectation was removed and marked open; its replacement waits on Q12.
- E7: "warn" applied as the minimum; cap-or-warn still waits on Q5.
- Q1–Q15 remain unanswered. Phase 0 not started.

## Corrections needed (exact proposed edits — applied after approval, see Gate outcome)

**E1 — §3.1, heading "Mean-shift for asymmetric tolerances (mandatory)"**
Replace with: "Midpoint re-centring of asymmetric tolerances (mandatory). Assumption: the process is centred on the tolerance midpoint, not on the nominal."
Reason: "mean shift" in the literature means the opposite (process off-centre). Formula unchanged.

**E2 — §3.1, sigma convention: add a line (currently missing; blocks Phase 1)**
"truncated_normal: underlying normal with σ0 = tᵢ/(3·cpᵢ), truncated at μ ± tᵢ. σᵢ = σ0·√(1 − 2kφ(k)/(2Φ(k) − 1)), k = 3·cpᵢ."
Needs the maintainer to confirm that truncation is at the tolerance limits.

**E3 — §3.2, RSS line: append**
"Assumes contributors are statistically independent. μ_Y ± 3σ_Y contains 99.73 % only if Y is normal. If 3σ_Y exceeds the worst-case half-range, report a warning."

**E4 — §3.2, Cpk: append**
"With a one-sided spec, report Cpu = (USL − μ)/(3σ) or Cpl = (μ − LSL)/(3σ) only. If σ_Y = 0, P_fail and Cpk are not computed; report pass/fail from μ_Y alone."

**E5 — Phase 1 property test (WRONG as written)**
Replace "WC half-range ≥ RSS 3σ half-range, always" with "…for stacks whose contributors are all normal or truncated_normal with cp ≥ 1 (compare with a small absolute tolerance, not strict ≥)."
Also "Scaling all tolerances by k" → "by k > 0".

**E6 — §3.3, zero-failure line**
Replace "report the upper bound (rule of three: ≈ 3/N)" with "report the exact one-sided 95 % upper bound 1 − 0.05^(1/N) (≈ 3/N, the rule of three), labelled 'one-sided 95 %'. The Wilson interval is labelled 'two-sided 95 %'."

**E7 — §3.2, Bender line**
Replace "range = k·√(Σ(aᵢtᵢ)²)" with "half-range = k·√(Σ(aᵢtᵢ)²). Uses tᵢ directly; cp and distribution are ignored. Source: Bender (1962), k = 1.5." Plus the cap/warn decision of Q5.

**E8 — §3.4, finite differences: append**
"h is in the contributor's own unit (mm or rad). Analytic-vs-FD tests use both rel = 1e-6 and an abs tolerance, because relative error is undefined at zero sensitivity."

**E9 — Phase 4 bonus-tolerance test (WRONG as I read it — GD&T, maintainer decides)**
"MC failure must be lower than the RFS equivalent": a bonus enlarges the position zone, so stack variation and gap-failure rate go *up*. Also "bonus = |actual size − MMC size|" is written for both MMC and LMC; for LMC the departure should be from LMC.

## New assumptions to add to ASSUMPTIONS.md (after approval)

1. Asymmetric tolerances are re-centred on the midpoint; the process is assumed centred there.
2. `σ = t/(3·cp)` for normal — from Cp = (USL − LSL)/(6σ), NIST e-Handbook §6.1.6.
3. `σ = t/√3` for uniform.
4. Truncated-normal definition (E2), if approved.
5. Contributors are statistically independent.
6. Analytic P_fail and Cpk assume a normal Y; exact only for linear stacks with all-normal inputs.
7. Worst case uses tolerance limits; unbounded `normal` samples in MC can fall outside it.
8. Wilson interval is two-sided 95 %; the zero-failure bound is one-sided 95 %.
9. The N/2-vs-N std comparison is a heuristic, not a convergence proof.

## Proposed additions (R3)

| Item | Class | Reason |
|---|---|---|
| Truncated-normal definition | MUST-ADD-NOW | Listed in the spec but cannot be implemented as written. |
| Independence stated; warning when 3σ > WC | MUST-ADD-NOW | Documentation plus one comparison; prevents physically impossible ranges in reports. |
| Flag analytic P_fail as approximate when any input is non-normal | MUST-ADD-NOW | ppm tails are the least reliable output outside the all-normal case. |
| `norm.sf` for the upper tail | MUST-ADD-NOW | Implementation detail; avoids precision loss at ppb level. |
| Process mean shift / drift per contributor (Mansoor; Greenwood & Chase) | LATER | Real and well documented, but changes the schema; reserve a field name now. |
| Assembly shift / float in clearance fits | LATER | Can be modelled today as a uniform contributor of ± clearance/2; document the recipe. |
| Skewed / triangular / empirical distributions | LATER | Scholz Table 1 lists factors; MC handles them once defined. |
| Correlated contributors | LATER | Needs a covariance input. Note: three plates from one lot (golden case A) may well be correlated. |
| Second-order mean shift (system moments) | LATER | MC already covers it; linear results get a zero-sensitivity warning meanwhile. |
| Several requirements per file (gap *and* flush) | LATER | Schema currently holds one `requirement`. |
| Thermal expansion | LATER | Deterministic nominal shift; user can pre-compute. |
| Tolerance allocation, cost-vs-tolerance | OUT-OF-SCOPE (v0.1) | Synthesis, not analysis. |
| Full 3D feature variation (SDT / Jacobian-torsor, T-Maps) | OUT-OF-SCOPE | Beyond the Phase 4 subset by the spec's own non-goals. |

## Known limitations / open risks

- **PMI reading unproven.** OCCT 7.8/7.9 reportedly returns no tolerance magnitude for NX/NIST AP242 files; "probably fixed" in 8.0. A Python-binding defect in the same area is open on OCP. Phase 5 may end up on the YAML fallback.
- **ASME Y14.5-2018 not consulted** (paywalled). No Phase 4 convention has a verified section reference.
- Primaries not read: Bender (1962), Gladman, Evans (1975), Cox (1986), Chase vector-loop papers (abstracts only).
- Convergence criterion has no source; it is a 4.5-sd event at the default N.
- The reviewer shares my model family; agreement on arithmetic is strong evidence, agreement on interpretation is weaker. Human check still needed.

## Items needing human review (open questions)

- **Q1.** May I install Miniforge/micromamba to run the pythonocc PMI check, or will you run it? (Currently: Python 3.14 only, no conda.)
- **Q2.** Truncated normal: truncate at μ ± t with σ0 = t/(3cp) (E2)? Something else?
- **Q3.** "Constant term" in μ_Y: add a `constant` field to the YAML requirement, or drop it from §3.2?
- **Q4.** `upper_tol == lower_tol` (t = 0): allowed? If every contributor has t = 0, contributions are 0/0 — raise an error or report "n/a"?
- **Q5.** Bender: when `k·RSS > WC`, cap at WC or only warn?
- **Q6.** Non-normal warning: any-non-normal-input (my proposal), or a dominance threshold you supply?
- **Q7.** Convergence check: keep as specified, or compare two independent halves?
- **Q8.** Vector loops: relative or absolute angles? Loop direction and gap sign? Zero-angle reference?
- **Q9.** Position tolerance: disk-uniform (σ = T/4) and 1D "±T/2 normal" (σ = T/6) disagree by 1.5×. Which is the convention?
- **Q10.** Units: is `mm` the only accepted value, or also `inch` (converted at input)? How are angle units declared in Phase 3?
- **Q11.** If `seed` is missing from the YAML: reject, or use a documented default?
- **Q12.** E9 — what was the bonus-tolerance test meant to show?
- **Q13.** Flatness/parallelism as ±t/2 added on top of size: under the envelope principle form is already inside the size limits, so this may double-count. Your call or a GD&T reference's.
- **Q14.** §6b says "read only SPEC.md"; the file is `root.md`. Rename, or is a SPEC.md coming?
- **Q15.** LGPL-3.0 pythonocc under an Apache-2.0 project: acceptable to you?

## Proposed plan for Phase 0

Only after approval of the edits above.

- `git init`; skeleton `src/detecttol/{core,gdt,cad,io,report,cli}`; `pyproject.toml`, `environment.yml`, ruff, mypy, pre-commit.
- CI matrix on three OSes, with a separate pip-only job for `core/`.
- `docs/ASSUMPTIONS.md` seeded with the approved assumptions; `docs/DECISIONS.md` with the answers to Q1–Q15.
- One smoke test. Gate: CI green, clean-clone `conda env create` + `pytest` verified.
- Needs from you: a GitHub repo, and conda available locally.
