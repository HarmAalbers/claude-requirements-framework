---
name: refactor-orchestrate
description: "Multi-layer top-down refactor workflow. Produces a validated plan and an orchestrator-prompt that runs in a fresh claude session, dispatching Haiku executor chunks and escalating contradictions to a Sonnet investigator."
argument-hint: "[<refactor-slug>]"
allowed-tools: ["Bash", "Glob", "Grep", "Read", "Write", "Edit", "Task", "AskUserQuestion", "WebFetch", "mcp__plugin_context7-plugin_context7__query-docs", "mcp__plugin_context7-plugin_context7__resolve-library-id"]
git_hash: 4c8508a
---

> **Workflow position**: invoked by `/req refactor`. Run directly to override the conductor.

# Refactor Orchestration — Deterministic Orchestrator

Multi-layer top-down refactor workflow. Satisfies no framework requirements (run `/requirements-framework:arch-review` first if your project enforces planning gates).

**See ADR-014 for design rationale.**

## Deterministic Execution Workflow

You MUST follow these steps in exact order. Do not skip steps or interpret — execute as written.

### Step 0: Resolve refactor slug

Parse the command argument (`$ARGUMENTS`, set by Claude Code from the user's invocation) into `SLUG`. If empty, prompt the user once via AskUserQuestion for a short kebab-case slug.

```bash
SLUG="${ARGUMENTS:-}"
DATE="$(date +%Y-%m-%d)"

if [[ -z "$SLUG" ]]; then
  # Use AskUserQuestion to prompt for a kebab-case slug (e.g., "router-layer", "auth-rewrite").
  # The response sets $SLUG. Validate: lowercase, hyphens only, no spaces.
  # (AskUserQuestion happens as a separate tool call between this and the next bash block.)
  : # SLUG to be set by user response
fi

# Validate slug format before composing paths
if [[ ! "$SLUG" =~ ^[a-z][a-z0-9-]*$ ]]; then
  echo "Invalid slug: must be lowercase kebab-case (a-z, 0-9, -). Got: '$SLUG'" >&2
  exit 2
fi

PLAN_PATH=".claude/plans/${DATE}-${SLUG}.md"
ORCH_PATH=".claude/plans/${DATE}-${SLUG}-orchestrator-prompt.md"
```

If either output file already exists, ask the user via AskUserQuestion: overwrite, append-date-suffix (`${DATE}-${SLUG}-2.md`), or abort.

### Step 1: Pre-flight checks

```bash
# Working tree must be clean
git diff --quiet || { echo "Working tree dirty — commit or stash first." >&2; exit 2; }

# .claude/plans/ must exist or be creatable
mkdir -p .claude/plans

# Project conventions sheet (if present) is readable
if [ -f .claude/refactor-conventions.md ]; then
  echo "Found .claude/refactor-conventions.md — will be included in Stage 1 inventory"
fi
```

Stop with explicit error if any pre-flight fails.

### Step 2: Invoke skill stage 1 (Inventory)

Dispatch two parallel Explore agents:

```
Task(subagent_type="Explore", prompt="...catalogue current layer state of target area...")
Task(subagent_type="Explore", prompt="...extract rules from relevant ADRs/design docs/conventions sheet...")
```

Collect "what is" + "what should be" reports.

### Step 3: Invoke skill stages 2–4 (Top-down design, context7 validation, harmonization)

Per the `requirements-framework:refactor-orchestration` skill workflow. Each stage produces a section of the in-progress plan content held in memory.

Context7 validation (Stage 3) is non-optional. Stop if context7 is unreachable; instruct user to retry.

### Step 4: Persist plan

Write the validated plan to `$PLAN_PATH` using the skill's `plan-template.md` structure (§0–§13).

### Step 5: Generate chunk queue

Decompose the plan into atomic chunks (one chunk = one commit). Group into phases (typically: shared primitives → protocols/contracts → per-feature rewrites → structural tests → smoke validation).

### Step 6: Persist orchestrator-prompt

Write the copy-paste orchestrator to `$ORCH_PATH` using the skill's `orchestrator-prompt-template.md`. The block must include:
- `=== BEGIN ORCHESTRATOR PROMPT ===` / `=== END ORCHESTRATOR PROMPT ===` markers
- Prerequisites block (plugin installed, working tree clean, baseline tests pass)
- Chunk queue
- Phase A–F dispatch logic
- Subagent_type strings using `requirements-framework:refactor-{executor,investigator,analyzer}` namespaced form

### Step 7: Verify outputs

```bash
[ -f "$PLAN_PATH" ] && [ -f "$ORCH_PATH" ] || { echo "Output files missing." >&2; exit 2; }

# Confirm BEGIN/END markers in orchestrator-prompt
grep -q '=== BEGIN ORCHESTRATOR PROMPT ===' "$ORCH_PATH" || exit 2
grep -q '=== END ORCHESTRATOR PROMPT ===' "$ORCH_PATH" || exit 2

# Confirm subagent_type uses namespaced form (positive AND negative checks)
grep -qE 'subagent_type[^"]*"requirements-framework:refactor-(executor|investigator|analyzer)"' "$ORCH_PATH" || {
  echo "Missing namespaced subagent_type references" >&2; exit 2;
}
grep -E 'subagent_type[^"]*"refactor-(executor|investigator|analyzer)"' "$ORCH_PATH" && {
  echo "Found un-namespaced subagent_type references" >&2; exit 2;
}
```

### Step 8: Final report to user

Print:
```
Plan written to: $PLAN_PATH
Orchestrator-prompt written to: $ORCH_PATH

NEXT STEPS:
1. Review the plan at $PLAN_PATH
2. Open a FRESH claude session (not this one)
3. Paste the block between === BEGIN ORCHESTRATOR PROMPT === and === END ORCHESTRATOR PROMPT === markers in $ORCH_PATH
4. The orchestrator runs Phases A–F; commits atomically per chunk; finishes with refactor-analyzer retrospective
```

This command does NOT auto-satisfy framework requirements. Run `/requirements-framework:arch-review` first if planning gates are required.

### Verdict

- **SUCCESS**: both output files exist, all verifications pass.
- **FAILED**: any pre-flight or verification step failed; report exit code with reason.
- **ABORTED**: user chose to abort during file-collision handling.
