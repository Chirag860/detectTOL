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

## Phase 3 (vector loops)

D23–D30 were chosen by the implementer on 2026-11-12 to carry out "continue with phase 3". **They are PROVISIONAL until the maintainer confirms them.**

| # | Question | Decision | Status | Reason |
|---|---|---|---|---|
| D22 | Q8 — relative or absolute angles | Relative | APPROVED 2026-11-12 | Maintainer: "choose relative angles". |
| D23 | Q8 — zero reference and sense | First angle from global +x; counter-clockwise positive | PROVISIONAL | Standard mathematical convention. |
| D24 | Q8 — gap sign | `Y = constant + Σ L_j cos(Θ_j − α)`: projection of the open chain's resultant on the measurement direction α; positive along α | PROVISIONAL | Reproduces the 1D sign rule (golden case A bit for bit). |
| D25 | 2D or 3D | **2D only.** 3D is not implemented | PROVISIONAL | A 3D chain with relative angles needs a rotation convention (axis order, frames) that the spec does not give, and no Phase 3 required test is 3D. Needs the maintainer. |
| D26 | Input format for loops | Python API only (`VectorLoop`, `analyze_loop`). No YAML, CLI or report support yet | PROVISIONAL | root.md §8: a change to the input schema after Phase 2 needs the maintainer. A proposal is in the Phase 3 report. |
| D27 | Output for loops | New `LoopResult` wrapping an unchanged `StackResult` | PROVISIONAL | Keeps report JSON schema v1 untouched. |
| D28 | Linearisation warnings | `ZERO_SENSITIVITY`: a variable whose linear effect `|a|·t` is ≤ 1e-12 mm while its exact one-at-a-time effect is > 1e-9 mm. `LINEARISATION_SUSPECT`: Monte Carlo std or mean differs from the linear value by more than 5 standard errors | PROVISIONAL | The spec asks for the consistency check but gives no threshold. 5 SE is tied to sampling error, not an arbitrary percentage. |
| D29 | Linearised mean | `Y(μ)`; no second-order correction | PROVISIONAL | Spec §3.4 as written. |
| D30 | Scope | Open chains only; α and the constant are exact | PROVISIONAL | No closed-loop solver in the spec's Phase 3 tests. |

### YAML and CLI for loops (added 2026-11-12)

The maintainer approved adding YAML/CLI support with the format proposed in the Phase 3 report ("Yes, add YAML/CLI"). That supersedes D26. The details below the approved outline are the implementer's and PROVISIONAL.

| # | Question | Decision | Status | Reason |
|---|---|---|---|---|
| D31 | Loop input format | `schema_version: 2`, `units: mm`, required `angle_units: deg \| rad`, a `loop` section with `measure_angle` and `vectors` (each `length` / `angle` is a number or a toleranced variable) | APPROVED 2026-11-12 | Maintainer approved the proposed format. |
| D32 | Linear files | `schema_version: 1` files are unchanged and still valid; a `loop` section selects the loop format | PROVISIONAL | No existing file or output changes. |
| D33 | Where angles are converted | Degrees → radians in the YAML loader (input); radians → the file's unit in Markdown/HTML (output). The core works in radians only | PROVISIONAL | root.md rule 5: convert only at input/output. |
| D34 | Units in JSON | The JSON report keeps radians and mm/rad; `loop.angle_units` records what the input used | PROVISIONAL | Machine-readable output stays in internal units; one convention for consumers. Markdown/HTML label every angle row with its unit. |
| D35 | Report schema | Loop reports are `schema_version: 2` (`report-v2.schema.json`): the v1 `result` block plus a `loop` block. Linear reports stay v1, byte-for-byte | PROVISIONAL | Supersedes D27's "API only"; v1 consumers are unaffected. |
| D36 | Example seed | `examples/wedge_height.yaml` uses seed 2, not 1 | PROVISIONAL | Seed 1 gives 227 failures where ~186 are expected (a 3-sigma draw; seeds 2–5 give 181–199, and an independent 2e7-sample run gives 1860 ppm vs 1865 predicted). An example whose interval misses the true value would mislead. |

