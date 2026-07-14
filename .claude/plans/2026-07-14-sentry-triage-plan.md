# Sentry Triage Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use requirements-framework:executing-plans to implement this plan task-by-task.

**Goal:** Surface unresolved Sentry issues in code being changed — via a conditional `sentry-triage` teammate in `/arch-review` plus a design-time hint in the brainstorming skill.

**Architecture:** Prompts-only change mirroring the existing `codex-arch-reviewer` conditional-teammate pattern: a new agent prompt, a `HAS_SENTRY` probe + teammate wiring in `arch-review.md.j2`, one sentence in the brainstorming skill, and config docs. No Python, no new gates. Config is an explicit `sentry: {org, project}` block in the requirements.yaml cascade; absent → silent skip.

**Tech Stack:** Plugin markdown prompts (`.md.j2` → rendered `.md` via `scripts/render_prompts.py`), Sentry MCP tools (`mcp__plugin_sentry_sentry__*`), Stacked Git.

**Design doc:** `.claude/plans/2026-07-14-sentry-triage-design.md` (approved 2026-07-14).

**Repo rules that apply to every task:**
- Commits via `stg new -m "..."` + `git add` + `stg refresh` — never `git commit`.
- Every `.md.j2` edit must be re-rendered: `uv run python scripts/render_prompts.py` (writes the paired `.md`), then `--check` must pass.
- Branch: `feat/sentry-triage` (already created, stg initialized).

---

### Task 1: Create the `sentry-triage` agent + register it (plugin version bump in same patch)

**Files:**
- Create: `plugins/requirements-framework/agents/sentry-triage.md.j2`
- Generated: `plugins/requirements-framework/agents/sentry-triage.md` (via render script)
- Modify: `plugins/requirements-framework/.claude-plugin/plugin.json` (agents array + version `7.0.0` → `7.1.0`)

**Step 1: Write the agent source file**

Create `plugins/requirements-framework/agents/sentry-triage.md.j2` with exactly this content (modeled on `codex-arch-reviewer.md.j2`; keep the `git_hash` line — the version script maintains it):

````markdown
---
name: sentry-triage
model: sonnet
description: |
  Checks Sentry for unresolved production errors/warnings in the code a plan is about to change. Reads the project's `sentry: {org, project}` block from the requirements.yaml cascade, derives the touched files from the plan (or branch diff), and searches Sentry via MCP for unresolved issues referencing those files. Skips silently when Sentry is not configured or the MCP tools are unavailable (teammate mode).

  Examples:
  <example>
  Context: Architecture review team wants production evidence about the code being modified.
  user: "Run architecture review on my plan"
  assistant: "The sentry-triage teammate will check Sentry for unresolved issues in the files the plan touches."
  <commentary>
  Used as a conditional teammate in /arch-review when the project declares a sentry: config block.
  </commentary>
  </example>
  <example>
  Context: User wants to know if the code they are changing has known production errors.
  user: "Are there Sentry errors in the code I'm about to change?"
  assistant: "I'll use the sentry-triage agent to search Sentry for unresolved issues in those files."
  <commentary>
  Can be used standalone for a file-scoped Sentry sweep.
  </commentary>
  </example>
color: orange
allowed-tools: ["Bash", "Read", "Glob", "Grep", "SendMessage", "TaskUpdate", "ToolSearch"]
git_hash: a9add9d
---

# Sentry Triage Agent

You check Sentry for unresolved production issues in the code a plan is about to change, so known errors become review input instead of post-ship surprises.

## Fail-Soft Invariant (read first)

You NEVER block the team and NEVER invent findings. Any failure — missing config, missing MCP tools, auth error, timeout, malformed plan — degrades to a one-line "skipped (<reason>)" report. Zero matches is a healthy result: report "no known issues", verdict CLEAN.

## Workflow

### 1. Read Sentry configuration

Read `.claude/requirements.local.yaml` then `.claude/requirements.yaml` (local wins). Extract the `sentry:` block:

```yaml
sentry:
  org: <organization-slug>
  project: <sentry-project-slug>
```

