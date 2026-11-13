"""2D vector-loop stacks with nonlinear geometry (spec Section 3.4, Phase 3).

Conventions (docs/ASSUMPTIONS.md A12-A15):

- A loop is an open chain of 2D vectors. Vector j has a length ``L_j`` [mm] and a
  **relative** angle ``phi_j`` [rad]: the counter-clockwise angle from the
  direction of the previous vector to this vector. The first angle is measured
  from the global +x axis. Absolute direction: ``Theta_j = phi_1 + ... + phi_j``.
- The requirement is the projection of the chain's resultant onto a measurement
  direction at absolute angle ``alpha`` [rad], plus a constant::

      Y = constant + sum_j L_j * cos(Theta_j - alpha)          [mm]

- Analytic sensitivities at the means::

      dY/dL_j   =  cos(Theta_j - alpha)                         [mm/mm]
      dY/dphi_k = -sum_{j >= k} L_j * sin(Theta_j - alpha)      [mm/rad]

  (a relative angle rotates its own vector and every vector after it).
- Worst case and RSS use the linearisation ``Y ~ Y(mu) + sum a_i (x_i - mu_i)``.
  Monte Carlo evaluates the exact ``Y``.

This module is Python-API only; angles are radians, lengths millimetres.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from typing import Annotated, Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator

from detecttol.core import montecarlo
from detecttol.core.analyze import analyze_linearised
from detecttol.core.models import (
    AnalysisConfig,
    Contributor,
    Distribution,
    FiniteFloat,
    Requirement,
)
from detecttol.core.montecarlo import FloatArray
from detecttol.core.results import StackResult

_STRICT = ConfigDict(strict=True, extra="forbid", frozen=True)

VariableKind = Literal["length", "angle", "pitch", "roll"]
LoopWarningCode = Literal["ZERO_SENSITIVITY", "LINEARISATION_SUSPECT"]

#: Finite-difference step rule of spec Section 3.4: h = max(FD_MIN_STEP, FD_REL_STEP * t).
FD_MIN_STEP = 1e-6
FD_REL_STEP = 1e-4
#: A variable's linear effect |a_i| t_i below this [mm] counts as "zero" ...
_ZERO_LINEAR_EFFECT_MM = 1e-12
#: ... and is reported when its exact one-at-a-time effect exceeds this [mm].
_NONZERO_EXACT_EFFECT_MM = 1e-9
#: Linear-vs-Monte-Carlo disagreement is flagged above this many standard errors.
_SUSPECT_N_SE = 5.0


class LoopVariable(BaseModel):
    """A toleranced length [mm] or relative angle [rad] in a vector loop.

    The unit follows from where the variable is used (``LoopVector.length`` ->
    mm, ``LoopVector.angle`` -> rad). ``upper_tol``/``lower_tol`` are signed
    deviations from ``nominal`` in that same unit.
    """

    model_config = _STRICT

    id: Annotated[str, Field(min_length=1)]
    nominal: FiniteFloat
    upper_tol: FiniteFloat
    lower_tol: FiniteFloat
    distribution: Distribution = "normal"
    cp: Annotated[float, Field(gt=0.0, allow_inf_nan=False)] = 1.0

    @model_validator(mode="after")
    def _check_tolerance_order(self) -> LoopVariable:
        if self.upper_tol < self.lower_tol:
            raise ValueError(
                f"upper_tol ({self.upper_tol}) must be >= lower_tol ({self.lower_tol})"
                f" for variable '{self.id}'"
            )
        return self

    def as_contributor(self, sensitivity: float) -> Contributor:
        """The same toleranced quantity as a :class:`Contributor` with a_i set."""
        return Contributor(
            id=self.id,
            nominal=self.nominal,
            upper_tol=self.upper_tol,
            lower_tol=self.lower_tol,
            sensitivity=sensitivity,
            distribution=self.distribution,
            cp=self.cp,
        )


class LoopVector(BaseModel):
    """One vector of the chain.

    Attributes:
        length: length [mm]; a fixed number or a toleranced :class:`LoopVariable`.
        angle: relative angle [rad], counter-clockwise from the previous vector's
            direction (from global +x for the first vector); fixed or toleranced.
    """

    model_config = _STRICT

    length: LoopVariable | FiniteFloat
    angle: LoopVariable | FiniteFloat


class VectorLoop(BaseModel):
    """An open 2D vector chain and the requirement measured on it.

    ``Y = requirement.constant + sum_j L_j cos(Theta_j - measure_angle)`` [mm].

    Attributes:
        name: name of the stack.
        vectors: the chain, in order.
        measure_angle: absolute direction [rad] onto which the resultant is
            projected (0 = global +x, pi/2 = global +y).
        requirement: spec limits on Y [mm] and the constant term.
        analysis: methods, Monte Carlo settings, Bender factor.
    """

    model_config = _STRICT

    name: Annotated[str, Field(min_length=1)]
    vectors: Annotated[list[LoopVector], Field(min_length=1)]
    measure_angle: FiniteFloat = 0.0
    requirement: Requirement
    analysis: AnalysisConfig = AnalysisConfig()

    @model_validator(mode="after")
    def _check_variables(self) -> VectorLoop:
        ids = [v.id for v, _, _ in self.variables()]
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        if dupes:
            raise ValueError(f"vectors: duplicate variable id(s) {dupes}")
        if not ids:
            raise ValueError("vectors: at least one length or angle must be a toleranced variable")
        return self

    def variables(self) -> list[tuple[LoopVariable, VariableKind, int]]:
        """Toleranced variables as ``(variable, kind, vector_index)``.

        Order: vector by vector, length before angle. This is the contributor
        order of the result and the Monte Carlo sampling order.
        """
        out: list[tuple[LoopVariable, VariableKind, int]] = []
        for j, vec in enumerate(self.vectors):
            if isinstance(vec.length, LoopVariable):
                out.append((vec.length, "length", j))
            if isinstance(vec.angle, LoopVariable):
                out.append((vec.angle, "angle", j))
        return out


class VariableDetail(BaseModel):
    """Per-variable sensitivity information.

    Attributes:
        id: variable id.
        kind: ``length``, ``angle`` (in-plane / yaw angle), ``pitch`` or ``roll``
            (the last two only in 3D loops).
        unit: ``mm`` or ``rad`` (unit of nominal, tolerances and sigma).
        vector_index: 0-based index of the vector the variable belongs to.
        sensitivity_analytic: dY/dx at the means [mm/mm or mm/rad].
        sensitivity_fd: central finite-difference estimate of the same.
        fd_step: step h used [mm or rad].
        linear_effect: ``|a_i| * t_i`` [mm].
        exact_effect: ``max |Y(mu +/- t_i e_i) - Y(mu)|`` [mm], all other
            variables at their means (one-at-a-time, exact function).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    kind: VariableKind
    unit: Literal["mm", "rad"]
    vector_index: int
    sensitivity_analytic: float
    sensitivity_fd: float
    fd_step: float
    linear_effect: float
    exact_effect: float


