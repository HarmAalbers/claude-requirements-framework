# Lazy-Dev Ladder — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: requirements-framework:executing-plans (or subagent-driven-development) — task-by-task, one stg patch per task.

**Goal:** Bias code/plan generation toward the least code that works, by injecting a compact "lazy ladder" ruleset at three hook seams + embedding it in the planning skills. On by default, single disable key, fail-open. Plus: retire the deprecated `code-simplifier` agent.

**Architecture:** One canonical ruleset file (`hooks/lib/lazy_dev/RULESET.md`) is (a) read at runtime by `handle-session-start.py`, `handle-prompt-submit.py`, `handle-subagent-start.py`, and (b) `{% include %}`-d into `writing-plans` + `brainstorming` skill templates via the existing Jinja renderer. No copy-drift: the hooks read the file; the skills include the same file (loader searchpath extended).

**Tech stack:** Python stdlib + PyYAML; Jinja2 (`[llm]` extra) for skill rendering via `uv run --with jinja2`; custom `TestRunner` in `hooks/test_requirements.py`; `stg` patches; `./sync.sh deploy`; `scripts/build_plugin_hooks.py` (bundle); `scripts/render_prompts.py` (`.md.j2 → .md`).

**Design doc:** `.claude/plans/2026-06-18-lazy-dev-debt-ledger-design.md`

## Decisions (settled)
- Ladder ruleset (not the debt ledger — deferred). All three placements. **On by default**, single key `hooks.lazy_dev.enabled`. Embed literally in planning skills via include. Retire `code-simplifier`.

## Single-source strategy
- Canonical: `hooks/lib/lazy_dev/RULESET.md` (pure markdown, variable-free).
- Runtime: `hooks/lib/lazy_dev/rules.py` reads it via `Path(__file__).parent / "RULESET.md"`, fail-open to empty.
- Skills: extend the Jinja `FileSystemLoader` searchpath (`hooks/lib/llm/templates.py`) to also include `hooks/lib/lazy_dev/`, so `writing-plans`/`brainstorming` `SKILL.md.j2` can `{% include 'RULESET.md' %}` the **same** file → no drift, no extra drift-test. (Fallback if loader change is rejected in review: a separate `partials/lazy_ladder.j2` + a 3-line equality test.)

## The canonical ruleset (create verbatim at `hooks/lib/lazy_dev/RULESET.md`)
```markdown
# Lazy-Dev Ladder

You are a lazy senior developer — lazy means efficient, not careless. The best code is the code never written.

Before writing code, stop at the first rung that holds:
1. Does this need to exist at all? Speculative need → skip it, say so in one line. (YAGNI)
2. Does the standard library already do this? Use it.
3. Does a native platform feature cover it? Use it (`<input type="date">` over a picker lib, a DB constraint over app code, CSS over JS).
4. Does an already-installed dependency solve it? Use it — never add a new dependency for what a few lines can do.
5. Can it be one line? Make it one line.
6. Only then: write the minimum code that works.

Never lazy about: input validation at trust boundaries, error handling that prevents data loss, security, accessibility, and anything explicitly requested. Between two same-size options, pick the edge-case-correct one — lazy means less code, not the flimsier algorithm.

Output: code first, then at most a couple of lines naming what you skipped and when to add it. Don't defend simplifications with prose.

<!-- Adapted from ponytail (https://github.com/DietrichGebert/ponytail), MIT-licensed. -->
```
Compact one-line reminder (used by prompt-submit), define as a constant in `rules.py`:
`Lazy-dev: prefer the least code that works — stdlib/native/installed-dep/one-line before custom; never skimp on validation, security, error handling, or accessibility.`

---

## GROUP A — Foundation (one patch: `lazy-dev-foundation`)

### Task A1: ruleset file + reader
**Files:** Create `hooks/lib/lazy_dev/__init__.py` (empty), `hooks/lib/lazy_dev/RULESET.md` (above), `hooks/lib/lazy_dev/rules.py`. Test: `hooks/test_requirements.py`.
**rules.py:**
```python
from pathlib import Path

_RULESET = Path(__file__).parent / "RULESET.md"
COMPACT_REMINDER = ("Lazy-dev: prefer the least code that works — stdlib/native/"
                    "installed-dep/one-line before custom; never skimp on validation, "
                    "security, error handling, or accessibility.")

def get_ruleset() -> str:
    """Full lazy-dev ladder text. Fail-open to '' if the file is missing."""
    try:
        return _RULESET.read_text(encoding="utf-8")
    except Exception:
        return ""
```
**Steps (TDD):**
1. Write test `test_lazy_dev_ruleset`: import `lazy_dev.rules`, assert `get_ruleset()` contains "stop at the first rung" and "Never lazy about"; assert `COMPACT_REMINDER` mentions "least code". Register in `main()`.
2. Run (`python3.11 hooks/test_requirements.py`) → RED (module missing).
3. Create the three files.
4. Run → GREEN.

