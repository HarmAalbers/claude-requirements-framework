# Plugin Dev Workflow Details

Comprehensive guide to the framework's build-copy plugin architecture and the
tools that keep the runtime bundle current: `build_plugin_hooks.py`,
`render_prompts.py`, and live-reload via `--plugin-dir`.

> There is **no** `~/.claude/hooks` deployment and **no** `sync.sh`. Both are
> retired. The framework runs as a self-contained plugin whose hook bundle is a
> build-copy of `hooks/`.

## Plugin-Owned Runtime Architecture

### Source Location
**Path**: `hooks/` (under `~/Tools/claude-requirements-framework/`)

- Git version controlled
- **Source of truth** for all hook + lib code
- Where you edit and where the test suite runs
- Contains:
  - `hooks/*.py` - lifecycle hook entry points + `requirements-cli.py`
  - `hooks/lib/*.py` - core library modules
  - `hooks/test_requirements.py` - test suite

### Plugin Bundle Location
**Path**: `plugins/requirements-framework/hooks/`

- A **build-copy** of `hooks/`, produced by `scripts/build_plugin_hooks.py`
- What Claude Code actually loads at runtime
- Registration lives in `plugins/requirements-framework/hooks/hooks.json`, the
  single source of truth, wiring every lifecycle hook via `${CLAUDE_PLUGIN_ROOT}`
- **Never edit the bundle directly** — your change is overwritten on the next
  build. Edit `hooks/` and rebuild.

### Prompt Templates
**Pattern**: `**/*.md.j2` → `**/*.md`

- Agent / command / skill prompts are authored as Jinja2 templates (`.md.j2`)
- `scripts/render_prompts.py` renders them to the `.md` files the plugin ships
- **Never edit a rendered `.md`** — edit the `.md.j2` and re-render

---

## Build & Render Commands

Everything runs through **`uv`** (ADR-021) — never bare `python3`.

### Rebuild the Bundle

```bash
cd ~/Tools/claude-requirements-framework
uv run python scripts/build_plugin_hooks.py
```

Copies hook + lib source from `hooks/` into `plugins/requirements-framework/hooks/`.
Run it after editing anything under `hooks/`.

### Check for Bundle Drift

```bash
uv run python scripts/build_plugin_hooks.py --check
```

Reports missing / stale-extra / content-differs files **without writing**. Exits
non-zero on drift — ideal as a pre-commit / CI guard. Treat a non-zero exit as
"rebuild before you commit."

### Render Prompt Templates

```bash
uv run python scripts/render_prompts.py
```

Renders every `*.md.j2` to its `*.md`. Run it after editing any template.

---

## Live-Reload

Load the plugin directly from the repo so edits are picked up on the next session:

```bash
claude --plugin-dir ~/Tools/claude-requirements-framework/plugins/requirements-framework
```

Rebuild the bundle and/or re-render prompts as needed, then start a **fresh
session** to load the changes.

---

## Workflow Scenarios

### Scenario: Normal Development

Edit source, rebuild the bundle, test, commit.

```bash
cd ~/Tools/claude-requirements-framework

# 1. Edit source
$EDITOR hooks/lib/requirements.py

# 2. Rebuild the bundle
uv run python scripts/build_plugin_hooks.py

# 3. Test
uv run python hooks/test_requirements.py

# 4. Commit (Stacked Git)
stg new my-change && stg refresh
```

### Scenario: Editing a Prompt

You change a command / agent / skill prompt.

```bash
# 1. Edit the template (never the rendered .md)
$EDITOR plugins/requirements-framework/commands/some-command.md.j2

# 2. Render
uv run python scripts/render_prompts.py

# 3. Reload in a fresh --plugin-dir session
```

### Scenario: Test-Driven Development

