# Project-Agnostic Refactor Orchestration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use requirements-framework:executing-plans to implement this plan task-by-task.

**Goal:** Remove hardcoded project-specific conventions from `refactor-executor.md` and make the orchestration system inject project context via fat dispatch prompts, enabling the executor to work correctly across any project.

**Architecture:** Conventions flow from `.claude/refactor-conventions.md` → plan §1 → orchestrator-prompt.md at planning time. At execution time, the orchestrator pre-reads plan sections and target files and inlines them (with line numbers) into each executor dispatch prompt. The executor gains a `NEEDS_CLARIFICATION` verdict and is resumed via `SendMessage` rather than re-dispatched.

**Tech Stack:** Markdown agent/skill definitions in `plugins/requirements-framework/`. No Python changes. Plugin version bump required after all edits.

---

### Task 1: Remove hardcoded rules from `refactor-executor.md`

**Files:**
- Modify: `plugins/requirements-framework/agents/refactor-executor.md`

**Step 1: Remove the two project-specific hard rules**

In `## Hard rules`, remove these two lines:
```
- For router-layer work specifically: NO `HTTPException`, NO `JSONResponse`, NO direct SDK imports (openai/azure/anthropic), ONE return statement per endpoint body.
- Use `Annotated[T, Marker]` for every FastAPI parameter when working on FastAPI routers.
```

**Step 2: Add the "fat prompt contract" rule**

After the existing `- NO try/except...` line, add:
```markdown
- DO NOT read the plan file. DO NOT grep or explore the codebase. All context you need is in this prompt. If something is missing or contradictory, use `verdict: NEEDS_CLARIFICATION` — do not guess, do not make partial edits.
```

**Step 3: Simplify the workflow to 3 steps**

Replace the current 5-step workflow:
```markdown
## Workflow

1. Apply the change using the inlined plan section and file contents provided in this prompt.
2. Verify before reporting:
   - `<lint command>` clean (typically `uv run ruff check <touched paths>`)
   - `<import smoke>` succeeds (typically `uv run python -c "import <touched module>"`)
   - `<test collect>` shows no new errors (typically `uv run pytest --collect-only -q 2>&1 | tail -5`)
3. Report back with:
   - Files touched (paths only)
   - Verification output (or one-line "all green")
   - Any deviation from the plan and the reason
   - Anything you noticed but did not change
```

**Step 4: Add `verdict: NEEDS_CLARIFICATION` to the Summary section**

In the `## Summary` section, after the `verdict: SKIPPED` line add:
```markdown
- `verdict: NEEDS_CLARIFICATION` — inlined context is ambiguous or contradictory; no edits made. Include one specific question under the verdict line.
```

**Step 5: Remove `Read`, `Grep`, `Glob` from `allowed-tools` frontmatter**

The fat-prompt contract must be structural, not just a prose instruction. In the YAML frontmatter, change:
```yaml
allowed-tools: ["Read", "Edit", "Write", "Bash", "Grep", "Glob"]
```
to:
```yaml
allowed-tools: ["Edit", "Write", "Bash"]
```

**Step 6: Verify the file looks correct**

Read the file and confirm:
- No FastAPI-specific rules remain in `## Hard rules`
- `DO NOT read the plan...` rule is present
- Workflow is 3 steps (not 5)
- `NEEDS_CLARIFICATION` verdict is present
- `allowed-tools` is `["Edit", "Write", "Bash"]` only

**Step 7: Commit**
```bash
git add plugins/requirements-framework/agents/refactor-executor.md
git commit -m "refactor(executor): remove project-specific rules, add fat-prompt contract and NEEDS_CLARIFICATION verdict"
```

---

### Task 2: Update SKILL.md Stage 1 to read the conventions file

**Files:**
- Modify: `plugins/requirements-framework/skills/refactor-orchestration/SKILL.md`

**Step 1: Extend the Stage 1 description**

