# Live-deriving status skill — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use requirements-framework:executing-plans to implement this plan task-by-task.

**Goal:** Convert `requirements-framework-status` from a hand-maintained static report into a skill that derives every volatile metric at runtime, so it can never drift again.

**Architecture:** Rewrite `SKILL.md.j2` (the render source) to (a) instruct Claude to run a block of verified read-only commands and report their output, and (b) keep only durable conceptual content static. Re-render to `SKILL.md`. Delete the derivable `references/component-inventory.md`. Bump the plugin, refresh git_hash, sync-check.

**Tech Stack:** Markdown + Jinja2 render pipeline (`scripts/render_prompts.py`), stg for commits.

---

## Verified derivation commands (embed these verbatim in the skill)

```bash
# Version
grep '"version"' plugins/requirements-framework/.claude-plugin/plugin.json

# Hook scripts (lifecycle handlers) — exclude tests, the CLI, lib/, and the
# vendored _langfuse_hook.py (leading-underscore = not a registered hook).
ls hooks/*.py | grep -vE 'test_|requirements-cli|/lib/|/_'

# Plugin component counts
ls plugins/requirements-framework/agents/*.md   | wc -l   # agents
ls plugins/requirements-framework/commands/*.md | wc -l   # commands
ls -d plugins/requirements-framework/skills/*/  | wc -l   # skills

# ADRs (read the range from the listing)
ls docs/adr/ADR-*.md

# CLI subcommands
req --help

# Live gating state for the current branch/session
req status
```

Confirmed output 2026-07-06: v4.24.1, 17 hook scripts (16 canonical + opt-in
`langfuse-trace.py`), 24 agents, 16 commands, 21 skills, 20 ADRs.

**Opt-in health check (NOT in the default block — ~28s):** the full test suite is a
heavy side effect for a "status" readout, so the skill marks it optional. Run only
when asked to verify health, and use a summary-sturdy filter:
```bash
python3 hooks/test_requirements.py 2>&1 | grep -E 'Results:|passed' | tail -1
```

---

### Task 1: Rewrite SKILL.md.j2

**Files:**
- Modify: `plugins/requirements-framework/skills/requirements-framework-status/SKILL.md.j2`

**Step 1:** Keep the frontmatter (`name`, `description`, `git_hash`) unchanged except git_hash (handled in Task 4).

**Step 2:** Replace the body. New structure:
1. One-line purpose.
2. `## Live status — run these and report the output` — the verified command block above, each command annotated with what it reports. Instruct: "Run the block, then summarize (version, test pass line, counts, ADR range, live gating). Do NOT quote pre-baked numbers — the point of this skill is that the numbers come from the repo."
3. `## Durable reference (does not change often)` — keep, trimmed: config cascade diagram, the 3-strategy table (Blocking/Dynamic/Guard), requirement scopes table, session lifecycle list, usage guide (`req init`/`status`/`doctor`; dev `./sync.sh`, test runner).
4. `## Deeper reference` — link ONLY `references/architecture-overview.md`.

**Step 3:** Delete from the body: "Current Implementation Status" static version block, "Quick Metrics" table, "Implementation Timeline / Phase 1-3", the static hook table, the static library list, the static agent/command/skill enumerations, the frozen ADR table, "Production Readiness" static counts, and the `component-inventory.md` link.

**Step 4: Commit** — `stg new` + `stg refresh` (Task done together with Task 2/3 render; commit after render is fresh).

---

### Task 2: Delete the derivable reference file

**Files:**
- Delete: `plugins/requirements-framework/skills/requirements-framework-status/references/component-inventory.md`

**Step 1:** `git rm` the file.
**Step 2:** Grep the skill dir for any remaining `component-inventory` links; remove them (should be covered by Task 1).
Run: `grep -rn component-inventory plugins/requirements-framework/skills/requirements-framework-status/` → expect no hits.

---

### Task 3: Re-render SKILL.md from the template

