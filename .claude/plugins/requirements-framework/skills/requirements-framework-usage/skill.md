---
name: requirements-framework-usage
description: This skill should be used when the user asks about "using requirements framework", "how to configure requirements", "add requirement checklist", "customize requirements", "requirements not working", "bypass requirements", "satisfy requirements", or needs help with the requirements framework CLI (req command). Also triggers on questions about requirement scopes, session management, or troubleshooting hooks.
---

# Requirements Framework Usage

Help users configure, customize, and troubleshoot the **Claude Code Requirements Framework** - a hook-based system that enforces development workflow practices.

**Repository**: https://github.com/HarmAalbers/claude-requirements-framework
**Documentation**: `~/.claude/hooks/README-REQUIREMENTS-FRAMEWORK.md`
**Global Config**: `~/.claude/requirements.yaml`

## Core Capabilities

1. **Configuration Guidance** - Help set up global, project, and local configs
2. **Checklist Customization** - Add/modify checklists for requirements
3. **CLI Usage** - Explain `req` command and session management
4. **Troubleshooting** - Debug hooks, permissions, and sync issues
5. **Best Practices** - Recommend workflows and patterns

## Quick Reference

### CLI Commands

```bash
# Check status
req status

# Satisfy requirement
req satisfy commit_plan
req satisfy adr_reviewed

# With explicit session
req satisfy commit_plan --session abc12345

# Clear requirement
req clear commit_plan

# List all requirements
req list

# View active sessions
req sessions
req sessions --project  # Current project only

# Interactive project setup (Phase 3.4)
req init                    # Interactive wizard
req init --preset strict    # Use preset
req init --yes              # Non-interactive

# Configuration management (Phase 3.5)
req config                           # View all requirements
req config commit_plan               # View specific requirement
req config commit_plan --enable      # Enable requirement
req config commit_plan --disable     # Disable requirement
req config commit_plan --scope branch   # Change scope
req config adr_reviewed --set adr_path=/custom/path  # Set arbitrary field

# Diagnostics (Phase 3)
req doctor              # Verify installation & sync status
req verify              # Quick installation check

# Maintenance
req prune               # Clean stale sessions & branches
```

### Configuration Locations

1. **Global** (`~/.claude/requirements.yaml`) - Defaults for all projects
2. **Project** (`.claude/requirements.yaml`) - Shared team config (committed)
3. **Local** (`.claude/requirements.local.yaml`) - Personal overrides (gitignored)

### Requirement Scopes

| Scope | Lifetime | Use Case |
|-------|----------|----------|
| `session` | Until Claude Code session ends | Daily planning, ADR review |
| `branch` | Persists across sessions | GitHub ticket linking |
| `permanent` | Never cleared automatically | Project setup |
| `single_use` | Cleared after triggering action | Pre-commit review (each commit) |

**Single-Use Scope**: Special scope that auto-clears after the triggering action completes. Perfect for requirements that must be satisfied before EVERY action (like reviewing code before each commit).

## Common Tasks

### Task: Add Checklist to Existing Requirement

When user wants to add a checklist to a requirement:

1. Identify which config file to edit (global, project, or local)
2. Add `checklist` field with array of strings
3. Each item should be concise (one clear action)
4. Deploy if editing repository version

**Example**:
```yaml
requirements:
  commit_plan:
    enabled: true
    scope: session
    checklist:
      - "Plan created via EnterPlanMode"
      - "Atomic commits identified"
      - "TDD approach documented"
      - "Linting/typecheck commands known"
```

### Task: Create Custom Requirement

When user wants a new requirement type:

```yaml
requirements:
  my_custom_requirement:
    enabled: true
    scope: session  # or branch, permanent, single_use
    trigger_tools:
      - Edit
      - Write
      - MultiEdit
    message: |
      🎯 **Custom requirement not satisfied**

      Explain what needs to be done here.
    checklist:
      - "First step"
      - "Second step"
      - "Third step"
```

### Task: Create Requirement for Bash Commands

Block specific Bash commands (like git commit, gh pr create):

