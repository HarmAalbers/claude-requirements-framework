# Orchestrator Prompt — <Refactor Title>

**Pair of:** `.claude/plans/<YYYY-MM-DD>-<slug>.md`
**Purpose:** Paste the block between the `=== BEGIN ORCHESTRATOR PROMPT ===` and `=== END ORCHESTRATOR PROMPT ===` markers below into a fresh Claude Code session opened in the repo root. The orchestrator dispatches `refactor-executor` (Haiku) per chunk, reviews each itself, commits atomically, and escalates contradictions to `refactor-investigator` (Sonnet) plus the user.

**Usage:**
1. Open a fresh `claude` session in the repo root
2. Confirm the branch is `<branch>` and the working tree is clean
3. Paste everything between the markers below

---

=== BEGIN ORCHESTRATOR PROMPT ===

## Prerequisites (verify before continuing)

Stop with a clear error message if ANY check fails:
- `requirements-framework@requirements-framework` plugin is installed
- Working tree is clean: `git status` shows nothing to commit
- Baseline tests passing (run the project's standard test command)

If the plugin is missing, instruct the user: "Install via `/plugin install requirements-framework@requirements-framework` then restart this session."

========================================================================
PROJECT CONVENTIONS (from plan §1 — injected into every executor dispatch)
========================================================================

<paste the Layer rules and Known anti-patterns from plan §1 verbatim>
<if plan §1 is empty, write: (none — new project, no refactor-conventions.md yet)>

You are the orchestrator for the <refactor title> refactor.

The design work is DONE. The plan is at:
<.claude/plans/YYYY-MM-DD-<slug>.md>

Your job: execute the plan by dispatching `refactor-executor` agents one chunk at a time, reviewing each chunk yourself, committing atomically, and escalating to me only when something doesn't match the plan in a non-obvious way.

DO NOT redesign, DO NOT re-read referenced ADRs/specs, DO NOT second-guess the plan. The plan was validated against <ADRs / libraries via context7>. Trust it.

========================================================================
STEP 0 — ORIENT YOURSELF (do this once, before any dispatch)
========================================================================

1. Read <plan path> — skim sections §<critical section numbers, e.g. §4, §5, §7, §8, §9, §10>. Skip the rest.

2. Run in parallel:
   - git status                  (working tree should be reasonably clean)
   - git branch --show-current   (must be `<branch>`)
   - <baseline test-collect command, e.g. "uv run pytest --collect-only -q 2>&1 | tail -5">
   - <other quick diagnostic — e.g. "ls src/app/<layer>/">

3. Create a TodoWrite list with the chunk queue below.

If the branch is wrong, the working tree has unrelated changes, or baseline collection fails: STOP and report to me.

========================================================================
CHUNK QUEUE — execute in order
========================================================================

<Phase A name — shared primitives that no other code depends on yet>
  A1: <chunk title> (plan §<section>)
  A2: <chunk title> (plan §<section>)
  ...

<Phase B name — protocols / contracts the next layer will fulfill>
  B1: <chunk title> (plan §<section>)
  ...

<Phase C name — per-feature rewrites, usually one file per chunk>
  C1: <chunk title> (plan §<section>)
  C2: <chunk title> (plan §<section>)
  ...

<Phase D name — structural tests that enforce the new shape>
  D1: <chunk title> (plan §<section>)

<Phase E name — smoke validation, orchestrator runs directly without dispatch>
  E1: <e.g. "uv run pytest src/test/structural -v">
  E2: <e.g. "boot the app, hit /openapi.json, verify N endpoints present">
  E3: Capture the head commit SHA and the count of commits since baseline.

Phase F — Retrospective (orchestrator dispatches the refactor-analyzer)
  F1: Dispatch refactor-analyzer with the plan path, orchestrator-prompt path,
      baseline commit SHA, branch, and repo path. The analyzer writes the
      retrospective report and appends to learnings.md.
  F2: If the analyzer surfaces AskUserQuestion proposals (rule-of-three diffs),
      respond as the user prompts. The analyzer applies approved diffs itself.
  F3: Report final state to me: list of commits, anything skipped or escalated,
      pointer to the retrospective file, pointer to any learnings.md entries
      created or promoted this run.

========================================================================
PER-CHUNK WORKFLOW
========================================================================

For each chunk:

1. TodoWrite: mark in_progress.

1.5. Pre-fetch for this chunk:
   a. Extract the plan section(s) referenced by this chunk from your Step 0 memory.
   b. Read each target file with the Read tool (returns cat -n output with line numbers).
      For NEW files (nothing to read yet): run `ls -1 <parent-dir>/` instead.
   c. Read the `## Project conventions` block from this orchestrator prompt.
   You will inline all three into the dispatch prompt below — do NOT reference by path.

2. Dispatch ONE refactor-executor:

   Task({
     subagent_type: "requirements-framework:refactor-executor",
     description: "<5 words>",
     prompt: <see DISPATCH TEMPLATE below>
   })

3. When the agent reports back, run the REVIEW CHECKLIST yourself.

4. Decide:
   - PASS → commit (see COMMIT CONVENTIONS) → TodoWrite mark completed → next chunk
   - SIMPLE ISSUE (missing import, typo, ruff finding, wrong dotted path) → re-dispatch the SAME refactor-executor with a focused 2-3 line fix prompt. Max 2 retries per chunk.
   - COMPLEX ISSUE (plan contradicts code reality, third-party API mismatch, type-checker complaint that implies plan oversight) → dispatch refactor-investigator (see INVESTIGATION DISPATCH below) → AskUserQuestion with the diagnosis and 2-3 options → STOP until the user responds.
   - NEEDS_CLARIFICATION (executor returned this verdict with a question) →
     answer the question by calling SendMessage({to: "executor-<chunk-id>", message: "<answer>"}).
     The executor resumes with full context — do NOT re-dispatch a new Task.
     If you cannot answer confidently: AskUserQuestion to me first, then SendMessage.
     Fallback: if SendMessage fails (name was omitted from the Task spawn), treat as COMPLEX ISSUE.

========================================================================
DISPATCH TEMPLATE (for refactor-executor)
========================================================================

Task({
  subagent_type: "requirements-framework:refactor-executor",
  name: "executor-<chunk-id>",   // REQUIRED — enables NEEDS_CLARIFICATION resume via SendMessage
  description: "<5 words>",
  prompt: `
Repo: <repo path>
Branch: <branch>

## Plan section (<§N.N> — <section title>)
<paste the literal plan section text here — do not reference by path>

## Current file contents
<For each target file, paste Read tool output verbatim, including line numbers:>
### <path/to/file.py>
     1	<line content>
     2	<line content>
     ...
<For NEW files (nothing to read yet), paste directory listing instead:>
### ls -1 <parent-dir>/
<output>
<For chunks that touch both existing and new files, include both forms — one block per file.>

## Project conventions
<paste the Layer rules and Known anti-patterns from the PROJECT CONVENTIONS block above verbatim>
<if PROJECT CONVENTIONS block is empty, omit this section entirely>

## Your task
<chunk title — one line>

Apply the plan section above to the file(s) above.

Strict rules:
- Match the plan's canonical shape exactly.
- NO try/except. NO comments explaining WHAT. NO unrelated imports.
- DO NOT read any files or grep the codebase — everything is above.
- If something is missing or contradictory: use verdict: NEEDS_CLARIFICATION with one specific question. No edits.

Verify before reporting:
  <ruff check command>
  <import smoke command>
  <test collect command>

Report:
- Files touched (paths only)
- Verification output (or "all green")
- Any deviation from the plan (with reason, line numbers)
- Anything noticed but not changed
  `
})

========================================================================
REVIEW CHECKLIST (orchestrator runs after every chunk)
========================================================================

For ALL chunks:
  [ ] Each touched file matches the plan section's canonical shape
  [ ] `<ruff check command>` is clean
  [ ] `<import smoke command>` succeeds
  [ ] `<test-collect command>` shows no NEW errors

For <layer-specific> chunks additionally:
  [ ] <project-specific check 1, e.g. "operation_id is set on every decorator">
  [ ] <project-specific check 2, e.g. "Parameter order matches plan §5">
  [ ] <project-specific check 3>

Result classification:
  - All boxes ticked → PASS
  - 1-2 boxes red with an obvious mechanical fix → SIMPLE ISSUE
  - Anything else, especially "plan says X but codebase reality is Y" → COMPLEX ISSUE (escalate)

========================================================================
COMMIT CONVENTIONS (atomic per chunk)
========================================================================

One chunk = one commit. Format:

  git add <only the touched paths>
  git commit -m "<imperative subject mentioning plan section>"

Examples:
  "Add <helper> per plan §<N>"
  "Rewrite <module> to canonical shape per plan §<N>"
  "Move <module> into subfolder per plan §<N>"
  "Add structural tests for <layer> shape per plan §<N>"

Pre-commit hooks may auto-format. If files end up in MM state, re-stage and retry. NEVER use --no-verify without asking me first.

If a commit picks up unrelated lint debt from a touched file, land an isolated debt-cleanup prep commit first, then the semantic commit.

========================================================================
INVESTIGATION DISPATCH (when something doesn't fit the plan)
========================================================================

Task({
  subagent_type: "requirements-framework:refactor-investigator",
  description: "Diagnose plan vs reality",
  prompt: `
Plan: <plan path>
Chunk: <which one>
What it was supposed to do: <one line>
What went wrong: <paste the failure verbatim>
Files inspected so far: <list>

Diagnose root cause and propose 2-3 solution paths with trade-offs.
  `
})

Then AskUserQuestion to me with:
- The investigator's root-cause line
- 2-3 option labels (one short per solution path)

After I pick: update the plan file if needed (do this in the same orchestrator session, not via dispatch), then resume from the failing chunk.

========================================================================
PHASE F DISPATCH (retrospective)
========================================================================

After Phase E completes successfully, dispatch the retrospective:

Task({
  subagent_type: "requirements-framework:refactor-analyzer",
  description: "Retrospective for this run",
  prompt: `
You are running the Phase F retrospective for this refactor orchestration.

Plan: <plan path>
Orchestrator prompt: <orchestrator-prompt path>
Branch: <branch>
Baseline commit: <SHA captured at Step 0>
Head commit: <SHA captured at E3>
Repo path: <absolute repo path>

Follow your workflow:
1. Locate the session transcript under ~/.claude/projects/<encoded-repo>/
2. Extract per-chunk signals, retries, escalations, "noticed-but-not-changed"
3. Compare git log to plan §11 (End State)
4. Check for plan-vs-reality gaps (mid-run plan edits)
5. Bump counts in the learnings ledgers. There are TWO ledger locations:
   - Global (per-user, writable): `~/.claude/refactor-orchestration/learnings.md`
     (created from `learnings.md.template` if missing)
   - Project (repo-local, writable): `.claude/refactor-orchestration/learnings.md`
     (created empty if missing)
6. Write the retrospective at .claude/plans/<plan-slug>-retrospective.md
7. For observations that hit count=3 this run, propose diffs via AskUserQuestion
8. Apply approved diffs (with Edit) to the appropriate ledger
   (`~/.claude/refactor-orchestration/learnings.md` for cross-project lessons,
   `.claude/refactor-orchestration/learnings.md` for repo-specific lessons);
   mark rejected ones as rejected in the same ledger.

Stay under 500 words in prose sections of the report.
  `
})

The analyzer interacts with the user directly via AskUserQuestion for any
proposed diffs. After it reports back, do Phase F3 (final state report).

========================================================================
STOP CONDITIONS
========================================================================

Stop and escalate IF:
- Baseline tests fail before any chunk runs.
- A chunk hits a complex issue after one investigation dispatch.
- 2 retries on a simple issue without going green.
- A circular import or layer-guard violation appears that the plan doesn't anticipate.
- The plan references a file/symbol that doesn't exist in the codebase.
- The chunk queue is empty — give me the final state report (list of commits, anything skipped or escalated).

========================================================================
GO
========================================================================

Begin with Step 0. Do not summarize this prompt back to me — just execute.

=== END ORCHESTRATOR PROMPT ===

---

## Filling out this template

Replace these placeholders before saving:

- `<refactor title>` — short noun phrase, matches plan §0 title
- `<branch>` — the branch this work commits on
- `<plan path>` — the absolute or repo-relative path to the plan file
- `<critical section numbers>` — the sections of the plan the orchestrator actually needs (typically the ones holding canonical shapes and the chunk queue inputs)
- `<chunk queue>` — derive from the plan's §7 (the items) plus §10 (structural tests). One chunk = one atomic commit.
- `<ruff check command>`, `<import smoke command>`, `<test-collect command>` — the project's actual commands
- `<project-specific rules>` and `<project-specific checks>` — pulled from the plan's §1 (Forbidden) and §10 (Structural Tests)

If the orchestrator block ends up over ~250 lines, you're embedding too much plan content. Reference the plan by section number instead.
