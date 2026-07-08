---
name: requirements-framework-status
description: This skill should be used when the user asks to "requirements framework status", "show requirements project context", "what's the state of requirements framework", "requirements framework overview", or wants a comprehensive status report of the requirements framework implementation and current state.
git_hash: b03be42
---

# Requirements Framework — Status Report

Report the current state of the **Claude Code Requirements Framework** by deriving
every volatile number from the repository at runtime. Do NOT quote pre-baked metrics —
the whole point of this skill is that the figures come from the repo, so they can
never drift.

## Live status — run these, then report the output

Run this block **from the framework repo root** (the paths are repo-relative; in a
marketplace/plugin-cache context they won't resolve — say so and skip rather than
invent a value). If a command errors, report that and move on.

```bash
# Version
grep '"version"' plugins/requirements-framework/.claude-plugin/plugin.json

# Hook scripts (lifecycle handlers) — exclude tests, the CLI, lib/, and the
# vendored _langfuse_hook.py (leading underscore = not a registered hook).
# langfuse-trace.py IS a hook (the opt-in observability Stop hook).
ls hooks/*.py | grep -vE 'test_|requirements-cli|/lib/|/_'

# Plugin component counts
ls plugins/requirements-framework/agents/*.md   | wc -l   # agents
ls plugins/requirements-framework/commands/*.md | wc -l   # commands
ls -d plugins/requirements-framework/skills/*/  | wc -l   # skills

# ADRs (read the numeric range from the listing, e.g. ADR-001 … ADR-020)
ls docs/adr/ADR-*.md

# CLI subcommands
req --help

# Live gating state for the current branch / session.
# Outside a live Claude Code session this prints a harmless
# "No Claude Code session detected" warning (still exit 0) — not a fault.
req status
```

Then report, in a compact table: **version**, **hook / agent / command / skill
counts**, **ADR range**, and a one-line summary of the **live gating state** from
`req status`. Flag anything unexpected (missing files, a non-fresh render).

**Opt-in health check** — the full test suite runs ~1500 tests (~30s), too heavy to
run on every status readout, so only run it when asked to verify health:

```bash
python3 hooks/test_requirements.py 2>&1 | grep -E 'Results:|passed' | tail -1
```

## Durable reference (rarely changes)

### Configuration cascade

```
Global (~/.claude/requirements.yaml)
    ↓ (merge if inherit=true)
Project (.claude/requirements.yaml)
    ↓ (always merge)
Local (.claude/requirements.local.yaml)
```

Priority: **local > project > global**.

### Requirement strategies

| Type | Satisfaction | Use case |
|------|--------------|----------|
| **Blocking** | Manual (`req satisfy`) or skill auto-satisfy | Planning, review gates |
| **Dynamic** | Auto-calculated, then approved | Branch size limits |
| **Guard** | Condition check | Protected branches |

### Requirement scopes

| Scope | Behavior |
|-------|----------|
| `session` | Cleared when the Claude Code session ends |
| `branch` | Persists across sessions on the same branch |
| `permanent` | Never auto-cleared |
| `single_use` | Cleared after the trigger command completes |

### Session lifecycle (hook events, in order)

```
SessionStart → UserPromptSubmit → PreToolUse → PermissionRequest →
PostToolUse → PostToolUseFailure → SubagentStart → PreCompact →
Stop → SessionEnd → TeammateIdle → TaskCompleted
```

(For the current concrete hook scripts, use the `ls hooks/*.py` line above rather
than a frozen list.)

## Usage guide

```bash
# Users
req init              # Interactive setup
req status            # Check current gating state
req doctor            # Verify installation

# Framework developers
./sync.sh status                              # Check repo ↔ deployed sync
./sync.sh deploy                              # Deploy repo → ~/.claude/hooks
python3 hooks/test_requirements.py            # Run the test suite
```

## Deeper reference

- `references/architecture-overview.md` — design patterns and architectural decisions.
- `docs/adr/` — Architecture Decision Records (list with the `ls docs/adr/` line above).
- Repository: https://github.com/HarmAalbers/claude-requirements-framework
