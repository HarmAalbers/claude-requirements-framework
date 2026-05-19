# Design: Project-agnostic refactor orchestration

**Date:** 2026-05-18
**Branch:** feat/refactor-orchestration-bundle
**Status:** Approved — hand off to writing-plans

---

## Problem

`refactor-executor.md` contains hardcoded FastAPI-specific conventions:
- `NO HTTPException`, `NO JSONResponse`, `NO direct SDK imports (openai/azure/anthropic)`
- `ONE return statement per endpoint body`
- `Use Annotated[T, Marker] for every FastAPI parameter`

These only apply to one project (statuta-rag-api-v2). Any other project gets wrong constraints injected into its executor agents.

A second problem was discovered: the executor is doing excessive reads and exploration per chunk (~86 tool calls observed in a live session) because the dispatch prompt is thin — it gives section references rather than inlined content, so the executor compensates by reading the plan, grepping for symbols, and catting related files.

---

## Design

### 1. `refactor-executor.md` — make it project-agnostic

**Remove** the two project-specific hard rules entirely:
```
- For router-layer work specifically: NO HTTPException, NO JSONResponse,
  NO direct SDK imports (openai/azure/anthropic), ONE return statement per endpoint body.
- Use Annotated[T, Marker] for every FastAPI parameter when working on FastAPI routers.
```

**Add** a hard rule that makes the "fat prompt" contract explicit:
```
- DO NOT read the plan. DO NOT grep or explore. All context is in this prompt.
  If something is missing or contradictory, use verdict: NEEDS_CLARIFICATION.
```

**Keep** only universally-applicable rules:
- NO try/except
- NO inline comments explaining WHAT
- Match the plan's canonical shape exactly
- Naming variance only where the plan uses a placeholder

**Add** `verdict: NEEDS_CLARIFICATION` to the verdict set:
```
verdict: NEEDS_CLARIFICATION — inlined context is ambiguous or contradictory.
  Include a single specific question. Do NOT make any edits before clarification.
```

**Workflow** collapses from 5 steps to 3:
1. Apply the change (plan section + file contents already in prompt)
2. Verify (ruff + import smoke + test collect)
3. Report

---

### 2. Convention flow — `.claude/refactor-conventions.md` → executor dispatch

Conventions travel a fixed path:

```
.claude/refactor-conventions.md
        ↓  read explicitly in Stage 1
Plan §1 "Forbidden / Layer rules"
        ↓  Stage 7 fills the placeholder
orchestrator-prompt.md  →  ## Project conventions block
        ↓  orchestrator inlines per chunk
Executor dispatch prompt  →  ## Project conventions
```

**SKILL.md Stage 1** gains an explicit bullet:
> If `.claude/refactor-conventions.md` exists, read it. Include its **Layer rules** and
> **Known anti-patterns** sections in the "what should be" report.

**Plan §1 (Forbidden)** is seeded from the conventions file when one exists. Empty for new projects — no blocking dependency.

**Bootstrap:** First run on a new project has no conventions file; the `## Project conventions` block is omitted from the dispatch template. After the first run, `refactor-analyzer` starts growing `.claude/refactor-conventions.md` via rule-of-three, so subsequent runs pick it up automatically.

---

### 3. Fat dispatch prompt — orchestrator pre-fetches content

The orchestrator gets a new **Step 2.5** before each chunk dispatch:

1. Extract the relevant plan section(s) for this chunk (already in memory from Step 0)
2. `Read` the target file(s) listed for this chunk (returns `cat -n` output with line numbers)
3. Build the dispatch prompt by inlining three blocks
4. Spawn the executor with a `name:` parameter

The dispatch template changes from thin (references) to fat (inlined content):

```
## Plan section (§4.2 — canonical shape)
<literal plan section text>

## Current file contents
### src/app/routes/foo.py
     1	from fastapi import APIRouter
     2	
     3	router = APIRouter()
     ...

## Project conventions
- NO HTTPException, NO JSONResponse
- ONE return statement per endpoint body

## Your task
Apply the plan section above to the file above.
Verify: <ruff command> + <import smoke command>
```

**New-file chunks:** include parent directory listing (`ls -1 <parent>/`) instead of file contents.

**Line numbers** (from `Read`'s `cat -n` output) give the executor:
- Exact `old_string` matches for `Edit` calls — no whitespace guessing
- Unambiguous deviation reporting: "changed line 42, reason: X"

---

### 4. Clarification protocol — resume via SendMessage

Each executor spawn gets a `name:` so the orchestrator can resume it:

```python
Agent({
  name: "executor-A1",
  subagent_type: "requirements-framework:refactor-executor",
  prompt: <fat dispatch prompt>
})
```

When the executor returns `verdict: NEEDS_CLARIFICATION`:

```
orchestrator reads the question
    ↓
orchestrator can answer? → SendMessage({to: "executor-A1", message: "<answer>"})
    ↓                       executor resumes with full context, no re-read needed
orchestrator cannot answer? → AskUserQuestion(human) → SendMessage({to: "executor-A1", ...})
```

**Why resume over re-dispatch:** the executor's full context (inlined plan section, file contents, conventions) is already in its context window. `SendMessage` resumes that window; a new `Task` dispatch would require re-inlining everything.

The per-chunk workflow in the orchestrator-prompt template gains:
```
- NEEDS_CLARIFICATION → answer inline via SendMessage({to: executor-name, ...}).
  If you cannot answer confidently: AskUserQuestion to me first, then SendMessage.
  Do NOT re-dispatch a new executor for clarification — resume the existing one.
```

---

## Files changed

| File | Change |
|------|--------|
| `plugins/requirements-framework/agents/refactor-executor.md` | Remove FastAPI rules; add DO NOT READ rule; add NEEDS_CLARIFICATION verdict; simplify workflow to 3 steps |
| `plugins/requirements-framework/skills/refactor-orchestration/orchestrator-prompt-template.md` | Add Step 2.5 (pre-fetch); fat dispatch template (3 inlined blocks); named executor spawns; NEEDS_CLARIFICATION handler |
| `plugins/requirements-framework/skills/refactor-orchestration/SKILL.md` | Stage 1: explicit read of `.claude/refactor-conventions.md` |

---

## What does NOT change

- `refactor-investigator.md` — unchanged (already project-agnostic)
- `refactor-analyzer.md` — unchanged (already grows `.claude/refactor-conventions.md`)
- `plan-template.md` — §1 (Forbidden) already exists; just needs a note that it should be seeded from conventions file
- `retrospective-template.md` — unchanged
- The two-ledger learning system — unchanged
