0. Your role and the rules you must follow

You are building a production-quality, open-source Python library and CLI for mechanical tolerance stack-up analysis. It must start with 1D stacks and grow into 2D/3D stacks with GD&T, read from STEP AP242 files. Engineers will use the results to make manufacturing decisions, so correctness matters more than features or speed.

Hard rules (never break these)
Never invent reference values. Every expected number in a test must be either (a) derived by hand in the test's docstring, step by step, or (b) supplied by the human maintainer (Chirag) from a trusted source. If you can't derive it, stop and ask.
Never change an expected value just to make a test pass. If a test fails, find the root cause. If you believe the expected value itself is wrong, stop and explain why. Do not edit it silently.
Never skip, xfail or delete a failing test without the maintainer's approval.
No silent assumptions. Record every modeling assumption (distribution choice, sigma convention, GD&T interpretation, sign convention) in docs/ASSUMPTIONS.md, with the reason and a reference.
Units are millimetres and radians internally. Convert only at input/output. Reject inputs with missing or unknown units.
Determinism. Every random process takes an explicit seed (numpy.random.default_rng(seed)). Same seed means identical output.
Stop at every phase gate. Write the phase report (Section 9) and wait for the human. Do not start the next phase on your own.
Independent verification (math phases only: R2, 1, 3, 4). At the end of those phases, start a separate reviewer subagent that has not seen your implementation reasoning. Give it only the spec and the test cases (not your code or your reasoning). Ask it to re-derive every hand-calculated expected value independently, then compare. Any disagreement must be resolved and recorded in the phase report. In the other phases (0, 2, 5, 6, 7) no reviewer subagent is needed; the tests, the end-to-end example and the human review are the check.
If anything in this spec is ambiguous or seems wrong, ask. Don't guess.
1. Problem statement

Real parts deviate from their nominal dimensions within tolerances. In an assembly those deviations accumulate, and a functional requirement (a gap, clearance, interference or alignment) may then fail. Today engineers either:

do 1D stack-ups in spreadsheets, which miss angular and 3D effects and are error-prone, or
buy expensive commercial 3D tools (CETOL 6σ, 3DCS, SOLIDWORKS TolAnalyst), which small firms and students often can't access.

detectTOL fills that gap with a free, scriptable, verifiable tool:

Exact 1D stack math (worst case, RSS, Monte Carlo) with contribution analysis.
2D/3D vector-loop stacks with nonlinear geometry.
A defined, documented subset of GD&T modeling.
Reading assemblies and semantic PMI from STEP AP242, with a YAML fallback.
Clear reports: the gap distribution, failure rate, and which tolerances drive it.
Non-goals (do not build these)
A GUI (CLI and Python API only; maybe an HTML report).
Full ASME Y14.5 coverage. Support only the subset in Phase 4.
Native SOLIDWORKS/CATIA file readers. STEP only.
Cloud or service features.
2. Tech stack (fixed)
Python 3.11+
Geometry/STEP: pythonocc-core (OCCT), installed via conda-forge. Provide environment.yml.
Math: numpy, scipy (scipy.stats for distributions and normal CDF)
Data models: pydantic v2 (strict validation)
CLI: typer
Reports: matplotlib (histograms), jinja2 (HTML/Markdown)
Testing: pytest, hypothesis (property-based), pytest-cov
Quality: ruff (lint and format), mypy --strict on src/detecttol/core
CI: GitHub Actions on windows-latest, macos-latest, ubuntu-latest
License: Apache-2.0
Layout: src/detecttol/ with sub-packages core/ (math, no OCCT dependency), gdt/, cad/ (OCCT/STEP), io/ (YAML/JSON), report/, cli/

Architecture rule: core/ must never import OCCT. The math must be testable without any CAD dependency.

3. Core definitions and math (draft: audited in Phase R, then implemented)

This section is the maintainer's working draft. Keep what is correct. Phase R must verify it against authoritative sources and propose corrections and additions; apply them only after maintainer approval. Until approved, implement exactly what is written here.

3.1 Contributor

Each contributor i has:

nominal (mm), upper_tol (≥ lower), lower_tol (signed, e.g. +0.2 / −0.0)
sensitivity aᵢ: +1 or −1 in 1D; any real number in linearized 2D/3D
distribution: normal (default), uniform, or truncated_normal
cp (process capability, default 1.0). Used only for normal-type distributions.

Midpoint re-centring of asymmetric tolerances (mandatory). Assumption: the process is centred on the tolerance midpoint, not on the nominal.

mean μᵢ = nominal + (upper_tol + lower_tol) / 2
half-range tᵢ = (upper_tol − lower_tol) / 2

Example: 10.0 +0.2/−0.0 → μ = 10.1, t = 0.1.

Sigma convention:

normal: σᵢ = tᵢ / (3·cpᵢ)
uniform over [μ−t, μ+t]: σᵢ = tᵢ / √3
truncated_normal: underlying normal with σ0 = tᵢ/(3·cpᵢ), truncated at μ ± tᵢ. σᵢ = σ0·√(1 − 2kφ(k)/(2Φ(k) − 1)), k = 3·cpᵢ.
Document all three in ASSUMPTIONS.md.
3.2 Stack result (linear case)
Mean of the requirement: μ_Y = Σ aᵢ μᵢ (plus any constant term)
Worst case: Y ∈ [μ_Y − Σ|aᵢ|tᵢ, μ_Y + Σ|aᵢ|tᵢ]
RSS (statistical): σ_Y = √(Σ aᵢ² σᵢ²). Report μ_Y ± 3σ_Y. Assumes contributors are statistically independent. μ_Y ± 3σ_Y contains 99.73 % only if Y is normal. If 3σ_Y exceeds the worst-case half-range, report a warning.
Optional: Modified/Bender RSS with a user-set correction factor k (default off): half-range = k·√(Σ(aᵢtᵢ)²). Uses tᵢ directly; cp and distribution are ignored. Source: Bender (1962), k = 1.5. If the result exceeds the worst-case half-range, report a warning (cap-or-warn is open question Q5 in docs/reports/phase-R.md). Document the formula and source.
Contribution %:
Worst case: |aᵢ|tᵢ / Σ|aⱼ|tⱼ
RSS: aᵢ²σᵢ² / Σaⱼ²σⱼ²
Each set must sum to 100% (assert to within 1e-9).
Predicted failure (normal assumption): P_fail = Φ((LSL − μ_Y)/σ_Y) + (1 − Φ((USL − μ_Y)/σ_Y)), with one-sided specs supported. Report as a fraction and as PPM. Also report Cpk = min(USL − μ, μ − LSL)/(3σ). With a one-sided spec, report Cpu = (USL − μ)/(3σ) or Cpl = (μ − LSL)/(3σ) only. If σ_Y = 0, P_fail and Cpk are not computed; report pass/fail from μ_Y alone.
3.3 Monte Carlo
Sample each contributor from its distribution with a seeded RNG. Vectorize; no Python loops over samples.
Evaluate the full (possibly nonlinear) requirement function Y = f(x₁…xₙ).
Default N = 100,000. Configurable.
Report: mean, std, min, max, percentiles (0.135, 2.5, 50, 97.5, 99.865), the fraction outside spec, and a Wilson 95% confidence interval on that fraction.
If 0 failures are observed, report the exact one-sided 95 % upper bound 1 − 0.05^(1/N) (≈ 3/N, the rule of three), labelled "one-sided 95 %" (the Wilson interval is labelled "two-sided 95 %"), rather than "0 ppm".
Convergence check: compare the std at N/2 and at N. Warn if the relative difference is > 1%.
3.4 Nonlinear stacks (Phase 3)
Y = f(x) is defined by a vector loop: a chain of 2D/3D vectors with lengths and angles.
Sensitivities aᵢ = ∂f/∂xᵢ at the means, computed analytically where possible. Otherwise use central finite differences with step h = max(1e-6, 1e-4·tᵢ). Test the two against each other. h is in the contributor's own unit (mm or rad). Analytic-vs-FD tests use both rel = 1e-6 and an abs tolerance, because relative error is undefined at zero sensitivity.
Linearized WC/RSS use these aᵢ. Monte Carlo uses the exact f.
Required consistency check: for small tolerances, the linearized RSS σ and the MC σ must agree within MC sampling error.
4. Input format (YAML, validated by pydantic)
yaml
schema_version: 1
units: mm
name: plate_stack_in_slot
requirement:
  description: gap between top plate and slot ceiling
  lsl: 0.0        # optional
  usl: null       # optional; at least one of lsl/usl required