```yaml
requirements:
  pre_deploy_check:
    enabled: true
    scope: single_use  # Must satisfy before EACH deploy
    trigger_tools:
      - tool: Bash
        command_pattern: "npm\\s+publish|yarn\\s+publish"
    message: |
      🚀 **Deployment check required**

      Run `/pre-deploy:check` before publishing.
```

**Pattern Matching**:
- Uses Python regex (case-insensitive)
- `\\s+` matches whitespace
- `|` for OR patterns
- Examples:
  - `git\\s+commit` - Matches `git commit -m "msg"`
  - `gh\\s+pr\\s+create` - Matches `gh pr create --title "..."`
  - `npm\\s+(publish|deploy)` - Matches `npm publish` or `npm deploy`

### Task: Set Up Auto-Satisfaction

Skills can automatically satisfy requirements when they complete:

**Built-in mappings** (`~/.claude/hooks/auto-satisfy-skills.py`):
- `pre-pr-review:pre-commit` → satisfies `pre_commit_review`
- `pre-pr-review:quality-check` → satisfies `pre_pr_review`

**Workflow**:
```
1. User runs: git commit → Blocked!
2. User runs: /pre-pr-review:pre-commit
3. Skill completes → Auto-satisfies pre_commit_review
4. User runs: git commit → Success!
5. PostToolUse hook → Clears single_use requirement
6. Next commit → Must run review again
```

**Add custom mapping**:
```python
# Edit ~/.claude/hooks/auto-satisfy-skills.py
SKILL_REQUIREMENTS = {
    'pre-pr-review:pre-commit': 'pre_commit_review',
    'my-plugin:my-skill': 'my_requirement',  # Add here
}
```

### Task: Troubleshoot Hook Not Triggering

Check these in order:

1. **On main/master?** - Hook skips these branches by design
2. **Config enabled?** - Check `.claude/requirements.yaml` has `enabled: true`
3. **Requirement enabled?** - Check specific requirement has `enabled: true`
4. **Hook registered?** - Check `~/.claude/settings.local.json` has:
   ```json
   {
     "hooks": {
       "PreToolUse": "~/.claude/hooks/check-requirements.py"
     }
   }
   ```
5. **Wildcard permissions?** - Check if `Edit(*)` or `Write(*)` in `permissions.allow` (these bypass hooks)
6. **Skip flag set?** - Check if `CLAUDE_SKIP_REQUIREMENTS` environment variable is set

### Task: Temporarily Disable Requirements

**Option 1**: Local override (per project)
```yaml
# .claude/requirements.local.yaml
enabled: false
```

**Option 2**: Environment variable
```bash
export CLAUDE_SKIP_REQUIREMENTS=1
```

**Option 3**: Disable specific requirement
```yaml
# .claude/requirements.local.yaml
requirements:
  commit_plan:
    enabled: false
```

## Phase 3 Features (2025-12-24)

### Interactive Project Setup: `req init`

**Added in Phase 3.4** - Context-aware initialization wizard

#### Usage

```bash
req init                    # Interactive mode
req init --preset strict    # Use preset (non-interactive)
req init --yes              # Non-interactive with defaults
req init --project          # Force project config (vs local)
req init --local            # Force local config
req init --preview          # Show changes without writing
```

#### Presets

Five pre-configured profiles for different workflows:

**1. strict** (Recommended for teams)
- All requirements enabled
- Session scope (daily verification)
- All hooks enabled (SessionStart, Stop verification)
- Ideal for: Teams with strong workflow enforcement

**2. relaxed** (Flexible workflow)
- Basic requirements only (commit_plan)
- Branch scope (persists across sessions)
- Minimal hooks
- Ideal for: Solo developers or flexible teams

**3. minimal** (Learning mode)
- Only commit_plan enabled
- Session scope
- Basic hooks
- Ideal for: Getting started, learning the framework

**4. advanced** (Experienced users)
- All features enabled
- Branch size limits (dynamic requirements)
- Protected branch guards
- Stop hook verification
- Ideal for: Power users who want all features

