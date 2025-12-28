# Requirements Framework

A powerful, standalone requirements management system for Claude Code that enforces workflow policies before code modifications.

## Overview

The Requirements Framework allows you to define and enforce workflow requirements (like commit planning, ADR reviews, GitHub ticket linking) before Claude can modify files in your projects.

**Key Features:**
- ✅ Session-scoped, branch-scoped, or permanent requirements
- ✅ Zero external dependencies (pure Python stdlib)
- ✅ Per-project configuration (versioned and code-reviewed)
- ✅ Local state management (never committed)
- ✅ Fail-open design (errors don't block work)
- ✅ Plan file whitelisting (no chicken-and-egg problems)

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   Claude Code Session                    │
│                                                           │
│  ┌─────────────┐    ┌──────────────────────────────┐   │
│  │   Edit/     │───▶│  PreToolUse Hook             │   │
│  │   Write/    │    │  (check-requirements.py)     │   │
│  │   MultiEdit │    └──────────────┬───────────────┘   │
│  └─────────────┘                   │                    │
│                                     ▼                    │
│                    ┌────────────────────────────┐       │
│                    │  Requirements Manager      │       │
│                    │  (~/.claude/hooks/lib/)    │       │
│                    └──────┬──────────────┬──────┘       │
│                           │              │               │
│             ┌─────────────▼───┐    ┌────▼──────────┐   │
│             │  Local State    │    │  Project      │   │
│             │  (.git/req/)    │    │  Config       │   │
│             └─────────────────┘    │  (.claude/)   │   │
│                                     └───────────────┘   │
└─────────────────────────────────────────────────────────┘
```

## Quick Start

### 1. Check Status

```bash
cd /your/project
req status
```

### 2. Satisfy Requirement

```bash
req satisfy commit_plan
```

### 3. Continue Working

Claude can now edit files - requirement is satisfied for this session.

## File Structure

```
~/.claude/hooks/
├── check-requirements.py        # PreToolUse hook (entry point)
├── requirements-cli.py           # CLI tool (req command)
└── lib/                          # Framework libraries
    ├── __init__.py
    ├── requirements.py           # Core BranchRequirements class
    ├── config.py                 # Configuration loader
    ├── state_storage.py          # State file I/O
    ├── git_utils.py              # Git operations
    └── session.py                # Session ID management
```

## Per-Project Setup

### Using `req init`

The `req init` command provides an interactive wizard to set up requirements for your project:

```bash
# Interactive wizard (recommended for first-time setup)
cd /your/project
req init

# Non-interactive mode (for scripts/automation)
req init --yes

# Choose a specific preset
req init --preset strict    # commit_plan + protected_branch
req init --preset relaxed   # commit_plan only (default)
req init --preset minimal   # framework enabled, no requirements

# Create local config only (personal overrides)
req init --local

# Preview config without writing files
req init --preview
```

### Presets

| Preset | Requirements | Use Case |
|--------|--------------|----------|
| `advanced` | All 7 requirements (blocking, guard, dynamic, single-use) | Global config showcase (recommended for ~/.claude/) |
| `inherit` | Empty, sets inherit: true | Projects using global config (recommended) |
| `relaxed` | commit_plan only (session scope) | Standalone projects, trying the framework |
| `strict` | commit_plan + protected_branch guard | Teams with strict workflow policies |
| `minimal` | Framework enabled, no requirements | "I'll configure it myself" |

**Context-Aware Defaults:**
- Running `req init` in `~/.claude/` → Defaults to `advanced`
- Running in project with global config → Defaults to `inherit`
- Running in project without global → Defaults to `relaxed`

### Automatic Detection

When you start a Claude Code session in a project without `.claude/requirements.yaml`, the SessionStart hook will suggest:

```
💡 **No requirements config found for this project**

To set up the requirements framework, run:
  `req init`

Or create `.claude/requirements.yaml` manually.
See `req init --help` for options.
```

This only appears on fresh session startup, not on resume/compact.

### Interactive Flow

Example of the interactive wizard:

```
$ req init

🚀 Requirements Framework Setup
──────────────────────────────────────────────────

Detecting project:
  ✓ Git repository at /Users/harm/my-project
  ○ .claude/ directory will be created

Which configuration file to create?
  > Project config (.claude/requirements.yaml) - shared with team
    Local config (.claude/requirements.local.yaml) - personal only

Choose a preset profile:
  > relaxed - Light touch: commit_plan only (recommended)
    strict - Full enforcement: commit_plan + protected_branch
    minimal - Framework enabled, no requirements (configure later)

Preview:
──────────────────────────────────────────────────
version: "1.0"
enabled: true
requirements:
  commit_plan:
    enabled: true
    scope: session
    ...

Create requirements.yaml? (Y/n): y

✅ Created project config (relaxed preset)
   .claude/requirements.yaml

💡 Next steps:
   • Run 'req status' to see your requirements
   • Make changes - you'll be prompted to satisfy requirements
   • Edit requirements.yaml to customize
```

## Configuration

### Global Defaults (`~/.claude/requirements.yaml`)

```yaml
version: "1.0"
enabled: true

requirements:
  commit_plan:
    enabled: false  # Disabled globally, projects opt-in
    type: blocking
    scope: session
    trigger_tools: [Edit, Write, MultiEdit]
    message: |
      📋 No commit plan found for this session
      Create a plan before making changes.
```

### Project Config (`.claude/requirements.yaml`)

```yaml
version: "1.0"
inherit: true
enabled: true

requirements:
  commit_plan:
    enabled: true  # Enable for this project
    checklist:  # NEW in v2.0 - Optional reminder checklist
      - "Plan created via EnterPlanMode"
      - "Atomic commits identified"
      - "TDD approach documented"
      - "Linting/typecheck commands known"
```

## Checklist Feature (v2.0)

### Overview

Requirements can now include optional **checklists** that display as visual reminders when a requirement blocks Claude.

### Checklist Display

When Claude is blocked, the checklist appears in the error message:

```
📋 **No commit plan found for this session**

Before making code changes, you should plan your commits.

**Checklist**:
⬜ 1. Plan created via EnterPlanMode
⬜ 2. Atomic commits identified
⬜ 3. Reviewed relevant ADRs
⬜ 4. TDD approach documented

**Current session**: `abc12345`

💡 **To satisfy from terminal**:
```bash
req satisfy commit_plan --session abc12345
```
```

### Adding Checklists

Add a `checklist` array to any requirement:

```yaml
requirements:
  commit_plan:
    enabled: true
    checklist:
      - "First item"
      - "Second item"
      - "Third item"
```

### Best Practices

- **Keep items concise**: 5-10 words per item
- **Make actionable**: Each item should be verifiable
- **Order logically**: Steps should flow naturally
- **Limit quantity**: 5-10 items maximum
- **Project-specific**: Customize for team workflows

### Configuration Inheritance

Checklists follow the same cascade as other config:
- Global config defines default checklist
- Project config can override entire checklist
- Local config can override again
- Set `checklist: []` to remove inherited checklist

## Key Components

### 1. Session Management (`lib/session.py`)
- Generates stable session IDs using parent PID
- Registry tracks active sessions per project/branch
- Auto-cleanup of stale sessions

### 2. State Storage (`lib/state_storage.py`)
- State files in `.git/requirements/` (gitignored)
- Atomic writes with file locking
- Per-branch, per-session tracking

### 3. Requirements Manager (`lib/requirements.py`)
- `is_satisfied()` - Check if requirement met (with TTL support)
- `satisfy()` - Mark requirement satisfied
- `clear()` - Clear requirement
- `cleanup_stale_branches()` - Remove old state

### 4. PreToolUse Hook (`check-requirements.py`)
- Intercepts Edit/Write/MultiEdit operations
- Checks requirements before allowing modifications
- **CRITICAL**: Whitelists plan files to prevent chicken-and-egg problems
- Fail-open design (errors logged but don't block)

## Plan File Whitelisting

**Problem**: Claude needs to write plan files, but hook blocks Write operations until `commit_plan` is satisfied.

**Solution**: The `should_skip_plan_file()` function automatically whitelists:
- `~/.claude/plans/*` - Global plan directory
- `{project}/.claude/plans/*` - Project plan directories
- Any path containing `/.claude/plans/`

**Why This Matters**:
- Plans can be created BEFORE satisfying `commit_plan`
- No chicken-and-egg blocking
- Plan mode works seamlessly with requirements framework

## CLI Commands

```bash
# Show status
req status

# Satisfy requirement
req satisfy commit_plan
req satisfy commit_plan --session abc123  # Explicit session

# Satisfy multiple at once
req satisfy commit_plan --session abc123 && req satisfy adr_reviewed --session abc123

# Clear requirement
req clear commit_plan
req clear --all

# List tracked branches
req list

# List active sessions
req sessions

# Cleanup stale state
req prune
```

## Scope Types

| Scope | Duration | Use Case |
|-------|----------|----------|
| **session** | Current Claude session only | Commit planning (fresh each session) |
| **branch** | Until branch deleted | GitHub ticket (once per feature) |
| **permanent** | Forever (until cleared) | One-time setup tasks |

## Workflow Example

```bash
# 1. Start work on feature branch
git checkout -b feature/add-auth

# 2. Start Claude Code
claude

# 3. Claude tries to edit file
# → Hook blocks: "commit_plan not satisfied"

# 4. User creates plan (satisfies requirement)
req satisfy commit_plan

# 5. Claude can now edit files
# → Hook allows edits (requirement satisfied)

# 6. Continue working...
# All edits proceed without prompts

# 7. New session tomorrow
claude
# → Hook blocks again (session-scoped requirement expired)
```

## Error Handling

The framework uses **fail-open** design:
- Syntax errors → Log error, allow operation
- Config errors → Log error, allow operation
- Timeout → Log error, allow operation
- Corrupted state → Rebuild state, allow operation

**Errors are logged to**: `~/.claude/requirements-errors.log`

## Permission Precedence

**IMPORTANT**: Claude Code's permission system has precedence:

```
permissions.allow > hooks > user approval
```

If you have wildcard permissions like `Edit(*)` or `Write(*)` in `~/.claude/settings.local.json`, they will **bypass the hook entirely**.

**Solution**: Remove wildcard permissions from `permissions.allow` if you want hooks to run.

## Testing

### Test Hook Manually

```bash
# Test with plan file (should skip)
echo '{"tool_name":"Write","tool_input":{"file_path":"~/.claude/plans/test.md"}}' \
  | python3 ~/.claude/hooks/check-requirements.py

# Test with regular file (should check requirements)
echo '{"tool_name":"Write","tool_input":{"file_path":"/project/src/index.ts"}}' \
  | python3 ~/.claude/hooks/check-requirements.py
```

### Test CLI

```bash
# Test in project directory
cd /your/project
req status
req satisfy test_req
req status  # Should show satisfied
```

## Troubleshooting

### Requirements Not Blocking

1. Check hook is registered: `cat ~/.claude/settings.json | grep check-requirements`
2. Check no wildcard permissions: `cat ~/.claude/settings.local.json | grep "Edit(\*)\|Write(\*)"`
3. Check project has config: `ls .claude/requirements.yaml`
4. Check branch is not main/master: `git branch --show-current`
5. Check errors: `tail ~/.claude/requirements-errors.log`

### Plan Files Still Blocked

1. Verify path contains `.claude/plans/`: `echo "/path/to/file"`
2. Test whitelisting: `python3 -c "from check-requirements import should_skip_plan_file; print(should_skip_plan_file('/your/path'))"`
3. Check hook syntax: `python3 -m py_compile ~/.claude/hooks/check-requirements.py`

### Session Not Found

1. Check session registry: `req sessions`
2. Use explicit session: `req satisfy commit_plan --session <id>`
3. Hook updates registry before checking requirements (automatic bootstrap)

## Advanced Features

### Auto-Satisfy (Phase 2 - Not Yet Implemented)

Automatically satisfy requirements based on patterns:

```yaml
requirements:
  github_ticket:
    enabled: true
    auto_satisfy:
      - type: branch_name_pattern
        pattern: '(\d+)-'
        extract: ticket
        prefix: '#'
```

Branch `feature/1234-auth` would auto-extract ticket `#1234`.

### Requirement Dependencies (Phase 4 - Future)

```yaml
requirements:
  tests_passing:
    enabled: true
    depends_on: [commit_plan]
```

## Design Principles

1. **Framework in `~/.claude`** - User-level installation, not per-project
2. **Projects opt-in via config** - Minimal footprint, versioned config
3. **State is local** - Never committed, per-branch tracking
4. **Zero dependencies** - Pure stdlib (PyYAML optional)
5. **Fail-open** - Errors don't block work
6. **Plan files whitelisted** - No chicken-and-egg problems

## Version History

- **v1.0** - Initial MVP with commit_plan requirement
- **v1.1** - Session registry and auto-detection
- **v1.2** - Enhanced error messages with session context
- **v1.3** - Permission bypass fix and session bootstrap fix
- **v1.4** - **Plan file whitelisting** (critical fix)

## Contributing

Framework code lives in `~/.claude/hooks/`. To update:

1. Modify Python files in `~/.claude/hooks/` or `~/.claude/hooks/lib/`
2. Test with `python3 -m py_compile <file>`
3. Test manually with hook invocation
4. Update documentation in this README
5. Update plan in `~/.claude/plans/unified-requirements-framework-v2.md`

## Links

- **Plan**: `~/.claude/plans/unified-requirements-framework-v2.md`
- **Progress**: `~/.claude/requirements-framework-progress.json`
- **Error Log**: `~/.claude/requirements-errors.log`
- **Session Registry**: `~/.claude/sessions.json`

---

**Built with ❤️ for better Claude Code workflows**
