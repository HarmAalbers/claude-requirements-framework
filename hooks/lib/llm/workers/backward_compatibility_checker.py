"""Structured-output worker around the `backward-compatibility-checker` agent prompt.

Step 18c. Pure transform: diff in, ReviewReport out, `allowed_tools=[]`.
Keeps its own `query`/`ResultMessage` imports for test mock-patching (see
`_base.run_worker` docstring).
"""

from hooks.lib.llm.claude import ResultMessage, query
from hooks.lib.llm.prompts import load_prompt
from hooks.lib.llm.schemas import ReviewReport
from hooks.lib.llm.workers._base import run_worker

_SYSTEM = (
    "You are backward-compatibility-checker, producing strict JSON output "
    "conforming to ReviewReport. Detect breaking changes: renamed/removed fields, "
    "changed types, altered API/schema contracts, signature changes that would "
    "break existing callers or tests. Suggest migration where relevant."
)


async def review(diff: str, scope: str = "unstaged") -> ReviewReport:
    """Run the backward-compatibility-checker agent over a diff and return a report.

    Raises:
        RuntimeError: on a non-success subtype or no terminal `ResultMessage`.
    """
    prompt = load_prompt("backward-compatibility-checker", diff=diff, scope=scope)
    return await run_worker(
        prompt=prompt,
        system=_SYSTEM,
        schema=ReviewReport,
        agent_label="backward-compatibility-checker",
        query=query,
        result_cls=ResultMessage,
    )


__all__ = ["review"]
