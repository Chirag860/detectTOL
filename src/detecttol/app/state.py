"""What the app does, as plain Python: open a model, pick faces, fill the table, analyse.

The page (:mod:`detecttol.app.ui`) only displays this state and calls its methods.
All numbers come from :mod:`detecttol.cad.cad_stack` and the core engine; the
verdict sentences are built from the result, never the other way round.
"""

from __future__ import annotations

import json
import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from detecttol.cad.cad_stack import (
    CadInput,
    CadStack,
    CadStackError,
    FitCheck,
    MissingKey,
    build_cad_stack,
    build_fit_check,
    missing_key,
    read_cad,
)
from detecttol.cad.pmi import FaceRef
from detecttol.cad.round import FitLimits, ResolvedDiameter, RoundFeatureError, find_round
from detecttol.core.models import AnalysisConfig, DrawingStandard, MonteCarloConfig
from detecttol.core.results import StackResult
from detecttol.standards.general import GeneralClass

PROJECT_VERSION = 1
CAD_SUFFIXES = (".sldasm", ".step", ".stp")
RowKind = Literal["cad", "table", "user", "missing", "gdt"]
Mode = Literal["gap", "fit"]


@dataclass(frozen=True)
class ChainRow:
    """One line of the chain table.

    Attributes:
        id: contributor id.
        part: part name.
        faces: ``"entry -> exit"`` face indices.
        nominal / upper / lower: [mm].
        sensitivity: +1 / -1.
        source: where the tolerance comes from, in words.
        kind: ``cad`` (read from the model), ``table`` (general tolerance or ISO
            286), ``user`` (typed in the app), ``missing`` (needs a value), ``gdt``.
        key: for rows the user may edit, the key of the missing dimension.
    """

    id: str
    part: str
    faces: str
    nominal: float
    upper: float
    lower: float
    sensitivity: float
    source: str
    kind: RowKind
    key: MissingKey | None = None


@dataclass(frozen=True)
class Verdict:
    """Plain-words answer. ``level``: ``ok`` (always fits), ``risk`` (can fail in the
    worst case), ``fail`` (fails at nominal)."""

    level: Literal["ok", "risk", "fail"]
    headline: str
    details: tuple[str, ...]


def _fmt(x: float | None) -> str:
    return "n/a" if x is None else f"{x:.4g}"


def _one_in(p: float) -> str:
    if p <= 0.0:
        return "none"
    if p < 1e-9:
        return "fewer than 1 in a billion"
    return f"about 1 in {1.0 / p:,.0f}"


def verdict(result: StackResult, fit: FitLimits | None = None) -> Verdict:
    """Plain-words verdict of a result (spec limits from the result itself).

    With ``fit`` (a hole/shaft fit check) the value is the clearance, and the
    headline names the kind of fit.
    """
    if fit is not None:
        return _fit_verdict(result, fit)
    limits = []
    if result.lsl is not None:
        limits.append(f"at least {_fmt(result.lsl)} mm")
    if result.usl is not None:
        limits.append(f"at most {_fmt(result.usl)} mm")
    spec = " and ".join(limits)
    details: list[str] = [f"Requirement: {spec}. Nominal-mean value {_fmt(result.mean)} mm."]
    inside_mean = (result.lsl is None or result.mean >= result.lsl) and (
        result.usl is None or result.mean <= result.usl
    )
    wc = result.worst_case
    rss = result.rss
    if rss is not None and rss.p_fail is not None:
        details.append(
            f"Statistical (RSS, normal processes at Cp = 1): predicted failures"
            f" {rss.p_fail_ppm:.3g} ppm ({_one_in(rss.p_fail)} assemblies); Cpk {_fmt(rss.cpk)}."
        )
    mc = result.monte_carlo
    if mc is not None:
        details.append(
            f"Monte Carlo ({mc.n:,} samples): {mc.n_fail} outside the spec"
            + (
                "; that is not zero risk: below"
                f" {1e6 * mc.zero_failure_upper_bound:.3g} ppm (95 %)."
                if mc.zero_failure_upper_bound is not None
                else "."
            )
        )
    if not inside_mean:
        return Verdict(
            "fail",
            f"Does not fit even at nominal size: {_fmt(result.mean)} mm is outside the"
            " requirement.",
            tuple(details),
        )
    if wc is not None and wc.meets_spec:
        return Verdict(
            "ok",
            "Always fits: even in the worst case the value stays between"
            f" {_fmt(wc.lower)} and {_fmt(wc.upper)} mm.",
            tuple(details),
        )
    if wc is not None:
        side = wc.lower if result.lsl is not None and wc.lower < result.lsl else wc.upper
        return Verdict(
            "risk",
            f"Can fail in the worst case: the value can reach {_fmt(side)} mm."
            + (
                f" Statistically {_one_in(rss.p_fail)} assemblies."
                if rss and rss.p_fail is not None
                else ""
            ),
            tuple(details),
        )
    return Verdict("risk", "No worst-case result was computed.", tuple(details))


