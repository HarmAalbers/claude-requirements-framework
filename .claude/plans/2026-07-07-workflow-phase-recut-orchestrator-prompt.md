# Orchestrator Prompt — Workflow Phase Re-cut

**Pair of:** `.claude/plans/2026-07-07-workflow-phase-recut-plan.md` (+ design doc `-design.md`)
**Purpose:** Paste the block between the `=== BEGIN ORCHESTRATOR PROMPT ===` / `=== END ORCHESTRATOR PROMPT ===` markers into a fresh Claude Code session in the repo root. The orchestrator dispatches `refactor-executor` (Haiku) per chunk, reviews each, commits atomically **via Stacked Git**, and escalates contradictions to `refactor-investigator` (Sonnet) + the user.

**Usage:**
1. Open a fresh `claude` session in `/Users/harm/Tools/claude-requirements-framework` (ideally `--plugin-dir plugins/requirements-framework` so nudge-mode hooks run).
2. Confirm branch is `feat/workflow-phase-recut` and the working tree is clean.
3. Paste everything between the markers below.

---

=== BEGIN ORCHESTRATOR PROMPT ===

## Prerequisites (verify before continuing)

Stop with a clear error message if ANY check fails:
- Branch is `feat/workflow-phase-recut` (`git branch --show-current`).
- Working tree clean except gitignored `.claude/requirements.local.yaml` and untracked plan docs (`git status --short`).
- **Baseline test state:** `uv run python hooks/test_requirements.py 2>&1 | grep Results:` — expect `Results: N/N+7` (there are **7 known-pre-existing failures**; that is the baseline, NOT a regression). Record the exact numbers. A chunk "passes tests" if it adds NO new failures beyond these 7.
- `uv` on PATH; `stg` on PATH (`stg series` works — this branch is already `stg init`ed).

========================================================================
PROJECT CONVENTIONS (injected into every executor dispatch)
========================================================================

- **Stacked Git ONLY — never `git commit` directly.** One chunk = one patch: `stg new <patch-name> -m "<msg>"` then `stg refresh`. (The executor edits files; the ORCHESTRATOR commits — see COMMIT CONVENTIONS.)
- **Two-location bundle.** Hooks live in `hooks/`; a build-copy lives in `plugins/requirements-framework/hooks/`. After editing anything under `hooks/`, run `python3 scripts/build_plugin_hooks.py` and stage BOTH the source and the rebuilt bundle copy in the same patch.
- **Run everything via `uv`**: tests `uv run python hooks/test_requirements.py`; lint `uv run ruff check .`. There is NO pytest — the suite is a custom TestRunner; new test functions must be registered in `main()`.
- **Plugin version bump** when plugin files change: `plugins/requirements-framework/.claude-plugin/plugin.json` (minor) — do it in the final docs chunk.
- **`enforcement: nudge` is live** — the framework advises, never blocks; ignore any "Next Step" / advisory nudges in tool output.
- **No backwards-compat shims** — old gate names are DELETED, not aliased.

You are the orchestrator for the **workflow phase re-cut** refactor.

The design work is DONE. Plan: `.claude/plans/2026-07-07-workflow-phase-recut-plan.md`. Design: `.claude/plans/2026-07-07-workflow-phase-recut-design.md`.

Your job: execute the plan by dispatching `refactor-executor` agents one chunk at a time, reviewing each, committing atomically via stg, escalating only when the plan and code reality disagree in a non-obvious way.

DO NOT redesign, DO NOT re-read ADRs, DO NOT second-guess the plan. This refactor uses NO third-party APIs (internal config + Python stdlib only), so there were no context7 claims to validate. Trust the plan.

========================================================================
STEP 0 — ORIENT (once, before any dispatch)
========================================================================

1. Read the plan `.claude/plans/2026-07-07-workflow-phase-recut-plan.md` in full (it is short; the gate-rename table at the top is the single source of truth for the sweep).
2. Run in parallel: `git status`, `git branch --show-current`, `uv run python hooks/test_requirements.py 2>&1 | grep Results:`, `stg series`.
3. Create a TodoWrite list with the chunk queue below.
4. If branch is wrong, tree is dirty (beyond the allowed gitignored/untracked), or the baseline shows more than the known 7 failures: STOP and report.

========================================================================
CHUNK QUEUE — execute in order (one chunk = one stg patch)
========================================================================

