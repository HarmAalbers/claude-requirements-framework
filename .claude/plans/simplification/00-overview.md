# Simplification Plan — Overview

**Goal**: Consolidate the requirements-framework into a single coherent workflow with the smallest possible initial context. **No new dependencies.** Each step is independently mergeable.

## End-state shape

```
SessionStart ─► compact briefing (~150 tok)
   │
   ▼
User prompt OR /req
   │
   ▼
workflow-index skill   (~80 tok metadata, body on demand)
   │
   ▼
/req conductor command   (derives phase, dispatches handoff)
   │
   ▼
Existing skill/command   (unchanged — does the work)
   │
   ▼
PostToolUse hooks   (unchanged — flip requirement flag)
   │
   ▼
Derived-phase advances automatically; statusline reflects it
```

## Steps in order

| # | Title | Independent? | Effort |
|---|---|---|---|
| 01 | Strip session briefing | yes | 0.5 day |
| 02 | Default ENABLE_TOOL_SEARCH on | yes | 0.5 day |
| 03 | Phase-aware statusline | yes | 0.5 day |
| 04 | `workflow-index` skill | yes | 0.5 day |
| 05 | `/req` conductor command | depends on 04 | 1 day |
| 06 | Migrate commands to aliases | depends on 05 | 1 day |
| 07 | Deprecation cleanup | depends on 06 | 0.5 day |

Total: ~4.5 working days, can run 01–04 in parallel (1 day wall clock).

## Non-goals (deferred to later, one at a time)

- Langfuse tracing / prompt registry
- Pydantic-validated agent output (Instructor)
- CosmosDB / LlamaIndex semantic memory
- Ragas evaluation harness
- Jinja2 prompt template engine
- PydanticAI supervisor (markdown command suffices for now)
- Extracting the three project-specific auditors to a dialect plugin

## Reversibility

Every step is a small Python or Markdown change. Each has a documented rollback. No data migrations.

## Token budget targets

| Component | Today | After Step 07 |
|---|---|---|
| Session briefing | ~1,500 tok | ~150 tok |
| Inlined skill bodies | ~700 tok | 0 tok |
| Deferred-tool dump | ~3,500 tok | ~0 tok (lazy) |
| **Framework overhead, initial** | **~13,750** | **~5,000** |

(Agent registry and available-skills system reminder are Claude Code-controlled and cannot be reduced without uninstalling plugins.)
