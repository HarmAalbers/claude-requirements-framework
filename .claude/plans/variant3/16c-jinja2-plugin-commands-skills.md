# Step 16c — Jinja2 plugin commands + skills (32 files, build-time render)

> **For Claude:** REQUIRED SUB-SKILL: Use requirements-framework:executing-plans to implement this plan task-by-task.

**Goal:** Establish `.md.j2` as source-of-truth for all 32 dispatched prompt files in the plugin (11 commands + 21 SKILL.md), with rendered `.md` output byte-identical to the pre-conversion files. Same engine, same acceptance gate as Step 16b.

**Architecture:** Build-time Jinja2 rendering via the existing `scripts/render_prompts.py` (StrictUndefined, FileSystemLoader). The renderer already walks `plugins/requirements-framework/` recursively, so commands and skills are picked up with zero infrastructure changes. The pre-commit hook and `update-plugin-versions.sh` integration from Step 16b remain in force.

Note on `keep_trailing_newline`: the Jinja2 Environment sets this flag, but it is effectively *inert* in our code path because `render_prompts.py` calls `render(src.read_text())` — passing template source as a string, not loading via `FileSystemLoader`. Python's `str.read_text()` already preserves trailing newlines on POSIX, and Jinja2's string-based render does not strip them. Trailing-newline fidelity for Step 16c is therefore guaranteed by Python's text-mode I/O semantics, not by the Jinja2 flag (tdd-validator finding, 2026-05-24).

**Tech Stack:** Jinja2 (already a dep), stg for atomic patches, `md5sum` for the acceptance gate, `python3 scripts/render_prompts.py --check` for fresh-state verification.

---

## Why now

Step 16b converted the 25 plugin agents — the highest-leverage target because of the 13-agent `diff_scope_load` partial. Commands and skills are the remaining prompt-bearing files in the plugin. Converting them now:

- Completes the "every dispatched plugin prompt has a `.md.j2` source" invariant.
- Lets future per-file extraction work (e.g., a shared "workflow-position" header for commands) drop in without an inter-format migration.
- Closes the asymmetry where agents have a build pipeline but adjacent files do not. Asymmetry creates drift.

**Empirical finding driving the scope:** `grep -E '\{\{|\{%'` across all 11 commands and 21 SKILL.md files returns zero matches. There are no Jinja2 syntax collisions. Unlike Step 16b's frontend-reviewer JSX surprise, this is a genuine verbatim-copy job for every file.

## Scope decisions (locked 2026-05-24)

| Decision | Choice | Reason |
|---|---|---|
| In scope | 11 commands + 21 `SKILL.md` = 32 files | Every prompt that Claude Code dispatches under `plugins/requirements-framework/` |
| Out of scope | 3 refactor-orchestration template files (`orchestrator-prompt-template.md`, `plan-template.md`, `retrospective-template.md`) | Not dispatched — these are skill-internal scaffolding read via `Read` and customised per-refactor. Their `<placeholder>` syntax is meant for human filling, not Jinja rendering. Converting would add file-pair maintenance for zero benefit. |
| Out of scope | New partials | Empirical: zero byte-identical kernels across commands/skills. Step 16b's discoverability rule applies — extract only when the kernel is byte-identical across multiple files. No qualifying kernels found. |
| Out of scope | `render_prompts.py` changes | The default path `plugins/requirements-framework/` already covers commands/skills recursively (verified). |
| In scope (added during arch-review) | One new invariant test: `test_all_plugin_md_files_have_j2_source` | Cross-validated by tdd-validator + adr-guardian. Turns the "every dispatched `.md` has a `.md.j2` source" rule from a manual shell check into a permanent regression guard. Authored in Patch 31. |
| Out of scope | Any other new tests | `test_plugin_templates_have_no_runtime_vars` already walks the whole plugin tree and will enforce the zero-runtime-var contract on commands/skills automatically. |
| Out of scope | `update-plugin-versions.sh` changes | The `.md.j2` skip-guards and re-render hooks landed in Step 16b's Patch 3 already handle commands and skills via the parallel discovery loops. |
| Plugin version | 4.5.0 → 4.6.0 | Minor bump: source-format change, no behavioural change (byte-identical render). Matches the 4.4.0 → 4.5.0 cadence from Step 16b. |
| Acceptance gate | Byte-identical | Snapshot MD5 of original `.md` must equal MD5 of rendered output. Strictest possible behavioural-equivalence check. Same gate as Step 16b. |

