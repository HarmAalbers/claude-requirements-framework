# Step 07 Deletion-Pass Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use requirements-framework:executing-plans to implement this plan task-by-task.

**Goal:** Delete three deprecated plugin artifacts (`/plan-review`, `/quality-check`, `code-simplifier` agent) and the dead `briefing_format: rich` code path, ship as plugin v4.0.0 with a Keep-a-Changelog `CHANGELOG.md`.

**Architecture:** Subtractive change on branch `refactor/step-07-finish-and-delete`. Eight atomic stg patches, each independently revertible. Test suite (1279/1279) must pass after every patch. References design doc `.claude/plans/simplification/07-deletion-pass-design.md`.

**Tech Stack:** Stacked Git (stg), Python 3 stdlib + PyYAML, `python3 hooks/test_requirements.py`, `./sync.sh deploy`.

---

## Pre-flight verification

Before starting any task, confirm the branch state.

**Step 0.1: Confirm branch and stg state**

```bash
git branch --show-current
stg series
```

Expected:
```
refactor/step-07-finish-and-delete
+ design-step-07-deletion-pass
> plan-step-07-deletion-pass
```

(The `>` marker is on the in-progress plan patch this file is being written into.)

**Step 0.2: Confirm baseline test count**

```bash
./sync.sh deploy && python3 ~/.claude/hooks/test_requirements.py 2>&1 | tail -5
```

Expected: `OK` line with `1279` (or current count); record this number — every later task references it.

---

## Task 0 (pre-execution): Amend ADR-012 to remove prohibition against deletion

**Blocker**: ADR-012 (`docs/adr/ADR-012-agent-teams-integration.md`) has an explicit `## Prohibited` section at lines 88–92:

> **Removing existing subagent commands**:
> - `/plan-review` and `/quality-check` must remain available as lightweight alternatives
> - Users who prefer lower token cost should always have a working option

This prohibition was written in the context of the team-command rollout (2026-02-13), when the lightweight alternatives needed protection to ensure the ecosystem wasn't disrupted mid-rollout. Now that the team-based commands are mature and the deprecation was publicly marked in 3.x, the rationale for the prohibition is no longer operative. The 4.0.0 clean break supersedes it.

**This task MUST complete before any deletion patches execute.** The ADR corpus must be internally consistent; merging deletions that contradict a standing `## Prohibited` section leaves the docs in a misleading state.

**Files:**
- Modify: `docs/adr/ADR-012-agent-teams-integration.md`

**Step 0.1: Create the stg patch**

```bash
stg new amend-adr-012-remove-prohibition -m "docs(adr): amend ADR-012 to supersede deletion prohibition

The Prohibited section at lines 88-91 states that /plan-review and /quality-check
must remain as lightweight alternatives. This prohibition was correct at the time
of the 2026-02-13 team-command rollout, when the alternatives needed protection.

4.0.0 (2026-05-20) removes both commands via a planned breaking release. The
deprecation was publicly marked in 3.x commits 3ca0bde and bdd0dc1. The ADR
prohibition is superseded by the clean-break policy established for 4.0.0.

This amendment documents the supersession so the ADR corpus remains internally
consistent post-deletion."
```

**Step 0.2: Edit ADR-012**

In `docs/adr/ADR-012-agent-teams-integration.md`, modify the `## Prohibited` section's "Removing existing subagent commands" block to read:

```markdown
**Removing existing subagent commands**:
- ~~`/plan-review` and `/quality-check` must remain available as lightweight alternatives~~
- **Superseded by 4.0.0 (2026-05-20)**: Both commands were marked deprecated in 3.x (commits `3ca0bde`, `bdd0dc1`) and removed in the 4.0.0 clean-break release. `/arch-review` is the replacement for plan-review; `/deep-review` is the replacement for quality-check.
```

Also update the `## Status` header to record the amendment:

```markdown
## Status
Approved (2026-02-13)
Amended (2026-02-13): Team commands promoted to primary review approach
Amended (2026-02-16): /pre-commit upgraded to team-based with subagent fallback
Amended (2026-02-17): /deep-review overhaul — all agents always run, no max_teammates cap, code-simplifier as teammate
Amended (2026-05-20): Prohibition against removing /plan-review and /quality-check superseded by 4.0.0 clean-break
```

**Step 0.3: Refresh**

```bash
git add docs/adr/ADR-012-agent-teams-integration.md
stg refresh
```

**Step 0.4: Confirm**

```bash
grep -A5 "Removing existing subagent" docs/adr/ADR-012-agent-teams-integration.md
```

Expected: the strikethrough text and "Superseded by 4.0.0" line visible.

---

## Task 1: Update status memory (mid-deletion pointer)

**Files:**
- Modify: `/Users/harm/.claude/projects/-Users-harm-Tools-claude-requirements-framework/memory/refactor-current-status.md`

**Step 1.1: Create the stg patch**

```bash
stg new update-status-memory-mid-deletion -m "memory: mark steps 03-07 merged to master, deletion-pass in progress

The previous memory snapshot was one merge behind reality. This patch:
- Flips steps 03-07 from 'stacked' to 'merged (commit <sha>)'
- Records that the 2-week soak was skipped per user decision 2026-05-20
- Sets the 'what next' pointer to 'deletion in progress on refactor/step-07-finish-and-delete'"
```

**Step 1.2: Update the memory file**

Change the simplification status table to mark Steps 03–07 as `✅ merged (<commit-sha>)` and bump `Last updated:` to today.