```bash
# 1. Write a failing test
$EDITOR hooks/test_requirements.py

# 2. Rebuild + run (RED)
uv run python scripts/build_plugin_hooks.py
uv run python hooks/test_requirements.py   # fails

# 3. Implement
$EDITOR hooks/lib/requirements.py

# 4. Rebuild + run (GREEN)
uv run python scripts/build_plugin_hooks.py
uv run python hooks/test_requirements.py   # green = 1544/1551

# 5. Commit
stg new tdd-change && stg refresh
```

### Scenario: Merge / Rebase

Standard git; there is no separate deploy step to reconcile.

```bash
cd ~/Tools/claude-requirements-framework

# 1. Integrate remote work
git pull --rebase origin master

# 2. Rebuild the bundle (source may have changed)
uv run python scripts/build_plugin_hooks.py

# 3. Test
uv run python hooks/test_requirements.py
```

---

## Bundle Contents

### Hook Files (copied `hooks/*.py`)

| File | Purpose |
|------|---------|
| `check-requirements.py` | PreToolUse hook entry point |
| `handle-session-start.py` | SessionStart hook |
| `handle-prompt-submit.py` | UserPromptSubmit hook |
| `handle-stop.py` | Stop hook |
| `handle-session-end.py` | SessionEnd hook |
| `handle-plan-enter.py` | PostToolUse for EnterPlanMode |
| `handle-plan-exit.py` | PostToolUse for ExitPlanMode |
| `auto-satisfy-skills.py` | PostToolUse for skills |
| `clear-single-use.py` | PostToolUse for Bash |
| `requirements-cli.py` | `req` CLI (bundled) |
| `test_requirements.py` | Test suite |

### Library Files (copied `hooks/lib/*.py`)

All `*.py` files in `hooks/lib/` are copied into the bundle:

| Module | Purpose |
|--------|---------|
| `requirements.py` | Core API |
| `config.py` | Configuration loader + workflow defaults |
| `state_storage.py` | State persistence |
| `session.py` | Session tracking |
| `registry_client.py` | Registry management |
| `*_strategy.py` | Requirement strategies |
| `branch_size_calculator.py` | Dynamic calculations |
| `calculation_cache.py` | Result caching |
| `message_dedup_cache.py` | Message deduplication |
| `git_utils.py` | Git operations |
| `colors.py` | Terminal colors |
| `logger.py` | Structured logging |
| `init_presets.py` | Init wizard presets |
| `interactive.py` | UI components |
| `feature_selector.py` | Feature selection |

---

## Pre-Commit Checklist

**Run before committing**:

```bash
cd ~/Tools/claude-requirements-framework

# 1. Confirm the bundle is not stale relative to hooks/
uv run python scripts/build_plugin_hooks.py --check
#    (non-zero exit → run `build_plugin_hooks.py` to rebuild)

# 2. Re-render prompts if you touched any *.md.j2
uv run python scripts/render_prompts.py

# 3. Run tests
uv run python hooks/test_requirements.py

# 4. Lint like CI (pinned ruff)
uv run ruff check .

# 5. Commit with Stacked Git — bump plugin.json in the same patch
#    when plugin files changed
stg new my-change && stg refresh
```

---

## Troubleshooting the Build

### Changes Not Taking Effect

```bash
# 1. Did you rebuild the bundle after editing hooks/?
uv run python scripts/build_plugin_hooks.py --check   # reports drift
uv run python scripts/build_plugin_hooks.py           # rebuild

# 2. For prompt changes, did you re-render?
uv run python scripts/render_prompts.py

# 3. Start a fresh --plugin-dir session to reload
```

### build_plugin_hooks.py --check Reports Drift You Didn't Expect

```bash
# The bundle is stale or has an extra file not in hooks/. Rebuild to reconcile:
uv run python scripts/build_plugin_hooks.py

# Then re-check
uv run python scripts/build_plugin_hooks.py --check
```

### uv Not Found / Wrong Interpreter

```bash
# All Python must run via uv (ADR-021). Materialize the env once:
uv sync

# Then prefix every command with `uv run`:
uv run python hooks/test_requirements.py
```
