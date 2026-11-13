# Phase 4 report — GD&T subset (and 3D vector loops)

2026-11-13. Maintainer instruction: "normal 3 sigma but implement 3d loops and then go ahead with phase 4 and 5 without stopping".

This report covers two things: the 3D extension of Phase 3, and Phase 4.

## Done

### 3D vector loops

- `detecttol.core.loop3d`: relative yaw / pitch / roll per vector, a measurement direction given as a vector, analytic and finite-difference sensitivities, exact Monte Carlo. Convention in ASSUMPTIONS A16.
- YAML (`pitch`, `roll`, `measure_direction`), CLI and reports; example `examples/tilted_post_3d.yaml`.
- The 2D engine is untouched; a planar 3D loop is tested against it.

### GD&T (`detecttol.gdt`, Python API)

- Flatness and parallelism → contributor `0 ± t/2`.
- Position RFS → contributor `0 ± T/2`, normal, σ = T/(6·cp) (the maintainer's choice).
- Position at MMC / LMC with bonus, hole or pin; exact Monte Carlo that reuses the size samples; closed-form σ for the linear results.
- Perpendicularity / angularity → angle tolerance `± atan(t/Lf)` for a loop vector.
- Planar datum reference frames (primary / secondary / tertiary), validated.
- `analyze_gdt(GdtStack)` returns the ordinary `StackResult`.

### Not done

- No YAML, CLI or report support for GD&T callouts (decision D43).
- Orientation tolerances only in loops, not in 1D stacks.
- The report does not warn that an MMC/LMC position makes the output non-normal.
- **The gate needs the human to approve the conventions. That has not happened.**

## Test results

Windows 11, conda env (Python 3.12.16, pythonocc-core 8.0.1.2). Real output of the final run:

```
src\detecttol\core\loop3d.py          156      0     36      0   100%
src\detecttol\core\loop.py            181      0     42      0   100%
src\detecttol\gdt\analyze.py           68      0     26      0   100%
src\detecttol\gdt\models.py            99      0     14      0   100%
TOTAL                                1891     15    450     16    99%
274 passed in 24.08s
ruff check: All checks passed!
mypy: Success: no issues found in 8 source files
```

- New tests: 11 for 3D loops in the core, 13 for 3D through YAML/CLI/reports, 16 for GD&T. The core and GD&T tests passed on their first run; no expected value was changed.
- Three older tests failed when the 3D example was added, because they assumed every loop example is 2D. They were made to dispatch on the loop type; nothing about their expectations changed.
- One snapshot changed deliberately: `wedge_height.json` gained `"measure_direction": null` (new field of report schema v2). The diff is that single line.
- CI result for this commit: see the end of `phase-5.md`.

## Golden values and who verified them

"Reviewer" = separate subagent given the conventions and the case definitions only — no code, none of my numbers. Human verification is pending on every row.

### 3D loops

| Case | Values | Me | Reviewer | Human |
|---|---|---|---|---|
| Single vector, L 50 ± 0.1, yaw 30° ± 0.2°, pitch 20° ± 0.2°, n = x | mean 40.68988; sens 0.8137977 / −23.49232 / −14.80991; W 0.2150797; σ 0.04218975 | ✔ | ✔ | pending |
| same, n = y | mean 23.49232; sens 0.4698463 / 40.68988 / −8.550504; W 0.2188660; σ 0.05085075 | ✔ | ✔ | pending |
| same, n = z | mean −17.10101; sens −0.3420201 / 0 / −46.98463; W 0.1982093; σ 0.05584520 | ✔ | ✔ | pending |
| Roll coupling, n = z | Y = 40·sin 10° = 6.945927; sens 39.39231 / 0.1736482; W 0.3524452; σ 0.1146241 | ✔ | ✔ | pending |
| Roll coupling, n = y | 39.39231; sens −6.945927 / 0.9848078; W 0.1098550; σ 0.02603150 | ✔ | ✔ | pending |
| Box diagonal 3-4-12 | P = (3, 4, 12); Y = 13 along the diagonal; ∂P/∂yaw₂ = (−4, 0, 0) | ✔ | ✔ | pending |
| Planar reduction | equals the 2D bracket: 71.96152; 0.8660254 / 4.641016 / 0.5 / 34.64102 | ✔ | ✔ | pending |
| Degree display (example file) | roll sensitivity 39.39231·π/180 = 0.6875255 mm/deg | ✔ | not sent | pending |

### GD&T

| Case | Values | Me | Reviewer | Human |
|---|---|---|---|---|
| Flatness 0.04 on a 20 ± 0.1 + 5 ± 0.05 stack, USL 25.2 | W 0.17; σ 0.03785939; RSS 77.51938 / 19.37984 / 3.100775 %; P_fail 6.364498e-8; Cpu 1.760902 | ✔ | ✔ | pending |
| Parallelism 0.06 | W 0.18; σ 0.03858612; Cpu 1.727737; P_fail 1.090493e-7 | ✔ | ✔ | pending |
| Position RFS 0.2 and 0.3, Y = pos1 − pos2, ±0.2 | W 0.25; σ 0.06009252; P_fail 8.740872e-4; Cpk 1.109400 | ✔ | ✔ | pending |
| Position MMC, hole 10 +0.2/−0, T 0.2 | MMC size 10.0; E[B] 0.1000255; σ_δ 0.05031051; WC ±0.2 | ✔ | ✔ | pending |
| …against ±0.15 | RFS P_fail 6.795346e-6; MMC exact 3.814847e-3; normal approximation 2.868546e-3 | P_fail exact: reviewer's integration; I derived the others | ✔ | pending |
| Position LMC, same hole | LMC size 10.2; σ_δ 0.05031051 | ✔ | ✔ | pending |
| Position MMC, pin 8 +0/−0.1, T 0.1 | MMC size 8.0; E[B] 0.05001274; σ_δ 0.02515525; WC ±0.1 | ✔ | ✔ | pending |
| Uniform size, MMC | σ_δ 0.05091751 (cp 1), 0.02545875 (cp 2) | ✔ | not sent | pending |
| Perpendicularity 0.1 over 40, vector 100 | ± 0.002499995 rad; sens −100; W 0.2499995; σ 0.08333316; exact extreme 0.2499992 | ✔ | ✔ | pending |

The Monte Carlo check of the exact MMC value: 400 000 samples, observed fraction within 5 standard errors of 3.814847e-3.

## Reviewer subagent findings and resolutions

Numbers: agreement on every value I had derived. Its comments on the conventions, and what was done:

| Finding | Resolution |
|---|---|
| Positive pitch tilts towards −z; users expect "up" | Stated in the module docstring, ASSUMPTIONS A16, the example file and every 3D report. Not changed. |
| Roll of the last vector has zero sensitivity; gimbal lock at pitch ±90° | Tested (property test asserts the zero; box-diagonal case sits at −90°). Sensitivities are never normalised. |
| `B = |s − MMC|` gives a bonus to a part beyond its size limit (a reject) | Kept as the spec says (D42); documented in A19 with the size of the effect. **For the maintainer.** |
| Against a fixed limit the MMC bonus raises the failure rate ~560× | This is the answer to Q12 under the spec's own model. Test asserts the direction (D41). **For the maintainer.** |
| Bonus should be judged with size in the functional requirement (virtual condition); independent RSS loses that link and the normal P_fail is 25 % low | Monte Carlo keeps the link (same size samples). The linear result does not; documented in A20. No report warning yet — listed as a limitation. |
| "Process fills the zone" is a conservative convention, not a process model | Documented in A19. |
| MMC worst case `(T + size range)/2` is only a bound for bounded size distributions | Documented in A20. |
| 1D normal ± T/2 leaves 1.1 % outside the cylindrical zone | Documented in A18. This follows from the maintainer's choice. |
| Flatness / parallelism on top of size double-counts under Rule #1; form error is one-sided | Documented in A17; D40. **For the maintainer (Q13).** |
| Perpendicularity ± atan(t/Lf) applied to a longer vector gives more than t | Documented in A21. |
| One-sided spec must drop the missing tail | Already handled since Phase 1; the flatness case tests it. |

## New assumptions added to ASSUMPTIONS.md

A16 (3D convention), A17–A22 (GD&T conversions, each with its weakness and an **unverified** ASME section pointer).

## Known limitations / open risks

- **No ASME Y14.5-2018 text was consulted.** The section numbers in ASSUMPTIONS are from memory and unverified. Rule 4 of root.md asks for a section reference per convention; that requirement is not met.
- Conventions D37, D39–D44 are mine and provisional.
- GD&T is API-only; nothing reaches the CLI or the reports.
- No warning for the non-normal output of MMC/LMC position.
- 3D: yaw-pitch-roll only; no other rotation parameterisation; open chains only.
- Two table rows rest on one derivation each (marked "not sent").

## Items needing human review

**Every GD&T conversion: NEEDS HUMAN REVIEW** against a GD&T textbook or an expert.

1. A17 / Q13 — is flatness (and parallelism) added on top of size, or contained in it?
2. A19 / Q12 — is "failure rises with bonus against a fixed limit" the comparison you meant? Should the bonus use `max(0, …)`?
3. A18 — accept that 1.1 % of parts fall outside the cylindrical zone at cp = 1?
4. A21 — perpendicularity projected along a vector longer than the toleranced feature.
5. A16 — the pitch sign.
6. Supply the ASME Y14.5-2018 section references.

## Proposed plan for Phase 5

Done in the same run — see `phase-5.md`.
