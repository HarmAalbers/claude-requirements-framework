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
- **🧪 Comprehensive Tests**: 147 passing tests with full TDD coverage
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
3. Register all four hooks (PreToolUse, SessionStart, Stop, SessionEnd) in your Claude Code settings

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
```

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

The framework includes comprehensive tests (147 tests, 100% passing):

```bash
# Run all tests
cd ~/.claude/hooks
python3 test_requirements.py

# Expected output:
# 🧪 Requirements Framework Test Suite
# ==================================================
# ...
# Results: 147/147 tests passed
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
│   ├── test_requirements.py        # Test suite (148 tests)
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

**Test Coverage**: 27 new tests (147 total after removing obsolete main/master skip test)

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

# Pull changes from ~/.claude/hooks → repo
./sync.sh pull

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
# 2. Pull changes to repository
cd ~/tools/claude-requirements-framework
./sync.sh pull

# 3. Commit
git add .
git commit -m "fix: Bug description"
git push origin master
```

**Important**: Always run `./sync.sh status` before committing to ensure you have the latest changes from both locations!

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
