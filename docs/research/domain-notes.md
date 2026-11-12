# R1 — Domain notes

Phase R, 2026-11-12. Research cap: 24 of ~25 searches/fetches used.

**Evidence labels used in every research doc**

- **[S]** the cited source states this (I read it this session).
- **[D]** derived by me from definitions; derivation is in `math-review.md`.
- **[I]** my inference from sources.
- **[K]** background knowledge that I did **not** re-verify against a source inside the search cap. Treat as UNSURE until the maintainer confirms.

Source numbers refer to the list at the bottom.

## 1. What tolerance stack-up analysis is

- Parts vary inside their tolerances; an assembly requirement `Y = f(x1..xn)` (gap, clearance, interference, alignment) inherits that variation. Stack-up analysis predicts the range or distribution of `Y` from the part tolerances. [S1]
- Scholz's review restricts itself to requirements that are "linear or approximately linear functions of the relevant part dimensions" [S1, abstract]. That is the same scope as detectTOL Section 3.2.
- Two cornerstone methods, worst case (arithmetic) and RSS (statistical); everything else is a compromise between them. [S1 §1, §3, §4]

## 2. Methods

| Method | What it does | When appropriate | Known criticisms |
|---|---|---|---|
| **Worst case (arithmetic)** | Adds `|a_i|·t_i` linearly. [S1 §3] | Few contributors, safety-critical fits, 100 % interchangeability required. | Guards against a combination that "can only happen" when every part is simultaneously at its worst limit [S1 §4 intro]; gives needlessly tight part tolerances as n grows. |
| **RSS (statistical)** | `T_Y = sqrt(Σ (a_i t_i)^2)`, assuming independent, centred, normal parts with `t_i = 3σ_i`. [S1 §4.1] | Many contributors of comparable size, processes in statistical control and centred. | Assumptions "should not necessarily be accepted at face value" [S1 §4.1]. Optimistic if processes are off-centre (mean shift), non-normal, or correlated. The CLT argument fails when "a small number of terms … completely swamp the variation of the remaining terms" [S1 §4.2, Assumption 3]. For n = 2 uniform parts the sum is triangular, not normal. [S1, later section; exact section number not captured from my text extraction] |
| **Modified RSS — inflation factors** | `T_Y = c · RSS`. Bender (1962) gives `c = 1.5`. [S1 §4.2] Distribution-specific factors per contributor: normal 1, uniform 1.732, triangular 1.225, elliptical 1.5, etc. [S1 Table 1] | Quick conservative correction when process data are not available. | Bender's 1.5 is empirical: operators "usually give you 2/3 of the true spread" when asked what they can hold, so multiply by 3/2. [S1 §4.2] Greenwood & Chase call using it against mean shift "a Band-Aid". [S1 §5] For small n, `1.5·RSS` exceeds worst case. [D] |
| **Mean-shift models** | Stack the mean shifts arithmetically (worst case) and the remaining within-tolerance variation by RSS. Proposed by Mansoor (1963), extended by Greenwood & Chase (1987). [S1 §5.1] | Processes that cannot be centred (tool wear, setup error). | Needs a per-part shift fraction, which the designer usually has to guess. [I] |
| **Monte Carlo** | Sample each input, evaluate the exact `f`, count failures. | Nonlinear `f`, non-normal inputs, any case where the output is not normal. | Sampling error on small failure rates: at N = 100 000 a true 3 ppm rate usually shows zero failures. [D] Needs input distributions that are rarely known. [I] |
| **Method of system moments** | Propagate the first four moments of each input through a Taylor expansion of `f` (first or second order), then fit a distribution to the output moments. Associated with Evans (1975) and Cox (1986). [K; both are cited by S1 §1 as stack-analysis references, but I did not read them] | Nonlinear `f` where MC is too slow; gives a second-order mean shift that pure linearisation misses. | Needs second derivatives; fitted output distribution is an approximation. [K] |

**Disagreement between sources.** The Bender citation is given as *Graphic Science*, December 1962 by a journal bibliography [S2] and by Scholz (year only) [S1]; a forum/blog pair instead attributes it to an SAE paper from 1968 [S3]. I could not open the primary. I use "Bender (1962)" and mark the exact citation UNSURE.

**Gladman.** root.md names Gladman as a modified-RSS source. I found only a bibliographic entry (C. A. Gladman, "Applying Probability to Tolerances Used in Engineering Design", Trans. Inst. Eng. Australia, 1980) [S2]. What factor Gladman proposes: UNSURE, not verified.

## 3. 1D vs 2D vs 3D

- **1D**: every contributor lies along the measurement direction; `a_i = ±1`. Misses angular effects (a tilted part changes the stack by `L·sin θ`). [D]
- **2D/3D vector loop (Chase / Gao / Magleby)**: the assembly is modelled as chains of vectors. Open loops describe the critical assembly feature; closed loops describe kinematic constraints between mating parts. The method covers "small kinematic adjustments between mating parts". [S4, abstract of Gao, Chase & Magleby 1998]
- **Direct linearisation (DLM)**: first-order Taylor expansion of the loop equations gives a sensitivity (Jacobian) matrix; WC and RSS are then applied to the linear model. The same group published a comparison of DLM with Monte Carlo (1995). [S4]
- **Monte Carlo on geometry**: resample dimensions and re-solve the (nonlinear) assembly each time. This is the 3DCS approach. [K]
- **Small displacement torsor (SDT)**: a feature's deviation from nominal is written as three small translations and three small rotations; Bourdet introduced it (originally to fit a surface to a point cloud). [S5] The **unified Jacobian–torsor model** (Desrochers, Ghie, Laperrière 2003) uses torsors with constraints to bound tolerance zones and a Jacobian to propagate them to the functional requirement. [S5]
- Relevance to detectTOL: Phase 3 is an open-loop vector model without kinematic adjustment (no closed loops). Phase 4 uses per-feature translation/rotation deviations, which is a simplified SDT view without the zone constraints that couple translation and rotation. [I] — see open questions in the phase report.