def _fit_verdict(result: StackResult, fit: FitLimits) -> Verdict:
    base = verdict(result)
    kind = fit.kind.capitalize()
    span = f"{_fmt(fit.min_clearance)} to {_fmt(fit.max_clearance)} mm"
    details = (
        f"{kind} fit (IS 919 / ISO 286): clearance from {span}; a negative clearance is an"
        " interference.",
        *base.details,
    )
    if base.level == "ok":
        return Verdict(
            "ok", f"{kind} fit, always meets the requirement: clearance {span}.", details
        )
    wc = result.worst_case
    if base.level == "fail":
        return Verdict(
            "fail",
            f"{kind} fit: the requirement fails even at mid-tolerance (clearance"
            f" {_fmt(result.mean)} mm).",
            details,
        )
    side = span if wc is None else _fmt(wc.lower if result.lsl is not None else wc.upper) + " mm"
    return Verdict("risk", f"{kind} fit: can fail, the clearance can reach {side}.", details)


def _diameter_kind(dia: ResolvedDiameter) -> tuple[RowKind, str]:
    source = dia.tolerance_source or ""
    if dia.cad_source:
        detail = f"; {source}" if source else ""
        return "cad", f"{dia.cad_source}{detail}"
    if source.startswith("entered by the user"):
        return "user", "entered by you"
    if source.startswith("NEEDS A VALUE"):
        return "missing", "no tolerance in the model: enter one"
    return "table", source or "input"