**5. inherit** (Maintain consistency)
- Inherits from global config
- Adds project-specific customizations only
- Ideal for: Consistent multi-project setups

#### Features

- **Auto-detects global config** - Suggests inheritance when global config exists
- **Creates `.claude/requirements.yaml`** - Project or local config
- **Updates `.gitignore`** - Adds requirements state files automatically
- **Suggests SessionStart hook** - If not already registered
- **Preview mode** - Review changes before applying
- **Non-destructive** - Won't overwrite without `--force` flag

#### Example Interactive Flow

```
$ req init

Requirements Framework Initialization
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Detected global config at ~/.claude/requirements.yaml

? Choose configuration profile:
  ❯ strict - All requirements, session scope (Recommended)
    relaxed - Basic requirements, branch scope
    minimal - Learning mode, commit_plan only
    advanced - All features + branch size limits
    inherit - Maintain consistency with global

? Config location:
  ❯ Project (.claude/requirements.yaml) - Shared with team
    Local (.claude/requirements.local.yaml) - Personal only

? Enable SessionStart hook? (shows status on startup) Yes

✅ Created .claude/requirements.yaml
✅ Updated .gitignore
✅ SessionStart hook enabled

📚 Next steps:
  - Review config: req config
  - Check status: req status
  - Satisfy requirements: req satisfy commit_plan
```

---

### Configuration Management: `req config`

**Added in Phase 3.5** - View and modify requirement settings without editing YAML

#### View Configuration

```bash
req config                  # View all requirements (pretty-printed)
req config commit_plan      # View specific requirement

# Output example:
# commit_plan:
#   enabled: true
#   scope: session
#   type: blocking
#   message: "📋 **Commit Plan Required**..."
#   checklist:
#     - "Plan created via EnterPlanMode"
#     - "Atomic commits identified"
```

#### Modify Requirements

```bash
# Toggle requirement
req config commit_plan --enable
req config commit_plan --disable

# Change scope
req config commit_plan --scope branch
req config commit_plan --scope session
req config commit_plan --scope permanent
req config commit_plan --scope single_use

# Update message
req config commit_plan --message "New message text"

# Set arbitrary fields
req config adr_reviewed --set adr_path=/custom/path
req config branch_size_limit --set threshold=500
req config github_ticket --set auto_extract=true

# Set JSON values
req config my_requirement --set metadata='{"key":"value"}'
req config my_requirement --set numbers=42
req config my_requirement --set enabled=true
```

#### Flags

- `--enable` / `--disable` - Toggle requirement on/off
- `--scope SCOPE` - Change scope (session/branch/permanent/single_use)
- `--message TEXT` - Update user-facing message
- `--set KEY=VALUE` - Set arbitrary fields
  - Auto-parses numbers, booleans, arrays, objects (JSON)
  - Examples: `threshold=400`, `enabled=true`, `list='["a","b"]'`
- `--yes` - Skip confirmation prompts
- `--project` - Modify project config (`.claude/requirements.yaml`)
- `--local` - Modify local config (`.claude/requirements.local.yaml`)

#### Interactive Config Selection

When location not specified, prompts:

```
? Which config should be modified?
  ❯ Project (.claude/requirements.yaml) - Shared with team (committed)
    Local (.claude/requirements.local.yaml) - Personal only (gitignored)
```

#### Preview & Confirmation

Shows changes before applying:

```
$ req config commit_plan --disable

Preview of changes:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  commit_plan:
-   enabled: true
+   enabled: false
    scope: session
    message: "..."

? Apply these changes to .claude/requirements.yaml? (Y/n)
```

---

### Diagnostics: `req doctor`

**Added in Phase 3** - Verifies framework installation and sync status

#### What It Checks

