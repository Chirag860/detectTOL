# Phase ISO report: drawing standard option (IS / ISO) and tolerance tables

2026-11-14. Windows 11, conda env, Python 3.12.16, pythonocc-core 8.0.1.2.
Approved by the maintainer on 2026-11-13 ("yes build all the steps").

## Done

- **Step A, drawing standard.** `standard: asme | iso | is` in YAML schema v1 and v3, on `Stack` and on `GdtStack`.
  - `is` and `iso` follow the same rules (ISO 8015 = IS 12160, independency). The report prints the IS numbers.
  - Under ISO / IS, flatness on a sized face adds ±t/2 by default. `envelope: true` (Ⓔ) restores containment.
  - Parallelism with `within_size: true` needs `envelope: true` under ISO / IS; without it the input is refused.
  - With no standard given, ASME is assumed. A `STANDARD_ASSUMED` warning appears only when a result depends on it.
  - `StackResult.standard` is in the JSON (`null` when not stated). The Markdown/HTML "Drawing standard" line appears only when a standard is stated.
  - PMI flatness without `within_size` now follows the stack's standard instead of being forced to ASME.
- **Step B, ISO 286 / IS 919 classes.** `tolerance_class: H7 | h6 | JS9 | js8` (IT5–IT18, up to 500 mm), for linear stacks and for STEP dimensions (looked up at the measured size). Other letters are refused with an explanation.
- **Step C, IS 2102 / ISO 2768-1 general tolerances.** `tolerance_class: general` together with a top-level `general_tolerance: f | m | c | v`.
- New package `detecttol.standards` (no CAD dependency). New CLI command `detecttol limits 25 H7` / `detecttol limits 25 general --general m`.
- New warnings: `TOLERANCE_FROM_TABLE` (lists every looked-up tolerance with its source) and `TABLE_NOT_VERIFIED` (ISO 286 values).
- Example: `examples/is_fit_and_general.yaml`. README section "Indian (IS) and ISO drawings".

## Research and sources

| Indian standard | Equivalent | How confirmed |
|---|---|---|
| IS 12160:2015 | ISO 8015:2011 | BIS catalogue listing (search result) |
| IS 8000 (Part 1):2019 | ISO 1101:2017, identical | BIS catalogue, standards.ie |
| IS 919 (Part 1):2014 | ISO 286-1:2010, identical under dual numbering | BIS catalogue page (fetched) |
| IS 2102 (Part 1):1993 (R2014) | ISO 2768-1:1989 | BIS scan, standards.ie |

- **IS 2102 (Part 1):1993 scan** (law.resource.org): the text layer of Table 1 is readable. All 30 values are present; the last two columns are jumbled.
- **IS 919 (Part 1) and (Part 2):1993 scans**: Table 1 and the limit-deviation tables did **not** survive OCR (for example "t" for "+", columns run together). The annex A formulae and rounding rules (Tables 7, 8) are readable.
- The standard says Table 1 governs over the formulae. The formulae reproduce 71 of the 91 transcribed IT5–IT11 values; the 20 departures are pinned in a test.

## Test results

Real output of the final run:

```
392 passed in 25.93s
ruff check: All checks passed!
ruff format --check: 96 files already formatted
mypy (core, strict): Success: no issues found in 8 source files
mypy --strict src/detecttol/standards: Success: no issues found in 4 source files
coverage TOTAL 97 %; core/analyze.py, models.py, results.py 100 %; standards/ 95-100 %
```

- 59 new tests: `tests/standards/` (3 files) and `tests/cad/test_step_standard.py`.
- All 333 existing tests pass unchanged; no expected value was edited.
- Two JSON snapshots each gained the one line `"standard": null`. The JSON Schema files gained the field and the three warning codes (regenerated with sorted keys, as committed before).

## Golden values and who verified them

