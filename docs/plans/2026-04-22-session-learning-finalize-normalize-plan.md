# Session-Learning Finalize + Normalize — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use requirements-framework:executing-plans to implement this plan task-by-task.

**Goal:** Fix two data-collection bugs in the session learning system so session metrics files are properly finalized and team event hooks write to canonical session files.

**Architecture:** Two independent one-line-ish fixes in the hook lifecycle:
1. `handle-session-end.py` adds a new step that calls `metrics.finalize_session()` before the Obsidian block.
2. `handle-task-completed.py` and `handle-teammate-idle.py` call `normalize_session_id()` on the raw stdin value before constructing `SessionMetrics`.
Both fixes preserve the existing fail-open discipline: each new block has its own try/except, errors log and never propagate.

**Tech Stack:** Python 3, stdlib only. Integration-style tests via `subprocess.run` piping JSON to hook scripts inside a `tempfile.TemporaryDirectory`.

---

## Design

### Bug #1 — `finalize_session()` never called

**Root cause.** `hooks/handle-session-end.py:130-143` constructs a `SessionMetrics` instance, calls `get_summary()`, and hands the summary to Obsidian. It never calls `metrics.finalize_session()` (defined at `hooks/lib/session_metrics.py:551`). Every session file has `ended_at: null` and `duration_seconds: null` forever.

**Evidence.** All 149 files in `.git/requirements/sessions/` have `ended_at: null`. Obsidian session notes also carry null durations as a downstream consequence.

**Fix.** New step 3.5 inserted between current step 3 (WIP tracking, ends line 128) and step 4 (Obsidian, begins line 130), with its own try/except.

### Bug #2 — team hooks skip `normalize_session_id()`

**Root cause.** Two hooks read the raw session_id from stdin and pass it directly to `SessionMetrics`:
- `hooks/handle-task-completed.py:79` — `session_id = input_data.get('session_id', '')`
- `hooks/handle-teammate-idle.py:77` — `session_id = input_data.get('session_id', '')`

When Claude Code provides a full UUID, these hooks write to `sessions/<uuid>.json` while every other hook writes to `sessions/<8char>.json`. This leaves 45 orphan UUID files in the current directory.

**Fix.** Import `normalize_session_id` from `session` and apply it after the empty-check in both hooks.

### Out of Scope

- 45 orphan UUID files — one-time migration, separate task.
- Branch refresh bug, empty `git.commits`, `satisfied_at` causality, PostToolUseFailure coverage — follow-up issues.
- Changes to `session_metrics.py` — `finalize_session()` already exists and is tested.

---

## Task 1: Fix Bug #1 — SessionEnd must finalize metrics

**Files:**
- Test: `hooks/test_requirements.py` (add new test near existing `test_session_end_hook` at line 2753)
- Modify: `hooks/handle-session-end.py` (add new step 3.5 between lines 128 and 130)
- Deploy: `./sync.sh deploy`

### Step 1: Write the failing test

Add `test_session_end_finalizes_metrics` to `hooks/test_requirements.py` immediately after `test_session_end_hook`. Register in `main()`.

The test must:
- Initialize a git repo in a tempdir.
- Create `.claude/requirements.yaml` with minimal config.
- Pre-create an unfinalized session metrics file at `.git/requirements/sessions/<id>.json` with `ended_at: null`.
- Pipe SessionEnd JSON to the hook script via `subprocess.run`.
- Assert `ended_at` and `duration_seconds` are populated after the hook runs.

Follow the existing `test_session_end_hook` pattern exactly (tempdir, subprocess, JSON stdin).

### Step 2: Run test — verify RED

```bash
cd /Users/harm/Tools/claude-requirements-framework
./sync.sh deploy
python3 hooks/test_requirements.py 2>&1 | grep -A 2 "finalizes metrics"
```

Expected: `SessionEnd sets ended_at` → FAIL.

### Step 3: Write the implementation

In `hooks/handle-session-end.py`, insert between current line 128 and line 130 (after WIP tracking, before Obsidian):

```python
        # 3.5. Finalize session metrics (sets ended_at + duration_seconds)
        try:
            from session_metrics import SessionMetrics
            metrics = SessionMetrics(session_id, project_dir, branch)
            metrics.finalize_session()
            logger.debug("Session metrics finalized")
        except Exception as e:
            logger.debug("Session metrics finalization failed (fail-open)", error=str(e))
```

