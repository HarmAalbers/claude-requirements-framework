"""Structured-output worker around the `silent-failure-hunter` agent prompt.

Step 18c. Pure transform: diff in, ReviewReport out, `allowed_tools=[]`.
Keeps its own `query`/`ResultMessage` imports for test mock-patching (see
`_base.run_worker` docstring).
"""

from hooks.lib.llm.claude import ResultMessage, query
from hooks.lib.llm.prompts import load_prompt
from hooks.lib.llm.schemas import ReviewReport
from hooks.lib.llm.workers._base import run_worker

_SYSTEM = (
    "You are silent-failure-hunter, producing strict JSON output conforming to "
    "ReviewReport. Hunt error handling that suppresses, swallows, or hides "
    "failures: bare excepts, ignored return codes, fallbacks without logging, "
    "unactionable error messages. Quality over quantity."
)


async def review(diff: str, scope: str = "unstaged") -> ReviewReport:
    """Run the silent-failure-hunter agent over a diff and return a typed report.

    Raises:
        RuntimeError: on a non-success subtype or no terminal `ResultMessage`.
    """
    prompt = load_prompt("silent-failure-hunter", diff=diff, scope=scope)
    return await run_worker(
        prompt=prompt,
        system=_SYSTEM,
        schema=ReviewReport,
        agent_label="silent-failure-hunter",
        query=query,
        result_cls=ResultMessage,
    )


__all__ = ["review"]
