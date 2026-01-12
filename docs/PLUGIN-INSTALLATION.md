# Plugin Installation Guide

> **Note**: This guide covers the Requirements Framework **plugin** installation. For hook installation, see the [main README](../README.md#installation).

## Table of Contents

1. [Overview](#overview)
2. [Installation Methods](#installation-methods)
3. [Verification](#verification)
4. [Troubleshooting](#troubleshooting)
5. [Plugin vs. Hooks](#plugin-vs-hooks)
6. [Development Mode](#development-mode)
7. [Configuration](#configuration)
8. [Related Documentation](#related-documentation)

---

## Overview

The Requirements Framework plugin extends Claude Code with workflow automation and code review capabilities.

**What's Included:**
- **10 specialized review agents** - ADR Guardian, Tool Validator, Code Reviewer, Silent Failure Hunter, Test Analyzer, Type Design Analyzer, Comment Analyzer, Code Simplifier, Backward Compatibility Checker, Codex Review Agent
- **2 orchestrator commands** - `/requirements-framework:pre-commit`, `/requirements-framework:quality-check`
- **5 management skills** - Status reporting, usage help, framework building, development workflow, Codex review

**Installation Location:** `~/.claude/plugins/requirements-framework/` (symlink)
**Plugin Version:** 2.0.4
**Component Details:** See [Plugin Components](../README.md#plugin-components) in main README

---

## Installation Methods

### Method 1: Via install.sh (Recommended)

The installation script automatically creates the plugin symlink:

```bash
cd ~/Tools/claude-requirements-framework
./install.sh
```

**What install.sh does:**
1. Copies hooks to `~/.claude/hooks/`
2. Creates plugin symlink at `~/.claude/plugins/requirements-framework/`
3. Verifies plugin manifest and shows version
4. Displays component count (agents, commands, skills)

**Expected Output:**
```
🔌 Setting up plugin symlink...
✅ Plugin symlinked: ~/.claude/plugins/requirements-framework
   → /path/to/repo/plugin
   Plugin version: 2.0.4
```

### Method 2: Manual Installation

If you prefer manual installation or install.sh isn't available:

```bash
# Create plugins directory
mkdir -p ~/.claude/plugins

# Create symlink
ln -s ~/Tools/claude-requirements-framework/plugin \
      ~/.claude/plugins/requirements-framework

# Verify
ls -la ~/.claude/plugins/requirements-framework
```

**Verify symlink points to correct location:**
```bash
readlink ~/.claude/plugins/requirements-framework
# Expected: /path/to/repo/plugin
```

### Method 3: Development Mode

Development mode is the same as Method 2 (manual installation). The symlink enables live updates:

```bash
# Same as Method 2
ln -s ~/Tools/claude-requirements-framework/plugin \
      ~/.claude/plugins/requirements-framework
```

**Benefits:**
- Changes to plugin files immediately reflect in Claude Code
- No need to reinstall after editing agents/commands/skills
- Perfect for plugin development and testing

---

## Verification

After installation, verify the plugin loaded successfully:

### Step 1: Check Symlink Exists

```bash
ls -la ~/.claude/plugins/requirements-framework
```

**Expected output:**
```
lrwxr-xr-x  ... → /path/to/repo/.claude/plugins/requirements-framework
```

**Verify:**
- Shows as symlink (first character is `l`)
- Points to correct source directory
- Source directory exists and is accessible

**Quick check:**
```bash
test -L ~/.claude/plugins/requirements-framework && echo "✓ Symlink exists" || echo "✗ Missing"
readlink ~/.claude/plugins/requirements-framework
test -f ~/.claude/plugins/requirements-framework/.claude-plugin/plugin.json && echo "✓ Valid plugin" || echo "✗ Invalid"
```

### Step 2: Test Commands

In Claude Code, test command autocomplete:

```
Type: /requirements-framework:

Should autocomplete to:
  • /requirements-framework:pre-commit [aspects]
  • /requirements-framework:quality-check [parallel]
```

**Run a command:**
```
/requirements-framework:pre-commit tools
```

**Expected:** Tool validator agent runs, checks pyright/ruff/eslint

### Step 3: Test Skills

In Claude Code, trigger a skill:

```
You: "Show requirements framework status"
```

**Expected:** `requirements-framework-status` skill triggers and displays status report

**Other skill triggers:**
- "How to use requirements framework" → `requirements-framework-usage`
- "Extend requirements framework" → `requirements-framework-builder`
- "Fix requirements framework bug" → `requirements-framework-development`
- "Run Codex review" → `codex-review`

### Step 4: Check Plugin Manifest

```bash
cat ~/.claude/plugins/requirements-framework/.claude-plugin/plugin.json
```

**Expected fields:**
```json
{
  "name": "requirements-framework",
  "version": "2.0.4",
  "description": "Claude Code Requirements Framework - Enforces development workflow...",
  "skills": [...],
  "commands": [...],
  "agents": [...]
}
```

**Verify:**
- Version is `2.0.4`
- 5 skills listed
- 2 commands listed
- 10 agents listed

---

## Troubleshooting

### Plugin Not Appearing

**Symptom:** Commands don't autocomplete, skills don't trigger

**Diagnosis:**
```bash
# Check if symlink exists
test -L ~/.claude/plugins/requirements-framework && echo "Symlink exists" || echo "Missing"

# Check where it points
readlink ~/.claude/plugins/requirements-framework

# Check if manifest exists
test -f ~/.claude/plugins/requirements-framework/.claude-plugin/plugin.json && echo "Manifest found" || echo "Missing"

# Check manifest validity
python3 -c "import json; json.load(open('$HOME/.claude/plugins/requirements-framework/.claude-plugin/plugin.json'))"
```

**Solutions:**

1. **Symlink missing** → Run `./install.sh` or create manually (Method 2)
2. **Wrong target** → Remove and recreate:
   ```bash
   rm ~/.claude/plugins/requirements-framework
   cd ~/Tools/claude-requirements-framework
   ./install.sh
   ```
3. **Manifest missing** → Update repo:
   ```bash
   cd ~/Tools/claude-requirements-framework
   git pull
   ```
4. **Plugin not loading** → Restart Claude Code session

### Symlink Points to Wrong Location

**Symptom:** Symlink exists but points to old/incorrect location

**Fix:**
```bash
# Remove old symlink
rm ~/.claude/plugins/requirements-framework

# Recreate with correct path
cd ~/Tools/claude-requirements-framework
./install.sh
```

**Verify:**
```bash
readlink ~/.claude/plugins/requirements-framework
# Should match your actual repo location
```

### Permission Errors

**Symptom:** "Permission denied" when creating symlink or accessing plugin

**Diagnosis:**
```bash
ls -la ~/.claude/
ls -la ~/.claude/plugins/
```

**Fix:**
```bash
# Fix ownership
sudo chown -R $(whoami) ~/.claude/

# Recreate symlink
cd ~/Tools/claude-requirements-framework
./install.sh
```

### Commands Work But Skills Don't

**Cause:** Skills use natural language triggering based on description patterns

**Verify skill descriptions:**
```bash
cat ~/.claude/plugins/requirements-framework/skills/requirements-framework-status/skill.md
```

**Use exact trigger phrases:**
- ✅ "Show requirements framework status"
- ✅ "How to use requirements framework"
- ❌ "Show me status" (too vague)
- ❌ "Framework status" (missing trigger words)

**Check skill frontmatter:**
```yaml
---
description: This skill should be used when the user asks to "requirements framework status", "show requirements project context"...
---
```

Use phrases from the `description` field.

### Plugin Version Mismatch

**Symptom:** Plugin version doesn't match expected or doesn't update

**Cause:** Symlink may be broken, or repo needs updating

**Fix:**
```bash
# Update repo
cd ~/Tools/claude-requirements-framework
git pull

# Symlink updates automatically
cat ~/.claude/plugins/requirements-framework/.claude-plugin/plugin.json | grep version
```

**Expected:** Version should match what's in repo

**Force reinstall:**
```bash
rm ~/.claude/plugins/requirements-framework
./install.sh
```

### Plugin Directory Not Found

**Symptom:** install.sh says "Plugin directory not found at ..."

**Cause:** Old repo version or missing plugin files

**Fix:**
```bash
cd ~/Tools/claude-requirements-framework
git pull
git log --oneline -5 plugin/

# Verify directory exists
ls -la plugin/.claude-plugin/plugin.json
```

**If missing:**
```bash
# Ensure you're on correct branch
git status
git checkout master  # or main

# Pull latest
git pull origin master
```

---

## Plugin vs. Hooks

The Requirements Framework has two complementary components:

### Hooks (Core Runtime Enforcement)

**Location:** `~/.claude/hooks/`
**Purpose:** Enforce requirements by blocking file edits until satisfied
**Components:**
- `check-requirements.py` (PreToolUse hook)
- `handle-session-start.py`, `handle-stop.py`, `handle-session-end.py` (lifecycle hooks)
- `auto-satisfy-skills.py`, `clear-single-use.py` (PostToolUse hooks)
- `lib/` modules (core logic)
- `req` CLI command

**Installed by:** Copied to `~/.claude/hooks/` by `install.sh`

### Plugin (Workflow Automation Tools)

**Location:** `~/.claude/plugins/requirements-framework/` (symlink)
**Purpose:** Provide agents, commands, and skills to satisfy requirements
**Components:**
- 10 agents (code review, workflow enforcement)
- 2 commands (pre-commit, quality-check orchestrators)
- 5 skills (management and status)

**Installed by:** Symlinked by `install.sh`

### How They Work Together

```
┌─────────────────────────────────────────────────────────────┐
│  User tries to Edit/Write file                             │
└─────────────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│  HOOKS (check-requirements.py)                              │
│  • Check if pre_commit_review requirement satisfied         │
│  • If NOT satisfied → Block edit with message               │
└─────────────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│  User runs: /requirements-framework:pre-commit              │
│  (PLUGIN command)                                           │
└─────────────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│  Command completes → PostToolUse hook                       │
│  (auto-satisfy-skills.py)                                   │
│  • Detects pre-commit command finished                      │
│  • Auto-satisfies pre_commit_review requirement             │
└─────────────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│  User can now Edit/Write files                              │
│  (requirement satisfied)                                    │
└─────────────────────────────────────────────────────────────┘
```

**Key Integration:** `auto-satisfy-skills.py` (PostToolUse hook) maps plugin commands to requirements:

| Plugin Command | Satisfies Requirement |
|----------------|----------------------|
| `/requirements-framework:pre-commit` | `pre_commit_review` |
| `/requirements-framework:quality-check` | `pre_pr_review` |

**See:** `~/.claude/hooks/auto-satisfy-skills.py` for mapping logic

---

## Development Mode

### Live Editing Workflow

The symlink enables immediate updates without reinstallation:

```bash
# 1. Edit agent in repo
vim ~/Tools/claude-requirements-framework/plugin/agents/code-reviewer.md

# 2. Changes are live immediately (symlink)
# No restart needed - Claude Code auto-reloads plugins

# 3. Test in Claude Code
/requirements-framework:pre-commit code

# 4. Commit changes
cd ~/Tools/claude-requirements-framework
git add plugin/agents/code-reviewer.md
git commit -m "feat(agent): enhance code-reviewer detection"
```

### Testing Changes

**Agent changes:**
```bash
# Edit agent
vim plugin/agents/test-analyzer.md

# Test via command (agents invoked by commands)
/requirements-framework:pre-commit tests
```

**Command changes:**
```bash
# Edit command
vim plugin/commands/pre-commit.md

# Test directly
/requirements-framework:pre-commit all
```

**Skill changes:**
```bash
# Edit skill
vim plugin/skills/requirements-framework-status/skill.md

# Test via natural language
"Show requirements framework status"
```

### Sync Not Needed

**Plugin:** Symlinked - no sync needed, changes immediate
**Hooks:** Copied - requires sync

```bash
# For hook changes only:
./sync.sh status   # Check sync status
./sync.sh deploy   # Deploy hooks
```

**Plugin changes:** No sync required (symlink keeps in sync automatically)

---

## Configuration

The plugin respects the same configuration cascade as hooks:

### Configuration Files

1. **`~/.claude/requirements.yaml`** (Global)
2. **`.claude/requirements.yaml`** (Project)
3. **`.claude/requirements.local.yaml`** (Local overrides)

See [Configuration System](../README.md#configuration-system) for details.

### Enabling Plugin-Related Requirements

To use plugin commands as requirement satisfaction mechanisms:

**~/.claude/requirements.yaml:**
```yaml
requirements:
  pre_commit_review:
    scope: single_use
    message: "Run /requirements-framework:pre-commit before committing"

  pre_pr_review:
    scope: single_use
    message: "Run /requirements-framework:quality-check before creating PR"
```

**How it works:**
1. Requirement enabled → Blocks edits
2. User runs plugin command → Command completes
3. PostToolUse hook (auto-satisfy-skills.py) → Auto-satisfies requirement
4. Edit unblocked

**See:** [Plugin Components](../README.md#plugin-components) for command details

---

## Related Documentation

### Main Documentation
- **[Main README](../README.md)** - Framework overview and quick start
- **[Plugin Components](../README.md#plugin-components)** - Detailed agent/command/skill descriptions
- **[Plugin README](../plugin/README.md)** - Plugin-specific usage guide

### Architecture
- **[ADR-006: Plugin Architecture](./adr/ADR-006-plugin-architecture-code-review.md)** - Design decisions for plugin system

### Development
- **[Requirements Framework Development](../README.md#development)** - Contributing to the framework
- **[Sync Guide](../CLAUDE.md)** - Hook deployment and sync workflow

### Configuration
- **[Configuration System](../README.md#configuration-system)** - Configuration cascade and customization
- **[Examples](../examples/)** - Example configurations

---

## Support

### Self-Service

1. **Check this troubleshooting guide** - [Troubleshooting](#troubleshooting) section above
2. **Run diagnostics:**
   ```bash
   req doctor --repo ~/Tools/claude-requirements-framework
   ```
3. **Test hooks:**
   ```bash
   python3 ~/.claude/hooks/test_requirements.py
   ```

### Get Help

- **Issues:** https://github.com/HarmAalbers/claude-requirements-framework/issues
- **Discussions:** https://github.com/HarmAalbers/claude-requirements-framework/discussions

---

## Version History

- **v2.0.4** - Current stable release with 10 agents, 2 commands, 5 skills
  - Plugin installation via install.sh
  - Auto-satisfy mechanism for requirements
  - Comprehensive code review suite