## Files touched

**Created (32 new `.md.j2` source files):**

Commands (11):
- `plugins/requirements-framework/commands/arch-review.md.j2`
- `plugins/requirements-framework/commands/brainstorm.md.j2`
- `plugins/requirements-framework/commands/codex-review.md.j2`
- `plugins/requirements-framework/commands/commit-checks.md.j2`
- `plugins/requirements-framework/commands/deep-review.md.j2`
- `plugins/requirements-framework/commands/execute-plan.md.j2`
- `plugins/requirements-framework/commands/pre-commit.md.j2`
- `plugins/requirements-framework/commands/refactor-orchestrate.md.j2`
- `plugins/requirements-framework/commands/req.md.j2`
- `plugins/requirements-framework/commands/session-reflect.md.j2`
- `plugins/requirements-framework/commands/write-plan.md.j2`

Skills (21):
- `plugins/requirements-framework/skills/brainstorming/SKILL.md.j2`
- `plugins/requirements-framework/skills/dispatching-parallel-agents/SKILL.md.j2`
- `plugins/requirements-framework/skills/executing-plans/SKILL.md.j2`
- `plugins/requirements-framework/skills/finishing-a-development-branch/SKILL.md.j2`
- `plugins/requirements-framework/skills/receiving-code-review/SKILL.md.j2`
- `plugins/requirements-framework/skills/refactor-orchestration/SKILL.md.j2`
- `plugins/requirements-framework/skills/requesting-code-review/SKILL.md.j2`
- `plugins/requirements-framework/skills/requirements-framework-builder/SKILL.md.j2`
- `plugins/requirements-framework/skills/requirements-framework-development/SKILL.md.j2`
- `plugins/requirements-framework/skills/requirements-framework-status/SKILL.md.j2`
- `plugins/requirements-framework/skills/requirements-framework-usage/SKILL.md.j2`
- `plugins/requirements-framework/skills/session-learning/SKILL.md.j2`
- `plugins/requirements-framework/skills/subagent-driven-development/SKILL.md.j2`
- `plugins/requirements-framework/skills/systematic-debugging/SKILL.md.j2`
- `plugins/requirements-framework/skills/test-driven-development/SKILL.md.j2`
- `plugins/requirements-framework/skills/using-git-worktrees/SKILL.md.j2`
- `plugins/requirements-framework/skills/using-requirements-framework/SKILL.md.j2`
- `plugins/requirements-framework/skills/verification-before-completion/SKILL.md.j2`
- `plugins/requirements-framework/skills/workflow-index/SKILL.md.j2`
- `plugins/requirements-framework/skills/writing-plans/SKILL.md.j2`
- `plugins/requirements-framework/skills/writing-skills/SKILL.md.j2`

**Modified (housekeeping patch only):**
- `plugins/requirements-framework/.claude-plugin/plugin.json` — bump `version` to `"4.6.0"`
- `CHANGELOG.md` — prepend v4.6.0 entry
- `DEVELOPMENT.md` — extend "Plugin Agent Authoring" section to cover commands + skills (rename to "Plugin Prompt Authoring")
- `~/.claude/projects/.../memory/refactor-current-status.md` — mark Step 16c done
- `requirements-framework/...` marketplace mirror — produced by `./update-plugin-versions.sh`

**Untouched:**
- `plugins/requirements-framework/skills/refactor-orchestration/*-template.md` (3 files) — out of scope per the table above
- `scripts/render_prompts.py`, `update-plugin-versions.sh`, `tests/test_render_prompts.py`, `tests/test_partials.py`, `scripts/pre-commit-check.sh`, `hooks/lib/llm/prompts/partials/diff_scope_load.j2` — all Step 16b infrastructure remains as-is
- The 25 agent `.md.j2` files from Step 16b — already converted

## Patch breakdown (33 atomic patches)