### Task A2: config flag default
**Files:** `hooks/lib/config.py` (`HOOK_DEFAULTS` ~line 873). Test: `hooks/test_requirements.py`.
1. Test `test_lazy_dev_flag_default`: `RequirementsConfig(tmp).get_hook_config('lazy_dev','enabled')` is `True` by default; with `hooks: {lazy_dev: {enabled: false}}` → `False`. Register.
2. RED.
3. Add to `HOOK_DEFAULTS`: `"lazy_dev": {"enabled": True},`.
4. GREEN.

### Task A3: sync.sh deploys `.md` under lib
**Files:** `sync.sh` (two `find`/glob filters: `get_py_files_recursive` ~line 66, `deploy_to_hooks` ~line 355). Add `-o -name "*.md"` to both so `hooks/lib/lazy_dev/RULESET.md` deploys to `~/.claude/hooks`.
1. Edit both globs.
2. Verify: `./sync.sh deploy` then confirm `~/.claude/hooks/lib/lazy_dev/RULESET.md` exists.

**Commit A:** `stg new -m "feat(lazy-dev): canonical ruleset + reader + config flag (default on) + sync .md" lazy-dev-foundation` → `git add` the new files + config.py + sync.sh + test file → `stg refresh --index`.

---

## GROUP B — Hook injections (three patches)

All three read the flag once: `if not config.get_hook_config('lazy_dev','enabled'): skip`. Each new block in its own `try/except` (fail-open). Import `from lazy_dev.rules import get_ruleset, COMPACT_REMINDER` (lib is on `sys.path`).

### Task B1: SessionStart full-ruleset injection (`session-start-ladder`)
**File:** `hooks/handle-session-start.py`. Append the full ruleset to the `parts` list inside `if inject_context:` (after the status append, before the single `emit_hook_context("SessionStart", "\n\n".join(parts))`).
- Gate on `config.get_hook_config('lazy_dev','enabled')`.
- Fires once/session (no dedup needed).
**TDD:** test that `parts` includes the ruleset when enabled and omits it when disabled — extract a tiny helper `_ladder_block(config)` returning the text or `""` and unit-test that (mirrors how `_status_or_fallback` was made testable). Register, RED, implement, GREEN, full suite.

### Task B2: prompt-submit compact reminder (`prompt-submit-ladder`)
**Files:** `hooks/handle-prompt-submit.py`, new `hooks/lib/ruleset_marker.py` (dedup helper modeled on `hooks/lib/brainstorm.py`).
- `ruleset_marker.py`: `shown(session_id, project_dir)` / `mark_shown(...)` using `get_state_dir(project_dir)/f'.lazy-ladder-{_safe_session_token(session_id)}'`, both fail-open. (Reuse `_safe_session_token` from brainstorm or duplicate the tiny sanitizer.)
- In `handle-prompt-submit.py` `main()`: after `reqs = BranchRequirements(...)`, before the brainstorm block — if `lazy_dev.enabled` and `_prompt_is_substantive(prompt)` and not `shown(...)`: `emit_hook_context('UserPromptSubmit', COMPACT_REMINDER)`, `mark_shown(...)`. Do **not** early-return (let brainstorm nudge + status injection still run).
**TDD:** test the marker helper (shown→False first, mark, then True; fail-open). Register, RED, implement, GREEN, full suite.

### Task B3: SubagentStart ladder for code-touching agents (`subagent-ladder`)
**File:** `hooks/handle-subagent-start.py`. Add `CODE_TOUCHING_AGENTS = {'requirements-framework:refactor-executor', ...}` alongside `REVIEW_AGENTS`; broaden the early-return gate to allow either set; for code-touching agents (when `lazy_dev.enabled`) build a ladder block and emit via the existing single `emit_hook_context('SubagentStart', ...)`.
**TDD:** test that a code-touching `agent_type` yields the ladder text and a non-listed type yields nothing. Register, RED, implement, GREEN, full suite.

---

## GROUP C — Planning-skill include (one patch: `planning-skill-ladder`)

**Files:** `hooks/lib/llm/templates.py` (loader searchpath), `plugins/requirements-framework/skills/writing-plans/SKILL.md.j2` + `SKILL.md`, `plugins/requirements-framework/skills/brainstorming/SKILL.md.j2` + `SKILL.md`.
1. In `templates.py`, change `FileSystemLoader(_PROMPTS_ROOT)` → `FileSystemLoader([_PROMPTS_ROOT, Path(__file__).parent.parent / 'lazy_dev'])` (so `{% include 'RULESET.md' %}` resolves to the canonical file).
2. Add `{% include 'RULESET.md' %}` at the appropriate spot in both `SKILL.md.j2` files (own line; mind `keep_trailing_newline`).
3. Re-render: `uv run --with jinja2 python3 scripts/render_prompts.py` (regenerates both `SKILL.md`). Commit `.md.j2` AND rendered `.md`.
4. Verify: `uv run --with jinja2 python3 scripts/render_prompts.py --check` exits 0 (freshness); `python3 tests/test_render_prompts.py` green (include-target-exists + zero-var contract).
**Note:** no new drift test — `render --check` + `test_missing_include_reports_render_failure` + `test_all_plugin_md_files_have_j2_source` already guard this.

