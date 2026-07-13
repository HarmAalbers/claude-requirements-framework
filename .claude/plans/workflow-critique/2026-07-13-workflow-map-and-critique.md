# The Full Nudged Workflow — Map and Critique

**Date:** 2026-07-13 · **Tier:** deep (brainstorming) · **Status:** all decisions settled — awaiting user review of this file

Goal: a code-grounded map of the complete workflow the framework nudges, then a critique
of its gaps/friction, converging on design decisions. Grounded against `hooks/lib/config.py`
(WORKFLOW_DEFAULTS, `config.py:911`), this repo's `.claude/requirements.yaml` +
`.claude/requirements.local.yaml`, and `hooks/lib/derive_phase.py`.

## Part 1 — The Map (verified 2026-07-13)

### Always-on scaffolding (before any phase)

- **SessionStart** injects the "N/10 satisfied" banner + recommended next steps.
- **UserPromptSubmit** every turn: lazy-dev ladder + brainstorm-before-planning nudge
  (until `design_approved`).
- **Safety guards** on Edit/Write (advisory under `enforcement: nudge`):
  `protected_branch`, `branch_size_limit` (warn 250 / block 400), `single_session_per_project`.
- `/req` conductor + statusline: current phase = first phase (declared order) whose gate
  is unsatisfied (`derive_phase.py:126`).

### The 7-node backbone (ADR-022), per branch

| # | Phase | Type | Nudged command | Gate (scope) | Trip-wire |
|---|-------|------|----------------|--------------|-----------|
| 1 | design | spine | `/brainstorming` (+ plan-mode entry) | `design_approved` (session) | Edit/Write |
| 2 | plan | spine | `/writing-plans` | `plan_written` (session) | Edit/Write |
| 3 | validate | team | `/arch-review` (6 agents), cond. `/codex-review` | `plan_validated` (session) | Edit/Write |
| 4 | build | spine | `/executing-plans`; loop `/pre-commit` per commit | `implementation_done` (marker, `trigger_tools: []`); loop `pre_commit_review` (single_use) | `git commit` re-arms loop |
| 5 | review | team | `/deep-review` (or `/v3-review`), cond. `/codex-review` | `pr_reviewed` (single_use) | `gh pr create` |
| 6 | verify | spine | `/verification-before-completion` | `verified` (single_use) | `git push` |
| 7 | ship | spine | `/finishing-a-development-branch` | — (gateless) | — |

### Cross-cutting mechanics

- Auto-satisfy: PostToolUse[Skill] flips the mapped gate when the skill completes;
  state per branch at `<git-common-dir>/requirements/<branch>.json`.
- Stop hook re-verifies session-scoped gates (`verify_scopes: [session]`).
- SessionStart carry-over: session-scope satisfactions carried from a session ended
  ≤300s ago (`requirements.py:597`).
- SessionEnd: clears pause, session-learning prompt, Langfuse trace.
- Everything fail-open; `enforcement: nudge` = advisories + once-per-phase nudge chain.

## Part 2 — Critique (tension points)

### A. Phase order vs trip-wire order disagree — DECIDED: verify becomes a loop

Backbone: Review → Verify. Trip-wires: `verified` on `git push`, `pr_reviewed` on
`gh pr create` — real flow pushes before PR, so trip-wires fire Verify → Review.

