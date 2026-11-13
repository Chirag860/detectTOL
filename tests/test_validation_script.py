"""The independent golden-value verification must keep passing."""

from __future__ import annotations

import subprocess
import sys

from tests.conftest import REPO_ROOT


def test_independent_verification_of_golden_values() -> None:
    """validation/verify_golden.py recomputes every hand-derived constant of the
    test suite without importing detecttol (numerical integration, explicit
    rotation matrices, finite differences) and exits 0 only if all agree."""
    proc = subprocess.run(
        [sys.executable, "-I", str(REPO_ROOT / "validation" / "verify_golden.py")],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "86 of 86 golden values confirmed independently" in proc.stdout