@dataclass
class AppState:
    """One engineer's session: a model, a requirement, edits, and the last result."""

    cad: CadInput | None = None
    cad_file: Path | None = None
    drawings: list[Path] = field(default_factory=list)
    face_from: FaceRef | None = None
    face_to: FaceRef | None = None
    picking: Literal["from", "to"] = "from"
    mode: Mode = "gap"
    hole: FaceRef | None = None
    shaft: FaceRef | None = None
    fit: FitCheck | None = None
    lsl: float | None = 0.0
    usl: float | None = None
    standard: DrawingStandard = "is"
    general_class: GeneralClass | None = "m"
    overrides: dict[MissingKey, tuple[float, float]] = field(default_factory=dict)
    samples: int = 100_000
    seed: int = 42
    built: CadStack | None = None
    result: StackResult | None = None
    error: str | None = None

    # -- model -------------------------------------------------------------------------

    def open(self, path: str | Path, drawings: Sequence[str | Path] = ()) -> None:
        """Read a model (SolidWorks: ~20 s). Resets faces, edits and results."""
        p = Path(path)
        if p.suffix.lower() not in CAD_SUFFIXES:
            raise CadStackError(f"{p.name}: open a .SLDASM, .step or .stp file")
        cad = read_cad(p, list(drawings))
        self.cad, self.cad_file, self.drawings = cad, p, [Path(d) for d in drawings]
        self.face_from = self.face_to = None
        self.hole = self.shaft = None
        self.picking = "from"
        self.overrides.clear()
        self.built = self.result = self.fit = None
        self.error = None

    def summary(self) -> str:
        if self.cad is None:
            return "No model open."
        n_parts = len(self.cad.model.parts)
        round_found = ""
        if self.cad.diameters or self.cad.positions:
            round_found = (
                f", {len(self.cad.diameters)} diameters, {len(self.cad.positions)} positions"
            )
        return (
            f"{n_parts} parts; tolerances found ({self.cad.origin}): {len(self.cad.dimensions)}"
            f" dimensions, {len(self.cad.flatness)} flatness{round_found}."
        )

    def face_label(self, ref: FaceRef | None) -> str:
        if ref is None or self.cad is None:
            return "not chosen"
        face = self.cad.model.part(ref.part).faces[ref.face_index]
        if face.cylinder is not None:
            feature = find_round(self.cad.model, ref)
            return f"{ref.part}:{feature.face} ({feature.kind} dia {feature.diameter:g})"
        n = face.normal or (0.0, 0.0, 0.0)
        return f"{ref.part}:{ref.face_index} (normal {tuple(round(v, 3) + 0.0 for v in n)})"

    def set_mode(self, mode: Mode) -> None:
        """Switch between a gap between two faces and a hole/shaft fit."""
        if mode != self.mode:
            self.mode = mode
            self.result = None
            self.refresh()

    # -- requirement -------------------------------------------------------------------

    def pick(self, key: str) -> None:
        """A face was clicked (``PART:FACE``).

        Gap mode: set face 1 or face 2 (alternating); a round face is refused with a
        hint. Fit mode: a hole face sets the hole, a pin/shaft face the shaft.

        Raises:
            CadStackError: the face does not fit the mode (nothing is changed).
        """
        part, _, index = key.rpartition(":")
        ref = FaceRef(part, int(index))
        face = None if self.cad is None else self.cad.model.part(part).faces[ref.face_index]
        round_face = face is not None and face.cylinder is not None
        if self.mode == "fit":
            if not round_face or self.cad is None:
                raise CadStackError(f"{key} is not a hole or a shaft; click a round face")
            feature = find_round(self.cad.model, ref)
            chosen = FaceRef(part, feature.face)
            if feature.internal:
                self.hole = chosen
            else:
                self.shaft = chosen
            self.result = None
            self.refresh()
            return
        if round_face:
            raise CadStackError(
                f"{self.face_label(ref)} is round: a gap is measured between flat faces."
                " Use the Fit check for a hole and a shaft."
            )
        if self.picking == "from":
            self.face_from, self.picking = ref, "to"
        else:
            self.face_to, self.picking = ref, "from"
        self.result = None
        self.refresh()

    def set_override(self, key: MissingKey, upper: float, lower: float) -> None:
        self.overrides[key] = (upper, lower)
        self.result = None
        self.refresh()

    def refresh(self) -> None:
        """Rebuild the chain (or the fit) after any change; errors go to ``self.error``."""
        self.built, self.fit, self.error = None, None, None
        if self.mode == "fit":
            self._refresh_fit()
            return
        if self.cad is None or self.face_from is None or self.face_to is None:
            return
        try:
            self.built = build_cad_stack(
                self.cad,
                self.face_from,
                self.face_to,
                lsl=self.lsl,
                usl=self.usl,
                standard=self.standard,
                general_class=self.general_class,
                name=self.cad_file.stem if self.cad_file else "stack",
                description=f"distance {self.face_from.part}:{self.face_from.face_index}"
                f" -> {self.face_to.part}:{self.face_to.face_index}",
                analysis=AnalysisConfig(
                    methods=["worst_case", "rss", "monte_carlo"],
                    monte_carlo=MonteCarloConfig(n=self.samples, seed=self.seed),
                ),
                overrides=self.overrides,
                placeholder_missing=True,
            )
        except (CadStackError, ValueError) as exc:
            self.error = str(exc)

    def _refresh_fit(self) -> None:
        if self.cad is None or self.hole is None or self.shaft is None:
            return
        try:
            self.fit = build_fit_check(
                self.cad,
                self.hole,
                self.shaft,
                lsl=self.lsl,
                usl=self.usl,
                general_class=self.general_class,
                analysis=AnalysisConfig(
                    methods=["worst_case", "rss", "monte_carlo"],
                    monte_carlo=MonteCarloConfig(n=self.samples, seed=self.seed),
                ),
                overrides=self.overrides,
                placeholder_missing=True,
            )
        except (CadStackError, RoundFeatureError, ValueError) as exc:
            self.error = str(exc)

    @property
    def needs_value(self) -> int:
        """Rows still waiting for a tolerance."""
        if self.mode == "fit":
            return len(self.fit.needs_value) if self.fit else 0
        return len(self.built.needs_value) if self.built else 0

    # -- table ------------------------------------------------------------------------

    def _diameter_row(self, dia: ResolvedDiameter, sensitivity: float) -> ChainRow:
        kind, source = _diameter_kind(dia)
        key = None if kind == "cad" else (dia.part, dia.face, dia.face)
        what = "hole" if dia.internal else "pin"
        return ChainRow(
            dia.id, dia.part, f"{what} dia ({dia.face})", dia.nominal, dia.upper_tol,
            dia.lower_tol, sensitivity, source, kind, key,
        )  # fmt: skip

    def rows(self) -> list[ChainRow]:
        if self.mode == "fit":
            if self.fit is None:
                return []
            return [
                self._diameter_row(self.fit.hole, 1.0),
                self._diameter_row(self.fit.shaft, -1.0),
            ]
        if self.built is None:
            return []
        missing = {missing_key(m) for m in self.built.needs_value}
        rows: list[ChainRow] = []
        for link in self.built.chain.links:
            c = link.contributor
            key = None
            if c.id.startswith("float "):
                # white only when both diameters came from the model
                filled = {d.id for d in self.built.chain.filled_diameters}
                kind = "table" if any(f" {i}" in c.id for i in filled) else "cad"
                source = c.tolerance_source or c.id
            elif c.cad_source:
                kind = "cad"
                source = c.cad_source
                if c.tolerance_source and c.tolerance_source.startswith("position"):
                    source = f"{c.cad_source}: {c.tolerance_source}"
            elif c.tolerance_source and c.tolerance_source.startswith("entered by the user"):
                kind, source = "user", "entered by you"
            elif c.tolerance_source and c.tolerance_source.startswith("NEEDS A VALUE"):
                kind, source = "missing", "no tolerance in the model: enter one"
            else:
                kind, source = "table", c.tolerance_source or "input"
            if kind in ("user", "missing", "table") and c.cad_source is None:
                a, b = sorted((link.from_face, link.to_face))
                key = (link.part, a, b)
                if kind == "missing" and key not in missing:  # pragma: no cover - consistency
                    kind = "table"
            rows.append(
                ChainRow(
                    c.id,
                    link.part,
                    f"hole {link.from_face} / pin {link.to_face}"
                    if c.id.startswith("float ")
                    else f"{link.from_face} -> {link.to_face}",
                    c.nominal,
                    c.upper_tol,
                    c.lower_tol,
                    c.sensitivity,
                    source,
                    kind,
                    key,
                )
            )
        # diameters the chain needed but the model did not tolerance (editable)
        for dia in self.built.chain.filled_diameters:
            rows.append(self._diameter_row(dia, 0.0))
        if self.built.gdt is not None:
            gdt = self.built.gdt
            used = gdt.linear_contributors()[len(gdt.stack.contributors) :]
            for callout, c in zip(gdt.callouts, used, strict=True):
                if c.half_range > 0:
                    std = gdt.effective_standard.upper()
                    how = f"adds +/-{c.half_range:g} ({std}: not inside a size)"
                else:
                    how = f"adds nothing ({gdt.effective_standard.upper()}: inside the size)"
                rows.append(
                    ChainRow(
                        callout.id,
                        callout.id.split(":")[0],
                        "",
                        0.0,
                        c.upper_tol,
                        c.lower_tol,
                        1.0,
                        f"flatness {callout.tolerance:g}: {how}",
                        "gdt",
                    )
                )
        return rows

    # -- analysis ---------------------------------------------------------------------

    def analyze(self) -> StackResult:
        if self.mode == "fit":
            if self.fit is None:
                raise CadStackError(self.error or "choose a hole and a shaft first")
            self.result = self.fit.analyze()
            return self.result
        if self.built is None:
            raise CadStackError(self.error or "choose two faces first")
        self.result = self.built.analyze()
        return self.result

    def verdict(self) -> Verdict:
        if self.result is None:
            raise CadStackError("analyse first")
        return verdict(self.result, self.fit.limits if self.mode == "fit" and self.fit else None)

    def report_html(self) -> str:
        from detecttol import __version__
        from detecttol.report import build_report, render_histogram_png, to_html, utc_timestamp

        if self.result is None:
            raise CadStackError("analyse first")
        report = build_report(
            self.result,
            version=__version__,
            generated_at=utc_timestamp(),
            input_file=str(self.cad_file) if self.cad_file else None,
        )
        return to_html(report, render_histogram_png(self.result))

    # -- project file -----------------------------------------------------------------

    def to_project(self) -> dict[str, Any]:
        return {
            "detecttol_project": PROJECT_VERSION,
            "cad_file": str(self.cad_file) if self.cad_file else None,
            "drawings": [str(d) for d in self.drawings],
            "from": [self.face_from.part, self.face_from.face_index] if self.face_from else None,
            "to": [self.face_to.part, self.face_to.face_index] if self.face_to else None,
            "mode": self.mode,
            "hole": [self.hole.part, self.hole.face_index] if self.hole else None,
            "shaft": [self.shaft.part, self.shaft.face_index] if self.shaft else None,
            "lsl": self.lsl,
            "usl": self.usl,
            "standard": self.standard,
            "general_class": self.general_class,
            "overrides": [
                [k[0], k[1], k[2], u, lo] for k, (u, lo) in sorted(self.overrides.items())
            ],
            "samples": self.samples,
            "seed": self.seed,
        }

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_project(), indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> AppState:
        """Re-open a saved project (re-reads the CAD model, so edits in CAD are picked up)."""
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if data.get("detecttol_project") != PROJECT_VERSION:
            raise CadStackError(f"{Path(path).name}: not a detectTOL project file")
        state = cls(
            lsl=data["lsl"],
            usl=data["usl"],
            standard=data["standard"],
            general_class=data["general_class"],
            samples=data["samples"],
            seed=data["seed"],
        )
        state.open(data["cad_file"], data["drawings"])
        state.overrides = {
            (o[0], int(o[1]), int(o[2])): (float(o[3]), float(o[4])) for o in data["overrides"]
        }
        if data["from"] and data["to"]:
            state.face_from = FaceRef(data["from"][0], int(data["from"][1]))
            state.face_to = FaceRef(data["to"][0], int(data["to"][1]))
        state.mode = data.get("mode", "gap")
        if data.get("hole"):
            state.hole = FaceRef(data["hole"][0], int(data["hole"][1]))
        if data.get("shaft"):
            state.shaft = FaceRef(data["shaft"][0], int(data["shaft"][1]))
        state.refresh()
        return state


def is_finite(x: float | None) -> bool:
    return x is None or math.isfinite(x)
