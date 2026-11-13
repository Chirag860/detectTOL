"""GD&T subset (spec Phase 4): callouts and their conversion to contributors.

Supported, and nothing else (docs/ASSUMPTIONS.md A17-A22):

- Flatness / parallelism, zone width ``t``. For a regular feature of size the
  envelope rule (ASME Y14.5-2018 5.8.1, Rule #1) already keeps form inside the
  size limits, so by default (``within_size=True``) the callout adds **no**
  variation to a stack through that size. With ``within_size=False`` (Rule #1
  does not apply: independency, stock, free state, or the surface is not part
  of the size dimension in the stack) it adds a contributor ``0 +/- t/2``.
- Position, diametral zone ``T``, RFS: contributor ``0 +/- T/2`` along the
  stack direction, normal, ``sigma = T/(6 cp)``.
- Position at MMC / LMC: the zone grows by the bonus ``B``, the departure of the
  actual size from the MMC (LMC) size, limited to ``[0, size range]``. Stack
  model: ``delta = (T + B)/(6 cp) * z``, ``z ~ N(0,1)``.
- Perpendicularity / angularity: zone width ``t`` over feature length ``Lf`` ->
  angular contributor ``+/- atan(t/Lf)`` rad for a vector loop.
- Datum reference frames: primary / secondary / tertiary **planar** datums,
  validated but not used to compute sensitivities (the user supplies the stack
  direction through ``sensitivity``).

All lengths are millimetres, angles radians.
"""

from __future__ import annotations

import math
from typing import Annotated, Literal

import numpy as np
import numpy.typing as npt
from pydantic import BaseModel, ConfigDict, Field, model_validator
from scipy import integrate, stats

from detecttol.core.loop import LoopVariable
from detecttol.core.models import Contributor, Distribution, FiniteFloat

_STRICT = ConfigDict(strict=True, extra="forbid", frozen=True)

