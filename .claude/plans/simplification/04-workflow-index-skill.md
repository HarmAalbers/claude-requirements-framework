# Step 04 — `workflow-index` skill (index-first discovery)

## Goal

A single tiny skill whose metadata describes the whole workflow shape. Claude reads it once to know where to go next; the body loads only on activation.

This is the **Anthropic-recommended progressive-disclosure pattern**: ~100-token metadata, ~3K-token body, deferred assets.

## Why now

We don't yet have the conductor command (Step 05). The index skill is its read-only sibling — it teaches Claude the map. Step 05 will *act* on the map.

## Files touched

- `plugins/requirements-framework/skills/workflow-index/SKILL.md` (new)
- `plugins/requirements-framework/.claude-plugin/plugin.json` — register the new skill

## Implementation

`SKILL.md`:

```markdown
---
name: workflow-index
description: Use this skill at the start of any non-trivial work in a project that uses the requirements-framework. It maps the current phase to the single next command to run. Triggers on "what next", "where am I", "/req", or when the user is uncertain what workflow to use.
git_hash: uncommitted
---

# Workflow Index

The requirements-framework workflow is a 6-phase pipeline. At any moment, your project is in exactly one phase, derived from requirement state.

## Phase → next command

| Phase | When | Run |
|-------|------|-----|
| design | design_approved unsatisfied | `/brainstorm` |
| plan | plan_written unsatisfied | `/arch-review` |
| implement | verification_evidence unsatisfied | `/execute-plan` |
| review | pre_pr_review unsatisfied | `/deep-review` then `/codex-review` |
| refactor | (manual) when a large refactor is needed | `/refactor-orchestrate` |
| ship | all session requirements satisfied | finalize commits + PR |

## Single entry point

If unsure, just run `/req`. The conductor will derive the phase and dispatch for you.

## Status check

```bash
req status            # short
req status --verbose  # full requirement table
```

## Common transitions

- After `/brainstorm` → `design_approved` flips → next phase: plan
- After `/arch-review` → 4 planning requirements flip → next phase: implement
- After `/deep-review` → `pre_pr_review` flips → next phase: ship
```

## Example

User types: "what should I do next?"

Today: Claude searches through 20 skill descriptions, weighs options, may pick wrong.
After: Claude activates `workflow-index` (it matches "what next"), reads the table, says "You're in *review* phase — run `/deep-review`."

## Acceptance

- [ ] Skill installs via `./sync.sh deploy`
- [ ] `/plugin list` shows `workflow-index` registered
- [ ] In a fresh session, asking "what's next?" leads Claude to invoke this skill
- [ ] Skill body is < 5,000 tokens (within Anthropic's recommended ceiling)
- [ ] Metadata description is < 200 tokens

## Rollback

Delete the skill file and remove from `plugin.json`. No side effects.

## Effort

0.5 day

## Depends on

Nothing structurally, but works best paired with Step 05.