```bash
req doctor

# Output:
Requirements Framework Doctor
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Python Version: ✅ 3.11.5 (minimum 3.9 required)
Hook Registration: ✅ 4 hooks registered in settings.json
File Permissions: ✅ All executable (~/.claude/hooks/*.py)
Sync Status: ⚠️ 2 files need sync (repo → deployed)
Library Imports: ✅ All imports successful
Test Suite: ✅ 421/421 tests passing (100%)

⚠️ Recommendations:
  • Run './sync.sh deploy' to sync 2 modified files
  • File: check-requirements.py (repo newer)
  • File: requirements-cli.py (repo newer)

💡 Commands:
  • Sync: cd ~/Tools/claude-requirements-framework && ./sync.sh deploy
  • Test: python3 ~/.claude/hooks/test_requirements.py
  • Status: req status
```

#### Checks Performed

1. **Python Version** - Ensures 3.9+ (required for framework)
2. **Hook Registration** - Verifies hooks in `~/.claude/settings.json`:
   - PreToolUse
   - SessionStart
   - Stop
   - SessionEnd
   - PostToolUse hooks
3. **File Permissions** - Checks all Python files are executable
4. **Sync Status** - Compares repository vs deployed files:
   - Lists files that differ
   - Shows which is newer
   - Suggests sync command
5. **Library Imports** - Tests all `lib/` modules import successfully
6. **Test Suite** - Runs test suite and reports pass/fail count

#### When to Use

- After installing or updating the framework
- When hooks aren't triggering as expected
- Before reporting issues
- After editing framework code
- During troubleshooting

---

### Installation Verification: `req verify`

Quick check that framework is properly installed

```bash
req verify

# Output:
✅ Requirements framework is properly installed
  • CLI accessible: python3 ~/.claude/hooks/requirements-cli.py
  • Hooks directory exists: ~/.claude/hooks/
  • Core libraries present: 17/17 modules found
  • Test suite accessible: test_requirements.py found

ℹ️ For detailed diagnostics, run: req doctor
```

Simpler than `req doctor` - just verifies basics are in place.

---

## Checklist Feature (New in v2.0)

### Checklist Display

When Claude is blocked by a requirement, checklists appear in the error message:

```
📋 **No commit plan found for this session**

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

### Best Practices for Checklists

1. **Keep items concise** - One clear action per item (5-10 words)
2. **Make actionable** - Each item should be verifiable
3. **Order logically** - Steps should flow naturally
4. **Limit quantity** - 5-10 items maximum (more = less useful)
5. **Project-specific** - Customize for team workflows

**Good Example**:
```yaml
checklist:
  - "Plan created via EnterPlanMode"
  - "Atomic commits identified"
  - "Tests written (TDD approach)"
```

**Bad Example**:
```yaml
checklist:
  - "Think about what you're going to do and maybe write it down somewhere"
  - "Various things related to commits and organization"
  - "Remember to follow best practices for software development"
```

## Session Management

### How Sessions Work

- Each Claude Code session gets a unique ID (8-char hex like `abc12345`)
- Sessions are tracked in `~/.claude/sessions.json`
- Requirements are scoped to sessions (or branches/permanent)
- CLI auto-detects the correct session

### Session Commands

```bash
# View all active sessions
req sessions

# Output shows:
# Active Claude Code Sessions
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#
# Session: abc12345
#   Project: /Users/harm/Work/cclv2
#   Branch: feature/auth
#   PID: 12345
#   Started: 2025-12-10 09:15:30
```

### Using Explicit Session IDs

When `req` can't auto-detect, use `--session`:

```bash
req satisfy commit_plan --session abc12345
req status --session abc12345
req clear commit_plan --session abc12345
```

## Configuration Patterns

### Pattern: Project with Multiple Requirements

```yaml
# .claude/requirements.yaml (project)
inherit: true

requirements:
  commit_plan:
    enabled: true
    checklist:
      - "Plan created"
      - "Commits identified"

  github_ticket:
    enabled: true
    scope: branch
    message: |
      🎫 **Link this branch to a GitHub issue**

  tests_passing:
    enabled: true
    scope: session
    message: |
      ✅ **Run tests before making changes**
```

### Pattern: Personal Override

```yaml
# .claude/requirements.local.yaml (gitignored)
requirements:
  commit_plan:
    enabled: false  # Disable for myself only
