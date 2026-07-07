# Workflow Phase Re-cut (Approach B) — Design

**Date:** 2026-07-07
**Branch:** `feat/workflow-phase-recut` (stacked on `feat/nudge-only-workflow`)
**Status:** Approved design (brainstorm complete) → next: writing-plans
**Depends on:** the nudge-only overhaul (enforcement: nudge, `resolve_current_phase`) — this re-cut redesigns the workflow vocabulary that the nudge chain drives.

## Problem

The workflow phase model is a flat linear list that hides the real structure of the work:
- "Design" is really a 3-phase arc (design / plan / validate); phase→gate is lopsided (1 / 2 / 4 gates).
- Gates are **double-owned**: `commit_plan` by both `writing-plans` and `arch-review`; `tdd_planned` by both `arch-review` (is the *plan* TDD-ready?) and `test-driven-development` (am I *doing* TDD?) — same name, two different moments.
- Each phase's skill is itself a bundle (arch-review = a 6-agent team), invisible to the model.
- No notion of conditional side-quests (security/frontend/codex) — they're absent from the workflow.

The bottom-up inventory (all skills/agents/commands/checks) showed the graph is **not one kind of thing**: a sequential spine + parallel teams + a per-commit loop + conditional side-quests.

## Decisions (from brainstorm)

1. **Re-think ground-up** from the work itself (not patch the current 8), including the workflow steps.
2. **Typed nodes:** the model formally represents spine / team / loop / conditional.
3. **Conditionals are manual** — declared per node, surfaced as *available* side-quests; no auto-matching engine, no gate.
4. **One gate per team** — Validate and Review each collapse to a single gate; the redundant standalone gates fold away.
5. **New global default + clean gate renames** — the 7-node typed backbone becomes `WORKFLOW_DEFAULTS`; old gate names are removed cleanly (no compat shims, per project convention).

## The 7-node typed backbone

```
Design → Plan → Validate → Build → Review → Verify → Ship
[spine] [spine] [TEAM]    [spine] [TEAM]   [spine] [spine]
                                   +loop (in Build)
```

| Node | Type | Gate | Skill / Command | Attached |
|------|------|------|-----------------|----------|
| Design | spine | `design_approved` | `brainstorming` | — |
| Plan | spine | `plan_written` | `writing-plans` | — |
| Validate | team | `plan_validated` | `/arch-review` | *conditional:* codex-arch-reviewer |
| Build | spine + loop | `implementation_done` | `executing-plans` | *loop:* `/pre-commit` → `pre_commit_review`, re-armed per commit |
| Review | team | `pr_reviewed` | `/deep-review` | *conditionals:* codex-review, appsec-auditor, tenant-isolation-auditor, compliance-auditor, frontend-reviewer |
| Verify | spine | `verified` | `verification-before-completion` | — |
| Ship | spine | — | `finishing-a-development-branch` | — |

**Teams (agents fan out in parallel inside the command):**
- Validate `/arch-review` → adr-guardian, solid-reviewer, tdd-validator, commit-planner, refactor-advisor, backward-compatibility-checker
- Review `/deep-review` → code-reviewer, silent-failure-hunter, tool-validator, test-analyzer, comment-analyzer, type-design-analyzer

## Node type semantics (reuse existing runtime; new machinery is small)

- **spine** — nudge one skill; gate satisfied by that skill via auto-satisfy. *(unchanged)*
- **team** — nudge one orchestrating command; command fans out its agents; ONE gate satisfied on command completion via auto-satisfy. `type: team` is metadata that lets the conductor describe it ("runs a review team"). derive_phase / resolve_current_phase are **unchanged** — they walk phases by gate; team vs spine is transparent to derivation.
- **loop** — a `single_use` gate (`pre_commit_review`) attached to the Build node, re-armed on the commit command by the existing `clear-single-use` hook. *(existing behavior)* New part: declare it under Build so the conductor surfaces "run /pre-commit before each commit" while in Build.
- **conditional** — a declared list of optional side-quest skills/agents on a node. The conductor / nudge lists them as *available here*. No gate, no auto-fire, invoked at discretion. *(new, trivial: a list + surfacing text)*

## Gate consolidation: ~11 → 7

| Old gate(s) | New |
|-------------|-----|
| `design_approved` | `design_approved` (kept) |
| `plan_written` (+ `commit_plan` on writing-plans) | `plan_written` (commit_plan dropped from writing-plans) |
| `adr_reviewed` + `tdd_planned` + `solid_reviewed` + `commit_plan` | **`plan_validated`** (one team gate) |
| `implementation_done` | `implementation_done` (kept) |
| `pre_commit_review` | `pre_commit_review` (kept — the Build loop) |
| `pre_pr_review` | **`pr_reviewed`** (rename) |
| `codex_reviewer` | *removed as a gate* → conditional side-quest |
| `pre_push_verification` | **`verified`** (rename) |