Leave the Obsidian block (lines 130-143) unchanged.

### Step 4: Run test — verify GREEN

```bash
./sync.sh deploy
python3 hooks/test_requirements.py 2>&1 | grep -A 2 "finalizes metrics"
```

Expected: PASS.

### Step 5: Run full suite

```bash
python3 hooks/test_requirements.py 2>&1 | tail -15
```

Expected: no regressions.

### Step 6: Commit (atomic)

```bash
git add hooks/handle-session-end.py hooks/test_requirements.py
git commit -m "fix(session): call finalize_session() in SessionEnd hook"
```

Full commit message body explains the bug, evidence (149 files with ended_at=null), and rationale for placing finalize before Obsidian.

---

## Task 2: Fix Bug #2a — TaskCompleted must normalize session_id

**Files:**
- Test: `hooks/test_requirements.py` (add near existing `test_task_completed_hook` at line 8575)
- Modify: `hooks/handle-task-completed.py` (lines 36, 79)

### Step 1: Write the failing test

Add `test_task_completed_normalizes_session_id`. Pipe a UUID session_id; assert `sessions/<8char>.json` exists and `sessions/<uuid>.json` does not.

Use test UUID `cad0ac4d-3933-45ad-9a1c-14aec05bb940` → expected short `cad0ac4d`.

### Step 2: Run test — verify RED

### Step 3: Write the implementation

In `hooks/handle-task-completed.py`:
- Line 36 area: add `from session import normalize_session_id`
- Line 79: rename to `raw_session = input_data.get('session_id', '')`, move empty-check up, then `session_id = normalize_session_id(raw_session)`.

### Step 4: Run test — verify GREEN

---

## Task 3: Fix Bug #2b — TeammateIdle must normalize session_id (paired commit with Task 2)

**Files:**
- Test: `hooks/test_requirements.py` (add near existing `test_teammate_idle_hook` at line 8425)
- Modify: `hooks/handle-teammate-idle.py` (lines 35, 77)

### Steps 1-4

Mirror Task 2 pattern exactly, for the teammate-idle hook.

### Step 5: Run full suite

```bash
python3 hooks/test_requirements.py 2>&1 | tail -15
```

### Step 6: Commit Bug #2 (atomic, both hooks together)

```bash
git add hooks/handle-task-completed.py hooks/handle-teammate-idle.py hooks/test_requirements.py
git commit -m "fix(hooks): normalize session IDs in team event hooks"
```

---

## Task 4: Sync check + final verification

```bash
./sync.sh status
python3 ~/.claude/hooks/test_requirements.py 2>&1 | tail -15
```

---

## Notes for the implementer

- Each commit must pass the full test suite.
- Deploy via `./sync.sh deploy` after every code change — tests run against deployed hooks at `~/.claude/hooks/`.
- Don't use `--no-verify`; if pre-commit hooks fail, read and fix.

---

## Preparatory Refactoring

Three refactoring questions were considered against the principle *"first refactor to make the change easy, then make the change"* — weighed against the anti-pattern of over-refactoring a 2-line fix.

### Question 1 — Extract `extract_session_id(input_data)` helper? **SKIP**

**Finding.** 13 of 15 hooks already use this canonical 3-line pattern:
```python
raw_session = input_data.get('session_id')
if not raw_session:
    return 0
session_id = normalize_session_id(raw_session)
```
Examples: `handle-tool-failure.py:54-58`, `handle-plan-exit.py:73`, `handle-stop.py:163`, `handle-pre-compact.py:45`, `handle-session-end.py:49-57`, `check-requirements.py:242`, etc.

The two buggy hooks (`handle-task-completed.py:79`, `handle-teammate-idle.py:77`) are **outliers** that drifted from the existing convention. The fix is conforming to the canonical pattern, not inventing a new one.