```

### Pattern: Team Default with Opt-Out

```yaml
# Global: enabled: false (opt-in)
# Project: enabled: true (team requires it)
# Local: enabled: false (I opt-out temporarily)
```

## Sync Workflow (for Development)

If user is developing/maintaining the framework:

**Repository**: `~/Tools/claude-requirements-framework/`
**Deployed**: `~/.claude/hooks/`

```bash
cd ~/Tools/claude-requirements-framework

# Check sync status
./sync.sh status

# Deploy repo → ~/.claude/hooks
./sync.sh deploy

# Pull ~/.claude/hooks → repo
./sync.sh pull

# See differences
./sync.sh diff
```

See `DEVELOPMENT.md` for full workflow guide.

## Error Messages Explained

### "No commit plan found for this session"

**Cause**: `commit_plan` requirement enabled but not satisfied

**Solution**:
1. Create a commit plan
2. Run: `req satisfy commit_plan`

### "Permission denied" (from hook)

**Cause**: Requirement blocking file modifications

**Solution**: Satisfy the requirement shown in the message

### "Session not found"

**Cause**: CLI can't auto-detect session

**Solution**: Use explicit session ID:
```bash
req sessions  # Find session ID
req satisfy commit_plan --session <id>
```

### "Hook not triggering"

See "Task: Troubleshoot Hook Not Triggering" above

## Testing

### Run Full Test Suite

```bash
python3 ~/.claude/hooks/test_requirements.py

# Expected:
# 🧪 Requirements Framework Test Suite
# Results: 421/421 tests passed (100%)
```

### Test Specific Scenario

```bash
# Create test branch
git checkout -b test/requirements

# Ensure requirements enabled
cat .claude/requirements.yaml

# Try to edit (should block)
# Satisfy requirement
req satisfy commit_plan

# Try to edit (should work)
```

## Advanced Features

### Auto-Satisfaction via Skills

Requirements can be automatically satisfied when specific skills complete.

**How It Works**:
1. User tries action (e.g., `git commit`) → Blocked by `pre_commit_review`
2. User runs skill (e.g., `/pre-pr-review:pre-commit`)
3. Skill completes → PostToolUse hook auto-satisfies `pre_commit_review`
4. User retries action → Success!
5. PostToolUse hook → Clears `single_use` requirement (if applicable)

**Built-in Mappings** (`~/.claude/hooks/auto-satisfy-skills.py`):
```python
SKILL_REQUIREMENTS = {
    'pre-pr-review:pre-commit': 'pre_commit_review',
    'pre-pr-review:quality-check': 'pre_pr_review',
    'code-reviewer': 'code_review',  # Example
}
```

**Configuration Example**:
```yaml
requirements:
  pre_commit_review:
    enabled: true
    scope: single_use  # Cleared after each commit
    auto_satisfy:
      on_skill_complete: ["pre-pr-review:pre-commit", "code-reviewer"]
```

### Single-Use Requirements

Requirements that automatically clear after the triggering action completes.

**Use Case**: Enforce code review before EVERY commit (not just once per session):

```yaml
requirements:
  pre_commit_review:
    enabled: true
    scope: single_use  # Auto-cleared after action
    trigger_tools:
      - tool: Bash
        command_pattern: "git\\s+commit"
```

**Workflow**:
```
1. git commit → Blocked (pre_commit_review not satisfied)
2. /pre-pr-review:pre-commit → Auto-satisfies
3. git commit → Success!
4. PostToolUse hook → Clears single_use requirement
5. git commit (again) → Blocked (must review again)
```

**Difference from `session` scope**:
- `session`: Satisfy once, valid until session ends
- `single_use`: Must satisfy before EACH action

### Message Deduplication

The framework prevents spam by deduplicating identical messages.

**How It Works**:
- 5-minute TTL cache per unique message
- First occurrence: Message shown to user
- Subsequent occurrences (within 5 min): Silently suppressed
- 90% reduction in repeated prompts

**Automatically Applied**:
- No configuration needed
- Works for all requirements
- Prevents parallel tool calls from spamming identical messages

### Stop Hook Verification

Prevents Claude from stopping with unsatisfied requirements.

**Default Behavior**:
- Claude tries to stop (end of task)
- Stop hook checks session-scoped requirements
- If unsatisfied → Blocks stop, reminds user
- Once satisfied → Allows stop

**Configuration**:
```yaml
hooks:
  stop:
    verify_requirements: true  # Enable/disable
    verify_scopes: [session]    # Which scopes to check
