# Variant 3 — Full-Stack Production Platform: Overview

> **2026-05-22 — Substrate pivot.** This overview has been rewritten to reflect [ADR-016](../../../docs/adr/ADR-016-v3-claude-agent-sdk-substrate.md). The original plan assumed Instructor + Anthropic SDK + PydanticAI; the revised plan rides on `claude-agent-sdk` with native `output_format` and agent-based aggregation. Individual step plans (10, 11, 13, 15, 18) are partially superseded — their headers point at ADR-016, and their bodies will be rewritten when each step executes.

**Prerequisite**: Simplification plan Steps 01–07 complete (`.claude/plans/simplification/`).

**Goal**: Layer in production-grade LLM platform capabilities — observability, structured output, retrieval-augmented memory, prompt versioning, evaluation, token budgeting — one independent step at a time, all riding on the Claude Agent SDK substrate (no separate Anthropic API key required).

## Why this works only after simplification

Each integration here observes, validates, traces, or augments the workflow. If we add observability to a tangled workflow we get clean traces of a tangle. The simplification work makes the surface area legible first.

## Substrate (revised 2026-05-22 — see ADR-016)

V3 is built on **Claude Agent SDK** (`claude-agent-sdk`, Python). All model calls go through the SDK; the SDK subprocess spawns the bundled `claude` CLI, which inherits Claude Max auth from `~/.claude/`. No Anthropic API key is needed or used.

```python
# The canonical V3 call shape:
from claude_agent_sdk import query, ClaudeAgentOptions, ResultMessage
from hooks.lib.llm.schemas import ReviewReport  # Step 09

async for msg in query(
    prompt=...,
    options=ClaudeAgentOptions(
        system_prompt=...,
        model="claude-sonnet-4-6",
        allowed_tools=[],   # no tool use; pure LLM call
        max_turns=5,        # output_format needs ≥2 turns for internal retry
        output_format={
            "type": "json_schema",
            "schema": ReviewReport.model_json_schema(),
        },
    ),
):
    if isinstance(msg, ResultMessage):
        if msg.subtype == "success":
            return ReviewReport.model_validate(msg.structured_output)
        # subtype == "error_max_structured_output_retries" — handle failure
```

That call shape is the V3 worker primitive. Schemas (Step 09) define the contracts.

## Stack choices (validated 2026-05-22)

