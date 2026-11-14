# App plan, Step 4 report: one-click Windows install and user guide

2026-11-14. Windows 11, Miniforge (conda), SOLIDWORKS 2026 (rev 34.4.1).

## Done

- **`installer/install_detectTOL.bat`** (double-click) runs `installer/install.ps1`. It works per user and needs no administrator rights:
  1. It finds conda (Miniforge / Miniconda / Anaconda, user or machine-wide, or on PATH). If there is none, it **asks** before downloading Miniforge from its official GitHub release, then installs it silently for this user.
  2. It creates the `detecttol` environment from `installer/environment-app.yml` (run-time packages only: no dev tools, plus nicegui, pywin32 and pillow). If the environment exists, it only adds the app's packages, with `--freeze-installed` so nothing else changes.
  3. It installs detectTOL from the folder: editable for a git clone, so `git pull` updates the app; a normal install otherwise.
  4. It checks that `detecttol`, `OCC`, `nicegui` and `win32com` import.
  5. It writes `%LOCALAPPDATA%\detectTOL\detectTOL.bat` (activates the environment and starts the app) and a ± icon. It creates a **detectTOL** shortcut on the Desktop and in the Start menu, minimised.

  Options: `-DryRun` (show the steps, change nothing), `-EnvName`, `-NoShortcuts`.
- **`installer/uninstall_detectTOL.bat`** removes the shortcuts and the launcher. It removes the conda environment only if you answer `y`.
- **App lifetime:**
  - **Quit** button in the header;
  - stops by itself 60 s after the last browser tab closed;
  - a second start (e.g. a double-click while it runs) only opens the browser.
- **App fixes** found while taking the guide screenshots:
  - Typing an exact face name (`Frame:4`) chooses it; before, it needed a click on the entry.
  - The right column no longer wraps below the left one once the chain table appears.
- **`docs/USER_GUIDE.md`** covers: install; putting DimXpert tolerances in SolidWorks; the four app steps with screenshots (`docs/guides/img/`); how to read the result; what to do when something goes wrong; limits. The README links it.
- DECISIONS D72 (setup script now, single .exe later) and D73 (app lifetime).

## Checked on this PC

| Check | Result |
|---|---|
| `install.ps1 -DryRun` | listed exactly the 5 steps, changed nothing |
| `install.ps1` (environment already existed) | packages present; detectTOL reinstalled editable; *detecttol 0.1.0.dev0, nicegui 4.0.0, OK*; launcher, icon and both shortcuts written |
| Shortcuts | target the launcher, icon set, window minimised (style 7) |
| Desktop shortcut double-click (started with `Start-Process`) | app listening on 127.0.0.1:8765, served by `python -m detecttol app`; your default browser opened |
| Quit button | process gone, port free |
| Second start while running | printed *detectTOL is already running: http://127.0.0.1:8765*, no second server |
| Idle shutdown | *not observed live*: the tab the shortcut opened in your Chrome stayed connected, which correctly keeps the app alive. Covered by tests instead (below). |
| Full app flow for the guide (SolidWorks route) | same results as Step 3: chain Block_C → B → A → Frame, *Always fits … 0.54 and 1.36 mm* |

**Not tested:** a first install on a PC without conda (the Miniforge download path), and installing from a downloaded ZIP (non-editable). Both need a clean machine or a Windows user account without conda.

## Test results

Real output of the final run:

```
421 passed, 2 skipped in 22.80s          (the 2 skipped = live SolidWorks tests)
DETECTTOL_SOLIDWORKS=1 tests/solidworks/test_live.py: 2 passed in 25.43s
ruff check: All checks passed!   ruff format --check: 119 files already formatted
mypy (core, strict): Success: no issues found in 8 source files
```

New: `tests/app/test_lifecycle.py`:
- waits for a first tab, then stops after the idle time;
- a reconnecting tab resets the idle clock;
- port-in-use detection.

## Known limitations / open risks

- **The installer needs the internet** the first time (conda packages, about 1 GB) and takes 5–15 minutes.
- **First-time install is untested** on a PC without conda. Neither is a ZIP download (see above).
- **No single .exe yet.** A colleague needs the folder (git or ZIP) and runs the installer once. A conda `constructor` installer is the next option if you want to hand out one file.
- **The browser and the console:** the shortcut starts a minimised console window (the app's log) and opens your default browser. Closing the console stops the app immediately.
- **Updating** means re-running the installer (or `git pull` for a clone). There is no update check inside the app.

## Items needing your review

1. Double-click the **detectTOL** Desktop icon, open one of your own assemblies, and tell me what is unclear in the app or in [docs/USER_GUIDE.md](../USER_GUIDE.md).
2. D72: is a setup script fine for now, or do you need a single installer `.exe` to give to colleagues?
3. If you can, try the installer on a second PC or Windows account without conda. That's the untested path.

## Next (Step 5 of the plan)

Validation with your real models: 2–3 assemblies, compared with a hand calculation or SolidWorks TolAnalyst. Results go into `validation/`. This is also Phase 7's input.
