"""Render a :class:`Report` as JSON, Markdown or HTML."""

from __future__ import annotations

import base64

from jinja2 import Environment, StrictUndefined, select_autoescape

from detecttol.core.results import ContributorSummary, StackResult
from detecttol.report.model import Report

_DASH = "n/a"


def fmt(value: float | None, digits: int = 6) -> str:
    """Format a number to ``digits`` significant figures; ``n/a`` for ``None``."""
    if value is None:
        return _DASH
    out = f"{value:.{digits}g}"
    return "0" if out in ("-0", "0") else out


def fmt_pct(value: float | None) -> str:
    """Format a percentage with two decimals."""
    return _DASH if value is None else f"{value:.2f}"


def sorted_contributors(result: StackResult) -> list[ContributorSummary]:
    """Contributors sorted by RSS contribution, then worst-case contribution, descending.

    Python's sort is stable, so ties keep the input order.
    """
    return sorted(
        result.contributors,
        key=lambda c: (-(c.rss_contribution_pct or 0.0), -(c.wc_contribution_pct or 0.0)),
    )


def to_json(report: Report) -> str:
    """Report as pretty-printed JSON (follows ``report-v1.schema.json``)."""
    return report.model_dump_json(indent=2) + "\n"


_MD_TEMPLATE = """\
# Tolerance stack report: {{ r.name }}

{% if r.description %}{{ r.description }}

{% endif -%}
## Input summary

- Units: {{ r.units }}
- LSL: {{ fmt(r.lsl) }}
- USL: {{ fmt(r.usl) }}
- Constant term: {{ fmt(r.constant) }}
- Input file: {{ report.input_file or 'n/a' }}

| Contributor | Nominal | Upper tol | Lower tol | Sensitivity | Distribution | Cp | Mean | Half-range t | Sigma |
|---|---|---|---|---|---|---|---|---|---|
{% for c in r.contributors -%}
| {{ c.id }} | {{ fmt(c.nominal) }} | {{ fmt(c.upper_tol) }} | {{ fmt(c.lower_tol) }} | {{ fmt(c.sensitivity) }} | {{ c.distribution }} | {{ fmt(c.cp) }} | {{ fmt(c.mean) }} | {{ fmt(c.half_range) }} | {{ fmt(c.sigma) }} |
{% endfor %}
## Results

- Mean of Y: {{ fmt(r.mean) }} {{ r.units }}
{% if r.worst_case %}
### Worst case

- Half-range: {{ fmt(r.worst_case.half_range) }}
- Range: [{{ fmt(r.worst_case.lower) }}, {{ fmt(r.worst_case.upper) }}]
- Meets spec: {{ 'yes' if r.worst_case.meets_spec else 'NO' }}
{% endif %}{% if r.rss %}
### RSS (statistical)

- Sigma: {{ fmt(r.rss.sigma) }}
- 3-sigma half-range: {{ fmt(r.rss.three_sigma) }}
- Mean +/- 3 sigma: [{{ fmt(r.rss.lower) }}, {{ fmt(r.rss.upper) }}]
- Predicted failure (normal assumption): {{ fmt(r.rss.p_fail) }} = {{ fmt(r.rss.p_fail_ppm) }} ppm
- Cpl: {{ fmt(r.rss.cpl) }}
- Cpu: {{ fmt(r.rss.cpu) }}
- Cpk: {{ fmt(r.rss.cpk) }}
{% endif %}{% if r.modified_rss %}
### Modified RSS (Bender, k = {{ fmt(r.modified_rss.k) }})

- Half-range: {{ fmt(r.modified_rss.half_range) }}
- Range: [{{ fmt(r.modified_rss.lower) }}, {{ fmt(r.modified_rss.upper) }}]
{% endif %}{% if r.monte_carlo %}{% set mc = r.monte_carlo %}
### Monte Carlo

- Samples N: {{ mc.n }}
- Seed: {{ mc.seed }}
- Mean: {{ fmt(mc.mean) }}
- Std: {{ fmt(mc.std) }}
- Min / max: {{ fmt(mc.min) }} / {{ fmt(mc.max) }}
- Percentiles 0.135 / 2.5 / 50 / 97.5 / 99.865: {{ fmt(mc.percentiles.p0_135) }} / {{ fmt(mc.percentiles.p2_5) }} / {{ fmt(mc.percentiles.p50) }} / {{ fmt(mc.percentiles.p97_5) }} / {{ fmt(mc.percentiles.p99_865) }}
{% if mc.zero_failure_upper_bound is not none -%}
- Outside spec: 0 of {{ mc.n }} observed. Not 0 ppm: failure rate < {{ fmt(1e6 * mc.zero_failure_upper_bound) }} ppm (one-sided 95 % upper bound)
{% else -%}
- Outside spec: {{ mc.n_fail }} of {{ mc.n }} = {{ fmt(mc.fraction_fail_ppm) }} ppm
{% endif -%}
- Wilson interval (two-sided 95 %): [{{ fmt(1e6 * mc.wilson_lower) }}, {{ fmt(1e6 * mc.wilson_upper) }}] ppm
- Convergence (std at N/2 vs N): {{ fmt(mc.std_half) }} vs {{ fmt(mc.std) }}, {{ 'converged' if mc.converged else 'NOT CONVERGED' }}
{% if histogram_ref %}
![Monte Carlo histogram]({{ histogram_ref }})
{% endif %}{% endif %}
## Contributions (sorted, largest first)

| Contributor | RSS % | Worst case % |
|---|---|---|
{% for c in contributors_sorted -%}
| {{ c.id }} | {{ fmt_pct(c.rss_contribution_pct) }} | {{ fmt_pct(c.wc_contribution_pct) }} |
{% endfor %}
## Warnings

{% if r.warnings -%}
{% for w in r.warnings -%}
- **{{ w.code }}**: {{ w.message }}
{% endfor -%}
{% else -%}
None.
{% endif %}
---

detecttol {{ report.tool.version }} | report schema v{{ report.schema_version }} | seed {{ r.monte_carlo.seed if r.monte_carlo else 'n/a' }} | generated {{ report.generated_at }}
"""

