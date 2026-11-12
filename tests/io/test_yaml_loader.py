"""YAML loading: examples load, bad files give clear errors."""

from __future__ import annotations

from pathlib import Path

import pytest

from detecttol import analyze
from detecttol.io import StackInputError, load_stack
from tests.conftest import EXAMPLES


@pytest.mark.parametrize("path", sorted(EXAMPLES.glob("*.yaml")), ids=lambda p: p.name)
def test_every_example_loads_and_analyses(path: Path) -> None:
    result = analyze(load_stack(path))
    assert result.contributors
    assert result.monte_carlo is not None


def test_golden_case_a_example_matches_the_spec_input() -> None:
    stack = load_stack(EXAMPLES / "golden_case_a.yaml")
    assert stack.name == "plate_stack_in_slot"
    assert [c.id for c in stack.contributors] == ["slot_depth", "plate_1", "plate_2", "plate_3"]
    assert [c.sensitivity for c in stack.contributors] == [1.0, -1.0, -1.0, -1.0]
    assert stack.requirement.lsl == 0.0 and stack.requirement.usl is None
    assert stack.analysis.monte_carlo is not None
    assert (stack.analysis.monte_carlo.n, stack.analysis.monte_carlo.seed) == (100_000, 42)


def test_missing_file_gives_clear_error(tmp_path: Path) -> None:
    with pytest.raises(StackInputError, match="file not found"):
        load_stack(tmp_path / "nope.yaml")


def test_invalid_yaml_gives_clear_error(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("name: [unclosed\n", encoding="utf-8")
    with pytest.raises(StackInputError, match="not valid YAML"):
        load_stack(bad)


def test_validation_error_from_file_names_the_field(tmp_path: Path) -> None:
    text = (EXAMPLES / "golden_case_a.yaml").read_text(encoding="utf-8")
    bad = tmp_path / "bad.yaml"
    bad.write_text(text.replace("units: mm", "units: inch"), encoding="utf-8")
    with pytest.raises(StackInputError) as info:
        load_stack(bad)
    assert info.value.errors[0].startswith("units:")
