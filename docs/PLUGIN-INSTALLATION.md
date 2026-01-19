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

**Installation Location:** `~/.claude/plugins/cache/requirements-framework-local/requirements-framework/2.0.5/`
**Plugin Version:** 2.0.5
**Component Details:** See [Plugin Components](../README.md#plugin-components) in main README

---

## Installation Methods

### Method 1: CLI Flag (Recommended for Testing)

**Official, zero-risk method** for testing plugin components:

```bash
# Launch Claude Code with plugin temporarily loaded
claude --plugin-dir ~/.claude/plugins/requirements-framework
```

**When to use:**
- ✅ First-time testing to verify plugin structure
- ✅ Development work with live reload
- ✅ Quick verification without system modifications
- ✅ Before committing to persistent installation

**Benefits:**
- Zero risk - no system file modifications
- Official, documented Claude Code feature
- Live reload - changes immediately available
- Can test multiple plugins simultaneously

**Limitations:**
- ⚠️ Must use CLI flag every launch
- ⚠️ Not persistent across sessions
- ⚠️ May not work with UI-launched Claude Code

**Verification:**
```
# In Claude Code session
Type: /requirements-framework:
# Should show: pre-commit, quality-check, codex-review
```

### Method 2: Marketplace Installation (Recommended for Persistent Use)

**Official method** for permanent plugin installation:

**Step 1:** Run install.sh to set up hooks and local marketplace

```bash
cd ~/Tools/claude-requirements-framework
./install.sh
```

**Step 2:** Register the local marketplace in Claude Code

```
# In Claude Code session
/plugin marketplace add ~/Tools/claude-requirements-framework
```

**Step 3:** Install the plugin from marketplace

```
/plugin install requirements-framework@requirements-framework-local
```

**Step 4:** Verify installation

```
/requirements-framework:pre-commit
```

**What gets installed:**
- Local marketplace registered with Claude Code
- Plugin copied to cache directory
- Persistent across Claude Code sessions
- Updates via reinstall command

**To update:**
```
/plugin uninstall requirements-framework@requirements-framework-local
/plugin install requirements-framework@requirements-framework-local
```

### Method 3: Manual Symlink (Deprecated)

> **⚠️ DEPRECATED:** This method is no longer recommended. Use Method 2 (Marketplace) for persistent installation or Method 1 (CLI Flag) for development.

**Note:** Symlink installation has been deprecated in v2.0.5 because it conflicts with marketplace installation and causes version tracking issues.

If you have an existing symlink at `~/.claude/plugins/requirements-framework/`, remove it and use marketplace installation instead:

```bash
# Remove deprecated symlink
rm -rf ~/.claude/plugins/requirements-framework

# Use marketplace installation (Method 2)
```

**For development with live reload**, use the `--plugin-dir` flag (Method 1) instead of creating a symlink

---

## Verification

After installation, verify the plugin loaded successfully:

### Step 1: Check Plugin Installation

```bash
# In Claude Code session
/plugin list
```

**Expected output:**
```
requirements-framework@2.0.5 (requirements-framework-local)
```

**Verify via filesystem:**
```bash
# Check cache directory exists
ls ~/.claude/plugins/cache/requirements-framework-local/requirements-framework/

# Check plugin manifest
cat ~/.claude/plugins/cache/requirements-framework-local/requirements-framework/2.0.5/.claude-plugin/plugin.json | head -5
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
cat ~/.claude/plugins/cache/requirements-framework-local/requirements-framework/2.0.5/.claude-plugin/plugin.json
```

**Expected fields:**
```json
{
  "name": "requirements-framework",
  "version": "2.0.5",
  "description": "Claude Code Requirements Framework - Enforces development workflow...",
  "skills": [...],
  "commands": [...],
  "agents": [...]
}
```

**Verify:**
- Version is `2.0.5`
- 5 skills listed
- 3 commands listed
- 17 agents listed

---

## Troubleshooting

### Plugin Not Appearing

**Symptom:** Commands don't autocomplete, skills don't trigger

**Diagnosis:**
```bash
# Check if plugin is installed
/plugin list

# Check cache directory
ls ~/.claude/plugins/cache/requirements-framework-local/requirements-framework/

# Check if manifest exists
test -f ~/.claude/plugins/cache/requirements-framework-local/requirements-framework/2.0.5/.claude-plugin/plugin.json && echo "Manifest found" || echo "Missing"
```

**Solutions:**

1. **Plugin not installed** → Install via marketplace:
   ```bash
   /plugin marketplace add ~/Tools/claude-requirements-framework
   /plugin install requirements-framework@requirements-framework-local
   ```
2. **Old version cached** → Reinstall:
   ```bash
   /plugin uninstall requirements-framework@requirements-framework-local
   /plugin marketplace update requirements-framework-local
   /plugin install requirements-framework@requirements-framework-local
   ```
3. **Manifest missing** → Update repo and reinstall:
   ```bash
   cd ~/Tools/claude-requirements-framework
   git pull
   /plugin marketplace update requirements-framework-local
   /plugin uninstall requirements-framework@requirements-framework-local
   /plugin install requirements-framework@requirements-framework-local
   ```
4. **Plugin not loading** → Restart Claude Code session

### Conflicting Installation (Symlink + Marketplace)

**Symptom:** Plugin behaves unexpectedly, wrong version shown

**Cause:** Both a symlink AND marketplace installation exist

**Fix:**
```bash
# Remove deprecated symlink if it exists
rm -rf ~/.claude/plugins/requirements-framework

# Verify only marketplace installation remains
ls ~/.claude/plugins/
# Should NOT show "requirements-framework" directory

# Check plugin via marketplace
/plugin list
```

### Permission Errors

**Symptom:** "Permission denied" when installing plugin

**Diagnosis:**
```bash
ls -la ~/.claude/
ls -la ~/.claude/plugins/
```

**Fix:**
```bash
# Fix ownership
sudo chown -R $(whoami) ~/.claude/

# Reinstall
/plugin uninstall requirements-framework@requirements-framework-local
/plugin install requirements-framework@requirements-framework-local
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

**Cause:** Marketplace cache may be stale, or repo needs updating

**Fix:**
```bash
# Update repo
cd ~/Tools/claude-requirements-framework
git pull

# Sync version numbers
./sync-versions.sh --verify

# Update marketplace and reinstall
/plugin marketplace update requirements-framework-local
/plugin uninstall requirements-framework@requirements-framework-local
/plugin install requirements-framework@requirements-framework-local

# Verify version
/plugin list
```

**Expected:** Version should match what's in `plugins/requirements-framework/.claude-plugin/plugin.json`

### Plugin Directory Not Found

**Symptom:** install.sh says "Plugin directory not found at ..."

**Cause:** Old repo version or missing plugin files

**Fix:**
```bash
cd ~/Tools/claude-requirements-framework
git pull
git log --oneline -5 plugins/requirements-framework/

# Verify directory exists
ls -la plugins/requirements-framework/.claude-plugin/plugin.json
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

**Location:** `~/.claude/plugins/cache/requirements-framework-local/requirements-framework/2.0.5/`
**Purpose:** Provide agents, commands, and skills to satisfy requirements
**Components:**
- 17 agents (code review, workflow enforcement)
- 3 commands (pre-commit, quality-check, codex-review orchestrators)
- 5 skills (management and status)

**Installed by:** Marketplace installation (copied to cache)

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

For development, use the `--plugin-dir` flag to load the plugin directly from the repo:

```bash
# Launch Claude Code with plugin loaded from repo
claude --plugin-dir ~/Tools/claude-requirements-framework/plugins/requirements-framework
```

Changes to plugin files are immediately available (live reload):

```bash
# 1. Edit agent in repo
vim ~/Tools/claude-requirements-framework/plugins/requirements-framework/agents/code-reviewer.md

# 2. Changes are live immediately (--plugin-dir loads from repo)
# No restart needed - Claude Code auto-reloads plugins

# 3. Test in Claude Code
/requirements-framework:pre-commit code

# 4. Commit changes
cd ~/Tools/claude-requirements-framework
git add plugins/requirements-framework/agents/code-reviewer.md
git commit -m "feat(agent): enhance code-reviewer detection"
```

### Testing Changes

**Agent changes:**
```bash
# Edit agent
vim plugins/requirements-framework/agents/test-analyzer.md

# Test via command (agents invoked by commands)
/requirements-framework:pre-commit tests
```

**Command changes:**
```bash
# Edit command
vim plugins/requirements-framework/commands/pre-commit.md

# Test directly
/requirements-framework:pre-commit all
```

**Skill changes:**
```bash
# Edit skill
vim plugins/requirements-framework/skills/requirements-framework-status/skill.md

# Test via natural language
"Show requirements framework status"
```

### Development vs Production

**Development (--plugin-dir flag):**
- Changes to plugin files are immediately available
- No reinstall needed - Claude Code auto-reloads

**Production (Marketplace installation):**
- Changes require reinstall via marketplace commands:
  ```bash
  /plugin marketplace update requirements-framework-local
  /plugin uninstall requirements-framework@requirements-framework-local
  /plugin install requirements-framework@requirements-framework-local
  ```

**Hooks:** Always require sync (copied to `~/.claude/hooks/`)
```bash
./sync.sh status   # Check sync status
./sync.sh deploy   # Deploy hooks
```

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
- **[Plugin README](../plugins/requirements-framework/README.md)** - Plugin-specific usage guide

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

- **v2.0.5** - Current stable release with 10 agents, 3 commands, 5 skills
  - Plugin installation via install.sh
  - Auto-satisfy mechanism for requirements
  - Comprehensive code review suite
