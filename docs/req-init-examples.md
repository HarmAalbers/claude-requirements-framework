# `req init` Usage Examples

Comprehensive examples showing how to use the enhanced `req init` command for different scenarios.

## Scenario 1: First-Time Global Setup

**Situation**: You've just installed the framework and want to set up global defaults for all your projects.

```bash
# Run from anywhere
cd ~/.claude
req init
```

**Interactive Flow**:
```
🌍 Global Requirements Framework Setup
   Setting up defaults for all your projects
──────────────────────────────────────────────────

Detecting environment:
  ✓ Git repository at /Users/you/.claude

How would you like to configure?
  > 1. Quick Preset - Choose from preset profiles (recommended)
    2. Custom Selection - Pick specific features
    3. Manual Setup - Start minimal, configure later

[Select: 1 - Quick Preset]

Choose a preset profile:
  > 1. advanced - All features (recommended for global)
    2. relaxed - Baseline requirements only
    3. minimal - Framework enabled, configure later

[Select: 1 - advanced]

Preview:
──────────────────────────────────────────────────
requirements:
  commit_plan:
    enabled: true
    type: blocking
    scope: session
    ...
  adr_reviewed:
    enabled: true
    ...
  branch_size_limit:
    enabled: true
    type: dynamic
    calculator: branch_size_calculator
    thresholds:
      warn: 250
      block: 400
    ...
  pre_commit_review:
    enabled: true
    scope: single_use
    ...
  pre_pr_review:
    enabled: true
    scope: single_use
    ...
──────────────────────────────────────────────────

Create requirements.yaml? [Y/n]: y

✅ Created Global config (advanced preset)
   /Users/you/.claude/requirements.yaml

💡 Next steps:
   • Run 'req status' to see your requirements
   • Make changes - you'll be prompted to satisfy requirements
   • Edit requirements.yaml to customize
```

**Result**: You now have a comprehensive global config showcasing all framework capabilities!

---

## Scenario 2: Project Setup (With Global Config)

**Situation**: You have a global config and want to set up a new project to inherit those defaults.

```bash
cd /Users/you/my-project
req init
```

**Interactive Flow**:
```
🚀 Project Requirements Setup
   Configuring project-specific requirements
──────────────────────────────────────────────────

Detecting environment:
  ✓ Git repository at /Users/you/my-project
  ✓ .claude/ directory exists
  ✓ Global config found
     Project will inherit from global defaults

How would you like to configure?
  > 1. Quick Preset - Choose from preset profiles (recommended)
    2. Custom Selection - Pick specific features
    3. Manual Setup - Start minimal, configure later

[Select: 1 - Quick Preset]

Choose a preset profile:
  > 1. inherit - Use global defaults (recommended)
    2. relaxed - Override with relaxed preset
    3. minimal - Start minimal

[Select: 1 - inherit]

Preview:
──────────────────────────────────────────────────
inherit: true
requirements: {}
version: '1.0'
enabled: true
──────────────────────────────────────────────────

Create requirements.yaml? [Y/n]: y

✅ Created project config (inherit preset)
   /Users/you/my-project/.claude/requirements.yaml
```

**Result**: Minimal config that inherits all 7 requirements from your global config!

---

## Scenario 3: Project Setup (No Global Config)

**Situation**: Setting up a project without having created global defaults yet.

```bash
cd /Users/you/my-project
req init
```

**Interactive Flow**:
```
🚀 Project Requirements Setup
   Setting up project requirements
──────────────────────────────────────────────────

Detecting environment:
  ✓ Git repository at /Users/you/my-project
  ○ .claude/ directory will be created
  ⚠ No global config found
     Tip: Run 'req init' to create global defaults first

How would you like to configure?
  > 1. Quick Preset - Choose from preset profiles (recommended)
    2. Custom Selection - Pick specific features
    3. Manual Setup - Start minimal, configure later

[Select: 1 - Quick Preset]

Choose a preset profile:
    1. inherit - Use global when created
  > 2. relaxed - Standalone requirements
    3. minimal - Framework enabled, no requirements

[Select: 2 - relaxed]
```

**Note**: The wizard warns you that no global config exists and suggests creating one first, but still lets you proceed with a standalone project config.

---

## Scenario 4: Custom Feature Selection

**Situation**: You want specific requirements, not a full preset.

```bash
cd /Users/you/my-project
req init
```

**Interactive Flow**:
```
How would you like to configure?
    1. Quick Preset - Choose from preset profiles (recommended)
  > 2. Custom Selection - Pick specific features
    3. Manual Setup - Start minimal, configure later

[Select: 2 - Custom Selection]

Select features to enable:
  ✓ Commit Planning - Require planning before code changes
  ✓ ADR Review - Check Architecture Decision Records
  ☐ Protected Branches - Prevent edits on main/master
  ✓ Branch Size Limits - Warn/block large PRs
  ☐ Pre-Commit Review - Review before every commit
  ✓ Pre-PR Review - Quality check before PR creation

Preview:
──────────────────────────────────────────────────
inherit: true
requirements:
  commit_plan:
    enabled: true
    ...
  adr_reviewed:
    enabled: true
    ...
  branch_size_limit:
    enabled: true
    type: dynamic
    ...
  pre_pr_review:
    enabled: true
    scope: single_use
    ...
──────────────────────────────────────────────────

Create requirements.yaml? [Y/n]: y

✅ Created project config (custom 4 features)
```

