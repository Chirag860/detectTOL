"""Monte Carlo histogram rendering (PNG) with LSL/USL lines."""

from __future__ import annotations

import io

import matplotlib

matplotlib.use("Agg")  # headless; must be set before pyplot is imported

import itertools

import matplotlib.pyplot as plt

from detecttol.core.results import StackResult


def render_histogram_png(result: StackResult, dpi: int = 110) -> bytes | None:
    """PNG bytes of the Monte Carlo histogram of Y [mm]; ``None`` if MC was not run.

    Dashed vertical lines mark LSL and USL when present.
    """
    mc = result.monte_carlo
    if mc is None:
        return None
    edges, counts = mc.histogram.edges, mc.histogram.counts
    fig, ax = plt.subplots(figsize=(7.0, 3.6))
    try:
        widths = [b - a for a, b in itertools.pairwise(edges)]
        if all(w == 0 for w in widths):
            ax.axvline(edges[0], color="#3b6ea5", linewidth=2)
        else:
            ax.bar(edges[:-1], counts, width=widths, align="edge", color="#3b6ea5", linewidth=0)
        if result.lsl is not None:
            ax.axvline(result.lsl, color="#c0392b", linestyle="--", label=f"LSL = {result.lsl:g}")
        if result.usl is not None:
            ax.axvline(result.usl, color="#c0392b", linestyle="-.", label=f"USL = {result.usl:g}")
        ax.set_xlabel(f"Y [{result.units}]")
        ax.set_ylabel("samples")
        ax.set_title(f"{result.name}: Monte Carlo, N = {mc.n}, seed = {mc.seed}")
        if result.lsl is not None or result.usl is not None:
            ax.legend(loc="upper right", frameon=False)
        fig.tight_layout()
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=dpi)
        return buf.getvalue()
    finally:
        plt.close(fig)
