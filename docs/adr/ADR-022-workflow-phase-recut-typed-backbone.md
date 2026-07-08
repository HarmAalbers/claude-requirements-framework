# ADR-022: Workflow Phase Re-cut — Typed 7-Node Backbone

**Status:** Accepted
**Date:** 2026-07-07
**Supersedes:** the flat 8-phase workflow vocabulary (design / plan-write / plan-validate / implement / commit-review / review / cleanup / ship)
**Related:** ADR-011 (message externalization), the nudge-only overhaul (enforcement: nudge)

## Context

The workflow phase model was a flat linear list that hid the real structure of the work:

- "Design" was really a 3-phase arc (design / plan / validate); the phase→gate mapping was lopsided (1 / 2 / 4 gates).
- Gates were **double-owned**: `commit_plan` by both `writing-plans` and `arch-review`; `tdd_planned` by both `arch-review` (is the *plan* TDD-ready?) and `test-driven-development` (am I *doing* TDD?) — one name, two different moments.
- Each phase's skill was itself a bundle (`/arch-review` = a 6-agent team), invisible to the model and the conductor.
- There was no notion of conditional side-quests (codex / appsec / frontend) — they were absent from the workflow entirely.

A bottom-up inventory of every skill/agent/command showed the graph is **not one kind of thing**: a sequential spine + parallel teams + a per-commit loop + conditional side-quests.

## Decision

Re-model the workflow as a **typed 7-node backbone**, make it the framework default (`WORKFLOW_DEFAULTS`), and delete the old gate names cleanly (no compat shims, per the project convention).

```
Design → Plan → Validate → Build → Review → Verify → Ship
[spine] [spine] [TEAM]    [spine] [TEAM]   [spine] [spine]
                                   +loop (in Build)
```

| Node | Type | Gate | Skill / Command | Attached |
|------|------|------|-----------------|----------|
| Design   | spine | `design_approved`      | `brainstorming` | — |
| Plan     | spine | `plan_written`         | `writing-plans` | — |
| Validate | team  | `plan_validated`       | `/arch-review`  | *conditional:* `/codex-review` |
| Build    | spine + loop | `implementation_done` | `executing-plans` | *loop:* `/pre-commit` → `pre_commit_review`, re-armed per commit |
| Review   | team  | `pr_reviewed`          | `/deep-review`  | *conditionals:* `/codex-review`, appsec, frontend |
| Verify   | spine | `verified`             | `verification-before-completion` | — |
| Ship     | spine | — (gateless)           | `finishing-a-development-branch` | — |

### Node type semantics (reuses existing runtime; new machinery is tiny)

- **spine** — nudge one skill; its gate is satisfied by that skill via auto-satisfy. *(unchanged)*
- **team** — nudge one orchestrating command; the command fans out its agents; ONE gate is satisfied on command completion. `type: team` is metadata that lets the conductor describe it ("runs a review team"). `derive_phase` / `resolve_current_phase` are unchanged — they walk phases by gate, so team vs spine is transparent to derivation.
- **loop** — a `single_use` gate (`pre_commit_review`) declared on the Build node, re-armed on the commit command by the existing `clear-single-use` hook. New part: declaring it under Build so the conductor surfaces "run `/pre-commit` before each commit" while in Build.
- **conditional** — a declared list of optional side-quest skills/agents on a node, surfaced by the conductor as *available here*. No gate, no auto-fire, invoked at discretion.

### Gate consolidation: ~11 → 7

| Old gate(s) | New |
|-------------|-----|
| `design_approved` | `design_approved` (kept) |
| `plan_written` (+ `commit_plan` on `writing-plans`) | `plan_written` (drops `commit_plan`) |
| `adr_reviewed` + `tdd_planned` + `solid_reviewed` + `commit_plan` | **`plan_validated`** (one team gate) |
| `implementation_done` | `implementation_done` (kept) |
| `pre_commit_review` | `pre_commit_review` (kept — the Build loop) |
| `pre_pr_review` | **`pr_reviewed`** (rename) |
| `codex_reviewer` | *removed as a gate* → conditional side-quest |
| `pre_push_verification` | **`verified`** (rename) |

Safety guards are unchanged and orthogonal: `protected_branch`, `branch_size_limit`, `single_session_per_project` (advisory under `enforcement: nudge`).

## Consequences

**Positive**
- One gate per team; the lopsided many-gates-per-phase shape is gone.
- No double-ownership: `arch-review` owns `plan_validated`; `writing-plans` owns only `plan_written`; build-time TDD is advisory (no longer owns a gate).
- The conductor/nudge now surfaces the loop, team fan-out, and conditional side-quests — structure the model previously couldn't see.
- The schema needed almost no new machinery: `config._normalize_phase` already preserves unknown keys, so `type`/`loop`/`conditionals` pass through; `phase_directive` gained an optional phase-config arg to render the extra advisory lines.

**Costs / migration**
- Old gate names are deleted; a project still referencing them gets a validation error pointing at the new name (the intended migration signal). No compat aliases.
- The vocabulary migration touched every surface that named the old gates: `WORKFLOW_DEFAULTS`, `PHASE_GATES`, the auto-satisfy map, project + example configs, the `feature_catalog` (upgrade/sync), the `req init` generators (`init_presets` + `feature_selector`), and the test suite.
- **`req init` generators were outside the original plan's blast radius** and were migrated after surfacing the gap — leaving them would have generated configs with gates no skill auto-satisfies.

**Watch-outs discovered during implementation**
- YAML footgun: a bare `on: commit` key in the loop config parses as the boolean `True` under YAML 1.1 — the key must be quoted (`"on": commit`). `WORKFLOW_DEFAULTS` (Python) is unaffected.

## Alternatives rejected

- **Keep the flat 8-phase list** (patch boundaries only) — doesn't fix the hidden-structure problem.
- **Auto-matching conditionals** (path globs / content regex) — rejected a matching engine in favor of manually-declared side-quests (lazy-dev).
- **Keep sub-gates under teams** — preserves the lopsided many-gates-per-phase shape.
- **Compat aliases for old gate names** — contradicts the no-backwards-compat convention.

## References

- Design: `.claude/plans/2026-07-07-workflow-phase-recut-design.md`
- Plan: `.claude/plans/2026-07-07-workflow-phase-recut-plan.md`