Find the line:
```
1. **Inventory.** Two parallel `Explore` agents: one catalogues the layer's current state (every file, every function, every leaked responsibility), one extracts rules from the relevant ADRs / design docs / framework conventions. Produces a "what is" and a "what should be" report.
```

Replace with:
```markdown
1. **Inventory.** Two parallel `Explore` agents: one catalogues the layer's current state (every file, every function, every leaked responsibility), one extracts rules from the relevant ADRs / design docs / framework conventions. If `.claude/refactor-conventions.md` exists, read it and include its **Layer rules** and **Known anti-patterns** sections in the "what should be" report — these are project-tier constraints promoted by prior `refactor-analyzer` runs and must be respected in the plan's §1 (Forbidden). Produces a "what is" and a "what should be" report.
```

**Step 2: Add a note to Stage 5 about seeding §1 from the conventions file**

Find the line:
```
5. **Persist plan.** Write the plan to `.claude/plans/<YYYY-MM-DD>-<slug>.md` using `plan-template.md` (§0–§13 structure). Keep the section headers stable — anyone reading multiple plans should recognize the shape.
```

Append to it:
```markdown
   When a conventions file was read in Stage 1, its Layer rules and Known anti-patterns must appear verbatim in plan §1 (Forbidden). New projects with no conventions file leave §1 populated only from ADR analysis — that is correct and expected.
```

**Step 3: Verify**

Read the file and confirm Stage 1 and Stage 5 contain the new text.

**Step 4: Commit**
```bash
git add plugins/requirements-framework/skills/refactor-orchestration/SKILL.md
git commit -m "feat(refactor-orchestration): Stage 1 reads .claude/refactor-conventions.md into plan §1"
```

---

### Task 3: Rewrite the orchestrator-prompt-template dispatch section

**Files:**
- Modify: `plugins/requirements-framework/skills/refactor-orchestration/orchestrator-prompt-template.md`

This is the most substantial change. Three sub-changes:

#### 3a — Add Step 2.5 (pre-fetch) to the per-chunk workflow

After the existing Step 2 in `========================================================================
PER-CHUNK WORKFLOW`, before `2. Dispatch ONE refactor-executor:`, add a new `1.5.` step:

```markdown
1.5. Pre-fetch for this chunk:
   a. Extract the plan section(s) referenced by this chunk from your Step 0 memory.
   b. Read each target file with the Read tool (returns cat -n output with line numbers).
      For NEW files (nothing to read yet): run `ls -1 <parent-dir>/` instead.
   c. Read the `## Project conventions` block from this orchestrator prompt.
   You will inline all three into the dispatch prompt below — do NOT reference by path.
```

#### 3b — Replace the DISPATCH TEMPLATE block

Replace the current DISPATCH TEMPLATE section (the block from line 110 to ~130) with:

````markdown
========================================================================
DISPATCH TEMPLATE (for refactor-executor)
========================================================================

Task({
  subagent_type: "requirements-framework:refactor-executor",
  name: "executor-<chunk-id>",   ← use chunk ID, e.g. "executor-A1"
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
<For NEW files, paste directory listing instead:>
### ls -1 <parent-dir>/
<output>

## Project conventions
<paste the Layer rules and Known anti-patterns from plan §1 verbatim>
<if plan §1 is empty, omit this block entirely>

## Your task
<chunk title — one line>

Apply the plan section above to the file(s) above.

Strict rules:
- Match the plan's canonical shape exactly.
- NO try/except. NO comments explaining WHAT. NO unrelated imports.
- DO NOT read any files or grep the codebase — everything is above.
- If something is missing or contradictory: verdict: NEEDS_CLARIFICATION with one question. No edits.

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
````

#### 3c — Add NEEDS_CLARIFICATION handler to the per-chunk workflow

In the `4. Decide:` block of PER-CHUNK WORKFLOW, after the existing `COMPLEX ISSUE` bullet, add:

```markdown
   - NEEDS_CLARIFICATION (executor returned this verdict with a question) →
     answer the question by calling SendMessage({to: "executor-<chunk-id>", message: "<answer>"}).
     The executor resumes with full context — do NOT re-dispatch a new Task.
     If you cannot answer confidently: AskUserQuestion to me first, then SendMessage.
