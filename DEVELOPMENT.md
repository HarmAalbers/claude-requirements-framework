# Development Workflow

This document explains how to develop, test, and maintain the Claude Code Requirements Framework while keeping the git repository and deployed installation in sync.

## Architecture Overview

The framework exists in two locations:

1. **Git Repository** (Source of Truth): `~/Tools/claude-requirements-framework/`
   - Version controlled
   - Where you make changes
   - Push to GitHub

2. **Deployed Location** (Active Installation): `~/.claude/hooks/`
   - Where Claude Code loads the hooks from
   - Active runtime environment
   - Where the framework actually executes

## Sync Strategy

Use the `sync.sh` script to keep these locations in sync:

```bash
cd ~/Tools/claude-requirements-framework

# Check sync status
./sync.sh status

# Deploy changes from repo → ~/.claude/hooks
./sync.sh deploy

# See what's different
./sync.sh diff
```

## Development Workflows

### Workflow 1: Standard Development (Recommended)

**Edit in repository → Deploy → Test → Commit**

```bash
# 1. Make changes in the repository
cd ~/Tools/claude-requirements-framework
vim hooks/lib/config.py  # or any file

# 2. Deploy to active installation
./sync.sh deploy

# 3. Run tests
python3 ~/.claude/hooks/test_requirements.py

# 4. Test in actual Claude Code session
# Try triggering the hook by editing a file in a project

# 5. Commit changes
git add .
git commit -m "Add new feature"
git push
```

### Workflow 2: Quick Fix in Production

**Edit in ~/.claude/hooks → Copy back to repo → Deploy → Commit**

If you need to quickly fix something in the deployed version:

```bash
# 1. Edit the deployed file
vim ~/.claude/hooks/check-requirements.py

# 2. Test immediately (it's already active)
python3 ~/.claude/hooks/test_requirements.py

# 3. Copy changes back to repository (manual)
cd ~/Tools/claude-requirements-framework
cp ~/.claude/hooks/check-requirements.py hooks/check-requirements.py

# 4. Deploy from repo to ensure both locations match
./sync.sh deploy

# 5. Commit the changes
git add .
git commit -m "Fix: emergency bug fix"
git push
```

### Workflow 3: Test-Driven Development (TDD)

**Write tests → Edit in repo → Deploy → Run tests**

```bash
# 1. Write tests in repository
cd ~/Tools/claude-requirements-framework
vim hooks/test_requirements.py

# 2. Deploy tests
./sync.sh deploy

# 3. Run tests (should FAIL - RED phase)
python3 ~/.claude/hooks/test_requirements.py

# 4. Implement feature in repository
vim hooks/lib/requirements.py

# 5. Deploy implementation
./sync.sh deploy

# 6. Run tests (should PASS - GREEN phase)
python3 ~/.claude/hooks/test_requirements.py

# 7. Refactor if needed, keeping tests green

# 8. Commit when done
git add .
git commit -m "Add feature with TDD"
git push
```

## File Structure

```
~/Tools/claude-requirements-framework/    (Git Repository)
├── hooks/
│   ├── check-requirements.py          → ~/.claude/hooks/check-requirements.py
│   ├── handle-session-start.py        → ~/.claude/hooks/handle-session-start.py
│   ├── handle-stop.py                 → ~/.claude/hooks/handle-stop.py
│   ├── handle-session-end.py          → ~/.claude/hooks/handle-session-end.py
│   ├── auto-satisfy-skills.py         → ~/.claude/hooks/auto-satisfy-skills.py
│   ├── clear-single-use.py            → ~/.claude/hooks/clear-single-use.py
│   ├── handle-plan-exit.py            → ~/.claude/hooks/handle-plan-exit.py
│   ├── requirements-cli.py            → ~/.claude/hooks/requirements-cli.py
│   ├── ruff_check.py                  → ~/.claude/hooks/ruff_check.py
│   ├── test_requirements.py           → ~/.claude/hooks/test_requirements.py
│   ├── test_branch_size_calculator.py → ~/.claude/hooks/test_branch_size_calculator.py
│   └── lib/
│       ├── __init__.py                → ~/.claude/hooks/lib/__init__.py
│       ├── branch_size_calculator.py  → ~/.claude/hooks/lib/branch_size_calculator.py
│       ├── calculation_cache.py       → ~/.claude/hooks/lib/calculation_cache.py
│       ├── calculator_interface.py    → ~/.claude/hooks/lib/calculator_interface.py
│       ├── config.py                  → ~/.claude/hooks/lib/config.py
│       ├── git_utils.py               → ~/.claude/hooks/lib/git_utils.py
│       ├── logger.py                  → ~/.claude/hooks/lib/logger.py
│       ├── message_dedup_cache.py     → ~/.claude/hooks/lib/message_dedup_cache.py
│       ├── requirement_strategies.py  → ~/.claude/hooks/lib/requirement_strategies.py
│       ├── requirements.py            → ~/.claude/hooks/lib/requirements.py
│       ├── session.py                 → ~/.claude/hooks/lib/session.py
│       ├── state_storage.py           → ~/.claude/hooks/lib/state_storage.py
│       ├── messages.py                → ~/.claude/hooks/lib/messages.py
│       └── message_validator.py       → ~/.claude/hooks/lib/message_validator.py
├── examples/                           (Not deployed)
├── docs/                               (Not deployed, includes ADRs)
├── sync.sh                             (Sync script - uses dynamic file discovery)
├── install.sh                          (Installation script)
└── README.md                           (Documentation)
```

