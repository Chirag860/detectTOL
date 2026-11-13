"""GD&T subset (spec Phase 4): callouts and their conversion to contributors.

Supported, and nothing else (docs/ASSUMPTIONS.md A17-A22):

- Flatness / parallelism: zone width ``t`` -> translational contributor
  ``0 +/- t/2`` along the stack direction.
- Position, diametral zone ``T``, RFS: contributor ``0 +/- T/2`` along the
  stack direction, normal, ``sigma = T/(6 cp)``.
- Position at MMC / LMC: the zone grows by the bonus ``B = |actual size -
  MMC (or LMC) size|``; deviation ``delta = (T + B)/(6 cp) * z``, ``z ~ N(0,1)``.
- Perpendicularity / angularity: zone width ``t`` over feature length ``Lf`` ->
  angular contributor ``+/- atan(t/Lf)`` rad for a vector loop.
- Datum reference frames: primary / secondary / tertiary **planar** datums,
  validated but not used to compute sensitivities (the user supplies the stack
  direction through ``sensitivity``).

Every conversion is a modelling convention that needs review against
ASME Y14.5-2018 by a qualified person (see docs/reports/phase-4.md).
All lengths are millimetres, angles radians.
"""

from __future__ import annotations

import math
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from detecttol.core.loop import LoopVariable
from detecttol.core.models import Contributor, Distribution, FiniteFloat

_STRICT = ConfigDict(strict=True, extra="forbid", frozen=True)

DatumLabel = Annotated[str, Field(pattern=r"^[A-Z]{1,2}$")]
PositiveFloat = Annotated[float, Field(gt=0.0, allow_inf_nan=False)]
MaterialCondition = Literal["RFS", "MMC", "LMC"]
FeatureType = Literal["hole", "pin"]


class PlanarDatum(BaseModel):
    """A planar datum feature (the only kind supported).

    Attributes:
        label: datum letter(s), ``A`` .. ``ZZ``.
        description: free text, e.g. the face it sits on.
    """

    model_config = _STRICT

    label: DatumLabel
    description: str = ""


class DatumReferenceFrame(BaseModel):
    """Primary / secondary / tertiary planar datum references, in precedence order.

    No material-condition modifiers on datums, no datum targets, no
    non-planar datum features.
    """

    model_config = _STRICT

    primary: DatumLabel
    secondary: DatumLabel | None = None
    tertiary: DatumLabel | None = None

    @model_validator(mode="after")
    def _check(self) -> DatumReferenceFrame:
        if self.tertiary is not None and self.secondary is None:
            raise ValueError("tertiary datum given without a secondary datum")
        labels = self.labels()
        if len(set(labels)) != len(labels):
            raise ValueError(f"datum labels must be distinct, got {list(labels)}")
        return self

    def labels(self) -> tuple[str, ...]:
        """Referenced labels in precedence order."""
        return tuple(x for x in (self.primary, self.secondary, self.tertiary) if x is not None)


class _TranslationalCallout(BaseModel):
    """Common fields of callouts that become one translational contributor."""

    model_config = _STRICT

    id: Annotated[str, Field(min_length=1)]
    tolerance: PositiveFloat
    sensitivity: FiniteFloat = 1.0
    cp: PositiveFloat = 1.0


class Flatness(_TranslationalCallout):
    """Flatness, zone width ``tolerance`` [mm] (a form tolerance: no datums).

    Conversion: contributor ``0 +/- tolerance/2`` along the stack direction.
    """

    kind: Literal["flatness"] = "flatness"
    distribution: Distribution = "normal"

    def to_contributor(self) -> Contributor:
        """Contributor with nominal 0, tolerance ``+/- t/2`` [mm]."""
        return _zone_contributor(
            self.id, self.tolerance, self.sensitivity, self.distribution, self.cp
        )


class Parallelism(_TranslationalCallout):
    """Parallelism to a datum, zone width ``tolerance`` [mm].

    Conversion: contributor ``0 +/- tolerance/2`` along the stack direction.
    """

    kind: Literal["parallelism"] = "parallelism"
    datums: DatumReferenceFrame
    distribution: Distribution = "normal"

    def to_contributor(self) -> Contributor:
        """Contributor with nominal 0, tolerance ``+/- t/2`` [mm]."""
        return _zone_contributor(
            self.id, self.tolerance, self.sensitivity, self.distribution, self.cp
        )


