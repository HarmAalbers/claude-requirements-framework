---
name: requirements-framework-usage
description: This skill should be used when the user asks about "using requirements framework", "how to configure requirements", "add requirement checklist", "customize requirements", "requirements not working", "bypass requirements", "satisfy requirements", or needs help with the requirements framework CLI (req command). Also triggers on questions about requirement scopes, session management, or troubleshooting hooks.
git_hash: 54fa3c3
---

# Requirements Framework Usage

Help users configure, customize, and troubleshoot the **Claude Code Requirements Framework** - a hook-based system that enforces development workflow practices.

The framework ships as a **self-contained Claude Code plugin**. Hook registration is owned by the plugin (`hooks.json` resolved via `${CLAUDE_PLUGIN_ROOT}`); there is no `~/.claude/hooks` deploy step and no `sync.sh`. All Python entrypoints run through `uv` (never a bare `python3`).

**Repository**: https://github.com/HarmAalbers/claude-requirements-framework
**Documentation**: `plugins/requirements-framework/README.md` (in the repo) and the ADRs under `docs/adr/`

## Workflow Backbone (ADR-022, typed 7-node)

The default workflow is a typed 7-node backbone. Each node has one gate (except the gateless final `ship`):

```
Design → Plan → Validate → Build → Review → Verify → Ship
```

| Node | Gate | Skill / Command |
|------|------|-----------------|
| design   | `design_approved`     | `/brainstorming` |
| plan     | `plan_written`        | `/writing-plans` |
| validate | `plan_validated`      | `/arch-review` (team; conditional `/codex-review`) |
| build    | `implementation_done` | `/executing-plans` (loop: `/pre-commit` → `pre_commit_review` per commit) |
| review   | `pr_reviewed`         | `/deep-review` (team; conditional `/codex-review`) |
| verify   | `verified`            | `/verification-before-completion` |
| ship     | — (gateless)          | `/finishing-a-development-branch` |

**Retired gate names** (a config still naming one gets a validation error pointing at the new name):
`commit_plan`, `adr_reviewed`, `tdd_planned`, `solid_reviewed` → **`plan_validated`**; `pre_pr_review` → **`pr_reviewed`**; `pre_push_verification` → **`verified`**; `codex_reviewer` → removed (now a conditional side-quest, not a gate). `pre_commit_review` survives as the Build per-commit loop gate.

## Core Capabilities

1. **Configuration Guidance** - Help set up global, project, and local configs
2. **Checklist Customization** - Add/modify checklists for requirements
3. **CLI Usage** - Explain `req` command and session management
4. **Troubleshooting** - Debug hooks, permissions, and sync issues
5. **Best Practices** - Recommend workflows and patterns

## Quick Reference

### Essential CLI Commands

```bash
req status                    # Check requirement status
req satisfy plan_validated    # Mark requirement satisfied (USER action)
req clear plan_validated      # Clear a requirement (USER action)
req pause                     # Pause blocking gates for this session (Claude may run this)
req resume                    # Resume blocking gates for this session
req list                      # List tracked branches
req sessions                  # View active sessions
req init                      # Interactive project setup
req config plan_validated     # View/modify configuration
req doctor                    # Verify installation (plugin hook integrity)
```

