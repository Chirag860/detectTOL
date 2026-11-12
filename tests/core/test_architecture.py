"""Architecture rule: core/ never imports OCCT (and nothing outside core)."""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import detecttol.core

CORE_DIR = Path(detecttol.core.__file__).parent
FORBIDDEN_ROOTS = {"OCC", "OCP"}
ALLOWED_DETECTTOL = "detecttol.core"


def _imported_modules(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


def test_core_sources_do_not_import_cad_or_other_subpackages() -> None:
    files = sorted(CORE_DIR.glob("*.py"))
    assert files
    for path in files:
        for name in _imported_modules(path):
            assert name.split(".")[0] not in FORBIDDEN_ROOTS, f"{path.name} imports {name}"
            if name.startswith("detecttol"):
                assert name.startswith(ALLOWED_DETECTTOL), f"{path.name} imports {name}"


def test_importing_the_package_does_not_load_occt() -> None:
    code = (
        "import sys, detecttol, detecttol.io, detecttol.report, detecttol.cli.main;"
        "bad = [m for m in sys.modules if m.split('.')[0] in ('OCC', 'OCP')];"
        "sys.exit(1 if bad else 0)"
    )
    proc = subprocess.run([sys.executable, "-c", code], check=False, capture_output=True)
    assert proc.returncode == 0, proc.stderr.decode()
