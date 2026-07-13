# ADR-023: Six-Node Backbone Re-cut — Verify as a Build Loop, Branch-Scoped Early Gates, Tier Signal

**Status:** Accepted
**Date:** 2026-07-13
**Amends:** ADR-022 (typed 7-node backbone) — the node set, one scope decision, and a schema key change
**Related:** the nudge-only overhaul (`enforcement: nudge`), brainstorming-v2 (tiered triage router)

## Context

A code-grounded map of the full nudged workflow (`.claude/plans/workflow-critique/2026-07-13-workflow-map-and-critique.md`, verified against `hooks/lib/config.py:WORKFLOW_DEFAULTS`, this repo's `requirements.yaml` + `requirements.local.yaml`, and `hooks/lib/derive_phase.py`) surfaced four tensions in the ADR-022 backbone:

- **A — phase order vs trip-wire order disagree.** The backbone runs Review → Verify, but the trip-wires fire Verify → Review: `verified` trips on `git push`, `pr_reviewed` on `gh pr create`, and the real flow pushes before opening a PR. Investigation showed the `verified` gate is `single_use`, trips on *every* push, and is re-armed per push — mechanically the ADR-022 **loop** pattern, yet modeled as a spine phase. Verification already happens at build checkpoints, per push (the gate), and at Ship (`finishing-a-development-branch` re-runs the full suite before offering merge options). The spine slot added only a nudge position — and caused the contradiction. Also found: `verification-before-completion/SKILL.md` claimed "guidance-only: does not auto-satisfy any requirement" while project config wired it as `satisfied_by_skill` for `verified` (doc drift).
- **B — session scope on branch-level facts.** `design_approved` / `plan_written` / `plan_validated` were `session`-scoped but record branch-level facts. Day-2 sessions on the same branch re-nudged an already-approved design; the 300s carry-over only covered quick restarts.
- **C — the workflow doesn't scale down.** brainstorming-v2 triages small/standard/deep, but the tier died inside the skill: a small-tier one-file fix still left `plan_written` / `plan_validated` unsatisfied, so the chain nudged `/writing-plans` + `/arch-review` for trivial work — eroding trust in all nudges.
- **D — edge coverage.** `test-driven-development`, `systematic-debugging`, `receiving-code-review` are unwired from the backbone.

## Decision

### A — Drop the verify spine node; verify becomes a per-push loop on build

The 7-node spine becomes **6 nodes**: Design → Plan → Validate → Build → Review → Ship. The `verified` gate is unchanged (still `single_use`, still trips on `git push`); it is re-attached as a **loop on the build node**:

```
Design → Plan → Validate → Build ─────────────→ Review → Ship
[spine]  [spine] [TEAM]     [spine]                [TEAM]   [spine]
                            loop: pre_commit_review (on: commit)
                            loop: verified          (on: push)
```

Trip-wires are requirement-level, so the `verified` backstop still fires on pushes in any phase. Review keeps its spine/team slot — `/deep-review` is genuinely phase-shaped (a cross-validated branch review with a verdict). Ship's built-in test run stays the terminal check. The verify SKILL.md auto-satisfy drift is corrected in the same change.

**Schema change (breaking, no compat shim):** a build node lists its loops under a **`loops`** list (`[{gate, skill, on}, ...]`), replacing ADR-022's singular `loop` mapping. `WorkflowValidator` hard-errors on the removed `loop` key and points at `loops`; a config using `loop` fails validation and falls back to defaults.

### B — The three early gates go branch-scoped

`design_approved` / `plan_written` / `plan_validated` are promoted to `scope: branch` (config-only; the satisfy path already honors `config.get_scope`). They now persist across sessions on the same branch, so day-2 sessions don't re-nudge. The per-commit / per-push loop gates stay `single_use`; `implementation_done` deliberately stays `session` (day-2 build sessions *should* re-nudge "continue executing").

### C — Small tier flows into the plan/validate gates

A new branch-level **tier signal** is recorded by a Claude-runnable `req tier <small|standard|deep>` command (modeled on `req pause` — it only annotates state; the auto-satisfy hook decides what it means). When `brainstorming` completes on a branch marked `tier=small`, the auto-satisfy path also satisfies `plan_written` + `plan_validated`, recorded with `method='tier'` so state shows *why* they flipped. The derived phase then advances to build and the statusline/nudges stay in agreement. brainstorming's triage step announces and records the tier.

### D — No wiring changes

TDD is already threaded upstream (writing-plans bakes "write the failing test" into the plan template; arch-review's tdd-validator checks the plan's TDD strategy; executing-plans + subagent-driven-development instruct executors to follow the TDD skill) — never as a post-hoc gate after code is written. `systematic-debugging` and `receiving-code-review` stay ambient (event-driven via skill description). Ship stays gateless.

## Consequences

- The backbone is 6 nodes; the gate vocabulary is **unchanged** (still 7 gates) — only the verify *node* was removed, not the `verified` gate.
- `PHASE_GATES` (the `derive_phase` fail-open fallback) drops `("verify", "verified")` to stay byte-for-byte in sync with `WORKFLOW_DEFAULTS`.
- Existing project configs that use the singular `loop` key get a hard validation error pointing at `loops` (house rule: no shims). Migrating other projects' configs is out of scope — they get the error.
- `req tier` is additive; users allowlist it like `req pause`. No permission-plumbing changes.

## Rejected alternatives

- **Swap verify before review** (Verify → Review): keeps the flattening error and introduces evidence staleness (verifying before the review changes anything).
- **Keep the verify node and document the mismatch**: papers over a real phase-vs-trip-wire contradiction.
- **Tier-aware nudge suppression** (instead of flowing tier into gates): creates a new phase-vs-nudge split — the statusline would still derive "plan" while the nudge stays silent.
- **Do nothing for small tiers**: nudge noise on trivial work erodes trust in all nudges (weakest option).

## Follow-up

- **E** (two definitions of "satisfied": `derive_phase._is_satisfied` counts any session; the PreToolUse chain checks the current session) is mostly dissolved by B's branch-scope for the early gates. After B, the only backbone gate still session-scoped is `implementation_done`; the asymmetry there is pinned by a characterization test and a fix is deliberately deferred (out of scope).