If neither file has a `sentry:` block with at least `org`: output "Sentry not configured — skipping triage" and EXIT (SendMessage that line to the lead and mark your task complete if in teammate mode).

### 2. Load Sentry MCP tools

Use ToolSearch with query "+sentry issues" (or "select:..." if you know the names) to load the Sentry MCP tool schemas (`mcp__plugin_sentry_sentry__*` — typically `search_issues`, `get_issue_details`). If no Sentry MCP tools exist in this session: output "Sentry MCP unavailable — skipping triage" and EXIT (fail-soft).

### 3. Determine the touched surface

Use the plan file path provided in your prompt. Read it and extract the files the plan will create/modify (the `**Files:**` blocks and any paths in prose). Fall back to the branch diff when the plan yields nothing:

```bash
git diff --name-only origin/master...HEAD 2>/dev/null || git diff --name-only main...HEAD
```

Ignore created-from-scratch files (they cannot have Sentry history); keep modified files. If the touched surface is empty: report "no existing files touched — nothing to triage" and EXIT.

### 4. Search Sentry

For each touched file (cap at 15 — note any overflow), search unresolved issues in the configured org/project whose stack frames or metadata reference it. Query by basename first, then by module/function names for fuzzier hits, e.g.:

- `is:unresolved stack.filename:"*<basename>*"`
- `is:unresolved "<dotted.module.path>"`

Restrict to the last 90 days. Deduplicate issues that match multiple files.

### 5. Report

Severity is your judgment call from frequency × recency × overlap with the planned change:
- **CRITICAL**: high-frequency or recent unresolved error in code the plan directly modifies
- **IMPORTANT**: unresolved error adjacent to the change (same module, shared call path)
- **INFO**: low-frequency / stale issues worth a glance

**Output format:**

```markdown
# Sentry Triage

## Scope
- Org/project: <org>/<project>
- Files checked: N (of M touched; overflow noted)

## Findings

### CRITICAL: [Issue title]
- **Sentry**: <issue ID and URL>
- **Location**: `path/to/file.py` (frame match)
- **Frequency**: X events / Y users, last seen <date>
- **Overlap**: How the planned change intersects this error
- **Recommendation**: Fix in this plan | fix first | consciously defer

## Summary
- **CRITICAL**: X · **IMPORTANT**: Y · **INFO**: Z
- **Verdict**: ISSUES FOUND | CLEAN | SKIPPED (<reason>)
```

### 6. Teammate mode

When running as a teammate in `/arch-review`: share the report via SendMessage to the lead and mark your task complete via TaskUpdate — including on every skip path.

## Guidelines

1. **Config and tools first** — exit fast and quietly when Sentry isn't set up.
2. **Never block** — any error path ends in a SKIPPED report, not a stall.
3. **Production evidence only** — do not review code quality; that belongs to the other teammates.
4. **Always link** — every finding carries its Sentry issue URL so the user can act on it.
````

**Step 2: Render and verify**

Run: `uv run python scripts/render_prompts.py && uv run python scripts/render_prompts.py --check`
Expected: reports one newly rendered file; check passes ("all rendered file(s) are fresh"). `plugins/requirements-framework/agents/sentry-triage.md` now exists.

**Step 3: Register the agent + bump version**

In `plugins/requirements-framework/.claude-plugin/plugin.json`:
- Append `"./agents/sentry-triage.md"` to the `agents` array (after `refactor-analyzer.md`).
- Change `"version": "7.0.0"` → `"version": "7.1.0"`.

**Step 4: Verify**

Run: `uv run python -c "import json; d=json.load(open('plugins/requirements-framework/.claude-plugin/plugin.json')); assert './agents/sentry-triage.md' in d['agents'] and d['version']=='7.1.0'; print('OK', len(d['agents']), 'agents')"`
Expected: `OK 25 agents`

**Step 5: Commit**

```bash
stg new sentry-triage-agent -m "feat(agents): add sentry-triage conditional teammate (7.1.0)"
git add plugins/requirements-framework/agents/sentry-triage.md.j2 plugins/requirements-framework/agents/sentry-triage.md plugins/requirements-framework/.claude-plugin/plugin.json
stg refresh
```

