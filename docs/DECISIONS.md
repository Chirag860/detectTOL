# Design decisions

Decisions that are not dictated by `root.md`. Each has a status:

- **APPROVED** — the maintainer said so.
**Update 2026-11-12:** the maintainer accepted D3–D21 as they stood ("Accept all"). They were first recorded as PROVISIONAL (see the phase 0–2 reports) and are now APPROVED. Changing one from here on is a schema/API change (root.md §8).

- **PROVISIONAL** — chosen by the implementer on 2026-11-12 so that Phases 0–2 could proceed without a stop (the maintainer asked for a non-stop run to Phase 2). Each one answers an open question from `docs/reports/phase-R.md`. **The maintainer must confirm or change them**; changing one after Phase 2 is a schema/API change (root.md §8).

| # | Question | Decision | Status | Reason |
|---|---|---|---|---|
| D1 | Spec edits E1–E9 (Phase R) | Applied to root.md | APPROVED 2026-11-12 | Maintainer: "Approve all". |
| D2 | Q1 — conda on the dev machine | Miniforge installed for the current user in `%USERPROFILE%\miniforge3`, not added to PATH | APPROVED 2026-11-12 | Maintainer: "install it". |
| D3 | Q3 — "constant term" of μ_Y | Optional `requirement.constant` [mm], default 0 | APPROVED 2026-11-12 | §3.2 mentions a constant term; a field with a zero default changes nothing for existing files. |
| D4 | Q4 — zero tolerance (`upper_tol == lower_tol`) | Allowed. If *every* contributor has zero tolerance: contributions, P_fail and Cpk are `null`, pass/fail is judged from the mean, and a `ZERO_VARIATION` warning is raised | APPROVED 2026-11-12 | Follows approved edit E4 (σ_Y = 0 → no P_fail/Cpk). Fixed dimensions (gauge blocks, shims) are legitimate inputs. |
| D5 | Q5 — Bender `k·RSS` above worst case | Warn (`MODIFIED_RSS_EXCEEDS_WORST_CASE`), do not cap | APPROVED 2026-11-12 | A warning hides nothing; capping would silently change a number. |
| D6 | Q6 — when to flag analytic P_fail as approximate | Whenever any contributor with non-zero tolerance is not `normal` (`NON_NORMAL_INPUT`) | APPROVED 2026-11-12 | A dominance threshold would be an invented number. |
| D7 | Q7 — Monte Carlo convergence check | As specified: std of the first N/2 samples vs all N, warn above 1 % | APPROVED 2026-11-12 | Spec text kept. Documented as a heuristic (ASSUMPTIONS A9). |
| D8 | Q10 — units | `units: mm` is the only accepted value; anything else is rejected | APPROVED 2026-11-12 | Strictest reading of rule 5. Inch input can be added later without breaking files. |
| D9 | Q11 — missing Monte Carlo seed | Rejected. `analysis.monte_carlo.seed` is required whenever `monte_carlo` is in `methods` | APPROVED 2026-11-12 | Rule 6: every random process takes an explicit seed. |
| D10 | Missing `analysis` block | Defaults to `methods: [worst_case, rss]` (no Monte Carlo, hence no seed needed) | APPROVED 2026-11-12 | Lets a minimal file run without inventing a seed. |
| D11 | Sensitivity values | Any finite real number (zero allowed) | APPROVED 2026-11-12 | §3.1 allows real sensitivities for linearised stacks. |
| D12 | Bender factor range | `analysis.modified_rss_k >= 1`; absent = off | APPROVED 2026-11-12 | k < 1 would make "modified RSS" less conservative than RSS. |
| D13 | Worst-case limit exactly on a spec limit | Counts as meeting the spec, with 1e-9 mm slack | APPROVED 2026-11-12 | Float rounding (~1e-14 mm) otherwise reports a false violation, e.g. range [0.20, 0.50] vs USL 0.50. |
| D14 | Monte Carlo failure test | A sample fails if `Y < LSL` or `Y > USL` (strict) | APPROVED 2026-11-12 | Consistent with D13: a value on the limit is in spec. |
| D15 | Truncated-normal sampling | Inverse CDF from one uniform draw per sample | APPROVED 2026-11-12 | Deterministic, vectorised, no rejection loop. |
| D16 | Sample statistics | Sample std uses ddof = 1; percentiles use numpy's default linear interpolation; histogram has 60 equal-width bins | APPROVED 2026-11-12 | Conventional defaults; all stated in the result model docstrings. |
| D17 | CLI output | With `--out DIR`: writes `DIR/<name>.<fmt>` (+ `<name>_histogram.png` for Markdown; HTML embeds the image). Without `--out`: prints to stdout | APPROVED 2026-11-12 | The spec gives the flags but not the file naming. |
| D18 | CLI exit codes | 0 = analysis ran (even if the stack fails its spec); 2 = input error | APPROVED 2026-11-12 | A failing stack is a result, not a tool error. |
| D19 | Reproducible timestamps | `SOURCE_DATE_EPOCH` overrides the report timestamp | APPROVED 2026-11-12 | Standard convention; needed for byte-identical reports. |
| D20 | Q14 — spec file name | Kept as `root.md` | APPROVED 2026-11-12 | No instruction to rename; §6b's "SPEC.md" is read as `root.md`. |
| D21 | Q15 — LGPL pythonocc under Apache-2.0 | Listed in `environment.yml` only; not a `pip` dependency of the package; never imported by Phases 0–2 code | APPROVED 2026-11-12 | Keeps the question open without blocking; needs the maintainer's licence call before Phase 5. |

## Still open (not needed until later phases)

Q8 (vector-loop angle and sign conventions), Q9 (position-tolerance distribution), Q12 (bonus-tolerance test expectation), Q13 (flatness on top of size).