Safety guards unchanged and orthogonal: `protected_branch`, `branch_size_limit`, `single_session_per_project` (advisory in nudge mode).

## Config schema (new `workflow:` shape)

```yaml
workflow:
  default_phase: design
  ship_phase: ship
  phases:
    - { name: design,   type: spine, gate: design_approved,     skill: "requirements-framework:brainstorming", brainstorm_on_enter: true }
    - { name: plan,     type: spine, gate: plan_written,        skill: "requirements-framework:writing-plans" }
    - { name: validate, type: team,  gate: plan_validated,      skill: "requirements-framework:arch-review",
        conditionals: ["requirements-framework:codex-review"] }
    - { name: build,    type: spine, gate: implementation_done, skill: "requirements-framework:executing-plans",
        loop: { gate: pre_commit_review, skill: "requirements-framework:pre-commit", on: commit } }
    - { name: review,   type: team,  gate: pr_reviewed,         skill: "requirements-framework:deep-review",
        conditionals: ["requirements-framework:codex-review", "appsec-auditor", "frontend-reviewer"] }
    - { name: verify,   type: spine, gate: verified,            skill: "requirements-framework:verification-before-completion" }
    - { name: ship,     type: spine, gate: null,                skill: "requirements-framework:finishing-a-development-branch" }
```

`config.py` `_normalize_workflow` accepts and preserves the new `type` / `loop` / `conditionals` keys (already preserves unknown keys — verify and extend). New keys are metadata; absence defaults `type: spine`, no loop, no conditionals.

## Auto-satisfy map changes (`hooks/auto-satisfy-skills.py`)

```
brainstorming           -> design_approved            (unchanged)
writing-plans           -> plan_written               (drop commit_plan)
arch-review             -> plan_validated             (was: commit_plan, adr_reviewed, tdd_planned, solid_reviewed)
executing-plans         -> implementation_done        (unchanged)
pre-commit              -> pre_commit_review           (unchanged — Build loop)
deep-review / v3-review -> pr_reviewed                (rename)
verification-before-completion -> verified            (rename)
codex-review            -> (removed; conditional, not a gate)
test-driven-development -> (removed as tdd_planned owner; build-time TDD is advisory)
```

## Conductor & nudge surfacing

- The proactive nudge (`resolve_current_phase` from nudge-only) already walks phases by gate — works unchanged with the new vocabulary. A `team` phase nudges its command; the directive text can note "(runs a review team)".
- While in **Build**, the conductor additionally surfaces the loop: "run `/pre-commit` before each commit."
- For a node with `conditionals`, the conductor lists them as optional: "Available here: `/codex-review`, `/appsec-auditor`, `/frontend-reviewer`."
- `derive_phase.py --with-skill` and `/req` read the new fields; `workflow-index` updated to describe typed nodes.

## Blast radius / migration

- Rewrite `WORKFLOW_DEFAULTS` (config.py) + `PHASE_GATES` fallback (derive_phase.py) to the 7-node vocabulary.
- Rewrite this project's `.claude/requirements.yaml` + `.claude/requirements.local.yaml` + `examples/*.yaml` gate names.
- Rename/remove message YAML files for renamed/removed gates.
- **Many existing tests assert the current phase names/gates** (`plan-write → plan_written`, `plan-validate → solid_reviewed`, `with-skill: plan-validate → arch-review`, `zero-config: N sat → phase`, etc.). These must be rewritten to the new vocabulary — the largest single work item.
- No compat shims: old gate names are deleted; a project still on them updates its config (surfaced via validation errors).

## Testing strategy (TDD)

- Config: `_normalize_workflow` preserves `type`/`loop`/`conditionals`; `WORKFLOW_DEFAULTS` is the 7-node backbone; validator accepts the new keys.
- derive_phase / resolve_current_phase: walk the new vocabulary (design→plan→validate→build→review→verify→ship); loop/conditional nodes transparent to linear derivation.
- auto-satisfy: arch-review→plan_validated (one gate), renames land, codex/tdd owners removed.
- Conductor: loop + conditionals surfaced for the right nodes.
- Regression: nudge-only behavior (advisory, phase nudge) still works over the new vocabulary.

## Alternatives rejected
- Keep the flat linear list (patch boundaries only) — doesn't fix the hidden-structure problem the user set out to solve.
- Auto-matching conditionals (path globs / content regex) — rejected for a matching engine; manual side-quests chosen (lazy-dev).
- Keep sub-gates under teams — keeps the lopsided many-gates-per-phase shape.
- Compat aliases for old gate names — contradicts the no-backwards-compat convention.

## Deferred / out of scope
- Auto-matching conditionals (could add path globs later if manual proves insufficient — `log()` the gap).
- Merging/splitting spine nodes further (e.g. Design+Plan) — backbone approved at 7.