DatumLabel = Annotated[str, Field(pattern=r"^[A-Z]{1,2}$")]
PositiveFloat = Annotated[float, Field(gt=0.0, allow_inf_nan=False)]
MaterialCondition = Literal["RFS", "MMC", "LMC"]
FeatureType = Literal["hole", "pin"]
FloatArray = npt.NDArray[np.float64]


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

    Attributes:
        within_size: ``True`` (default) when the surface belongs to a regular
            feature of size whose size dimension is in the stack: under the
            envelope rule the flatness is a refinement *inside* the size limits
            and adds no variation, so the contributor has zero tolerance.
            ``False`` when Rule #1 does not apply to it: the contributor is then
            ``0 +/- tolerance/2`` along the stack direction.
    """

    kind: Literal["flatness"] = "flatness"
    distribution: Distribution = "normal"
    within_size: bool = True

    def to_contributor(self) -> Contributor:
        """Contributor with nominal 0 and tolerance ``+/- t/2`` (or 0 if within size) [mm]."""
        zone = 0.0 if self.within_size else self.tolerance
        return _zone_contributor(self.id, zone, self.sensitivity, self.distribution, self.cp)


class Parallelism(_TranslationalCallout):
    """Parallelism to a datum, zone width ``tolerance`` [mm].

    Attributes:
        within_size: required, no default. ``True`` when the toleranced face
            and the datum face are the two faces of the size dimension that is
            in the stack: the parallelism error is then contained in that size
            tolerance and adds nothing. ``False`` when the datum is another
            feature: the contributor is ``0 +/- tolerance/2``.
    """

    kind: Literal["parallelism"] = "parallelism"
    datums: DatumReferenceFrame
    distribution: Distribution = "normal"
    within_size: bool

    def to_contributor(self) -> Contributor:
        """Contributor with nominal 0 and tolerance ``+/- t/2`` (or 0 if within size) [mm]."""
        zone = 0.0 if self.within_size else self.tolerance
        return _zone_contributor(self.id, zone, self.sensitivity, self.distribution, self.cp)


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
    ``T + B`` where the bonus ``B`` is the departure of the actual size from the
    MMC (or LMC) size, limited to ``[0, size range]``.
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

    def _wants_smallest(self) -> bool:
        if self.material_condition == "RFS" or self.feature is None:
            raise ValueError("only defined for MMC / LMC callouts")
        return (self.feature == "hole") == (self.material_condition == "MMC")

    def reference_size(self, size: Contributor) -> float:
        """MMC or LMC size [mm] of the feature, from its size contributor.

        Hole: MMC = smallest size (nominal + lower_tol), LMC = largest.
        Pin:  MMC = largest size (nominal + upper_tol), LMC = smallest.
        """
        smallest = size.nominal + size.lower_tol
        largest = size.nominal + size.upper_tol
        return smallest if self._wants_smallest() else largest

    def bonus(self, size: Contributor, actual: FloatArray | float) -> FloatArray:
        """Bonus tolerance [mm] for actual size(s) ``actual`` [mm].

        The departure from the reference (MMC or LMC) size towards the other
        limit, clamped to ``[0, size range]``: a part beyond its reference size
        is out of tolerance and earns no bonus; one beyond the other limit earns
        no more than the full size range.
        """
        reference = self.reference_size(size)
        values = np.asarray(actual, dtype=np.float64)
        departure = values - reference if self._wants_smallest() else reference - values
        return np.clip(departure, 0.0, 2.0 * size.half_range)

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
        """Standard deviation [mm] of the positional deviation with bonus (stack model).

        ``delta = (T + B)/(6 cp) * z`` with ``z ~ N(0,1)`` independent of the
        size, so ``sigma = sqrt(E[(T + B)^2])/(6 cp)`` and
        ``E[(T + B)^2] = (T + E[B])^2 + Var[B]``.

        The reference size is a size limit and the size distribution is
        symmetric about mid-tolerance, so ``E[B] = t_s`` (half the size range).

        - bounded size distributions (uniform, truncated normal) are not
          affected by the clamp: ``Var[B] = sigma_s^2``;
        - a normal size is clipped at both limits, i.e. at ``+/- k sigma0`` with
          ``k = t_s/sigma0`` (= 3 cp of the size):
          ``Var[B] = sigma0^2 * ((2 Phi(k) - 1) - 2 k phi(k) + 2 k^2 Phi(-k))``.
        """
        t_s, sigma_s = size.half_range, size.sigma
        variance = sigma_s * sigma_s
        if size.distribution == "normal" and sigma_s > 0.0:
            k = t_s / sigma_s
            tail = 0.5 * math.erfc(k / math.sqrt(2.0))  # Phi(-k)
            pdf = math.exp(-0.5 * k * k) / math.sqrt(2.0 * math.pi)
            variance *= (1.0 - 2.0 * tail) - 2.0 * k * pdf + 2.0 * k * k * tail
        second_moment = (self.tolerance + t_s) ** 2 + variance
        return math.sqrt(second_moment) / (6.0 * self.cp)

    def process_sigma(self) -> float:
        """Positional process scatter per axis [mm]: ``T/(6 cp)`` (fixed-process model)."""
        return self.tolerance / (6.0 * self.cp)

    def reject_probability(self, size: Contributor | None = None) -> float:
        """Probability that a part fails the position check at inspection.

        Fixed-process model: the radial positional deviation ``r`` is Rayleigh
        with ``sigma_p = T/(6 cp)`` per axis, independent of the feature size.
        A part is rejected when ``r > (T + B)/2`` (RFS: ``B = 0``), so

            P_reject = E_s[ exp(-((T + B(s))/2)^2 / (2 sigma_p^2)) ]

        RFS gives ``exp(-(3 cp)^2 / 2)`` (1.11 % at cp = 1). With MMC/LMC the
        bonus widens the acceptance zone, so the value is never higher than at
        RFS: this is the benefit of the modifier. The expectation over the size
        distribution is evaluated by numerical quadrature.

        Args:
            size: the size contributor; required with MMC / LMC.
        """
        sigma_p = self.process_sigma()

        def conditional(bonus: float) -> float:
            return math.exp(-(((self.tolerance + bonus) / 2.0) ** 2) / (2.0 * sigma_p * sigma_p))

        if self.material_condition == "RFS":
            return conditional(0.0)
        if size is None:
            raise ValueError(f"position '{self.id}': the size contributor is required")
        mu, t_s = size.mean, size.half_range
        if t_s == 0.0:
            return conditional(float(self.bonus(size, mu)))
        if size.distribution == "uniform":
            dist = stats.uniform(loc=mu - t_s, scale=2.0 * t_s)
            lo, hi = mu - t_s, mu + t_s
        else:
            sigma0 = t_s / (3.0 * size.cp)
            k = 3.0 * size.cp
            if size.distribution == "normal":
                dist = stats.norm(loc=mu, scale=sigma0)
                lo, hi = mu - 10.0 * sigma0, mu + 10.0 * sigma0
            else:
                dist = stats.truncnorm(-k, k, loc=mu, scale=sigma0)
                lo, hi = mu - t_s, mu + t_s

        def integrand(s: float) -> float:
            return conditional(float(self.bonus(size, s))) * float(dist.pdf(s))

        value, _error = integrate.quad(
            integrand, lo, hi, points=[mu - t_s, mu, mu + t_s], epsabs=1e-13, epsrel=1e-11
        )
        return float(value)


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
