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

### Session Lifecycle (Six Hooks)
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

PostToolUse (handle-plan-exit.py) - after ExitPlanMode
    → Shows requirements status proactively
    → Fires before any Edit attempts begin

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

**Hooks** (in `hooks/`):
- `check-requirements.py` - PreToolUse hook entry point
- `handle-session-start.py` - SessionStart hook (context injection)
- `handle-plan-exit.py` - PostToolUse hook for ExitPlanMode
- `auto-satisfy-skills.py` - PostToolUse hook for skill completion
- `clear-single-use.py` - PostToolUse hook for clearing single-use requirements
- `handle-stop.py` - Stop hook (requirement verification)
- `handle-session-end.py` - SessionEnd hook (cleanup)
- `requirements-cli.py` - `req` command implementation
- `ruff_check.py` - Ruff linter hook
- `test_requirements.py` - Test suite (544 tests)
- `test_branch_size_calculator.py` - Branch size calculator tests

**Core Library** (in `hooks/lib/`):
- `requirements.py` - Core BranchRequirements API
- `config.py` - Configuration loader with cascade logic + hook config
- `state_storage.py` - JSON state in `.git/requirements/[branch].json`
- `session.py` - Session tracking and registry
- `registry_client.py` - Registry client for session tracking

**Strategy Pattern** (in `hooks/lib/`):
- `strategy_registry.py` - Central dispatch mechanism for requirement types
- `base_strategy.py` - Abstract base class for strategies
- `blocking_strategy.py` - Blocking requirement type
- `dynamic_strategy.py` - Dynamic requirement type
- `guard_strategy.py` - Guard requirement type (see ADR-004)
- `strategy_utils.py` - Strategy utility functions

**Utilities** (in `hooks/lib/`):
- `branch_size_calculator.py` - Calculate branch diff size
- `calculation_cache.py` - Caching for calculations
- `calculator_interface.py` - Calculator interface abstraction
- `message_dedup_cache.py` - TTL-based deduplication for parallel calls
- `git_utils.py` - Git utilities (branch, repo detection)
- `config_utils.py` - Configuration utility functions
- `colors.py` - Color output for CLI
- `logger.py` - Structured JSON logging
- `feature_selector.py` - Feature selection logic
- `init_presets.py` - Initialization presets
- `interactive.py` - Interactive prompts

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
- **Strategy pattern**: Extensible requirement types via modular strategy architecture (see `hooks/lib/*_strategy.py`)

## Testing Plugin Components

The framework includes 10 agents, 3 commands, and 4 skills that extend Claude Code's capabilities. To test these components during development:

```bash
# Launch Claude Code with plugin loaded (official method)
claude --plugin-dir ~/.claude/plugins/requirements-framework

# This loads the plugin without persistent installation
# Changes to plugin files are immediately available (live reload)
```

**Test commands:**
```
/requirements-framework:pre-commit [aspects]
/requirements-framework:quality-check [parallel]
/requirements-framework:codex-review [scope]
```

**Test skills** (natural language):
- "Show requirements framework status"
- "How to use requirements framework"
- "Extend requirements framework"

**Test agents** (via Task tool or commands):
- code-reviewer, tool-validator, silent-failure-hunter
- test-analyzer, type-design-analyzer, comment-analyzer
- code-simplifier, backward-compatibility-checker
- adr-guardian, codex-review-agent

**For persistent installation**, see `docs/PLUGIN-INSTALLATION.md` for marketplace-based setup.

## Requirement Scopes
| Scope | Behavior |
|-------|----------|
| `session` | Cleared when Claude Code session ends |
| `branch` | Persists across sessions on same branch |
| `permanent` | Never auto-cleared |

## Additional Documentation
- `DEVELOPMENT.md` - Comprehensive development guide with detailed implementation notes
- `docs/adr/` - Architecture Decision Records documenting key design decisions
  - ADR-004: Guard requirement strategy
  - ADR-008: CLAUDE.md weekly maintenance process
- `plugin/README.md` - Plugin architecture with agents, commands, and skills
