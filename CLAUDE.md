# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build & Test Commands

```bash
# Run test suite
python3 hooks/test_requirements.py

# Sync between repo and deployed location (~/.claude/hooks)
./sync.sh status   # Check sync status (run before committing!)
./sync.sh deploy   # Copy repo → ~/.claude/hooks

# Installation
./install.sh

# Configure logging (debug, info, warning, error)
req logging                         # Show current config
req logging --level debug --local   # Enable debug logging
req logging --destinations file stdout --local  # Log to file and stdout
tail -f ~/.claude/requirements.log  # View logs in real-time
```

## Architecture

### Two-Location System
The framework exists in two places that must stay synchronized:
- **Repository** (`~/Tools/claude-requirements-framework/`) - Source of truth, git-controlled
- **Deployed** (`~/.claude/hooks/`) - Active runtime where Claude Code loads hooks

Always run `./sync.sh status` before committing to ensure both locations are in sync.

### Session Lifecycle (Thirteen Hooks)
```
SessionStart (handle-session-start.py)
    → Clean stale sessions
    → Update registry with current session
    → Inject full status into context

UserPromptSubmit (handle-prompt-submit.py) - before Claude processes user prompt
    → Inject compact requirement status for edit/commit prompts
    → Track prompt count in session metrics

PreToolUse (check-requirements.py) - triggered on Edit/Write/Bash/EnterPlanMode/ExitPlanMode
    → Load config (global → project → local cascade)
    → Check requirements against session/branch state
    → Allow or block with message
    → Plan mode triggers enable ADR validation at planning time

PermissionRequest (handle-permission-request.py) - before permission dialog shown
    → Auto-deny dangerous command patterns (rm -rf, force push, etc.)
    → Log permission patterns in session metrics

PostToolUse (auto-satisfy-skills.py) - after Skill tool completes
    → Auto-satisfy requirements when review skills complete
    → Maps: /requirements-framework:pre-commit → pre_commit_review (deprecated, kept for backward compat)
    → Maps: /requirements-framework:quality-check → pre_pr_review
    → Maps: /requirements-framework:codex-review → codex_reviewer
    → Maps: /requirements-framework:plan-review → commit_plan, adr_reviewed, tdd_planned, solid_reviewed
    → Maps: /requirements-framework:deep-review → pre_pr_review
    → Maps: /requirements-framework:arch-review → commit_plan, adr_reviewed, tdd_planned, solid_reviewed

PostToolUse (clear-single-use.py) - after certain Bash commands
    → Clears single_use requirements after trigger commands
    → Example: Clears single_use requirements after trigger commands

PostToolUse (handle-plan-enter.py) - after EnterPlanMode
    → Auto-invoke brainstorming skill if design_approved not satisfied
    → Configurable via hooks.plan_enter.brainstorm_on_enter (default: true)

PostToolUse (handle-plan-exit.py) - after ExitPlanMode
    → Shows requirements status proactively
    → Fires before any Edit attempts begin

PostToolUseFailure (handle-tool-failure.py) - when a tool call fails
    → Track failure patterns in session metrics
    → Suggest running review after repeated failures (threshold: 3)

SubagentStart (handle-subagent-start.py) - when a subagent is spawned
    → Inject requirement context into review subagents
    → Track subagent spawn events in session metrics

PreCompact (handle-pre-compact.py) - before context compaction
    → Save requirement state and session metrics before compaction
    → Track compaction frequency in session metrics

Stop (handle-stop.py) - when Claude finishes
    → Check stop_hook_active flag (prevent loops!)
    → Verify session-scoped requirements
    → Block stop if unsatisfied (enabled by default)

SessionEnd (handle-session-end.py) - session ends
    → Remove session from registry
    → Optional: clear session state

TeammateIdle (handle-teammate-idle.py) - when teammate goes idle (ADR-012)
    → Log idle event to session metrics
    → Optionally re-engage idle teammate (exit code 2)
    → Disabled by default (hooks.agent_teams.keep_working_on_idle)

TaskCompleted (handle-task-completed.py) - when team task completes (ADR-012)
    → Record task completion in session metrics
    → Optionally validate task output quality
    → Disabled by default (hooks.agent_teams.validate_task_completion)
```

### Configuration Cascade
1. **Global**: `~/.claude/requirements.yaml`
2. **Project**: `.claude/requirements.yaml` (version controlled)
3. **Local**: `.claude/requirements.local.yaml` (gitignored)

