"""3D vector loops (extension of Phase 3).

Conventions (docs/ASSUMPTIONS.md A16):

- Each vector j has a length ``L_j`` [mm] and three **relative** angles [rad]:
  yaw ``psi_j``, pitch ``beta_j`` and roll ``rho_j``. Every vector carries a
  frame; the frame of vector j is obtained from the previous one by rotating
  about the previous frame's own axes, in this order::

      R_0 = I
      M_j = Rz(psi_j) @ Ry(beta_j) @ Rx(rho_j)
      R_j = R_{j-1} @ M_j

  Vector j points along the local x axis: ``d_j = R_j @ e_x``.
- Rotation matrices are the usual right-handed, active ones::

      Rz(a) = [[c, -s, 0], [s, c, 0], [0, 0, 1]]
      Ry(a) = [[c, 0, s], [0, 1, 0], [-s, 0, c]]
      Rx(a) = [[1, 0, 0], [0, c, -s], [0, s, c]]

  For a single vector (``R_0 = I``): ``d = (cos psi cos beta, sin psi cos beta,
  -sin beta)``. Positive yaw turns the vector from +x towards +y; **positive
  pitch tilts it towards -z** (right-hand rule about +y). Roll turns the frame
  about the vector's own axis: it does not move that vector, only later ones.
- Requirement: ``Y = constant + n . sum_j L_j d_j`` for a unit measurement
  direction ``n`` [mm].
- Analytic sensitivities: ``dY/dL_j = n . d_j``; for an angle of vector k,
  ``dY/dangle = n . sum_{j >= k} L_j (R_{k-1} @ dM_k @ M_{k+1} ... M_j) e_x``
  where ``dM_k`` is ``M_k`` with the corresponding factor replaced by its
  derivative. Worst case and RSS are linearised; Monte Carlo is exact.

With pitch = roll = 0 and ``n`` in the xy-plane this reduces to the 2D loop of
:mod:`detecttol.core.loop` (yaw = the 2D relative angle).
"""

from __future__ import annotations

import math
from typing import Annotated

import numpy as np
import numpy.typing as npt
from pydantic import BaseModel, ConfigDict, Field, model_validator

from detecttol.core import montecarlo
from detecttol.core.loop import (
    LoopResult,
    LoopVariable,
    VariableKind,
    assemble_loop_result,
    fd_step,
)
from detecttol.core.models import AnalysisConfig, FiniteFloat, Requirement
from detecttol.core.montecarlo import FloatArray

_STRICT = ConfigDict(strict=True, extra="forbid", frozen=True)

Matrix = npt.NDArray[np.float64]

_E_X = np.array([1.0, 0.0, 0.0])
#: A measurement direction shorter than this is rejected (cannot be normalised).
_MIN_DIRECTION_NORM = 1e-12


def rot_z(a: float) -> Matrix:
    """Right-handed rotation about z by ``a`` [rad]."""
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])


def rot_y(a: float) -> Matrix:
    """Right-handed rotation about y by ``a`` [rad]."""
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, 0.0, s], [0.0, 1.0, 0.0], [-s, 0.0, c]])


def rot_x(a: float) -> Matrix:
    """Right-handed rotation about x by ``a`` [rad]."""
    c, s = math.cos(a), math.sin(a)
    return np.array([[1.0, 0.0, 0.0], [0.0, c, -s], [0.0, s, c]])


def _d_rot_z(a: float) -> Matrix:
    c, s = math.cos(a), math.sin(a)
    return np.array([[-s, -c, 0.0], [c, -s, 0.0], [0.0, 0.0, 0.0]])


def _d_rot_y(a: float) -> Matrix:
    c, s = math.cos(a), math.sin(a)
    return np.array([[-s, 0.0, c], [0.0, 0.0, 0.0], [-c, 0.0, -s]])


def _d_rot_x(a: float) -> Matrix:
    c, s = math.cos(a), math.sin(a)
    return np.array([[0.0, 0.0, 0.0], [0.0, -s, -c], [0.0, c, -s]])


class LoopVector3D(BaseModel):
    """One vector of a 3D chain.

    Attributes:
        length: length [mm]; fixed number or toleranced variable.
        yaw: relative rotation about the previous frame's z axis [rad].
        pitch: then about the new y axis [rad]; positive tilts towards -z.
        roll: then about the vector's own axis [rad].
    """

    model_config = _STRICT

    length: LoopVariable | FiniteFloat
    yaw: LoopVariable | FiniteFloat = 0.0
    pitch: LoopVariable | FiniteFloat = 0.0
    roll: LoopVariable | FiniteFloat = 0.0