**Investigation (2026-07-13):**
- The verify *skill* is a cross-cutting discipline ("no completion claims without fresh
  evidence — ALWAYS before commits/PRs/task switches"), not a phase activity.
- The `verified` *gate* is `single_use`, trips on every `git push`, re-armed per push —
  mechanically the ADR-022 **loop** pattern, yet modeled as spine phase 6.
- Verification already happens at build checkpoints, per push (the gate), and at Ship
  (`finishing-a-development-branch` Step 1 re-runs the full test suite before offering
  merge options). The phase slot adds only a nudge position — and causes the contradiction.
- **Doc drift found:** `verification-before-completion/SKILL.md` says "guidance-only:
  does not auto-satisfy any requirement", but project config wires it as
  `satisfied_by_skill` for `verified`. Fix the skill doc when implementing.

**Decision (2026-07-13): drop the verify spine node; attach
`{gate: verified, skill: verification-before-completion, on: push}` as a loop on the
build node (trip-wires are requirement-level, so the backstop still fires on pushes in
any phase). Spine becomes 6 nodes: design → plan → validate → build → review → ship.**
Review keeps its spine/team slot — `/deep-review` is genuinely phase-shaped
(11-agent cross-validated branch review with verdict). Ship's built-in test run stays
the terminal check. Rejected: swapping verify before review (evidence staleness,
keeps the flattening error); keep-and-document (papers over the mismatch).

### B. Session scope on branch-level facts — DECIDED: branch scope

`design_approved` / `plan_written` / `plan_validated` are session-scoped but state
branch-level facts. Day-2 sessions on the same branch re-nudge an already-approved
design; the 300s carry-over only covers quick restarts.
**Decision (2026-07-13): promote all three to `scope: branch`.** Verify/pre-commit
loops stay `single_use`. Side effect: dissolves most of E.

### E. Two definitions of "satisfied"

`derive_phase._is_satisfied` (`derive_phase.py:60`) counts ANY session's satisfaction;
the PreToolUse nudge chain checks the CURRENT session. Statusline can say "build" while
the chain re-asks design. Needs one targeted test on whether SessionEnd deletes session
entries. Mostly dissolved by B's branch-scope decision for the early gates; check the
remaining session-scoped gates after B lands.

### C. Workflow doesn't scale down — OPEN

Brainstorming-v2 triages small/standard/deep, but the tier dies inside the skill: a
small-tier task still leaves `plan_written`/`plan_validated` unsatisfied → chain nudges
`/writing-plans` + `/arch-review` for a one-file fix.
Directions: (1) tier flows into gates — small-tier terminal auto-satisfies plan/validate;
(2) tier-aware nudge suppression; (3) do nothing (noise erodes nudge trust — weakest).

**Decision (2026-07-13): (1) — tier flows into gates.** Small tier auto-satisfies
`plan_written` + `plan_validated`, recorded as `satisfied_by: tier:small`, so the derived
phase advances to build and statusline/nudges stay in agreement. Prerequisite machinery:
a tier signal in branch state that the auto-satisfy path can read (e.g. a Claude-runnable
`req tier <small|standard|deep>` marker, modeled on `req pause`; exact mechanism is a
writing-plans decision). Rejected: nudge suppression (creates a new phase-vs-nudge
split); do nothing (nudge noise on trivial work erodes trust in all nudges).

### D. Edge coverage — DECIDED: no wiring changes

- `test-driven-development`, `systematic-debugging`, `receiving-code-review` unwired
  from the backbone. Investigation showed TDD is already threaded through the chain at
  the right (upstream) points: writing-plans bakes "Write the failing test" into the plan
  template (`SKILL.md:77`); arch-review's tdd-validator checks the plan's TDD strategy
  (part of `plan_validated`); executing-plans step 4 + subagent-driven-development
  instruct executors to follow the TDD skill.
- **Decision (2026-07-13): wire nothing.** TDD belongs in design/plan and in executor
  awareness — never as a post-hoc gate after code is written. systematic-debugging and
  receiving-code-review stay ambient (event-driven, triggered by skill description).
  Ship stays gateless — its skill already re-runs the test suite and is terminal.

## Part 3 — Decisions

| Point | Decision | Notes |
|-------|----------|-------|
| B | Promote `design_approved`/`plan_written`/`plan_validated` to `scope: branch` | 2026-07-13 |
| A | Drop verify spine node; verify = loop `on: push` on build; 6-node spine | 2026-07-13; also fix verify SKILL.md auto-satisfy drift |
| C | Small tier auto-satisfies plan_written + plan_validated (`tier:small` marker) | 2026-07-13; tier-signal mechanism → writing-plans |
| D | No wiring changes — TDD already threaded upstream; debugging/review-feedback stay ambient; ship stays gateless | 2026-07-13 |
| E | Re-check after B lands | Targeted test on SessionEnd clearing; branch scope dissolves it for the early gates |

## Part 4 — Resulting target backbone (6-node spine, two loops)

```
Design → Plan → Validate → Build ──────────────→ Review → Ship
[spine]  [spine] [TEAM]     [spine]                [TEAM]   [spine]
                            loop: pre_commit_review (on: commit)
                            loop: verified          (on: push)
```

| Node | Gate (scope) | Skill |
|------|--------------|-------|
| design   | `design_approved` (**branch**)  | `/brainstorming` (small tier also satisfies plan_written + plan_validated via `tier:small`) |
| plan     | `plan_written` (**branch**)     | `/writing-plans` |
| validate | `plan_validated` (**branch**)   | `/arch-review` + cond. `/codex-review` |
| build    | `implementation_done` (marker)  | `/executing-plans`; loops: `/pre-commit` per commit, `/verification-before-completion` per push |
| review   | `pr_reviewed` (single_use)      | `/deep-review` + cond. `/codex-review` |
| ship     | — (gateless)                    | `/finishing-a-development-branch` (re-runs tests) |

Implementation notes for writing-plans:
- Scope migration for the three early gates: session → branch (config defaults +
  examples + this repo's yaml). No compat shim (house rule) — but check WorkflowValidator
  and carry-over logic for session-scope assumptions.
- Verify-as-loop: WORKFLOW_DEFAULTS change + ADR-022 amendment (or new ADR); confirm the
  loop machinery supports two loops on one node; fix verify SKILL.md auto-satisfy drift;
  YAML footgun applies (`"on": push`).
- Tier signal: new `req tier` marker (Claude-runnable, like `req pause`) + auto-satisfy
  reads it on brainstorming completion; brainstorming skill terminal announces it.
- E follow-up test: does SessionEnd delete `sessions[id]` satisfaction entries?
  (`derive_phase._is_satisfied` any-session vs PreToolUse current-session.)
