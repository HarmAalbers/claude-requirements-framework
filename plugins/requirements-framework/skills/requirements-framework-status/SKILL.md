---
name: requirements-framework-status
description: This skill should be used when the user asks to "requirements framework status", "show requirements project context", "what's the state of requirements framework", "requirements framework overview", or wants a comprehensive status report of the requirements framework implementation and current state.
git_hash: 7953a43
---

# Requirements Framework - Status Report

Provides comprehensive project context and current state of the **Claude Code Requirements Framework**.

## Current Implementation Status

**Version**: 2.1.0
**Status**: ✅ Production Ready & Feature Complete
**Repository**: https://github.com/HarmAalbers/claude-requirements-framework

---

## Quick Metrics

| Metric | Value |
|--------|-------|
| **Production Code** | ~8,500 lines |
| **Test Suite** | 544 tests (100% pass) |
| **Hooks** | 9 active |
| **Library Modules** | 17 |
| **CLI Commands** | 11 |
| **Requirement Types** | 3 strategies |
| **Plugin Agents** | 16 |
| **Plugin Commands** | 11 |
| **Plugin Skills** | 19 |

**→ Full component inventory**: See `references/component-inventory.md`

---

## Implementation Timeline

### Phase 1: MVP ✅ (2025-12-09)
- Core framework structure
- Session management
- State storage (`.git/requirements/`)
- Configuration cascade
- PreToolUse hook
- CLI tool (`req` command)

### Phase 2: Additional Requirements ⏭️
- Skipped - Not needed for current use cases

### Phase 3: Polish & UX ✅ (2025-12-24)
- Session registry & auto-detection (77 tests)
- Enhanced error messages
- Terminal colors (NO_COLOR support)
- `req init` interactive wizard (42 tests)
- `req config` management (14 tests)

---

## Core Components

### Hooks (9 total)

| Hook | Type | Purpose |
|------|------|---------|
| `check-requirements.py` | PreToolUse | Blocks Edit/Write if unsatisfied |
| `handle-session-start.py` | SessionStart | Context injection, status display |
| `handle-stop.py` | Stop | Verify requirements before stopping |
| `handle-session-end.py` | SessionEnd | Cleanup sessions |
| `handle-plan-exit.py` | PostToolUse | Show status after planning |
| `auto-satisfy-skills.py` | PostToolUse | Auto-satisfy on skill completion |
| `clear-single-use.py` | PostToolUse | Clear single_use after action |
| `ruff_check.py` | PreToolUse | Python linting |

### Libraries (17 modules)

**Core**: `requirements.py`, `config.py`, `state_storage.py`, `session.py`, `registry_client.py`

**Strategies**: `strategy_registry.py`, `base_strategy.py`, `blocking_strategy.py`, `dynamic_strategy.py`, `guard_strategy.py`

**Utilities**: `branch_size_calculator.py`, `calculation_cache.py`, `message_dedup_cache.py`, `git_utils.py`, `colors.py`, `logger.py`

### CLI Commands (11)

`status`, `satisfy`, `clear`, `init`, `config`, `doctor`, `verify`, `sessions`, `list`, `prune`, `logging`

---

## Architecture Overview

### Configuration Cascade

```
Global (~/.claude/requirements.yaml)
    ↓ (merge if inherit=true)
Project (.claude/requirements.yaml)
    ↓ (always merge)
Local (.claude/requirements.local.yaml)
```

### Requirement Strategies

| Type | Satisfaction | Use Case |
|------|--------------|----------|
| **Blocking** | Manual (`req satisfy`) | Planning, review |
| **Dynamic** | Auto-calculated | Branch size limits |
| **Guard** | Condition check | Protected branches |

### Session Lifecycle

```
SessionStart → PreToolUse → PostToolUse → Stop → SessionEnd
```

**→ Full architecture details**: See `references/architecture-overview.md`

---

## Advanced Features

| Feature | Status | Description |
|---------|--------|-------------|
| Auto-Satisfaction | ✅ | Skills auto-satisfy requirements |
| Single-Use Scope | ✅ | Clears after each action |
| Message Dedup | ✅ | 5-min TTL, 90% spam reduction |
| Stop Verification | ✅ | Blocks stop if unsatisfied |
| Branch Guards | ✅ | Protected branch enforcement |
| Branch Size Calc | ✅ | Dynamic with 30-sec cache |
| Interactive Init | ✅ | 5 context-aware presets |
| Config Management | ✅ | `req config` without YAML editing |