class VectorLoop3D(BaseModel):
    """An open 3D vector chain and the requirement measured on it.

    ``Y = requirement.constant + n . sum_j L_j R_j e_x`` [mm], with ``n`` the
    normalised ``measure_direction``.

    Attributes:
        name: name of the stack.
        vectors: the chain, in order.
        measure_direction: ``(x, y, z)`` of the measurement direction in the
            global frame; any non-zero length, normalised internally.
        requirement: spec limits on Y [mm] and the constant term.
        analysis: methods, Monte Carlo settings, Bender factor.
    """

    model_config = _STRICT

    name: Annotated[str, Field(min_length=1)]
    vectors: Annotated[list[LoopVector3D], Field(min_length=1)]
    measure_direction: tuple[FiniteFloat, FiniteFloat, FiniteFloat]
    requirement: Requirement
    analysis: AnalysisConfig = AnalysisConfig()

    @model_validator(mode="after")
    def _check(self) -> VectorLoop3D:
        if math.sqrt(math.fsum(c * c for c in self.measure_direction)) < _MIN_DIRECTION_NORM:
            raise ValueError("measure_direction: must not be the zero vector")
        ids = [v.id for v, _, _ in self.variables()]
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        if dupes:
            raise ValueError(f"vectors: duplicate variable id(s) {dupes}")
        if not ids:
            raise ValueError("vectors: at least one length or angle must be a toleranced variable")
        return self

    def unit_direction(self) -> Matrix:
        """The normalised measurement direction ``n`` (shape ``(3,)``)."""
        n = np.array(self.measure_direction, dtype=np.float64)
        return n / float(np.linalg.norm(n))

    def variables(self) -> list[tuple[LoopVariable, VariableKind, int]]:
        """Toleranced variables as ``(variable, kind, vector_index)``.

        Order: vector by vector; within a vector length, yaw (kind ``angle``),
        pitch, roll. This is the contributor order and the sampling order.
        """
        out: list[tuple[LoopVariable, VariableKind, int]] = []
        for j, vec in enumerate(self.vectors):
            fields: tuple[tuple[LoopVariable | float, VariableKind], ...] = (
                (vec.length, "length"),
                (vec.yaw, "angle"),
                (vec.pitch, "pitch"),
                (vec.roll, "roll"),
            )
            for value, kind in fields:
                if isinstance(value, LoopVariable):
                    out.append((value, kind, j))
        return out


def _mean_of(value: LoopVariable | float) -> float:
    if isinstance(value, LoopVariable):
        return value.nominal + (value.upper_tol + value.lower_tol) / 2.0
    return value


def _mean_table(loop: VectorLoop3D) -> list[list[float]]:
    """Per vector ``[L, yaw, pitch, roll]`` with every variable at its mean."""
    return [
        [_mean_of(v.length), _mean_of(v.yaw), _mean_of(v.pitch), _mean_of(v.roll)]
        for v in loop.vectors
    ]


_COLUMN: dict[VariableKind, int] = {"length": 0, "angle": 1, "pitch": 2, "roll": 3}


def loop3d_value(table: list[list[float]], n: Matrix, constant: float = 0.0) -> float:
    """Exact requirement value [mm] for per-vector rows ``[L, yaw, pitch, roll]``.

    ``constant + n . sum_j L_j R_j e_x`` with ``R_j = R_{j-1} Rz(yaw) Ry(pitch) Rx(roll)``.
    Angles in radians, ``n`` a unit vector.
    """
    r = np.eye(3)
    terms: list[float] = []
    for length, yaw, pitch, roll in table:
        r = r @ rot_z(yaw) @ rot_y(pitch) @ rot_x(roll)
        terms.append(length * float(n @ r[:, 0]))
    return constant + math.fsum(terms)


def analytic_sensitivities_3d(loop: VectorLoop3D) -> list[float]:
    """dY/dx_i at the means, in ``variables()`` order [mm/mm or mm/rad]."""
    table = _mean_table(loop)
    n = loop.unit_direction()
    count = len(table)
    local = [rot_z(row[1]) @ rot_y(row[2]) @ rot_x(row[3]) for row in table]
    frames: list[Matrix] = []  # frames[j] = R_j
    r = np.eye(3)
    for m in local:
        r = r @ m
        frames.append(r)

    out: list[float] = []
    for _var, kind, k in loop.variables():
        if kind == "length":
            out.append(float(n @ frames[k][:, 0]))
            continue
        _length, yaw, pitch, roll = table[k]
        if kind == "angle":
            d_local = _d_rot_z(yaw) @ rot_y(pitch) @ rot_x(roll)
        elif kind == "pitch":
            d_local = rot_z(yaw) @ _d_rot_y(pitch) @ rot_x(roll)
        else:
            d_local = rot_z(yaw) @ rot_y(pitch) @ _d_rot_x(roll)
        before = np.eye(3) if k == 0 else frames[k - 1]
        d_frame = before @ d_local  # dR_k / d(angle)
        terms = []
        for j in range(k, count):
            if j > k:
                d_frame = d_frame @ local[j]  # dR_j / d(angle)
            terms.append(table[j][0] * float(n @ d_frame[:, 0]))
        out.append(math.fsum(terms))
    return out


