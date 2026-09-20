"""Human-readable renderers for Migration Studio validation results."""

from __future__ import annotations

import html

from .validation import ValidationReport


def render_validation_markdown(report: ValidationReport) -> str:
    """Render a deterministic operator-facing report without losing the digest."""
    lines = [
        f"# Migration validation: `{report.asset_id}`",
        "",
        f"- Status: **{report.status.upper()}**",
        f"- Level: `{report.level}`",
        f"- Report digest: `{report.digest}`",
        f"- Expected digest: `{report.expected_digest}`",
        f"- Actual digest: `{report.actual_digest}`",
        "",
        "| Check | Mode | Status | Message | Metrics |",
        "| --- | --- | --- | --- | --- |",
    ]
    for check in report.checks:
        metrics = ", ".join(f"{key}={value}" for key, value in check.metrics) or "-"
        lines.append(
            f"| `{check.check_id}` | `{check.mode}` | **{check.status.upper()}** | "
            f"{check.message} | {metrics} |"
        )
        if check.details:
            lines.extend(("", "<details>", "<summary>Details</summary>", "", "```json"))
            import json

            lines.append(
                json.dumps(list(check.details), ensure_ascii=False, indent=2, sort_keys=True)
            )
            lines.extend(("```", "</details>"))
    return "\n".join(lines) + "\n"


def render_validation_html(report: ValidationReport) -> str:
    """Render a self-contained HTML report suitable for download from the UI."""
    rows = []
    for check in report.checks:
        metrics = ", ".join(f"{key}={value}" for key, value in check.metrics) or "-"
        details = ""
        if check.details:
            import json

            details = (
                "<details><summary>Details</summary><pre>"
                + html.escape(
                    json.dumps(list(check.details), ensure_ascii=False, indent=2, sort_keys=True)
                )
                + "</pre></details>"
            )
        rows.append(
            "<tr>"
            + "".join(
                f"<td>{html.escape(str(value))}</td>"
                for value in (
                    check.check_id,
                    check.mode,
                    check.status.upper(),
                    check.message,
                    metrics,
                )
            )
            + f"<td>{details}</td></tr>"
        )
    return """<!doctype html>
<meta charset="utf-8">
<title>Migration validation: {asset}</title>
<style>body{{font:14px system-ui;background:#10151c;color:#e8eef5;margin:32px}}
table{{border-collapse:collapse;width:100%}}
td,th{{border:1px solid #33404d;padding:8px;text-align:left}}
th{{background:#1b2632}} .status{{font-weight:700}}</style>
<h1>Migration validation: <code>{asset}</code></h1>
<p>Status: <strong>{status}</strong> · Level: <code>{level}</code> ·
Digest: <code>{digest}</code></p>
<table><thead><tr><th>Check</th><th>Mode</th><th>Status</th><th>Message</th><th>Metrics</th><th>Details</th></tr></thead><tbody>{rows}</tbody></table>
""".format(
        asset=html.escape(report.asset_id),
        status=html.escape(report.status.upper()),
        level=html.escape(report.level),
        digest=html.escape(report.digest),
        rows="".join(rows),
    )


__all__ = ("render_validation_html", "render_validation_markdown")