```

#### 3d — Add PROJECT CONVENTIONS block to the orchestrator prompt body

After the PREREQUISITES block (before `You are the orchestrator...`), add:

```markdown
========================================================================
PROJECT CONVENTIONS (from plan §1 — injected into every executor dispatch)
========================================================================

<paste the Layer rules and Known anti-patterns from plan §1 verbatim>
<if plan §1 is empty, write: (none — new project, no refactor-conventions.md yet)>
```

**Step 3e: Verify**

Read the file and confirm:
- Step 2.5 (pre-fetch) is present in PER-CHUNK WORKFLOW
- Dispatch template has `name: "executor-<chunk-id>"`
- Dispatch template has `## Plan section`, `## Current file contents`, `## Project conventions` blocks
- `NEEDS_CLARIFICATION` handler is in the `4. Decide:` block
- `PROJECT CONVENTIONS` block is in the prompt body

**Step 3f: Commit**
```bash
git add plugins/requirements-framework/skills/refactor-orchestration/orchestrator-prompt-template.md
git commit -m "feat(refactor-orchestration): fat dispatch prompt — inline plan section, file contents, project conventions; named executor spawns; NEEDS_CLARIFICATION handler"
```

---

### Task 4: Bump plugin version and update git_hash fields

**Files:**
- Modify: `plugins/requirements-framework/.claude-plugin/plugin.json`

**Step 1: Bump version from 3.0.1 → 3.1.0**

This is a minor version bump (new feature: project-agnostic dispatch, fat prompts, NEEDS_CLARIFICATION).

```json
"version": "3.1.0"
```

**Step 2: Update git_hash fields**

```bash
./update-plugin-versions.sh
```

Expected: updates `git_hash` in `refactor-executor.md`, `SKILL.md`, `orchestrator-prompt-template.md`.

**Step 3: Verify hashes are current**

```bash
./update-plugin-versions.sh --verify
```

Expected: all files report current hash (no `*` suffix).

**Step 4: Check sync status**

```bash
./sync.sh status
```

Expected: shows files that need deploying.

**Step 5: Deploy to runtime**

```bash
./sync.sh deploy
```

**Step 6: Commit**
```bash
git add plugins/requirements-framework/.claude-plugin/plugin.json \
        plugins/requirements-framework/agents/refactor-executor.md \
        plugins/requirements-framework/skills/refactor-orchestration/SKILL.md \
        plugins/requirements-framework/skills/refactor-orchestration/orchestrator-prompt-template.md
git commit -m "chore: bump plugin to 3.1.0, update git_hash fields after refactor-orchestration project-agnostic changes"
```

---

### Task 5: Seed `.claude/refactor-conventions.md` for statuta-rag-api-v2

**Files:**
- Create: `/Users/harm/Lotte/statuta-rag-api-v2/.claude/refactor-conventions.md`

The conventions removed from `refactor-executor.md` must be preserved for the project that needs them.

**Step 1: Check if the file already exists**

```bash
ls /Users/harm/Lotte/statuta-rag-api-v2/.claude/refactor-conventions.md 2>/dev/null || echo "missing"
```

**Step 2: If missing, create it with the FastAPI layer rules**

```markdown
# Refactor Conventions for statuta-rag-api-v2

> Auto-grown by refactor-analyzer rule-of-three promotions. Gitignored by default.
> Read by refactor-orchestration Stage 1 (inventory).

## Layer rules

- Router layer: NO `HTTPException`, NO `JSONResponse`, NO direct SDK imports (`openai`/`azure`/`anthropic`).
- Router layer: ONE return statement per endpoint body.
- Router layer: Use `Annotated[T, Marker]` for every FastAPI parameter.

## Naming & API patterns

## Cross-cutting checklists

## Known anti-patterns
```

