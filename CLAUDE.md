# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build & Test Commands

```bash
# Run test suite
python3 hooks/test_requirements.py

# Sync between repo and deployed location (~/.claude/hooks)
./sync.sh status   # Check sync status (run before committing!)
./sync.sh deploy   # Copy repo → ~/.claude/hooks
./sync.sh pull     # Copy ~/.claude/hooks → repo

# Installation
./install.sh
```

## Architecture

### Two-Location System
The framework exists in two places that must stay synchronized:
- **Repository** (`~/Tools/claude-requirements-framework/`) - Source of truth, git-controlled
- **Deployed** (`~/.claude/hooks/`) - Active runtime where Claude Code loads hooks

Always run `./sync.sh status` before committing to ensure both locations are in sync.

### Session Lifecycle (Four Hooks)
```
SessionStart (handle-session-start.py)
    → Clean stale sessions
    → Inject full status into context

PreToolUse (check-requirements.py) - triggered on Edit/Write
    → Load config (global → project → local cascade)
    → Check requirements against session/branch state
    → Allow or block with message

Stop (handle-stop.py) - when Claude finishes
    → Check stop_hook_active flag (prevent loops!)
    → Verify session-scoped requirements
    → Block stop if unsatisfied (enabled by default)

SessionEnd (handle-session-end.py) - session ends
    → Remove session from registry
    → Optional: clear session state
```

### Configuration Cascade
1. **Global**: `~/.claude/requirements.yaml`
2. **Project**: `.claude/requirements.yaml` (version controlled)
3. **Local**: `.claude/requirements.local.yaml` (gitignored)

### Key Components
- `hooks/check-requirements.py` - PreToolUse hook entry point
- `hooks/handle-session-start.py` - SessionStart hook (context injection)
- `hooks/handle-stop.py` - Stop hook (requirement verification)
- `hooks/handle-session-end.py` - SessionEnd hook (cleanup)
- `hooks/requirements-cli.py` - `req` command implementation
- `hooks/ruff_check.py` - Ruff linter hook
- `hooks/test_requirements.py` - Comprehensive test suite (147 tests)
- `hooks/test_branch_size_calculator.py` - Branch size calculator tests
- `hooks/lib/requirements.py` - Core BranchRequirements API
- `hooks/lib/config.py` - Configuration loader with cascade logic + hook config
- `hooks/lib/requirement_strategies.py` - Strategy pattern for requirement types
- `hooks/lib/state_storage.py` - JSON state in `.git/requirements/[branch].json`
- `hooks/lib/session.py` - Session tracking and registry
- `hooks/lib/branch_size_calculator.py` - Calculate branch diff size
- `hooks/lib/message_dedup_cache.py` - TTL-based deduplication for parallel calls
- `hooks/lib/logger.py` - Structured JSON logging

## Development Patterns

### TDD Workflow
1. Write tests in `hooks/test_requirements.py`
2. Deploy: `./sync.sh deploy`
3. Run tests (RED): `python3 ~/.claude/hooks/test_requirements.py`
4. Implement feature
5. Deploy and run tests (GREEN)
6. Commit

### Design Principles
- **Fail-open**: Errors in the hook never block work
- **Zero dependencies**: Python stdlib only (PyYAML optional, falls back to JSON)
- **Strategy pattern**: Extensible requirement types via `requirement_strategies.py`

## Requirement Scopes
| Scope | Behavior |
|-------|----------|
| `session` | Cleared when Claude Code session ends |
| `branch` | Persists across sessions on same branch |
| `permanent` | Never auto-cleared |
