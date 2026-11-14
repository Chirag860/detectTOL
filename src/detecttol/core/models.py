"""Input data models for a tolerance stack (spec Section 3.1 and Section 4).

All lengths are millimetres. Validation is strict: unknown fields, wrong types,
missing units and inconsistent tolerances are rejected with a message that names
the offending field.
"""

from __future__ import annotations

import math
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Distribution = Literal["normal", "uniform", "truncated_normal"]
Method = Literal["worst_case", "rss", "monte_carlo"]
#: Drawing standard a stack's tolerances follow (see :mod:`detecttol.standards`):
#: ``asme`` (ASME Y14.5, envelope principle), ``iso`` (ISO 8015, independency)
#: or ``is`` (Indian Standards, IS 12160 = ISO 8015: same rules as ``iso``).
DrawingStandard = Literal["asme", "iso", "is"]

FiniteFloat = Annotated[float, Field(allow_inf_nan=False)]

_STRICT = ConfigDict(strict=True, extra="forbid", frozen=True)


class Contributor(BaseModel):
    """One dimension in the stack.

    Attributes:
        id: unique name of the contributor.
        nominal: nominal dimension [mm].
        upper_tol: signed upper deviation from nominal [mm], e.g. ``+0.2``.
        lower_tol: signed lower deviation from nominal [mm], e.g. ``-0.0``.
            Must satisfy ``upper_tol >= lower_tol``.
        sensitivity: a_i = dY/dx_i [mm/mm]; +1 or -1 in a 1D stack.
        distribution: ``normal`` (default), ``uniform`` or ``truncated_normal``.
        cp: process capability Cp (> 0, default 1.0). Used by ``normal`` and
            ``truncated_normal`` only; ignored for ``uniform``.
        tolerance_source: where the tolerance came from when it was looked up
            in a standard's table (e.g. an ISO 286 class or an IS 2102 general
            tolerance); ``None`` when it was given directly. Set by the input
            loaders, reported as a ``TOLERANCE_FROM_TABLE`` warning.
        tolerance_verified: False when that table has not been checked against
            a printed copy of the standard (``TABLE_NOT_VERIFIED`` warning).
        cad_source: where the tolerance was read in a CAD model (e.g. a
            SolidWorks DimXpert annotation or STEP PMI); ``None`` otherwise.
            Reported as a ``TOLERANCE_FROM_CAD`` warning.
    """

    model_config = _STRICT

    id: Annotated[str, Field(min_length=1)]
    nominal: FiniteFloat
    upper_tol: FiniteFloat
    lower_tol: FiniteFloat
    sensitivity: FiniteFloat
    distribution: Distribution = "normal"
    cp: Annotated[float, Field(gt=0.0, allow_inf_nan=False)] = 1.0
    tolerance_source: str | None = None
    tolerance_verified: bool = True
    cad_source: str | None = None

    @model_validator(mode="after")
    def _check_tolerance_order(self) -> Contributor:
        if self.upper_tol < self.lower_tol:
            raise ValueError(
                f"upper_tol ({self.upper_tol}) must be >= lower_tol ({self.lower_tol})"
                f" for contributor '{self.id}'"
            )
        return self

    @property
    def mean(self) -> float:
        """Midpoint-re-centred mean [mm]: ``nominal + (upper_tol + lower_tol)/2``."""
        return self.nominal + (self.upper_tol + self.lower_tol) / 2.0

    @property
    def half_range(self) -> float:
        """Tolerance half-range t [mm]: ``(upper_tol - lower_tol)/2`` (>= 0)."""
        return (self.upper_tol - self.lower_tol) / 2.0

    @property
    def sigma(self) -> float:
        """Standard deviation [mm] under the documented sigma convention.

        - normal:            ``sigma = t / (3 cp)``
        - uniform:           ``sigma = t / sqrt(3)``
        - truncated_normal:  ``sigma = sigma0 * sqrt(1 - 2 k phi(k) / (2 Phi(k) - 1))``
          with ``sigma0 = t / (3 cp)`` and ``k = 3 cp`` (truncation at mean +/- t).
        """
        t = self.half_range
        if self.distribution == "uniform":
            return t / math.sqrt(3.0)
        sigma0 = t / (3.0 * self.cp)
        if self.distribution == "normal":
            return sigma0
        return sigma0 * truncated_normal_sd_factor(3.0 * self.cp)


