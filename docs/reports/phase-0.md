# Phase 0 report — repo and CI

2026-11-12. Not stopped at this gate, on the maintainer's instruction ("continue non stop till phase 2").

## Done

- Git repository initialised on branch `main` (local only; no remote).
- Package skeleton `src/detecttol/{core,gdt,cad,io,report,cli}`; `gdt/` and `cad/` are empty placeholders.
- `pyproject.toml` (setuptools, Apache-2.0, console script `detecttol`), `environment.yml`, ruff and mypy config, `.pre-commit-config.yaml`, `.gitattributes`, `.gitignore`, `LICENSE`, README.
- `docs/ASSUMPTIONS.md` (Phase R) and `docs/DECISIONS.md` (21 decisions, 19 of them provisional).
- GitHub Actions workflow `.github/workflows/ci.yml`: a pip-only job (3 OSes × Python 3.11/3.12: ruff, format check, mypy, pytest, CLI run) and a conda job (3 OSes, full `environment.yml`).
- Smoke test `tests/test_smoke.py`.
- Miniforge 26.9.4 installed for the current user at `%USERPROFILE%\miniforge3` (installer signature: Valid; not added to PATH, not registered as system Python).

## Gate status

| Gate item | Status |
|---|---|
| `conda env create` + `pytest` from a clean clone | **Met on Windows** (details below) |
| CI green on windows-latest, macos-latest, ubuntu-latest | **NOT MET — CI has never run.** There is no GitHub repository and no `gh` CLI here. The workflow file is unverified. |

## Test results

### How the clean-clone check was done (exact steps)

1. `git clone C:\Users\DELL\Desktop\detectTOL <scratch>\clean` at commit `5f5b3e7`.
2. In the clone: `conda env create -n detecttol-clean -f environment.yml` (a new environment, separate from the development one).
3. `conda run -n detecttol-clean python -m pytest`.
4. `conda run -n detecttol-clean detecttol analyze examples/golden_case_a.yaml --format json`.

Real output:

```
Installing pip dependencies: ...working... done
111 passed in 8.03s
{
  "schema_version": 1,
  "tool": {
```

### Pip-only route (what the fast CI job does), same clean clone

`py -m venv .venv` with the system Python 3.14.8, then `pip install -e ".[dev]"`, pytest, ruff, mypy, CLI:

```
Python 3.14.8
TOTAL                                 560      3    116      3    99%
111 passed in 8.15s
All checks passed!
43 files already formatted
Success: no issues found in 6 source files
{
  "schema_version": 1,
  "tool": {
```

Note: the verification script as a whole ended with exit code 255. Every check above had already printed its passing result; the last command piped the CLI's JSON into "first 3 lines only", which closes the pipe early. I attribute the exit code to that and did not re-run it. A clean CLI exit (code 0, empty stderr) is covered by the subprocess test `test_python_dash_m_entry_point_runs_end_to_end`.

So the suite passes on two Python versions (3.12 conda, 3.14 pip), both on Windows.

### Development environment

Python 3.12.16, numpy 2.5.4, scipy 1.18.1, pydantic 2.14.3, pythonocc-core 8.0.1.2:

```
111 passed in 13.33s
ruff check: All checks passed!
ruff format: 43 files already formatted
mypy: Success: no issues found in 6 source files
```

## Golden values and who verified them

None in this phase.

## Reviewer subagent findings and resolutions

Not required for Phase 0 (root.md rule 8).

## New assumptions added to ASSUMPTIONS.md

None.

## Known limitations / open risks

- **CI unverified** (see gate table). Likely trouble spots when it first runs: the conda job's shell activation on Windows, and matplotlib font caching time.
- macOS and Linux have not been tested at all.
- On Windows the conda env must be activated: calling its `python.exe` directly crashed inside matplotlib/numpy (delay-load error 0xc06d007f). `conda activate detecttol` or `conda run -n detecttol …` works.
- `environment.yml` pins `pythonocc-core>=8.0.1`, which makes the environment large and slow to create, although nothing uses it before Phase 5.
- The pre-commit hooks are configured but were not installed or run (`pre-commit install` needs the maintainer's go-ahead to touch `.git/hooks`).
- Commits are authored as "Chirag" with the maintainer's e-mail, set in this repository's local git config only.

## Items needing human review

1. Create a GitHub repository, push `main`, and look at the first CI run.
2. Q15: is the LGPL-3.0 pythonocc dependency acceptable for an Apache-2.0 project?
3. Q14: keep `root.md` as the spec file name, or rename to `SPEC.md`?

## Proposed plan for Phase 1

Done in the same run — see `phase-1.md`.
