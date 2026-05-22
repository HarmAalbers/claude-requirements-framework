"""Workflow router — picks one handoff target via output_format=HandoffResult.

Step 18. Thin Python script per ADR-016's supersession of the
PydanticAI-based design: the SDK's native `output_format` plus the
`Literal` target type on HandoffResult provides typed routing without
any wrapper framework. ~30 lines of actual logic.

Inputs:
    phase        — string from `hooks/lib/derive_phase.py` (one of
                   design, plan-write, plan-validate, implement,
                   review, refactor, ship).
    unsatisfied  — list of unsatisfied requirement names.

Output: HandoffResult (target ∈ 7 literals, rationale: str).

Scope notes:
    - The Markdown /req command stays the deterministic default in
      this step; the supervisor is purely additive infrastructure
      ready to be wired in once Step 13 (retrieval) adds reasoning
      context that derive_phase cannot produce.
    - allowed_tools=[] keeps the supervisor a pure transform.
    - The agent label "req-supervisor" propagates to the Step 17a
      budget ledger via the wrapper at hooks.lib.llm.claude.
    - User prompt template lives in `prompts/req-supervisor.txt`
      and is loaded through the Step 12 PromptLoader so it can be
      iterated in the Langfuse registry without code changes.

Design: .claude/plans/variant3/18-pydanticai-req-supervisor.md
"""

from __future__ import annotations

from hooks.lib.llm.claude import ClaudeAgentOptions, ResultMessage, query
from hooks.lib.llm.prompts import load_prompt
from hooks.lib.llm.schemas import HandoffResult


_SYSTEM = (
    "You are the requirements-framework workflow router. Return strict "
    "JSON conforming to HandoffResult. Pick exactly one target — do not "
    "invoke it."
)


def _build_options() -> ClaudeAgentOptions:
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


async def route(phase: str, unsatisfied: list[str]) -> HandoffResult:
    """Pick the next handoff target for the current session state.

    Args:
        phase: deterministic phase from `derive_phase.py`.
        unsatisfied: list of unsatisfied requirement names (may be empty —
            renders as the literal "(none)" in the prompt so the LLM
            doesn't see an empty bracket and improvise).

    Returns:
        HandoffResult with target in the 7-target literal vocabulary and
        a short rationale string.

    Raises:
        RuntimeError: if the SDK reports
            `error_max_structured_output_retries` (the agent could not
            produce valid JSON within the SDK's internal retry cap) or if
            no terminal `ResultMessage` is observed.
    """
    unsat_repr = ", ".join(unsatisfied) if unsatisfied else "(none)"
    prompt = load_prompt("req-supervisor").format(
        phase=phase, unsatisfied=unsat_repr)
    options = _build_options()

    async for msg in query(prompt=prompt, options=options):
        if isinstance(msg, ResultMessage):
            if msg.subtype == "success" and msg.structured_output:
                return HandoffResult.model_validate(msg.structured_output)
            raise RuntimeError(
                f"req-supervisor failed: subtype={msg.subtype!r}")
    raise RuntimeError("req-supervisor: no ResultMessage observed")


__all__ = ["route"]
