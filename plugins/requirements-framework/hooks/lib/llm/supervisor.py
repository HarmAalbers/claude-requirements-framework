"""Workflow router — picks one handoff target via output_format=HandoffResult.

Step 18. Thin Python script per ADR-016's supersession of the
PydanticAI-based design: the SDK's native `output_format` plus the
`HandoffResult` schema provides typed routing without any wrapper
framework. ~30 lines of actual logic.

Inputs:
    phase        — string from `hooks/lib/derive_phase.py` (one of the
                   configured workflow phase names: design, plan-write,
                   plan-validate, implement, review, refactor, ship by
                   default; a project may reorder/rename/add phases).
    unsatisfied  — list of unsatisfied requirement names.
    phases       — optional list of phase descriptors ({name, description,
                   skill, ...}). When omitted, the zero-config menu from
                   `config.RequirementsConfig.WORKFLOW_DEFAULTS` is used so the
                   router mirrors the project's own phase vocabulary.

Output: HandoffResult (target = a configured phase NAME, rationale: str).
The target is validated against the active phase-name set and clamped to the
input `phase` if the model hallucinates an out-of-vocabulary value, so a bad
routing decision never propagates.

Scope notes:
    - The Markdown /req command stays the deterministic default in
      this step; the supervisor is purely additive infrastructure
      ready to be wired in once Step 13 (retrieval) adds reasoning
      context that derive_phase cannot produce.
    - allowed_tools=[] keeps the supervisor a pure transform.
    - The agent label "req-supervisor" propagates to the Step 17a
      budget ledger via the wrapper at hooks.lib.llm.claude.
    - User prompt template lives in `prompts/req-supervisor.md.j2`
      and is loaded through the Step 12 PromptLoader so it can be
      iterated in the Langfuse registry without code changes.

Design: .claude/plans/variant3/18-pydanticai-req-supervisor.md
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Optional

from hooks.lib.llm.prompts import load_prompt
from hooks.lib.llm.schemas import HandoffResult

# The claude_agent_sdk wrapper is imported lazily inside route()/_build_options
# so this module stays import-safe WITHOUT the optional `[llm]` SDK installed
# (mirrors the `llm` scaffold contract). The pure helpers below — `_default_phases`,
# `_phase_names`, `_resolve_target` — are therefore unit-testable with no SDK.
if TYPE_CHECKING:  # pragma: no cover — typing only, never imported at runtime.
    from hooks.lib.llm.claude import ClaudeAgentOptions

LOG = logging.getLogger("requirements.supervisor")


_SYSTEM = (
    "You are the requirements-framework workflow router. Return strict "
    "JSON conforming to HandoffResult. Pick exactly one target phase NAME "
    "from the configured workflow phases — do not invoke it."
)


def _default_phases() -> list[dict[str, Any]]:
    """Zero-config routing menu: the WORKFLOW_DEFAULTS phase descriptors.

    Imported lazily from ``config`` so the supervisor stays import-light and
    has no hard dependency on the config package at module-load time. This is a
    class-level constant lookup — NO project I/O. Fail-open: returns ``[]`` if
    the import or attribute access ever fails, which the prompt and clamp both
    tolerate.
    """
    try:
        from hooks.lib.config import RequirementsConfig

        return [dict(p) for p in RequirementsConfig.WORKFLOW_DEFAULTS["phases"]]
    except Exception:  # noqa: BLE001 — fail-open: never break routing on import.
        return []


def _phase_names(phases: list[Any]) -> set[str]:
    """The set of valid phase NAMES in *phases*. Defensive against schema drift."""
    names: set[str] = set()
    for entry in phases:
        name = entry.get("name") if isinstance(entry, dict) else None
        if isinstance(name, str) and name:
            names.add(name)
    return names


def _resolve_target(target: str, phases: list[Any], fallback_phase: str) -> str:
    """Return *target* if it names a configured phase, else *fallback_phase*.

    A hallucinated target — one the model invented that is not in the active
    phase vocabulary — is clamped to the input phase so a bad routing decision
    never propagates downstream. Pure, synchronous, and unit-testable without
    any LLM call.
    """
    if target in _phase_names(phases):
        return target
    LOG.warning(
        "req-supervisor: out-of-vocab target %r clamped to input phase %r",
        target,
        fallback_phase,
    )
    return fallback_phase


def _build_options() -> "ClaudeAgentOptions":
    from hooks.lib.llm.claude import ClaudeAgentOptions

    options = ClaudeAgentOptions(
        system_prompt=_SYSTEM,
        allowed_tools=[],
        max_turns=3,
    )
    # `output_format` and `agent` are set dynamically — same rationale as
    # in workers/code_reviewer.py: the dataclass signature varies across
    # SDK minor versions, and `agent` is our extension for the budget
    # recorder's label (see hooks/lib/llm/claude.py `_agent_label`).
    setattr(options, "output_format", {
        "type": "json_schema",
        "schema": HandoffResult.model_json_schema(),
    })
    try:
        setattr(options, "agent", "req-supervisor")
    except (AttributeError, TypeError):
        pass
    return options


async def route(
    phase: str,
    unsatisfied: list[str],
    phases: Optional[list[Any]] = None,
) -> HandoffResult:
    """Pick the next handoff target for the current session state.

    Args:
        phase: deterministic phase from `derive_phase.py`.
        unsatisfied: list of unsatisfied requirement names (may be empty —
            renders as the literal "(none)" in the prompt so the LLM
            doesn't see an empty bracket and improvise).
        phases: optional list of phase descriptors that define the routing
            vocabulary and menu. When ``None``, the zero-config
            ``WORKFLOW_DEFAULTS`` phases are used.

    Returns:
        HandoffResult whose ``target`` is one of the configured phase names.
        A hallucinated out-of-vocabulary target is clamped to the input
        ``phase`` (fail-open) rather than propagated.

    Raises:
        RuntimeError: if the SDK reports
            `error_max_structured_output_retries` (the agent could not
            produce valid JSON within the SDK's internal retry cap) or if
            no terminal `ResultMessage` is observed.
    """
    from hooks.lib.llm.claude import ResultMessage, query

    if phases is None:
        phases = _default_phases()
    unsat_repr = ", ".join(unsatisfied) if unsatisfied else "(none)"
    prompt = load_prompt(
        "req-supervisor", phase=phase, unsatisfied=unsat_repr, phases=phases
    )
    options = _build_options()

    async for msg in query(prompt=prompt, options=options):
        if isinstance(msg, ResultMessage):
            if msg.subtype == "success" and msg.structured_output:
                result = HandoffResult.model_validate(msg.structured_output)
                result.target = _resolve_target(result.target, phases, phase)
                return result
            raise RuntimeError(
                f"req-supervisor failed: subtype={msg.subtype!r}")
    raise RuntimeError("req-supervisor: no ResultMessage observed")


__all__ = ["route"]