### Key Components

**Hooks** (in `hooks/`):
- `check-requirements.py` - PreToolUse hook entry point
- `handle-session-start.py` - SessionStart hook (context injection)
- `handle-prompt-submit.py` - UserPromptSubmit hook (prompt context injection)
- `handle-permission-request.py` - PermissionRequest hook (auto-deny dangerous commands)
- `handle-plan-enter.py` - PostToolUse hook for EnterPlanMode (brainstorm auto-invoke)
- `handle-plan-exit.py` - PostToolUse hook for ExitPlanMode
- `auto-satisfy-skills.py` - PostToolUse hook for skill completion
- `clear-single-use.py` - PostToolUse hook for clearing single-use requirements
- `handle-tool-failure.py` - PostToolUseFailure hook (failure pattern tracking)
- `handle-subagent-start.py` - SubagentStart hook (review agent context injection)
- `handle-pre-compact.py` - PreCompact hook (pre-compaction state saving)
- `handle-stop.py` - Stop hook (requirement verification)
- `handle-session-end.py` - SessionEnd hook (cleanup)
- `handle-teammate-idle.py` - TeammateIdle hook (team progress tracking, ADR-012)
- `handle-task-completed.py` - TaskCompleted hook (team task quality gates, ADR-012)
- `requirements-cli.py` - `req` command implementation
- `ruff_check.py` - Ruff linter hook
- `test_requirements.py` - Test suite (950+ tests)
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

**Session Learning** (in `hooks/lib/`):
- `session_metrics.py` - Session data collection and storage
- `learning_updates.py` - Apply and track learning updates with rollback

**Message System** (in `hooks/lib/`):
- `messages.py` - MessageLoader for externalized YAML messages (see ADR-011)
- `message_validator.py` - Validation for message files

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
- **Dependencies**: Python stdlib + PyYAML for YAML config parsing
- **Strategy pattern**: Extensible requirement types via modular strategy architecture (see `hooks/lib/*_strategy.py`)

## Testing Plugin Components

The framework includes 19 agents, 8 commands, and 5 skills that extend Claude Code's capabilities.

### Development Testing (Live Reload)

For development, use the `--plugin-dir` flag for live reload:

```bash
# Launch Claude Code with plugin loaded directly from repo
claude --plugin-dir ~/Tools/claude-requirements-framework/plugin

# Changes to plugin files are immediately available (live reload)
```

### Production Testing (Marketplace Installation)

For testing the installed plugin:

```bash
# Reinstall to get latest version
/plugin uninstall requirements-framework@requirements-framework
/plugin marketplace update requirements-framework
/plugin install requirements-framework@requirements-framework
```

**Test commands:**
```
/requirements-framework:deep-review          # Primary: cross-validated team review
/requirements-framework:arch-review [path]   # Primary: team-based architecture review
/requirements-framework:pre-commit [aspects] # Pre-commit code review
/requirements-framework:quality-check [parallel]  # Lightweight alternative to /deep-review
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
- adr-guardian, codex-review-agent, solid-reviewer
- tenant-isolation-auditor, appsec-auditor, compliance-auditor

**For installation details**, see `docs/PLUGIN-INSTALLATION.md`.

## Serena MCP Configuration

The project uses Serena MCP for semantic code analysis. For optimal performance with Claude Code:

### Configuration Location
`~/.claude/plugins/cache/claude-plugins-official/serena/[version]/.mcp.json`

### Optimal Settings
```json
{
  "serena": {
    "command": "uvx",
    "args": [
      "--from",
      "git+https://github.com/oraios/serena",
      "serena",
      "start-mcp-server",
      "--context",
      "claude-code",
      "--project",
      "/Users/harm/Tools/claude-requirements-framework"
    ]
  }
}
```

### Key Configuration Flags

- `--context claude-code` - Disables tools that duplicate Claude Code's built-in capabilities (prevents conflicts)
- `--project <path>` - Explicitly specifies project directory for focused codebase analysis

### Token Efficiency

Enable on-demand tool loading (requires Claude Code v2.0.74+) by adding to `~/.zshrc`:

```bash
# Enable on-demand tool loading for Claude Code (reduces token usage)
export ENABLE_TOOL_SEARCH=true
```

Then reload shell: `source ~/.zshrc`

This prevents sending complete tool descriptions at startup, reducing token consumption while allowing dynamic tool discovery.

### Verification

After configuration changes, restart Claude Code to apply settings. Verify Serena is active with the correct project context by checking available MCP tools.

## Plan Mode Triggers
Requirements can now trigger on plan mode transitions:
- `EnterPlanMode` - Triggers when Claude enters planning mode
- `ExitPlanMode` - Triggers when Claude exits planning mode

This enables multi-phase ADR workflows:
```yaml
adr_plan_validation:
  enabled: true
  type: blocking
  scope: single_use
  trigger_tools:
    - ExitPlanMode  # Validates plan after planning
  satisfied_by_skill: 'adr-guardian'
