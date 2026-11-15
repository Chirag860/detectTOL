"""Independent checks for the diameter plan (fits, pin float, positions).

Like ``verify_golden.py`` this imports nothing from ``detecttol`` and only the
standard library. It does two things:

1. **Plausibility of the extracted ISO 286 fundamental deviations.** ISO 286-1
   gives formulae for the shaft fundamental deviations (D = geometric mean of the
   size step, result in micrometres), e.g. g: es = -2.5 D^0.34. The table in
   ``src/detecttol/standards/iso286.py`` (read here as text, with ``ast``) is
   compared with them. The printed table is rounded by the standard's own rules,
   which this script does not reproduce, so the comparison reports the largest
   difference per letter and flags any step that differs by more than a rounding
   allowance (1 um, or 5 % for values above 20 um). **This is a plausibility check,
   not a verification**: the table still needs a printed IS 919 / ISO 286 copy.

2. **The golden values of the tests**, recomputed from first principles: fit limits
   and kinds, the pin float, positions with and without the MMC bonus, the pin-chain
   worst case and RSS sigma, and the clearance-fit RSS sigma.

Run:  python validation/verify_diameters.py
Exit code 0: every golden value agreed. Table steps that differ from the formulae
are listed as NEEDS HUMAN CHECK (they do not change the exit code): the formulae
are approximations the printed table may depart from, and only a printed copy can
settle them.
"""

from __future__ import annotations

import ast
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FAILURES: list[str] = []
FLAGS: list[str] = []


def _table(name: str):  # type: ignore[no-untyped-def]
    """A module-level constant of iso286.py, read without importing the package."""
    tree = ast.parse((ROOT / "src" / "detecttol" / "standards" / "iso286.py").read_text("utf-8"))
    for node in tree.body:
        target = node.target if isinstance(node, ast.AnnAssign) else None
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
        if isinstance(target, ast.Name) and target.id == name and node.value is not None:
            return ast.literal_eval(node.value)
    raise KeyError(name)


SIZE_STEPS = _table("SIZE_STEPS")
IT5_TO_IT11 = _table("_IT5_TO_IT11")
DEV_STEPS = _table("DEVIATION_STEPS")
ES = _table("_SHAFT_ES_UM")
EI = _table("_SHAFT_EI_UM")


def it(nominal: float, grade: int) -> int:
    i = next(k for k, up in enumerate(SIZE_STEPS) if nominal <= up + 1e-9)
    return IT5_TO_IT11[i][grade - 5]


def mean_d(i: int, values: tuple[int, ...]) -> float:
    """Geometric mean D of the size step the value at deviation step ``i`` belongs to.

    The standard computes most deviations over the main size steps (e.g. 10-18 mm)
    and only some over the intermediate ones (10-14, 14-18). A main step is used
    when the table gives the same value for all its intermediate steps. The first
    step uses 1 and 3 mm.
    """
    hi = DEV_STEPS[i]
    main = next(k for k, up in enumerate(SIZE_STEPS) if hi <= up + 1e-9)
    main_lo = 0.0 if main == 0 else SIZE_STEPS[main - 1]
    same = [values[j] for j, up in enumerate(DEV_STEPS) if main_lo < up <= SIZE_STEPS[main] + 1e-9]
    if len(set(same)) == 1:
        lo, hi = (1.0 if main == 0 else main_lo), SIZE_STEPS[main]
    else:
        lo = 1.0 if i == 0 else DEV_STEPS[i - 1]
    return math.sqrt(lo * hi)


#: Known places where the printed table departs from the formula on purpose.
DOCUMENTED = {("m", 0): "m up to 3 mm is +2 um in the table (m6 = +8/+2), not IT7 - IT6 = 4"}


FORMULAE = {
    # letter: (table, formula in um of D)
    "c": (ES, lambda d: -52 * d**0.2 if d <= 40 else -(95 + 0.8 * d)),
    "d": (ES, lambda d: -16 * d**0.44),
    "e": (ES, lambda d: -11 * d**0.41),
    "f": (ES, lambda d: -5.5 * d**0.41),
    "g": (ES, lambda d: -2.5 * d**0.34),
    "k47": (EI, lambda d: 0.6 * d ** (1 / 3)),
    "n": (EI, lambda d: 5 * d**0.34),
}


