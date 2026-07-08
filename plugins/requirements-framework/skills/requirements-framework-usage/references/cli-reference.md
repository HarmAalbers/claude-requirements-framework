# CLI Command Reference

Complete reference for the `req` command-line tool. Verified against `hooks/requirements-cli.py`.

> **Who runs what**: `req satisfy` / `req clear` are **user** actions — they represent a human's approval of a gate. `req pause` / `req resume` and read-only commands (`req status`, `req list`, `req doctor`, …) are runnable by Claude.

## Command Overview

| Command | Purpose | Common Flags |
|---------|---------|--------------|
| `req status` | Show requirement status | `--verbose`, `--session`, `--branch`, `--summary`, `--timing` |
| `req satisfy <name>...` | Mark requirement(s) satisfied (alias: `req approve`) | `--session`, `--branch`, `--metadata` |
| `req clear [name]` | Clear a requirement | `--all`, `--session`, `--branch` |
| `req pause` | Pause blocking gates for this session | `--session`, `--reason` |
| `req resume` | Resume blocking gates for this session | `--session` |
| `req list` | List tracked branches | - |
| `req sessions` | View active sessions | `--project` |
| `req init` | Initialize project config | `--preset`, `--yes`, `--project`, `--local`, `--force`, `--preview` |
| `req config` | View/modify configuration | `--enable`, `--disable`, `--scope`, `--set`, `--message`, `--sources`, `--project`, `--local`, `--yes` |
| `req enable [name]` | Enable the framework | - |
| `req disable [name]` | Disable the framework | - |
| `req doctor` | Comprehensive diagnostics | `--verbose`, `--json`, `--ci`, `--repo` |
| `req verify` | Verify installation | `--ci`, `--repo` |
| `req prune` | Clean stale state | - |
| `req logging` | Configure logging | `--level`, `--destinations`, `--file`, `--project`, `--local`, `--yes` |
| `req learning ...` | Session learning system | subcommands: `list`, `stats`, `rollback`, `disable` |
| `req upgrade ...` | Cross-project feature upgrade | subcommands: `scan`, `status`, `recommend`, `apply` |
| `req messages ...` | Externalized message files | subcommands: `validate`, `list` |
| `req wip ...` | WIP project tracking | subcommands: `list`, `status`, `set`, `clean`, `summary` |
| `req budget ...` | Token/cost budget reporting | subcommands: `status`, `tail`, `warn-if-over` |

---

## req status

Show current requirement status for the session/branch.

```bash
req status                    # Default view
req status --verbose          # All sessions + all requirements
req status --summary          # One-line summary only
req status --timing           # Detailed timing breakdown
req status --session abc123   # Specific session (8-char ID)
req status --branch feat/x    # Specific branch
```

**Output includes**:
- Satisfied/unsatisfied requirements
- Session ID and project path
- Scope information (session/branch/permanent/single_use)

---

## req satisfy (alias: req approve)

Mark one or more requirements as satisfied. Accepts multiple names. `req approve` is an alias with identical semantics (reads more naturally for dynamic requirements like `branch_size_limit`).

> This is a **user** action.

```bash
req satisfy plan_validated                     # Basic usage
req satisfy plan_validated pr_reviewed         # Satisfy several at once
req satisfy plan_validated --session abc123    # Explicit session
req satisfy plan_validated --metadata '{"k":"v"}'  # Attach JSON metadata
req approve branch_size_limit                  # Alias, e.g. for a dynamic gate
```

**Flags**:
- `--session <id>` - Specify session ID (auto-detected if omitted)
- `--branch <name>` - Target branch (default: current)
- `--metadata <json>` - Attach JSON metadata to the satisfaction

There is **no `--ttl` flag**. Time-to-live for dynamic/approval requirements is configured per-requirement via the `approval_ttl` attribute in YAML, not on the command line.

---

## req clear

Clear a satisfied requirement. The requirement name is optional when `--all` is given.

> This is a **user** action.

```bash
req clear plan_validated                    # Clear one requirement
req clear --all                             # Clear all requirements
req clear plan_validated --session abc123   # Explicit session
```

**Flags**: `--all`, `--session <id>`, `--branch <name>`

---

## req pause / req resume

Pause (and later resume) the framework's blocking gates for the current session only. Paused gates auto-resume at session end. Claude may run these (unlike `req satisfy`).

```bash
req pause                       # Pause blocking gates this session
req pause --reason "hotfix"     # Pause with a note
req resume                      # Undo the pause
```

**Flags**: `--session <id>`, and for pause `--reason <text>`.

---

## req list

List tracked branches (branches that have requirement state on disk).

```bash
req list
```

---

## req sessions

View active Claude Code sessions.

```bash
req sessions              # All active sessions
req sessions --project    # Current project only
```

**Output includes**: session ID, project path, branch name, PID, start time. The registry lives at `~/.claude/sessions.json`.

---

## req init

Initialize requirements configuration for a project. **By default this writes the local, gitignored `.claude/requirements.local.yaml`**; pass `--project` to write the version-controlled `.claude/requirements.yaml`.

