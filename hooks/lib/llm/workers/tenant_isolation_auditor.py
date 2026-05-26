"""Structured-output worker around the `tenant-isolation-auditor` agent prompt.

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
    "You are tenant-isolation-auditor, producing strict JSON output conforming "
    "to ReviewReport. In multi-tenant code, hunt cross-tenant data leakage: "
    "DB queries missing a tenant filter, caches without tenant-scoped keys, "
    "global filter bypasses, cross-tenant background jobs, and shared singletons "
    "holding tenant state. Report only when the change touches such code."
)


async def review(diff: str, scope: str = "unstaged") -> ReviewReport:
    """Run the tenant-isolation-auditor agent over a diff and return a report.

    Raises:
        RuntimeError: on a non-success subtype or no terminal `ResultMessage`.
    """
    prompt = load_prompt("tenant-isolation-auditor", diff=diff, scope=scope)
    return await run_worker(
        prompt=prompt,
        system=_SYSTEM,
        schema=ReviewReport,
        agent_label="tenant-isolation-auditor",
        query=query,
        result_cls=ResultMessage,
    )


__all__ = ["review"]
