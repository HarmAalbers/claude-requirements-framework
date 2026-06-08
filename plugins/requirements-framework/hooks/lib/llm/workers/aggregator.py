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

import json

from hooks.lib.llm.claude import ClaudeAgentOptions, ResultMessage, query
from hooks.lib.llm.prompts import load_prompt
from hooks.lib.llm.schemas import ReviewReport
from hooks.lib.llm.workers._base import REVIEW_MODEL


_SYSTEM = (
    "You are a review aggregator producing strict JSON output. "
    "Merge semantic duplicates, keep distinct findings, attribute sources."
)


def _build_options() -> ClaudeAgentOptions:
    options = ClaudeAgentOptions(
        system_prompt=_SYSTEM,
        allowed_tools=[],
        max_turns=5,
        model=REVIEW_MODEL,
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
    prompt = load_prompt("review-aggregator", reports_json=reports_json)
    options = _build_options()

    async for msg in query(prompt=prompt, options=options):
        if isinstance(msg, ResultMessage):
            if msg.subtype == "success" and msg.structured_output:
                return ReviewReport.model_validate(msg.structured_output)
            raise RuntimeError(
                f"aggregator failed: subtype={msg.subtype!r}")
    raise RuntimeError("aggregator: no ResultMessage observed")


__all__ = ["aggregate"]
