---
name: requirements-framework-development
description: This skill should be used when the user asks to "develop requirements framework", "fix requirements framework bug", "rebuild the plugin bundle", "update framework code", "test framework changes", or needs help with the framework development workflow including the hooks/ → bundle build, live-reload testing, TDD for the framework itself, and contributing changes.
git_hash: 2389595
---

# Requirements Framework Development

Guide for developing, fixing, and maintaining the **Claude Code Requirements Framework**.

**Repository**: `~/Tools/claude-requirements-framework` (git-controlled source of truth)
**Runtime**: the plugin at `plugins/requirements-framework/` (loaded by Claude Code)
**Remote**: https://github.com/HarmAalbers/claude-requirements-framework.git

## Core Concept: Plugin-Owned Runtime + Build-Copy Bundle

There is **no** `~/.claude/hooks` deployment and **no** `sync.sh` — both have been removed.
The framework runs entirely as a **self-contained plugin**:

| Piece | Path | Role |
|-------|------|------|
| **Hook source** | `hooks/` | Where you edit hook + lib code (source of truth) |
| **Plugin bundle** | `plugins/requirements-framework/hooks/` | Build-copy of `hooks/`, produced by `scripts/build_plugin_hooks.py` |
| **Hook registration** | `plugins/requirements-framework/hooks/hooks.json` | Single source of truth; registers all lifecycle hooks via `${CLAUDE_PLUGIN_ROOT}` |
| **Prompt templates** | `**/*.md.j2` | Rendered to `.md` by `scripts/render_prompts.py` |

Because the bundle is a **build-copy**, editing `hooks/` is not enough — you must
rebuild the bundle so the plugin runtime picks up your change.

**→ Full dev workflow details**: See `references/sync-workflow-details.md`

## uv Is Required (ADR-021)

Every Python entrypoint runs through **`uv`** — never bare `python3` (the only
exception is `statusline.sh`). Run all tooling via `uv run …` so the synced env
(`PyYAML` + the `dev` group) is guaranteed.

```bash
uv sync                                    # one-time: materialize .venv
uv run python hooks/test_requirements.py   # run the test suite
uv run ruff check .                         # lint (pinned, matches CI)
```

## Build Tools — The Essential Commands

```bash
cd ~/Tools/claude-requirements-framework

# Rebuild the plugin bundle after editing anything in hooks/
uv run python scripts/build_plugin_hooks.py

# Report bundle drift without writing (use before committing / in CI)
uv run python scripts/build_plugin_hooks.py --check

# Re-render prompt templates (*.md.j2 → *.md) after editing a template
uv run python scripts/render_prompts.py
```

`build_plugin_hooks.py --check` exits non-zero when the bundle is stale relative
to `hooks/` — treat that as "rebuild before you commit."

## Live-Reload Testing

Load the plugin straight from the repo so edits are picked up on the next session:

```bash
claude --plugin-dir ~/Tools/claude-requirements-framework/plugins/requirements-framework
```

Rebuild the bundle (`build_plugin_hooks.py`) and re-render prompts
(`render_prompts.py`) as needed, then start a fresh session to load the changes.

## Development Workflows

### Workflow A: Standard Development

**Pattern**: Edit source → Rebuild bundle → Test → Commit

```bash
cd ~/Tools/claude-requirements-framework

# 1. Edit hook / lib source
$EDITOR hooks/lib/requirements.py

# 2. Rebuild the plugin bundle
uv run python scripts/build_plugin_hooks.py

# 3. Test
uv run python hooks/test_requirements.py

# 4. Commit (Stacked Git — see below)
stg new fix-requirements
stg refresh
```

### Workflow B: Editing a Prompt Template

**Pattern**: Edit `.md.j2` → Render → Live-reload

```bash
# 1. Edit the template (never the rendered .md — it is regenerated)
$EDITOR plugins/requirements-framework/commands/some-command.md.j2

# 2. Render templates
uv run python scripts/render_prompts.py

# 3. Reload in a fresh --plugin-dir session
```

### Workflow C: Test-Driven Development

**Pattern**: Test (RED) → Rebuild → Implement → Rebuild → Test (GREEN) → Commit

```bash
# 1. Write failing test
$EDITOR hooks/test_requirements.py

# 2. Rebuild + run (RED)
uv run python scripts/build_plugin_hooks.py
uv run python hooks/test_requirements.py   # fails

# 3. Implement feature
$EDITOR hooks/lib/requirements.py

# 4. Rebuild + run (GREEN)
uv run python scripts/build_plugin_hooks.py
uv run python hooks/test_requirements.py   # passes (green = 1544/1551)

# 5. Commit atomically
stg new tdd-feature
stg refresh
```

## Version Control: Stacked Git (stg)

This project authors every local commit through **Stacked Git** — **never
`git commit` directly**.

```bash
git checkout -b feat/your-branch
stg init                 # per-branch, one time (master already initialized)

stg new <patch-name>     # create a new empty patch (opens editor for description)
# ... edit files ...
stg refresh              # fold working-tree changes into the top patch
stg new <next-patch>     # start the next logical patch on top
```

