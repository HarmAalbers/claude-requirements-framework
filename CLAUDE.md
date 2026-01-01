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

### Session Lifecycle (Five Hooks)
```
SessionStart (handle-session-start.py)
    → Clean stale sessions
    → Update registry with current session
    → Inject full status into context

PreToolUse (check-requirements.py) - triggered on Edit/Write
    → Load config (global → project → local cascade)
    → Check requirements against session/branch state
    → Allow or block with message

PostToolUse (auto-satisfy-skills.py) - after Skill tool completes
    → Auto-satisfy requirements when review skills complete
    → Maps: /requirements-framework:pre-commit → pre_commit_review
    → Maps: /requirements-framework:quality-check → pre_pr_review
    → Maps: /requirements-framework:codex-review → codex_reviewer

PostToolUse (clear-single-use.py) - after certain Bash commands
    → Clears single_use requirements after trigger commands
    → Example: Clears pre_commit_review after git commit

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
- `hooks/test_requirements.py` - Comprehensive test suite (447 tests)
- `hooks/test_branch_size_calculator.py` - Branch size calculator tests
- `hooks/lib/requirements.py` - Core BranchRequirements API
- `hooks/lib/config.py` - Configuration loader with cascade logic + hook config
- `hooks/lib/requirement_strategies.py` - Strategy pattern for requirement types
- `hooks/lib/state_storage.py` - JSON state in `.git/requirements/[branch].json`
- `hooks/lib/session.py` - Session tracking and registry
- `hooks/lib/branch_size_calculator.py` - Calculate branch diff size
- `hooks/lib/message_dedup_cache.py` - TTL-based deduplication for parallel calls
- `hooks/lib/logger.py` - Structured JSON logging

## Plugin Component Versioning

All plugin components (agents, commands, skills) include a `git_hash` field in their YAML frontmatter showing the last commit that modified the file. This enables version tracking and A/B testing of component effectiveness.

### Updating Versions

After modifying plugin components:

```bash
# Update git_hash fields
./update-plugin-versions.sh

# Verify changes
./update-plugin-versions.sh --check

# Commit with updated hashes
git add .
git commit -m "feat: update code-reviewer agent"

# Deploy to runtime
./sync.sh deploy
```

### Hash Format

- `abc1234` - Committed, no modifications
- `abc1234*` - Committed but has uncommitted changes
- `uncommitted` - New file, never committed

### Usage Modes

```bash
./update-plugin-versions.sh           # Update all files
./update-plugin-versions.sh --check   # Dry-run (show what would change)
./update-plugin-versions.sh --verify  # Verify hashes are current
```

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