```

Use cases:
- Pre-planning ADR review (EnterPlanMode)
- Plan validation against ADRs (ExitPlanMode)
- Architectural compliance at planning stage

See `examples/global-requirements.yaml` for full example configuration.

## Requirement Scopes
| Scope | Behavior |
|-------|----------|
| `session` | Cleared when Claude Code session ends |
| `branch` | Persists across sessions on same branch |
| `permanent` | Never auto-cleared |
| `single_use` | Cleared after trigger command completes |

## Session Learning

The session learning system helps Claude Code improve over time by analyzing sessions and suggesting updates to memories, skills, and commands.

### Enable Session Learning

Add to your `.claude/requirements.yaml`:

```yaml
hooks:
  session_learning:
    enabled: true
    prompt_on_stop: true  # Prompts for review when ending session
    min_tool_uses: 5      # Minimum activity before prompting
```

### Usage

```bash
/session-reflect          # Full analysis with recommendations
/session-reflect quick    # Quick summary statistics
/session-reflect analyze-only  # Analysis without applying changes

req learning stats        # Show learning statistics
req learning list         # List recent updates
req learning rollback 3   # Undo update #3
```

### Storage

- Session metrics: `.git/requirements/sessions/<session_id>.json`
- Learning history: `.git/requirements/learning_history.json`
- Updated memories: `.serena/memories/*.md`

### Design

- **Fail-open**: Metric recording errors never block execution
- **Atomic writes**: File locking + atomic rename for data safety
- **User approval**: All updates require user approval before applying
- **Rollback capable**: Every change recorded with previous content hash

## Obsidian CLI Integration

The framework can log session data to Obsidian via the [Obsidian CLI](https://help.obsidian.md/cli) (requires Obsidian v1.12.4+ with CLI enabled).

### Enable

```yaml
# In requirements.yaml (global or project)
hooks:
  obsidian:
    enabled: true
    vault: "MyVault"              # Optional, defaults to active vault
    session_folder: "Claude/Sessions"  # Folder for detail notes
    index_note: "Claude/Sessions Log"  # Ledger note name
    update_on_commit: true        # Log git commits to timeline
    update_on_requirement: true   # Log requirement satisfactions
    timeout: 5                    # CLI call timeout (seconds)
```

### What Gets Logged

- **SessionStart**: Creates a detail note with YAML frontmatter (project, branch, status, tags) + adds row to ledger
- **Git commits**: Appends timeline entry to detail note
- **Requirement satisfaction**: Appends timeline entry to detail note
- **SessionEnd**: Finalizes detail note with metrics (duration, tool uses, commits) + updates ledger row

### Architecture

- `hooks/lib/obsidian.py` — `ObsidianClient` (CLI wrapper) + `ObsidianSessionLogger` (lifecycle orchestrator)
- Integrates into: `handle-session-start.py`, `handle-session-end.py`, `auto-satisfy-skills.py`, `clear-single-use.py`
- **Fail-open**: Obsidian errors never block Claude Code. If Obsidian isn't running, logging is silently skipped.

## Agent Teams (ADR-012)

The framework uses Claude Code Agent Teams as the **primary review approach**. Agents collaborate, cross-validate findings, and produce unified verdicts.

### Commands (Recommended)
- `/deep-review` — Cross-validated team-based code review with agent debate. Satisfies `pre_pr_review`.
- `/arch-review` — Multi-perspective architecture review with commit planning. Satisfies `commit_plan`, `adr_reviewed`, `tdd_planned`, `solid_reviewed`.

### Lightweight Alternatives
- `/quality-check` — Sequential/parallel subagent review (lower cost, no cross-validation)
- `/plan-review` — Sequential subagent plan review (lower cost, no cross-validation)

### Configuration
```yaml
hooks:
  agent_teams:
    enabled: true           # Enabled by default
    keep_working_on_idle: false  # Re-engage idle teammates
    validate_task_completion: false  # Validate task output
    max_teammates: 5        # Token cost cap
    fallback_to_subagents: true  # Graceful degradation
```

### When to Use Teams vs Lightweight Alternatives
| Use Teams (`/deep-review`, `/arch-review`, `/pre-commit`) | Use Lightweight (`/quality-check`, `/plan-review`) |
|---|---|
| Default for most reviews (recommended) | Need faster, cheaper review |
| Complex changes affecting multiple areas | Simple, focused changes |
| Want cross-validated findings with debate | Independent findings are sufficient |
| Architecture decisions with trade-offs | Single-aspect reviews |
| Pre-commit with 2+ review agents (default) | `/pre-commit code` (single agent, no team value) |

### Hook Events
- `TeammateIdle` — Fires when teammate goes idle. Configurable re-engagement.
- `TaskCompleted` — Fires when team task completes. Configurable validation.

## Message Externalization

Framework messages are stored in external YAML files for customization without code changes.

### Message Directory Cascade
```
~/.claude/messages/              # Global defaults
<project>/.claude/messages/      # Project-specific (version controlled)
<project>/.claude/messages.local/ # Local overrides (gitignored)
```

Priority: **local > project > global** (same as requirements config)

### Message File Schema
Each requirement has 6 required fields:
```yaml
version: "1.0"
blocking_message: |
  ## Blocked: {req_name}
  **Execute**: `/{satisfied_by_skill}`
short_message: "Requirement `{req_name}` not satisfied (waiting...)"
success_message: "Requirement `{req_name}` satisfied"
header: "Commit Plan"
action_label: "Run `/plan-review`"
fallback_text: "req satisfy {req_name}"
```

### Special Files
- `_templates.yaml` - Default templates by requirement type (blocking/guard/dynamic)
- `_status.yaml` - Status briefing format templates (compact/standard/rich)

### CLI Commands
```bash
req messages validate           # Validate all message files
req messages validate --fix     # Generate missing files from templates
req messages list               # List loaded files with cascade sources
```

### Customizing Messages
```bash
# Project-level override
mkdir -p .claude/messages
cat > .claude/messages/commit_plan.yaml << 'EOF'
version: "1.0"
blocking_message: |
  ## Need a Plan First
  Run `/plan-review` before editing.
short_message: "Plan required"
success_message: "Plan approved"
header: "Planning"
action_label: "`/plan-review`"
fallback_text: "req satisfy commit_plan"
EOF
```

See ADR-011 for design details.

## Cross-Project Feature Upgrade

The `req upgrade` command helps discover and adopt new framework features across all projects on your machine.

### Usage

```bash
req upgrade scan               # Scan machine for projects using the framework
req upgrade status             # Show feature status for current project
req upgrade status --all       # Show all tracked projects (brief)
req upgrade recommend          # Generate YAML snippets for missing features
req upgrade recommend -f NAME  # Show snippet for specific feature
```

### How It Works

1. **Project Registry**: Stores discovered projects at `~/.claude/project_registry.json`
2. **Feature Catalog**: Tracks all available features with version info and YAML examples
3. **Auto-Registration**: Projects are registered when sessions start (no manual scan needed)

### Example

```bash
$ req upgrade status
Feature Status: /Users/harm/Work/my-project
────────────────────────────────────────────────
  Requirements:
    commit_plan               ✓ Enabled
    session_learning          ○ Not configured
────────────────────────────────────────────────
  Enabled: 2/12 features

$ req upgrade recommend --feature session_learning
# Shows ready-to-copy YAML snippet
```

## Additional Documentation
- `DEVELOPMENT.md` - Comprehensive development guide with detailed implementation notes
- `docs/adr/` - Architecture Decision Records documenting key design decisions
  - ADR-004: Guard requirement strategy
  - ADR-008: CLAUDE.md weekly maintenance process
  - ADR-010: Cross-project feature upgrade system
  - ADR-011: Externalize messages to YAML files
  - ADR-012: Agent Teams integration
- `plugins/requirements-framework/README.md` - Plugin architecture with agents, commands, and skills