**Step 3: Verify the file is gitignored**

```bash
cd /Users/harm/Lotte/statuta-rag-api-v2 && git check-ignore -v .claude/refactor-conventions.md
```

If NOT ignored, add to `.gitignore`:
```bash
echo ".claude/refactor-conventions.md" >> /Users/harm/Lotte/statuta-rag-api-v2/.gitignore
```

**Step 4: Commit in statuta-rag-api-v2** (or leave untracked — it's gitignored)

No commit needed if gitignored. Just verify the file exists at the right path.

---

## Preparatory Refactoring

**Verdict: No preparatory commits required.** All insertion and replacement points are cleanly delimited and can be executed directly.

### Analysis per task

**Task 1 — `refactor-executor.md`**

- The two FastAPI-specific rules (lines 19–20) are at the tail of `## Hard rules`. Removing them leaves a coherent, self-contained rule set — no surrounding cleanup needed.
- The `## Workflow` section (steps 1–5) is replaced wholesale. Steps 1 ("Read the plan sections") and 2 ("Read the file(s)") disappear entirely under the fat-prompt contract; the new 3-step workflow is a clean swap of the whole section. No structural prep needed.
- The `## Summary` verdict list is a simple bullet append — no structural issues.

**Task 2 — `SKILL.md`**

- Stage 1 (line 37–38) is a single long sentence already on its own list item. Find-and-replace is unambiguous.
- Stage 5 (line 45) ends with a period and is followed by Stage 6 on a blank line. The appended continuation text indents cleanly below it.
- No inconsistencies to clean up.

**Task 3 — `orchestrator-prompt-template.md`**

- **3a (Step 2.5):** Steps 1–4 are clearly numbered in `PER-CHUNK WORKFLOW`. Inserting a fractional `1.5` step between Step 1 (TodoWrite) and Step 2 (Dispatch) is unambiguous and requires no renumbering.
- **3b (Dispatch template):** The `DISPATCH TEMPLATE` block is already isolated between `========================================================================` dividers. The plan references "line 110 to ~130" — these are approximate. **Use the `========================================================================` delimiters as the exact boundaries, not hardcoded line numbers.** The block to replace is everything from `========================================================================\nDISPATCH TEMPLATE (for refactor-executor)` through the closing `========================================================================` line before `REVIEW CHECKLIST`.
- **3c (NEEDS_CLARIFICATION handler):** The `4. Decide:` block ends with `STOP until the user responds.` — the new bullet appends cleanly after the `COMPLEX ISSUE` bullet.
- **3d (PROJECT CONVENTIONS block):** Inserts between the PREREQUISITES block (ends at line 22) and the `You are the orchestrator...` line (line 24). One blank line separates them — clean insertion point.

### One caution for the implementer

When executing Task 3b, do **not** rely on line numbers from the plan — use the section header text `DISPATCH TEMPLATE (for refactor-executor)` and the surrounding `========================================================================` fences as match anchors. The line numbers were approximate at planning time.

---

## Execution order

Tasks 1 → 2 → 3 → 4 → 5

Tasks 1–4 are all in this repo (`claude-requirements-framework`). Task 5 is in a different repo and can run after Task 4 completes.

---

## Atomic Commit Strategy

### Commit 1 — `refactor(executor): remove project-specific rules, add fat-prompt contract and NEEDS_CLARIFICATION verdict`

**Files:** `plugins/requirements-framework/agents/refactor-executor.md`

**What it does:** Removes the two FastAPI/router-specific hard rules from `## Hard rules`, adds the "DO NOT read the plan file" fat-prompt contract rule, collapses the 5-step workflow to 3 steps, and adds the `NEEDS_CLARIFICATION` verdict to `## Summary`.

**Before committing, verify:**
- No FastAPI-specific lines remain in `## Hard rules`
- `DO NOT read the plan file...` rule is present after the `NO try/except` line
- `## Workflow` has exactly 3 numbered steps
- `verdict: NEEDS_CLARIFICATION` line is present in `## Summary`

---

### Commit 2 — `feat(refactor-orchestration): Stage 1 reads .claude/refactor-conventions.md into plan §1`

**Files:** `plugins/requirements-framework/skills/refactor-orchestration/SKILL.md`

**What it does:** Extends the Stage 1 inventory description to read `.claude/refactor-conventions.md` when present and include its Layer rules / Known anti-patterns in the "what should be" report. Adds a note to Stage 5 that conventions file content must appear verbatim in plan §1 (Forbidden).

**Before committing, verify:**
- Stage 1 text references `.claude/refactor-conventions.md` and the two sections by name
- Stage 5 text references that conventions content must appear verbatim in plan §1 (Forbidden)
- No other lines changed

---

### Commit 3 — `feat(refactor-orchestration): fat dispatch prompt — inline plan section, file contents, project conventions; named executor spawns; NEEDS_CLARIFICATION handler`

**Files:** `plugins/requirements-framework/skills/refactor-orchestration/orchestrator-prompt-template.md`

**What it does:** Four coordinated edits to a single file — add Step 2.5 pre-fetch block (3a), replace the DISPATCH TEMPLATE block with the fat-prompt version including named executor spawns (3b), add `NEEDS_CLARIFICATION` handler to the `4. Decide:` block (3c), add `PROJECT CONVENTIONS` block to the orchestrator prompt body (3d).

**Rationale for keeping 3a–3d together:** All four sub-changes mutually depend on each other — Step 2.5 pre-fetches data that 3b inlines, 3c handles the verdict 3b introduces, and 3d supplies the conventions block 3b references. Any intermediate state would be an incoherent half-rewrite.

**Before committing, verify:**
- `1.5. Pre-fetch for this chunk:` step is present in `PER-CHUNK WORKFLOW`
- Dispatch template has `name: "executor-<chunk-id>"` field
- Dispatch template has `## Plan section`, `## Current file contents`, `## Project conventions` blocks
- `NEEDS_CLARIFICATION` handler is in the `4. Decide:` block with `SendMessage` instruction
- `PROJECT CONVENTIONS` block is present in the prompt body (before `You are the orchestrator...`)

---

### Commit 4 — `chore: bump plugin to 3.1.0, update git_hash fields after refactor-orchestration project-agnostic changes`

**Files:**
- `plugins/requirements-framework/.claude-plugin/plugin.json`
- `plugins/requirements-framework/agents/refactor-executor.md` (git_hash only)
- `plugins/requirements-framework/skills/refactor-orchestration/SKILL.md` (git_hash only)
- `plugins/requirements-framework/skills/refactor-orchestration/orchestrator-prompt-template.md` (git_hash only)

**What it does:** Bumps version from `3.0.1` → `3.1.0` (minor bump: new feature, no breaking changes), then runs `./update-plugin-versions.sh` to refresh `git_hash` in all three modified plugin files, then deploys to runtime with `./sync.sh deploy`.

**Rationale for being last:** `git_hash` fields capture the commit SHA of the content changes — they must be updated after Commits 1–3 are committed, not before.

**Before committing, verify:**
- `plugin.json` shows `"version": "3.1.0"`
- `./update-plugin-versions.sh --verify` reports no `*` suffixes (all hashes are current)
- `./sync.sh status` shows expected files

---

### Task 5 — Seed `statuta-rag-api-v2` conventions (no commit in this repo)

**Repo:** `/Users/harm/Lotte/statuta-rag-api-v2/`
**File:** `.claude/refactor-conventions.md`

This is cross-repo work. The file is gitignored in `statuta-rag-api-v2`, so no commit is needed there either — just verify the file exists at the right path with the FastAPI router rules that were removed from `refactor-executor.md`.

**Run after Commit 4 completes.**