| # | Patch name | What |
|---|---|---|
| 1 | `step-16c-convert-arch-review` | Convert `commands/arch-review.md` |
| 2 | `step-16c-convert-brainstorm` | Convert `commands/brainstorm.md` |
| 3 | `step-16c-convert-codex-review` | Convert `commands/codex-review.md` |
| 4 | `step-16c-convert-commit-checks` | Convert `commands/commit-checks.md` |
| 5 | `step-16c-convert-deep-review` | Convert `commands/deep-review.md` |
| 6 | `step-16c-convert-execute-plan` | Convert `commands/execute-plan.md` |
| 7 | `step-16c-convert-pre-commit` | Convert `commands/pre-commit.md` |
| 8 | `step-16c-convert-refactor-orchestrate` | Convert `commands/refactor-orchestrate.md` |
| 9 | `step-16c-convert-req` | Convert `commands/req.md` |
| 10 | `step-16c-convert-session-reflect` | Convert `commands/session-reflect.md` |
| 11 | `step-16c-convert-write-plan` | Convert `commands/write-plan.md` |
| 12 | `step-16c-convert-skill-brainstorming` | Convert `skills/brainstorming/SKILL.md` |
| 13 | `step-16c-convert-skill-dispatching-parallel-agents` | Convert `skills/dispatching-parallel-agents/SKILL.md` |
| 14 | `step-16c-convert-skill-executing-plans` | Convert `skills/executing-plans/SKILL.md` |
| 15 | `step-16c-convert-skill-finishing-a-development-branch` | Convert `skills/finishing-a-development-branch/SKILL.md` |
| 16 | `step-16c-convert-skill-receiving-code-review` | Convert `skills/receiving-code-review/SKILL.md` |
| 17 | `step-16c-convert-skill-refactor-orchestration` | Convert `skills/refactor-orchestration/SKILL.md` |
| 18 | `step-16c-convert-skill-requesting-code-review` | Convert `skills/requesting-code-review/SKILL.md` |
| 19 | `step-16c-convert-skill-requirements-framework-builder` | Convert `skills/requirements-framework-builder/SKILL.md` |
| 20 | `step-16c-convert-skill-requirements-framework-development` | Convert `skills/requirements-framework-development/SKILL.md` |
| 21 | `step-16c-convert-skill-requirements-framework-status` | Convert `skills/requirements-framework-status/SKILL.md` |
| 22 | `step-16c-convert-skill-requirements-framework-usage` | Convert `skills/requirements-framework-usage/SKILL.md` |
| 23 | `step-16c-convert-skill-session-learning` | Convert `skills/session-learning/SKILL.md` |
| 24 | `step-16c-convert-skill-subagent-driven-development` | Convert `skills/subagent-driven-development/SKILL.md` |
| 25 | `step-16c-convert-skill-systematic-debugging` | Convert `skills/systematic-debugging/SKILL.md` |
| 26 | `step-16c-convert-skill-test-driven-development` | Convert `skills/test-driven-development/SKILL.md` |
| 27 | `step-16c-convert-skill-using-git-worktrees` | Convert `skills/using-git-worktrees/SKILL.md` |
| 28 | `step-16c-convert-skill-using-requirements-framework` | Convert `skills/using-requirements-framework/SKILL.md` |
| 29 | `step-16c-convert-skill-verification-before-completion` | Convert `skills/verification-before-completion/SKILL.md` |
| 30 | `step-16c-convert-skill-workflow-index` | Convert `skills/workflow-index/SKILL.md` |
| 31 | `step-16c-convert-skill-writing-plans` | Convert `skills/writing-plans/SKILL.md` |
| 32 | `step-16c-convert-skill-writing-skills` | Convert `skills/writing-skills/SKILL.md` |
| 33 | `step-16c-housekeeping` | plugin.json 4.5.0→4.6.0, CHANGELOG v4.6.0, DEVELOPMENT.md update, marketplace sync, memory pointer |

**Rationale for one-patch-per-file granularity:** Step 16b demonstrated the value of bisect-friendly history when frontend-reviewer's JSX syntax forced an in-place fix via `stg goto`. Even though Step 16c has zero known syntax conflicts, the granular history costs nothing extra (each patch is ~30 seconds of mechanical work) and preserves the same safety property.

## Per-file migration procedure (Patches 1..32)

This is the validated 6-step recipe from Step 16b, trimmed: there are no pilot/fanout phases, no partial-include site setup, no `{% raw %}` wrapping pre-planned.

### Step 1: Snapshot

