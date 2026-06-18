# Retire `code-simplifier` Agent — Plan

> **For Claude:** REQUIRED SUB-SKILL: executing-plans / subagent-driven-development. One stg patch per group.

**Goal:** Cleanly remove the already-DEPRECATED `code-simplifier` agent (no shims), including the two commands that still actively spawn it.

**Branch:** `chore/retire-code-simplifier` (from master `140053de`, plugin 4.22.0). Independent of the lazy-dev ladder branch.

**Why now:** decided during the lazy-dev brainstorm. `code-simplifier` is marked DEPRECATED; the built-in `/simplify` + `code-reviewer` cover its intent.

**Critical coupling (from recon):** `/deep-review` and `/pre-commit` ACTIVELY spawn `requirements-framework:code-simplifier`. Deleting the agent without editing these breaks both commands at runtime. Edit the `.md.j2` source then re-render to `.md` (`uv run --with jinja2 python3 scripts/render_prompts.py`).

**Tech:** `stg`; `uv run --with jinja2 python3 scripts/render_prompts.py` (skills/commands/agents render); `python3 scripts/build_plugin_hooks.py` (hook bundle); `python3.11 hooks/test_requirements.py`; `python3.11 tests/test_review_roster.py`.

**Version note:** bump plugin.json 4.22.0 → 4.23.0 here. The lazy-dev branch ALSO uses 4.23.0; whichever merges second must re-bump (reconcile at merge — flagged, not solved here).

---

## Group R1 — delete agent + manifest + REVIEW_AGENTS (patch `retire-cs-agent`)
- Delete `plugins/requirements-framework/agents/code-simplifier.md` AND `code-simplifier.md.j2` (delete both — the `.j2` is source, else a re-render regenerates the `.md`).
- `plugins/requirements-framework/.claude-plugin/plugin.json`: remove the `"./agents/code-simplifier.md",` array entry (keep JSON valid — no trailing-comma break). The agents array goes 25 → 24.
- `hooks/handle-subagent-start.py` line ~45: remove `'requirements-framework:code-simplifier',` from `REVIEW_AGENTS`.
- (Bundle copy `plugins/requirements-framework/hooks/handle-subagent-start.py` is regenerated in R4, not hand-edited.)
**Verify:** `python3 -c "import json; d=json.load(open('plugins/requirements-framework/.claude-plugin/plugin.json')); assert not any('code-simplifier' in a for a in d['agents']); print(len(d['agents']),'agents')"` → 24.

## Group R2 — fix the spawning commands (patch `retire-cs-commands`)
Edit `.md.j2` source then re-render (`uv run --with jinja2 python3 scripts/render_prompts.py`), commit BOTH `.j2` and `.md`.
- `commands/deep-review.md.j2`: remove the code-simplifier task assignment (~line 92), the teammate spawn block (~128) and renumber the 8–12 list, the two cross-validation rule rows (~167–168), and the report-template Team line (~232). Ensure the remaining team roster/numbering is coherent.
- `commands/pre-commit.md.j2`: remove the `simplify` aspect doc (~35), the `RUN_CODE_SIMPLIFIER` var + its all-aspect trigger logic (~88–89), the whole Step-9 spawn block (~206–212), the two agent-selection-logic lines (~265–266), the output-format line (~300), the `all` example clause (~335), the usage note (~359). After edits, NO remaining text should imply a "simplify" aspect or spawn.
**Verify:** `grep -rn code-simplifier plugins/requirements-framework/commands/` → nothing; both commands still read coherently (manual scan).

## Group R3 — doc hygiene (patch `retire-cs-docs`)
Stale references that don't break runtime but should be cleaned (edit `.md.j2` + re-render where a `.j2` exists):
- `plugins/requirements-framework/README.md`: remove the "7. Code Simplifier" entry + renumber following; fix the file-tree line and the agent table row.
- `README.md` (top): remove the `code-simplifier` list mention.
- `skills/requirements-framework-status/SKILL.md.j2` (+ `.md`): remove from the Review-agents list (re-render).
- `skills/requirements-framework-status/references/component-inventory.md`: remove the table row + fix the "Agents (19 total)" header → 18.
- `skills/receiving-code-review/SKILL.md.j2` (+ `.md`): remove the illustrative mention (re-render).
- `CLAUDE.md`: remove `code-simplifier` from the test-agents list.
- Optional: stale comments in `hooks/lib/llm/workers/rosters.py` and `tests/test_review_roster.py` (no runtime effect).
**Do NOT touch:** `CHANGELOG.md`, `docs/adr/*`, `docs/plans/*`, `.claude/plans/*` (history), `egg-info/PKG-INFO` (generated).

## Group R4 — bundle + version + verify (patch `retire-cs-bundle-version` + chore)
- Bump `plugins/requirements-framework/.claude-plugin/plugin.json` 4.22.0 → 4.23.0.
- `python3 scripts/build_plugin_hooks.py` (regenerates the bundle, incl. the REVIEW_AGENTS edit in the bundled `handle-subagent-start.py`).
- Bump `.claude-plugin/marketplace.json` 4.21.0 → 4.23.0 (manual; skip `update-plugin-versions.sh` — it can't re-render without global jinja2 and churns 64 files).
**Final verification (all must pass):**
- `python3.11 hooks/test_requirements.py` → `Results: N/N` (0 fail).
- `uv run --with jinja2 python3 scripts/render_prompts.py --check` → exit 0.
- `python3.11 scripts/build_plugin_hooks.py --check` → in sync.
- `python3.11 tests/test_review_roster.py` → green (roster already excludes code-simplifier).
- `grep -rn code-simplifier . --exclude-dir=.git` → ONLY history (CHANGELOG/adr/plans/egg-info).

## Execution
Subagent-driven, one stg patch per group, spec+quality review (esp. R2 — the command surgery must keep `/deep-review` and `/pre-commit` coherent). Gates on this branch must be satisfied before source edits (handle via `req satisfy` when first blocked).