## 4. Commercial tools (public information only)

The one search I spent on vendor documentation returned nothing authoritative. Everything in this table is **[K] and UNSURE**; I recommend the maintainer either confirms from vendor docs or accepts that this section is context only.

| Tool | High-level model |
|---|---|
| CETOL 6σ (Sigmetrix) | Sensitivity/derivative-based statistical analysis on a CAD-integrated assembly model; a thesis on CETOL lists a "derivative-based analysis" section [S6, secondary]. System-moments attribution: [K]. |
| 3DCS Variation Analyst | Monte Carlo simulation on points and features of the CAD geometry. [K] |
| SOLIDWORKS TolAnalyst | Worst-case and RSS min/max over a DimXpert-annotated assembly. [K] |
| EZtol (Sigmetrix) | 1D stack-up tool with CAD integration (CATIA, NX, SOLIDWORKS). [S7, product listing] |

## 5. Existing open-source tools

Do not copy code from any of these.

| Tool | What it does | What it does not | License |
|---|---|---|---|
| **StackCore** (PyPI `stackcore` 0.3.3, 2025-07) | Monte Carlo stack-up for "linear and geometric assemblies", worst case, histograms; numba-parallel variant. [S8] | RSS not mentioned; no STEP/PMI import (a separate Fusion 360 add-in exists). [S8] | MIT [S8] |
| **Tol-Ninja** (GitHub `slehmann1/Tol-Ninja`) | Tkinter GUI stack-up tool, numpy/scipy, PDF report. Last push 2022-06. [S9] | No CAD import; GUI-first. [S9, I] | MIT [S9] |
| **stackups** (PyPI) | Stack-up package. [S10] | — | **Proprietary**, paid per seat — not open source. [S10] |
| **otaf** (Open Tolerance Analysis Framework) | Statistical tolerance analysis of mechanical assemblies. [S10] | Not checked. | GPLv3 [S10] — incompatible with copying into an Apache-2.0 project. |
| **Statistical Tolerance Analysis and Synthesis with Python** | Code accompanying a 2021 paper. [S10] | Not a maintained library. [I] | MIT (code), CC BY 4.0 (paper) [S10] |

Gap that detectTOL would fill [I]: none of the above reads STEP AP242 PMI, and none documents hand-derived golden values with independent verification.

## Sources

1. F. Scholz, *Tolerance Stack Analysis Methods — A Critical Review*, Boeing Information & Support Services, Nov 1995. https://faculty.washington.edu/fscholz/DATAFILES498B2008/TOLSTACK.pdf
2. Bibliography in Korea Science article listing Bender (1962) and Gladman (1980). https://koreascience.or.kr/article/JAKO200509906395776.page
3. Eng-Tips thread "MRSS = 1.5 × RSS, why 1.5 factor" (low authority). https://www.eng-tips.com/threads/mrss-1-5-rss-why-1-5-factor.439698
4. J. Gao, K. W. Chase, S. P. Magleby, "Generalized 3-D tolerance analysis of mechanical assemblies with small kinematic adjustments", *IIE Transactions* 30(4), 367–377, 1998 (abstract only). https://scilit.net/publications/d1546ca77cfb3d2f3ec8d7e3a662f1d8
5. Desrochers, Ghie, Laperrière, "Application of a Unified Jacobian–Torsor Model for Tolerance Analysis", *ASME JCISE*, 2003 (abstract). https://next.sciencegate.app/document/10.1115/1.1573235 ; Polini & Marziale review of Jacobian and torsor models. https://typeset.io/pdf/a-review-of-two-models-for-tolerance-analysis-of-an-assembly-dtfqj4hgls.pdf
6. M. Pergolato, thesis using CETOL 6σ, Univ. Bologna (secondary). https://amslaurea.unibo.it/26907/1/Thesis_Pergolato_Marco.pdf
7. Sigmetrix EZtol product page. https://www.sigmetrix.com/marketplace/eztol-1-year-subscription-for-catia-nx-and-solidworks
8. StackCore on PyPI. https://pypi.org/project/stackcore/
9. Tol-Ninja on GitHub. https://github.com/slehmann1/Tol-Ninja
10. PyPI `stackups` https://pypi.org/project/stackups ; otaf and the 2021 paper repository as returned by search (ecosyste.ms index). https://science.ecosyste.ms/projects/13533
11. K. W. Chase & A. R. Parkinson, "A survey of research in the application of tolerance analysis to the design of mechanical assemblies", *Research in Engineering Design* 3(1), 23–37, 1991 — located but full text not obtained. https://www.sciencegate.app/document/10.1007/bf01580066