```bash
FILE_MD="plugins/requirements-framework/commands/arch-review.md"  # example
BEFORE_MD5=$(md5sum "$FILE_MD" | awk '{print $1}')
echo "Before MD5: $BEFORE_MD5"
```

### Step 2: Author the `.md.j2` source

Verbatim copy. **Do not edit content.** The `git_hash` field in YAML frontmatter is updated by `./update-plugin-versions.sh` at marketplace sync; do not hand-edit.

```bash
cp "$FILE_MD" "${FILE_MD}.j2"
```

### Step 3: Render

```bash
python3 scripts/render_prompts.py
```

The renderer writes the rendered `.md` next to the `.md.j2`. With a verbatim copy this overwrites `arch-review.md` with effectively the same bytes (modulo `keep_trailing_newline=True` semantics, which match the input file's trailing-newline state).

### Step 4: Byte-identical render check

```bash
AFTER_MD5=$(md5sum "$FILE_MD" | awk '{print $1}')
echo "After MD5: $AFTER_MD5"
[ "$BEFORE_MD5" = "$AFTER_MD5" ] && echo "✓ byte-identical" || { echo "✗ MISMATCH" && exit 1; }
```

If MISMATCH: investigate (likely a trailing-newline edge case in the source file). Step 16b found this never tripped — `keep_trailing_newline=True` handled every variant.

### Step 5: Stg-commit

```bash
stg new step-16c-convert-arch-review -m "feat(step-16c): convert commands/arch-review to .md.j2 (byte-identical render)"
git add "$FILE_MD" "${FILE_MD}.j2"
stg refresh --index
```

If `git status` shows additional changes after the `--index` refresh, those are the `update-plugin-versions.sh` `git_hash` adjustments — defer those to the housekeeping patch (Patch 33).

### Step 6: Cleanup (between patches)

```bash
python3 scripts/render_prompts.py --check  # must exit 0
stg series | tail -3                       # confirm patch landed
```

## Housekeeping patch (Patch 31)

Single atomic patch with **eight** edits. Five are the original housekeeping work; three are cross-validated arch-review findings folded in:

1. `plugins/requirements-framework/.claude-plugin/plugin.json` — `"version": "4.5.0"` → `"4.6.0"`.
2. `CHANGELOG.md` — prepend a v4.6.0 entry:
   ```markdown
   ## [4.6.0] — 2026-05-24

   ### Changed
   - Plugin commands (11) and skills (21) now authored as `.md.j2` Jinja2 sources rendered to `.md` at build time. Source format change only; rendered output is byte-identical to the previous `.md` files. Completes the Step 16b agent conversion to cover every dispatched prompt under `plugins/requirements-framework/`.

   ### Added
   - `tests/test_render_prompts.py::test_all_plugin_md_files_have_j2_source` — automated guard that turns the previously-manual "every dispatched `.md` has a `.md.j2` source" check into a permanent regression test.

   ### Fixed
   - `scripts/pre-commit-check.sh` error-path hint no longer hardcodes `agents/*.md` — covers the whole plugin tree.

   ### Notes
   - No new partials extracted: empirical scan of all 32 files found no byte-identical kernels qualifying for shared extraction under Step 16b's discoverability rule.
   - Zero Jinja2 syntax collisions detected — no files required `{% raw %}{% endraw %}` wrapping (contrast with Step 16b's frontend-reviewer JSX fix).
   - Three refactor-orchestration template files (`orchestrator-prompt-template.md`, `plan-template.md`, `retrospective-template.md`) are explicitly excluded: they are skill-internal scaffolding, not dispatched prompts.
   ```
3. `DEVELOPMENT.md` — rename "## Plugin Agent Authoring (Step 16b)" → "## Plugin Prompt Authoring (Steps 16b + 16c)". Add: "The same `.md.j2` source / rendered `.md` pattern now applies to all 25 agents, 11 commands, and 21 skills under `plugins/requirements-framework/`." Plus a one-line scope note: "Plugin `.md.j2` files cannot use `{% include 'partials/...' %}` against `hooks/lib/llm/prompts/partials/` — that loader root is scoped to runtime worker templates, not plugin build-time prompts." (codex-arch-reviewer finding)
4. `scripts/pre-commit-check.sh` line 29 — change `git add plugins/requirements-framework/agents/*.md` hint to `git add -u plugins/requirements-framework/` (cross-validated by codex-arch-reviewer + refactor-advisor). One-line edit.
5. `scripts/render_prompts.py` docstring (line 2) — replace "Step 16b" with "Steps 16b–16c" so the script's self-description matches reality. (solid-reviewer cosmetic note)
6. `tests/test_render_prompts.py` — add `test_all_plugin_md_files_have_j2_source`. This is the one test we are scoping in for Step 16c, on the strength of two independent arch-review agents (tdd-validator + adr-guardian) calling out the missing automated enforcement. Implementation:
   ```python
   def test_all_plugin_md_files_have_j2_source() -> None:
       """Every dispatched plugin .md must have a .md.j2 source.

       Excludes reference material under skills/*/references/, plugin docs
       (README.md, ATTRIBUTION.md), and the 3 documented refactor-orchestration
       templates (read at skill runtime, not dispatched).
       """
       EXCLUDED_NAMES = {
           "README.md", "ATTRIBUTION.md",
           "orchestrator-prompt-template.md", "plan-template.md",
           "retrospective-template.md",
       }
       missing = []
       # Agents and commands: flat .md scan
       for sub in ("agents", "commands"):
           for md in (PLUGIN_TREE / sub).glob("*.md"):
               if md.name in EXCLUDED_NAMES:
                   continue
               if not Path(str(md) + ".j2").exists():
                   missing.append(str(md.relative_to(PLUGIN_TREE)))
       # Skills: only SKILL.md at depth 2
       for md in PLUGIN_TREE.glob("skills/*/SKILL.md"):
           if not Path(str(md) + ".j2").exists():
               missing.append(str(md.relative_to(PLUGIN_TREE)))
       assert not missing, f"missing .md.j2 source for: {missing}"
   ```
7. `./update-plugin-versions.sh` — run after edits 1–6 to refresh `git_hash` fields and sync the marketplace mirror. Add the resulting changes to the same patch.
8. Update `~/.claude/projects/-Users-harm-Tools-claude-requirements-framework/memory/refactor-current-status.md`: mark Step 16c done; update "Last updated" to 2026-05-24. (Memory file is outside the repo and not committed; this is a manual edit performed alongside the housekeeping patch but does not appear in the patch diff.)

## Preparatory Refactoring

Two small prep items. Neither changes behaviour; both prevent confusion during execution. Handle as Patch 0 or fold PREP-2 into the housekeeping patch.

### PREP-1 — Fix the acceptance gate command (medium: produces 27 false positives without this)

The acceptance criterion #1 command scans all `*.md` files recursively and checks for `.j2` siblings. After all 32 patches land, it still reports **27 MISSING files**: 22 `references/*.md` under various skills (reference material, not dispatched), 2 plugin docs (`README.md`, `ATTRIBUTION.md`), and 3 explicitly-excluded refactor-orchestration templates. The parenthetical in criterion #1 understates the real count by 24.

**Fix:** replace the acceptance gate command with a scoped version that only targets dispatched files:

```bash
find plugins/requirements-framework/{agents,commands} -name '*.md' -type f \
  | while read f; do [ -f "${f}.j2" ] || echo "MISSING: $f"; done
find plugins/requirements-framework/skills -maxdepth 2 -name 'SKILL.md' -type f \
  | while read f; do [ -f "${f}.j2" ] || echo "MISSING: $f"; done
```

This is a plan-text correction (criterion #1 below is already updated).

### PREP-2 — Update pre-commit hook error message (low: cosmetic, but stale since Step 16b)

`scripts/pre-commit-check.sh` line 29 still tells the user to stage `plugins/requirements-framework/agents/*.md` after a render failure. After Step 16c this path is incomplete — stale commands or skills trigger the same failure. Change the hint to `plugins/requirements-framework/**/*.md` (or drop the path entirely). Fold this one-line change into Patch 1 or the housekeeping patch.

---

## Acceptance

The step is complete when ALL of the following hold:

1. **Source-of-truth coverage**: every dispatched prompt file under `plugins/requirements-framework/{agents,commands,skills}` has a `.md.j2` sibling. Verify using scoped commands that exclude `references/`, `README.md`, `ATTRIBUTION.md`, and the 3 refactor-orchestration templates:

   ```bash
   find plugins/requirements-framework/{agents,commands} -name '*.md' -type f \
     | while read f; do [ -f "${f}.j2" ] || echo "MISSING: $f"; done
   find plugins/requirements-framework/skills -maxdepth 2 -name 'SKILL.md' -type f \
     | while read f; do [ -f "${f}.j2" ] || echo "MISSING: $f"; done
   ```

   Both commands produce no output.
2. **Byte-identical render**: `python3 scripts/render_prompts.py --check` exits 0 with all files reporting "fresh".
3. **Static contract**: `python3 -m pytest tests/test_render_prompts.py::test_plugin_templates_have_no_runtime_vars -q` passes.
4. **Full test sweep**: `python3 -m pytest tests/test_render_prompts.py tests/test_partials.py -q` exits 0. Includes the new `test_all_plugin_md_files_have_j2_source` invariant guard added in Patch 31.
5. **Pre-commit hook**: `python3 scripts/render_prompts.py --check` continues to be invoked by `scripts/pre-commit-check.sh`. The hook's error-path hint is corrected in Patch 31 to cover the whole plugin tree (was hardcoded to `agents/*.md`).
6. **Marketplace mirror**: `requirements-framework/` (marketplace directory) contains the new `.md.j2` files and updated rendered `.md` files. `./update-plugin-versions.sh --verify` shows no missing files.
7. **Plugin version**: `plugins/requirements-framework/.claude-plugin/plugin.json` reports `"version": "4.6.0"`.
8. **Working tree clean** after Patch 31; `stg series` shows 31 new patches stacked on top of Step 16b's patches.

## Rollback

Per-file rollback within Step 16c is trivial because each file is its own patch:

```bash
stg goto step-16c-convert-<name>
stg delete <patch>
stg push -a
```

Whole-step rollback:

```bash
# Pop all 31 patches off the stack
stg pop -a $(stg series | grep step-16c | awk '{print $2}')
```

The Step 16b infrastructure (`render_prompts.py`, the partial, the tests, the pre-commit hook, the `update-plugin-versions.sh` integration) is untouched by Step 16c, so a rollback leaves the agent layer intact and functional.

## Effort

- Per-file conversion: ~2 minutes (snapshot + cp + render + diff + stg commands).
- 30 patches × 2 min = ~60 minutes for the file patches (shim-batching saves ~4 min vs. 33-patch version).
- Housekeeping patch (Patch 31): ~25 minutes — changelog, version bump, docstring update, pre-commit hook fix, DEVELOPMENT.md update, new test, marketplace sync, memory pointer.
- Pre-PR review (deep-review + codex-review + verification-before-completion): ~30 minutes.
- **Total: ~2 hours active work.**

## Depends on

- Step 16b (commit `step-16b-housekeeping` and predecessors): provides the Jinja2 engine, render script, tests, pre-commit hook, `update-plugin-versions.sh` skip-guards, and the validated byte-identical procedure. Step 16c reuses all of these unchanged.

## Honest scope notes

- **No new partial extractions** even where they look tempting. Examples checked and rejected:
  - The `> **Workflow position**: invoked by /req X. Run directly to override the conductor.` line appears on 6 commands but the slot (`X`) varies per file → not a byte-identical kernel.
  - The `## Deterministic Execution Workflow` H2 header appears on 3 commands but the prose immediately after differs per command → not a kernel.
  - Skills universally start with `# <Skill Name>` then `## Overview` then prose, but the prose is unique per skill → no kernel.
  - Step 16b's empirical rule: don't reach for partials until duplication is byte-identical across a meaningful population. Step 16c finds none.

- **The 3 refactor-orchestration template files stay as `.md`.** They are not loaded by Claude Code at dispatch; the refactor-orchestration skill reads them at runtime. They contain prose-level placeholders meant for humans to fill (`<Layer>`, `<branch>`, `YYYY-MM-DD`). Converting them to `.md.j2` would add a render step that produces an identical output (no Jinja syntax in them) at the cost of doubled file maintenance. We can revisit this if the templates ever grow shared kernels with other prompts — but that's not the case today.

- **Plugin version semantics.** Source-format-only changes get a minor bump (Step 16b: 4.4.0 → 4.5.0; Step 16c: 4.5.0 → 4.6.0). This signals to plugin consumers that the user-visible behaviour is unchanged but the source distribution layout grew new files.

- **The plan is intentionally short.** Step 16b's plan was 914 lines because it had to design the engine, design 5 partials (4 of which were rejected empirically), validate a pilot, then fan out. Step 16c is "do the proven thing for the next 32 files." The brevity is a feature.

## Testing strategy

**One new test added in Patch 31** (Housekeeping). Existing tests carry the rest of the safety net:

- **NEW** `tests/test_render_prompts.py::test_all_plugin_md_files_have_j2_source` — asserts every dispatched `.md` under `agents/`, `commands/`, and `skills/*/SKILL.md` has a `.md.j2` sibling. Permanent regression guard for the "every dispatched plugin prompt has a `.md.j2` source" invariant. Added on the strength of cross-validated arch-review findings (tdd-validator + adr-guardian both independently flagged the missing automated enforcement).
- `tests/test_render_prompts.py::test_plugin_templates_have_no_runtime_vars` — walks the whole plugin tree, asserts every `.md.j2` renders with zero caller vars. Will catch any accidental introduction of `{{ var }}` runtime syntax in a converted file.
- `tests/test_render_prompts.py::test_check_mode_*` — verifies the `--check` mode behaviour we rely on in the acceptance gate.
- `tests/test_partials.py` — unchanged; still validates `diff_scope_load.j2` and its boundary newline contract (Step 16b artifact).
- Manual byte-diff verification per file is the Step 16c "per-patch test": MD5(before) == MD5(after).

## Risk assessment

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| `{{` or `{%` in a skill that I didn't grep for | Very Low | Render fails loudly via `StrictUndefined` or `TemplateSyntaxError` | Pre-scan already showed zero matches; the `test_plugin_templates_have_no_runtime_vars` test will catch any missed case at refresh time |
| Trailing-newline edge case causing MD5 mismatch | Very Low | Caught at Step 4 of per-file procedure | Python's text-mode `read_text()` preserves trailing newlines on POSIX; Jinja2's string-render does not strip them. (Note: the Environment's `keep_trailing_newline=True` flag is inert in the string-render code path — see Architecture paragraph.) Empirically handled every Step 16b variant. |
| CRLF line endings in a source `.md` | Very Low | False MISMATCH on macOS (read_text translates CRLF→LF) | Repo's `.gitattributes` and contributors' editors enforce LF. tdd-validator confirmed no current files have CRLF. |
| `update-plugin-versions.sh` produces noisy diffs that pollute file patches | Medium | Cosmetic only — `git_hash` field churn | Defer all `update-plugin-versions.sh` output to Patch 33 (housekeeping). Use `stg refresh --index` to absorb only the staged file. |
| 33-patch stack pushes branch over `branch_size_limit` again | High | Stop hook re-blocks at session end | Already approved this session; will need re-approval on next session — accept and document. |
| Marketplace mirror desynchronisation | Low | `./update-plugin-versions.sh --verify` flags it | Verify step in acceptance criteria #6. |

## Atomic Commit Strategy (refined 2026-05-24)

### Question 1 — One-patch-per-file vs. batching small shims

**Verdict: batch the three 11-line dispatcher shims into one patch; keep all other files one-per-patch.**

The three command shims (`brainstorm.md`, `execute-plan.md`, `write-plan.md`) are 11 lines each and structurally identical: YAML frontmatter + one `> Workflow position` line + one `Invoke the … skill` line. Splitting them into three separate patches adds zero bisect value — no known syntax risk exists for Step 16c, and the only scenario where per-file granularity pays off (a StrictUndefined render failure isolated to one file, as in Step 16b's frontend-reviewer JSX incident) cannot be triggered by a verbatim copy of a file with confirmed zero `{{`/`{%` occurrences. A single patch for the trio is still atomic (one logical change: "convert the three skill-dispatcher shims"), is faster to author, and keeps the stack at 31 patches instead of 33.

**Revised patch table (31 patches):**

| # | Patch name | What |
|---|---|---|
| 1 | `step-16c-convert-arch-review` | `commands/arch-review.md` |
| 2 | `step-16c-convert-brainstorm-execute-plan-write-plan` | Three 11-line dispatcher shims (brainstorm / execute-plan / write-plan) |
| 3 | `step-16c-convert-codex-review` | `commands/codex-review.md` |
| 4 | `step-16c-convert-commit-checks` | `commands/commit-checks.md` |
| 5 | `step-16c-convert-deep-review` | `commands/deep-review.md` |
| 6 | `step-16c-convert-pre-commit` | `commands/pre-commit.md` |
| 7 | `step-16c-convert-refactor-orchestrate` | `commands/refactor-orchestrate.md` |
| 8 | `step-16c-convert-req` | `commands/req.md` |
| 9 | `step-16c-convert-session-reflect` | `commands/session-reflect.md` |
| 10–30 | `step-16c-convert-skill-<name>` | 21 SKILL.md files (one per file, unchanged) |
| 31 | `step-16c-housekeeping` | plugin.json 4.5.0→4.6.0, CHANGELOG, DEVELOPMENT.md, marketplace sync, memory pointer |

### Question 2 — Should the housekeeping patch be split?

**Verdict: keep as one patch.**

The Step 16b housekeeping patch (`step-16b-housekeeping`) bundled plugin.json, CHANGELOG, pre-commit hook, docs, and marketplace sync in one patch, and that precedent held up cleanly. For Step 16c the housekeeping content is lighter (no new pre-commit hook, no README changes beyond a one-sentence doc update). The five edits in Patch 31 are causally coupled — a version bump in `plugin.json` without the matching CHANGELOG entry, or a marketplace sync without the version bump, leaves the repo in a transient inconsistent state. Splitting them into multiple patches would require documenting which intermediate states are intentionally inconsistent, adding complexity without benefit. The one exception worth considering: `./update-plugin-versions.sh` output can be noisy (touches `git_hash` on every converted file). **Mitigation already in place**: the per-file procedure defers all `update-plugin-versions.sh` output to Patch 31 via `stg refresh --index`, so the housekeeping patch absorbs it cleanly with no spillover into file patches.

### Question 3 — Naming convention clarity

**Verdict: the convention is clear; one adjustment for the batched shims patch.**

`step-16c-convert-<name>` and `step-16c-convert-skill-<name>` follow the exact pattern from Step 16b (`step-16b-convert-<name>`), which proved readable in `stg series` output and in git log. The only addition needed is a compound name for the batched shims:

```
step-16c-convert-brainstorm-execute-plan-write-plan
```

This is longer than typical but unambiguous. An abbreviated form `step-16c-convert-dispatcher-shims` is also acceptable — it conveys the logical grouping better at the cost of less literal traceability to file names. Either works; the implementation agent should pick one and use it consistently.

### Question 4 — Per-file procedure: spillover risk

**Verdict: the procedure is sound; one clarification needed on ordering.**

The 6-step recipe (snapshot → cp → render → diff → `stg refresh --index` → `--check`) correctly uses `--index` to absorb only the staged `.md` and `.md.j2` files and defer `git_hash` churn to Patch 31. The risk identified in the risk table ("Medium" likelihood for `update-plugin-versions.sh` noisy diffs) is already mitigated by this choice.

One clarification for the implementation agent: **do not run `./update-plugin-versions.sh` between patches 1..30**. Only run it in Patch 31. Running it mid-sequence would cause `git_hash` fields on already-converted files to update, creating unstaged changes that `stg refresh --index` would silently skip — but a subsequent `git status` check (Step 6) would reveal them as untracked noise and could confuse the implementation agent about patch boundaries. The Step 6 cleanup (`python3 scripts/render_prompts.py --check` + `stg series | tail -3`) is sufficient verification between patches; `update-plugin-versions.sh` is deferred entirely to Patch 31.

**Revised effort estimate:** 31 patches × ~2 min ≈ 62 min (saves ~4 min vs. 33 patches).

## What this does NOT do

- Does not change runtime behaviour of any command or skill (byte-identical render is the strictest possible equivalence claim).
- Does not introduce per-environment or per-tenant template variables. Plugin distribution remains static.
- Does not touch the 25 agent `.md.j2` files from Step 16b.
- Does not extend `render_prompts.py`, `update-plugin-versions.sh`, or test files.
- Does not promote any skill or command to a different abstraction (no extraction of common front-matter, no shared invocation snippets).
- Does not address Step 19 (dialect-specific behaviour) or Step 20 (Sonnet pinning). Those remain queued downstream.
