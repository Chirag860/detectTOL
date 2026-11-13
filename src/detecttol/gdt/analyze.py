"""Analyse a linear stack together with GD&T callouts (spec Phase 4)."""

from __future__ import annotations

from typing import Annotated

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator

from detecttol.core import linear, montecarlo
from detecttol.core.analyze import analyze_linearised
from detecttol.core.models import Contributor, Stack
from detecttol.core.montecarlo import FloatArray
from detecttol.core.results import AnalysisWarning, StackResult
from detecttol.gdt.models import Flatness, Parallelism, PlanarDatum, Position

Callout = Annotated[Flatness | Parallelism | Position, Field(discriminator="kind")]


class GdtStack(BaseModel):
    """A linear stack plus GD&T callouts that add variation to it.

    ``Y = constant + sum(a_i x_i) + sum(a_g d_g)`` where each ``d_g`` is the
    deviation contributed by one callout along the stack direction [mm].

    Attributes:
        stack: the dimensional (size) stack.
        datums: declared planar datum features.
        callouts: flatness, parallelism and position callouts.
    """

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    stack: Stack
    datums: list[PlanarDatum] = []
    callouts: list[Callout] = []

    @model_validator(mode="after")
    def _check(self) -> GdtStack:
        labels = [d.label for d in self.datums]
        if len(set(labels)) != len(labels):
            raise ValueError(f"datums: duplicate label(s) in {labels}")
        contributor_ids = {c.id for c in self.stack.contributors}
        seen: set[str] = set()
        for callout in self.callouts:
            if callout.id in contributor_ids or callout.id in seen:
                raise ValueError(f"callouts: id '{callout.id}' is not unique")
            seen.add(callout.id)
            frame = getattr(callout, "datums", None)
            if frame is not None:
                missing = [x for x in frame.labels() if x not in labels]
                if missing:
                    raise ValueError(
                        f"callouts: '{callout.id}' references undeclared datum(s) {missing}"
                    )
            if (
                isinstance(callout, Position)
                and callout.size_contributor is not None
                and callout.size_contributor not in contributor_ids
            ):
                raise ValueError(
                    f"callouts: '{callout.id}' size_contributor"
                    f" '{callout.size_contributor}' is not a contributor of the stack"
                )
        return self

    def size_of(self, callout: Position) -> Contributor | None:
        """The size contributor a position callout refers to, if any."""
        for c in self.stack.contributors:
            if c.id == callout.size_contributor:
                return c
        return None

    def linear_contributors(self) -> list[Contributor]:
        """Stack contributors followed by one linearised contributor per callout."""
        out = list(self.stack.contributors)
        for callout in self.callouts:
            if isinstance(callout, Position):
                out.append(callout.to_contributor(self.size_of(callout)))
            else:
                out.append(callout.to_contributor())
        return out


def sample_gdt_stack(gdt: GdtStack, n: int, seed: int) -> FloatArray:
    """``n`` Monte Carlo samples of Y [mm] for a stack with callouts.

    Sampling order from one ``default_rng(seed)``: the stack contributors in
    order (identical to the plain 1D engine), then the callouts in order.
    A position callout at MMC/LMC reuses the *same* samples of its size
    contributor: ``delta = (T + |s - m|)/(6 cp) * z``.
    """
    rng = np.random.default_rng(seed)
    y = np.full(n, gdt.stack.requirement.constant, dtype=np.float64)
    samples: dict[str, FloatArray] = {}
    for c in gdt.stack.contributors:
        x = montecarlo.sample_contributor(c, n, rng)
        samples[c.id] = x
        y += c.sensitivity * x
    for callout in gdt.callouts:
        size = gdt.size_of(callout) if isinstance(callout, Position) else None
        if isinstance(callout, Position) and callout.material_condition != "RFS" and size:
            bonus = callout.bonus(size, samples[size.id])
            sigma = (callout.tolerance + bonus) / (6.0 * callout.cp)
            y += callout.sensitivity * sigma * rng.standard_normal(n)
        else:
            contributor = (
                callout.to_contributor(size)
                if isinstance(callout, Position)
                else callout.to_contributor()
            )
            y += contributor.sensitivity * montecarlo.sample_contributor(contributor, n, rng)
    return y


def analyze_gdt(gdt: GdtStack) -> StackResult:
    """Analyse a stack with GD&T callouts.

    Worst case and RSS use one linearised contributor per callout (see the
    callout classes). Monte Carlo samples the callouts exactly, including the
    size-dependent bonus zone of MMC/LMC position callouts. All lengths in mm.

    With an MMC/LMC position callout the output is a scale mixture of normals,
    not a normal: the analytic P_fail and Cpk under-predict the tail (about 25 %
    low in the documented test case). A ``NON_NORMAL_INPUT`` warning is added
    for every such callout that is not already reported.
    """
    contributors = gdt.linear_contributors()
    stack = gdt.stack
    result = analyze_linearised(
        name=stack.name,
        units=stack.units,
        requirement=stack.requirement,
        contributors=contributors,
        analysis=stack.analysis,
        mean=linear.stack_mean(contributors, stack.requirement.constant),
        sampler=lambda n, seed: sample_gdt_stack(gdt, n, seed),
    )
    bonus_ids = [
        c.id
        for c in gdt.callouts
        if isinstance(c, Position) and c.material_condition != "RFS" and c.sensitivity != 0.0
    ]
    if not bonus_ids or result.rss is None:
        return result
    warning = AnalysisWarning(
        code="NON_NORMAL_INPUT",
        message=(
            "P_fail and Cpk assume a normal output, but position callout(s) with an MMC/LMC"
            f" bonus make it a scale mixture of normals: {', '.join(bonus_ids)}. The analytic"
            " P_fail under-predicts the tail; prefer the Monte Carlo result."
        ),
    )
    return result.model_copy(update={"warnings": [*result.warnings, warning]})