Note: `sync.sh` uses dynamic file discovery - new `.py` files are automatically included in sync operations.

## Sync Script Reference

### `sync.sh status`

Shows the sync status of all files:

```
📊 Sync Status
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Repository:  /Users/harm/Tools/claude-requirements-framework
Deployed:    /Users/harm/.claude/hooks

File Status:
  ✓ check-requirements.py - In sync
  ↑ requirements-cli.py - Out of sync (run './sync.sh deploy' to update deployed)
  ⚠ lib/config.py - Not deployed
  ✗ lib/old_module.py - Missing in repository (exists in deployed)
```

**Symbols**:
- `✓` - Files are in sync
- `↑` - Out of sync (deploy to update)
- `⚠` - Not deployed (exists in repository only)
- `✗` - Missing in repository (exists in deployed only)

### `sync.sh deploy`

Copies all files from repository → `~/.claude/hooks/`

- Overwrites deployed files
- Sets executable permissions
- Useful after making changes in the repo

### `sync.sh diff`

Shows detailed differences between repository and deployed versions.

Uses `diff -u` to show line-by-line changes.

## New in v2.1: Message Deduplication

### Feature Overview

**Problem**: When Claude makes parallel Write/Edit calls (5-12 files simultaneously), the hook executes repeatedly, showing identical blocking messages 5-12 times. This creates overwhelming spam.

**Solution**: TTL-based message deduplication cache that:
- Shows full blocking message on first occurrence
- Shows minimal "⏸️ waiting..." indicator for subsequent blocks within 5 seconds
- Automatically expires after TTL to show updated messages

### Files Involved

- `hooks/lib/message_dedup_cache.py` (NEW - 286 lines)
- `hooks/lib/requirement_strategies.py` (MODIFIED - deduplication integration)

### Debug Mode

Enable debug logging to see deduplication behavior:

```bash
export CLAUDE_DEDUP_DEBUG=1

# Now when hooks execute, you'll see:
# [DEDUP] Showing (first time or expired): /path/to/project:branch:session:commit_plan
# [DEDUP] Suppressing: /path/to/project:branch:session:commit_plan
```

### Testing Deduplication

```bash
# Test parallel writes
cd ~/some-project
git checkout -b test-dedup

# This should trigger multiple hook invocations
claude "create 5 files: a.py b.py c.py d.py e.py with hello world"

# Expected behavior:
# - First block: Full 15-line message with checklist
# - Blocks 2-5: "⏸️ Requirement `commit_plan` not satisfied (waiting...)"
```

### Cache Location

```bash
# Unix
/tmp/claude-message-dedup-{uid}.json

# Windows
/tmp/claude-message-dedup-{username}.json

# Fallback (if /tmp issues)
~/.claude/message-dedup.json
```

### Clear Cache (for testing)

```python
from message_dedup_cache import MessageDedupCache
cache = MessageDedupCache()
cache.clear()
```

Or manually:
```bash
rm /tmp/claude-message-dedup-$(id -u).json
```

---

## New in v2.2: Message Externalization

### Feature Overview

**Problem**: Framework messages were hardcoded in Python files (~180 strings), making customization difficult without code changes.

**Solution**: External YAML files with cascade loading (same pattern as requirements config).

### Directory Structure

