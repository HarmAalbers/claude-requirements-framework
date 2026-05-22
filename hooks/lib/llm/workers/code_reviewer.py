"""Structured-output worker around the `code-reviewer` agent prompt.

Step 10 pilot. Calls `claude_agent_sdk.query()` with native `output_format`
(SDK v0.2.82+) through the budget-recording wrapper at
`hooks.lib.llm.claude`, so every invocation is auto-recorded into the
monthly $-tracker ledger (Step 17a).

Workers are pure transforms: diff in, ReviewReport out. `allowed_tools=[]`
prevents the agent from reading/writing files or shelling out — the
supervisor (Step 18) handles all I/O.

Not yet wired into `/deep-review`. That happens in Step 18.
"""

from __future__ import annotations

from hooks.lib.llm.claude import ClaudeAgentOptions, ResultMessage, query
from hooks.lib.llm.schemas import ReviewReport


_SYSTEM = (
    "You are code-reviewer, producing strict JSON output conforming to "
    "ReviewReport. Filter aggressively — quality over quantity. "
    "Only report findings you are confident about."
)

_PROMPT = """\
Review the diff below. For each issue, produce a ReviewFinding with:
  severity:   CRITICAL | IMPORTANT | SUGGESTION
  file, line: location (line >= 1)
  category:   security | performance | logic | style | test | compatibility | complexity
  title:      10-120 chars
  body:       1-3 sentences explaining the issue
  suggested_fix: optional code or guidance
  confidence: 0.0-1.0

Wrap them in a ReviewReport with agent='code-reviewer', scope={scope!r}, and a 1-3 sentence summary.

```diff
{diff}
```
"""


def _build_options() -> ClaudeAgentOptions:
    options = ClaudeAgentOptions(
        system_prompt=_SYSTEM,
        allowed_tools=[],
        max_turns=5,
    )
    # `output_format` and `agent` are set dynamically because their presence
    # in the dataclass signature varies across SDK minor versions, and
    # `agent` is our extension for the budget recorder's label (see
    # hooks/lib/llm/claude.py `_agent_label`). setattr both keeps Pyright
    # quiet and is forward-compatible.
    setattr(options, "output_format", {
        "type": "json_schema",
        "schema": ReviewReport.model_json_schema(),
    })
    try:
        setattr(options, "agent", "code-reviewer")
    except (AttributeError, TypeError):
        # If ClaudeAgentOptions becomes frozen in a future SDK release,
        # budget entries fall back to the model name. Not fatal.
        pass
    return options


async def review(diff: str, scope: str = "unstaged") -> ReviewReport:
    """Run the code-reviewer agent over a diff and return a typed report.

    Raises:
        RuntimeError: if the SDK reports `error_max_structured_output_retries`
            (the agent could not produce valid JSON within the SDK's internal
            retry cap) or if no terminal `ResultMessage` is observed.
    """
    prompt = _PROMPT.format(diff=diff, scope=scope)
    options = _build_options()

    async for msg in query(prompt=prompt, options=options):
        if isinstance(msg, ResultMessage):
            if msg.subtype == "success" and msg.structured_output:
                return ReviewReport.model_validate(msg.structured_output)
            raise RuntimeError(
                f"code-reviewer failed: subtype={msg.subtype!r}")
    raise RuntimeError("code-reviewer: no ResultMessage observed")


__all__ = ["review"]