---

## GROUP D — Retire `code-simplifier` (separate concern — see structural note)

> **Live runtime coupling**: `/deep-review` and `/pre-commit` actively spawn `code-simplifier`. Deleting the agent without editing these breaks both commands. Edit `.md.j2` source then re-render (or edit both `.md.j2` and `.md`).

### Task D1 (`retire-code-simplifier-agent`): delete agent + manifest
- Delete `plugins/requirements-framework/agents/code-simplifier.md` and `code-simplifier.md.j2`.
- `plugin.json`: remove the `'./agents/code-simplifier.md',` array entry (keep JSON valid).
- `hooks/handle-subagent-start.py` + `plugins/requirements-framework/hooks/handle-subagent-start.py`: remove `'requirements-framework:code-simplifier',` from `REVIEW_AGENTS` (line ~45, both copies).

### Task D2 (`retire-code-simplifier-commands`): fix the spawning commands
- `commands/deep-review.md.j2` (+ rendered `.md`): drop the code-simplifier task (~92), teammate spawn (~128) and renumber, the two cross-validation rows (~167-168), and the report-Team line (~232).
- `commands/pre-commit.md.j2` (+ rendered `.md`): drop the `simplify` aspect (~35), `RUN_CODE_SIMPLIFIER` var + all-triggers logic (~88-89), the Step-9 spawn block (~206-212), agent-selection lines (~265-266), output-format line (~300), the `all` example clause (~335), usage note (~359). Ensure no remaining text implies a simplify aspect.
- Re-render commands; commit `.j2` + `.md`.

### Task D3 (`retire-code-simplifier-docs`): doc hygiene
- `plugins/.../README.md` (entry 7 + renumber, tree line, agent table), top `README.md`, `requirements-framework-status` `SKILL.md.j2`+`.md` (list + re-render), `component-inventory.md` (row + "Agents (19 total)"→18), `receiving-code-review` `SKILL.md.j2`+`.md`, `CLAUDE.md` test-agents list. Optional: stale comments in `rosters.py`, `tests/test_review_roster.py`.
- **Do NOT touch** `CHANGELOG.md`, `docs/adr/*`, `docs/plans/*`, `.claude/plans/*`, `egg-info/PKG-INFO` (history/generated).
**Verify D:** `grep -rn code-simplifier . --exclude-dir=.git` shows only history/changelog; a JSON assert that no plugin agent contains `code-simplifier` (24 agents remain); `python3 tests/test_review_roster.py` green.

---

## GROUP E — Build, version, verify (one patch + one chore patch)

### Task E1 (`lazy-dev-bundle-version`): bundle + version
- Bump `plugins/requirements-framework/.claude-plugin/plugin.json` `4.22.0 → 4.23.0` (minor).
- `python3 scripts/build_plugin_hooks.py` (rebuild hook bundle — includes the 3 edited hooks + bundled `RULESET.md`).
- Confirm `diff` of each edited hook vs its bundle copy is identical.
**Commit:** include the bundle changes + plugin.json bump.

### Task E2 (`chore-plugin-hashes`): hashes/marketplace
- `./update-plugin-versions.sh` (syncs `marketplace.json` version + git_hash frontmatter). Commit churn in its own chore patch.

### Task E3: final verification (no code)
- `python3.11 hooks/test_requirements.py` → `Results: N/N` (0 fail).
- `uv run --with jinja2 python3 scripts/render_prompts.py --check` → exit 0.
- `python3 scripts/build_plugin_hooks.py --check` → no `.py` drift.
- `./sync.sh deploy && ./sync.sh status` → in sync (incl. `RULESET.md`).
- `grep -rn code-simplifier . --exclude-dir=.git` → history only.

---

## Structural note (confirm before executing)
Groups A–C + E are the **ladder feature**. Group D (**retire code-simplifier**, 19 files, live command coupling) is independent. Options: (1) keep both on this branch as separate patch-groups (one PR); (2) split D to its own branch/PR (matches the narrow-PR habit). Recommend confirming with the user.

## Execution
Subagent-driven, one stg patch per task, spec+quality review per group. Gates on this branch (`design_approved`, `plan_written`, `commit_plan`, etc.) must be satisfied before source edits — handle via `req satisfy` on `feat/lazy-dev-debt-ledger` when first blocked.