```
~/.claude/
  messages/                    # Global defaults
    _templates.yaml            # Shared templates by type
    _status.yaml               # Status format templates
    commit_plan.yaml           # Per-requirement messages
    adr_reviewed.yaml
    ...

<project>/.claude/
  messages/                    # Project-specific (version controlled)
  messages.local/              # Local overrides (gitignored)
```

### Files Involved

- `hooks/lib/messages.py` (NEW - Core MessageLoader class)
- `hooks/lib/message_validator.py` (NEW - Validation logic)
- `hooks/lib/base_strategy.py` (MODIFIED - `_get_message_loader()` method)
- `hooks/lib/blocking_strategy.py` (MODIFIED - Uses MessageLoader)
- `hooks/lib/guard_strategy.py` (MODIFIED - Uses MessageLoader)
- `hooks/check-requirements.py` (MODIFIED - Injects MessageLoader into context)
- `hooks/requirements-cli.py` (MODIFIED - `req messages` command)

### Message File Schema

Each requirement needs 6 fields:

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

### CLI Commands

```bash
# Validate all message files
req messages validate

# Generate missing files from templates
req messages validate --fix

# List files with cascade sources
req messages list
```

### Testing Message Customization

```bash
# Create project override
mkdir -p .claude/messages
cat > .claude/messages/commit_plan.yaml << 'EOF'
version: "1.0"
blocking_message: |
  ## Custom Message
  This is a project-specific blocking message.
short_message: "Custom short message"
success_message: "Custom success"
header: "Custom Header"
action_label: "Custom action"
fallback_text: "req satisfy commit_plan"
EOF

# Verify it loads
req messages list
# Should show: commit_plan.yaml (project)

# Test the message appears
# Trigger a requirement block
```

### Design Notes

- **Cascade Priority**: local > project > global (same as requirements config)
- **Strict Mode**: Off at runtime (`strict=False`) for backwards compatibility
- **Context Injection**: MessageLoader passed via context dict to singleton strategies
- **Calculator Messages**: Stay in code (need access to dynamic result data)

See ADR-011 for full design rationale.

---

## Testing

### Unit Tests

Run the comprehensive test suite:

```bash
# From deployed location (faster)
python3 ~/.claude/hooks/test_requirements.py

# From repository (same tests)
cd ~/Tools/claude-requirements-framework
python3 hooks/test_requirements.py

# Expected output:
# 🧪 Requirements Framework Test Suite
# ==================================================
# Results: 447/447 tests passed
```

### Integration Testing

Test the hook in a real Claude Code session:

```bash
# 1. Create a test branch in a project
cd ~/some-project
git checkout -b test/hook-testing

# 2. Ensure requirements are enabled
cat .claude/requirements.yaml

# 3. Try to edit a file (should be blocked)
# Claude Code will show the requirement blocker

# 4. Satisfy the requirement
req satisfy commit_plan

# 5. Try to edit again (should work)
```

## Common Scenarios

### Scenario: You modified files in ~/.claude/hooks and forgot

```bash
# Check what's out of sync
cd ~/Tools/claude-requirements-framework
./sync.sh status

# Review differences
./sync.sh diff

# Copy any deployed changes you want to keep back into the repo
cp ~/.claude/hooks/check-requirements.py hooks/check-requirements.py

# Review changes
git diff

# Commit if good
git add .
git commit -m "Sync: reconcile deployed changes"
git push
```

### Scenario: You want to deploy a new feature

```bash
# Make changes in repository
cd ~/Tools/claude-requirements-framework
vim hooks/lib/requirements.py

# Deploy to test
./sync.sh deploy

# Run tests
python3 ~/.claude/hooks/test_requirements.py

# If tests pass, commit
git add .
git commit -m "Add new feature"
git push
```

### Scenario: Emergency production fix

```bash
# Fix directly in deployed location
vim ~/.claude/hooks/check-requirements.py

# Test immediately (no deploy needed)
python3 ~/.claude/hooks/test_requirements.py

# Copy fix into repo when done
cd ~/Tools/claude-requirements-framework
cp ~/.claude/hooks/check-requirements.py hooks/check-requirements.py

# Deploy to keep repo as source of truth
./sync.sh deploy

# Commit and push
git add .
git commit -m "Hotfix: critical bug"
git push
```

### Scenario: Fresh installation on new machine

