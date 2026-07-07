# Retrospective — Workflow Phase Re-cut (Typed-Node Backbone)

**Plan:** `.claude/plans/2026-07-07-workflow-phase-recut-plan.md`
**Design:** `.claude/plans/2026-07-07-workflow-phase-recut-design.md`
**Orchestrator prompt:** `.claude/plans/2026-07-07-workflow-phase-recut-orchestrator-prompt.md`
**Branch:** `feat/workflow-phase-recut`
**Baseline commit:** `65461770`
**Head commit:** `797a882d`
**Run date:** 2026-07-07

## 1. Run Summary

| Metric | Value |
|---|---|
| Chunks total | 10 (A1 RED, A1 GREEN, A2, B1, B2, C1, D1×2, D2, F) |
| Chunks dispatched to refactor-executor | 3 (A1, A2, B1) |
| Chunks done by orchestrator directly | 7 (B2, C1, D1×2, D2, E, F) |
| Chunks escalated to investigator | 0 |
| Chunks escalated to user (AskUserQuestion) | 1 (D2 scope-add: migrate `req init` generators) |
| Commits total | 10 |
| Commits per chunk (median) | 1.0 |
| Plan sections edited mid-run | 1 (Task 5 dropped; Task 7 split; D2 added) |
| Test result | 1544/1551 (== 7-failure baseline, 0 net new) |

## 2. Per-chunk Signals

| Chunk | Files touched | Retries | Escalation | Notes |
|---|---|---|---|---|
| A1 RED/GREEN | config.py, test_requirements.py | 0 | no | TDD-split as planned |
| A2 | derive_phase.py, test_requirements.py | 0 | no | — |
| B1 | auto-satisfy-skills.py, test_requirements.py | 0 | no | — |
| B2 | requirements.yaml, examples/*, feature_catalog.py | 0 | no | feature_catalog.py was an unplanned but test-forced addition |
| B3 (message files) | none | — | — | **no-op** — no old-vocab message files existed |
| C1 | handle-prompt-submit.py, brainstorm.py | 0 | no | additive surfacing, largest diff (+138/-34) |
| D1 (test sweep) | test_requirements.py (statusline), requirements-cli.py, handle-session-start.py | 0 | no | split into two commits |
| D2 | feature_selector.py, init_presets.py | 0 | user (AskUserQuestion) | unplanned; no test enforced this vocab |
| F | ADR-022, CLAUDE.md, plugin.json, marketplace.json | 0 | no | docs + bump |

Executor vs. self-execution ratio (3/10) is lower than typical for this skill; the orchestrator judged B2 onward as faster to do directly once the vocabulary-rename pattern was established.

## 3. Cross-chunk Patterns

**Pattern: planned deletion chunk was a no-op.** Task 5 (message files for renamed/removed gates) assumed old-vocab message files existed to delete. None did — the per-gate message loader fails open to `_templates.yaml`, so no gate-specific files had ever been created. The chunk was correctly skipped rather than manufacturing dead files. See §5/§6, slug `plan-assumes-artifact-exists-unverified`.

**Pattern: blast radius underestimated by test coverage.** Two consumers of the old gate vocabulary were missed by the plan's Task 1–4 file list and only surfaced because of test coupling or a manual sweep: `feature_catalog.py` (forced into B2 by a catalog↔config sync test) and `init_presets.py`/`feature_selector.py` (the `req init` generators — no test enforced their vocabulary at all; they were emitting deleted gate names silently until D1's sweep found them, then approved as D2 via AskUserQuestion). The common root cause: the plan's file inventory was scoped to modules with existing vocabulary-assertion tests, not to all string-literal producers of gate names. See slug `vocab-migration-blast-radius-no-test-coverage`.

**Pattern: executor self-commit despite explicit "don't commit" rule.** `refactor-executor.md` already states "Don't commit. The orchestrator commits after review," but the agent has `Bash` in `allowed-tools`, and this run saw inconsistent behavior — some executor dispatches left the working tree for the orchestrator to `stg refresh`, at least one instead ran its own stg/git commit. The rule is unambiguous in prose but not structurally enforced by tool scoping. See slug `executor-self-commit-unenforced`.

## 4. Plan-vs-Reality Gaps

Three deviations from the frozen plan: Task 5 dropped (no-op, confirmed harmless), Task 7 executed as two commits instead of one (test-sweep vs. CLI source-sweep split naturally along file boundaries), and one unplanned scope-add (D2, `req init` generators) approved live via AskUserQuestion rather than being in the original Task list. All three are consistent with Stage-1 inventory (file discovery) being narrower than the actual vocabulary surface — the design doc and plan enumerated files with *tests* referencing gate names, not all files with *string literals* of gate names.

## 5. Recommendations

### Medium severity (ledger only — not yet at rule-of-three)

1. **`plan-template.md`**: Before scheduling a deletion/migration chunk, add a verification step ("confirm the target artifacts exist") rather than assuming prior inventory was exhaustive. Rationale: Task 5 was scheduled against a nonexistent artifact set (this run).
   - learnings.md slug: `plan-assumes-artifact-exists-unverified` (count: 1)
2. **`plan-template.md`**: Stage-1 inventory should include a repo-wide grep for literal vocabulary strings (not just test-covered call sites) before freezing chunk scope. Rationale: `feature_catalog.py` and the `req init` generators both carried the old vocabulary with no enforcing test (this run).
   - learnings.md slug: `vocab-migration-blast-radius-no-test-coverage` (count: 1)
3. **`refactor-executor.md`**: Consider narrowing `allowed-tools` to exclude `git`/`stg` subcommands, or add a pre-flight/post-flight check in the orchestrator prompt that asserts a clean-vs-dirty tree delta matches "no commit made." Rationale: the "don't commit" rule already exists in prose but was not followed uniformly (this run).
   - learnings.md slug: `executor-self-commit-unenforced` (count: 1)

### Out of scope (outside the 5 buckets)

- A bare `on: commit` key in this repo's YAML configs parses as boolean `True` under YAML 1.1 (Norway-problem variant) — must be quoted `"on": commit`. This is a project-specific YAML fact, not an orchestration-process learning; recorded in `.claude/refactor-conventions.md` rather than the ledger.

## 6. Learnings Ledger Entries This Run

All three entries are newly created this run (global ledger — the observations concern the shared plugin templates/agents, not this-repo-only code). None reach rule-of-three; no AskUserQuestion proposal fired this run.

| Slug | Status | Count | Affected artifact | One-line observation |
|---|---|---|---|---|
| `plan-assumes-artifact-exists-unverified` | open | 1 | plan-template.md | Deletion chunk scheduled against an artifact set that didn't exist |
| `vocab-migration-blast-radius-no-test-coverage` | open | 1 | plan-template.md | Inventory scoped to test-covered files misses untested vocabulary producers |
| `executor-self-commit-unenforced` | open | 1 | refactor-executor.md | "Don't commit" rule not structurally enforced; violated inconsistently |

## 7. Further reading

- `~/.claude/refactor-orchestration/learnings.md` — global ledger (seeded this run from the plugin template; 3 new entries appended)
- `.claude/refactor-conventions.md` — new, this run (YAML `on:` key gotcha)
- ADR-022 (`docs/adr/ADR-022-workflow-phase-recut-typed-backbone.md`) — design record for the typed backbone this refactor implemented
