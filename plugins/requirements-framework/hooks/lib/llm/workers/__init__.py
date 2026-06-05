"""Structured-output workers for V3 review agents.

Each worker calls `claude_agent_sdk.query()` with native `output_format`
through the budget-recording wrapper at `hooks.lib.llm.claude`, returning
a Pydantic-validated `ReviewReport`. Workers are pure transforms: diff
in, ReviewReport out (no filesystem, no shell, `allowed_tools=[]`).

The `aggregate` agent merges N worker reports into one unified
ReviewReport with semantic deduplication and attribution.

Step 10 landed `review` (code-reviewer) + `aggregate`. Step 18b adds the
fan-out coordinator and two more review workers:
    - `review`          — code-reviewer worker (pilot)
    - `aggregate`       — review aggregator agent
    - `fanout_review`   — multi-worker fan-out coordinator
    - `FanoutResult`    — fan-out result (report + session_id + survivor_count)

The `solid-reviewer` and `appsec-auditor` workers are reached via their own
modules (`workers.solid_reviewer.review`, `workers.appsec_auditor.review`); the
fan-out coordinator wires them in by default.

Imports are lazy (PEP 562 `__getattr__`) so the package itself stays
importable in environments without the optional `[llm]` extras (e.g. the
framework's own test suite, which exercises the scaffold structure).
Attribute access triggers the actual import — and any missing-dep
ImportError — at the point of first use.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

__all__ = ["FanoutResult", "aggregate", "fanout_review", "review"]


if TYPE_CHECKING:
    # Help type-checkers see the eventual attribute shape without running
    # the imports at module load time.
    from hooks.lib.llm.workers.aggregator import aggregate
    from hooks.lib.llm.workers.code_reviewer import review
    from hooks.lib.llm.workers.fanout import FanoutResult, fanout_review


def __getattr__(name: str) -> Any:
    if name == "review":
        from hooks.lib.llm.workers.code_reviewer import review as _review
        return _review
    if name == "aggregate":
        from hooks.lib.llm.workers.aggregator import aggregate as _aggregate
        return _aggregate
    if name in ("fanout_review", "FanoutResult"):
        from hooks.lib.llm.workers import fanout
        return getattr(fanout, name)
    raise AttributeError(
        f"module 'hooks.lib.llm.workers' has no attribute {name!r}")
