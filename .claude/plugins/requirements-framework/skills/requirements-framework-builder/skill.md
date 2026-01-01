---
name: requirements-framework-builder
description: This skill should be used when the user asks to "check requirements framework status", "show requirements progress", "extend requirements framework", "add new requirement type", or wants to customize the unified requirements framework. Also triggers on phrases like "where are we with requirements", "requirements status", "requirements framework overview".
git_hash: 8f2e466
---

# Requirements Framework - Production Status

**Current Status**: ✅ PRODUCTION READY (v2.0.1)
**Last Updated**: 2025-12-28
**Implementation**: Complete - All phases finished

## Implementation History

**Phase 1 (MVP)**: ✅ Complete - All 11 steps (100%) - 2025-12-09
**Phase 2 (Additional Requirements)**: ⏭️ Skipped - Not needed for current use cases
**Phase 3 (Polish & UX)**: ✅ Complete - All 6 steps (100%) - 2025-12-24
**Repository**: ✅ https://github.com/HarmAalbers/claude-requirements-framework

## Phase 3 Completion (2025-12-24)

All 6 steps completed:

1. ✅ **Session Registry & Auto-Detection** (77 tests)
   - Session registry infrastructure (`~/.claude/sessions.json`)
   - CLI auto-detection (req satisfy auto-finds correct session)
   - New `req sessions` command
   - PID validation and stale cleanup

2. ✅ **Enhanced Error Messages** (4 sub-steps)
   - Session context in error messages
   - Session bootstrap bug fix
   - Permission override bypass fix
   - Plan file whitelisting

3. ✅ **Terminal Colors**
   - Full color module (`lib/colors.py`)
   - NO_COLOR and FORCE_COLOR support
   - TERM=dumb detection

4. ✅ **Per-Project Setup - `req init` Command** (42 tests)
   - Interactive wizard with InquirerPy fallback
   - Five preset profiles: advanced, inherit, relaxed, strict, minimal
   - Non-interactive mode with --yes flag
   - SessionStart hook auto-detection

5. ✅ **CLI Configuration Management - `req config` Command** (14 tests)
   - View and modify requirement settings
   - --enable, --disable, --scope, --message flags
   - --set KEY=VALUE for arbitrary fields
   - Interactive prompt for project vs local config

6. ✅ **Documentation Updates**
   - Updated README.md with Phase 3 features
   - Created ADR-005 for per-project init design
   - Comprehensive framework documentation

### Production Features (v2.0)

- ✅ **421 passing tests** (100% pass rate - comprehensive TDD coverage)
- ✅ **9 active hooks** (SessionStart, PreToolUse, 3x PostToolUse, Stop, SessionEnd, 2 additional)
- ✅ **17 library modules** (requirements, config, session, state, calculator, etc.)
- ✅ **11 CLI commands** (status, satisfy, clear, init, config, doctor, verify, sessions, prune, etc.)
- ✅ **3 requirement strategies** (Blocking, Dynamic, Guard)
- ✅ **Auto-satisfaction** via PostToolUse hooks (skills, bash integration)
- ✅ **Single-use requirements** (auto-cleared after completion)
- ✅ **Message deduplication** (90% reduction in spam, 5-min TTL cache)
- ✅ **Stop hook verification** (prevents stopping with unsatisfied requirements)
- ✅ **Protected branch guards** (prevents edits on main/master)
- ✅ **Branch size calculator** (dynamic requirements with caching)
- ✅ **Interactive initialization** (5 context-aware presets)
- ✅ **Configuration management** (req config for all settings)
- ✅ **Diagnostics** (req doctor verifies installation & sync)
- ✅ Comprehensive documentation and ADRs
- ✅ Git repository with sync workflow
- ✅ Installation script

### New Hooks (v2.0)

| Hook | Type | Purpose |
|------|------|---------|
| `auto-satisfy-skills.py` | PostToolUse (Skill) | Auto-satisfy requirements when mapped skills complete |
| `clear-single-use.py` | PostToolUse (Bash) | Clear `single_use` requirements after action completes |

### New Configuration Options (v2.0)

```yaml
# Bash command pattern matching
trigger_tools:
  - tool: Bash
    command_pattern: "git\\s+commit"  # Regex pattern

# Single-use scope (clears after each action)
scope: single_use
```

**Plan Location**: `~/.claude/plans/unified-requirements-framework-v2.md` (historical reference)
**Progress File**: `requirements-framework-progress.json` (in repository)

## Current Mode: Maintenance & Extension

The framework is complete and production-ready. This skill now focuses on:

1. **Status Reporting** - Provide current implementation state and metrics
2. **Extension Guidance** - Help add new requirement types or features
3. **Customization Support** - Assist with project-specific configurations
4. **Troubleshooting** - Help diagnose and fix framework issues

## Framework Overview

### Architecture

- **Location**: `~/.claude/hooks/` (user-level deployment)
- **Repository**: `/Users/harm/Tools/claude-requirements-framework/`
- **Sync Tool**: `./sync.sh` (keeps deployment in sync with repo)

### Key Components

**Hooks (9 total)**:
- `check-requirements.py` - PreToolUse (blocks file modifications)
- `handle-session-start.py` - SessionStart (injects context)
- `handle-stop.py` - Stop (verifies requirements before stopping)
- `handle-session-end.py` - SessionEnd (cleanup)
- `handle-plan-exit.py` - PostToolUse for ExitPlanMode
- `auto-satisfy-skills.py` - PostToolUse for Skill tool
- `clear-single-use.py` - PostToolUse for Bash
- `ruff_check.py` - Linting hook
- (1 additional hook)