`git push` works unchanged (stg patches are ordinary git commits). Keep patches
atomic — one logical change each. When a patch touches plugin files, bump
`plugins/requirements-framework/.claude-plugin/plugin.json` **inside the same
patch**.

## Testing

### Run Full Test Suite

```bash
uv run python hooks/test_requirements.py

# Expected: green = 1544/1551 (7 pre-existing failures are known/ignored)
```

### Run Specific Tests

```bash
# By name pattern
uv run python hooks/test_requirements.py -k "test_session"

# Verbose output
uv run python hooks/test_requirements.py -v
```

### Integration Testing

```bash
# 1. Enable in a project
cd ~/some-project
cat > .claude/requirements.local.yaml <<EOF
version: "1.0"
enabled: true
requirements:
  plan_validated:
    enabled: true
    scope: session
EOF

# 2. Start Claude (--plugin-dir), try editing → should block
# 3. Satisfy: req satisfy plan_validated
# 4. Try editing → should work
```

## Workflow Gates (ADR-022)

The typed 7-node backbone uses these gates:

| Gate | Node |
|------|------|
| `design_approved`      | design |
| `plan_written`         | plan |
| `plan_validated`       | validate (team) |
| `implementation_done`  | build |
| `pr_reviewed`          | review (team) |
| `verified`             | verify |
| — (gateless)           | ship |

**Retired** (do NOT reintroduce — no compat shims): `commit_plan`,
`adr_reviewed`, `tdd_planned`, `solid_reviewed`, `pre_pr_review`,
`pre_push_verification`, `codex_reviewer`. A config still naming an old gate gets
a validation error pointing at the new name.

## Common Agent Tasks

### Fix a Bug

```bash
cd ~/Tools/claude-requirements-framework

# 1. Edit source
$EDITOR hooks/lib/FILE.py

# 2. Rebuild + test
uv run python scripts/build_plugin_hooks.py
uv run python hooks/test_requirements.py

# 3. Commit
stg new fix-bug && stg refresh
```

### Add a Feature

```bash
cd ~/Tools/claude-requirements-framework

# 1. Edit source
$EDITOR hooks/lib/FILE.py

# 2. Rebuild + test
uv run python scripts/build_plugin_hooks.py && uv run python hooks/test_requirements.py

# 3. Commit
stg new add-feature && stg refresh
```

### Before Committing

```bash
cd ~/Tools/claude-requirements-framework

# Confirm the bundle is not stale relative to hooks/
uv run python scripts/build_plugin_hooks.py --check

# Lint like CI does
uv run ruff check .
```

## Troubleshooting Quick Reference

### Changes Not Taking Effect

```bash
# Did you rebuild the bundle after editing hooks/?
uv run python scripts/build_plugin_hooks.py --check   # reports drift
uv run python scripts/build_plugin_hooks.py           # rebuild

# For prompt changes, did you re-render?
uv run python scripts/render_prompts.py

# Then start a fresh --plugin-dir session to reload.
```

### Tests Fail

```bash
# Rebuild first — a stale bundle can diverge from hooks/ source
uv run python scripts/build_plugin_hooks.py

# Run with verbose
uv run python hooks/test_requirements.py -v
```

### Hook Not Triggering

```bash
# Registration lives in the plugin, not settings.json
cat plugins/requirements-framework/hooks/hooks.json

# Confirm you launched with the plugin loaded
claude --plugin-dir ~/Tools/claude-requirements-framework/plugins/requirements-framework
```

**→ Full troubleshooting**: See `references/troubleshooting-development.md`

## Best Practices

1. **Rebuild the bundle after editing `hooks/`** — `build_plugin_hooks.py`
2. **`--check` before committing** — catch a stale bundle early
3. **Test after every change** — `uv run python hooks/test_requirements.py`
4. **Everything via `uv run`** — never bare `python3` (except `statusline.sh`)
5. **Commit atomically with stg** — one logical change per patch; bump `plugin.json` in the same patch when plugin files change

## Golden Rules

1. **`hooks/` is source of truth** — always edit there, never the bundle copy
2. **The bundle is a build artifact** — regenerate it with `build_plugin_hooks.py`
3. **Prompts are `.md.j2` → `.md`** — edit the template, render with `render_prompts.py`
4. **`uv run` for all Python** — the synced env guarantees deps (ADR-021)
5. **Stacked Git for every commit** — `stg new` / `stg refresh`, never `git commit`

## Resources

- **CLAUDE.md**: `~/Tools/claude-requirements-framework/CLAUDE.md` (authoritative build/test commands)
- **DEVELOPMENT.md**: Full development guide
- **Bundle build**: `uv run python scripts/build_plugin_hooks.py [--check]`
- **Prompt render**: `uv run python scripts/render_prompts.py`
- **Tests**: `uv run python hooks/test_requirements.py`

## Reference Files

- `references/sync-workflow-details.md` - Detailed bundle-build / render / live-reload workflow and scenarios
- `references/troubleshooting-development.md` - Development troubleshooting
