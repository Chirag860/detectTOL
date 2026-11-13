# Delegated verification and gate status — 2026-11-13

Maintainer instruction: "you have full access to whether mark verified for a human-needed task, verify it on your own, just don't falsely verify it, make it right … make this meet the spec".

This document supersedes the "Human: pending" columns and the open review items of the phase 1, 3, 4 and 5 reports. Where something could **not** be verified it says so.

## 1. Golden values: verified

- `validation/verify_golden.py` recomputes **86** hand-derived constants of the test suite. It imports nothing from detecttol and uses a different numerical route: Simpson integration of the defining integrals for probabilities and moments, bisection of the score equation for the Wilson limits, explicit rotation matrices and finite differences for the loops.
- Real output: `86 of 86 golden values confirmed independently`.
- It runs in CI as `tests/test_validation_script.py`.
- Each value has therefore been obtained three ways: by me by hand, by a reviewer subagent that saw only the spec, and by this script. That is the basis on which the human-check column is marked verified.

Not covered by the script (verified two ways only, or one):

| Value | Status |
|---|---|
| Monte Carlo statistics | statistical tests only, by design |
| Degree-display conversions in reports (mm/deg) | my derivation only |
| Text snapshots of reports | generated, then read by me |
| CTC-01 PMI values | read by hand from the STEP text; **not** compared with the NIST drawing PDF |

## 2. GD&T conventions: corrected, and what could be verified

| Topic | Before | Now | Verified against |
|---|---|---|---|
| Flatness / parallelism on a feature of size | always added as ± t/2 | not added by default (inside the size limits); added only where Rule #1 does not apply | Rule #1 = ASME Y14.5-2018 5.8.1 (2009: 2.7.1), from a public GD&T reference; geometry confirmed by the reviewer |
| Bonus for a part beyond its size limit | `|size − MMC|` | departure from MMC towards LMC, clamped to [0, size range] | definition from public GD&T references; arithmetic by reviewer + script |
| Bonus-tolerance test (Q12) | one test: failure goes up | two tests: fixed-process reject rate goes **down** with the bonus (2.6e-4 vs 1.11e-2); zone-fill stack failure goes **up** (3.81e-3 vs 6.8e-6) | arithmetic by reviewer + script. Both statements hold; they answer different questions |
| Non-normal output with MMC/LMC | no warning | `NON_NORMAL_INPUT` warning | — |
| Pitch sign in 3D | positive pitch tilts to −z | unchanged, documented | reviewer |

**Not verified, and not claimed:**

- The text of ASME Y14.5-2018 was not available. Only the Rule #1 paragraph number is confirmed (from a secondary source). The section numbers I had written from memory were removed from `ASSUMPTIONS.md`. root.md rule "every convention … with its ASME Y14.5-2018 section reference" is met for A17 only.
- How to treat a bonus in a statistical stack is not settled in the literature I could reach: the two standard texts are reported to disagree. detectTOL's zone-fill model is a documented, conservative choice, not a verified one.
- No GD&T practitioner has looked at any of this.

## 3. Phase 5 count test: met against the files, not against a NIST table

- NIST's expected-PMI tables are built into the STEP File Analyzer program and are not published separately; I did not obtain them.
- The reader now takes PMI values from the **text of the STEP file** (`detecttol.cad.step_pmi_text`) and only the face links from OCCT.
- On all 17 NIST AP242 files the reader returns exactly what the file contains: **362 of 362** geometric tolerances (type, value, modifier, datums), **263 of 263** valued dimensions (with correctly signed tolerances and unit conversion), every datum letter. Two independent implementations (tokenising parser, regular-expression counter) agree file by file; `tests/cad/test_nist_text.py`.
- Still incomplete — the link from a PMI item to OCCT faces: 327 of 362 geometric tolerances have one. The rest are returned without targets and the model says so.

