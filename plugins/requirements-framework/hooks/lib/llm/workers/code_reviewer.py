"""Structured-output worker around the `code-reviewer` agent prompt.

Step 10 pilot; refactored in Step 18b to delegate the shared query-loop to
`workers/_base.run_worker()`.

Calls `claude_agent_sdk.query()` with native `output_format` (SDK v0.2.82+)
through the budget-recording wrapper at `hooks.lib.llm.claude`, so every
invocation is auto-recorded into the monthly $-tracker ledger (Step 17a).

Workers are pure transforms: diff in, ReviewReport out. `allowed_tools=[]`
prevents the agent from reading/writing files or shelling out — the fan-out
coordinator (Step 18b) handles all I/O and observability session binding.

`query` and `ResultMessage` are imported HERE (not in `_base`) and passed into
`run_worker` so that `patch.object(code_reviewer, "query", ...)` in the tests
intercepts the call. See `_base.run_worker` docstring.
"""

from hooks.lib.llm.claude import ResultMessage, query
from hooks.lib.llm.prompts import load_prompt
from hooks.lib.llm.schemas import ReviewReport
from hooks.lib.llm.workers._base import run_worker

_SYSTEM = (
    "You are code-reviewer, producing strict JSON output conforming to "
    "ReviewReport. Filter aggressively — quality over quantity. "
    "Only report findings you are confident about."
)


async def review(diff: str, scope: str = "unstaged") -> ReviewReport:
    """Run the code-reviewer agent over a diff and return a typed report.

    Raises:
        RuntimeError: if the SDK reports `error_max_structured_output_retries`
            (the agent could not produce valid JSON within the SDK's internal
            retry cap) or if no terminal `ResultMessage` is observed.
    """
    prompt = load_prompt("code-reviewer", diff=diff, scope=scope)
    return await run_worker(
        prompt=prompt,
        system=_SYSTEM,
        schema=ReviewReport,
        agent_label="code-reviewer",
        query=query,
        result_cls=ResultMessage,
    )


__all__ = ["review"]