---

### Task 2: Wire sentry-triage into `/arch-review`

**Files:**
- Modify: `plugins/requirements-framework/commands/arch-review.md.j2` (6 spots, mirroring HAS_CODEX)
- Generated: `plugins/requirements-framework/commands/arch-review.md` (re-render)

All edits go in the `.md.j2`; line numbers reference the current rendered `.md` for orientation.

**Step 1: Extend the probe (Step 2.5, ~line 64)**

Replace the Step 2.5 block:

````markdown
### Step 2.5: Check Conditional Agent Availability

```bash
which codex 2>/dev/null
grep -qE '^sentry:' .claude/requirements.yaml .claude/requirements.local.yaml 2>/dev/null && echo HAS_SENTRY
```

Set flags:
- **HAS_CODEX** = true if `which codex` succeeds (exit code 0)
- **HAS_SENTRY** = true if a top-level `sentry:` block exists in `.claude/requirements.yaml` or `.claude/requirements.local.yaml` (MCP availability is checked by the agent itself — it skips gracefully)
````

**Step 2: Add the task (Step 3 task list, after item 7)**

```markdown
8. **Task**: "Sentry issue triage" — assigned to sentry-triage, ONLY if HAS_SENTRY is true
9. **Task**: "Synthesize architectural assessment" — blocked by all above, assigned to lead
```

(Renumber the old item 8 to 9.)

**Step 3: Add the teammate spawn block (Step 4, after the codex-arch-reviewer block, ~line 138)**

```markdown
**sentry-triage teammate** (ONLY if HAS_SENTRY is true):
- `subagent_type`: "requirements-framework:sentry-triage"
- `name`: "sentry-triage"
- `prompt`: Pass the plan file path `$PLAN_FILE` and instruction:
  "Read the plan from `$PLAN_FILE`. Check Sentry for unresolved issues in the files this plan modifies, per your agent instructions. Share findings via SendMessage with severity levels. Mark task complete when done — including when you skip."
```

**Step 4: Add synthesis cross-reference rules (Step 6, new item after item 5, ~line 175)**

```markdown
6. **Cross-reference Sentry triage findings** (only if sentry-triage participated):
   - If sentry-triage flags an unresolved issue in a region another agent also flags: escalate to CRITICAL — "Production evidence confirms the concern"
   - If sentry-triage flags a CRITICAL issue in a touched file no other agent flagged: keep as standalone IMPORTANT — "Known production error in code being modified — plan should fix or consciously defer it"
   - If sentry-triage reports SKIPPED or CLEAN: note the status; no escalation
```

(Renumber old item 6 "Produce unified verdict" to 7.)

**Step 5: Extend the report template (Output Format, ~lines 218 & 236)**

Team list gains: `- sentry-triage: [status or "skipped (not configured)"]`

After the `## Codex Architecture Analysis` section add:

```markdown
## Known Production Issues (Sentry)
[Findings from sentry-triage, cross-referenced with other agents, or "skipped (not configured)"]
```

**Step 6: Render and verify**

Run: `uv run python scripts/render_prompts.py && uv run python scripts/render_prompts.py --check`
Then: `grep -c 'HAS_SENTRY' plugins/requirements-framework/commands/arch-review.md`
Expected: 5 (probe ×2, task list, spawn block, cross-ref intro... adjust expectation to actual count after edit, but ≥4) — and `grep -c 'sentry-triage' plugins/requirements-framework/commands/arch-review.md` ≥ 6.

**Step 7: Commit**

```bash
stg new arch-review-sentry -m "feat(commands): arch-review spawns sentry-triage when sentry: configured"
git add plugins/requirements-framework/commands/arch-review.md.j2 plugins/requirements-framework/commands/arch-review.md
stg refresh
```

---

### Task 3: Design-time hint in the brainstorming skill

**Files:**
- Modify: `plugins/requirements-framework/skills/brainstorming/SKILL.md.j2:34`
- Generated: `plugins/requirements-framework/skills/brainstorming/SKILL.md` (re-render)

**Step 1: Edit the anchor-peek line**

In `SKILL.md.j2`, replace:

```markdown
2. **Anchor peek** — read just enough code to sketch credible approaches; not an exploration spree. Deeper reads happen later, on demand.
```

with:

```markdown
2. **Anchor peek** — read just enough code to sketch credible approaches; not an exploration spree. Deeper reads happen later, on demand. If the project declares a `sentry:` block in its requirements.yaml, also query Sentry (MCP) for unresolved issues in the area being changed — known production errors are design input.
```

**Step 2: Render and verify**

Run: `uv run python scripts/render_prompts.py && uv run python scripts/render_prompts.py --check`
Then: `grep -c 'sentry' plugins/requirements-framework/skills/brainstorming/SKILL.md`
Expected: ≥1

**Step 3: Commit**

```bash
stg new brainstorm-sentry-hint -m "feat(skills): brainstorming anchor peek checks Sentry when configured"
git add plugins/requirements-framework/skills/brainstorming/SKILL.md.j2 plugins/requirements-framework/skills/brainstorming/SKILL.md
stg refresh
```

---

### Task 4: Documentation (README + DEVELOPMENT.md)

**Files:**
- Modify: `plugins/requirements-framework/README.md` (agent count line 17: `24 agents` → `25 agents`; agents section: add sentry-triage row; new "Sentry integration" config subsection)
- Modify: `DEVELOPMENT.md` (configuration section: document the `sentry:` block)

**Step 1: README edits**

- Line 17: `- **24 agents**` → `- **25 agents**`.
- In the agents listing (find the table/section listing codex-arch-reviewer), add sentry-triage with one line: "Checks Sentry for unresolved issues in files a plan touches; conditional teammate in /arch-review, skips when unconfigured."
- Add a config subsection (near where conditional/Codex behavior is documented, or under Configuration):

````markdown
### Sentry integration (optional)

Declare the project's Sentry mapping to enable the `sentry-triage` teammate in `/arch-review` and the design-time Sentry hint in brainstorming:

```yaml
# .claude/requirements.yaml (or .local.yaml)
sentry:
  org: your-org-slug
  project: your-project-slug
```

Requires the Sentry MCP server in the session. No block (or no MCP) → the check is skipped silently.
````

**Step 2: DEVELOPMENT.md edit**

In the configuration cascade / config keys documentation, add one paragraph: the `sentry:` top-level block is consumed only by agent prompts (never by the Python loader — unknown top-level keys pass through the cascade untouched); shape `sentry: {org, project}`.

**Step 3: Verify**

Run: `grep -n '25 agents' plugins/requirements-framework/README.md && grep -n 'sentry' DEVELOPMENT.md`
Expected: both hit.

**Step 4: Commit**

```bash
stg new sentry-docs -m "docs: document sentry: config block and sentry-triage agent"
git add plugins/requirements-framework/README.md DEVELOPMENT.md
stg refresh
```

---

### Task 5: Full verification sweep

**Step 1: Test suite** — `uv run python hooks/test_requirements.py`
Expected: green-local (all pass except the 5 known local-environment config-validation failures).

**Step 2: Lint** — `uv run ruff check .`
Expected: no errors (no Python changed, must stay clean).

**Step 3: Render check** — `uv run python scripts/render_prompts.py --check`
Expected: all fresh.

**Step 4: Bundle** — `uv run python scripts/build_plugin_hooks.py`
Expected: completes; if it modifies bundle files, fold them into the last patch (`git add -A plugins/ && stg refresh`), else nothing to commit.

**Step 5: Manual smoke (with the user)** — add to this repo's `.claude/requirements.local.yaml`:

```yaml
sentry:
  org: harmaalbers
  project: <pick an existing project>
```

Then run `/arch-review` on this branch via the `--plugin-dir` dev build and confirm the sentry-triage teammate spawns, searches, and reports (or cleanly reports SKIPPED/CLEAN). Remove the test block after, if unwanted.

---

## Out of scope (deliberate)

- `/deep-review` wiring — deferred until validate-time value is proven.
- Auto-discovery of org/project — rejected in design (wrong-org risk).
- Python config-schema support for `sentry:` — not needed; prompts read YAML directly.