class LoopWarning(BaseModel):
    """A linearisation-related condition the engineer must know about."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: LoopWarningCode
    message: str


class LoopResult(BaseModel):
    """Result of a vector-loop analysis.

    Attributes:
        result: the stack result. Worst case, RSS, contributions, P_fail and Cpk
            are **linearised** about the means; ``result.monte_carlo`` uses the
            exact function. ``result.contributors[i].sensitivity`` is the
            analytic a_i; for an angle variable nominal/tolerances/sigma are in
            radians and the sensitivity in mm/rad.
        variables: per-variable detail, same order as ``result.contributors``.
        mc_std_rel_diff: ``(std_MC - sigma_linear)/sigma_linear``; ``None``
            without Monte Carlo or when ``sigma_linear == 0``.
        mc_std_rel_se: approximate relative standard error of the Monte Carlo
            std, ``1/sqrt(2 (N - 1))`` (exact for a normal Y).
        mc_mean_shift: ``mean_MC - Y(mu)`` [mm] (second-order mean shift that the
            linearisation ignores, plus sampling noise).
        mc_mean_se: standard error of the Monte Carlo mean, ``std_MC/sqrt(N)`` [mm].
        loop_warnings: linearisation warnings.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    result: StackResult
    variables: list[VariableDetail]
    mc_std_rel_diff: float | None
    mc_std_rel_se: float | None
    mc_mean_shift: float | None
    mc_mean_se: float | None
    loop_warnings: list[LoopWarning]


def _mean_values(loop: VectorLoop) -> tuple[list[float], list[float]]:
    """Lengths [mm] and relative angles [rad] with every variable at its mean."""
    lengths, angles = [], []
    for vec in loop.vectors:
        lengths.append(_mean_of(vec.length))
        angles.append(_mean_of(vec.angle))
    return lengths, angles


def _mean_of(value: LoopVariable | float) -> float:
    if isinstance(value, LoopVariable):
        return value.nominal + (value.upper_tol + value.lower_tol) / 2.0
    return value


def _half_range_of(var: LoopVariable) -> float:
    return (var.upper_tol - var.lower_tol) / 2.0