contributors:
  - id: slot_depth
    nominal: 50.00
    upper_tol: 0.10
    lower_tol: -0.10
    sensitivity: 1
    distribution: normal
    cp: 1.0
  - id: plate_1
    nominal: 16.60
    upper_tol: 0.05
    lower_tol: -0.05
    sensitivity: -1
  # ...
analysis:
  methods: [worst_case, rss, monte_carlo]
  monte_carlo: {n: 100000, seed: 42}

Validation must reject: missing units, upper_tol < lower_tol, unknown distribution, duplicate ids, cp ≤ 0, and requirements with neither LSL nor USL. Every error message must name the field.

5. Phases (do them in order, and stop at each gate)
Phase R: Research and context (do this FIRST, before writing any code)

Goal: understand the domain well enough to catch mistakes in this spec, and verify Section 3 before any of it is implemented. Use web search and fetch. Prefer primary and authoritative sources (standards bodies, textbooks, university and NIST material, the documentation of OCCT/pythonocc, CadQuery, existing open-source tools) over blogs and SEO pages. Cite every source (title + URL). Distinguish what a source states from what you infer. If sources disagree, say so; don't pick silently.

R1. Domain context. Write docs/research/domain-notes.md covering, in plain language:

What tolerance stack-up analysis is, and the standard methods: worst case, RSS/statistical, modified RSS (Bender, Gladman, etc.), Monte Carlo, and the method of system moments. When each is appropriate, and the known criticisms of each.
How commercial tools (CETOL 6σ, 3DCS, SOLIDWORKS TolAnalyst, EZtol) model stacks at a high level, from their public documentation only. This is context, not a design to copy.
1D vs 2D vs 3D stacks; vector-loop (Chase / Gao) models vs direct linearization vs Monte Carlo on geometry; the role of Jacobians, sensitivities and the DOF/"small displacement torsor" (SDT) approach to GD&T.
Existing open-source tools (StackCore, Tol-Ninja, stackups, and anything else you find). What they do, what they don't, their licenses. Don't copy code from them.

R2. Verify Section 3 (core math). Treat Section 3 as a draft to be audited, not as truth. Keep everything that is correct. For each formula and convention, check it against at least one authoritative source and write the result in docs/research/math-review.md using this table:

| Item (e.g. mean shift, sigma = t/3Cp, RSS, Wilson CI, P_fail, Cpk, Bender factor, finite-difference step) | Spec says | Sources checked | Verdict: CORRECT / CORRECT-WITH-CAVEAT / WRONG / UNSURE | Action |

Specifically examine:

The treatment of asymmetric tolerances and the mean shift
The sigma convention (t/(3Cp)) and its link to Cp/Cpk, and the "6σ" and "Cp 1.33" conventions used in industry
Whether the normal-distribution assumption for the stack output is justified (central limit theorem) and its failure modes (few contributors, one dominant contributor, uniform inputs)
The Wilson interval, the rule-of-three bound, and the Monte Carlo convergence criterion
The linearization and the finite-difference step-size rule
The correction factors used in modified RSS, with the original source
Any sign-convention pitfalls in vector loops

R3. Find what is missing. List the things a serious tolerance-analysis tool should have that Section 3 or the phases don't cover (examples to investigate, not a checklist to blindly add: assembly shift/float and clearance-fit variation, mean shift/drift of processes, non-normal and skewed or truncated process distributions, correlated contributors, sensitivity-based "tolerance allocation" and cost-versus-tolerance trade-offs, geometric-feature variation in 3D, thermal expansion, gap-and-flush type requirements). Classify each as MUST-ADD-NOW / LATER / OUT-OF-SCOPE with a one-line reason. Don't add anything that isn't in the existing math without the maintainer's approval.

