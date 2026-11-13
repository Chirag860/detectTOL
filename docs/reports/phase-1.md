# Phase 1 report — 1D math engine

> **Superseded in part (2026-11-13).** The human-check columns, the review items and (for phases 4 and 5) several conventions and gate statements below were revised under the maintainer's delegation. Read `verification-2026-11-13.md` first.

2026-11-12. Run without a stop at the Phase 0 gate, on the maintainer's instruction ("continue non stop till phase 2").

## Done

- `detecttol.core`: `analyze(stack) -> StackResult` for linear stacks `Y = constant + Σ aᵢxᵢ`.
  - `models.py` — strict pydantic input models, midpoint re-centring, sigma conventions (normal, uniform, truncated normal).
  - `linear.py` — mean, worst case, RSS, Bender modified RSS, contributions, P_fail, Cpl/Cpu/Cpk.
  - `montecarlo.py` — seeded vectorised sampling, Wilson interval, zero-failure bound, convergence check, percentiles, histogram.
  - `analyze.py` — orchestration and warnings.
- `detecttol.io`: YAML loader; every validation message starts with the field path.
- All Phase 1 required tests: golden A, golden B (asymmetric), uniform case, one-sided spec, zero-failure case, 8 property tests, validation tests for every Section 4 rule.
- `core/` imports nothing outside `core/`, numpy, scipy, pydantic (enforced by a test).

## Test results

Windows 11, conda env `detecttol` (Python 3.12.16, numpy 2.5.4, scipy 1.18.1, pydantic 2.14.3). Real output:

```
src\detecttol\core\analyze.py          61      0     24      0   100%
src\detecttol\core\linear.py           44      0     12      0   100%
src\detecttol\core\models.py           89      0     20      0   100%
src\detecttol\core\montecarlo.py       65      0     18      0   100%
src\detecttol\core\results.py          92      0      0      0   100%
TOTAL                                 560      3    116      3    99%
111 passed in 13.33s
ruff check: All checks passed!
ruff format: 43 files already formatted
mypy: Success: no issues found in 6 source files
```

- Coverage of `core/`: 100 % (gate: ≥ 95 %). Two defensive lines are excluded with `# pragma: no cover`: the internal "percentages sum to 100" assertion and a guard that pydantic validation already makes unreachable.
- The 111 tests include the Phase 2 tests (same run).

### Failures met on the way, and their root causes

No expected value was changed to make a test pass.

| Failure | Root cause | Fix |
|---|---|---|
| Wilson lower limit at x = 0 returned 2.2e-19, test expected exactly 0 | **Code defect.** Float residue where the limit is analytically 0 (the reviewer had predicted this) | Code: lower limit set to exactly 0 at x = 0, upper to exactly 1 at x = N |
| Case A modified-RSS lower limit differed from the hand formula by 4e-15 | **Test tolerance defect.** I had used a 1e-15 absolute tolerance on a difference of nearly equal numbers; μ_Y itself carries ~1e-14 mm rounding | Tolerance changed to abs 1e-12 mm with the reason in a comment. Expected value 0.0015687 unchanged |
| `ast.parse` rejected `core/__init__.py` | Byte-order mark written by a PowerShell command | BOMs stripped from six `__init__.py` files |
| Hard crash in matplotlib (Windows 0xc06d007f) | Environment, not code: the conda env's `python.exe` was called without activating the env | Run through an activated env (`conda activate` / `conda run`) |

## Golden values and who verified them

"Reviewer" = separate subagent given only the spec text and the case definitions, no code and none of my numbers. Human verification is pending for every row.

