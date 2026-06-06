"""Structured-output worker around the `test-analyzer` agent prompt.

Step 18c. Pure transform: diff in, ReviewReport out, `allowed_tools=[]`.
Keeps its own `query`/`ResultMessage` imports for test mock-patching (see
`_base.run_worker` docstring).
"""

from __future__ import annotations

from hooks.lib.llm.claude import ResultMessage, query
from hooks.lib.llm.prompts import load_prompt
from hooks.lib.llm.schemas import ReviewReport
from hooks.lib.llm.workers._base import run_worker

_SYSTEM = (
    "You are test-analyzer, producing strict JSON output conforming to "
    "ReviewReport. Assess test coverage quality for the changed code: missing "
    "tests for critical paths and edge cases, weak assertions, untested error "
    "handling. Do not demand 100% coverage; flag meaningful gaps only."
)


async def review(diff: str, scope: str = "unstaged") -> ReviewReport:
    """Run the test-analyzer agent over a diff and return a typed report.

    Raises:
        RuntimeError: on a non-success subtype or no terminal `ResultMessage`.
    """
    prompt = load_prompt("test-analyzer", diff=diff, scope=scope)
    return await run_worker(
        prompt=prompt,
        system=_SYSTEM,
        schema=ReviewReport,
        agent_label="test-analyzer",
        query=query,
        result_cls=ResultMessage,
    )


__all__ = ["review"]
