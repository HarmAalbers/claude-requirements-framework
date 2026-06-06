---
name: workflow-index
description: Use this skill at the start of any non-trivial work in a project that uses the requirements-framework. It maps the current phase to the single next command to run. Triggers on "what next", "where am I", "/req", or when the user is uncertain what workflow to use.
git_hash: bc28b83
---

# Workflow Index

The requirements-framework runs your project through an ordered phase pipeline. At any moment the project is in exactly one phase, derived from requirement state.

**The phase order is configured per project** via the `workflow:` config section, so the number, names, and order of phases can differ from the default map below. Do not hardcode the pipeline. The authoritative runtime resolution is:

- **`/req`** — the conductor. It resolves the current phase *and* the skill that phase dispatches to, live from the project's config, then routes you. When unsure what to run, just run `/req`.
- **`req status`** — shows the current requirement state the phase is derived from.

```bash
req status            # short
req status --verbose  # full requirement table
```

## Default (zero-config) workflow — fallback reference

This is the **built-in default** that applies when a project has no `workflow:` section. Use it as a mental model only; a configured project may reorder, rename, or add phases, and `/req` always wins over this table.

| Phase | When | Run |
|-------|------|-----|
| design | `design_approved` unsatisfied | `/brainstorm` |
| plan-write | `plan_written` unsatisfied | `/write-plan` |
| plan-validate | `solid_reviewed` unsatisfied (after plan_written) | `/arch-review` |
| implement | `verification_evidence` unsatisfied | `/execute-plan` |
| review | `pre_pr_review` unsatisfied | `/deep-review` then `/codex-review` |
| refactor | (manual) when a large refactor is needed | `/refactor-orchestrate` |
| ship | all session requirements satisfied | finalize commits + PR |

In the default workflow, planning is split because two skills are needed to clear all planning gates: `/write-plan` produces a plan (flips `plan_written`), and `/arch-review` validates it (flips `commit_plan`, `adr_reviewed`, `tdd_planned`, `solid_reviewed`).

## Common transitions (default workflow)

- After `/brainstorm` → `design_approved` flips → next phase: **plan-write**
- After `/write-plan` → `plan_written` flips → next phase: **plan-validate**
- After `/arch-review` → 4 planning requirements flip → next phase: **implement**
- After `/deep-review` → `pre_pr_review` flips → next phase: **ship**

## How to use this index

1. Prefer `/req` — it reads the project's configured workflow and routes for you.
2. If reasoning by hand, read the user's recent prompt and `req status`, then identify the *next* unsatisfied gate along the configured pipeline (the default map above when the project is zero-config).
3. Recommend (or invoke) the matching command for that phase.
4. If multiple phases look open, default to the earliest one — the pipeline runs top-to-bottom.

This skill is *read-only*: it teaches the map but does not move the project. To act on the map, run `/req` (the conductor command that auto-dispatches the configured skill) or invoke the matching command directly.