| Value | Me | Reviewer subagent | Source |
|---|---|---|---|
| IT5–IT18, step 18–30 (9, 13, 21, 33, 52, 84, 130, 210 … 3300) | ✔ | ✔ | annex A formulae + 10× rule |
| IT5–IT11, step 80–120 (15, 22, 35, 54, 87, 140, 220) | ✔ | ✔ | annex A formulae |
| H7 / h6 / JS7 / js8 at 25 mm | ✔ | ✔ | from the IT values above |
| IT7 at 30 → 21, at 30.001 → 25 | ✔ | ✔ (the formula gives 25 too) | boundary rule |
| js9 at 16.6 mm = ±0.0215 | ✔ | ✔ (formula 43 µm) | formula = table |
| IT14 at 1.5 mm = 250; IT7 at 3 mm = 10 and at 500 mm = 63 | ✔ | table-only (the formula gives 220, 9, 62) | **transcribed table, unverified** |
| H7/h7 fit at 25: mean 0.021, range [0, 0.042] | ✔ | ✔ | arithmetic |
| IS 2102-m stack: mean 0.2, W 0.9, σ 0.1527525 | ✔ | ✔ (arithmetic only) | Table 1 values |
| Flatness: ASME W 0.15 / σ 0.03726780; ISO/IS W 0.17 / σ 0.03785939 | ✔ | ✔ | arithmetic |

## Reviewer subagent findings and resolutions

1. **Docstring slips** in the 80–120 derivation (i = 2.172532, not 2.172400; 139.04 and 217.25). No rounded value is affected. **Fixed.**
2. **Flatness is one-sided** (open, not changed). Form cannot make the effective height smaller than the minimum size, only larger by up to t. The symmetric `0 ± t/2` model gets the upper worst case right, puts the mean t/2 too low, and has a lower bound that cannot occur. `+t/2 ± t/2` or uniform on [0, t] would be more faithful. This affects the existing A17 convention (ASME `within_size=False`) as much as the new ISO default. → **Question Q-ISO-2 below.** Changing it would change existing expected values, so it was not done on my own (rule 2).
3. **Parallelism with Ⓔ** is contained "largely as under Rule #1". The reviewer is UNSURE about edge cases where the datum is set from an imperfect face. → recorded in D62 as UNSURE.
4. Under independency, the opposite face's form and any bow are also uncontrolled, so a single flatness callout may not be the whole form contribution. → added to the known limitations.

## New assumptions and decisions

- ASSUMPTIONS A29 (standard field), A30 (independency), A31 (IS 2102 table), A32 (ISO 286 subset, unverified).
- DECISIONS D60–D64: D61, D62 and D63 are PROVISIONAL.

## End-to-end check

- `examples/is_fit_and_general.yaml`: mean 0.6105, worst case [0.1, 1.121], σ 0.120236. All three match the hand check in the file.
- The maintainer's `tolerance_stack_test.step` with `standard: is` and every dimension at IS 2102-m:
  - frame ±0.3, blocks ±0.2 / ±0.3 / ±0.3
  - worst case [−0.1, 2.1]: **fails** the gap ≥ 0 requirement
  - RSS σ 0.185592, predicted failure 0.036 ppm

## Known limitations / open risks

- **ISO 286: only H, h, JS and js**, and the IT table is a transcription that no human has checked (`TABLE_NOT_VERIFIED` on every use). Shaft or hole letters such as g6, k6 or P7 need ISO 286-1 Tables 2–3.
- **IS 2102: linear dimensions only.** Broken edges (Table 2), angles (Table 3) and IS 2102 (Part 2) general geometrical tolerances are not covered.
- The independency default covers flatness and parallelism only. Other form effects under ISO (opposite face, bow) are not modelled automatically.
- Vector loops (schema v2) do not take `standard` or `tolerance_class` yet.
- A STEP file's PMI does not yet supply the standard or Ⓔ; both come from the YAML file.

## Items needing human review

1. **Check the 91 IT5–IT11 values** in `src/detecttol/standards/iso286.py` against a printed IS 919 (Part 1) / ISO 286-1 Table 1. Then set `TABLE_VERIFIED = True`, and the warning disappears.
2. Spot-check the IS 2102 (Part 1) Table 1 values in `src/detecttol/standards/general.py`, especially the last two columns (over 1000 mm).
3. **Q-ISO-1:** under IS/ISO with Ⓔ, is a parallelism to the opposite face contained in the size (D62)?
4. **Q-ISO-2:** keep flatness as `0 ± t/2`, or change it to one-sided `+t/2 ± t/2` (both standards; this changes A17 expected values)?
5. D61 (ASME fallback with a warning) and D63 (ship the unverified table with a warning): confirm or change.

## Proposed plan for Phase 7

Unchanged from the Phase 6 report: the `validation/` table with reference results you supply (now with at least one IS/ISO case, for example a TolAnalyst or textbook result for an IS drawing), the theory and GD&T docs including the IS/ISO rules, and the PyPI release decisions.