**Result**: Tailored config with exactly the features you want!

---

## Scenario 5: Non-Interactive/Automated Setup

**Situation**: Setting up multiple projects in a script or CI/CD pipeline.

```bash
# Global setup
req init --yes --preset advanced

# Project setup (inherit from global)
cd /path/to/project1
req init --yes --preset inherit

cd /path/to/project2
req init --yes --preset inherit

# Standalone project (specific preset)
cd /path/to/standalone-project
req init --yes --preset relaxed
```

**Result**: Fast automated setup without interactive prompts!

---

## Scenario 6: Local Personal Overrides

**Situation**: Your team uses the project config, but you want personal overrides.

```bash
cd /Users/you/team-project
req init --local
```

**Interactive Flow**:
```
📝 Local Requirements Override Setup
   Creating personal overrides (gitignored)
──────────────────────────────────────────────────

Detecting environment:
  ✓ Git repository at /Users/you/team-project
  ✓ .claude/ directory exists
  ⚠ Local config exists

How would you like to configure?
  > 1. Quick Preset - Choose from preset profiles (recommended)
    2. Custom Selection - Pick specific features
    3. Manual Setup - Start minimal, configure later

[For local, only minimal preset is offered]

Choose a preset profile:
  > 1. minimal - Override specific settings only

Preview:
──────────────────────────────────────────────────
version: '1.0'
enabled: true
requirements: {}
──────────────────────────────────────────────────

Create requirements.local.yaml? [Y/n]: y
```

**Note**: Local configs always deep-merge with project and global, so start minimal and add only your personal overrides using `req config`.

---

## Scenario 7: Preview Before Creating

**Situation**: You want to see what a preset looks like before committing to it.

```bash
# Preview advanced preset
req init --preset advanced --preview

# Preview inherit preset
req init --preset inherit --preview

# Preview for local config
req init --local --preset minimal --preview
```

**Output**:
```
📋 Preview: Project config (advanced preset)
──────────────────────────────────────────────────
requirements:
  commit_plan:
    enabled: true
    type: blocking
    scope: session
    ...
  [... full config displayed ...]
──────────────────────────────────────────────────
ℹ️  Would create: /path/to/project/.claude/requirements.yaml
```

**Result**: See the full configuration without writing any files!

---

## Scenario 8: Overwrite Existing Config

**Situation**: You want to change your preset after initial setup.

```bash
# Try to init when config exists
req init --preset advanced

# Output: ⚠️  Config already exists: .claude/requirements.yaml

# Force overwrite
req init --preset advanced --force
```

**Result**: Replaces existing config with new preset (use with caution!).

---

## Comparison: Before vs After

### Before Enhancement

```bash
$ req init
Choose a preset profile:
  > 1. relaxed - commit_plan only
    2. strict - commit_plan + protected_branch
    3. minimal - empty

[Limited to 2 requirement types, no feature discovery]
```

### After Enhancement

```bash
$ req init
How would you like to configure?
  > 1. Quick Preset
    2. Custom Selection  [NEW!]
    3. Manual Setup

[Select Quick Preset → Context-aware options]

# In global setup:
  > 1. advanced - All features [NEW! DEFAULT]
    2. relaxed
    3. minimal

# In project with global:
  > 1. inherit - Use global [NEW! DEFAULT]
    2. relaxed
    3. minimal

[Discover all 7 requirement types including dynamic, single-use, guards]
```

---

## Advanced Usage

### Custom Feature Combinations

Mix and match requirements using Custom Selection:

- **Solo Developer**: commit_plan + branch_size_limit
- **Team Project**: commit_plan + protected_branch + pre_pr_review
- **Open Source**: commit_plan + adr_reviewed + github_ticket + pre_pr_review
- **Enterprise**: All features enabled

### Workflow Recommendations

**Recommended Setup Pattern:**

1. **Global setup** (once):
   ```bash
   cd ~/.claude
   req init --preset advanced
   ```

2. **Each project** (simple):
   ```bash
   cd /path/to/project
   req init --preset inherit
   ```

3. **Personal overrides** (optional):
   ```bash
   req init --local
   # Then: req config <requirement> --disable (or other modifications)
   ```

This pattern gives you:
- Consistent defaults across all projects (global)
- Easy per-project inheritance (inherit preset)
- Personal flexibility (local overrides)

---

## Feature Discovery

The `advanced` preset is designed to be an **educational tool**. When you run it, you'll see:

1. **Blocking requirements** (commit_plan, adr_reviewed)
2. **Guard requirements** (protected_branch) - prevents operations
3. **Dynamic requirements** (branch_size_limit) - auto-calculated with thresholds
4. **Single-use requirements** (pre_commit_review, pre_pr_review) - re-satisfy each time
5. **Branch-scoped requirements** (github_ticket, disabled) - once per branch
6. **Tool-specific triggers** with command patterns (git commit, gh pr create)
7. **Hooks configuration** (stop hook verification)

You can start with `advanced`, see everything in action, then create `inherit` configs for new projects - you've learned the system through doing!

---

## Tips

- **Preview first**: Always use `--preview` when trying a new preset
- **Start global**: Create `~/.claude/requirements.yaml` with `advanced` first
- **Projects inherit**: Use `inherit` preset for projects (simple and consistent)
- **Local for personal**: Use local configs for personal workflow preferences
- **Custom for power users**: Use Custom Selection when you know exactly what you want
- **Force carefully**: `--force` overwrites existing configs - use sparingly