R4. Check the technical assumptions of later phases. In a short feasibility note (docs/research/feasibility.md), check against current documentation, and by running small throwaway scripts where possible:

Can the pythonocc-core version available from conda-forge for Python 3.11+ read STEP AP242 with semantic PMI (XCAFDoc_DimTolTool), and on which operating systems? What does it return for a real file? If PMI cannot be read reliably, say so and propose the fallback.
Where can public AP242 test files with PMI be obtained (e.g. NIST MBE PMI test models), and under what license can they be used or redistributed?
Is detecttol free on PyPI and GitHub? Check, and report; don't register anything.

R5. Research report and gate. Write docs/reports/phase-R.md (template in Section 9) with: a summary of what you learned, every place where Section 3 or any phase needed correction (give exact proposed edits), proposed additions, risks, and open questions for the maintainer. Then STOP. The maintainer reviews the proposed spec changes; only approved changes are applied to Section 3 and to docs/ASSUMPTIONS.md. Don't start Phase 0 until the maintainer approves.

Rule 1 applies to research too: a number or formula you can't trace to a source is marked UNSURE, never presented as fact.

Phase 0: Repo and CI
Package skeleton, environment.yml, pyproject.toml, ruff/mypy config, pre-commit, GitHub Actions matrix (3 OSes), README stub, docs/ASSUMPTIONS.md, docs/DECISIONS.md.
One smoke test. CI is green on all 3 OSes.
Gate: CI green, and conda env create + pytest work from a clean clone (state exactly how you verified this).
Phase 1: 1D math engine (core/)
Implement Section 3.1–3.3 for linear stacks. Python API: analyze(stack) -> StackResult (pydantic model).
Required tests:
Golden case A (derived below; must match exactly to the stated precision).
Golden case B: an asymmetric tolerance (mean shift).
A uniform-distribution case.
A one-sided spec case, plus a case with zero MC failures (checks the rule-of-three output).
Property tests (hypothesis):
WC half-range ≥ RSS 3σ half-range, for stacks whose contributors are all normal or truncated_normal with cp ≥ 1 (compare with a small absolute tolerance, not strict ≥)
Contribution sets each sum to 100%
Flipping all sensitivities negates μ_Y and leaves σ_Y unchanged
Scaling all tolerances by k > 0 scales σ_Y and the WC range by k
A single contributor gives WC range = t and RSS 3σ = t (normal, cp = 1)
MC std is within 2% of RSS σ for linear normal stacks at N = 200k
Same seed gives bit-identical MC output
Validation-error tests for every rule in Section 4.
Coverage of core/ ≥ 95%.

Golden case A (hand-derived; use as the anchor test): Slot depth 50.00 ±0.10 (a = +1). Three plates, each 16.60 ±0.05 (a = −1). Requirement: gap ≥ 0 (LSL = 0). Normal, cp = 1.

μ_Y = 50.00 − 3×16.60 = 0.20
WC half-range = 0.10 + 3×0.05 = 0.25 → range [−0.05, 0.45] (WC fails the spec)
RSS: 3σ_Y = √(0.10² + 3×0.05²) = √0.0175 = 0.1322876 (7 s.f.) → σ_Y = 0.0440959
RSS range ≈ [0.0677124, 0.3322876]
Contributions, WC: slot 40%, each plate 20%
Contributions, RSS: slot 0.01/0.0175 = 57.142857%, each plate 0.0025/0.0175 = 14.285714%
P_fail = Φ(−0.20/σ_Y) = Φ(−4.535574…). Compute the expected value in the test with scipy.stats.norm.cdf, not a hard-coded rounded number. It is ≈ 2.9 ppm, and the test must assert that it lies in 2.5–3.3 ppm as a sanity check.

Have the reviewer subagent re-derive all of the above independently.

