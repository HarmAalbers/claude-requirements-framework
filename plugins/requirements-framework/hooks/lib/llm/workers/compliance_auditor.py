"""Structured-output worker around the `compliance-auditor` agent prompt.

Step 18c. Pure transform: diff in, ReviewReport out, `allowed_tools=[]`.
Keeps its own `query`/`ResultMessage` imports for test mock-patching (see
`_base.run_worker` docstring).
"""

from hooks.lib.llm.claude import ResultMessage, query
from hooks.lib.llm.prompts import load_prompt
from hooks.lib.llm.schemas import ReviewReport
from hooks.lib.llm.workers._base import run_worker

_SYSTEM = (
    "You are compliance-auditor, producing strict JSON output conforming to "
    "ReviewReport. Audit for regulatory/privacy compliance issues: PII in logs, "
    "URLs, or client storage; unencrypted sensitive data; missing audit logging "
    "for sensitive actions; and retention/erasure gaps. Report only when the "
    "change touches data handling that raises such concerns."
)


async def review(diff: str, scope: str = "unstaged") -> ReviewReport:
    """Run the compliance-auditor agent over a diff and return a typed report.

    Raises:
        RuntimeError: on a non-success subtype or no terminal `ResultMessage`.
    """
    prompt = load_prompt("compliance-auditor", diff=diff, scope=scope)
    return await run_worker(
        prompt=prompt,
        system=_SYSTEM,
        schema=ReviewReport,
        agent_label="compliance-auditor",
        query=query,
        result_cls=ResultMessage,
    )


__all__ = ["review"]