def loop_value(
    lengths: Sequence[float], angles: Sequence[float], measure_angle: float, constant: float = 0.0
) -> float:
    """Exact requirement value [mm]: ``constant + sum_j L_j cos(Theta_j - alpha)``.

    Args:
        lengths: vector lengths L_j [mm].
        angles: relative angles phi_j [rad] (first one from global +x, CCW positive).
        measure_angle: alpha, absolute measurement direction [rad].
        constant: constant term [mm].
    """
    theta = 0.0
    terms: list[float] = []
    for length, phi in zip(lengths, angles, strict=True):
        theta += phi
        terms.append(length * math.cos(theta - measure_angle))
    # Same summation as the 1D engine (constant + exact sum of the terms).
    return constant + math.fsum(terms)


def analytic_sensitivities(loop: VectorLoop) -> list[float]:
    """dY/dx_i at the means for every toleranced variable, in ``variables()`` order.

    ``dY/dL_j = cos(Theta_j - alpha)`` [mm/mm];
    ``dY/dphi_k = -sum_{j >= k} L_j sin(Theta_j - alpha)`` [mm/rad].
    """
    lengths, angles = _mean_values(loop)
    alpha = loop.measure_angle
    thetas: list[float] = []
    theta = 0.0
    for phi in angles:
        theta += phi
        thetas.append(theta)
    # tail[k] = sum_{j >= k} L_j sin(Theta_j - alpha)
    tail = [0.0] * (len(lengths) + 1)
    for j in range(len(lengths) - 1, -1, -1):
        tail[j] = tail[j + 1] + lengths[j] * math.sin(thetas[j] - alpha)
    out: list[float] = []
    for _var, kind, j in loop.variables():
        out.append(math.cos(thetas[j] - alpha) if kind == "length" else -tail[j])
    return out


def fd_step(half_range: float) -> float:
    """Finite-difference step of spec Section 3.4: ``h = max(1e-6, 1e-4 * t)``.

    ``h`` is in the variable's own unit (mm or rad).
    """
    return max(FD_MIN_STEP, FD_REL_STEP * half_range)


def _value_with(loop: VectorLoop, index: int, delta: float) -> float:
    """Exact Y with variable ``index`` displaced by ``delta`` from its mean."""
    lengths, angles = _mean_values(loop)
    _var, kind, j = loop.variables()[index]
    if kind == "length":
        lengths[j] += delta
    else:
        angles[j] += delta
    return loop_value(lengths, angles, loop.measure_angle, loop.requirement.constant)


def finite_difference_sensitivities(loop: VectorLoop) -> list[float]:
    """Central finite-difference dY/dx_i at the means, in ``variables()`` order.

    ``(Y(mu + h e_i) - Y(mu - h e_i)) / (2h)`` with ``h = fd_step(t_i)``.
    """
    out = []
    for i, (var, _kind, _j) in enumerate(loop.variables()):
        h = fd_step(_half_range_of(var))
        out.append((_value_with(loop, i, h) - _value_with(loop, i, -h)) / (2.0 * h))
    return out


def sample_loop(loop: VectorLoop, n: int, seed: int) -> FloatArray:
    """``n`` Monte Carlo samples of the exact Y [mm]; shape ``(n,)``.

    Variables are sampled in ``variables()`` order from one
    ``numpy.random.default_rng(seed)``; fixed values consume no random draw.
    Same seed and input give bit-identical output.
    """
    rng = np.random.default_rng(seed)
    alpha = loop.measure_angle
    y = np.full(n, loop.requirement.constant, dtype=np.float64)
    theta = np.zeros(n, dtype=np.float64)
    for vec in loop.vectors:
        length = _sample_value(vec.length, n, rng)
        theta = theta + _sample_value(vec.angle, n, rng)
        y += length * np.cos(theta - alpha)
    return y


def _sample_value(
    value: LoopVariable | float, n: int, rng: np.random.Generator
) -> FloatArray | float:
    if isinstance(value, LoopVariable):
        # The sensitivity is irrelevant for sampling one variable.
        return montecarlo.sample_contributor(value.as_contributor(1.0), n, rng)
    return value


def analyze_loop(loop: VectorLoop) -> LoopResult:
    """Analyse a 2D vector loop.

    Linearised worst case / RSS / P_fail use the analytic sensitivities at the
    means; Monte Carlo uses the exact function. Finite-difference sensitivities
    are computed alongside as a cross-check and returned in ``variables``.

    Lengths are millimetres and angles radians, in and out.
    """
    lengths, angles = _mean_values(loop)
    return assemble_loop_result(
        name=loop.name,
        requirement=loop.requirement,
        analysis=loop.analysis,
        variables=loop.variables(),
        analytic=analytic_sensitivities(loop),
        fd=finite_difference_sensitivities(loop),
        y_mean=loop_value(lengths, angles, loop.measure_angle, loop.requirement.constant),
        value_with=lambda index, delta: _value_with(loop, index, delta),
        sampler=lambda n, seed: sample_loop(loop, n, seed),
    )