```bash
# Clone repository
git clone https://github.com/HarmAalbers/claude-requirements-framework.git
cd claude-requirements-framework

# Install (deploys automatically)
./install.sh

# Verify sync status
./sync.sh status
# Should show: All files in sync
```

## Best Practices

### 1. Always Check Sync Status Before Committing

```bash
cd ~/Tools/claude-requirements-framework
./sync.sh status
# If status shows missing/out-of-sync files, reconcile in repo before committing
git add .
git commit -m "Your changes"
```

### 2. Run Tests After Every Deploy

```bash
./sync.sh deploy
python3 ~/.claude/hooks/test_requirements.py
```

### 3. Use Meaningful Commit Messages

Follow the pattern used in the framework:

```bash
# Good
git commit -m "Add checklist feature to requirement blockers"
git commit -m "Fix: session registry bootstrap timing issue"
git commit -m "Test: add coverage for empty checklist handling"

# Bad
git commit -m "updates"
git commit -m "fix bug"
```

### 4. Keep Repository and Deploy in Sync

Make it a habit to check sync status daily:

```bash
cd ~/Tools/claude-requirements-framework
./sync.sh status
```

### 5. Test Before Pushing

```bash
# Full workflow
./sync.sh deploy
python3 ~/.claude/hooks/test_requirements.py
git add .
git commit -m "Your message"
git push
```

## Troubleshooting

### Problem: "Repository is newer" but I didn't make changes

**Cause**: Files were copied during repository creation

**Solution**: Deploy to sync them up
```bash
./sync.sh deploy
./sync.sh status  # Should show all in sync now
```

### Problem: "Missing in repository" after an emergency edit

**Cause**: You edited in `~/.claude/hooks/` without copying changes back

**Solution**: Copy changes into the repo, then deploy
```bash
cp ~/.claude/hooks/check-requirements.py hooks/check-requirements.py
./sync.sh deploy
git diff  # Review what changed
git add .
git commit -m "Sync: reconcile deployed changes"
```

### Problem: Tests pass in repo but fail when deployed

**Cause**: File permission issues or missing files

**Solution**: Redeploy with verbose output
```bash
./sync.sh deploy
ls -la ~/.claude/hooks/
python3 ~/.claude/hooks/test_requirements.py
```

### Problem: Changes not taking effect in Claude Code

**Cause**: Claude Code may cache hook files

**Solution**: Restart Claude Code session or clear cache
```bash
# Redeploy to ensure files are up to date
./sync.sh deploy

# Restart Claude Code
# The hook will reload on next invocation
```

## Advanced: Automation

### Git Hook for Auto-Sync Check

Create `.git/hooks/pre-commit` in the repository:

```bash
#!/bin/bash

cd ~/Tools/claude-requirements-framework

# Check if repo is missing deployed changes
if ./sync.sh status | grep -q "Missing in repository"; then
    echo "⚠️  Warning: Repository is missing deployed changes!"
    echo "   Copy deployed changes into the repo before committing."
    echo ""
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi
```

### Periodic Sync Reminder

Add to your shell profile (~/.zshrc or ~/.bashrc):

```bash
# Check requirements framework sync status on cd to repo
claude_req_sync_check() {
    if [[ "$PWD" == *"claude-requirements-framework"* ]]; then
        if [ -f "./sync.sh" ]; then
            echo "💡 Run './sync.sh status' to check sync status"
        fi
    fi
}

# Run on directory change
chpwd_functions+=(claude_req_sync_check)  # zsh
# or
PROMPT_COMMAND="${PROMPT_COMMAND:+$PROMPT_COMMAND$'\n'}claude_req_sync_check"  # bash
```

## Contributing

When contributing changes:

1. Fork the repository
2. Clone your fork
3. Install the framework: `./install.sh`
4. Make changes in the repository
5. Deploy and test: `./sync.sh deploy && python3 ~/.claude/hooks/test_requirements.py`
6. Ensure sync status is clean: `./sync.sh status`
7. Commit and push to your fork
8. Create a pull request

## Summary

| Action | Command | When |
|--------|---------|------|
| Check status | `./sync.sh status` | Before committing, periodically |
| Deploy to hooks | `./sync.sh deploy` | After making changes in repo |
| See differences | `./sync.sh diff` | When investigating issues |
| Run tests | `python3 ~/.claude/hooks/test_requirements.py` | After every change |

**Golden Rule**: Always keep repository and deployed in sync. The `sync.sh` script is your friend!
