# Claude Code Requirements Framework

A powerful hook-based system for enforcing development workflow requirements in Claude Code. Ensures critical steps like commit planning, ADR review, and test-driven development are completed before code modifications.

## Features

- **🔒 PreToolUse Hook**: Blocks file modifications until requirements are satisfied
- **🛑 Stop Hook**: Verifies all requirements before Claude finishes (prevents incomplete work)
- **🚀 SessionStart Hook**: Injects full requirement status at session start
- **🧹 SessionEnd Hook**: Cleans up session state when session ends
- **📋 Customizable Checklists**: Display reminder checklists in requirement blocker messages
- **🎯 Session & Branch Scoping**: Requirements can be session-specific, branch-specific, or permanent
- **⚡ CLI Tool**: Simple `req` command for managing requirements
- **🔄 Session Auto-Detection**: Automatically finds the correct session without manual configuration
- **🚫 Message Deduplication**: Prevents spam when Claude makes parallel tool calls
- **🧪 Comprehensive Tests**: 447 passing tests with full TDD coverage
- **📦 Project Inheritance**: Cascade configuration from global → project → local
- **🔧 Development Tools**: Bidirectional sync.sh for seamless development workflow

## Quick Start

### Installation

```bash
# Clone the repository
git clone <repository-url> ~/tools/claude-requirements-framework
cd ~/tools/claude-requirements-framework

# Run the installation script
./install.sh
```

The installer will:
1. Copy hooks to `~/.claude/hooks/`
2. Install the global configuration to `~/.claude/requirements.yaml`
3. Register all hooks (PreToolUse, PostToolUse, SessionStart, Stop, SessionEnd) in your Claude Code settings
4. Create plugin symlink at `~/.claude/plugins/requirements-framework`

### Verify Plugin Installation

After running `install.sh`, verify the plugin loaded successfully:

```bash
# Check plugin appears in Claude Code
# Start a new session and type:
/requirements-framework:

# Should autocomplete to:
# - /requirements-framework:pre-commit [aspects]
# - /requirements-framework:quality-check [parallel]

# Or check the symlink:
ls -la ~/.claude/plugins/requirements-framework
```