Required edits to `refactor-current-status.md`:
- Header line: `**Last updated: 2026-05-20** (Steps 03–07 merged to master; deletion-pass in progress on `refactor/step-07-finish-and-delete`)`
- Status table rows 03–07: change `🔄 stacked (...)` to `✅ merged (<sha>)` using `git log master --oneline | grep -E "Step 0[3-7]"` to pick the sha
- "What next" section: rewrite to say deletion-pass is in flight; soak skipped per user decision 2026-05-20

**Step 1.3: Refresh the patch**

```bash
stg refresh
stg show | head -20
```

Expected: the diff shows only the memory file modified, with the status table changes visible.

**Step 1.4: Run test suite** (sanity — should be unaffected by memory edit)

```bash
python3 hooks/test_requirements.py 2>&1 | tail -5
```

Expected: `OK` with baseline count.

---

## Task 2: Delete `/plan-review` command

**Files:**
- Delete: `plugins/requirements-framework/commands/plan-review.md`
- Modify: `CLAUDE.md` (table referencing `/plan-review`)
- Modify: `hooks/auto-satisfy-skills.py` (mapping for `plan-review` → multiple requirements)
- Modify: `hooks/handle-plan-exit.py` (lines 138–148: hardcoded `plan-review` skill check and `/plan-review` output string)
- Modify: `hooks/handle-session-start.py` (lines 203, 249: docstring examples referencing `/plan-review`)
- Possibly modify: `README.md`, `docs/PLUGIN-INSTALLATION.md`, `plugins/requirements-framework/README.md`

> **Behavioral bug (HIGH)**: `hooks/handle-plan-exit.py` lines 138–148 hardcode a check for
> `auto_resolve_skill == 'requirements-framework:plan-review'` and emit `/plan-review` as the
> user-visible next action. After deletion, any user with `auto_resolve_skill: requirements-framework:plan-review`
> in their config will see a dead command every time they exit plan mode. Fix: generalize the
> `all_plan_review` path to use `_shorten_skill_name` dynamically from the skill name, or simply
> remove the special-case and let it fall through to the generic table renderer (lines 154–164).
>
> Lines 203 and 249 in `handle-session-start.py` are docstring examples — they are **not** runtime
> output. Update them to `/arch-review` for documentation accuracy.

**Step 2.1: Find all references**

```bash
grep -rn "plan-review" --include="*.md" --include="*.py" --include="*.yaml" --include="*.json" . | grep -v "^./node_modules" | grep -v "^./.git"
```

Expected: a list of references — the command file itself, CLAUDE.md table entries, auto-satisfy mapping, plus any docs. Capture this list before any deletion.

**Step 2.2: Create the stg patch**

```bash
stg new delete-plan-review-command -m "remove: /plan-review command (superseded by /arch-review and /req plan)

The plan-review command was marked deprecated in commit 3ca0bde. Its scope is fully
covered by /arch-review (team-based, cross-validated) and the /req plan conductor.

This patch:
- Deletes plugins/requirements-framework/commands/plan-review.md
- Removes the plan-review entry from hooks/auto-satisfy-skills.py's skill→requirement map
- Updates CLAUDE.md test-commands list and lightweight-alternatives table
- Updates docs and README that referenced /plan-review"
```

**Step 2.3: Delete the command file**

```bash
git rm plugins/requirements-framework/commands/plan-review.md
```

**Step 2.4: Update `hooks/auto-satisfy-skills.py`**

Read the file, locate the dictionary entry where the key is `'requirements-framework:plan-review'` (or similar) mapping to `['commit_plan', 'adr_reviewed', 'tdd_planned', 'solid_reviewed']`, and remove that entry. Use the Read tool first to locate it, then Edit to remove.

**Step 2.5: Update `CLAUDE.md`**

Read lines mentioning `/plan-review` in CLAUDE.md (there are at least two: the test-commands block under "Test commands" and the lightweight-alternatives table under "When to Use Teams vs Lightweight Alternatives"). Remove the `/plan-review` rows; in the auto-satisfy mapping list, remove the "Maps: /requirements-framework:plan-review → ..." line.

**Step 2.6: Fix `hooks/handle-plan-exit.py` (behavioral bug)**

Read lines 135–165. The `all_plan_review` special-case block (lines 138–152) emits a hardcoded `/plan-review`
string to the user. Fix by removing the special-case entirely — let all unsatisfied requirements fall through
to the generic table renderer (lines 154–164), which derives commands dynamically from config.

Before edit:
```python
# Check if all unsatisfied requirements can be resolved by plan-review
all_plan_review = all(
    req_config.get('auto_resolve_skill', '') == 'requirements-framework:plan-review'
    for _, req_config in unsatisfied
)

lines = ["## Plan Validation Required", ""]

if all_plan_review:
    # Simple directive when plan-review resolves all
    lines.append("**Next Action (run now)**: `/plan-review`")
    lines.append("")
    lines.append("Run this immediately after exiting plan mode, before any Edit/Write call.")
    lines.append("")
    lines.append(f"Satisfies: {', '.join(req_names)}")
else:
    # Show table for mixed requirements
    lines.append("| Requirement | Execute |")
    lines.append("|-------------|---------|")
    ...
```

After edit (delete the `all_plan_review` branch entirely, keep only the table renderer):
```python
lines = ["## Plan Validation Required", ""]
lines.append("| Requirement | Execute |")
lines.append("|-------------|---------|")

for req_name, req_config in unsatisfied:
    auto_skill = req_config.get('auto_resolve_skill', '')
    if auto_skill:
        short_skill = _shorten_skill_name(f"/{auto_skill}")
        lines.append(f"| {req_name} | `{short_skill}` |")
    else:
        lines.append(f"| {req_name} | `req satisfy {req_name}` |")
```