**Who runs what**: `req satisfy` / `req clear` are **user** actions (they represent a human's approval of a gate). `req pause` / `req resume` and read-only commands like `req status` are runnable by Claude.

**→ Full CLI reference**: See `references/cli-reference.md`

### Configuration Locations

1. **Global** (`~/.claude/requirements.yaml`) - Defaults for all projects
2. **Project** (`.claude/requirements.yaml`) - Shared team config (committed)
3. **Local** (`.claude/requirements.local.yaml`) - Personal overrides (gitignored)

### Requirement Scopes

| Scope | Lifetime | Use Case |
|-------|----------|----------|
| `session` | Until Claude session ends | Design/plan gates, ADR review |
| `branch` | Persists across sessions | GitHub ticket linking |
| `permanent` | Never auto-cleared | Project setup |
| `single_use` | Cleared after triggering action | `pre_commit_review` (each commit) |

## Common Tasks

### Task: Add Checklist to Requirement

```yaml
# In .claude/requirements.yaml
requirements:
  plan_validated:
    enabled: true
    scope: session
    checklist:
      - "Plan reviewed by /arch-review"
      - "Atomic commits identified"
      - "TDD approach documented"
```

### Task: Create Custom Requirement

```yaml
requirements:
  my_requirement:
    enabled: true
    scope: session
    trigger_tools:
      - Edit
      - Write
    message: |
      🎯 **Custom Requirement**

      Explain what needs to be done.

      **To satisfy**: `req satisfy my_requirement`
    checklist:
      - "First step"
      - "Second step"
```

**→ More examples**: See `examples/custom-requirement.yaml`

### Task: Block Specific Bash Commands

```yaml
requirements:
  pre_commit_review:
    enabled: true
    scope: single_use
    trigger_tools:
      - tool: Bash
        command_pattern: "git\\s+commit"
    message: "Review required before commit"
```

**Pattern Tips**:
- `\\s+` matches whitespace
- `|` for OR: `git\\s+(commit|push)`
- Case-insensitive by default

**→ More patterns**: See `examples/bash-command-trigger.yaml`

### Task: Temporarily Disable Requirements

**Option 1**: Local override
```yaml
# .claude/requirements.local.yaml
enabled: false
```

**Option 2**: Environment variable
```bash
export CLAUDE_SKIP_REQUIREMENTS=1
```

**Option 3**: Disable specific requirement
```bash
req config plan_validated --disable --local
```

## Interactive Setup

Use `req init` for guided project setup:

```bash
req init                    # Interactive wizard
req init --preset strict    # Use preset (non-interactive)
req init --yes              # Non-interactive with defaults
```

**Presets**:
- `strict` - All requirements, session scope (teams)
- `relaxed` - Basic requirements, branch scope
- `minimal` - Minimal gate set (learning)
- `advanced` - All features + branch limits + guards
- `inherit` - Inherit from global config

## Configuration Management

View and modify settings without editing YAML:

```bash
# View
req config                     # All requirements
req config plan_validated      # Specific requirement
req config --sources           # Show which cascade layer set each value

# Modify
req config plan_validated --enable
req config plan_validated --disable
req config plan_validated --scope branch
req config plan_validated --set adr_path=/custom/path
```

**→ Full config options**: See `references/cli-reference.md`

## Session Management

Sessions are auto-detected. Manual override when needed:

```bash
req sessions                             # List active sessions
req satisfy plan_validated --session ID  # Explicit session
```

## Troubleshooting Quick Guide

### Hook Not Triggering?

1. Check if on main/master (skipped by design)
2. Verify config enabled: `req config`
3. Check plugin hook integrity: `req doctor` (validates `hooks.json` and the scripts it registers)
4. Confirm the plugin is installed/enabled: `/plugin`
5. Verify no skip flag: `echo $CLAUDE_SKIP_REQUIREMENTS`

### Session Not Found?

```bash
req sessions                # Find session ID
req satisfy NAME --session ID
req prune                   # Clean stale sessions
```

**→ Full troubleshooting guide**: See `references/troubleshooting.md`

## Advanced Features

### Auto-Satisfaction via Skills

Skills can automatically satisfy requirements:

```
1. git commit → Blocked by pre_commit_review
2. /requirements-framework:pre-commit runs
3. Auto-satisfies pre_commit_review
4. git commit → Success!
5. single_use clears → Next commit requires review again
```

**Built-in mappings (review commands/skills)**:
- `requirements-framework:arch-review` → `plan_validated` (one Validate gate)
- `requirements-framework:deep-review` → `pr_reviewed`
- `requirements-framework:v3-review` → `pr_reviewed`
- `requirements-framework:pre-commit` → `pre_commit_review` (Build per-commit loop)

**Built-in mappings (process skills)**:
- `requirements-framework:brainstorming` → `design_approved`
- `requirements-framework:writing-plans` → `plan_written`
- `requirements-framework:executing-plans` → `implementation_done`
- `requirements-framework:verification-before-completion` → `verified`
- `requirements-framework:systematic-debugging` → `debugging_systematic`
- `requirements-framework:requesting-code-review` → `pre_commit_review`

**Not gates** (guidance-only / conditional): `requirements-framework:codex-review` is a conditional side-quest on the Validate and Review teams, not a gate; `test-driven-development` is advisory and owns no gate.

### Process Skills (Development Lifecycle)

The framework includes process skills that guide the full development lifecycle:

| Skill | Purpose |
|-------|---------|
| `brainstorming` | Design-first development (explore → design → approve) |
| `writing-plans` | Create bite-sized implementation plans |
| `executing-plans` | Execute plans with batch checkpoints |
| `test-driven-development` | RED-GREEN-REFACTOR cycle enforcement |
| `systematic-debugging` | 4-phase root-cause investigation |
| `verification-before-completion` | Fresh evidence before claiming done |
| `subagent-driven-development` | Parallel task execution with review |
| `finishing-a-development-branch` | Branch completion and merge options |
| `using-git-worktrees` | Isolated workspace creation |
| `dispatching-parallel-agents` | Concurrent problem solving |
| `receiving-code-review` | Technical evaluation of feedback |
| `requesting-code-review` | Dispatching review agents |
| `writing-skills` | TDD-for-documentation (meta-skill) |

Use `/brainstorm`, `/write-plan`, `/execute-plan` commands to invoke process skills directly.

For large multi-layer refactors that exceed a single session, use `/requirements-framework:refactor-orchestrate` — multi-layer top-down refactor workflow (produces plan + orchestrator-prompt for fresh-session execution).

### Single-Use Scope

Requires satisfaction before EACH action:

```yaml
pre_commit_review:
  scope: single_use  # Must satisfy before EVERY commit
```

### Dynamic Requirements

Auto-calculated conditions (e.g., branch size):

```yaml
branch_size_limit:
  type: dynamic
  threshold: 400
```

### Guard Requirements

Condition checks (e.g., protected branches):

```yaml
protected_branch:
  type: guard
  branches: [main, master]
```

**→ Advanced features details**: See `references/advanced-features.md`

## Checklist Best Practices

1. **Keep items concise** - 5-10 words per item
2. **Make actionable** - Each item verifiable
3. **Order logically** - Steps flow naturally
4. **Limit quantity** - 5-10 items maximum

**Good**:
```yaml
checklist:
  - "Plan reviewed by /arch-review"
  - "Atomic commits identified"
  - "Tests written (TDD)"
```

**Bad**:
```yaml
checklist:
  - "Think about what you're going to do and write it down"
  - "Various commit-related activities"
```

## Configuration Patterns

### Pattern: Team Config with Personal Overrides

```yaml
# .claude/requirements.yaml (team - committed)
requirements:
  plan_validated:
    enabled: true
    scope: session

# .claude/requirements.local.yaml (personal - gitignored)
requirements:
  plan_validated:
    enabled: false  # I opt-out
```

### Pattern: Inheritance

```yaml
# Project inherits and extends global
version: "1.0"
inherit: true

requirements:
  plan_validated:
    checklist:
      - "Project-specific checklist item"
```

**→ More patterns**: See `references/configuration-patterns.md`

## Diagnostics

```bash
req doctor   # Full installation check
req verify   # Quick verification
```

`req doctor` checks:
- Python version (3.9+)
- PyYAML availability
- Plugin hook integrity (`hooks.json` + the scripts it registers via `${CLAUDE_PLUGIN_ROOT}`)
- `req` on PATH and callable
- Plugin installation

Use `req doctor --verbose` for all checks, `--json` for machine-readable output, and `--ci` to skip local Claude Code config checks.

## Key Principles

1. **Fail open** - Errors don't block Claude
2. **Skip protected** - Main/master often skipped
3. **User override** - Local settings always win
4. **Session-isolated** - Requirements don't leak
5. **Team configurable** - Projects control workflow

## Resources

- **Plugin README**: `plugins/requirements-framework/README.md` (in the repo)
- **GitHub**: https://github.com/HarmAalbers/claude-requirements-framework
- **Dev Guide**: `DEVELOPMENT.md` (in the repo)
- **ADRs**: `docs/adr/` (ADR-022 = the typed 7-node workflow backbone)
- **Tests** (run via uv): `uv run python hooks/test_requirements.py`

## Reference Files

- `references/cli-reference.md` - Complete CLI command documentation
- `references/configuration-patterns.md` - Common configuration patterns
- `references/advanced-features.md` - Auto-satisfy, dynamic, guards
- `references/troubleshooting.md` - Error messages, debugging
- `examples/project-requirements.yaml` - Full project config
- `examples/custom-requirement.yaml` - Custom requirement template
- `examples/bash-command-trigger.yaml` - Bash command patterns