## 3D loops, Phase 4 and Phase 5 (2026-11-12/13)

Maintainer instruction: "normal 3 sigma but implement 3d loops and then go ahead with phase 4 and 5 without stopping". D38 is the maintainer's; **everything else in this table is the implementer's and PROVISIONAL.**

| # | Question | Decision | Status | Reason |
|---|---|---|---|---|
| D37 | 3D rotation convention | Relative yaw (z) → pitch (y) → roll (x) about the moving axes, right-handed; vector along local x; positive pitch tilts towards −z (A16). Supersedes D25 | PROVISIONAL | The spec gives none. Standard aerospace-style sequence; reduces to the 2D convention. |
| D38 | Q9 — position tolerance distribution | Normal with ±T/2 at 3σ (σ = T/(6·cp)) | APPROVED 2026-11-12 | Maintainer: "normal 3 sigma". |
| D39 | 3D in YAML | Schema v2 extended: optional `pitch` / `roll` per vector and optional `loop.measure_direction: [x, y, z]`; a loop is 3D when any of them is present. Report schema v2 gained `loop.measure_direction` and the variable kinds `pitch` / `roll` | PROVISIONAL | Additive; every earlier v2 file is unchanged. Schema v2 was introduced one day earlier and has no outside users. |
| D40 | Q13 — flatness on top of size | Implemented as the spec says (extra `± t/2` contributor); the user decides whether to include the callout | PROVISIONAL — NEEDS HUMAN REVIEW | Double-counts under Rule #1; conservative. Not my call. |
| D41 | Q12 — bonus-tolerance test | The test asserts that with an MMC bonus the failure rate of a *fixed* positional limit goes **up** (3.81e-3 vs 6.8e-6) | PROVISIONAL — NEEDS HUMAN REVIEW | That is what the spec's own model gives. Whether this is the comparison the maintainer wants is still Q12. |
| D42 | Bonus formula for parts beyond the size limit | `|actual − MMC|` as the spec says, not `max(0, …)` | PROVISIONAL | Spec text; effect is 0.006 % on σ in the test case. `max(0, …)` is physically cleaner. |
| D43 | GD&T input | Python API only (`detecttol.gdt`): no YAML or report support for callouts | PROVISIONAL | Phase 4 asks for conversions and tests, not for a file format; avoids another schema change without approval. |
| D44 | Orientation tolerances | Only as an angle tolerance for vector loops; no 1D conversion | PROVISIONAL | Spec: "in Phase 3 loops". |
| D45 | PMI reading route | XCAF (`XCAFDoc_DimTolTool`). Dimensions and datums through their objects; geometric tolerances through the raw child labels (type, value, material modifier), because the Python class has no methods | PROVISIONAL | Verified against the file text on NIST files; see phase-5 report for what is and is not read. |
| D46 | "Documented counts" for the NIST models | Replaced by an independent, OCCT-free count of the entities in the file text (`cad/step_text.py`), plus hand-read values for CTC-01 | PROVISIONAL | No plain count table from NIST was located. |
| D47 | NIST files in tests | Downloaded once by a fixture into the pytest cache, SHA-256 pinned; not committed. Skipped with a message when offline | PROVISIONAL | NIST: "can be used without any restrictions"; keeps 14 MB out of the repo. |
| D48 | Annotation file | `schema_version: 1`, `units: mm`; kinds `dimension` (two parallel planar faces), `flatness`, `datum`; face = part name + index + centroid/normal fingerprint (1e-6 mm, 1e-9) | PROVISIONAL | Spec outline; tolerances are my choice. |
| D49 | Synthetic STEP files | Geometry only. No synthetic PMI | PROVISIONAL | Writing PMI created through the Python binding crashes OCCT 8.0.1 (access violation). |
| D50 | OCCT console output | OCCT's default message printers are removed once per process | PROVISIONAL | root.md §6: no printing in library code. |

## Still open (not needed until later phases)

Q9 is answered (D38). Q12 (bonus-tolerance test expectation) and Q13 (flatness on top of size) are implemented provisionally as D41 and D40 and still need the maintainer or a GD&T reference.