```

**Use Case**: Ensures commit plan is created before session ends

**Override** (for current session only):
```bash
# Disable stop verification for emergency
req config --set hooks.stop.verify_requirements=false --local
```

### Protected Branch Guards

Prevent direct edits on main/master branches (guard requirement type).

**Configuration**:
```yaml
requirements:
  protected_branch:
    enabled: true
    type: guard  # New strategy type (vs blocking/dynamic)
    branches: [main, master, production]
    message: |
      🚫 **Cannot edit files on protected branch**

      Please create a feature branch first.
```

**Guard vs Blocking**:
- **Blocking**: Requires manual satisfaction (`req satisfy`)
- **Guard**: Condition must pass (automatically evaluated)

**For Emergency Hotfixes**:
```bash
# Approve for current session only
req approve protected_branch
```

### Dynamic Requirements (Branch Size)

Requirements that calculate conditions at runtime.

**Example: Branch Size Limit**

```yaml
requirements:
  branch_size_limit:
    enabled: true
    type: dynamic  # Auto-calculates condition
    scope: session
    threshold: 400  # Max changes before warning
    calculation_cache_ttl: 30  # Cache results (seconds)
    message: |
      📊 **Branch has {size} changes (threshold: {threshold})**

      Consider splitting into smaller branches.
```

**How It Works**:
1. Tool triggered (Edit/Write)
2. Dynamic calculator runs: `branch_size_calculator.py`
3. Calculates: `git diff main...HEAD --numstat | wc -l`
4. If size > threshold → Blocks with message
5. Result cached for 30 seconds (performance)

**Benefits**:
- No manual satisfaction needed
- Encourages small, reviewable PRs
- Caching avoids performance impact

**Customization**:
```python
# lib/branch_size_calculator.py
def calculate_branch_size(project_dir, branch):
    # Custom calculation logic here
    return size
```

### Custom Requirement Types

Create your own requirement strategy:

```python
# lib/requirement_strategies.py
class MyCustomStrategy(RequirementStrategy):
    def is_satisfied(self, requirement, state, session_id):
        # Custom logic here
        return True  # or False

    def satisfy(self, requirement, state, session_id, **kwargs):
        # Custom satisfaction logic
        pass
```

Then register in configuration:
```yaml
requirements:
  my_custom:
    enabled: true
    type: my_custom  # References MyCustomStrategy
```

## Advanced Topics

### TTL (Time-To-Live)

Expire requirements automatically:

```bash
# Satisfy for 1 hour
req satisfy commit_plan --ttl 3600

# Satisfy for 24 hours
req satisfy commit_plan --ttl 86400
```

### Metadata

Store additional data with satisfaction:

```bash
req satisfy github_ticket --metadata '{"ticket":"#123","reviewer":"alice"}'
```

### State Files

Requirements state stored in `.git/requirements/[branch].json`:

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
          "satisfied_at": 1702345678
        }
      }
    }
  }
}
```

## Key Principles

1. **Fail open** - Errors don't block Claude (logged to `~/.claude/requirements-errors.log`)
2. **Skip main/master** - Never block production branches
3. **User override** - Settings respect user's local overrides
4. **Session-isolated** - Requirements don't leak across sessions
5. **Team configurable** - Projects control their workflow

## Resources

- **README**: `~/.claude/hooks/README-REQUIREMENTS-FRAMEWORK.md`
- **GitHub**: https://github.com/HarmAalbers/claude-requirements-framework
- **Dev Guide**: `~/Tools/claude-requirements-framework/DEVELOPMENT.md`
- **Sync Tool**: `~/Tools/claude-requirements-framework/sync.sh`
- **Tests**: `~/.claude/hooks/test_requirements.py`