def table_plausibility() -> None:
    print("1. ISO 286 fundamental deviations: table vs ISO 286-1 formulae (plausibility)")
    for letter, (table, formula) in FORMULAE.items():
        worst = 0.0
        flagged = []
        for i, value in enumerate(table[letter]):
            f = formula(mean_d(i, table[letter]))
            diff = abs(value - f)
            allowance = max(1.0, 0.05 * abs(value)) if abs(value) > 20 else 1.0
            worst = max(worst, diff)
            if diff > allowance + 0.5:  # +0.5: the formula value itself is unrounded
                flagged.append(f"step {i} (<= {DEV_STEPS[i]:g} mm): table {value}, formula {f:.1f}")
        status = "ok" if not flagged else f"{len(flagged)} step(s) flagged"
        print(f"   {letter:>3}: largest |table - formula| = {worst:.2f} um  [{status}]")
        for line in flagged:
            print(f"        {line}")
            FLAGS.append(f"table {letter}: {line}")
    # m = IT7 - IT6 at the IT step of each deviation step (exact rule, no rounding)
    bad = []
    for i, value in enumerate(EI["m"]):
        nominal = DEV_STEPS[i]
        expected = it(nominal, 7) - it(nominal, 6)
        if value != expected:
            if ("m", i) in DOCUMENTED:
                print(f"     m: step <= {nominal:g}: documented exception: {DOCUMENTED[('m', i)]}")
                continue
            bad.append(f"step <= {nominal:g}: m {value} vs IT7 - IT6 = {expected}")
    print(f"     m: equals IT7 - IT6 at every other step  [{'ok' if not bad else 'MISMATCH'}]")
    FAILURES.extend(bad)


def check(label: str, computed: float, expected: float, tol: float = 1e-12) -> None:
    ok = abs(computed - expected) <= tol
    print(f"   {'ok ' if ok else 'BAD'} {label}: {computed:.12g} (test: {expected:.12g})")
    if not ok:
        FAILURES.append(label)


def golden() -> None:
    print("2. Golden values of the tests, recomputed")
    # fit H7/g6 dia 20 (hole +0.021/0, shaft -0.007/-0.020)
    hole_lo, hole_hi = 20.0, 20.021
    shaft_lo, shaft_hi = 19.980, 19.993
    check("H7/g6 smallest clearance", hole_lo - shaft_hi, 0.007)
    check("H7/g6 largest clearance", hole_hi - shaft_lo, 0.041)
    sigma = math.hypot((hole_hi - hole_lo) / 6, (shaft_hi - shaft_lo) / 6)
    check(
        "H7/g6 RSS sigma (normal, Cp 1: range/6 each)",
        sigma,
        math.sqrt(0.0035**2 + (0.0065 / 3) ** 2),
    )
    # table spot values: limit = deviation + IT
    check("g6 at 20: es -7 (18-24), ei = es - IT6(18-30)", (-7 - it(20, 6)) / 1000, -0.020)
    check("k6 at 25: ei +2, es = ei + IT6", (2 + it(25, 6)) / 1000, 0.015)
    check("p6 at 50: ei +26, es = ei + IT6(30-50)", (26 + it(50, 6)) / 1000, 0.042)
    check("F8 at 20: EI = +20, ES = EI + IT8", (20 + it(20, 8)) / 1000, 0.053)
    # fit kinds at 25 with H7 (25.000 .. 25.021)
    check("H7/k6 smallest clearance (transition)", 25.0 - 25.015, -0.015)
    check("H7/s6 largest clearance (interference)", 25.021 - 25.035, -0.014)
    # pin float: hole 6.2 +/-0.05, pin 6 +0/-0.02
    half = (6.25 - 5.98) / 2
    check("pin float half range", half, 0.135)
    # positions: RFS T/2; MMC zone grows by the hole's size range (0.1) at most
    check("position RFS half zone", 0.1 / 2, 0.05)
    check("position MMC largest half zone", (0.1 + (6.25 - 6.15)) / 2, 0.1)
    # pin chain B1 -> hole -> pin -> hole -> B2
    check("pin chain worst case (RFS)", 0.05 + half + half + 0.05, 0.37)
    check("pin chain worst case (MMC)", 0.1 + half + half + 0.1, 0.47)
    rss = math.sqrt(2 * (0.05 / 3) ** 2 + 2 * (half / math.sqrt(3)) ** 2)
    check("pin chain RSS sigma (normal / uniform)", rss, 0.1127189228, tol=1e-10)
    # general tolerance m: dia 6 (3-6) +/-0.1, dia 6.2 and 20 (6-30) +/-0.2
    check("pin float with class m", ((6.2 + 0.2) - (6.0 - 0.1)) / 2, 0.25)


def main() -> int:
    table_plausibility()
    golden()
    print()
    if FLAGS:
        print(f"NEEDS HUMAN CHECK against a printed IS 919 / ISO 286 ({len(FLAGS)} table step(s)):")
        for f in FLAGS:
            print(f"  - {f}")
    if FAILURES:
        print(f"{len(FAILURES)} problem(s):")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("all golden values agree (the table check is plausibility only, see the module notes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
