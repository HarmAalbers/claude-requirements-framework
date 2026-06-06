# Step 18 — PydanticAI `req-supervisor` (replaces Markdown /req)

> **⚠️ SUPERSEDED IN PART by [ADR-016](../../../docs/adr/ADR-016-v3-claude-agent-sdk-substrate.md) (2026-05-22).**
>
> PydanticAI is **no longer load-bearing** for this step. The two motivations that originally selected it have both weakened:
> - `@agent.tool` handoff binding → native `output_format` with `HandoffResult.target` as a `Literal` does the same job at the substrate level.
> - `Hooks()` capability for tracing → the Agent SDK's PreToolUse/PostToolUse hooks (Python callables) are more granular and don't need a wrapper framework.
>
> Revised target: **a thin Python script** (~30 lines) that calls `query(output_format=HandoffResult.model_json_schema())`, reads the result, and prints/invokes the chosen handoff. The supervisor collapses from "PydanticAI agent with custom provider adapter" to "small async function." Spike-validated end-to-end.
>
> The body below preserves the original PydanticAI-based design as a historical reference. It will be rewritten when this step is executed.

## Observability requirement (added 2026-05-22, Langfuse skill audit)

When this step is rewritten, the supervisor MUST own the Langfuse session/tag boundary for a review run:

- The supervisor generates a `session_id` (uuid4) per fan-out and propagates it to every worker call.
- Each worker call enters an OpenInference `using_attributes(session_id=..., tags=["worker:<name>", "feature:review"])` context (or sets `langfuse.session.id` / `langfuse.tags` OTel attributes directly on the active span) so that the N workers + 1 aggregator appear as one filterable session in the Langfuse UI.
- Without this, the existing Step 11 instrumentation produces unrelated AGENT-level traces that can't be grouped after the fact.

**Why here, not Step 11:** Step 11 only sees a single `query()` call — it has no notion of a "review run." The supervisor is the first layer that knows N workers belong together, so session-binding is its responsibility.

**Reference:** `~/.claude/skills/langfuse/references/instrumentation.md` §4 ("Discover Additional Context Needs"). Audit performed 2026-05-22 against the Step 11/12 implementation.

## Goal

Replace the Markdown `/req` command (from simplification Step 05) with a PydanticAI agent that owns the workflow routing. Adds typed handoff tools and `Hooks()` capability for instrumentation.

## Why now

Everything else is in place: schemas (09), Instructor wrapper (10), Langfuse (11–12), retrieval (13–14), eval (15), templating (16), budgeting (17). The supervisor consolidates them.

## Files touched

- `hooks/lib/llm/supervisor.py` (populated)
- `plugins/requirements-framework/commands/req.md` — replace body with a thin Python invocation
- `hooks/lib/llm/handoffs.py` (new — each `handoff_to_X` tool)

## Validated APIs