def truncated_normal_sd_factor(k: float) -> float:
    """Ratio sd(truncated) / sd(underlying) for a normal truncated at +/- k sigma.

    Formula: ``sqrt(1 - 2 k phi(k) / (2 Phi(k) - 1))`` where ``phi`` and ``Phi`` are
    the standard normal pdf and cdf. Dimensionless. Requires ``k > 0``.
    """
    pdf = math.exp(-0.5 * k * k) / math.sqrt(2.0 * math.pi)
    mass = math.erf(k / math.sqrt(2.0))  # = 2 Phi(k) - 1
    return math.sqrt(1.0 - 2.0 * k * pdf / mass)


class Requirement(BaseModel):
    """Functional requirement on the stack output Y.

    Attributes:
        description: free text.
        lsl: lower specification limit [mm] or ``None``.
        usl: upper specification limit [mm] or ``None``.
            At least one of ``lsl``/``usl`` is required.
        constant: constant term added to Y [mm] (default 0).
    """

    model_config = _STRICT

    description: str = ""
    lsl: FiniteFloat | None = None
    usl: FiniteFloat | None = None
    constant: FiniteFloat = 0.0

    @model_validator(mode="after")
    def _check_limits(self) -> Requirement:
        if self.lsl is None and self.usl is None:
            raise ValueError("at least one of lsl / usl must be given")
        if self.lsl is not None and self.usl is not None and self.usl < self.lsl:
            raise ValueError(f"usl ({self.usl}) must be >= lsl ({self.lsl})")
        return self


class MonteCarloConfig(BaseModel):
    """Monte Carlo settings.

    Attributes:
        n: number of samples (>= 2, default 100 000).
        seed: seed for ``numpy.random.default_rng`` (required, >= 0).
    """

    model_config = _STRICT

    n: Annotated[int, Field(ge=2)] = 100_000
    seed: Annotated[int, Field(ge=0)]


class AnalysisConfig(BaseModel):
    """Which analyses to run.

    Attributes:
        methods: any of ``worst_case``, ``rss``, ``monte_carlo`` (no duplicates).
        monte_carlo: required when ``monte_carlo`` is in ``methods``.
        modified_rss_k: Bender correction factor k (>= 1). ``None`` = off (default).
    """

    model_config = _STRICT

    methods: Annotated[list[Method], Field(min_length=1)] = ["worst_case", "rss"]
    monte_carlo: MonteCarloConfig | None = None
    modified_rss_k: Annotated[float, Field(ge=1.0, allow_inf_nan=False)] | None = None

    @model_validator(mode="after")
    def _check_methods(self) -> AnalysisConfig:
        if len(set(self.methods)) != len(self.methods):
            raise ValueError("methods must not contain duplicates")
        if "monte_carlo" in self.methods and self.monte_carlo is None:
            raise ValueError(
                "monte_carlo settings (with an explicit seed) are required when"
                " 'monte_carlo' is listed in methods"
            )
        return self


class Stack(BaseModel):
    """A complete linear tolerance stack: Y = constant + sum(a_i * x_i).

    ``standard`` names the drawing standard (``None`` = not stated). It does not
    change plus/minus stack math; it is echoed in the result and decides how
    GD&T callouts are converted (:mod:`detecttol.gdt`).
    """

    model_config = _STRICT

    schema_version: Literal[1]
    units: Literal["mm"]
    name: Annotated[str, Field(min_length=1)]
    standard: DrawingStandard | None = None
    requirement: Requirement
    contributors: Annotated[list[Contributor], Field(min_length=1)]
    analysis: AnalysisConfig = AnalysisConfig()

    @model_validator(mode="after")
    def _check_unique_ids(self) -> Stack:
        seen: set[str] = set()
        dupes: list[str] = []
        for c in self.contributors:
            if c.id in seen and c.id not in dupes:
                dupes.append(c.id)
            seen.add(c.id)
        if dupes:
            raise ValueError(f"contributors: duplicate id(s) {dupes}")
        return self
