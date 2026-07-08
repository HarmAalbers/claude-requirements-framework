---
name: workflow-index
description: Use this skill at the start of any non-trivial work in a project that uses the requirements-framework. It maps the current phase to the single next command to run. Triggers on "what next", "where am I", "/req", or when the user is uncertain what workflow to use.
git_hash: 4b624f2
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
| plan | `plan_written` unsatisfied | `/write-plan` |
| validate | `plan_validated` unsatisfied (after plan_written) | `/arch-review` (optional `/codex-review`) |
| build | `implementation_done` unsatisfied | `/execute-plan` (loops `/pre-commit` per commit) |
| review | `pr_reviewed` unsatisfied | `/deep-review` (optional `/codex-review`) |
| verify | `verified` unsatisfied | `verification-before-completion` |
| ship | all gates satisfied (gateless) | `finishing-a-development-branch` |

This is the ADR-022 typed 7-node backbone: Design → Plan → Validate → Build → Review → Verify → Ship. Planning is split across two phases: `/write-plan` produces a plan (flips `plan_written`), and `/arch-review` validates it (flips `plan_validated`).

## Common transitions (default workflow)

- After `/brainstorm` → `design_approved` flips → next phase: **plan**
- After `/write-plan` → `plan_written` flips → next phase: **validate**
- After `/arch-review` → `plan_validated` flips → next phase: **build**
- After `/execute-plan` → `implementation_done` flips → next phase: **review**
- After `/deep-review` → `pr_reviewed` flips → next phase: **verify**
- After `verification-before-completion` → `verified` flips → next phase: **ship**

## How to use this index

1. Prefer `/req` — it reads the project's configured workflow and routes for you.
2. If reasoning by hand, read the user's recent prompt and `req status`, then identify the *next* unsatisfied gate along the configured pipeline (the default map above when the project is zero-config).
3. Recommend (or invoke) the matching command for that phase.
4. If multiple phases look open, default to the earliest one — the pipeline runs top-to-bottom.

This skill is *read-only*: it teaches the map but does not move the project. To act on the map, run `/req` (the conductor command that auto-dispatches the configured skill) or invoke the matching command directly.