class Position(_TranslationalCallout):
    """Position, diametral zone ``tolerance`` = T [mm].

    Attributes:
        datums: datum reference frame.
        material_condition: ``RFS`` (default), ``MMC`` or ``LMC``.
        feature: ``hole`` (internal) or ``pin`` (external); required with MMC/LMC.
        size_contributor: id of the stack contributor that is the feature's size
            (diameter); required with MMC/LMC. Give it ``sensitivity: 0`` if the
            size itself does not enter the stack.

    Along one stack direction the positional deviation is modelled as normal
    with ``+/- T/2`` at 3 sigma (``sigma = T/(6 cp)``). With MMC/LMC the zone is
    ``T + B`` where ``B = |actual size - MMC size|`` (or LMC size).
    """

    kind: Literal["position"] = "position"
    datums: DatumReferenceFrame
    material_condition: MaterialCondition = "RFS"
    feature: FeatureType | None = None
    size_contributor: str | None = None

    @model_validator(mode="after")
    def _check(self) -> Position:
        if self.material_condition != "RFS" and (
            self.feature is None or self.size_contributor is None
        ):
            raise ValueError(
                f"position '{self.id}': feature and size_contributor are required with"
                f" material_condition {self.material_condition}"
            )
        return self

    def reference_size(self, size: Contributor) -> float:
        """MMC or LMC size [mm] of the feature, from its size contributor.

        Hole: MMC = smallest size (nominal + lower_tol), LMC = largest.
        Pin:  MMC = largest size (nominal + upper_tol), LMC = smallest.
        """
        if self.material_condition == "RFS" or self.feature is None:
            raise ValueError("reference_size is only defined for MMC / LMC callouts")
        smallest = size.nominal + size.lower_tol
        largest = size.nominal + size.upper_tol
        wants_smallest = (self.feature == "hole") == (self.material_condition == "MMC")
        return smallest if wants_smallest else largest

    def to_contributor(self, size: Contributor | None = None) -> Contributor:
        """Linearised contributor for worst case and RSS.

        RFS: ``0 +/- T/2``, normal, cp as given.

        MMC/LMC (needs ``size``): worst-case half-range ``(T + size range)/2``
        (largest possible zone) and ``sigma = sqrt(E[(T + B)^2])/(6 cp)``; the
        returned contributor carries an *equivalent* cp so that its sigma equals
        that value. Monte Carlo does not use this contributor: it samples the
        size and the deviation jointly (see :func:`analyze_gdt`).
        """
        if self.material_condition == "RFS":
            return _zone_contributor(self.id, self.tolerance, self.sensitivity, "normal", self.cp)
        if size is None:
            raise ValueError(f"position '{self.id}': the size contributor is required")
        half = (self.tolerance + 2.0 * size.half_range) / 2.0
        sigma = self.bonus_sigma(size)
        return Contributor(
            id=self.id,
            nominal=0.0,
            upper_tol=half,
            lower_tol=-half,
            sensitivity=self.sensitivity,
            distribution="normal",
            cp=half / (3.0 * sigma),
        )

    def bonus_sigma(self, size: Contributor) -> float:
        """Standard deviation [mm] of the positional deviation with bonus.

        ``delta = (T + B)/(6 cp) * z`` with ``z ~ N(0,1)`` independent of the
        size, so ``sigma = sqrt(E[(T + B)^2])/(6 cp)`` and
        ``E[(T + B)^2] = T^2 + 2 T E[B] + E[B^2]``.

        ``B = |s - m|`` where ``m`` is a size limit, so ``s - m`` has mean
        ``+/- t_s`` and the size's own sigma:

        - bounded size distributions (uniform, truncated normal) never cross
          ``m``: ``E[B] = t_s``, ``E[B^2] = t_s^2 + sigma_s^2``;
        - a normal size is unbounded; with ``r = t_s/sigma0`` (= 3 cp of the size)
          the folded-normal mean is
          ``E[B] = sigma0 sqrt(2/pi) exp(-r^2/2) + t_s (1 - 2 Phi(-r))``
          and ``E[B^2] = t_s^2 + sigma0^2``.
        """
        t_s, sigma_s = size.half_range, size.sigma
        mean_sq = t_s * t_s + sigma_s * sigma_s
        if size.distribution == "normal" and sigma_s > 0.0:
            r = t_s / sigma_s
            tail = 0.5 * math.erfc(r / math.sqrt(2.0))  # Phi(-r)
            mean_b = sigma_s * math.sqrt(2.0 / math.pi) * math.exp(-0.5 * r * r) + t_s * (
                1.0 - 2.0 * tail
            )
        else:
            mean_b = t_s
        second_moment = self.tolerance**2 + 2.0 * self.tolerance * mean_b + mean_sq
        return math.sqrt(second_moment) / (6.0 * self.cp)


class Orientation(BaseModel):
    """Perpendicularity or angularity, zone width ``tolerance`` over ``feature_length``.

    Conversion: an angular tolerance ``+/- atan(tolerance / feature_length)``
    [rad] on the direction of the toleranced feature, for use as the angle of a
    vector in a loop. The translational effect at a point of interest then
    follows from the loop geometry (lever arm x angle).
    """

    model_config = _STRICT

    kind: Literal["perpendicularity", "angularity"]
    id: Annotated[str, Field(min_length=1)]
    tolerance: PositiveFloat
    feature_length: PositiveFloat
    datums: DatumReferenceFrame
    distribution: Distribution = "normal"
    cp: PositiveFloat = 1.0

    def angle_half_range(self) -> float:
        """Angular half-range [rad]: ``atan(tolerance / feature_length)``."""
        return math.atan(self.tolerance / self.feature_length)

    def to_loop_variable(self, nominal_angle: float) -> LoopVariable:
        """Loop angle variable ``nominal_angle +/- atan(t/Lf)`` [rad].

        Args:
            nominal_angle: nominal relative angle of the vector [rad], e.g.
                ``pi/2`` for a perpendicular feature.
        """
        half = self.angle_half_range()
        return LoopVariable(
            id=self.id,
            nominal=nominal_angle,
            upper_tol=half,
            lower_tol=-half,
            distribution=self.distribution,
            cp=self.cp,
        )


def _zone_contributor(
    cid: str, zone: float, sensitivity: float, distribution: Distribution, cp: float
) -> Contributor:
    return Contributor(
        id=cid,
        nominal=0.0,
        upper_tol=zone / 2.0,
        lower_tol=-zone / 2.0,
        sensitivity=sensitivity,
        distribution=distribution,
        cp=cp,
    )