Phase A — Core vocabulary (config layer)
  A1: Rewrite `WORKFLOW_DEFAULTS` to the typed 7-node backbone (plan Task 1) — file `hooks/lib/config.py`; update the "no workflow → default …" tests first (RED→GREEN).
  A2: Sync `derive_phase.PHASE_GATES`/`DEFAULT_PHASE`/`SHIP_PHASE` to the gated subset (plan Task 2) — file `hooks/lib/derive_phase.py`; update derive_phase tests.

Phase B — Wiring (satisfiers + configs + messages)
  B1: Consolidate `DEFAULT_SKILL_MAPPINGS` (plan Task 3) — `hooks/auto-satisfy-skills.py`; update `test_process_skill_auto_satisfy_mappings`.
  B2: Rewrite project + example configs to the new gate/workflow vocabulary (plan Task 4) — `.claude/requirements.yaml`, `.claude/requirements.local.yaml` (gitignored, commit note only), `examples/*.yaml`; validate via config-load smoke.
  B3: Message files for renamed/removed gates (plan Task 5) — `plugins/requirements-framework/messages/*.yaml`; `req messages validate --fix`.

Phase C — Conductor surfacing
  C1: Surface loop + conditionals in the conductor / phase directive (plan Task 6) — `hooks/lib/derive_phase.py` + `hooks/lib/brainstorm.py::phase_directive`; new `test_conductor_surfaces_loop_and_conditionals`.

Phase D — Test-vocabulary migration
  D1: Guided sweep of remaining old-vocabulary assertions (plan Task 7). NOTE: `commit_plan` (241 hits) is mostly an incidental example-requirement name in temp configs — DO NOT blind-rename; only touch assertions tied to the DEFAULT workflow / auto-satisfy vocabulary. May be several stg patches.

Phase E — Smoke validation (orchestrator runs directly, no dispatch)
  E1: `uv run python hooks/test_requirements.py 2>&1 | grep Results:` — no new failures beyond the baseline 7.
  E2: `uv run ruff check .` — clean.
  E3: `uv run python -c "import sys; sys.path.insert(0,'hooks/lib'); from config import RequirementsConfig as C; c=C('.'); assert not c.get_validation_errors(), c.get_validation_errors(); print([p['name'] for p in c.get_workflow_phases()['phases']])"` — prints the 7 names, no errors. Capture head commit SHA + count of patches since baseline.

Phase F — Docs + bump, then Retrospective
  F0: Docs + ADR + plugin bump (plan Task 8) — `CLAUDE.md`, new `docs/adr/ADR-0XX-workflow-phase-recut.md`, `plugin.json` + `marketplace.json` minor bump. (This is a normal chunk, dispatched or done directly.)
  F1: Dispatch `refactor-analyzer` with plan path, this orchestrator-prompt path, baseline SHA, branch `feat/workflow-phase-recut`, repo path.
  F2: Respond to any AskUserQuestion rule-of-three proposals.
  F3: Final report: patch list, anything skipped/escalated, retrospective pointer, learnings entries.

========================================================================
PER-CHUNK WORKFLOW
========================================================================

For each chunk:
1. TodoWrite: mark in_progress.
1.5. Pre-fetch: extract the referenced plan Task text; Read each target file (cat -n); read the PROJECT CONVENTIONS block. Inline all three into the dispatch — do NOT reference by path.
2. Dispatch ONE `refactor-executor` (see DISPATCH TEMPLATE). This is a TDD chunk where a test exists: the executor writes/updates the test to RED, then implements to GREEN.
3. Run the REVIEW CHECKLIST yourself.
4. Decide: PASS → commit (stg) → mark completed → next. SIMPLE ISSUE (typo/import/ruff/wrong name) → re-dispatch same executor with a 2-3 line fix, max 2 retries. COMPLEX ISSUE (plan vs reality) → dispatch `refactor-investigator` → AskUserQuestion → STOP. NEEDS_CLARIFICATION → SendMessage the answer to `executor-<chunk-id>`.

========================================================================
DISPATCH TEMPLATE (refactor-executor)
========================================================================