_HTML_TEMPLATE = """\
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Tolerance stack report: {{ r.name }}</title>
<style>
body { font-family: system-ui, sans-serif; margin: 2rem auto; max-width: 62rem; padding: 0 1rem; color: #1c1c1c; }
table { border-collapse: collapse; margin: 0.5rem 0 1.25rem; }
th, td { border: 1px solid #c8c8c8; padding: 0.3rem 0.6rem; text-align: right; }
th:first-child, td:first-child { text-align: left; }
th { background: #f0f2f5; }
.warn { background: #fff4d6; border-left: 4px solid #d99a00; padding: 0.5rem 0.8rem; margin: 0.4rem 0; }
.bad { color: #b3261e; font-weight: 600; }
footer { margin-top: 2rem; font-size: 0.85rem; color: #555; border-top: 1px solid #ccc; padding-top: 0.6rem; }
img { max-width: 100%; }
</style>
</head>
<body>
<h1>Tolerance stack report: {{ r.name }}</h1>
{% if r.description %}<p>{{ r.description }}</p>{% endif %}

<h2>Input summary</h2>
<table>
<tr><th>Units</th><td>{{ r.units }}</td></tr>
<tr><th>LSL</th><td>{{ fmt(r.lsl) }}</td></tr>
<tr><th>USL</th><td>{{ fmt(r.usl) }}</td></tr>
<tr><th>Constant term</th><td>{{ fmt(r.constant) }}</td></tr>
<tr><th>Input file</th><td>{{ report.input_file or 'n/a' }}</td></tr>
</table>
<table>
<tr><th>Contributor</th><th>Nominal</th><th>Upper tol</th><th>Lower tol</th><th>Sensitivity</th><th>Distribution</th><th>Cp</th><th>Mean</th><th>Half-range t</th><th>Sigma</th></tr>
{% for c in r.contributors -%}
<tr><td>{{ c.id }}</td><td>{{ fmt(c.nominal) }}</td><td>{{ fmt(c.upper_tol) }}</td><td>{{ fmt(c.lower_tol) }}</td><td>{{ fmt(c.sensitivity) }}</td><td>{{ c.distribution }}</td><td>{{ fmt(c.cp) }}</td><td>{{ fmt(c.mean) }}</td><td>{{ fmt(c.half_range) }}</td><td>{{ fmt(c.sigma) }}</td></tr>
{% endfor -%}
</table>

<h2>Results</h2>
<p>Mean of Y: {{ fmt(r.mean) }} {{ r.units }}</p>
{% if r.worst_case %}
<h3>Worst case</h3>
<table>
<tr><th>Half-range</th><td>{{ fmt(r.worst_case.half_range) }}</td></tr>
<tr><th>Range</th><td>[{{ fmt(r.worst_case.lower) }}, {{ fmt(r.worst_case.upper) }}]</td></tr>
<tr><th>Meets spec</th><td>{% if r.worst_case.meets_spec %}yes{% else %}<span class="bad">NO</span>{% endif %}</td></tr>
</table>
{% endif %}
{% if r.rss %}
<h3>RSS (statistical)</h3>
<table>
<tr><th>Sigma</th><td>{{ fmt(r.rss.sigma) }}</td></tr>
<tr><th>3-sigma half-range</th><td>{{ fmt(r.rss.three_sigma) }}</td></tr>
<tr><th>Mean +/- 3 sigma</th><td>[{{ fmt(r.rss.lower) }}, {{ fmt(r.rss.upper) }}]</td></tr>
<tr><th>Predicted failure (normal assumption)</th><td>{{ fmt(r.rss.p_fail) }} = {{ fmt(r.rss.p_fail_ppm) }} ppm</td></tr>
<tr><th>Cpl</th><td>{{ fmt(r.rss.cpl) }}</td></tr>
<tr><th>Cpu</th><td>{{ fmt(r.rss.cpu) }}</td></tr>
<tr><th>Cpk</th><td>{{ fmt(r.rss.cpk) }}</td></tr>
</table>
{% endif %}
{% if r.modified_rss %}
<h3>Modified RSS (Bender, k = {{ fmt(r.modified_rss.k) }})</h3>
<table>
<tr><th>Half-range</th><td>{{ fmt(r.modified_rss.half_range) }}</td></tr>
<tr><th>Range</th><td>[{{ fmt(r.modified_rss.lower) }}, {{ fmt(r.modified_rss.upper) }}]</td></tr>
</table>
{% endif %}
{% if r.monte_carlo %}{% set mc = r.monte_carlo %}
<h3>Monte Carlo</h3>
<table>
<tr><th>Samples N</th><td>{{ mc.n }}</td></tr>
<tr><th>Seed</th><td>{{ mc.seed }}</td></tr>
<tr><th>Mean</th><td>{{ fmt(mc.mean) }}</td></tr>
<tr><th>Std</th><td>{{ fmt(mc.std) }}</td></tr>
<tr><th>Min / max</th><td>{{ fmt(mc.min) }} / {{ fmt(mc.max) }}</td></tr>
<tr><th>Percentiles 0.135 / 2.5 / 50 / 97.5 / 99.865</th><td>{{ fmt(mc.percentiles.p0_135) }} / {{ fmt(mc.percentiles.p2_5) }} / {{ fmt(mc.percentiles.p50) }} / {{ fmt(mc.percentiles.p97_5) }} / {{ fmt(mc.percentiles.p99_865) }}</td></tr>
{% if mc.zero_failure_upper_bound is not none -%}
<tr><th>Outside spec</th><td>0 of {{ mc.n }} observed. Not 0 ppm: failure rate &lt; {{ fmt(1e6 * mc.zero_failure_upper_bound) }} ppm (one-sided 95 % upper bound)</td></tr>
{% else -%}
<tr><th>Outside spec</th><td>{{ mc.n_fail }} of {{ mc.n }} = {{ fmt(mc.fraction_fail_ppm) }} ppm</td></tr>
{% endif -%}
<tr><th>Wilson interval (two-sided 95 %)</th><td>[{{ fmt(1e6 * mc.wilson_lower) }}, {{ fmt(1e6 * mc.wilson_upper) }}] ppm</td></tr>
<tr><th>Convergence (std at N/2 vs N)</th><td>{{ fmt(mc.std_half) }} vs {{ fmt(mc.std) }}, {% if mc.converged %}converged{% else %}<span class="bad">NOT CONVERGED</span>{% endif %}</td></tr>
</table>
{% if histogram_b64 %}<img alt="Monte Carlo histogram of Y with LSL/USL lines" src="data:image/png;base64,{{ histogram_b64 }}">{% endif %}
{% endif %}

<h2>Contributions (sorted, largest first)</h2>
<table>
<tr><th>Contributor</th><th>RSS %</th><th>Worst case %</th></tr>
{% for c in contributors_sorted -%}
<tr><td>{{ c.id }}</td><td>{{ fmt_pct(c.rss_contribution_pct) }}</td><td>{{ fmt_pct(c.wc_contribution_pct) }}</td></tr>
{% endfor -%}
</table>

<h2>Warnings</h2>
{% if r.warnings -%}
{% for w in r.warnings -%}
<div class="warn"><strong>{{ w.code }}</strong>: {{ w.message }}</div>
{% endfor -%}
{% else -%}
<p>None.</p>
{% endif %}
<footer>detecttol {{ report.tool.version }} | report schema v{{ report.schema_version }} | seed {{ r.monte_carlo.seed if r.monte_carlo else 'n/a' }} | generated {{ report.generated_at }}</footer>
</body>
</html>
"""