For detailed installation, troubleshooting, and component reference:
- **[Plugin Installation Guide](docs/PLUGIN-INSTALLATION.md)** - Comprehensive reference
- **[Plugin README](plugin/README.md)** - Plugin-specific docs
- **[Plugin Components](#plugin-components)** (below) - Agent/command/skill descriptions

### Project Setup

After installation, initialize requirements for your project:

```bash
# Interactive wizard (recommended)
cd /your/project
req init

# Or non-interactively
req init --yes --preset relaxed
```

#### Initialization Modes

The interactive wizard offers three configuration approaches:

**1. Quick Preset** (Recommended)
Choose from context-aware presets optimized for your setup:

- **`advanced`** - All features (recommended for global config)
  - 7 requirements showcasing every capability
  - Dynamic checks (branch_size_limit with calculator)
  - Single-use requirements (pre_commit_review, pre_pr_review)
  - Guard requirements (protected_branch)
  - Perfect for discovering what the framework can do

- **`inherit`** - Use global defaults (recommended for projects)
  - Sets `inherit: true`
  - Empty requirements (relies on global config)
  - Perfect for projects when you have global config

- **`relaxed`** - Baseline requirements
  - commit_plan only
  - Good for standalone projects or trying the framework

- **`strict`** - Full enforcement
  - commit_plan + protected_branch
  - Good for team projects with protected branches

- **`minimal`** - Framework enabled, no requirements
  - Configure later manually

**2. Custom Selection**
Interactive checkbox to pick specific features:
- Choose from: commit_plan, adr_reviewed, protected_branch, branch_size_limit, pre_commit_review, pre_pr_review
- Perfect for power users who know exactly what they want

**3. Manual Setup**
Starts with minimal config - configure everything yourself later

#### Context-Aware Behavior

`req init` automatically detects your context:

- **Global setup** (`~/.claude/` directory): Defaults to `advanced` preset
- **Project with global config**: Defaults to `inherit` preset
- **Project without global**: Defaults to `relaxed` preset
- **Local override**: Only offers `minimal` preset

The `req init` command creates `.claude/requirements.yaml` with your chosen configuration.

### Basic Usage

```bash
# Check requirement status
req status

# Satisfy the commit_plan requirement
req satisfy commit_plan

# Clear a requirement
req clear commit_plan

# List all requirements
req list

# View active sessions
req sessions

# Configure a requirement
req config commit_plan --enable --scope branch

# Set custom fields (e.g., ADR location)
req config adr_reviewed --set adr_path=/docs/adr

# Diagnose installation and sync status
req doctor --repo ~/Tools/claude-requirements-framework
```

### Doctor Command

Use `req doctor` to verify the framework is installed and synced correctly:

- Confirms the `PreToolUse` hook is registered in `~/.claude/settings.json`
- Ensures `check-requirements.py` and `requirements-cli.py` are executable
- Checks the current project for `.claude/requirements.yaml`
- Compares repository files to the deployed `~/.claude/hooks` installation and recommends whether to deploy or reconcile differences

Pass `--repo` to point at your repository copy if auto-detection fails:

```bash
req doctor --repo ~/Tools/claude-requirements-framework
```

### Managing Configuration

The `req config` command lets you view and modify requirement settings without manually editing YAML files:

```bash
# View current configuration for a requirement
req config commit_plan

# Enable/disable a requirement
req config github_ticket --enable
req config commit_plan --disable

# Change scope
req config commit_plan --scope branch

# Set custom message
req config adr_reviewed --message "📚 Review ADRs in docs/adr/"

# Set arbitrary fields (great for custom requirements)
req config adr_reviewed --set adr_path=/docs/adr
req config dynamic_req --set approval_ttl=600
req config my_requirement --set custom_field="value"

# Multiple changes at once
req config commit_plan --enable --scope branch --message "Custom"

# Interactive mode (asks project vs local)
req config commit_plan --enable

# Non-interactive (for scripts)
req config commit_plan --disable --local --yes
```

The `--set` flag supports:
- **Strings**: `--set adr_path=/docs/adr`
- **Numbers**: `--set approval_ttl=600` (auto-parsed as JSON)
- **Booleans**: `--set strict=true`
- **Arrays**: `--set branches='["main","master"]'`

## Requirements Types

### commit_plan (Recommended)

Ensures you create a commit plan before making code changes.

**Checklist** (customizable):
- ⬜ Identified the changes needed for this feature/fix
- ⬜ Determined atomic commit boundaries (each commit is reviewable)
- ⬜ Planned commit sequence and dependencies
- ⬜ Considered what can be safely rolled back
- ⬜ Created plan file documenting the approach

**Configuration**:
```yaml
requirements:
  commit_plan:
    enabled: true
    scope: session  # Resets each Claude Code session
    trigger_tools:
      - Edit
      - Write
      - MultiEdit
```

### github_ticket

Links branches to GitHub issues for traceability.

```yaml
requirements:
  github_ticket:
    enabled: true
    scope: branch  # Once per branch
```

### adr_reviewed (Example: cclv2 project)

Ensures relevant Architecture Decision Records are reviewed.

```yaml
requirements:
  adr_reviewed:
    enabled: true
    scope: session
    message: |
      📚 **Have you reviewed relevant ADRs?**

      ADRs are in: /path/to/ADR/
```

### protected_branch (Guard Type)

Prevents direct edits on protected branches (main/master).

**Type**: Guard - Checks conditions rather than requiring manual satisfaction

```yaml
requirements:
  protected_branch:
    enabled: true
    type: guard
    guard_type: protected_branch
    protected_branches:
      - master
      - main
```

### branch_size_limit (Dynamic Type)

Automatically calculates branch size and blocks large PRs.

**Type**: Dynamic - Calculated automatically, not manually satisfied

```yaml
requirements:
  branch_size_limit:
    enabled: true
    type: dynamic
    calculator: branch_size_calculator
    scope: session
    thresholds:
      warn: 250   # Log warning (non-blocking)
      block: 400  # Block with denial message
    cache_ttl: 60  # Recalculate every 60 seconds
    approval_ttl: 3600  # 1 hour approval via `req approve`
```

### pre_commit_review (Single-Use Scope)

Requires code review before every commit.

**Scope**: single_use - Must re-satisfy before EACH commit

```yaml
requirements:
  pre_commit_review:
    enabled: true
    type: blocking
    scope: single_use
    trigger_tools:
      - tool: Bash
        command_pattern: "git\\s+(commit|cherry-pick|revert|merge)"
    message: |
      Run `/requirements-framework:pre-commit` to review your code
```

**Auto-satisfied** when you run `/requirements-framework:pre-commit`

### pre_pr_review (Single-Use Scope)

Requires comprehensive quality check before creating each PR.

```yaml
requirements:
  pre_pr_review:
    enabled: true
    type: blocking
    scope: single_use
    trigger_tools:
      - tool: Bash
        command_pattern: "gh\\s+pr\\s+create"
    message: |
      Run `/requirements-framework:quality-check` for comprehensive review
```

**Auto-satisfied** when you run `/requirements-framework:quality-check`

### codex_reviewer (AI-Powered Review)

Requires AI-powered code review before creating PRs.

```yaml
requirements:
  codex_reviewer:
    enabled: true
    type: blocking
    scope: single_use
    trigger_tools:
      - tool: Bash
        command_pattern: "gh\\s+pr\\s+create"
    message: |
      Run `/requirements-framework:codex-review` for AI-powered review
```

**Auto-satisfied** when you run `/requirements-framework:codex-review`

### Project-Specific Skills (`satisfied_by_skill`)

Connect any project skill to auto-satisfy a requirement when it completes.

**Use Case**: Projects with custom review skills (e.g., architecture review against ADRs)

```yaml
# .claude/requirements.yaml (in your project)
requirements:
  architecture_review:
    enabled: true
    type: blocking
    scope: single_use
    trigger_tools:
      - tool: Bash
        command_pattern: 'gh\s+pr\s+create'
    satisfied_by_skill: 'architecture-guardian'  # Your project skill name
    message: |
      🏗️ Run the architecture-guardian skill to review against ADRs
```

**How It Works**:
1. Define a skill in your project (`.claude/skills/architecture-guardian.md`)
2. Add `satisfied_by_skill: 'skill-name'` to your requirement config
3. When the skill completes, the requirement is automatically satisfied
4. PR creation is allowed (requirement is satisfied)

**Naming Convention**:
- Project skills: Use skill name from frontmatter (e.g., `'architecture-guardian'`)
- Plugin skills: Use namespaced format (e.g., `'requirements-framework:pre-commit'`)

### hooks.stop Configuration

Controls whether sessions can end with unsatisfied requirements.

```yaml
hooks:
  stop:
    verify_requirements: true  # Block session end if requirements unsatisfied
```

When enabled, the Stop hook prevents Claude Code sessions from ending until all session-scoped requirements are satisfied.

---

## Plugin Components

The requirements framework includes a comprehensive plugin with specialized agents, orchestrator commands, and management skills.

### Agents (10)

**Workflow Enforcement**:
- **adr-guardian** - Validates plans and code against Architecture Decision Records (BLOCKING authority)
- **codex-review-agent** - Orchestrates OpenAI Codex CLI for AI-powered code review

**Pre-Commit Review Suite** (8 specialized reviewers):
- **tool-validator** - Executes pyright/ruff/eslint to catch CI errors locally (Haiku model)
- **code-reviewer** - CLAUDE.md compliance, bug detection, code quality (Opus model, confidence ≥80)
- **silent-failure-hunter** - Error handling audit with zero tolerance for silent failures (Sonnet model)
- **test-analyzer** - Test coverage quality with CRITICAL gap detection for code without tests
- **type-design-analyzer** - Type invariants and encapsulation analysis with 4-dimensional rating
- **comment-analyzer** - Documentation accuracy and comment rot detection
- **code-simplifier** - Final code polish for clarity and maintainability (Sonnet model)
- **backward-compatibility-checker** - Schema migration detection with Alembic verification (Sonnet model)

### Commands (3)

**`/requirements-framework:pre-commit [aspects]`**

Fast pre-commit review with smart agent selection:
- **Default** (no args): tool-validator + code-reviewer + silent-failure-hunter
- **Arguments**: `tools`, `code`, `errors`, `compat`, `tests`, `types`, `comments`, `simplify`, `all`, `parallel`
- **Integrated with**: `pre_commit_review` requirement (auto-satisfies on completion)
- **Execution**: Deterministic workflow with blocking gates (tool errors stop AI review)

Examples:
```bash
/requirements-framework:pre-commit              # Fast essential checks
/requirements-framework:pre-commit tools        # Just CI tools
/requirements-framework:pre-commit all parallel # Comprehensive + fast
/requirements-framework:pre-commit tests types  # Specific aspects
```

**`/requirements-framework:quality-check [parallel]`**

Comprehensive pre-PR review with all 8 review agents:
- **Smart selection**: Conditionally runs agents based on file types (tests, types, comments, schemas)
- **Deterministic execution**: 10-step workflow with enforced order and file type detection
- **Blocking gate**: Tool-validator must pass before AI review
- **Integrated with**: `pre_pr_review` requirement (auto-satisfies on completion)

Examples:
```bash
/requirements-framework:quality-check           # Thorough sequential
/requirements-framework:quality-check parallel  # Fast comprehensive
```

**`/requirements-framework:codex-review [focus]`**

AI-powered code review using OpenAI Codex CLI:
- **Focus areas**: `security`, `performance`, `bugs`, `style`, `all` (default)
- **Autonomous agent**: Handles prerequisites, scope detection, and error recovery
- **Integrated with**: `codex_reviewer` requirement (auto-satisfies on completion)
- **Requirements**: OpenAI Codex CLI (`npm install -g @openai/codex` + `codex login`)

Examples:
```bash
/requirements-framework:codex-review            # All focus areas
/requirements-framework:codex-review security   # Security vulnerabilities
/requirements-framework:codex-review performance # Performance optimization
```

### Skills (4)
- **requirements-framework-builder** - Framework management, extension, and status checking
- **requirements-framework-development** - Framework development workflow and sync operations
- **requirements-framework-status** - Status reporting and progress tracking
- **requirements-framework-usage** - Usage help, troubleshooting, and configuration guidance

---

## Configuration System

### 3-Level Cascade

1. **Global** (`~/.claude/requirements.yaml`) - Default requirements for all projects
2. **Project** (`.claude/requirements.yaml`) - Shared team configuration (committed to repo)
3. **Local** (`.claude/requirements.local.yaml`) - Personal overrides (gitignored)

### Example: Global Config

```yaml
# ~/.claude/requirements.yaml
version: "1.0"
enabled: true

requirements:
  commit_plan:
    enabled: false  # Disabled by default - projects opt-in
    scope: session
    trigger_tools: [Edit, Write, MultiEdit]
    message: |
      📋 **No commit plan found for this session**

      Before making code changes, you should plan your commits.
    checklist:
      - "Identified the changes needed"
      - "Determined atomic commit boundaries"
      - "Created plan file"
```

### Example: Project Config

```yaml
# .claude/requirements.yaml (committed to repo)
version: "1.0"
inherit: true  # Merge with global config

requirements:
  commit_plan:
    enabled: true  # Enable for this project
    checklist:
      - "Plan created via EnterPlanMode"
      - "Reviewed relevant ADRs"
      - "TDD approach in plan"

  adr_reviewed:
    enabled: true
```

### Example: Local Override

```yaml
# .claude/requirements.local.yaml (gitignored)
requirements:
  commit_plan:
    enabled: false  # Temporarily disable for myself
```

### Logging Configuration

Configure how the hook emits JSON logs:

```yaml
logging:
  level: info               # One of: debug, info, warning, error
  destinations: [file]      # Any of: stdout, file (can list multiple)
  file: ~/.claude/requirements.log  # Optional custom log path
```

Defaults keep the existing fail-open behavior: level `error` with file logging to
`~/.claude/requirements.log` so normal runs stay quiet unless something fails.

### Hook Configuration

Configure behavior for each hook:

```yaml
hooks:
  session_start:
    inject_context: true       # ON by default - show full status at start
  stop:
    verify_requirements: true  # ON by default - enforce requirements
    verify_scopes: [session]   # Which scopes to verify (default: session only)
  session_end:
    clear_session_state: false # OFF by default - preserve state for debugging
```

To disable the Stop hook verification:

```yaml
hooks:
  stop:
    verify_requirements: false  # Turn off requirement verification at stop
```

## Session Lifecycle

The framework uses four hooks to manage the complete session lifecycle:

```
┌─────────────────────────────────────────────────────────┐
│                    SESSION LIFECYCLE                     │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  🚀 SessionStart ────────────────────────────────────►  │
│     • Clean stale sessions (prune)                      │
│     • Inject full requirement status + instructions     │
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │              WORK LOOP                          │   │
│  │  🔒 PreToolUse (Edit/Write)                     │   │
│  │  • Block if requirements not satisfied          │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
│  🛑 Stop ───────────────────────────────────────────►   │
│     • Verify all requirements satisfied (ON by default) │
│     • Block stop if incomplete (force continuation)     │
│                                                         │
│  🧹 SessionEnd ─────────────────────────────────────►   │
│     • Clean up session-specific state                   │
│     • Update registry (mark session inactive)           │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### Hook Details

| Hook | When | Can Block | Purpose |
|------|------|-----------|---------|
| SessionStart | Session starts/resumes | No | Inject context, clean stale sessions |
| PreToolUse | Before Edit/Write | Yes | Block modifications until requirements satisfied |
| Stop | Claude about to finish | Yes | Final verification before stopping |
| SessionEnd | Session ends | No | Cleanup session state |

### Stop Hook Behavior

The Stop hook prevents Claude from finishing with unsatisfied requirements:

1. **Enabled by default** - No configuration needed
2. **Checks session-scoped requirements** - Branch/permanent scopes are not verified by default
3. **Safe loop prevention** - Uses `stop_hook_active` flag to prevent infinite continuation loops
4. **Helpful messaging** - Shows which requirements need satisfaction

Example output when blocked:
```
⚠️ **Requirements not satisfied**: commit_plan

Please satisfy these requirements before finishing, or use
`req satisfy <name>` to mark them complete.
```

## Checklists Feature

Checklists provide visual reminders of important steps when requirements block your workflow.

### Adding Checklists

```yaml
requirements:
  commit_plan:
    enabled: true
    checklist:
      - "Plan created via EnterPlanMode and planning agents/skills"
      - "Atomic commits identified (from agent/skill analysis)"
      - "Reviewed relevant ADRs (in /ADR/ directory)"
      - "TDD approach implemented in todo list/plan"
      - "Linting/formatting/typecheck commands known"
```

### Checklist Display

When Claude Code is blocked, the checklist appears in the error message:

```
📋 **No commit plan found for this session**

**Checklist**:
⬜ 1. Plan created via EnterPlanMode and planning agents/skills
⬜ 2. Atomic commits identified (from agent/skill analysis)
⬜ 3. Reviewed relevant ADRs (in /ADR/ directory)
...

**Current session**: `abc12345`

💡 **To satisfy from terminal**:
```bash
req satisfy commit_plan --session abc12345
```
```

## Advanced Features

### Session Management

The framework automatically manages session state:

- **Session Registry** (`~/.claude/sessions.json`) - Tracks active Claude Code sessions
- **Auto-Detection** - CLI automatically finds the correct session
- **PID Validation** - Stale sessions are automatically cleaned up

```bash
# View all active sessions
req sessions

# View sessions for current project only
req sessions --project

# Use specific session explicitly
req satisfy commit_plan --session abc12345
```

### Scopes

Requirements can have different lifetimes:

| Scope | Behavior | Use Case |
|-------|----------|----------|
| `session` | Cleared when Claude Code session ends | Daily planning, ADR review |
| `branch` | Persists across sessions on same branch | GitHub ticket linking |
| `permanent` | Never cleared automatically | Project setup tasks |

### State Storage

State is stored in `.git/requirements/[branch].json`:

```json
{
  "version": "1.0",
  "branch": "feature/auth",
  "requirements": {
    "commit_plan": {
      "scope": "session",
      "sessions": {
        "abc12345": {
          "satisfied": true,
          "satisfied_at": 1702345678,
          "satisfied_by": "cli"
        }
      }
    }
  }
}
```

### TTL (Time-To-Live)

Requirements can expire automatically:

```bash
# Satisfy for 1 hour
req satisfy commit_plan --ttl 3600
```

## Testing

The framework includes comprehensive tests (447 tests, 100% passing):

```bash
# Run all tests
cd ~/.claude/hooks
python3 test_requirements.py

# Expected output:
# 🧪 Requirements Framework Test Suite
# ==================================================
# ...
# Results: 447/447 tests passed
```

Test categories:
- Session management (31 tests)
- Configuration loading (13 tests)
- Hook config (6 tests)
- Requirements manager (9 tests)
- CLI commands (15 tests)
- PreToolUse hook behavior (13 tests)
- SessionStart hook (5 tests)
- Stop hook (7 tests)
- SessionEnd hook (5 tests)
- Session registry removal (4 tests)
- Checklist rendering (8 tests)
- Message deduplication (13 tests)
- Logging (19 tests)

## Architecture

### Components

```
~/.claude/
├── hooks/
│   ├── check-requirements.py       # PreToolUse hook (blocks edits)
│   ├── handle-session-start.py     # SessionStart hook (context injection)
│   ├── handle-stop.py              # Stop hook (requirement verification)
│   ├── handle-session-end.py       # SessionEnd hook (cleanup)
│   ├── requirements-cli.py         # CLI tool (req command)
│   ├── test_requirements.py        # Test suite (447 tests)
│   └── lib/
│       ├── config.py               # Configuration cascade + hook config
│       ├── git_utils.py            # Git operations
│       ├── logger.py               # Structured JSON logging
│       ├── requirements.py         # Core requirements manager
│       ├── session.py              # Session tracking + registry
│       └── state_storage.py        # JSON state persistence
├── requirements.yaml               # Global configuration
└── sessions.json                   # Active session registry

<project>/.git/requirements/
└── [branch].json                   # Branch-specific state
```

### Hook Flow

```
SESSION START
─────────────
1. Claude Code session starts
   ↓
2. SessionStart hook triggered (handle-session-start.py)
   - Cleans stale sessions from registry
   - Loads configuration
   - Outputs full requirement status with instructions
   ↓
3. Context injected into Claude's context

WORK LOOP
─────────
4. Claude Code invokes Edit/Write tool
   ↓
5. PreToolUse hook triggered (check-requirements.py)
   - Loads configuration (global → project → local)
   - Gets current session ID
   - Updates session registry
   - Checks all enabled requirements
   ↓
6a. All requirements satisfied
    → Hook returns empty output
    → Edit/Write proceeds

6b. Requirement not satisfied
    → Hook returns "deny" decision
    → Shows message with checklist
    → Edit/Write blocked

SESSION END
───────────
7. Claude about to stop
   ↓
8. Stop hook triggered (handle-stop.py)
   - Checks stop_hook_active flag (prevents loops)
   - Verifies session-scoped requirements
   ↓
9a. All requirements satisfied → Stop allowed

9b. Requirements unsatisfied
    → Returns {"decision": "block", "reason": "..."}
    → Claude continues to satisfy requirements

10. Session ends (user exits, clears, etc.)
    ↓
11. SessionEnd hook triggered (handle-session-end.py)
    - Removes session from registry
    - Optionally clears session-scoped state
```

## Development

### Creating Custom Requirements

1. Add to your configuration:

```yaml
requirements:
  my_custom_requirement:
    enabled: true
    scope: session
    trigger_tools: [Edit, Write]
    message: |
      🎯 **Custom requirement not satisfied**

      Please complete [your custom step]
    checklist:
      - "Custom step 1"
      - "Custom step 2"
```

2. Satisfy it when ready:

```bash
req satisfy my_custom_requirement
```

### Adding New Features

The framework was built using TDD (Test-Driven Development):

1. Write tests first in `test_requirements.py`
2. Run tests to see failures (RED)
3. Implement the feature
4. Run tests to see passes (GREEN)
5. Refactor if needed

Example test structure:

```python
def test_my_feature(runner: TestRunner):
    """Test my new feature."""
    print("\n📦 Testing my feature...")

    # Test setup
    with tempfile.TemporaryDirectory() as tmpdir:
        # ... test code ...
        runner.test("Feature works", result == expected)
```

## Troubleshooting

### Hook Not Triggering

1. Check hooks are registered in `~/.claude/settings.local.json`:

```json
{
  "hooks": {
    "PreToolUse": "~/.claude/hooks/check-requirements.py",
    "SessionStart": "~/.claude/hooks/handle-session-start.py",
    "Stop": "~/.claude/hooks/handle-stop.py",
    "SessionEnd": "~/.claude/hooks/handle-session-end.py"
  }
}
```

2. Check the requirement is enabled:

```bash
req list
```

### Permission Override Issues

If wildcards like `Edit(*)` or `Write(*)` are in `permissions.allow`, hooks are bypassed. Remove them:

```json
{
  "permissions": {
    "allow": [
      // Remove these if present:
      // "Edit(*)",
      // "Write(*)"
    ]
  }
}
```

### Session Not Found

```bash
# Check active sessions
req sessions

# Use explicit session ID if needed
req satisfy commit_plan --session <session-id>
```

### Skip Requirements Temporarily

```bash
# Disable framework temporarily
export CLAUDE_SKIP_REQUIREMENTS=1

# Or disable in config
# .claude/requirements.local.yaml
enabled: false
```

## Examples

See the `examples/` directory for:
- `global-requirements.yaml` - Global configuration template
- `project-requirements.yaml` - Project-specific configuration example

## What's New in v2.3

### 🎯 Project-Specific Skill Requirements (`satisfied_by_skill`)

**Feature**: Connect any project skill to auto-satisfy a requirement when it completes.

Projects can now define custom skills that automatically satisfy requirements, enabling:
- Architecture review skills that gate PR creation
- Custom code review workflows per project
- ADR compliance checks specific to each codebase

**How to Use**:
```yaml
# .claude/requirements.yaml
requirements:
  architecture_review:
    enabled: true
    type: blocking
    scope: single_use
    trigger_tools:
      - tool: Bash
        command_pattern: 'gh\s+pr\s+create'
    satisfied_by_skill: 'architecture-guardian'  # NEW FIELD
    message: |
      🏗️ Run the architecture-guardian skill before creating PR
```

**Workflow**:
1. User exits plan mode → Shows proactive reminder
2. User runs `/architecture-guardian` skill
3. `auto-satisfy-skills.py` hook fires → Auto-satisfies `architecture_review`
4. User runs `gh pr create` → Allowed (requirement satisfied)
5. `clear-single-use.py` fires → Clears requirement for next PR

**Configuration-Driven**: No framework changes needed for new skills. Just add `satisfied_by_skill` to your requirement config.

**Test Coverage**: 454 tests passing (7 new tests for this feature)

---

## What's New in v2.2

### Full Session Lifecycle Hooks

The framework now supports the complete Claude Code session lifecycle with four hooks:

**🚀 SessionStart Hook**
- Fires when Claude Code session starts or resumes
- Injects full requirement status into context automatically
- Cleans stale sessions from registry
- Configurable via `hooks.session_start.inject_context`

**🛑 Stop Hook (Enabled by Default)**
- Prevents Claude from finishing with unsatisfied requirements
- **Opt-out design** - works out of the box
- Safe infinite loop prevention via `stop_hook_active` flag
- Configurable via `hooks.stop.verify_requirements`

**🧹 SessionEnd Hook**
- Fires when session ends (exit, clear, logout)
- Removes session from registry
- Optional session state cleanup (disabled by default)

**Test Coverage**: Comprehensive test suite (447 total tests, 100% passing)

---

## What's New in v2.1

### 🚫 Message Deduplication

**Problem Solved**: When Claude makes parallel Write/Edit calls (e.g., modifying 5 files simultaneously), the hook previously executed 5 times, showing identical blocking messages 5-12 times. This created overwhelming walls of text.

**Solution**: TTL-based deduplication cache that:
- Shows full blocking message on **first occurrence**
- Shows minimal "⏸️ Requirement `name` not satisfied (waiting...)" for subsequent blocks within 5 seconds
- Automatically expires to show updated messages when you retry

**Impact**: 90% reduction in message output, ~5000 tokens saved per blocking scenario

**Debug Mode**: Set `export CLAUDE_DEDUP_DEBUG=1` to see cache behavior in stderr

**Implementation**: Cross-platform (Unix + Windows), atomic file writes, fail-open design

---

## Troubleshooting

### Installation Issues

**Problem**: Hooks not firing after installation

1. **Check hook registration format**:
   ```bash
   cat ~/.claude/settings.local.json
   ```
   Hooks should use the array-of-matchers format:
   ```json
   {
     "hooks": {
       "PreToolUse": [{
         "matcher": "*",
         "hooks": [{"type": "command", "command": "~/.claude/hooks/check-requirements.py"}]
       }]
     }
   }
   ```

2. **Verify hooks are executable**:
   ```bash
   ls -l ~/.claude/hooks/*.py
   ```
   If not executable: `chmod +x ~/.claude/hooks/*.py`

3. **Test hook manually**:
   ```bash
   echo '{"tool_name":"Read"}' | python3 ~/.claude/hooks/check-requirements.py
   ```
   Should return immediately with no errors.

4. **Re-run installation**:
   ```bash
   cd ~/tools/claude-requirements-framework
   ./install.sh
   ```

**Problem**: `req` command not found

- Add `~/.local/bin` to your PATH:
  ```bash
  echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc  # or ~/.zshrc
  source ~/.bashrc
  ```

### Common Errors

**Problem**: "Unknown requirement: xyz"

**Solution**: The requirement doesn't exist in your configuration. Check:

1. **Typo in requirement name?**
   - Use `req status` to see available requirements
   - The error message will show "Did you mean?" suggestions

2. **Requirement not defined?**
   - Add it to:
     - Global: `~/.claude/requirements.yaml`
     - Project: `.claude/requirements.yaml`
     - Local: `.claude/requirements.local.yaml`
   - Or run `req init` to set up project requirements

**Problem**: "No active Claude session detected"

This means `req satisfy` couldn't find your Claude Code session. Solutions:

1. **Use explicit session ID** (recommended):
   ```bash
   req satisfy commit_plan --session abc12345
   ```
   Find your session ID in the blocking message or via `req sessions`.

2. **Use branch-level satisfaction** (satisfies all sessions on the branch):
   ```bash
   req satisfy commit_plan --branch
   ```

3. **Set CLAUDE_SESSION_ID environment variable**:
   ```bash
   export CLAUDE_SESSION_ID=abc12345
   req satisfy commit_plan
   ```

**Problem**: Requirements satisfied but still blocking

1. **Check scope mismatch**:
   - Requirement might be `branch` scope but you satisfied it with `session` scope
   - Use `req status` to see the scope
   - Satisfy with matching scope: `req satisfy <name> --branch` or `req satisfy <name> --session <id>`

2. **Check session ID**:
   - You might be satisfying a different session
   - Use `req sessions` to list active sessions
   - Use `req status` to see current session

3. **TTL expired**:
   - Dynamic requirements have approval TTLs (default 5 minutes)
   - Re-satisfy the requirement: `req satisfy <name>`

**Problem**: Framework blocking when it shouldn't

1. **Disable temporarily**:
   ```bash
   export CLAUDE_SKIP_REQUIREMENTS=1
   # Work normally
   unset CLAUDE_SKIP_REQUIREMENTS
   ```

2. **Disable specific requirement**:
   ```bash
   req config <requirement_name> --disable --local --yes
   ```

3. **Check configuration**:
   ```bash
   req config <requirement_name>  # Show current config
   req doctor  # Full diagnostic
   ```

### Sync Issues (Development)

**Problem**: Changes not taking effect

1. **Deploy changes**:
   ```bash
   cd ~/tools/claude-requirements-framework
   ./sync.sh deploy
   ```

2. **Check sync status**:
   ```bash
   ./sync.sh status  # Shows files that differ
   ./sync.sh diff     # Shows actual differences
   ```

3. **Verify deployment**:
   ```bash
   python3 ~/.claude/hooks/test_requirements.py
   ```

**Problem**: Lost work after sync

- The repository is the source of truth
- Always run `./sync.sh status` before committing
- If you edited deployed files, copy those changes into the repo before deploying

### Performance Issues

**Problem**: Hooks slow down file operations

1. **Check calculation cache**:
   - Dynamic requirements cache results for 30 seconds
   - Clear cache if stale: `rm ~/tmp/claude-req-calc-cache-*.json`

2. **Check message dedup cache**:
   - Enable debug mode to see cache behavior:
     ```bash
     export CLAUDE_DEDUP_DEBUG=1
     ```

3. **Disable expensive requirements**:
   ```bash
   req config branch_size_limit --disable --local --yes
   ```

### Getting Help

1. **Run diagnostics**:
   ```bash
   req doctor
   ```

2. **Check logs**:
   ```bash
   tail -f ~/.claude/requirements.log
   ```

3. **Test manually**:
   ```bash
   python3 ~/.claude/hooks/test_requirements.py
   ```

4. **Report issues**: https://github.com/anthropics/claude-code/issues

---

## Development Workflow

### Keeping Repository and Deployed Installation in Sync

The framework exists in two locations:
- **Repository**: `~/tools/claude-requirements-framework/` (source of truth, git-controlled)
- **Deployed**: `~/.claude/hooks/` (active installation, where Claude Code loads hooks)

Use the `sync.sh` script to keep them in sync:

```bash
cd ~/tools/claude-requirements-framework

# Check sync status (run this FIRST before committing!)
./sync.sh status

# Deploy changes from repo → ~/.claude/hooks
./sync.sh deploy

# See detailed differences
./sync.sh diff
```

### Standard Development Workflow

```bash
# 1. Make changes in repository
vim hooks/lib/config.py

# 2. Deploy to test
./sync.sh deploy

# 3. Run tests
python3 ~/.claude/hooks/test_requirements.py

# 4. Commit when tests pass
git add .
git commit -m "feat: Add feature"
git push origin master
```

### Quick Fix Workflow (Claude-Driven)

```bash
# 1. Claude edits deployed files (in ~/.claude/hooks/)
# 2. Copy changes into repository (repeat for each file changed)
cd ~/tools/claude-requirements-framework
cp ~/.claude/hooks/check-requirements.py hooks/check-requirements.py

# 3. Deploy from repo to keep source of truth
./sync.sh deploy

# 4. Commit
git add .
git commit -m "fix: Bug description"
git push origin master
```

**Important**: Always run `./sync.sh status` before committing to ensure repo and deployed locations match!

See [DEVELOPMENT.md](DEVELOPMENT.md) for detailed development workflows, TDD practices, and troubleshooting guide.

### Architecture Decision Records (ADRs)

Important architectural decisions are documented in `docs/adr/`:

- **ADR-001**: Remove main/master branch skip - Requirements now enforced on all branches
- **ADR-002**: Use Claude Code's native session_id - Better session correlation
- **ADR-003**: Dynamic sync file discovery - sync.sh auto-discovers new files

## Contributing

1. Fork the repository
2. Create a feature branch
3. Write tests for your changes (TDD)
4. Deploy and test: `./sync.sh deploy && python3 ~/.claude/hooks/test_requirements.py`
5. Ensure sync status is clean: `./sync.sh status`
6. Commit and submit a pull request

## License

MIT License - See LICENSE file for details

## Credits

Built with Test-Driven Development (TDD) methodology for reliability and maintainability.

## Support

For issues, questions, or contributions, please open an issue on GitHub.