**Libraries (17 modules)** in `lib/`:
- Core: `requirements.py`, `config.py`, `state_storage.py`
- Session: `session.py`, `registry_client.py`
- Strategies: `requirement_strategies.py`
- Utilities: `git_utils.py`, `colors.py`, `logger.py`
- Calculators: `branch_size_calculator.py`, `calculation_cache.py`
- Interactive: `interactive.py`, `init_presets.py`, `feature_selector.py`
- And more...

**CLI Tool**: `requirements-cli.py` (1,839 lines, 11 commands)

### Requirement Types

1. **Blocking** - Manual satisfy required (commit_plan, github_ticket, adr_reviewed)
2. **Dynamic** - Auto-check conditions (branch_size_limit with calculations)
3. **Guard** - Conditions must pass (protected_branch check)

## How to Extend the Framework

### Adding a New Requirement Type

To add a custom requirement (e.g., `code_review`, `security_scan`):

1. **Define in configuration** (`.claude/requirements.yaml`):
   ```yaml
   requirements:
     code_review:
       enabled: true
       type: blocking  # or dynamic, guard
       scope: session  # or branch, permanent, single_use
       trigger_tools: [Edit, Write, MultiEdit]
       message: |
         📝 **Code Review Required**

         Please review your changes before proceeding.

         **To satisfy**: `req satisfy code_review`
   ```

2. **For dynamic requirements** (auto-calculated conditions):
   - Implement calculator in `lib/` (e.g., `code_quality_calculator.py`)
   - Add to `requirement_strategies.py`
   - Update tests in `test_requirements.py`

3. **For auto-satisfy** (integrate with skills/tools):
   - Update `auto-satisfy-skills.py` with mapping
   - Add skill pattern matching

4. **Test the new requirement**:
   ```bash
   cd /Users/harm/Tools/claude-requirements-framework
   python3 hooks/test_requirements.py
   ```

### Customizing for a Project

Use `req init` for guided setup, or manually create:

**.claude/requirements.yaml**:
```yaml
version: "1.0"
inherit: true  # Inherit from global config
enabled: true

requirements:
  commit_plan:
    enabled: true
    message: "Custom message for this project"

  custom_requirement:
    enabled: true
    type: blocking
    scope: branch
    message: "Project-specific requirement"
```

### Troubleshooting

Common issues and solutions:

1. **Hook not triggering**: Check `req doctor` for hook registration
2. **Wrong session ID**: Use `req sessions` to see active sessions
3. **Sync issues**: Run `./sync.sh status` to check repo vs deployed
4. **Test failures**: Run `python3 hooks/test_requirements.py -v` for details

## CLI Commands Reference

All available commands:

| Command | Description | Example |
|---------|-------------|---------|
| `req status` | Show requirement status | `req status` |
| `req satisfy` | Mark requirement satisfied | `req satisfy commit_plan` |
| `req clear` | Clear a requirement | `req clear commit_plan` |
| `req init` | Interactive project setup | `req init --preset strict` |
| `req config` | View/modify configuration | `req config commit_plan --enable` |
| `req doctor` | Verify installation | `req doctor` |
| `req verify` | Quick installation check | `req verify` |
| `req sessions` | View active sessions | `req sessions` |
| `req list` | List all requirements | `req list` |
| `req prune` | Clean stale data | `req prune` |
| `req enable` | Enable a requirement | `req enable commit_plan` |
| `req disable` | Disable a requirement | `req disable commit_plan` |

## Development Workflow

### Making Changes to the Framework

1. **Edit in repository**:
   ```bash
   cd /Users/harm/Tools/claude-requirements-framework
   # Edit files in hooks/, hooks/lib/, etc.
   ```

2. **Run tests** (TDD workflow):
   ```bash
   python3 hooks/test_requirements.py
   ```

3. **Deploy changes**:
   ```bash
   ./sync.sh deploy  # Copy repo → ~/.claude/hooks/
   ```

4. **Verify deployment**:
   ```bash
   req doctor
   ```

### Test Coverage

- **Total tests**: 421 (100% pass rate)
- **Test file**: `hooks/test_requirements.py` (3,792 lines)
- **Test categories**: 16+ covering all hooks and features

## Architecture Decision Records

See `docs/adr/` for architectural decisions:

- **ADR-001**: Remove main/master branch skip
- **ADR-002**: Use Claude Code's native session_id
- **ADR-003**: Dynamic sync file discovery
- **ADR-004**: Guard requirement strategy
- **ADR-005**: Per-project init command

## Key Resources

- **README**: `/Users/harm/Tools/claude-requirements-framework/README.md`
- **Development Guide**: `DEVELOPMENT.md`
- **Framework Docs**: `docs/README-REQUIREMENTS-FRAMEWORK.md`
- **Sync Tool**: `./sync.sh` (status, deploy, pull commands)
- **Installation**: `./install.sh`

## When to Use This Skill

Invoke this skill when you need to:

- ✅ Check the current state of the framework
- ✅ Understand what features are available
- ✅ Add a new requirement type to the framework
- ✅ Customize requirements for a specific project
- ✅ Troubleshoot framework issues
- ✅ Understand the architecture and design decisions

**For daily usage** (checking/satisfying requirements), use the `requirements-framework-usage` skill instead.
