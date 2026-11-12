"""Load and validate a stack definition from YAML (spec Section 4)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from detecttol.core.models import Stack


class StackInputError(ValueError):
    """The input file is missing, unreadable or fails validation.

    ``errors`` holds one message per problem; each message starts with the
    dotted path of the offending field, e.g. ``contributors[1].cp: ...``.
    """

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("; ".join(errors))


def _format_loc(loc: tuple[int | str, ...]) -> str:
    out = ""
    for part in loc:
        if isinstance(part, int):
            out += f"[{part}]"
        else:
            out += f".{part}" if out else str(part)
    return out or "(root)"


def parse_stack(data: Any) -> Stack:
    """Validate already-parsed data (a mapping) into a :class:`Stack`.

    Raises:
        StackInputError: with one field-named message per validation problem.
    """
    if not isinstance(data, dict):
        raise StackInputError(["(root): the document must be a mapping of fields"])
    try:
        return Stack.model_validate(data)
    except ValidationError as exc:
        messages = []
        for err in exc.errors():
            loc = _format_loc(tuple(err["loc"]))
            msg = str(err["msg"]).removeprefix("Value error, ")
            messages.append(f"{loc}: {msg}")
        raise StackInputError(messages) from exc


def load_stack(path: str | Path) -> Stack:
    """Read a YAML stack file and return the validated :class:`Stack`.

    All dimensions in the file must be millimetres (``units: mm``).

    Raises:
        StackInputError: file not found, not valid YAML, or failing validation.
    """
    p = Path(path)
    if not p.is_file():
        raise StackInputError([f"file not found: {p}"])
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise StackInputError([f"{p}: not valid YAML ({exc})"]) from exc
    return parse_stack(data)