| Case | Values | Me | Reviewer | Human |
|---|---|---|---|---|
| A (spec anchor) | μ_Y 0.20; WC ±0.25 → [−0.05, 0.45]; 3σ 0.1322876; σ 0.04409586; RSS [0.0677124, 0.3322876]; WC 40/20/20/20 %; RSS 57.142857/14.285714 %; z −4.535574; P_fail 2.872356e-6; Cpl 1.511858 | ✔ | ✔ | pending |
| A + Bender k=1.5 | half-range 0.1984313 → [0.0015687, 0.3984313]; below WC | ✔ | ✔ | pending |
| B (asymmetric, two-sided) | μ 30.10/29.75, t 0.10/0.05; μ_Y 0.35; WC ±0.15 → [0.20, 0.50]; σ 0.03726780; 3σ 0.1118034; WC 66.667/33.333 %; RSS 80/20 %; P_fail 2.849707e-5; Cpl 2.236068; Cpu = Cpk 1.341641; Bender 0.1677051 > WC | ✔ | ✔ | pending |
| C (uniform + normal) | σ₁ 0.1732051; σ₂ 0.03333333; μ_Y 1.0; WC ±0.40; σ 0.1763834; 3σ 0.5291503 > WC; RSS 96.428571/3.571429 %; normal-approx P_fail 2.628061e-3; Cpl 0.9449112; Cpu 1.133893 | ✔ | ✔ | pending |
| D (cp = 2, USL only) | σ 0.02/0.02; μ_Y 35.0; WC ±0.18; σ 0.02828427; RSS 50/50 %; WC 66.667/33.333 %; P_fail 2.034760e-4; Cpu 1.178511 | ✔ | ✔ | pending |
| E (truncated normal) | cp 1: factor 0.9865784, σ 0.09865784; cp 2/3: factor 0.8796257, σ 0.1319438 | ✔ | ✔ | pending |
| F (intervals) | Wilson x=0,N=1000: [0, 3.826759e-3]; x=5,N=1000: [2.137536e-3, 1.165096e-2]; x=3,N=1e5: [1.020276e-5, 8.820805e-5]; zero-failure bound N=1000: 2.991250e-3 | ✔ | ✔ | pending |
| G (single contributor) | WC = 3σ = 0.2; with a = −2.5: μ_Y −25, WC 0.5, σ 0.1666667 | ✔ | ✔ | pending |
| H (constant +0.05) | μ_Y 0.25; WC [0, 0.50]; P_fail 7.162118e-9 | ✔ | ✔ | pending |

Not hand-derivable, so tested statistically only: Monte Carlo mean, std, percentiles and failure counts (tolerances are stated in standard errors in each test).

## Reviewer subagent findings and resolutions

- **Numbers:** agreed with every value above. No disagreement.
- **Finding 1 — float edge cases** (Wilson lower limit at x = 0; worst-case limit landing exactly on a spec limit): both real. Resolved in code (exact limits at x = 0 / x = N; 1e-9 mm slack, decision D13) and covered by tests (cases B and H).
- **Finding 2 — normal P_fail is badly wrong for case C:** worst case [0.6, 1.4] lies inside the spec [0.5, 1.6], yet the normal formula reports 2628 ppm. Resolved as far as the spec allows: `NON_NORMAL_INPUT` and `RSS_EXCEEDS_WORST_CASE` warnings fire, and Monte Carlo reports 0 failures in 100 000. The formula itself is the spec's and is unchanged.
- **Finding 3 — Bender can exceed worst case** (cases B, D): warning implemented; cap-or-warn remains the maintainer's call (D5).
- **Finding 4 — Bender ignores cp and distribution:** documented (ASSUMPTIONS A10).

## New assumptions added to ASSUMPTIONS.md

None beyond A1–A11 from Phase R. Implementation choices are in `docs/DECISIONS.md` (D3–D16), all marked PROVISIONAL.

## Known limitations / open risks

- **Nine Phase R questions (Q3–Q7, Q10, Q11, Q14, Q15) were answered by me, not by the maintainer**, to keep the run going, along with further implementation choices. All are listed as PROVISIONAL in DECISIONS.md (D3–D21). Any of them may be wrong for your use.
- Analytic P_fail and Cpk are only as good as the normal assumption (see case C).
- Contributors are assumed independent; there is no correlation input.
- No process mean shift: every process is assumed centred on its tolerance midpoint.
- The convergence check almost never fires at the default N (Phase R, item 19).
- Bit-identical Monte Carlo output is tested on this machine only; identical seeds across OSes or numpy versions are not proven (the JSON snapshot test therefore compares floats at rel 1e-9).
- Only `mm`. Only linear stacks.

## Items needing human review

1. Hand-check the golden table above (at least A and B).
2. Confirm or change decisions D3–D12.
3. Decide Q5 (cap Bender at worst case?) and Q6 (non-normal warning rule).

## Proposed plan for Phase 2

Done in the same run — see `phase-2.md`.
