"""OCCT housekeeping shared by the CAD modules."""

from __future__ import annotations

import contextlib

from OCC.Core.Message import message

_silenced = False


def silence_occt() -> None:
    """Stop OCCT from writing transfer statistics and parser errors to the console.

    OCCT prints through its default messenger; library code must not print
    (root.md, section 6), so its printers are removed once per process. Errors
    still reach the caller as return codes, which the readers turn into
    exceptions.
    """
    global _silenced
    if _silenced:
        return
    with contextlib.suppress(Exception):
        message.DefaultMessenger().ChangePrinters().Clear()
    _silenced = True