**Step 2.7: Update `hooks/handle-session-start.py` docstrings**

Lines 203 and 249 are in docstring example output — not user-visible at runtime. Update both to reference
`/arch-review` instead of `/plan-review` so the docstring reflects the actual replacement command.

Line 203: `**Run \`/plan-review\`** → ...` → `**Run \`/arch-review\`** → ...`
Line 249: `🚀 **Run \`/plan-review\`** → ...` → `🚀 **Run \`/arch-review\`** → ...`

**Step 2.9: Update `README.md` and other docs**

```bash
grep -rn "plan-review" --include="*.md" .
```

For each remaining reference, replace with `/arch-review` (or `/req plan` where context fits).

**Step 2.10: Refresh and test**

```bash
git add -A
stg refresh
./sync.sh deploy && python3 ~/.claude/hooks/test_requirements.py 2>&1 | tail -5
```

Expected: tests pass with the same baseline count. If a test referenced `/plan-review` explicitly, it should still pass (test references that command's *deprecation*, not its existence), or be removed in this same patch.

**Step 2.11: Final sweep grep**

```bash
grep -rn "plan-review" --include="*.md" --include="*.py" --include="*.yaml" . | grep -v "^./.git" | grep -v "CHANGELOG" | grep -v "plans/simplification"
```

Expected: empty (or only references in plan/design docs which are historical, and the upcoming CHANGELOG entry).

---

## Task 3: Delete `/quality-check` command

**Files:**
- Delete: `plugins/requirements-framework/commands/quality-check.md`
- Modify: `CLAUDE.md`
- Modify: `hooks/auto-satisfy-skills.py`
- Possibly modify: `README.md`, `docs/`

**Step 3.1: Find all references**

```bash
grep -rn "quality-check" --include="*.md" --include="*.py" --include="*.yaml" --include="*.json" . | grep -v "^./.git"
```

**Step 3.2: Create the stg patch**

```bash
stg new delete-quality-check-command -m "remove: /quality-check command (superseded by /deep-review)

The quality-check command was marked deprecated in commit 3ca0bde. /deep-review is
the cross-validated team-based replacement; quality-check's parallel-subagent mode
was a lightweight alternative kept while the team-based path stabilized.

This patch:
- Deletes plugins/requirements-framework/commands/quality-check.md
- Removes the quality-check entry from hooks/auto-satisfy-skills.py's mapping
- Updates CLAUDE.md (test-commands list, lightweight-alternatives table, auto-satisfy mapping list)
- Updates docs that referenced /quality-check"
```

**Step 3.3: Delete the command file**

```bash
git rm plugins/requirements-framework/commands/quality-check.md
```

**Step 3.4: Update `hooks/auto-satisfy-skills.py`**

Remove the entry mapping `'requirements-framework:quality-check'` (or similar) to `['pre_pr_review']`.

**Step 3.5: Update `CLAUDE.md`**

Same pattern as Task 2.5: remove `/quality-check` rows from test-commands block and the lightweight-alternatives table; remove the "Maps: /requirements-framework:quality-check → ..." line.

**Step 3.6: Refresh and test**

```bash
git add -A
stg refresh
./sync.sh deploy && python3 ~/.claude/hooks/test_requirements.py 2>&1 | tail -5
```

Expected: baseline count.

**Step 3.7: Final sweep grep**

```bash
grep -rn "quality-check" --include="*.md" --include="*.py" --include="*.yaml" . | grep -v "^./.git" | grep -v "CHANGELOG" | grep -v "plans/simplification"
```

Expected: empty.

---

## Task 4: Delete `code-simplifier` agent

**Files:**
- Delete: `plugins/requirements-framework/agents/code-simplifier.md`
- Modify: `plugins/requirements-framework/.claude-plugin/plugin.json` (remove from `agents` array; bump version to 4.0.0)
- Modify: `hooks/handle-subagent-start.py` (remove `'requirements-framework:code-simplifier'` from `REVIEW_AGENTS` set — stale entry, harmless at runtime but prevents misleading context injection)
- Modify: `CLAUDE.md` (agent list)
- Possibly modify: `plugins/requirements-framework/README.md`, command files that invoke `code-simplifier`

**Step 4.1: Find all references**

```bash
grep -rn "code-simplifier" --include="*.md" --include="*.py" --include="*.yaml" --include="*.json" . | grep -v "^./.git"
```

Critical: if any command or skill file invokes `code-simplifier` via the Task tool, that file must be updated to use `code-reviewer` (or have the invocation removed) atomically.

**Step 4.2: Create the stg patch**

```bash
stg new delete-code-simplifier-agent -m "remove: code-simplifier agent (superseded by code-reviewer)

Agent audit identified code-simplifier as fully overlapping with code-reviewer.
Marked deprecated in commit 3ca0bde.

This patch:
- Deletes plugins/requirements-framework/agents/code-simplifier.md
- Removes the ./agents/code-simplifier.md line from plugin.json agents array
- Updates CLAUDE.md agents list
- Redirects any internal Task-tool invocations of code-simplifier → code-reviewer"
```

**Step 4.3: Delete the agent file**

```bash
git rm plugins/requirements-framework/agents/code-simplifier.md
```

**Step 4.4: Update `plugin.json`**

Remove the `"./agents/code-simplifier.md",` line from the `agents:` array. Keep the trailing comma policy consistent with the file's existing style (JSON does not allow trailing commas — the line above the removed line keeps its comma; the new last line of the array should not have one).

**Step 4.5: Update `CLAUDE.md`**

In the "Test agents" block under `## Testing Plugin Components`, remove `code-simplifier` from the comma-separated list.

**Step 4.6: Update `hooks/handle-subagent-start.py` — remove stale REVIEW_AGENTS entry**

Read the `REVIEW_AGENTS` set near the top of the file. Remove the `'requirements-framework:code-simplifier'` entry. This set controls which subagents receive requirement context injection at spawn time. After agent deletion, a match against a non-existent agent type is harmless at runtime (the spawn never happens), but leaving it in creates a misleading suggestion that the agent is still active.

```bash
grep -n "code-simplifier" hooks/handle-subagent-start.py
```

Expected: one line in `REVIEW_AGENTS`. Remove it.

**Step 4.7: Redirect any Task invocations**

```bash
grep -rn "subagent_type.*code-simplifier" --include="*.md" --include="*.py" .
grep -rn "Agent.*code-simplifier" --include="*.md" --include="*.py" .
```

If any matches, replace with `code-reviewer` in the same patch.

> Note: `deep-review.md` lines 167–168 use plain prose references to `code-simplifier` (not a `subagent_type` pattern), so the grep above will miss them. Check lines 160–175 of `deep-review.md` manually and update the cross-validation rule table if `code-simplifier` is listed there.

**Step 4.8: Refresh and test**

```bash
git add -A
stg refresh
./sync.sh deploy && python3 ~/.claude/hooks/test_requirements.py 2>&1 | tail -5
```

Expected: baseline count, *and* the plugin loads cleanly (the agents array change is structural). Watch the test output for any "plugin failed to load" or schema errors.

**Step 4.9: Smoke-test plugin load**

```bash
python3 -c "import json; m = json.load(open('plugins/requirements-framework/.claude-plugin/plugin.json')); print('agents:', len(m['agents'])); assert all('code-simplifier' not in a for a in m['agents'])"
```

Expected: `agents: <N-1>` (one fewer than before), no AssertionError.

---

## Task 5: Delete `briefing_format: rich` code path

**Files:**
- Modify: `hooks/handle-session-start.py` (remove the `if briefing_format == 'rich':` branch)
- Possibly modify: `hooks/lib/` helpers that build the rich format
- Modify: `hooks/test_requirements.py` (delete any test cases targeting rich format)
- Possibly modify: `hooks/lib/config.py` (if it validates `briefing_format` values, restrict to `compact`)

**Step 5.1: Map the rich-format surface**

```bash
grep -rn "rich" hooks/ | grep -i "briefing\|format" | grep -v "^hooks/.git"
grep -rn "briefing_format" hooks/ | grep -v "^hooks/.git"
```

Expected: a small set of references — the dispatcher in `handle-session-start.py`, possibly a helper file, and any tests that exercise `briefing_format: rich`.

**Step 5.2: Create the stg patch**

```bash
stg new delete-rich-briefing-format -m "remove: briefing_format: rich code path (only compact remains)

Step 01 made 'compact' the default and removed bootstrap, but the 'rich' branch
remained as a fallback. With no consumers and no audit-detected usage, the rich
path is now removed.

This patch:
- Deletes the 'rich' branch from hooks/handle-session-start.py
- Removes any helpers in hooks/lib/ that only served the rich format
- Removes tests targeting briefing_format: rich
- Tightens config validation so briefing_format only accepts 'compact'"
```

**Step 5.3: Edit `handle-session-start.py`**

Locate the `briefing_format` dispatch (likely a conditional or dict). Remove the rich branch entirely. If the dispatch becomes trivial (only one valid value), simplify it to a direct call.

**Step 5.4: Remove dead helpers**

If any `hooks/lib/*.py` file's only export was the rich builder, `git rm` it. Otherwise, edit out just the rich-format functions.

**Step 5.5: Update tests**

```bash
grep -n "rich" hooks/test_requirements.py
```

For each match in a `def test_*` body, remove that test case. If the test class becomes empty after removal, remove the class too.

**Step 5.6: Tighten config validation (if applicable)**

If `hooks/lib/config.py` enumerates accepted `briefing_format` values, narrow the list to `['compact']`. If it doesn't validate at all, no change needed — the field still works, just with one valid value.

**Step 5.7: Refresh and test**

```bash
git add -A
stg refresh
./sync.sh deploy && python3 ~/.claude/hooks/test_requirements.py 2>&1 | tail -5
```

Expected: count drops by the number of rich-format tests deleted. Record the new baseline.

**Step 5.8: Final sweep grep**

```bash
grep -rn "rich" hooks/ | grep -i "briefing\|format"
```

Expected: empty.

---

## Task 6: Bump plugin version to 4.0.0

**Files:**
- Modify: `plugins/requirements-framework/.claude-plugin/plugin.json`

**Step 6.1: Create the stg patch**

```bash
stg new bump-version-4.0.0 -m "bump: plugin version 3.4.x → 4.0.0 (breaking removals)

Bundles the version bump for the deletion patches above. Bumped at the end of the
deletion sequence so individual deletion patches stay independently revertible
without a version-bump ripple."
```

**Step 6.2: Update version field**

In `plugins/requirements-framework/.claude-plugin/plugin.json`, change the `"version"` field from its current value (e.g., `"3.4.2"` or whatever the post-auto-bump value is) to `"4.0.0"`.

**Step 6.3: Refresh and test**

```bash
git add -A
stg refresh
./sync.sh deploy && python3 ~/.claude/hooks/test_requirements.py 2>&1 | tail -5
```

Expected: baseline count from end of Task 5.

**Step 6.4: Confirm version**

```bash
python3 -c "import json; print(json.load(open('plugins/requirements-framework/.claude-plugin/plugin.json'))['version'])"
```

Expected: `4.0.0`.

---

## Task 7: Add `CHANGELOG.md`

**Files:**
- Create: `CHANGELOG.md` (repo root)

**Step 7.1: Create the stg patch**

```bash
stg new add-changelog -m "docs: add CHANGELOG.md (starts at 4.0.0)

Keep-a-Changelog format. Documents the 4.0.0 cleanup: removal of /plan-review,
/quality-check, code-simplifier agent, and briefing_format: rich. Prior history
references git log."
```

**Step 7.2: Create the file**

Create `/Users/harm/Tools/claude-requirements-framework/CHANGELOG.md` with:

```markdown
# Changelog

All notable changes to the requirements-framework plugin will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [4.0.0] — 2026-05-20

### Removed

- Command `/plan-review` — superseded by `/arch-review` (team-based, cross-validated) and `/req plan` (conductor).
- Command `/quality-check` — superseded by `/deep-review` (cross-validated team review).
- Agent `code-simplifier` — superseded by `code-reviewer` per agent-audit findings.
- Config value `hooks.session_start.briefing_format: rich` — superseded by `compact` (now the only accepted value).

### Changed

- Plugin major version reset to 4.0.0; deprecated paths landed in 3.x marking commits (`3ca0bde`, `bdd0dc1`) on master and are removed cleanly here.

### Migration

Update muscle memory and any local scripts:

| Old | New |
|---|---|
| `/plan-review` | `/arch-review` |
| `/quality-check` | `/deep-review` |
| `code-simplifier` | `code-reviewer` |
| `briefing_format: rich` | Remove the key entirely; `compact` is the default. |

There is no compatibility shim. The 4.0.0 boundary is intentional.

---

Pre-4.0 history: see `git log master` for commits before 2026-05-20.
```

**Step 7.3: Refresh**

```bash
git add CHANGELOG.md
stg refresh
```

**Step 7.4: Sanity check**

```bash
test -f CHANGELOG.md && head -20 CHANGELOG.md
```

Expected: file exists, top of file matches the content above.

---

## Task 8: MEMORY.md dedupe pass

**Files:**
- Possibly modify: `/Users/harm/.claude/projects/-Users-harm-Tools-claude-requirements-framework/memory/MEMORY.md`

**Step 8.1: Inspect for duplicates**

```bash
cat /Users/harm/.claude/projects/-Users-harm-Tools-claude-requirements-framework/memory/MEMORY.md
```

Look for: two `- [Title](file.md) — ...` lines pointing at the same `.md` file, or two lines with the same title pointing at different files.

**Step 8.2: If duplicates found, create patch and edit**

```bash
stg new memory-dedupe -m "memory: dedupe MEMORY.md index entries"
```

Then edit to remove the duplicates, refresh.

**Step 8.3: If no duplicates, skip the patch**

Move on to Task 9. Record in the final task summary that no dedupe was needed.

---

## Task 9: Update status memory (final state)

**Files:**
- Modify: `/Users/harm/.claude/projects/-Users-harm-Tools-claude-requirements-framework/memory/refactor-current-status.md`

**Step 9.1: Create the stg patch**

```bash
stg new update-status-memory-final -m "memory: step 07 deletion-pass complete; V3 step 08 next

All deletion patches landed and tested. Refactor-current-status.md reflects:
- Step 07 status: ✅ done (deletion pass complete, soak skipped 2026-05-20)
- Plugin version: 4.0.0
- 'What next' pointer: V3 Step 08 (Python LLM package scaffold)"
```

**Step 9.2: Update the memory file**

- Header: `**Last updated: 2026-05-20** (Step 07 deletion-pass complete; V3 phase unblocked)`
- Status table row 07: `✅ done (deletion pass — soak skipped per user decision 2026-05-20)`
- "What next" section: rewrite to make Step 08 the active pointer.

**Step 9.3: Refresh**

```bash
stg refresh
```

---

## Final verification (after all tasks)

**Step F.1: Full stack visible**

```bash
stg series
```

Expected:
```
+ design-step-07-deletion-pass
+ plan-step-07-deletion-pass
+ update-status-memory-mid-deletion
+ delete-plan-review-command
+ delete-quality-check-command
+ delete-code-simplifier-agent
+ delete-rich-briefing-format
+ bump-version-4.0.0
+ add-changelog
+ memory-dedupe        (only if Task 8 produced a patch)
> update-status-memory-final
```

**Step F.2: Test suite green**

```bash
./sync.sh deploy && python3 ~/.claude/hooks/test_requirements.py 2>&1 | tail -5
```

Expected: `OK` (count may be slightly lower than baseline if rich-format tests were removed in Task 5).

**Step F.3: Plugin loads in fresh session**

Suggest the user run `claude --plugin-dir /Users/harm/Tools/claude-requirements-framework/plugins/requirements-framework` in a separate terminal to confirm the plugin loads with the new manifest.

**Step F.4: Invoke `/verification-before-completion`**

Satisfies `verification_evidence` requirement.

**Step F.5: Invoke `/deep-review`**

Cross-validated team review of the full branch. Satisfies `pre_pr_review`.

**Step F.6: Invoke `/codex-review`**

External Codex CLI review. Satisfies `codex_reviewer`.

**Step F.7: Surface unsatisfied requirements**

```bash
req status
```

Expected: 0 unsatisfied (or all explicitly justified).

---

## Preparatory Refactoring

Analysis of the three main files touched by this plan. Conclusion: **no preparatory refactoring is warranted**. Detailed reasoning below.

---

### 1. `handle-session-start.py` — `format_adaptive_status` dispatcher

**Refactor considered**: Extract the `format_adaptive_status` logic into a dispatch table (dict mapping mode → formatter function) so the `rich` deletion is a one-key dict removal rather than a code branch removal.

**Decision: Defer / skip (LOW)**

The dispatcher is already minimal (lines 418–429 in the file). The current structure is:
```python
if mode == 'standard': return ...
if mode == 'rich':     return ...   # ← the line being deleted
# compact fallback
```
Deleting the `rich` branch is already a 2-line surgical edit. Extracting a dispatch table first would be a net increase in complexity for a deletion that is already trivially atomic. The docstring on `format_adaptive_status` also needs updating (it lists three formats), but that is part of the deletion patch itself, not preparatory.

**No preparatory work needed.**

---

### 2. `auto-satisfy-skills.py` — `DEFAULT_SKILL_MAPPINGS`

**Refactor considered**: Move `DEFAULT_SKILL_MAPPINGS` to a YAML config file so deletion of `plan-review` and `quality-check` entries becomes a data-only change, not a code change.

**Decision: Defer / skip (LOW)**

The two entries being deleted (`requirements-framework:plan-review` and `requirements-framework:quality-check`) are clearly identified at lines 48 and 44 respectively. The deletion is a 2-line removal in a flat dict literal. Moving to YAML first would: (a) add a file, (b) add a YAML load path, (c) require updating tests — all to enable a simpler deletion that is already simple. YAGNI: there is no evidence the mappings need to be user-configurable beyond the already-supported `satisfied_by_skill` field on individual requirements.

One observation worth noting: the comment `# Default skill to requirement mapping (for backwards compatibility)` at line 43 is slightly misleading — the dict is the *primary* mapping, not a backwards-compat shim. The deletion patch for Task 2/3 should update that comment, but no preparatory step is needed.

**No preparatory work needed.**

---

### 3. `plugin.json` — `agents` array

**Refactor considered**: Auto-generate the `agents` array from the `plugins/requirements-framework/agents/` directory listing so that deleting `code-simplifier.md` from disk automatically removes it from the manifest.

**Decision: Defer / skip (LOW)**

Auto-generation would require a build step (a script or Makefile target) that must be run and committed every time an agent is added or removed. That is a build process complexity increase. The current workflow — edit `plugin.json` manually alongside the agent file — is intentional and captured in CLAUDE.md's bump instructions. The `code-simplifier` deletion is a one-line JSON edit at line 18; the smoke-test in Task 4.8 already validates the result. Auto-generation is future work if the agent count grows large enough to make manual sync error-prone.

**No preparatory work needed.**

---

### Summary

All three planned deletions are already scoped to surgical, line-level edits. No preparatory restructuring would materially ease the removals beyond what the plan already describes. Proceed directly to Task 1.

---

## Commit Strategy (Refined)

### Summary of changes from original proposal

**The CLAUDE.md contradiction (resolved):**
The original proposal placed the version bump in a standalone Patch #6 (`bump-version-4.0.0`) after all deletions. CLAUDE.md is explicit: *"when a patch touches plugin files, bump `plugin.json` inside the same patch (not a separate one)."* Patch #4 (`delete-code-simplifier-agent`) already modifies `plugin.json` to remove the agent entry. Since Patch #4 is the last patch that legitimately modifies `plugin.json`, the version bump is folded into it. This satisfies both goals: individual deletion patches #2 and #3 remain independently revertible (they don't touch `plugin.json`), and the version bump lands atomically with the structural manifest change that justifies it.

**Memory patches collapsed:**
The original Patch #1 (`update-status-memory-mid-deletion`) and Patch #9 (`update-status-memory-final`) serve different purposes — one marks the deletion as "in-progress", the other marks it "complete." Since both live on the same local branch (never independently visible to others), the mid-deletion pointer has no audience until the branch is merged, at which point it is already out of date. The two patches are collapsed into a single final-state patch at the end of the stack. This reduces the patch count by one and avoids committing a transient intermediate state that immediately becomes stale.

**Rich-format test deletion stays with the code patch:**
Tests covering the rich briefing path exist solely to verify that code path. Deleting them in the same patch as the code deletion is correct — splitting would leave the test suite testing deleted code for one patch, creating a phantom green-to-green transition that obscures the real change.

---

### Refined sequence (8 patches)

| # | Patch name | Files touched | Test command | What to validate |
|---|---|---|---|---|
| 0 | `amend-adr-012-remove-prohibition` | `docs/adr/ADR-012-agent-teams-integration.md` | n/a (docs only) | `## Status` block shows 2026-05-20 amendment; `## Prohibited` block shows strikethrough + supersession note |
| 1 | `delete-plan-review-command` | `commands/plan-review.md` (rm), `hooks/auto-satisfy-skills.py`, `hooks/handle-plan-exit.py` (remove hardcoded `/plan-review` output), `hooks/handle-session-start.py` (update docstring examples), `CLAUDE.md`, `README.md`, any docs referencing `/plan-review` | `python3 hooks/test_requirements.py` | Baseline count unchanged; `grep -rn "plan-review"` returns empty (excluding plan/CHANGELOG files); `handle-plan-exit.py` no longer contains `requirements-framework:plan-review` literal |
| 2 | `delete-quality-check-command` | `commands/quality-check.md` (rm), `hooks/auto-satisfy-skills.py`, `CLAUDE.md`, `README.md`, any docs referencing `/quality-check` | `python3 hooks/test_requirements.py` | Baseline count unchanged; `grep -rn "quality-check"` returns empty (excluding plan/CHANGELOG files) |
| 3 | `delete-code-simplifier-agent` | `agents/code-simplifier.md` (rm), `plugin.json` (remove agent entry AND bump version to 4.0.0), `hooks/handle-subagent-start.py` (remove from REVIEW_AGENTS set), `CLAUDE.md` agents list, any docs | `python3 hooks/test_requirements.py` + `python3 -m json.tool plugin.json` | Baseline count unchanged; plugin JSON valid; agent removed; version = 4.0.0; `handle-subagent-start.py` no longer contains `requirements-framework:code-simplifier` |
| 4 | `delete-rich-briefing-format` | `hooks/handle-session-start.py`, any `hooks/lib/` helpers only serving rich format (rm or edit), tests in `hooks/test_requirements.py` covering `briefing_format: rich`, `hooks/lib/config.py` if it enumerates valid briefing_format values | `python3 hooks/test_requirements.py` | Count drops by N (number of rich tests removed); `grep -rn "rich" hooks/ \| grep -i "briefing\|format"` returns empty |
| 5 | `add-changelog` | `CHANGELOG.md` (new, repo root) | `test -f CHANGELOG.md && head -5 CHANGELOG.md` | File exists with correct Keep-a-Changelog header; 4.0.0 entry covers all four removed items |
| 6 | `memory-dedupe` | `memory/MEMORY.md` (only if duplicates found) | n/a (no code) | Inspect output of `cat MEMORY.md`; skip patch entirely if no duplicates |
| 7 | `update-status-memory-final` | `memory/refactor-current-status.md` | `python3 hooks/test_requirements.py` | Baseline count from end of Patch #4; memory file reflects Step 07 complete, plugin v4.0.0, V3 Step 08 next |

> Note: the `plan-step-07-deletion-pass` patch (this file) and `design-step-07-deletion-pass` are already on the stack as pre-existing patches. The 8 patches above stack on top of them.

---

### Per-patch detail

**Patch #0 — `amend-adr-012-remove-prohibition`**

Docs-only patch. No code changes, no test impact.

Edit `docs/adr/ADR-012-agent-teams-integration.md`:

1. Add a new amendment line to `## Status`:
   `Amended (2026-05-20): Prohibition against removing /plan-review and /quality-check superseded by 4.0.0 clean-break`

2. In `## Prohibited`, replace the "Removing existing subagent commands" block with a strikethrough + supersession note:
   ```
   **Removing existing subagent commands** ~~(superseded 2026-05-20)~~:
   - ~~`/plan-review` and `/quality-check` must remain available as lightweight alternatives~~
   - ~~Users who prefer lower token cost should always have a working option~~
   - **Superseded by 4.0.0 (2026-05-20)**: Both commands were marked deprecated in 3.x (commits `3ca0bde`, `bdd0dc1`) and removed in the 4.0.0 clean-break release. `/arch-review` replaces `/plan-review`; `/deep-review` replaces `/quality-check`. See CHANGELOG.md for migration guidance.
   ```

Validate: `grep -A4 "Removing existing" docs/adr/ADR-012-agent-teams-integration.md` shows the supersession note.

Independently revertible: yes — docs only.

---

**Patch #1 — `delete-plan-review-command`**

Pre-work: `grep -rn "plan-review" --include="*.md" --include="*.py" --include="*.yaml" . | grep -v "^./.git"` — capture full list before touching anything.

Files to cover:
- `plugins/requirements-framework/commands/plan-review.md` (delete)
- `hooks/auto-satisfy-skills.py` (remove `requirements-framework:plan-review` dict entry)
- `hooks/handle-plan-exit.py` (lines 138–152): remove the `all_plan_review` special-case block that emits a hardcoded `/plan-review` string. Delete the variable declaration and the entire `if all_plan_review:` branch; retain the `else:` table renderer but remove the `else:` keyword (the table path becomes unconditional).
- `hooks/handle-session-start.py` (lines 203, 249): update docstring example strings from `/plan-review` to `/arch-review` (documentation accuracy; these are not runtime output).
- `CLAUDE.md` (remove from test-commands block, lightweight-alternatives table, auto-satisfy mapping list)
- `README.md`, `plugins/requirements-framework/README.md`, `docs/PLUGIN-INSTALLATION.md`

Validate: Test suite at baseline; `grep -rn "plan-review"` empty outside plan/CHANGELOG/design docs; `grep -n "requirements-framework:plan-review" hooks/handle-plan-exit.py` returns empty.

Independently revertible: yes — touches no `plugin.json`, no shared state.

---

**Patch #2 — `delete-quality-check-command`**

Same pattern as Patch #1 with `quality-check` as the search term. Remove `requirements-framework:quality-check` dict entry from `hooks/auto-satisfy-skills.py`.

Pre-work: `grep -rn "quality-check" --include="*.md" --include="*.py" --include="*.yaml" . | grep -v "^./.git"`

Validate: Test suite at baseline; `grep -rn "quality-check"` empty outside plan/CHANGELOG/design docs.

Independently revertible: yes — touches no `plugin.json`.

---

**Patch #3 — `delete-code-simplifier-agent` (includes version bump)**

This is the only patch that modifies `plugin.json`. Per CLAUDE.md, the version bump lives here.

Steps in order:
1. `git rm plugins/requirements-framework/agents/code-simplifier.md`
2. Edit `plugin.json`: remove `"./agents/code-simplifier.md"` from agents array **and** bump `"version"` to `"4.0.0"` in the same edit pass. Watch trailing-comma correctness — JSON does not allow trailing commas.
3. Update `CLAUDE.md` agents list.
4. Remove `'requirements-framework:code-simplifier'` from `REVIEW_AGENTS` set in `hooks/handle-subagent-start.py`. This set controls which subagents receive requirement context injection — a stale entry pointing at a deleted agent is harmless at runtime but misleading in code review.
5. Check for Task-tool redirects: `grep -rn "subagent_type.*code-simplifier\|Agent.*code-simplifier" --include="*.md" --include="*.py" .` — replace with `code-reviewer` if found.
6. Check `plugins/requirements-framework/commands/deep-review.md` lines 160–175 **manually** for prose references to `code-simplifier` in the cross-validation rule table — the grep in step 5 uses a `subagent_type.*` pattern and will miss plain prose mentions.

JSON integrity check after edit:
```bash
python3 -m json.tool plugins/requirements-framework/.claude-plugin/plugin.json > /dev/null && echo "JSON valid"
python3 -c "import json; m=json.load(open('plugins/requirements-framework/.claude-plugin/plugin.json')); assert m['version']=='4.0.0'; assert all('code-simplifier' not in a for a in m['agents']); print('agents:', len(m['agents']))"
```

Independently revertible: yes — `stg pop` undoes agent deletion + version bump together, which is correct since the version bump is justified by this exact deletion.

---

**Patch #4 — `delete-rich-briefing-format`**

Steps:
1. Map the surface: `grep -rn "briefing_format\|rich" hooks/ | grep -v "test_"` then separately `grep -n "rich" hooks/test_requirements.py`.
2. Remove `if briefing_format == 'rich':` branch (and any dead helpers) from `handle-session-start.py`. If dispatch becomes trivial (one value), simplify to a direct call.
3. Remove dead helpers: if any `hooks/lib/*.py` file only served the rich builder, `git rm` it.
4. Remove rich-format test cases from `test_requirements.py`. If a test class becomes empty, remove the class too.
5. If `hooks/lib/config.py` enumerates valid `briefing_format` values, narrow to `['compact']`.

New test baseline = old baseline minus N (where N = number of rich-format tests removed). Record this as the new baseline for Patches #5-7.

Final sweep: `grep -rn "rich" hooks/ | grep -i "briefing\|format"` — must be empty.

Independently revertible: yes — pure code-path removal, no manifest changes.

---

**Patch #5 — `add-changelog`**

Purely additive. No risk of breaking anything. Place after all deletions so the CHANGELOG entry can accurately describe the full 4.0.0 surface that was removed.

Content: Keep-a-Changelog format, starting at `[4.0.0] — 2026-05-20`, with `### Removed`, `### Changed`, `### Migration` sections as specified in the design doc.

---

**Patch #6 — `memory-dedupe` (conditional)**

Run `cat /Users/harm/.claude/projects/-Users-harm-Tools-claude-requirements-framework/memory/MEMORY.md` and inspect. Two entries are duplicates only if they point at the *same file* — similar-sounding titles pointing at different files are not duplicates.

Skip this patch entirely if no true duplicates are found.

---

**Patch #7 — `update-status-memory-final`**

Final state update only (no mid-deletion pointer needed — mid-deletion state is transient and local).

Required edits to `refactor-current-status.md`:
- Header: `**Last updated: 2026-05-20** (Step 07 deletion-pass complete; V3 Step 08 next)`
- Step 07 row: `✅ done (deletion pass — soak skipped per user decision 2026-05-20; plugin v4.0.0)`
- "What next" section: V3 Step 08 is the active pointer.

---

### Deviations from original proposal

| Original | Refined | Reason |
|---|---|---|
| Patch #6 `bump-version-4.0.0` (standalone) | Folded into Patch #3 | CLAUDE.md rule: version bump goes in the same patch that modifies `plugin.json`. Patch #3 is the only patch touching `plugin.json`. |
| Patch #1 `update-status-memory-mid-deletion` | Removed entirely | Mid-deletion state is a transient local pointer with no external audience; collapsing into the final memory patch is cleaner. |
| 9 patches total (+ conditional dedupe) | 7 patches total (+ conditional dedupe already counted) | Net -2: standalone version bump and mid-deletion memory patches eliminated. |
| CHANGELOG after version bump (Patch #7) | CHANGELOG after all deletions as Patch #5 | No change in substance; version bump now lives in Patch #3, CHANGELOG still lands after all code changes. |

---

## Notes on stg edge cases

- If `stg new` opens an editor instead of taking `-m` (system mis-config), pass `--no-edit` after `-m`.
- If `stg refresh` complains about untracked files, use `git add <file>` first, then `stg refresh --index`.
- To inspect any patch in detail: `stg show <patch-name>`.
- To rename a patch mid-flight: `stg rename <old> <new>`.
- If a patch needs to be split: `stg pop`, then create two new patches against the popped diff.

---

## Anticipated regressions and how to handle them

| Symptom | Likely cause | Fix |
|---|---|---|
| Test suite drops to N-3 after Task 5 | Three rich-format tests deleted | Confirm the dropped tests were rich-only; accept the new baseline. |
| `req status` complains about a missing requirement | Auto-satisfy mapping was pruned but a satisfier-skill still listed in some file | Grep for the missing satisfier; either restore mapping or remove the consumer. |
| `./sync.sh deploy` fails | Possibly removed a file `sync.sh` still tries to copy | Check sync.sh's file list against deleted paths; update sync list if needed. |
| Plugin fails to load in fresh `claude` session | `plugin.json` agents array has a syntax error after the line removal | Validate JSON: `python3 -m json.tool plugins/requirements-framework/.claude-plugin/plugin.json`. |