Gate: all tests green, reviewer agrees with every golden value, ASSUMPTIONS.md updated.
Phase 2: CLI and reports
detecttol analyze stack.yaml [--format md|html|json] [--out DIR]
The report includes: input summary, results per method, a contribution table sorted descending, a MC histogram with LSL/USL lines, warnings (convergence, WC failure, zero-failure bound), and the tool version, seed and timestamp.
JSON output follows a versioned schema (schema_version). Commit a JSON Schema file and test the output against it.
Snapshot tests for the Markdown/JSON outputs of golden case A.
Gate: the CLI works on all 3 OSes in CI, and example files are in examples/.
Phase 3: 2D/3D nonlinear vector loops
Model a stack as a chain of vectors (length + direction/angle). Contributors can be lengths or angles.
Implement analytic or finite-difference sensitivities (Section 3.4).
Required closed-form tests (derive each in the docstring):
A pure 1D chain expressed as a vector loop must exactly reproduce golden case A.
Tilted pin: a pin of length L = 100 at angle θ from vertical. Tip lateral offset = L·sin θ. Check the sensitivity ∂/∂θ = L·cos θ at θ = 0 (= 100 mm/rad), and check the MC result against a direct sampling of L·sin θ.
A 2D triangle/angle case (e.g. the height of a wedge with an angle tolerance) with a closed-form answer.
Analytic vs finite-difference sensitivities agree to within 1e-6 relative.
Linear-vs-MC consistency for small tolerances, and a documented large-tolerance case where they diverge, which proves MC uses the exact f.
Gate: all closed-form tests pass and the reviewer confirms each derivation.
Phase 4: GD&T subset (gdt/)

Support only these, each converted to contributor deviations with documented conventions:

