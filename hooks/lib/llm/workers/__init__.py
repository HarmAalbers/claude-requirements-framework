"""Structured-output workers for V3 review agents.

Each worker calls `claude_agent_sdk.query()` with native `output_format`
through the budget-recording wrapper at `hooks.lib.llm.claude`, returning
a Pydantic-validated `ReviewReport`. Workers are pure transforms: diff
in, ReviewReport out (no filesystem, no shell, `allowed_tools=[]`).

The `aggregate` agent merges N worker reports into one unified
ReviewReport with semantic deduplication and attribution.

Step 10 lands:
    - `review`     — code-reviewer worker (pilot)
    - `aggregate`  — review aggregator agent

Step 18 will add the remaining review agents using the same template.

Imports are lazy (PEP 562 `__getattr__`) so the package itself stays
importable in environments without the optional `[llm]` extras (e.g. the
framework's own test suite, which exercises the scaffold structure).
Attribute access triggers the actual import — and any missing-dep
ImportError — at the point of first use.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

__all__ = ["aggregate", "review"]


if TYPE_CHECKING:
    # Help type-checkers see the eventual attribute shape without running
    # the imports at module load time.
    from hooks.lib.llm.workers.aggregator import aggregate
    from hooks.lib.llm.workers.code_reviewer import review


def __getattr__(name: str) -> Any:
    if name == "review":
        from hooks.lib.llm.workers.code_reviewer import review as _review
        return _review
    if name == "aggregate":
        from hooks.lib.llm.workers.aggregator import aggregate as _aggregate
        return _aggregate
    raise AttributeError(
        f"module 'hooks.lib.llm.workers' has no attribute {name!r}")
