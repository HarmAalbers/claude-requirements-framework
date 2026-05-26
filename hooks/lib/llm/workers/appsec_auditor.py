"""Structured-output worker around the `appsec-auditor` agent prompt.

Step 18b. Pure transform: diff in, ReviewReport out, `allowed_tools=[]`.
Delegates the query-loop to `_base.run_worker()`; keeps its own `query` /
`ResultMessage` imports so test mock-patching of this module's namespace
intercepts the call (see `_base.run_worker` docstring).
"""

from __future__ import annotations

from hooks.lib.llm.claude import ResultMessage, query
from hooks.lib.llm.prompts import load_prompt
from hooks.lib.llm.schemas import ReviewReport
from hooks.lib.llm.workers._base import run_worker

_SYSTEM = (
    "You are appsec-auditor, producing strict JSON output conforming to "
    "ReviewReport. Audit for OWASP Top 10 vulnerabilities. Only report issues "
    "you can tie to a concrete line in the diff."
)


async def review(diff: str, scope: str = "unstaged") -> ReviewReport:
    """Run the appsec-auditor agent over a diff and return a typed report.

    Raises:
        RuntimeError: if the SDK reports a non-success subtype or no terminal
            `ResultMessage` is observed.
    """
    prompt = load_prompt("appsec-auditor", diff=diff, scope=scope)
    return await run_worker(
        prompt=prompt,
        system=_SYSTEM,
        schema=ReviewReport,
        agent_label="appsec-auditor",
        error_prefix="appsec-auditor",
        query=query,
        result_cls=ResultMessage,
    )


__all__ = ["review"]
