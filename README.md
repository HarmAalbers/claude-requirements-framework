# Claude Code Requirements Framework

A powerful hook-based system for enforcing development workflow requirements in Claude Code. Ensures critical steps like commit planning, ADR review, and test-driven development are completed before code modifications.

## Features

- **🔒 PreToolUse Hook**: Blocks file modifications until requirements are satisfied
- **📋 Customizable Checklists**: Display reminder checklists in requirement blocker messages
- **🎯 Session & Branch Scoping**: Requirements can be session-specific, branch-specific, or permanent
- **⚡ CLI Tool**: Simple `req` command for managing requirements
- **🔄 Session Auto-Detection**: Automatically finds the correct session without manual configuration
- **🧪 Comprehensive Tests**: 89 passing tests with full TDD coverage
- **📦 Project Inheritance**: Cascade configuration from global → project → local

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
3. Register the PreToolUse hook in your Claude Code settings

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

The framework includes comprehensive tests (89 tests, 100% passing):

```bash
# Run all tests
cd ~/.claude/hooks
python3 test_requirements.py

# Expected output:
# 🧪 Requirements Framework Test Suite
# ==================================================
# ...
# Results: 89/89 tests passed
```

Test categories:
- Session management (31 tests)
- Configuration loading (13 tests)
- Requirements manager (9 tests)
- CLI commands (15 tests)
- Hook behavior (13 tests)
- Checklist rendering (8 tests)

## Architecture

### Components

```
~/.claude/
├── hooks/
│   ├── check-requirements.py       # PreToolUse hook (blocks edits)
│   ├── requirements-cli.py         # CLI tool (req command)
│   ├── test_requirements.py        # Test suite
│   └── lib/
│       ├── config.py               # Configuration cascade
│       ├── git_utils.py            # Git operations
│       ├── requirements.py         # Core requirements manager
│       ├── session.py              # Session tracking
│       └── state_storage.py        # JSON state persistence
├── requirements.yaml               # Global configuration
└── sessions.json                   # Active session registry

<project>/.git/requirements/
└── [branch].json                   # Branch-specific state
```

### Hook Flow

```
1. Claude Code invokes Edit/Write tool
   ↓
2. PreToolUse hook triggered
   ↓
3. check-requirements.py runs:
   - Loads configuration (global → project → local)
   - Gets current session ID
   - Updates session registry
   - Checks all enabled requirements
   ↓
4a. All requirements satisfied
    → Hook returns empty output
    → Edit/Write proceeds

4b. Requirement not satisfied
    → Hook returns "deny" decision
    → Shows message with checklist
    → Edit/Write blocked
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

1. Check hook is registered in `~/.claude/settings.local.json`:

```json
{
  "hooks": {
    "PreToolUse": "~/.claude/hooks/check-requirements.py"
  }
}
```

2. Verify you're not on `main`/`master` branch (skipped by design)

3. Check the requirement is enabled:

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

## Contributing

1. Fork the repository
2. Create a feature branch
3. Write tests for your changes (TDD)
4. Implement your feature
5. Ensure all tests pass
6. Submit a pull request

## License

MIT License - See LICENSE file for details

## Credits

Built with Test-Driven Development (TDD) methodology for reliability and maintainability.

## Support

For issues, questions, or contributions, please open an issue on GitHub.