def assemble_loop_result(
    *,
    name: str,
    requirement: Requirement,
    analysis: AnalysisConfig,
    variables: Sequence[tuple[LoopVariable, VariableKind, int]],
    analytic: Sequence[float],
    fd: Sequence[float],
    y_mean: float,
    value_with: Callable[[int, float], float],
    sampler: Callable[[int, int], FloatArray],
) -> LoopResult:
    """Build a :class:`LoopResult` from sensitivities and an exact evaluator.

    Shared by the 2D and 3D loop engines.

    Args:
        name: stack name.
        requirement: spec limits [mm]; its constant must already be in ``y_mean``,
            ``value_with`` and the sampler output.
        analysis: methods, Monte Carlo settings, Bender factor.
        variables: ``(variable, kind, vector_index)`` in contributor order.
        analytic: analytic dY/dx_i at the means [mm/mm or mm/rad].
        fd: finite-difference estimates of the same.
        y_mean: exact Y with every variable at its mean [mm].
        value_with: ``value_with(i, delta)`` = exact Y with variable ``i``
            displaced by ``delta`` (own unit) from its mean, others at their means.
        sampler: ``sampler(n, seed)`` = ``n`` Monte Carlo samples of the exact Y [mm].
    """
    contributors = [
        var.as_contributor(a) for (var, _k, _j), a in zip(variables, analytic, strict=True)
    ]
    result = analyze_linearised(
        name=name,
        units="mm",
        requirement=requirement,
        contributors=contributors,
        analysis=analysis,
        mean=y_mean,
        sampler=sampler,
    )

    warnings: list[LoopWarning] = []
    details: list[VariableDetail] = []
    for i, ((var, kind, j), a, a_fd) in enumerate(zip(variables, analytic, fd, strict=True)):
        t = _half_range_of(var)
        linear_effect = abs(a) * t
        exact_effect = max(abs(value_with(i, t) - y_mean), abs(value_with(i, -t) - y_mean))
        details.append(
            VariableDetail(
                id=var.id,
                kind=kind,
                unit="mm" if kind == "length" else "rad",
                vector_index=j,
                sensitivity_analytic=a,
                sensitivity_fd=a_fd,
                fd_step=fd_step(t),
                linear_effect=linear_effect,
                exact_effect=exact_effect,
            )
        )
        if linear_effect <= _ZERO_LINEAR_EFFECT_MM and exact_effect > _NONZERO_EXACT_EFFECT_MM:
            warnings.append(
                LoopWarning(
                    code="ZERO_SENSITIVITY",
                    message=(
                        f"Variable '{var.id}' has zero first-order sensitivity at the mean, but"
                        f" moving it across its tolerance changes Y by {exact_effect:.6g} mm."
                        " Worst case and RSS ignore this effect; use the Monte Carlo result."
                    ),
                )
            )

    std_rel_diff: float | None = None
    std_rel_se: float | None = None
    mean_shift: float | None = None
    mean_se: float | None = None
    mc = result.monte_carlo
    if mc is not None:
        sigma_lin = math.sqrt(math.fsum((c.sensitivity * c.sigma) ** 2 for c in contributors))
        std_rel_se = 1.0 / math.sqrt(2.0 * (mc.n - 1))
        mean_shift = mc.mean - y_mean
        mean_se = mc.std / math.sqrt(mc.n)
        if sigma_lin > 0.0:
            std_rel_diff = (mc.std - sigma_lin) / sigma_lin
        std_off = std_rel_diff is not None and abs(std_rel_diff) > _SUSPECT_N_SE * std_rel_se
        mean_off = mean_se > 0.0 and abs(mean_shift) > _SUSPECT_N_SE * mean_se
        if std_off or mean_off:
            warnings.append(
                LoopWarning(
                    code="LINEARISATION_SUSPECT",
                    message=(
                        "The linearised result and the exact Monte Carlo result differ by more"
                        f" than {_SUSPECT_N_SE:g} standard errors (std: linear {sigma_lin:.6g} mm"
                        f" vs Monte Carlo {mc.std:.6g} mm; mean: Y(mu) {y_mean:.6g} mm vs Monte"
                        f" Carlo {mc.mean:.6g} mm). The tolerances are too large for the linear"
                        " model; use the Monte Carlo result."
                    ),
                )
            )

    return LoopResult(
        result=result,
        variables=details,
        mc_std_rel_diff=std_rel_diff,
        mc_std_rel_se=std_rel_se,
        mc_mean_shift=mean_shift,
        mc_mean_se=mean_se,
        loop_warnings=warnings,
    )