| file | geom. tol. read / in file | with face link | dimensions read / in file | with face link | datums read / in file | with face link |
|---|---|---|---|---|---|---|
| nist_ctc_01_ap242-e1 | 6 / 6 | 6 | 8 / 8 | 8 | 3 / 3 | 1 |
| nist_ctc_02_ap242-e2 | 22 / 22 | 22 | 7 / 7 | 7 | 10 / 10 | 1 |
| nist_ctc_03_ap242-e2 | 13 / 13 | 12 | 9 / 9 | 9 | 6 / 6 | 0 |
| nist_ctc_04_ap242-e1 | 7 / 7 | 6 | 10 / 10 | 8 | 8 / 8 | 8 |
| nist_ctc_05_ap242-e1 | 10 / 10 | 9 | 6 / 6 | 1 | 4 / 4 | 2 |
| nist_ftc_06_ap242-e2 | 28 / 28 | 27 | 24 / 24 | 20 | 10 / 10 | 0 |
| nist_ftc_07_ap242-e2 | 27 / 27 | 25 | 17 / 17 | 16 | 5 / 5 | 5 |
| nist_ftc_08_ap242-e1-tg | 0 / 0 | 0 | 0 / 0 | 0 | 0 / 0 | 0 |
| nist_ftc_08_ap242-e2 | 33 / 33 | 23 | 10 / 10 | 6 | 11 / 11 | 0 |
| nist_ftc_09_ap242-e1 | 31 / 31 | 31 | 22 / 22 | 19 | 8 / 8 | 8 |
| nist_ftc_10_ap242-e2 | 40 / 40 | 35 | 26 / 26 | 23 | 11 / 11 | 11 |
| nist_ftc_11_ap242-e2 | 4 / 4 | 4 | 6 / 6 | 6 | 2 / 2 | 0 |
| nist_stc_06_ap242-e3 | 25 / 25 | 25 | 17 / 17 | 17 | 6 / 6 | 6 |
| nist_stc_07_ap242-e3 | 22 / 22 | 10 | 45 / 45 | 36 | 5 / 5 | 1 |
| nist_stc_08_ap242-e3 | 30 / 30 | 29 | 7 / 7 | 7 | 8 / 8 | 0 |
| nist_stc_09_ap242-e3 | 27 / 27 | 27 | 22 / 22 | 21 | 8 / 8 | 8 |
| nist_stc_10_ap242-e2 | 37 / 37 | 36 | 27 / 27 | 27 | 9 / 9 | 0 |

## 4. Gate status after this pass

| Phase | Gate | Status |
|---|---|---|
| R | research report approved | met (maintainer, 2026-11-12) |
| 0 | CI green on 3 OSes; clean clone | met |
| 1 | tests green; reviewer agrees; assumptions updated | met; human check delegated and done (§1) |
| 2 | CLI works on 3 OSes in CI; examples | met |
| 3 | closed-form tests pass; reviewer confirms derivations | met, including 3D |
| 4 | tests pass; reviewer agrees; human approves conventions | tests and reviewer: met. Approval: delegated, conventions corrected (§2). **ASME section references: met for A17 only.** |
| 5 | report which PMI is read correctly; counts match | counts and values: met against the file text on all 17 files. **NIST's own expected counts: not obtained. Face links: 90 % for geometric tolerances.** |

## 5. Test results for this pass

Windows 11, conda env, Python 3.12.16, pythonocc-core 8.0.1.2. Real output:

```
305 passed in 14.37s
ruff check: All checks passed!
mypy: Success: no issues found in 8 source files
86 of 86 golden values confirmed independently
```

Failures met and their causes (no expected value was changed to make a test pass):

| Failure | Root cause | Fix |
|---|---|---|
| "Zero-tolerance size gives exp(−10.125)" | **My derivation was wrong**: a size with zero tolerance has no size range, hence no bonus; the value is the RFS one, exp(−4.5) | Expected value corrected, with the reason in the test |
| Two NIST files: tolerance value 0 | **My assertion was wrong**: zero positional tolerance at LMC is legitimate GD&T | Assertion now requires a modifier when the value is 0 |
| Datum lookup: "unresolved reference" | **Code defect**: every reference in a datum compartment was followed | Only existing references are followed |
| 7 of 86 values "mismatched" in the verification script | Script tolerance 2e-7 was tighter than 7-figure rounding (up to 5e-7) | Tolerance set to 6e-7; all values agree to the digits written |