def _value_with(loop: VectorLoop3D, index: int, delta: float) -> float:
    table = _mean_table(loop)
    _var, kind, j = loop.variables()[index]
    table[j][_COLUMN[kind]] += delta
    return loop3d_value(table, loop.unit_direction(), loop.requirement.constant)


def finite_difference_sensitivities_3d(loop: VectorLoop3D) -> list[float]:
    """Central finite-difference dY/dx_i at the means (step ``h = max(1e-6, 1e-4 t)``)."""
    out = []
    for i, (var, _kind, _j) in enumerate(loop.variables()):
        h = fd_step((var.upper_tol - var.lower_tol) / 2.0)
        out.append((_value_with(loop, i, h) - _value_with(loop, i, -h)) / (2.0 * h))
    return out


def _sample(value: LoopVariable | float, n: int, rng: np.random.Generator) -> FloatArray:
    if isinstance(value, LoopVariable):
        return montecarlo.sample_contributor(value.as_contributor(1.0), n, rng)
    return np.full(n, value, dtype=np.float64)


def _batch_rotation(
    yaw: FloatArray, pitch: FloatArray, roll: FloatArray
) -> npt.NDArray[np.float64]:
    """Stack of ``Rz(yaw) @ Ry(pitch) @ Rx(roll)`` matrices, shape ``(n, 3, 3)``."""
    cz, sz = np.cos(yaw), np.sin(yaw)
    cy, sy = np.cos(pitch), np.sin(pitch)
    cx, sx = np.cos(roll), np.sin(roll)
    m = np.empty((yaw.size, 3, 3), dtype=np.float64)
    m[:, 0, 0] = cz * cy
    m[:, 0, 1] = cz * sy * sx - sz * cx
    m[:, 0, 2] = cz * sy * cx + sz * sx
    m[:, 1, 0] = sz * cy
    m[:, 1, 1] = sz * sy * sx + cz * cx
    m[:, 1, 2] = sz * sy * cx - cz * sx
    m[:, 2, 0] = -sy
    m[:, 2, 1] = cy * sx
    m[:, 2, 2] = cy * cx
    return m


def sample_loop3d(loop: VectorLoop3D, n: int, seed: int) -> FloatArray:
    """``n`` Monte Carlo samples of the exact Y [mm]; shape ``(n,)``.

    Variables are sampled in ``variables()`` order (length, yaw, pitch, roll per
    vector) from one ``default_rng(seed)``; fixed values consume no random draw.
    """
    rng = np.random.default_rng(seed)
    direction = loop.unit_direction()
    y = np.full(n, loop.requirement.constant, dtype=np.float64)
    frames = np.broadcast_to(np.eye(3), (n, 3, 3)).copy()
    for vec in loop.vectors:
        length = _sample(vec.length, n, rng)
        yaw = _sample(vec.yaw, n, rng)
        pitch = _sample(vec.pitch, n, rng)
        roll = _sample(vec.roll, n, rng)
        frames = frames @ _batch_rotation(yaw, pitch, roll)
        y += length * (frames[:, :, 0] @ direction)
    return y


def analyze_loop3d(loop: VectorLoop3D) -> LoopResult:
    """Analyse a 3D vector loop.

    Linearised worst case / RSS / P_fail from the analytic sensitivities at the
    means; Monte Carlo on the exact function; finite-difference sensitivities
    alongside as a cross-check. Lengths in millimetres, angles in radians.
    """
    return assemble_loop_result(
        name=loop.name,
        requirement=loop.requirement,
        analysis=loop.analysis,
        variables=loop.variables(),
        analytic=analytic_sensitivities_3d(loop),
        fd=finite_difference_sensitivities_3d(loop),
        y_mean=loop3d_value(_mean_table(loop), loop.unit_direction(), loop.requirement.constant),
        value_with=lambda index, delta: _value_with(loop, index, delta),
        sampler=lambda n, seed: sample_loop3d(loop, n, seed),
    )
