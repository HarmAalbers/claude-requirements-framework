"""Shared worker mechanics for structured-output Agent SDK calls.

Step 18b preparatory refactor. `code_reviewer.py` and `aggregator.py` (and the
supervisor) all repeat the same skeleton: build `ClaudeAgentOptions` with a
json_schema `output_format`, label the call for the budget ledger, run
`query()`, and validate the terminal `ResultMessage` into a Pydantic model.
`run_worker()` owns that skeleton once.

Two deliberate design constraints (see ADR-017 + arch-review):

    Callers pass `query` and `result_cls` in — they are NOT imported here.
    The worker modules keep their own `from ...claude import query,
    ResultMessage` so that `unittest.mock.patch.object(worker_module,
    "query", ...)` intercepts the call. If `_base` imported them, the
    worker's own namespace would be bypassed and existing tests would
    silently hit the real SDK.

    `run_worker()` does session/tag binding NOWHERE. Observability session
    binding is the fan-out coordinator's responsibility (ADR-017 §2). A
    worker — or this shared helper — must not enter a `review_session`.

Generic over the output schema (`schema: type[T]`) and `max_turns` so the same
helper serves review workers (ReviewReport, max_turns=5) and, later, the
supervisor (HandoffResult, max_turns=3) without a second extraction.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import Any, TypeVar

from pydantic import BaseModel

from hooks.lib.llm.claude import ClaudeAgentOptions

T = TypeVar("T", bound=BaseModel)


def build_options(
    *,
    system: str,
    schema: type[BaseModel],
    agent_label: str,
    max_turns: int,
) -> ClaudeAgentOptions:
    """Build the `ClaudeAgentOptions` shape every structured-output worker uses.

    `output_format` and `agent` are set via `setattr` because their presence in
    the dataclass signature varies across SDK minor versions, and `agent` is our
    extension for the budget recorder's label (see hooks/lib/llm/claude.py
    `_agent_label`). The `try/except (AttributeError, TypeError)` around `agent`
    is preserved: if `ClaudeAgentOptions` becomes frozen in a future SDK release,
    budget entries fall back to the model name rather than crashing.
    """
    options = ClaudeAgentOptions(
        system_prompt=system,
        allowed_tools=[],
        max_turns=max_turns,
    )
    setattr(options, "output_format", {
        "type": "json_schema",
        "schema": schema.model_json_schema(),
    })
    try:
        setattr(options, "agent", agent_label)
    except (AttributeError, TypeError):
        pass
    return options


async def run_worker(
    *,
    prompt: str,
    system: str,
    schema: type[T],
    agent_label: str,
    error_prefix: str,
    query: Callable[..., AsyncIterator[Any]],
    result_cls: type,
    max_turns: int = 5,
) -> T:
    """Run one structured-output agent call and validate the terminal result.

    Args:
        prompt: the rendered user prompt.
        system: the system prompt.
        schema: the Pydantic model to validate `structured_output` into AND to
            emit as the json_schema `output_format`.
        agent_label: budget-ledger label (e.g. "code-reviewer").
        error_prefix: prefix for RuntimeError messages — MUST match what the
            caller's tests assert verbatim (e.g. "code-reviewer").
        query: the SDK `query` callable, passed by the caller so mock-patching
            the caller's module namespace works (see module docstring).
        result_cls: the terminal-message type (`ResultMessage`), passed by the
            caller for the same mock-patching reason.
        max_turns: SDK turn cap; output_format needs >=2 for internal retry.

    Raises:
        RuntimeError: if the terminal `ResultMessage` reports a non-success
            subtype (e.g. `error_max_structured_output_retries`), or if the
            stream ends with no terminal `ResultMessage` observed. NEVER returns
            None on failure — the fan-out survivor filter depends on this.
    """
    options = build_options(
        system=system,
        schema=schema,
        agent_label=agent_label,
        max_turns=max_turns,
    )
    async for msg in query(prompt=prompt, options=options):
        if isinstance(msg, result_cls):
            if msg.subtype == "success" and msg.structured_output:
                return schema.model_validate(msg.structured_output)
            raise RuntimeError(
                f"{error_prefix} failed: subtype={msg.subtype!r}")
    raise RuntimeError(f"{error_prefix}: no ResultMessage observed")


__all__ = ["build_options", "run_worker"]
