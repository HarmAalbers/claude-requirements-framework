# Plugin Installation Guide

> **The plugin is self-contained.** Installing the plugin activates the entire
> runtime — hooks, agents, commands, and skills — from a single bundle. There is
> **no** separate hook deploy step (`sync.sh` / `~/.claude/hooks/` are legacy).

## Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Installation Methods](#installation-methods)
4. [Verification](#verification)
5. [Troubleshooting](#troubleshooting)
6. [How Hooks + Plugin Work Together](#how-hooks--plugin-work-together)
7. [Development Mode](#development-mode)
8. [Configuration](#configuration)
9. [Related Documentation](#related-documentation)

---

## Overview

The Requirements Framework plugin extends Claude Code with a gated development
workflow and a suite of code-review agents, commands, and skills.

**What's Included (plugin v4.31.0):**
- **24 review/workflow agents** — code-reviewer, tool-validator, silent-failure-hunter,
  test-analyzer, type-design-analyzer, comment-analyzer, backward-compatibility-checker,
  adr-guardian, solid-reviewer, tdd-validator, commit-planner, refactor-advisor,
  codex-review-agent, codex-arch-reviewer, tenant-isolation-auditor, appsec-auditor,
  compliance-auditor, frontend-reviewer, and the refactor-orchestration trio
  (refactor-executor / refactor-investigator / refactor-analyzer), among others.
- **16 commands** — including `/requirements-framework:deep-review`,
  `/requirements-framework:arch-review`, `/requirements-framework:pre-commit`,
  `/requirements-framework:codex-review`, `/requirements-framework:refactor-orchestrate`,
  and the `req`-workflow conductor commands.
- **21 skills** — status/usage/builder/development helpers plus the workflow
  skill library (brainstorming, writing-plans, executing-plans, verification,
  finishing-a-branch, etc.).
- **16 lifecycle hooks** — registered via the plugin's `hooks/hooks.json`
  (see [How Hooks + Plugin Work Together](#how-hooks--plugin-work-together)).

**Key point:** hooks are part of the plugin bundle. When the plugin loads, its
`hooks/hooks.json` registers every lifecycle hook through `${CLAUDE_PLUGIN_ROOT}`.
You do **not** copy anything into `~/.claude/hooks/`, and `install.sh` does **not**
write a `hooks` block into `~/.claude/settings.json`.

**Component Details:** See [Plugin Components](../README.md#plugin-components) and
`plugins/requirements-framework/README.md`.

---

## Prerequisites

**`uv` is required (ADR-021).** Every Python entrypoint — the `req` CLI, the
lifecycle hooks, and all build/test tooling — resolves its interpreter and
dependencies through `uv`. Nothing relies on the ambient `python3`.

```bash
# Install uv if it isn't already on PATH
curl -LsSf https://astral.sh/uv/install.sh | sh
# (see https://docs.astral.sh/uv/ for other install methods)
```

`install.sh` aborts early if `uv` is not found. At runtime the hooks and CLI
self-bootstrap under `uv` (`hooks/lib/_bootstrap.py`), so they work even when the
ambient `python3` on PATH lacks `PyYAML`.

---

## Installation Methods

### Method 1: GitHub Marketplace (Recommended for Users)

Install the plugin straight from GitHub — no local clone needed. This activates
hooks, agents, commands, and skills together.

```
# In a Claude Code session:
/plugin marketplace add HarmAalbers/claude-requirements-framework
/plugin install requirements-framework@requirements-framework
```

Enable per-marketplace auto-update so `master` pushes land at session startup
(UI toggle, or `extraKnownMarketplaces.<name>.autoUpdate: true` in
`~/.claude/settings.json`).

**To update manually:**
```
/plugin marketplace update requirements-framework
/plugin uninstall requirements-framework@requirements-framework
/plugin install requirements-framework@requirements-framework
```

> **Optional — the `req` CLI and statusline.** The plugin activates the runtime
> on its own. If you also want the `req` command on your PATH, the phase-aware
> statusline, and the `ENABLE_TOOL_SEARCH=true` shell env, clone the repo and run
> `./install.sh` (see [Method 3](#method-3-local-clone--install-sh-cli--statusline)).
> `install.sh` does **not** install hooks — the plugin does.

### Method 2: Development / Live Reload (`--plugin-dir`)

Load the plugin directly from a local clone with live reload — best for
developing agents, commands, skills, or hooks.

```bash
claude --plugin-dir ~/Tools/claude-requirements-framework/plugins/requirements-framework
```

**When to use:**
- Developing plugin components (changes are picked up on reload, no reinstall)
- Verifying plugin structure before a persistent install
- Testing multiple plugins simultaneously

**Limitations:**
- Must pass the flag every launch (not persistent)
- May not apply to UI-launched Claude Code sessions

### Method 3: Local Clone + `install.sh` (CLI + Statusline)

For contributors who have cloned the repo and want the `req` CLI, the statusline,
and shell env configured. This is **complementary** to installing the plugin — it
does not install hooks.

```bash
cd ~/Tools/claude-requirements-framework
./install.sh
```

`install.sh`:
- Verifies `uv` is on PATH (aborts if missing).
- Runs `uv sync` to materialize the project's `.venv`.
- Symlinks the `req` CLI to `~/.local/bin/req` (self-bootstraps under `uv`).
- Installs a global config to `~/.claude/requirements.yaml` (only if absent).
- Registers the phase-aware statusline in `~/.claude/settings.json` (only if you
  don't already have a custom `statusLine`).
- Offers to add `~/.local/bin` to PATH and `ENABLE_TOOL_SEARCH=true` to your
  shell rc (both idempotent).

It does **not** copy hook scripts anywhere or edit a `hooks` block in
`settings.json`. To activate hooks, install the plugin (Method 1) or launch with
`--plugin-dir` (Method 2). You can also register the local clone as a marketplace:

```
/plugin marketplace add ~/Tools/claude-requirements-framework
/plugin install requirements-framework@requirements-framework
```

---

## Verification

### Step 1: Check the Plugin Loaded

```
/plugin list
```

**Expected:** an entry like `requirements-framework@4.31.0 (requirements-framework)`.

### Step 2: Test Commands

In Claude Code, test command autocomplete:

```
Type: /requirements-framework:

Should include:
  • /requirements-framework:deep-review
  • /requirements-framework:arch-review
  • /requirements-framework:pre-commit
  • /requirements-framework:codex-review
```

Run one:
```
/requirements-framework:pre-commit
```

### Step 3: Test Skills (natural language)

- "Show requirements framework status" → `requirements-framework-status`
- "How to use requirements framework" → `requirements-framework-usage`
- "Extend requirements framework" → `requirements-framework-builder`

### Step 4: Confirm Hooks Are Active

Hooks come from the plugin bundle. The simplest confirmation is behavioral: with a
gated config in place, editing a file surfaces a requirement briefing/block at
`SessionStart` and on `Edit`/`Write`. You can also inspect the source of truth:

```bash
cat plugins/requirements-framework/hooks/hooks.json
```

All 16 lifecycle hooks are registered there via `${CLAUDE_PLUGIN_ROOT}`.

### Step 5 (optional): Run the Test Suite

Requires a local clone. Always run Python through `uv` — never bare `python3`:

```bash
cd ~/Tools/claude-requirements-framework
uv run python hooks/test_requirements.py
uv run ruff check .
```

---

## Troubleshooting

### Plugin / Commands / Skills Not Appearing

**Symptom:** Commands don't autocomplete, skills don't trigger, no requirement
briefing at session start.

**Solutions:**

1. **Plugin not installed** → install it:
   ```
   /plugin marketplace add HarmAalbers/claude-requirements-framework
   /plugin install requirements-framework@requirements-framework
   ```
2. **Stale cache / old version** → update and reinstall:
   ```
   /plugin marketplace update requirements-framework
   /plugin uninstall requirements-framework@requirements-framework
   /plugin install requirements-framework@requirements-framework
   ```
3. **Not loading at all** → restart the Claude Code session (plugins load at
   session start).

### `uv` Not Found

**Symptom:** `install.sh` aborts with "'uv' not found on PATH", or hooks/CLI fail
to run.

**Fix:** install `uv` and re-run:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### `req` Command Not Found

**Symptom:** `req: command not found` after `install.sh`.

**Fix:** ensure `~/.local/bin` is on PATH (the installer offers to add it), then
restart your shell or `source ~/.zshrc`.

### Skills Don't Trigger (but commands work)

Skills trigger on natural-language description patterns. Use exact trigger phrases:
- ✅ "Show requirements framework status"
- ❌ "Show me status" (too vague)

### Hooks Seem Inactive

Hooks are owned by the plugin's `hooks.json`, not `~/.claude/settings.json` and
not `~/.claude/hooks/`. If hooks appear inactive:
- Confirm the plugin is actually installed/loaded (`/plugin list`).
- If developing via `--plugin-dir`, confirm the flag pointed at
  `plugins/requirements-framework` and reload the session.
- There is nothing to "deploy" — `sync.sh`/`~/.claude/hooks` are legacy and no
  longer part of the runtime.

---

## How Hooks + Plugin Work Together

The plugin bundles both the enforcement layer (hooks) and the satisfaction layer
(agents/commands/skills). All 16 lifecycle hooks register from one file —
`plugins/requirements-framework/hooks/hooks.json` — using `${CLAUDE_PLUGIN_ROOT}`:

- **PreToolUse** (`check-requirements.py`) — checks gates on
  Edit/Write/MultiEdit/Bash/EnterPlanMode/ExitPlanMode/MCP; blocks until satisfied.
- **PostToolUse** (`auto-satisfy-skills.py`, `clear-single-use.py`,
  `handle-git-events.py`, `handle-plan-enter.py`, `handle-plan-exit.py`) —
  auto-satisfy gates on review completion, re-arm single-use loops, track git.
- **SessionStart / Stop / SessionEnd / PreCompact** — briefing injection,
  verification, cleanup, state saving (Stop also runs `langfuse-trace.py`).
- **UserPromptSubmit / SubagentStart / PostToolUseFailure / PermissionRequest /
  TeammateIdle / TaskCompleted** — context injection, safety, team lifecycle.

**The satisfaction flow:**

```
User tries to Edit/Write
        │
        ▼
PreToolUse (check-requirements.py) — gate unsatisfied → BLOCK with guidance
        │
        ▼
User runs a review command (e.g. /requirements-framework:deep-review)
        │
        ▼
PostToolUse (auto-satisfy-skills.py) — maps the command → satisfies its gate
        │
        ▼
Edit/Write is now unblocked
```

**Command → gate mapping** (ADR-022 gate vocabulary):

| Command | Satisfies gate |
|---------|----------------|
| `/requirements-framework:brainstorm` (brainstorming skill) | `design_approved` |
| `/requirements-framework:write-plan` (writing-plans skill) | `plan_written` |
| `/requirements-framework:arch-review` | `plan_validated` |
| `/requirements-framework:pre-commit` | `implementation_done` (per-commit loop) |
| `/requirements-framework:deep-review` | `pr_reviewed` |
| verification-before-completion skill | `verified` |

The current gate set is `design_approved`, `plan_written`, `plan_validated`,
`implementation_done`, `pr_reviewed`, `verified`. See the "Workflow Phase Backbone
(ADR-022)" section in `CLAUDE.md` for the full typed 7-node backbone.

---

## Development Mode

### Live Editing Workflow

Load the plugin from your clone with `--plugin-dir` and edit in place:

```bash
claude --plugin-dir ~/Tools/claude-requirements-framework/plugins/requirements-framework
```

Edit a component and reload the session to pick up changes — no reinstall, no
hook deploy:

```bash
# 1. Edit a component in the repo
$EDITOR plugins/requirements-framework/agents/code-reviewer.md

# 2. Reload the Claude Code session (or restart) to pick it up

# 3. Test it
/requirements-framework:pre-commit
```

### Testing Framework Changes

Run tests and lint through `uv` (matches CI):

```bash
cd ~/Tools/claude-requirements-framework
uv run python hooks/test_requirements.py
uv run ruff check .
```

> **Plugin version bump:** any change to plugin files (agents, commands, skills,
> hooks, or `plugin.json`) must bump the version in
> `plugins/requirements-framework/.claude-plugin/plugin.json` in the same commit.

### Development vs Production

**Development (`--plugin-dir`):** edits are picked up on session reload.

**Production (marketplace):** changes require a reinstall:
```
/plugin marketplace update requirements-framework
/plugin uninstall requirements-framework@requirements-framework
/plugin install requirements-framework@requirements-framework
```

---

## Configuration

The plugin respects the standard configuration cascade (same as the hooks it
bundles):

1. **`~/.claude/requirements.yaml`** (Global)
2. **`.claude/requirements.yaml`** (Project, version-controlled)
3. **`.claude/requirements.local.yaml`** (Local overrides, gitignored)

Priority: **local > project > global**.

Scaffold a project config with `req init` (or the `/req-init` command). See
[Configuration System](../README.md#configuration-system) for details and
`examples/` for reference configs.

---

## Related Documentation

- **[Main README](../README.md)** — framework overview and quick start
- **[Plugin README](../plugins/requirements-framework/README.md)** — plugin usage guide
- **[CLAUDE.md](../CLAUDE.md)** — operational essentials: stacked-git workflow,
  uv build/test, config cascade, the ADR-022 workflow backbone (ADR-021 uv). The
  full hook lifecycle (17 hook commands across 12 events) lives in `DEVELOPMENT.md`.
- **ADRs** (`docs/adr/`):
  - ADR-011 — externalized messages
  - ADR-012 — Agent Teams integration
  - ADR-020 — strict global preflight (opt-in, fail-closed adoption gate)
  - ADR-022 — typed 7-node workflow backbone / gate consolidation

---

## Support

1. Check the [Troubleshooting](#troubleshooting) section above.
2. Run the test suite from a clone: `uv run python hooks/test_requirements.py`.
3. **Issues:** https://github.com/HarmAalbers/claude-requirements-framework/issues
