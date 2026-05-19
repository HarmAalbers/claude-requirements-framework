# Variant 3 — Full-Stack Production Platform: Overview

**Prerequisite**: Simplification plan Steps 01–07 complete (`.claude/plans/simplification/`).

**Goal**: Layer in production-grade LLM platform capabilities — observability, structured output, retrieval-augmented memory, prompt versioning, evaluation, token budgeting — one independent step at a time. Each step landing on the clean foundation Steps 01–07 created.

## Why this works only after simplification

Each integration here observes, validates, traces, or augments the workflow. If we add observability to a tangled workflow we get clean traces of a tangle. The simplification work makes the surface area legible first.

## Stack choices (validated this round)

| Component | Library | Validation source |
|---|---|---|
| Supervisor agent runtime | **PydanticAI** | [docs](https://pydantic.dev/docs/ai/core-concepts/agent/) — `Agent`, `@agent.tool`, `Hooks()` capability |
| Structured agent output | **Instructor** | [docs](https://python.useinstructor.com/) — `instructor.from_anthropic`, `response_model`, `max_retries` |
| Observability + prompt registry | **Langfuse** (self-hosted) | [Langfuse Claude Agent SDK guide](https://langfuse.com/integrations/frameworks/claude-agent-sdk) |
| Auto-tracing | **openinference-instrumentation-claude-agent-sdk** | [PyPI](https://pypi.org/project/openinference-instrumentation-claude-agent-sdk/) |
| Vector store | **Qdrant** (chosen over CosmosDB) | User already has Qdrant skills; Apple Silicon Docker support; in-memory mode |
| Memory primitives | **LlamaIndex** | `Memory` + `VectorMemoryBlock` + `FactExtractionMemoryBlock` + `StaticMemoryBlock` |
| Eval | **Ragas** | `ToolCallAccuracy`, `AgentGoalAccuracyWithReference`, `MultiTurnSample` |
| Templating | **Jinja2** | standard, no validation needed |

## Why Qdrant over CosmosDB local

The standard CosmosDB Linux emulator does not support Apple Silicon. The new vNext-preview emulator does, but adds operational complexity (vector indexing policy config, certificate handling, single-instance constraint). Qdrant: (1) the user already has Qdrant skills installed, (2) `docker run -p 6333:6333 qdrant/qdrant` works on ARM out of the box, (3) the Python client has an in-memory mode for tests, (4) it's the de-facto choice for 2026 per most vector-DB comparison reports.

## Steps in order

| # | Title | Independent? | Effort |
|---|---|---|---|
| 08 | Python LLM package scaffold | yes | 0.5 day |
| 09 | Pydantic output schemas | yes | 0.5 day |
| 10 | Instructor-wrap `code-reviewer` | depends 08, 09 | 1 day |
| 11 | Self-host Langfuse + OpenInference instrumentation | yes | 1 day |
| 12 | Mirror first prompt to Langfuse registry | depends 11 | 0.5 day |
| 13 | Qdrant local + session embed/persist | depends 08 | 1 day |
| 14 | LlamaIndex memory composition | depends 13 | 1 day |
| 15 | Ragas eval harness + golden set | depends 09, 11 | 2 days |
| 16 | Jinja2 prompt templates | depends 12 | 1 day |
| 17 | Token budget enforcement | depends 16 | 1 day |
| 18 | PydanticAI `req-supervisor` (replaces Markdown /req) | depends 08, 10, 11 | 2 days |
| 19 | Extract dialect plugin (Dutch/.NET auditors) | yes | 1 day |
| 20 | Pin `model: sonnet` on review agents | yes | 0.5 day |

Total: ~12.5 days. Parallelizable into roughly 6 wall-clock days.

## Architecture (textual summary)

```
SessionStart hook
  ├─► derive phase
  ├─► embed user prompt → Qdrant query → retrieval.json
  └─► compact briefing (<300 tok)
        │
        ▼
PydanticAI supervisor (/req)
  ├─► Hooks() capability for instrumentation
  └─► 6 handoff tools → invoke target slash command
        │
        ▼
Worker subagent (e.g. /deep-review)
  ├─► Jinja2 renders prompt with retrieval + examples
  ├─► Instructor wraps Anthropic SDK call
  ├─► Returns Pydantic ReviewReport
  └─► OpenInference auto-traces span → Langfuse
        │
        ▼
PostToolUse hook
  ├─► auto-satisfy requirement (existing)
  ├─► Ragas score on this turn
  └─► langfuse.score(trace_id, ...)
        │
        ▼
SessionEnd hook
  ├─► summarize transcript
  ├─► embed → Qdrant upsert
  └─► LlamaIndex Memory update
```

## Non-goals for V3 (deferred)

- Federated multi-tenant Langfuse (single-tenant local is enough)
- Distributed Qdrant cluster (single-node is enough)
- Custom embedding model training (use OpenAI text-embedding-3-small or local bge-m3)
- Web UI for prompt management (Langfuse provides one)
- Hardware-accelerated inference (Claude API is enough)

## Reversibility

Every step has an explicit rollback path. The simplification layer (Steps 01–07) keeps working with V3 disabled (feature flag in `requirements.yaml`).
