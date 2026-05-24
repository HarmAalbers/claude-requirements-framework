---
name: workflow-index
description: Use this skill at the start of any non-trivial work in a project that uses the requirements-framework. It maps the current phase to the single next command to run. Triggers on "what next", "where am I", "/req", or when the user is uncertain what workflow to use.
git_hash: 053a179
---

# Workflow Index

The requirements-framework workflow is a 7-phase pipeline. At any moment, your project is in exactly one phase, derived from requirement state.

## Phase → next command

| Phase | When | Run |
|-------|------|-----|
| design | `design_approved` unsatisfied | `/brainstorm` |
| plan-write | `plan_written` unsatisfied | `/write-plan` |
| plan-validate | `solid_reviewed` unsatisfied (after plan_written) | `/arch-review` |
| implement | `verification_evidence` unsatisfied | `/execute-plan` |
| review | `pre_pr_review` unsatisfied | `/deep-review` then `/codex-review` |
| refactor | (manual) when a large refactor is needed | `/refactor-orchestrate` |
| ship | all session requirements satisfied | finalize commits + PR |

Planning is split because two skills are needed to clear all planning gates: `/write-plan` produces a plan (flips `plan_written`), and `/arch-review` validates it (flips `commit_plan`, `adr_reviewed`, `tdd_planned`, `solid_reviewed`).

## Single entry point

If unsure, just run `/req`. The conductor will derive the phase and dispatch for you.

## Status check

```bash
req status            # short
req status --verbose  # full requirement table
```

## Common transitions

- After `/brainstorm` → `design_approved` flips → next phase: **plan-write**
- After `/write-plan` → `plan_written` flips → next phase: **plan-validate**
- After `/arch-review` → 4 planning requirements flip → next phase: **implement**
- After `/deep-review` → `pre_pr_review` flips → next phase: **ship**

## How to use this index

1. Read the table above and the user's recent prompt.
2. Identify which requirement is the *next* unsatisfied one along the pipeline.
3. Recommend (or invoke) the matching command from the table.
4. If multiple phases look open, default to the earliest one — the pipeline runs top-to-bottom.

This skill is *read-only*: it teaches the map but does not move the project. To act on the map, run `/req` (the conductor command that auto-dispatches) or invoke the matching command directly.
