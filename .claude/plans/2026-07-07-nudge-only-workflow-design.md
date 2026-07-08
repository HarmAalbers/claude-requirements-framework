# Nudge-Only Workflow Conductor — Design

**Date:** 2026-07-07
**Branch:** `feat/nudge-only-workflow`
**Status:** Approved design (brainstorm complete) → next: writing-plans
**Decision axis:** enforcement model, not phase boundaries (phase re-cut deferred — see Deferred section)

## Problem

The framework blocks too hard. On `master` in a fresh session, the first `Edit`
trips ~9 gates at once (design/plan/arch gates + protected_branch + branch_size_limit).
Meanwhile the *one* piece users love — the brainstorm nudge — is a soft, proactive
directive that guides Claude to the right skill without a wall. The user wants that
nudge experience generalized across the **whole** workflow, and wants enforcement
softened to nudges everywhere.

## Decisions (from brainstorm)

1. **Enforce vs nudge:** nudge-only — drop hard blocks. The framework guides, never refuses.
2. **Safety rails (protected_branch / branch_size_limit / single_session):** nudge these too — everything is soft.
3. **Nudge persistence:** once per phase (fires when a phase becomes current, then quiet).
4. **Implement phase:** add a soft marker (flipped by execute-plan) so the chain nudges
   "write the code" once and only nudges review after the marker flips.
5. **Phase boundaries:** keep the current cut for now (Approach A); re-cut later (Approach B, deferred).

## Principle

A requirement stops being a *wall* and becomes two softer things:
1. a **progress marker** that advances the phase chain, and
2. an **advisory** that surfaces (never denies) when its trigger fires.

Nothing ever returns deny. The proactive nudge chain does the driving.

## Architecture — three mechanisms

### ① Proactive phase nudge (generalizes brainstorm)
On every `UserPromptSubmit`, `handle-prompt-submit.py` calls
`derive_phase_and_skill()` → `(current_phase, skill)`. If this phase hasn't been
nudged yet, emit *"Next step: `/<skill>`"* and mark it. When a skill runs,
`auto-satisfy-skills.py` flips the marker, the phase advances, and the next phase's
nudge fires on the following prompt. Chain:
`design → plan-write → plan-validate → implement → review → ship`, one nudge each.

Dedup marker key changes from `(session)` → `(session, phase)` — the single change
that turns "once ever" into "once per phase". Brainstorm's directive becomes phase 1's
variant; other phases render a generic "next step" directive from the phase's `skill`.

### ② Reactive advisory (makes everything soft)
`check-requirements.py` keeps evaluating exactly as today, but in nudge mode every
decision that *would* deny instead **allows + injects the existing message as advisory
context**. Covers the tool/command-triggered rails the phase chain doesn't (master
edits, >400-line diffs, git commit/push/PR). Deduped so it surfaces once per
phase/session, not on every Edit. Reuses all current messages verbatim.

### ③ Soft implement marker
New lightweight requirement `implementation_done`; `implement.gate` points at it;
`auto-satisfy-skills.py` maps `requirements-framework:execute-plan` / `executing-plans`
→ flip it. Chain nudges "write the code" once, rests while coding, nudges `/deep-review`
only after the marker flips.

## The one lever

New global config axis **`enforcement: block | nudge`** (default `block`; this project
sets `nudge`). One switch flips the whole project from walls to advisories — fully
reversible, no per-requirement surgery, keeps the safety-rail advisories. Other
projects stay on `block` (additive, backward-safe).

## Files touched

- `hooks/lib/config.py` — `enforcement` getter (cascade-aware, default `block`).
- `hooks/check-requirements.py` — nudge mode: deny → allow + advisory context, deduped.
- `hooks/lib/brainstorm.py` — generalize into phase-agnostic nudge (derive_phase already returns the skill).
- `hooks/handle-prompt-submit.py` — call the generalized nudge.
- `hooks/auto-satisfy-skills.py` — add execute-plan → implementation_done mapping.
- `.claude/requirements.local.yaml` — `enforcement: nudge`, wire implement gate.
- `hooks/test_requirements.py` — tests (register in TestRunner main()).
- `plugins/requirements-framework/.claude-plugin/plugin.json` — version bump.

## Alternatives rejected

- Per-requirement disable instead of the `enforcement` switch — loses the safety-rail
  advisories the user asked to keep; N edits vs one lever.
- A brand-new nudge hook — unnecessary; `handle-prompt-submit.py` already fires every turn.
- Skip implement / let implement rest — user chose the soft marker (most faithful).

## Testing strategy (TDD)

- `enforcement` resolution across the config cascade (global default block; local nudge).
- deny → advisory downgrade in nudge mode (no deny returned; message surfaced as context).
- phase-nudge dedup by `(session, phase)` — re-fires when phase advances, quiet within a phase.
- implement marker advances the chain (execute-plan flips implementation_done → phase → review).
- Backward-compat: block mode unchanged (other projects unaffected).

## Deferred — phase re-cut (Approach B)

Separate design conversation, start ONLY after this lands. "Design" is really a 3-phase
arc; phase→gate is not 1:1 (design→1, plan-write→2, plan-validate→4); `commit_plan` is
double-owned by `writing-plans` AND `arch-review`. Re-cut boundaries, resolve the
double-ownership, decide whether to factor domain-modeling out of brainstorming.
Durable backlog: project memory `project-phase-recut-backlog`; session task #15.