```bash
req init                     # Interactive, writes local config (default)
req init --preset strict     # Use a preset (non-interactive)
req init --yes               # Non-interactive with defaults
req init --project           # Write version-controlled requirements.yaml
req init --local             # Write local requirements.local.yaml (default)
req init --preview           # Preview changes without writing (alias: --dry-run)
req init --force             # Overwrite existing config
```

**Presets**: `strict`, `relaxed`, `minimal`, `advanced`, `inherit`.

---

## req config

View and modify requirement configuration.

### View

```bash
req config                    # View all requirements
req config plan_validated     # View a specific requirement
req config --sources          # Show which cascade layer set each value
```

### Modify

```bash
# Toggle a requirement
req config plan_validated --enable
req config plan_validated --disable

# Change scope
req config plan_validated --scope branch      # session | branch | permanent | single_use

# Update message
req config plan_validated --message "New message text"

# Set arbitrary fields (auto-parses JSON where possible)
req config plan_validated --set adr_path=/custom/path
req config branch_size_limit --set threshold=500
req config plan_validated --set metadata='{"key":"value"}'   # --set is repeatable
```

**Flags**: `--enable`, `--disable`, `--scope <scope>`, `--message <text>`, `--set KEY=VALUE` (repeatable), `--sources`, `--project`, `--local`, `--yes`.

---

## req enable / req disable

Enable or disable the requirements framework. The requirement-name positional is accepted but reserved for future per-requirement use — to toggle a single requirement, use `req config <name> --enable|--disable`.

```bash
req enable
req disable
```

---

## req doctor

Comprehensive diagnostics for the framework installation. Hook registration is **plugin-owned** — doctor validates `hooks.json` and the scripts it registers via `${CLAUDE_PLUGIN_ROOT}` (there is no `~/.claude/hooks` deploy or `~/.claude/settings.json` hooks block to check).

```bash
req doctor                # Default
req doctor --verbose      # Show all checks including passing ones
req doctor --json         # Machine-readable output
req doctor --ci           # CI mode: validate plugin hooks only, skip local config checks
req doctor --repo <path>  # Point at a specific hooks repo (auto-detected otherwise)
```

**Checks**:
1. Python version (minimum 3.9)
2. PyYAML availability
3. Plugin hook integrity (`hooks.json` + registered scripts)
4. `req` on PATH and callable
5. Plugin installation

---

## req verify

Verify the framework installation is working correctly.

```bash
req verify                # Full verification
req verify --ci           # CI mode: validate plugin hooks only
req verify --repo <path>  # Point at a specific hooks repo
```

---

## req prune

Clean up stale session and branch state.

```bash
req prune
```

---

## req logging

Configure logging settings. Writes to the local config by default.

```bash
req logging                                    # Show current config
req logging --level debug                      # Set log level
req logging --level debug --local              # For current project only
req logging --destinations file stdout         # Log to file and stdout
req logging --file /custom/path.log            # Custom log file path
```

**Log levels**: debug, info, warning, error.
**Destinations**: file, stdout, stderr.
**Flags**: `--level/-l`, `--destinations/-d`, `--file/-f`, `--project`, `--local` (default), `--yes/-y`.
**Default log file**: `~/.claude/requirements.log`.

---

## req learning

Manage the session learning system.

```bash
req learning list             # Show recent learning updates
req learning list --count 20  # Show more
req learning stats            # Show learning statistics
req learning rollback 3       # Roll back update #3
req learning disable          # Disable learning for this project
```

---

## req upgrade

Cross-project feature upgrade discovery and adoption.

```bash
req upgrade scan                   # Scan machine for framework projects
req upgrade status                 # Feature status for current project
req upgrade status --all           # All tracked projects (brief)
req upgrade recommend              # YAML snippets for missing features
req upgrade recommend --feature X  # Snippet for a specific feature
req upgrade apply --feature X      # Apply a feature to a config file
req upgrade apply --dry-run        # Show what would be added
```

---

## req messages

Manage externalized message files (ADR-011).

```bash
req messages validate         # Validate all message files
req messages validate --fix   # Generate missing files from templates
req messages list             # List loaded files and their cascade sources
```

---

## req wip

WIP (work-in-progress) project tracking.

```bash
req wip list                  # WIP dashboard
req wip list --status wip     # Filter by status (wip|done|paused|todo)
req wip status                # Current branch details
req wip set done              # Set branch status
req wip clean                 # Remove done entries
req wip summary "text..."     # Set/update the branch summary
```

---

## req budget

Token/cost budget reporting.

```bash
req budget status             # Current month budget status
req budget tail               # Recent budget log entries
req budget warn-if-over       # Non-zero exit if over budget (for scripting)
```

---

## Session ID Auto-Detection

Most commands auto-detect the correct session ID based on:
1. Current working directory
2. Active Claude Code process (PID)
3. Session registry (`~/.claude/sessions.json`)

Use `--session <id>` (8-char ID) when:
- Running from outside a Claude session
- Multiple sessions are active for the same project
- Auto-detection fails

---

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `CLAUDE_SKIP_REQUIREMENTS` | Set to `1` to skip all requirement checks (global bypass) |
| `RF_STRICT_OFF` | Set to `true` to instantly disable strict-preflight mode (ADR-020 kill-switch) |
| `NO_COLOR` | Disable colored output |
| `FORCE_COLOR` | Force colored output |
