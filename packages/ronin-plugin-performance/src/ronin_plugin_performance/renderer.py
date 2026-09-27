"""Dependency-free HTML renderer for exported Performance Studio reports."""

from __future__ import annotations

import html
from collections.abc import Mapping
from typing import Any


def render_report(report: Mapping[str, Any]) -> str:
    """Render a bounded accessible HTML fragment; data is escaped and capped."""
    series = (
        report.get("series", {}).get("stages", [])
        if isinstance(report.get("series"), Mapping)
        else []
    )
    rows = []
    bars = []
    for stage in list(series)[:200]:
        if not isinstance(stage, Mapping):
            continue
        label = html.escape(str(stage.get("id", "unknown")))
        duration = max(0.0, float(stage.get("duration_ms", 0) or 0))
        shuffle = max(0.0, float(stage.get("shuffle_bytes", 0) or 0))
        spill = max(0.0, float(stage.get("spill_bytes", 0) or 0))
        rows.append(
            f'<tr><th scope="row">{label}</th><td><meter min="0" max="100" value="{min(duration, 100)}">{duration:g} ms</meter> <span>{duration:g} ms</span></td><td>{shuffle:g} B</td><td>{spill:g} B</td></tr>'  # noqa: E501
        )
        bars.append((label, duration, shuffle, spill))
    score = html.escape(str(report.get("score", "n/a")))
    max_duration = max((item[1] for item in bars), default=1.0) or 1.0
    svg_rows = []
    for index, (label, duration, shuffle, spill) in enumerate(bars):
        y = 24 + index * 30
        width = round(320 * duration / max_duration, 2)
        svg_rows.append(
            f'<text x="0" y="{y + 12}" class="axis-label">{label}</text><rect x="92" y="{y}" width="{width}" height="16" fill="var(--viz-series-1)" data-tooltip="{label}: {duration:g} ms"/><text x="{min(420, 98 + width)}" y="{y + 12}" class="value-label">{duration:g} ms · shuffle {shuffle:g} B · spill {spill:g} B</text>'  # noqa: E501
        )
    svg_height = max(64, 24 + len(svg_rows) * 30)
    regression = report.get("regression")
    regression_html = ""
    if isinstance(regression, Mapping):
        regression_html = f'<p aria-live="polite">Baseline: <strong>{html.escape(str(regression.get("baseline_run_id", "n/a")))}</strong> · Regressions: <strong>{html.escape(str(len(regression.get("regressions", []))))}</strong></p>'  # noqa: E501
    return "\n".join(
        [
            '<section id="performance-studio-report" aria-labelledby="performance-studio-title">',
            '<h2 id="performance-studio-title">Performance Studio</h2>',
            f'<p aria-live="polite">Score: <strong>{score}</strong></p>',
            regression_html,
            f'<figure role="img" aria-labelledby="performance-stage-chart-title"><figcaption id="performance-stage-chart-title">Stage duration with shuffle and spill context</figcaption><svg class="performance-stage-chart" viewBox="0 0 720 {svg_height}" role="img" aria-label="Stage duration bars"><title>Stage duration by stage</title>{"".join(svg_rows)}</svg></figure>',  # noqa: E501
            '<table><caption>Stage duration, shuffle and spill</caption><thead><tr><th scope="col">Stage</th><th scope="col">Duration</th><th scope="col">Shuffle</th><th scope="col">Spill</th></tr></thead><tbody>',  # noqa: E501
            *rows,
            "</tbody></table></section>",
        ]
    )