**Why skip the helper.**
- Failure semantics vary across hooks (some log+error, some silently `return 0`, some log warning and continue). A single `extract_session_id()` would need a strategy parameter or would force behavior changes in all 13 sites.
- Three lines of recognizable code are easier to read than `session_id = extract_session_id(input_data)` that hides a null-check + normalization + implicit return value.
- The abstraction would need to be retro-applied to 13 other hooks to be consistent — turning a 2-line fix into a 13-hook refactor.

**Decision.** Apply the canonical inline pattern to the two outlier hooks. Matches what every other hook already does. **Zero new abstractions.**

### Question 2 — Share one `SessionMetrics` instance between finalize and Obsidian blocks? **YES (small win)**

**Finding.** The proposed plan creates a `SessionMetrics` instance in the new step 3.5, then the Obsidian block at line 138 creates a **second** `SessionMetrics(session_id, project_dir, branch)` with identical constructor args to call `get_summary()`.

This is worse than duplication — it's a **correctness smell**: `finalize_session()` mutates `ended_at` and `duration_seconds` on the file. If the Obsidian block instantiates a fresh `SessionMetrics`, it must re-read the file to see the finalized values. If it reads from in-memory state, it sees stale nulls. Sharing the instance makes the happens-before relationship explicit.

**Recommended adjustment to Task 1 Step 3.** Hoist the `SessionMetrics` import and instantiation to just before step 3.5, reuse in step 4:

```python
# 3.5. Finalize session metrics (sets ended_at + duration_seconds)
metrics = None
try:
    from session_metrics import SessionMetrics
    metrics = SessionMetrics(session_id, project_dir, branch)
    metrics.finalize_session()
    logger.debug("Session metrics finalized")
except Exception as e:
    logger.debug("Session metrics finalization failed (fail-open)", error=str(e))

# 4. Obsidian session logging: finalize session note
try:
    obsidian_enabled = config and config.get_hook_config('obsidian', 'enabled', False)
    if obsidian_enabled:
        from obsidian import ObsidianSessionLogger
        if metrics is None:
            from session_metrics import SessionMetrics
            metrics = SessionMetrics(session_id, project_dir, branch)
        obs_logger = ObsidianSessionLogger(config)
        summary = metrics.get_summary()
        obs_logger.finalize_in_background(session_id, project_dir, summary)
        logger.debug("Obsidian finalization spawned in background")
except Exception as e:
    logger.debug("Obsidian finalization failed (fail-open)", error=str(e))
```

The `metrics is None` fallback preserves fail-open: if finalize's try-block exploded, Obsidian still gets a fresh summary (possibly with null `ended_at`, but Obsidian already tolerated that state).

**Tradeoff.** Slightly more code (~3 extra lines) vs. eliminating duplicate instantiation + making the finalize→summary ordering an explicit dependency. **Net win** because it matches the natural data-flow narrative.

### Question 3 — Other structural improvements? **NONE REQUIRED**

Surveyed the three affected files for smells:

- **Import patterns.** `handle-task-completed.py` and `handle-teammate-idle.py` already do late imports for `SessionMetrics` inside the try-block. Adding one more import line (`normalize_session_id`) at module top fits existing style.
- **Fail-open idiom.** Both team hooks already wrap `SessionMetrics` calls in bare `try/except` with logger. Adding `normalize_session_id()` outside that try is fine — `normalize_session_id()` is pure, handles all input types (including empty strings), and cannot raise on documented inputs.
- **`append_progress_log` duplication** across `handle-task-completed.py` and `handle-teammate-idle.py` (lines 41-53 in both files) is a real code smell, but **orthogonal to this fix** and would create a scope-creep commit. File as a follow-up refactor, not a preparatory one.

### Summary

| Proposal | Verdict | Rationale |
|---|---|---|
| Extract `extract_session_id()` helper | Skip | Canonical 3-line pattern already in 13 hooks; adding helper requires retrofitting all 13. |
| Share `SessionMetrics` instance in SessionEnd | Adopt (minor Task 1 adjustment) | Correct happens-before semantics + eliminates duplicate construction for ~3 lines. |
| Deduplicate `append_progress_log` | Skip (for this plan) | Real smell, but orthogonal scope creep. File as follow-up. |

**Bottom line.** The original 2-line fixes are the right shape. One small Task 1 tweak (reuse the `SessionMetrics` instance) is worth adopting for correctness reasons. Everything else is over-refactoring.
