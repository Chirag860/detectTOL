"""Drawing standard and tolerance classes in STEP-based input (schema v3) and PMI mapping."""

from __future__ import annotations

import copy
from typing import Any

import pytest
import yaml

pytest.importorskip("OCC", reason="pythonocc-core is not installed")

from detecttol import analyze
from detecttol.cad.mapping import geomtol_to_callout
from detecttol.cad.step_reader import PmiGeomTolerance
from detecttol.cad.step_stack import build_step_stack
from detecttol.gdt import Flatness
from detecttol.io import StackInputError
from tests.conftest import EXAMPLES

STEP_EXAMPLES = EXAMPLES / "step"
EXACT = {"rel": 1e-12, "abs": 1e-15}
SEVEN_SF = {"rel": 1e-6}


def _plate_stack_doc() -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load(
        (STEP_EXAMPLES / "plate_stack.yaml").read_text(encoding="utf-8")
    )
    return data


def _with_general_tolerance(data: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(data)
    out["standard"] = "is"
    out["general_tolerance"] = "m"
    for item in out["annotations"]:
        item.pop("upper_tol")
        item.pop("lower_tol")
        item["tolerance_class"] = "general"
    return out


def test_general_tolerance_on_the_plate_stack_step_assembly() -> None:
    """Golden case A geometry, every dimension at IS 2102-m, sizes measured on the model.

    slot 50 -> +/-0.3, plates 16.6 -> +/-0.2: mean 0.2, W = 0.9,
    sigma = sqrt(0.09 + 3*0.04)/3 = 0.1527525 (same as the YAML-only test).
    """
    built = build_step_stack(_with_general_tolerance(_plate_stack_doc()), STEP_EXAMPLES)
    r = analyze(built.stack)
    assert r.standard == "is"
    assert r.mean == pytest.approx(0.2, abs=1e-9)
    assert r.worst_case is not None and r.rss is not None
    assert r.worst_case.half_range == pytest.approx(0.9, **EXACT)
    assert r.rss.sigma == pytest.approx(0.1527525, **SEVEN_SF)
    table = next(w for w in r.warnings if w.code == "TOLERANCE_FROM_TABLE")
    assert "slot_depth: IS 2102-m / ISO 2768-m (over 30 up to 120 mm): +/-0.3" in table.message


def test_iso286_class_on_a_step_dimension() -> None:
    """The plates as 16.6 js9: IT9 at 16.6 mm (above 10 up to 18) = 43 um -> +/-0.0215."""
    data = _plate_stack_doc()
    for item in data["annotations"]:
        if item["id"].startswith("plate"):
            item.pop("upper_tol")
            item.pop("lower_tol")
            item["tolerance_class"] = "js9"
    r = analyze(build_step_stack(data, STEP_EXAMPLES).stack)
    plates = [c for c in r.contributors if c.id.startswith("plate")]
    assert [(c.upper_tol, c.lower_tol) for c in plates] == [(0.0215, -0.0215)] * 3
    assert "TABLE_NOT_VERIFIED" in [w.code for w in r.warnings]


def test_step_annotation_tolerance_errors() -> None:
    data = _plate_stack_doc()
    data["annotations"][0]["tolerance_class"] = "H7"  # upper/lower still present
    with pytest.raises(StackInputError, match="either tolerance_class or upper_tol"):
        build_step_stack(data, STEP_EXAMPLES)
    data = _plate_stack_doc()
    for key in ("upper_tol", "lower_tol"):
        data["annotations"][0].pop(key)
    data["annotations"][0]["tolerance_class"] = "general"
    with pytest.raises(StackInputError, match="needs general_tolerance"):
        build_step_stack(data, STEP_EXAMPLES)


def test_pmi_flatness_without_within_size_follows_the_standard() -> None:
    """PMI carries no envelope information for a flatness: the drawing standard decides."""
    pmi = PmiGeomTolerance(
        name="Flatness.1", kind="Flatness", value=0.04, material_modifier=None,
        datums=(), targets=(),
    )  # fmt: skip
    callout = geomtol_to_callout(pmi, cid="f")
    assert isinstance(callout, Flatness)
    assert callout.within_size is True  # unchanged attribute default (ASME)
    assert callout.contained_in_size("asme") is True
    assert callout.contained_in_size("is") is False
    assert callout.to_contributor("iso").half_range == pytest.approx(0.02, **EXACT)