### Agent and tools
From [pydantic-ai docs](https://github.com/pydantic/pydantic-ai/blob/main/docs/tools.md):
```python
from pydantic_ai import Agent, RunContext

agent = Agent('openai:gpt-4o', deps_type=str, instructions="...")

@agent.tool
def get_player_name(ctx: RunContext[str]) -> str:
    return ctx.deps

result = agent.run_sync('My guess is 4', deps='Anne')
```

### Hooks capability
From [pydantic-ai capabilities docs](https://github.com/pydantic/pydantic-ai/blob/main/docs/capabilities.md):
```python
from pydantic_ai import Agent, ModelRequestContext, RunContext
from pydantic_ai.capabilities import Hooks

hooks = Hooks()

@hooks.on.before_model_request
async def log_request(ctx: RunContext[None], request_context: ModelRequestContext) -> ModelRequestContext:
    agent_name = ctx.agent.name if ctx.agent else 'unknown'
    print(f'[{agent_name}] Sending {len(request_context.messages)} messages')
    return request_context

agent = Agent('openai:gpt-5.2', name='my_agent', capabilities=[hooks])
```

### Dependency injection
```python
from dataclasses import dataclass
@dataclass
class MyDeps:
    api_key: str
    http_client: httpx.AsyncClient

agent = Agent('openai:gpt-4o', deps_type=MyDeps)

@agent.tool
async def fetch_data(ctx: RunContext[MyDeps], query: str) -> str:
    ...
```

## Implementation

```python
# hooks/lib/llm/supervisor.py
"""PydanticAI supervisor — owns workflow routing."""
from dataclasses import dataclass
from pydantic_ai import Agent, RunContext, ModelRequestContext
from pydantic_ai.capabilities import Hooks
from hooks.lib.llm.schemas import HandoffResult


@dataclass
class WorkflowDeps:
    branch: str
    phase: str
    unsatisfied: list[str]
    retrieved: list[dict]   # from Qdrant


_hooks = Hooks()

@_hooks.on.before_model_request
async def _log(ctx: RunContext[WorkflowDeps],
               request_context: ModelRequestContext) -> ModelRequestContext:
    # Langfuse trace metadata
    print(f"[supervisor] phase={ctx.deps.phase} "
          f"retrieved={len(ctx.deps.retrieved)} hits")
    return request_context


supervisor = Agent(
    "claude-sonnet-4-6",  # supervisor is routing — sonnet is enough
    deps_type=WorkflowDeps,
    output_type=HandoffResult,
    system_prompt=(
        "You are the requirements-framework workflow router. "
        "Given the current phase in ctx.deps.phase, choose exactly one "
        "handoff and return a HandoffResult with target + rationale. "
        "Do not perform the work yourself — only route."
    ),
    capabilities=[_hooks],
)


@supervisor.tool
async def handoff_to_design(ctx: RunContext[WorkflowDeps]) -> str:
    """Use when phase is 'design' — needs brainstorming."""
    return "/brainstorm"

@supervisor.tool
async def handoff_to_plan(ctx: RunContext[WorkflowDeps]) -> str:
    """Use when phase is 'plan' — needs arch-review."""
    return "/arch-review"

@supervisor.tool
async def handoff_to_implement(ctx: RunContext[WorkflowDeps]) -> str:
    """Use when phase is 'implement'."""
    return "/execute-plan"

@supervisor.tool
async def handoff_to_review(ctx: RunContext[WorkflowDeps]) -> str:
    """Use when phase is 'review' — needs deep-review."""
    return "/deep-review"

@supervisor.tool
async def handoff_to_refactor(ctx: RunContext[WorkflowDeps]) -> str:
    """Use for explicit refactor orchestration."""
    return "/refactor-orchestrate"

@supervisor.tool
async def handoff_to_ship(ctx: RunContext[WorkflowDeps]) -> str:
    """Use when all session-scoped requirements are satisfied."""
    return "/codex-review then open PR"
```

### Entry script
```python
# hooks/lib/llm/req_cli.py
"""Invoked by /req command. Loads state, runs supervisor, prints handoff."""
import json, sys
from pathlib import Path
import asyncio
from hooks.lib.llm.supervisor import supervisor, WorkflowDeps
from hooks.lib.derive_phase import derive_phase

def main():
    branch = Path(sys.argv[1] if len(sys.argv) > 1 else ".git/HEAD").read_text().strip().split("/")[-1]
    state = json.loads(Path(f".git/requirements/{branch}.json").read_text() or "{}")
    retrieval = json.loads(Path(f".git/requirements/retrieval-{branch}.json").read_text() or '{"hits":[]}')
    deps = WorkflowDeps(
        branch=branch,
        phase=derive_phase(state),
        unsatisfied=[k for k, v in state.get("requirements", {}).items()
                     if not v.get("satisfied")],
        retrieved=retrieval["hits"],
    )
    result = asyncio.run(supervisor.run("Route this session", deps=deps))
    print(f"Phase: {deps.phase}\nInvoking: {result.output.target}\nWhy: {result.output.rationale}")

if __name__ == "__main__":
    main()
```

### Update /req command (replaces simplification Step 05 markdown)
```markdown
---
name: req
description: "Workflow conductor (PydanticAI supervisor). Run with no args."
argument-hint: "[phase]"
allowed-tools: ["Bash"]
git_hash: uncommitted
---

# Req Conductor

Run:
```bash
python -m hooks.lib.llm.req_cli "$ARGUMENTS"
```

Then invoke the command the script prints.
```

## Example

```bash
$ /req
[supervisor] phase=review retrieved=2 hits
Phase: review
Invoking: /deep-review
Why: Session has pre_pr_review unsatisfied; 2 similar prior reviews suggest start here.
```

## Acceptance — revised for the ADR-016 thin-Python scope

- [x] `supervisor.route(phase, unsatisfied)` returns a `HandoffResult` with `target` in the 7-entry literal — proved by `tests/test_supervisor.py::test_route_returns_handoff_result` (mocked) and the 7-scenario smoke (`hooks/lib/llm/_spikes/v3_supervisor_smoke.py`)
- [x] Empty `unsatisfied` renders as `(none)` in the prompt so the LLM does not see an empty bracket and improvise — `test_empty_unsatisfied_renders_as_none`
- [x] `allowed_tools=[]` keeps the supervisor a pure transform — `test_route_passes_output_format_and_no_tools`
- [x] `options.agent = "req-supervisor"` so the budget ledger labels the call — `test_route_labels_options_with_agent_name`
- [x] `error_max_structured_output_retries` surfaces as a `RuntimeError` — `test_route_raises_on_error_subtype`
- [x] OpenInference auto-instrumentation produces a span for the supervisor call (Step 11 boundary) — verifiable via the smoke spike with `LANGFUSE_*` set
- [ ] **Deferred**: Markdown `/req` replacement. Per scoping decision 2026-05-22, the deterministic command stays; the supervisor is purely additive infrastructure ready to be wired in when Step 13 (retrieval) lands.
- [ ] **Deferred**: Latency-guard warning (>2s). Land with Step 17b token-budget enforcement.
- [ ] **Deferred** (Future Step 18 expansion): supervisor owns review fan-out and Langfuse session/tag boundary per the "Observability requirement" section above.

## Landing notes (2026-05-22)

Step 18 landed as **2 stacked stg patches** on `refactor/step-08-llm-package-scaffold`:

1. `step-18-extend-handoff-targets` — `HandoffResult.target` Literal grows 6 → 7 (adds `writing-plans`) + 2 new schema tests + the Observability-requirement plan-doc note. 22/22 schema tests green.
2. `step-18-supervisor-module` — `hooks/lib/llm/supervisor.py` (~30-line `route` function) + `prompts/req-supervisor.txt` + 11 mocked-SDK tests + a 7-scenario smoke spike. 11/11 supervisor tests green.

Scope honored from the user's 2026-05-22 decision matrix:
- **Supervisor function only** — no `/req` rewrite, no `/deep-review` rewiring.
- **Inputs: phase + unsatisfied list** — minimal MVP, expansion-ready (kwargs structure).
- **Schema extended** — `writing-plans` added to fix the 6 vs 7 mismatch with the Markdown `/req` table.

130/130 V3 tests pass (11 supervisor + 22 schemas + 12 prompts + 13 code-reviewer + 12 aggregator + 12 obs + 39 budget + 9 wrapper).

## Rollback

`git revert <commit>` restores the Markdown `/req`. The Python supervisor stays in the package but is unused.

## Effort

2 days

## Depends on

Steps 08, 09, 10, 11, 14 (deps + schemas + Instructor + Langfuse + retrieval).

## Honest scope note

PydanticAI's `Hooks()` fires only on **model-request boundaries**. For tool-call-level events (handoff_to_X calls), use the `event_stream_handler` parameter on `agent.run_stream(..., event_stream_handler=...)`. We rely on OpenInference auto-instrumentation for tool spans, not PydanticAI's event handler — simpler and consistent across Instructor + PydanticAI calls.
