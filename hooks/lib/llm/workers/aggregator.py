"""Aggregator agent — merge multiple ReviewReports into one unified report.

Step 10 second worker. Reads typed `ReviewReport` JSON from N reviewers
(different agents, different focus areas) and produces a single unified
`ReviewReport` with semantic deduplication, attribution, severity ranking,
and a narrative summary.

Why an agent and not a Python utility:
    Mechanical (file, line, category) keys are simultaneously too coarse
    (distinct issues at the same line collapse) and too fine (the same
    issue at adjacent lines stays duplicated). An LLM reading typed
    structured input produces semantically correct merges and a narrative
    summary for ~$0.03/run — validated by `hooks/lib/llm/_spikes/v3_spike.py`.

Wired into nothing yet. Step 18 (supervisor) consumes this.
"""

from __future__ import annotations

import json

from hooks.lib.llm.claude import ClaudeAgentOptions, ResultMessage, query
from hooks.lib.llm.schemas import ReviewReport


_SYSTEM = (
    "You are a review aggregator producing strict JSON output. "
    "Merge semantic duplicates, keep distinct findings, attribute sources."
)

_PROMPT_TEMPLATE = """\
You are the review-aggregator. You receive structured review reports from multiple reviewers (different agents, different focus areas) on the SAME code change. Produce a single unified ReviewReport.

Rules:

1. MERGE findings that describe the same underlying issue — even if reported at slightly different line numbers (±2 lines) or in different wording. When merging, take the worst severity and the highest confidence. Include attribution in the body, e.g. "[flagged by code-reviewer + appsec-auditor]".

2. KEEP DISTINCT findings separate — even if they happen to be at the same line. Two different bugs reported at the same line remain two findings.

3. RANK the final findings by severity (CRITICAL > IMPORTANT > SUGGESTION), then by confidence within each severity.

4. WRITE A NARRATIVE SUMMARY (1–3 sentences) that surfaces patterns across the findings — e.g., "Security issues cluster around the new export_users function."

Return a single ReviewReport with:
  - agent: "review-aggregator"
  - scope: copy from the inputs (they should all share the same scope)
  - findings: the merged, ranked list
  - summary: the narrative summary

Input worker reports (JSON):
{reports_json}
"""


def _build_options() -> ClaudeAgentOptions:
    options = ClaudeAgentOptions(
        system_prompt=_SYSTEM,
        allowed_tools=[],
        max_turns=5,
    )
    setattr(options, "output_format", {
        "type": "json_schema",
        "schema": ReviewReport.model_json_schema(),
    })
    try:
        setattr(options, "agent", "review-aggregator")
    except (AttributeError, TypeError):
        pass
    return options


async def aggregate(reports: list[ReviewReport]) -> ReviewReport:
    """Merge worker review reports into one unified ReviewReport.

    Args:
        reports: One or more ReviewReports from worker agents. Length-1 input
            is supported (degenerate case) — the aggregator will still
            produce a unified report with `agent='review-aggregator'`.

    Raises:
        ValueError: if `reports` is empty (callers must filter before calling).
        RuntimeError: if the SDK reports `error_max_structured_output_retries`
            or yields no terminal `ResultMessage`.
    """
    if not reports:
        raise ValueError("aggregate() requires at least one report")

    reports_json = json.dumps(
        [r.model_dump() for r in reports], indent=2)
    prompt = _PROMPT_TEMPLATE.format(reports_json=reports_json)
    options = _build_options()

    async for msg in query(prompt=prompt, options=options):
        if isinstance(msg, ResultMessage):
            if msg.subtype == "success" and msg.structured_output:
                return ReviewReport.model_validate(msg.structured_output)
            raise RuntimeError(
                f"aggregator failed: subtype={msg.subtype!r}")
    raise RuntimeError("aggregator: no ResultMessage observed")


__all__ = ["aggregate"]