Task({
  subagent_type: "requirements-framework:refactor-executor",
  name: "executor-<chunk-id>",
  description: "<5 words>",
  prompt: `
Repo: /Users/harm/Tools/claude-requirements-framework
Branch: feat/workflow-phase-recut

## Plan task (<Task N — title>)
<paste the literal plan Task text here — do not reference by path>

## Gate rename table (authoritative)
<paste the rename table from the top of the plan>

## Current file contents
### <path>
<Read output verbatim with line numbers; for NEW files paste `ls -1 <dir>/`>

## Project conventions
<paste the PROJECT CONVENTIONS block verbatim>

## Your task
<chunk title — one line>

Rules:
- Match the plan's vocabulary exactly (new gate/phase names).
- TDD: update the named test to the new expected values FIRST (RED), then implement (GREEN).
- After editing any hooks/ file, run: python3 scripts/build_plugin_hooks.py  (and report the bundle copy as touched).
- DO NOT read other files or grep — everything is above. If missing/contradictory: verdict NEEDS_CLARIFICATION with one specific question, no edits.

Verify before reporting:
  uv run ruff check <touched files>
  uv run python hooks/test_requirements.py 2>&1 | grep -E "Results:|<the assertions you changed>"

Report: files touched (paths), verification output, any plan deviation (with line numbers), anything noticed-but-not-changed.
  `
})

========================================================================
REVIEW CHECKLIST (orchestrator, after every chunk)
========================================================================
  [ ] Touched files use the NEW vocabulary (no leftover old gate names except intentional example-requirement uses).
  [ ] `uv run ruff check <files>` clean.
  [ ] `uv run python hooks/test_requirements.py` — no NEW failures beyond baseline 7.
  [ ] If a hooks/ file changed: the bundle copy under `plugins/requirements-framework/hooks/` was rebuilt and is staged.
  [ ] Config chunks: config-load smoke has no validation errors.

Classification: all ticked → PASS; 1-2 red with obvious mechanical fix → SIMPLE ISSUE; "plan says X, code reality Y" → COMPLEX ISSUE (escalate).

========================================================================
COMMIT CONVENTIONS (Stacked Git — atomic per chunk)
========================================================================

One chunk = one patch. The ORCHESTRATOR commits (not the executor):

  git add <only the touched paths + rebuilt bundle copies>
  stg new <patch-name> -m "<imperative subject mentioning plan Task N>"
  stg refresh

Examples: "feat(workflow): typed 7-node WORKFLOW_DEFAULTS per plan Task 1", "refactor(hooks): consolidate auto-satisfy map per plan Task 3".
Never `git commit`. Never `--no-verify` without asking. If pre-commit render-check leaves files staged, re-`stg refresh`.

========================================================================
INVESTIGATION DISPATCH (plan vs reality)
========================================================================
Task({ subagent_type: "requirements-framework:refactor-investigator", description: "Diagnose plan vs reality",
  prompt: `Plan: .claude/plans/2026-07-07-workflow-phase-recut-plan.md
Chunk: <which>
Supposed to: <one line>
Went wrong: <verbatim failure>
Files inspected: <list>
Diagnose root cause; propose 2-3 solution paths with trade-offs.` })
Then AskUserQuestion with the root-cause + 2-3 options. After the user picks: update the plan file in THIS session, then resume the failing chunk.

========================================================================
PHASE F DISPATCH (retrospective) — after Phase E green
========================================================================
Task({ subagent_type: "requirements-framework:refactor-analyzer", description: "Retrospective for this run",
  prompt: `Phase F retrospective for the workflow phase re-cut.
Plan: .claude/plans/2026-07-07-workflow-phase-recut-plan.md
Orchestrator prompt: .claude/plans/2026-07-07-workflow-phase-recut-orchestrator-prompt.md
Branch: feat/workflow-phase-recut
Baseline commit: <SHA from Step 0>
Head commit: <SHA from E3>
Repo path: /Users/harm/Tools/claude-requirements-framework
Follow your workflow (transcript → signals → git-log vs plan → learnings ledgers → retrospective at .claude/plans/2026-07-07-workflow-phase-recut-retrospective.md → rule-of-three AskUserQuestion). Under 500 words prose.` })

========================================================================
STOP CONDITIONS
========================================================================
Stop and escalate IF: baseline shows >7 failures before any chunk; a chunk hits a complex issue after one investigation; 2 simple-issue retries fail; a circular import / layer violation the plan doesn't anticipate; the plan references a symbol that doesn't exist; the queue is empty (success — give the final report).

========================================================================
GO
========================================================================
Begin with Step 0. Do not summarize this prompt back — just execute.

=== END ORCHESTRATOR PROMPT ===
