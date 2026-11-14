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
    MissingKey,
    build_cad_stack,
    missing_key,
    read_cad,
)
from detecttol.cad.pmi import FaceRef
from detecttol.core.models import AnalysisConfig, DrawingStandard, MonteCarloConfig
from detecttol.core.results import StackResult
from detecttol.standards.general import GeneralClass

PROJECT_VERSION = 1
CAD_SUFFIXES = (".sldasm", ".step", ".stp")
RowKind = Literal["cad", "table", "user", "missing", "gdt"]


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


def verdict(result: StackResult) -> Verdict:
    """Plain-words verdict of a result (spec limits from the result itself)."""
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


@dataclass
class AppState:
    """One engineer's session: a model, a requirement, edits, and the last result."""

    cad: CadInput | None = None
    cad_file: Path | None = None
    drawings: list[Path] = field(default_factory=list)
    face_from: FaceRef | None = None
    face_to: FaceRef | None = None
    picking: Literal["from", "to"] = "from"
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
        self.picking = "from"
        self.overrides.clear()
        self.built = self.result = None
        self.error = None

    def summary(self) -> str:
        if self.cad is None:
            return "No model open."
        n_parts = len(self.cad.model.parts)
        return (
            f"{n_parts} parts; tolerances found ({self.cad.origin}): {len(self.cad.dimensions)}"
            f" dimensions, {len(self.cad.flatness)} flatness."
        )

    def face_label(self, ref: FaceRef | None) -> str:
        if ref is None or self.cad is None:
            return "not chosen"
        face = self.cad.model.part(ref.part).faces[ref.face_index]
        n = face.normal or (0.0, 0.0, 0.0)
        return f"{ref.part}:{ref.face_index} (normal {tuple(round(v, 3) + 0.0 for v in n)})"

    # -- requirement -------------------------------------------------------------------

    def pick(self, key: str) -> None:
        """A face was clicked (``PART:FACE``): set the face being picked, then switch."""
        part, _, index = key.rpartition(":")
        ref = FaceRef(part, int(index))
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
        """Rebuild the chain after any change; errors go to ``self.error``."""
        self.built, self.error = None, None
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

    # -- table ------------------------------------------------------------------------

    def rows(self) -> list[ChainRow]:
        if self.built is None:
            return []
        missing = {missing_key(m) for m in self.built.needs_value}
        rows: list[ChainRow] = []
        for link in self.built.chain.links:
            c = link.contributor
            key = None
            if c.cad_source:
                kind: RowKind = "cad"
                source = c.cad_source
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
                    f"{link.from_face} -> {link.to_face}",
                    c.nominal,
                    c.upper_tol,
                    c.lower_tol,
                    c.sensitivity,
                    source,
                    kind,
                    key,
                )
            )
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
        if self.built is None:
            raise CadStackError(self.error or "choose two faces first")
        self.result = self.built.analyze()
        return self.result

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
        state.refresh()
        return state


def is_finite(x: float | None) -> bool:
    return x is None or math.isfinite(x)