| Layer | Library / approach | Validation source |
|---|---|---|
| Substrate | **`claude-agent-sdk` v0.2.82+** | Validated empirically under Max auth; see `hooks/lib/llm/_spikes/` |
| Structured output | **SDK-native `output_format`** with Pydantic `.model_json_schema()` | [Anthropic docs — Structured outputs](https://code.claude.com/docs/en/agent-sdk/structured-outputs) |
| Worker aggregation | **Aggregator agent** (LLM-based semantic dedup), not Python | Spike data — mechanical dedup keys are both too coarse and too fine |
| Supervisor runtime | Thin Python script: `query(output_format=HandoffResult)` | Spike-validated — replaces PydanticAI |
| Batch eval call site | **`ClaudeSDKClient`** persistent connection (Step 15) | [SDK README](https://github.com/anthropics/claude-agent-sdk-python) — amortizes subprocess startup across many calls |
| Observability + prompt registry | **Langfuse** (self-hosted) | [Langfuse Claude Agent SDK guide](https://langfuse.com/integrations/frameworks/claude-agent-sdk) |
| Auto-tracing | **openinference-instrumentation-claude-agent-sdk** | Already declared in `pyproject.toml` `[llm]` extras |
| Vector store | **Qdrant** (Apple Silicon native) | User has skills; in-memory mode for tests |
| Embeddings | **`sentence-transformers` (`BAAI/bge-small-en-v1.5`)** running locally | No external embedding API required; Max-friendly |
| Memory primitives | **LlamaIndex** | `Memory` + `VectorMemoryBlock` + `FactExtractionMemoryBlock` + `StaticMemoryBlock` |
| Eval | **Ragas** with Agent SDK as judge model | Custom Ragas LLM adapter wrapping `ClaudeSDKClient` |
| Templating | **Jinja2** | standard, no validation needed |

**No longer load-bearing** (removed or made optional):
- `instructor` — replaced by SDK-native `output_format`
- `anthropic` SDK direct usage — replaced by `claude-agent-sdk`
- `pydantic-ai` — replaced by thin Python supervisor

The current `pyproject.toml` `[llm]` extras still list `instructor`, `anthropic`, and `pydantic-ai` — these must be replaced with `claude-agent-sdk` + `sentence-transformers` + `onnxruntime` before any further V3 implementation work (a follow-up patch).

## Why Qdrant over CosmosDB

Unchanged from the original plan: the standard CosmosDB Linux emulator does not support Apple Silicon. Qdrant works on ARM out of the box, has an in-memory mode for tests, and the user already has skills.

## Steps in (revised) order

The original ordering put observability (Step 11) and budgeting (Step 17) in the middle. The 2026-05-22 spike revealed 7x latency variance on identical inputs, making "build observability first" the correct ordering.

| # | Title | Status | Notes |
|---|---|---|---|
| 08 | Python LLM package scaffold | ✅ done (7da31cd + cce6eaa) | Stacked patches on `refactor/step-08-llm-package-scaffold`. `pyproject.toml` `[llm]` extras need revision per ADR-016 |
| 09 | Pydantic output schemas | ✅ done (f0bdd82) | Substrate-agnostic; survives the pivot unchanged |
| 11 | Self-host Langfuse + Agent SDK instrumentation | ⬜ **NEXT** | Priority bumped — must precede workers due to latency variance |
| 17 | Token budget enforcement | ⬜ | Bumped — June-15 SDK credit pool makes cost predictability essential before workers run frequently |
| 10 | Agent SDK `output_format` wrapper + aggregator agent (pilot on `code-reviewer`) | ⬜ | Body needs full rewrite per ADR-016 — no Instructor, agent-based aggregation |
| 18 | Thin Python supervisor (replaces Markdown /req from 05) | ⬜ | Body needs rewrite — PydanticAI no longer used |
| 13 | Qdrant local + local sentence-transformers embedding | ⬜ | Body needs rewrite — no OpenAI embeddings; use `BAAI/bge-small-en-v1.5` locally |
| 14 | LlamaIndex memory composition | ⬜ | |
| 15 | Ragas eval harness + golden set (via `ClaudeSDKClient`) | ⬜ | Body needs rewrite — judge model is Agent SDK with persistent client; critical before Step 20 |
| 12 | Mirror first prompt to Langfuse registry | ⬜ | Depends on Step 11 |
| 16 | Jinja2 prompt templates | ⬜ | |
| 19 | Extract dialect plugin (Dutch/.NET auditors) | ⬜ | Independent; can land at any time |
| 20 | Pin `model: sonnet` on review agents | ⬜ | Gated on Step 15 eval data |

Total: ~12.5 days estimated. Parallelizable into roughly 6 wall-clock days. The Step-11-first ordering trades a small amount of "feature visibility early" for much better confidence in subsequent steps.

## Architecture (revised textual summary)

```
SessionStart hook
  ├─► derive phase (Step 03, simplification)
  ├─► embed user prompt via local sentence-transformers → Qdrant query → retrieval.json
  └─► compact briefing (<300 tok, Step 01 simplification)
        │
        ▼
/req conductor (thin Python: query(output_format=HandoffResult))
  ├─► reads retrieval + phase
  └─► returns HandoffResult with target ∈ {brainstorm, arch-review, execute-plan,
                                            deep-review, refactor-orchestrate, ship}
        │
        ▼
Worker calls in parallel via asyncio.gather([query(output_format=ReviewReport), ...])
  ├─► each worker:
  │     - system_prompt = agent.md body
  │     - output_format = ReviewReport schema
  │     - allowed_tools = [] (pure LLM, no tool use)
  │     - max_turns = 5 (SDK needs budget for internal retry)
  ├─► OpenInference auto-traces span → Langfuse (Step 11)
  └─► returns list[ReviewReport]
        │
        ▼
Aggregator agent call: query(output_format=ReviewReport)
  ├─► system_prompt: "merge semantic duplicates, keep distinct issues, rank, summarize"
  ├─► input: list[ReviewReport] as JSON in user prompt
  └─► returns unified ReviewReport with narrative summary
        │
        ▼
PostToolUse hook
  ├─► auto-satisfy requirement (existing)
  ├─► Ragas score on this turn (Step 15, via ClaudeSDKClient)
  └─► langfuse.score(trace_id, ...) (Step 11)
        │
        ▼
SessionEnd hook
  ├─► summarize transcript
  ├─► local sentence-transformers embed → Qdrant upsert
  ├─► LlamaIndex Memory update (Step 14)
  └─► flush Langfuse trace
```

## Cost envelope (post-June-15-2026 SDK credit pool)

Per [Anthropic's June 15, 2026 billing change](https://platform.claude.com/), Agent SDK usage migrates to a separate "Agent SDK credit pool" — $100/mo for Max 5x, $200/mo for Max 20x. These credits do not commingle with interactive Claude.ai/Claude Code usage and expire monthly.

Approximate V3 cost per `/deep-review` (Sonnet rates, per spike data):

| Operation | Approx cost |
|---|---|
| Supervisor call | ~$0.02 |
| 5 worker calls (parallel) | ~$0.20 |
| Aggregator call | ~$0.06 |
| **One `/deep-review`** | **~$0.30 typical, up to ~$1.00 worst-case on a large diff** |

A Max 5x user could run ~100–300 `/deep-review` invocations per month within the SDK credit pool. Step 17 (token budgeting) enforces this envelope explicitly.

## Non-goals for V3 (unchanged)

- Federated multi-tenant Langfuse (single-tenant local is enough)
- Distributed Qdrant cluster (single-node is enough)
- Custom embedding model training (use `BAAI/bge-small-en-v1.5` locally)
- Web UI for prompt management (Langfuse provides one)
- Hardware-accelerated inference (Apple Silicon CPU is enough for embeddings; Sonnet handles the model side)
- Direct Anthropic API access — explicitly out of scope per ADR-016

## Reversibility

Every step has an explicit rollback path. The simplification layer (Steps 01–07) keeps working with V3 disabled (feature flag in `requirements.yaml`). The substrate pivot itself is reversible: ADR-016 is a documentation change + a pending pyproject revision; no V3 code yet depends on the new substrate beyond the validated spike artifacts.
