"""Fixtures for the CAD tests.

The CAD tests need ``pythonocc-core`` and are skipped where it is not installed
(the pip-only CI job). The NIST tests also need the NIST PMI STEP files:

- set ``DETECTTOL_NIST_DIR`` to a folder that already holds the ``.stp`` files, or
- let the fixture download the NIST archive once into the pytest cache
  (checksum-pinned). Without network access those tests are skipped with a
  message; they are never silently passed.

NIST states that "the test cases, CAD models, and STEP files can be used without
any restrictions" and asks for acknowledgement. The files are not committed.
"""

from __future__ import annotations

import hashlib
import os
import urllib.request
import zipfile
from pathlib import Path

import pytest

NIST_URL = "https://www.nist.gov/system/files/documents/noindex/2024/06/19/NIST-PMI-STEP-Files.zip"
NIST_SHA256 = "8fa78429e6d8d9b0d7681d223b6aa9ec98c3772185c55b1a0e3679b21c181911"


@pytest.fixture(scope="session")
def nist_dir(request: pytest.FixtureRequest) -> Path:
    """Folder containing the NIST AP242 ``.stp`` files."""
    override = os.environ.get("DETECTTOL_NIST_DIR")
    if override:
        folder = Path(override)
        if not any(folder.glob("nist_ctc_01*ap242*.stp")):
            pytest.fail(f"DETECTTOL_NIST_DIR={override} does not contain the NIST files")
        return folder
    cache = request.config.cache.mkdir("nist_pmi_step_files")
    folder = Path(cache) / "NIST-PMI-STEP-Files"
    if any(folder.glob("nist_ctc_01*ap242*.stp")):
        return folder
    archive = Path(cache) / "NIST-PMI-STEP-Files.zip"
    try:
        req = urllib.request.Request(NIST_URL, headers={"User-Agent": "detecttol-tests"})
        with urllib.request.urlopen(req, timeout=120) as response:
            archive.write_bytes(response.read())
    except OSError as exc:
        pytest.skip(f"NIST test files could not be downloaded ({exc})")
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    if digest != NIST_SHA256:
        pytest.fail(f"NIST archive checksum mismatch: {digest}")
    with zipfile.ZipFile(archive) as zf:
        zf.extractall(cache)
    return folder