_md_env = Environment(undefined=StrictUndefined, autoescape=False, keep_trailing_newline=True)
_html_env = Environment(
    undefined=StrictUndefined,
    autoescape=select_autoescape(default=True, default_for_string=True),
    keep_trailing_newline=True,
)


def to_markdown(report: Report, histogram_ref: str | None = None) -> str:
    """Report as Markdown.

    Args:
        report: the report document.
        histogram_ref: relative path or URL of the histogram image to embed,
            or ``None`` to leave the image out.
    """
    return _md_env.from_string(_MD_TEMPLATE).render(
        report=report,
        r=report.result,
        contributors_sorted=sorted_contributors(report.result),
        histogram_ref=histogram_ref,
        fmt=fmt,
        fmt_pct=fmt_pct,
    )


def to_html(report: Report, histogram_png: bytes | None = None) -> str:
    """Report as a self-contained HTML page (histogram embedded as base64 PNG)."""
    b64 = None if histogram_png is None else base64.b64encode(histogram_png).decode("ascii")
    return _html_env.from_string(_HTML_TEMPLATE).render(
        report=report,
        r=report.result,
        contributors_sorted=sorted_contributors(report.result),
        histogram_b64=b64,
        fmt=fmt,
        fmt_pct=fmt_pct,
    )
