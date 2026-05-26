"""Render a unified `ReviewReport` into the ADR-013 markdown format.

Step 18c. `/v3-review` produces the same report shape users see from the
team-based `/deep-review`. Two public functions (arch-review #8):

    compute_verdict(report)        — pure verdict over finding counts; the SAME
                                     rule as /deep-review.
    render_review_markdown(report) — the full markdown document.

Known limitation (ADR-018): the fan-out aggregator merges by semantic
similarity but does NOT apply /deep-review's corroboration *escalation* rules,
so the verdict here may be milder at the severity margin.
"""

from __future__ import annotations

from hooks.lib.llm.schemas import ReviewReport

_SEVERITY_ORDER = ("CRITICAL", "IMPORTANT", "SUGGESTION")


def _counts(report: ReviewReport) -> dict[str, int]:
    counts = {sev: 0 for sev in _SEVERITY_ORDER}
    for f in report.findings:
        if f.severity in counts:
            counts[f.severity] += 1
    return counts


def compute_verdict(report: ReviewReport) -> str:
    """Return the verdict string, using the SAME thresholds as `/deep-review`.

    - any CRITICAL          → "FIX ISSUES FIRST"
    - else more than 5 IMPORTANT → "REVIEW RECOMMENDED"
    - else                  → "READY"
    """
    counts = _counts(report)
    if counts["CRITICAL"] > 0:
        return "FIX ISSUES FIRST"
    if counts["IMPORTANT"] > 5:
        return "REVIEW RECOMMENDED"
    return "READY"


def _render_finding(f) -> str:
    lines = [
        f"### {f.severity}: {f.title}",
        f"- **Location**: `{f.file}:{f.line}`",
        f"- **Description**: {f.body}",
    ]
    if f.suggested_fix:
        lines.append(f"- **Fix**: {f.suggested_fix}")
    return "\n".join(lines)


def render_review_markdown(
    report: ReviewReport,
    *,
    worker_errors: dict[str, str] | None = None,
) -> str:
    """Render the unified report as ADR-013 markdown.

    Args:
        report: the aggregated `ReviewReport`.
        worker_errors: optional {worker_name: error} for workers that failed in
            the fan-out; rendered as a "Workers that did not complete" section so
            the reader knows coverage was partial.
    """
    counts = _counts(report)
    verdict = compute_verdict(report)

    out: list[str] = [
        "# V3 Review — Fan-out Report",
        "",
        f"**Scope**: {report.scope}",
        "",
        f"**Summary**: {report.summary}",
        "",
    ]

    for sev in _SEVERITY_ORDER:
        findings = [f for f in report.findings if f.severity == sev]
        if not findings:
            continue
        for f in findings:
            out.append(_render_finding(f))
            out.append("")

    if worker_errors:
        out.append("## Workers that did not complete")
        for name, err in worker_errors.items():
            out.append(f"- **{name}**: {err}")
        out.append("")

    out.extend([
        "## Summary",
        f"- **CRITICAL**: {counts['CRITICAL']}",
        f"- **IMPORTANT**: {counts['IMPORTANT']}",
        f"- **SUGGESTION**: {counts['SUGGESTION']}",
        f"- **Verdict**: {verdict}",
    ])
    return "\n".join(out)


__all__ = ["compute_verdict", "render_review_markdown"]