**Files:**
- Modify (generated): `plugins/requirements-framework/skills/requirements-framework-status/SKILL.md`

**Step 1:** `python3 scripts/render_prompts.py` (renders all `.j2` → `.md`).
**Step 2:** Verify freshness: the render script / pre-commit hook reports "all rendered files fresh".
Run: `git diff --stat` → expect `SKILL.md` and `SKILL.md.j2` both changed, `component-inventory.md` deleted.

---

### Task 4: Bump version + git_hash + sync check

**Files:**
- Modify: `plugins/requirements-framework/.claude-plugin/plugin.json` (patch bump: 4.24.1 → 4.24.2)
- Modify: skill frontmatter `git_hash` via `./update-plugin-versions.sh`

**Step 1:** Bump `plugin.json` version (patch).
**Step 2:** `./sync.sh status` — confirm repo vs deployed state is understood (deployed runs from plugin cache; note if a redeploy is needed).
**Step 3:** `./update-plugin-versions.sh` to refresh `git_hash` frontmatter (keep churn contained to this change).

---

### Task 5: Verify by running the derivation block (evidence)

**Step 1:** Execute the full command block from the top of this plan.
**Step 2:** Confirm it prints today's real numbers (v4.24.2 after bump, 1529 tests, correct counts). This is the `verification_evidence`.
**Step 3:** Final commit / refresh so the stack is one clean patch (or logical patches: content, delete, version).

---

## Skipped (YAGNI)
- No helper script, no caching, no CI drift-check — inline derivation is self-verifying every run.
- No pytest test added: this is a documentation/skill change with no runtime code path; verification is running the derivation block (Task 5).

---

## Commit Plan

Two atomic `stg` patches. Rationale for the collapse from 5 tasks → 2 patches:
- The `.j2` rewrite, its rendered `.md`, the `component-inventory.md` deletion, and the `plugin.json` bump are **one logical change** — the skill is only coherent once the template no longer links the deleted reference AND the rendered output matches the source. Splitting any of these leaves an intermediate state where `SKILL.md` links a deleted file or drifts from `SKILL.md.j2` (fails the render-freshness pre-commit hook). The plugin version bump **must ride in this same patch** per the plugin-bump rule (it touches plugin files).
- The `update-plugin-versions.sh` git_hash frontmatter refresh is mechanical churn and is kept in its **own chore patch** per project convention, so the content patch's diff stays reviewable.

### Commit Sequence

| Order | Patch (stg name) | Message | Files | Depends On | Rollback Safe |
|-------|------------------|---------|-------|------------|---------------|
| 1 | `status-skill-live-derive` | `feat(skills): live-derive requirements-framework-status; bump plugin` | `skills/.../SKILL.md.j2`, `skills/.../SKILL.md`, `skills/.../references/component-inventory.md` (del), `.claude-plugin/plugin.json` | - | Yes |
| 2 | `status-skill-git-hash` | `chore: refresh plugin git_hash frontmatter` | skill frontmatter `git_hash` (whatever `update-plugin-versions.sh` touches) | 1 | Yes |

### Commit Details

#### Patch 1: feat(skills): live-derive requirements-framework-status; bump plugin
**Purpose**: Convert the status skill from a hand-maintained static report into a runtime-derived one; delete the now-derivable reference; bump the plugin so the change ships.
**Covers plan tasks**: 1, 2, 3, and the version bump of 4.
**Files**:
- `plugins/requirements-framework/skills/requirements-framework-status/SKILL.md.j2` — body rewrite (live command block + trimmed durable reference; frozen enumerations removed)
- `plugins/requirements-framework/skills/requirements-framework-status/SKILL.md` — regenerated via `python3 scripts/render_prompts.py`
- `plugins/requirements-framework/skills/requirements-framework-status/references/component-inventory.md` — `git rm` (derivable)
- `plugins/requirements-framework/.claude-plugin/plugin.json` — `4.24.1 → 4.24.2` (patch)
**Workflow**:
```bash
stg new status-skill-live-derive
# edit SKILL.md.j2 ; git rm references/component-inventory.md
python3 scripts/render_prompts.py
# bump plugin.json version
stg refresh   # iterate + refresh until the patch is right
```
**Verify before refresh**:
- `grep -rn component-inventory plugins/requirements-framework/skills/requirements-framework-status/` → no hits
- `git diff --stat` → `SKILL.md.j2` + `SKILL.md` modified, `component-inventory.md` deleted, `plugin.json` modified
- render-freshness check / pre-commit hook reports all rendered files fresh (SKILL.md matches SKILL.md.j2)
**Rollback**: Safe to revert as a unit; leaves the prior static skill intact.