---

## Plugin Components

### Agents (16)

**Workflow**: `adr-guardian`, `codex-review-agent`, `commit-planner`, `solid-reviewer`, `tdd-validator`

**Review**: `code-reviewer`, `silent-failure-hunter`, `test-analyzer`, `type-design-analyzer`, `comment-analyzer`, `code-simplifier`, `tool-validator`, `backward-compatibility-checker`

**Utility**: `comment-cleaner`, `import-organizer`, `session-analyzer`

### Commands (11)

- `/requirements-framework:arch-review` - Team-based architecture review (recommended for planning)
- `/requirements-framework:deep-review` - Cross-validated team review (recommended for PR)
- `/requirements-framework:pre-commit` - Quick pre-commit review
- `/requirements-framework:quality-check` - Lightweight PR review (alternative to /deep-review)
- `/requirements-framework:plan-review` - Lightweight plan review (alternative to /arch-review)
- `/requirements-framework:codex-review` - Codex-powered review
- `/requirements-framework:commit-checks` - Auto-fix code quality issues
- `/requirements-framework:session-reflect` - Session analysis and improvements
- `/requirements-framework:brainstorm` - Design-first development
- `/requirements-framework:write-plan` - Create implementation plan
- `/requirements-framework:execute-plan` - Execute plan with checkpoints

### Skills (19)

**Framework Skills (5):**
- `requirements-framework-usage` - Usage help
- `requirements-framework-status` - This skill
- `requirements-framework-development` - Dev workflow
- `requirements-framework-builder` - Extension guidance
- `session-learning` - Session analysis and improvement

**Process Skills (14):**
- `using-requirements-framework` - Bootstrap skill (session start injection)
- `brainstorming` - Design-first exploration
- `writing-plans` - Implementation plan creation
- `executing-plans` - Plan execution with checkpoints
- `test-driven-development` - RED-GREEN-REFACTOR enforcement
- `systematic-debugging` - Root-cause investigation
- `verification-before-completion` - Evidence-based completion
- `subagent-driven-development` - Parallel task execution
- `finishing-a-development-branch` - Branch completion options
- `using-git-worktrees` - Isolated workspaces
- `dispatching-parallel-agents` - Concurrent problem solving
- `receiving-code-review` - Technical feedback evaluation
- `requesting-code-review` - Review agent dispatch
- `writing-skills` - TDD-for-documentation meta-skill

---

## Architecture Decision Records

| ADR | Decision |
|-----|----------|
| ADR-001 | Remove main/master branch skip |
| ADR-002 | Use Claude Code's native session_id |
| ADR-003 | Dynamic sync file discovery |
| ADR-004 | Guard requirement strategy |
| ADR-005 | Per-project init command |
| ADR-006 | Plugin-based architecture |
| ADR-007 | Deterministic command orchestrators |
| ADR-008 | CLAUDE.md weekly maintenance |

---

## Production Readiness

- ✅ 544 tests, 100% pass rate
- ✅ TDD methodology throughout
- ✅ Fail-open design (errors don't block)
- ✅ Session management & cleanup
- ✅ Interactive setup wizard
- ✅ Comprehensive diagnostics (`req doctor`)
- ✅ Zero external dependencies
- ✅ Color support (NO_COLOR compliant)
- ✅ Performance optimization (caching)

---

## Usage Guide

### For New Users
```bash
req init              # Interactive setup
req status            # Check status
req doctor            # Verify installation
```

### For Framework Developers
```bash
./sync.sh status      # Check sync
./sync.sh deploy      # Deploy changes
python3 ~/.claude/hooks/test_requirements.py  # Run tests
```

### For Team Leads
```bash
req init --preset strict   # Team onboarding
req config                 # View settings
```

---

## Resources

- **Repository**: https://github.com/HarmAalbers/claude-requirements-framework
- **README**: `/Users/harm/Tools/claude-requirements-framework/README.md`
- **Development Guide**: `DEVELOPMENT.md`
- **Sync Tool**: `./sync.sh`
- **Tests**: `hooks/test_requirements.py`

## Reference Files

- `references/component-inventory.md` - Detailed component listing with line counts
- `references/architecture-overview.md` - Design patterns and architectural decisions
