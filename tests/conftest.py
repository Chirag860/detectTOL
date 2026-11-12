"""Shared test helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from detecttol import Stack

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = REPO_ROOT / "examples"
#: Vector-loop examples (schema_version 2); every other example is a linear stack.
LOOP_EXAMPLE_NAMES = ("two_link_bracket.yaml", "wedge_height.yaml")
LINEAR_EXAMPLES = sorted(p for p in EXAMPLES.glob("*.yaml") if p.name not in LOOP_EXAMPLE_NAMES)
LOOP_EXAMPLES = sorted(p for p in EXAMPLES.glob("*.yaml") if p.name in LOOP_EXAMPLE_NAMES)


def contributor(
    cid: str,
    nominal: float,
    upper: float,
    lower: float,
    a: float,
    distribution: str = "normal",
    cp: float = 1.0,
) -> dict[str, Any]:
    return {
        "id": cid,
        "nominal": nominal,
        "upper_tol": upper,
        "lower_tol": lower,
        "sensitivity": a,
        "distribution": distribution,
        "cp": cp,
    }


def make_stack(
    contributors: list[dict[str, Any]],
    *,
    lsl: float | None = None,
    usl: float | None = None,
    constant: float = 0.0,
    methods: list[str] | None = None,
    n: int | None = None,
    seed: int = 42,
    k: float | None = None,
) -> Stack:
    analysis: dict[str, Any] = {"methods": methods or ["worst_case", "rss"]}
    if n is not None:
        analysis["monte_carlo"] = {"n": n, "seed": seed}
        if "monte_carlo" not in analysis["methods"]:
            analysis["methods"] = [*analysis["methods"], "monte_carlo"]
    if k is not None:
        analysis["modified_rss_k"] = k
    return Stack.model_validate(
        {
            "schema_version": 1,
            "units": "mm",
            "name": "test_stack",
            "requirement": {"lsl": lsl, "usl": usl, "constant": constant},
            "contributors": contributors,
            "analysis": analysis,
        }
    )


def case_a_contributors() -> list[dict[str, Any]]:
    return [
        contributor("slot_depth", 50.00, 0.10, -0.10, 1.0),
        contributor("plate_1", 16.60, 0.05, -0.05, -1.0),
        contributor("plate_2", 16.60, 0.05, -0.05, -1.0),
        contributor("plate_3", 16.60, 0.05, -0.05, -1.0),
    ]


@pytest.fixture
def case_a() -> Stack:
    return make_stack(case_a_contributors(), lsl=0.0)