#### Patch 2: chore: refresh plugin git_hash frontmatter
**Purpose**: Update `git_hash` frontmatter to point at patch 1's commit; isolated so the feature diff stays clean.
**Covers plan tasks**: git_hash portion of 4.
**Files**:
- Whatever `./update-plugin-versions.sh` rewrites (at minimum the status skill's frontmatter `git_hash`)
**Workflow**:
```bash
stg new status-skill-git-hash
./update-plugin-versions.sh
stg refresh
```
**Verify**:
- `./update-plugin-versions.sh --verify` → hashes current
- `./sync.sh status` → repo vs deployed state understood (note if a plugin-cache redeploy is needed; deployed runs from the plugin cache)
**Rollback**: Safe; pure metadata.

### Test / Evidence Strategy (plan Task 5 — `verification_evidence`)
- No pytest change (docs/skill only). Verification is executing the derivation block from the top of this plan **after** patch 1:
  - `grep '"version"' plugins/requirements-framework/.claude-plugin/plugin.json` → `4.24.2`
  - `python3 hooks/test_requirements.py 2>&1 | tail -1` → `1529/1529` (unchanged; confirms no regression)
  - agent/command/skill counts + ADR range print today's real numbers
- Run this block once patch 2 is applied so the recorded evidence reflects the final stack state.

### Notes
- All four file groups are plugin files, so the version bump legitimately belongs in patch 1 (the plugin-bump rule is satisfied without a third patch).
- Do NOT split the render (`SKILL.md`) from the source (`SKILL.md.j2`): a patch containing only one of them fails render-freshness and is not independently valid.
- The deletion must be in patch 1, not later: the rewritten template drops the `component-inventory.md` link, so any intermediate commit that keeps the file leaves an orphan (harmless) OR a commit that keeps the link with the file deleted leaves a broken link (not valid). Bundling avoids both.
- `req satisfy` for the branch gates (`pre_commit_review`, `pre_pr_review`, etc.) is a separate workflow step, not a commit; not modeled here.

---

## Verdict

APPROVED
Reviewed: docs/status-skill-live-derive @ 2026-07-06T08:13:42Z

**Team**: adr-guardian (COMPLIANT), code-reviewer (approve w/ fixes), commit-planner (2-patch strategy). codex-arch-reviewer skipped (CLI unavailable). tdd-validator / solid-reviewer folded into synthesis — a documentation/skill change with no runtime code path or class design has no SOLID surface and no unit-test target (verification is the derivation block, Task 5).

**Fixes folded into the plan before landing**:
- IMPORTANT-1: hook-listing regex excludes vendored `hooks/_langfuse_hook.py` (`/_` added) so the count is honest (17, not 18).
- IMPORTANT-2: full test suite moved OUT of the default block → opt-in health check (~28s side effect is inappropriate for a status readout).
- Minor: sturdier `grep -E 'Results:|passed' | tail -1`; note the `req status` out-of-session warning and the repo-root path assumption in the skill body.

**Cross-validation**: No CRITICAL escalations. ADR-compliant (ADR-006/007/011/013/014/015 all checked clean); no breaking change (internal skill reference file, not a public artifact per ADR-015); deleting `component-inventory.md` sheds only stale/duplicated/derivable content.