Size (± tolerance): already handled
Flatness / parallelism: a zone of width t → translational deviation of ±t/2 along the stack direction, but only where the envelope rule does not already contain it. For a regular feature of size whose size dimension is in the stack (ASME Y14.5-2018 5.8.1, Rule #1) the form tolerance is a refinement inside the size limits and adds nothing; this is the default for flatness. (Revised 2026-11-13 under the maintainer's delegation.)
Perpendicularity / angularity (orientation): a zone of width t over a feature length L → angular deviation ≈ ±atan(t/L); in Phase 3 loops, also a translational effect at the point of interest
Position (diametral zone, RFS): zone diameter T → radial deviation within T/2. In a 1D stack direction that is ±T/2. In 2D, sample uniformly within a disk of diameter T for MC, and document this choice.
Position at MMC/LMC with bonus tolerance: bonus = departure of the actual size from the MMC size towards LMC for an MMC callout (from the LMC size towards MMC for an LMC callout), limited to [0, size range], where the feature's actual size is itself sampled from its size tolerance. Total zone = T + bonus.
Datums: support simple primary/secondary/tertiary planar datum reference frames only. Document the limitations clearly.

Every convention must be in ASSUMPTIONS.md with its ASME Y14.5-2018 section reference. Mark each GD&T conversion "NEEDS HUMAN REVIEW" in the phase report; the maintainer will check them against a GD&T textbook or an expert.

Tests: hand-derived cases for each GD&T type, including two bonus-tolerance cases compared with the RFS equivalent (revised 2026-11-13 under the maintainer's delegation): (a) for a fixed process, the inspection reject rate with the bonus must be lower than at RFS — the sense in which the original expectation is true; (b) in the stack ("zone-fill") model, where the deviation is allowed to use the enlarged zone, the failure rate of a fixed positional limit must be higher than at RFS.
Gate: tests pass, reviewer agrees, and the human approves the conventions.
Phase 5: STEP AP242 reader (cad/)
Read the assembly structure (XCAF: STEPCAFControl_Reader, XCAFDoc_ShapeTool), part transforms and B-rep faces.
Read semantic PMI via XCAFDoc_DimTolTool: dimensions, geometric tolerances and datums, with links to their target faces. Verify that this API works in the installed pythonocc version before designing around it, and document what is and isn't supported.
Map PMI to the contributor/GD&T models from Phases 1–4.
Fallback: a YAML "annotation file" that attaches tolerances to faces by stable identifiers (part name + face index + face centroid/normal fingerprint) when the STEP file has no semantic PMI.
Test data: use the NIST MBE PMI validation and conformance test models (public STEP AP242 files with semantic PMI). Before using them, verify that they're available and what license they carry. Don't commit files whose license doesn't allow it; download them in a test fixture instead. Also generate small synthetic STEP assemblies programmatically (boxes and plates) with known dimensions.
Tests: the number of PMI items read matches the documented counts for the test models; synthetic assemblies give the exact nominal dimensions; bad or missing files give clear errors.
Gate: report precisely which PMI types are read correctly and which aren't.
Phase 6: Building stack chains from CAD
The user specifies the requirement by naming two faces (via CLI/YAML).
Detect part-to-part contacts (coincident planar faces with opposite normals within a geometric tolerance of 1e-6 mm) and build an assembly contact graph.
Find the dimension chain from face A to face B through the graph, project onto the measurement direction, and produce the stack (sensitivities from geometry).
Handle and report: no path found, multiple paths (list them and ask the user to choose), and unsupported (non-planar) contacts.
Tests: synthetic assemblies where the expected chain and the result are known by construction. Golden case A rebuilt as an actual STEP assembly must give identical results to the YAML version.
Gate: end-to-end STEP → report for at least 3 synthetic assemblies.
Phase 7: External validation and release
validation/ folder: cases where the maintainer provides the reference results (hand calcs, a textbook worked example, or SOLIDWORKS TolAnalyst output). For each one, record the source, the inputs, the reference output, detectTOL's output, and the difference. Never fabricate these.
Docs: README with a quick-start, a theory page (all formulas from Section 3), the GD&T conventions, limitations, and how to contribute.
Release v0.1.0 to PyPI via trusted publishing; CHANGELOG.
Gate: the human signs off on the validation table.
6. Code quality requirements
Type hints everywhere; mypy --strict must pass on core/.
Every public function gets a docstring with units, and with formulas where relevant.
Floating-point comparisons use pytest.approx or numpy.isclose with explicit rel and abs values. Justify the tolerance in a comment.
No hidden global state. No printing inside library code (use logging).
Small, focused commits with clear messages, one logical change each.
6b. Usage budget (keep the work lean without lowering the bar)

Correctness rules 1-9 never relax. Everything else should be economical:

One phase per session. At the start of a session read only SPEC.md and the previous phase report, not the whole repo history. End the session at the gate.
Run tests narrowly while developing (the file or test you're changing), and the full suite once at the end of the phase.
Keep command output short: use -q, --tb=short, and tail/head where the output is long.
Research (Phase R) is capped: about 25 searches/fetches in total. Prefer one good primary source per question over many secondary ones. If a question isn't settled within the cap, mark it UNSURE and ask the maintainer rather than searching on.
Don't re-read files you just wrote. Don't re-run unchanged tests.
Write short reports. Reports are for a human reader: bullets and real numbers, not narrative.
Suggested model per phase (the maintainer chooses; this is guidance): R, 1, 3, 4, 5, 6 need the strongest model available because they involve math, GD&T interpretation or OCCT quirks; 0, 2 and 7 (scaffolding, CLI, reports, docs) can use a smaller, cheaper model.
7. Verification protocol (every phase)
Write the tests before or alongside the implementation. For math code, write the hand derivation first.
Run the full suite, lint and mypy locally. Paste the real final summary lines (pass/fail counts, coverage total, lint/mypy result) into the phase report; never summarize from memory. Don't paste full logs; include a failing test's output only when it failed.
In math phases, start the reviewer subagent (Rule 8). Record its findings and how each was resolved.
Run at least one end-to-end example by hand and inspect the output for plausibility: a sign error or a ×2 error in σ should be visible.
List any known weaknesses honestly.
8. When to stop and ask the human
A spec ambiguity or a suspected error in this spec
Any GD&T interpretation question
An OCCT/pythonocc API that doesn't behave as documented
Any expected value you can't derive yourself
Any change to the public API or input schema after Phase 2
9. Phase report template (write it to docs/reports/phase-N.md and show it)
# Phase N report
## Done
## Test results (paste real output: pytest summary, coverage, ruff, mypy)
## Golden values and who verified them (you / reviewer subagent / human)
## Reviewer subagent findings and resolutions
## New assumptions added to ASSUMPTIONS.md
## Known limitations / open risks
## Items needing human review
## Proposed plan for Phase N+1

Start now with Phase R (research). At the end, write the Phase R report and stop. Don't write code until the maintainer approves the research report.