"""V3-safe re-export of the Claude Agent SDK with observability pre-initialized.

V3 code SHOULD import from this module rather than from `claude_agent_sdk`
directly. Two side-effects matter at import time:

1. **Observability pre-init** (Step 11, R7): the OpenInference instrumentor
   monkey-patches `claude_agent_sdk.query` and `ClaudeSDKClient` at instrument
   time. Any module that imported those symbols BEFORE instrumentation would
   hold references to the un-traced originals. Routing all V3 imports through
   this wrapper guarantees the right import order without relying on developer
   discipline.

2. **Budget auto-record** (Step 17a): the re-exported `query` is a thin async
   generator that yields the SDK's messages unchanged, but siphons every
   `ResultMessage` into `budget.record()` for the monthly $-tracker ledger.
   Recording is fail-open — any exception in the budget module is swallowed
   and never propagates back to the caller's iteration.

Usage:
    from hooks.lib.llm.claude import query, ClaudeSDKClient, ClaudeAgentOptions

If env vars or extras are missing, observability silently no-ops; the budget
module is dependency-free and always available.

`ClaudeSDKClient` is re-exported untouched in this step. Its long-lived
session pattern produces ResultMessages too, but instrumenting it requires
subclassing or patch-wrapping the instance methods — out of scope for 17a.
Callers using `ClaudeSDKClient` directly will not have their cost recorded
until a follow-up patch. (The current V3 hot path uses `query()`.)
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

# Step 1 — initialize observability BEFORE importing claude_agent_sdk.
from hooks.lib.llm.observability import init_observability

init_observability()

# Step 2 — now import (or re-import) the SDK. The instrumentor's monkey-patch
# is already in place if observability was successfully enabled.
from claude_agent_sdk import (  # noqa: E402 — order is the point
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
)
from claude_agent_sdk import query as _sdk_query  # noqa: E402

# Step 3 — bring in the budget recorder. Import after the SDK so a (hypothetical)
# circular import via observability cannot interleave.
from hooks.lib.llm.budget import record as _budget_record  # noqa: E402


def _agent_label(options: Any) -> str | None:
    """Best-effort extraction of an agent identifier from ClaudeAgentOptions.

    The SDK's options object exposes `system_prompt` (str), `agents` (dict),
    and `model` (str). For now we prefer an explicit `agent` attribute if
    callers attach one (forward-compat), otherwise fall back to the model
    name, otherwise None — `budget.record()` defaults to "unknown".
    """
    if options is None:
        return None
    explicit = getattr(options, "agent", None)
    if explicit:
        return str(explicit)
    model = getattr(options, "model", None)
    return str(model) if model else None


async def query(
    *args: Any,
    prompt: Any = None,
    options: Any = None,
    **kwargs: Any,
) -> AsyncIterator[Any]:
    """Wrap `claude_agent_sdk.query` with automatic budget recording.

    Forwards positional and keyword arguments verbatim to the SDK. For each
    `ResultMessage` yielded, calls `budget.record(msg, agent=...)` exactly
    once. The recording is best-effort and never interferes with the
    caller's iteration.
    """
    agent = _agent_label(options) if options is not None else _agent_label(
        kwargs.get("options"))

    # Pass prompt/options explicitly so the SDK's kw-only signature is honored.
    call_kwargs = dict(kwargs)
    if prompt is not None:
        call_kwargs["prompt"] = prompt
    if options is not None:
        call_kwargs["options"] = options

    async for msg in _sdk_query(*args, **call_kwargs):
        if isinstance(msg, ResultMessage):
            try:
                _budget_record(msg, agent=agent)
            except Exception:  # noqa: BLE001 — fail-open: never break iteration
                # _budget_record is already fail-open internally; this is a
                # belt-and-braces guard for any edge case it doesn't catch.
                pass
        yield msg


__all__ = [
    "ClaudeAgentOptions",
    "ClaudeSDKClient",
    "ResultMessage",
    "query",
]
