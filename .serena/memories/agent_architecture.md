# Agent Architecture

> How plugin agents are structured, configured, and invoked

## Location & Discovery

**Agent files**: `plugin/agents/*.md` (markdown with YAML frontmatter)
**Registration**: `plugin/.claude-plugin/plugin.json` (must list all agents)

## YAML Frontmatter Structure

```yaml
---
name: agent-name              # Required: identifier
description: "Triggers..."    # Required: when to invoke this agent
model: inherit                # Optional: haiku/sonnet/opus/inherit
color: blue                   # Optional: UI color
allowed-tools: ["Read", "Edit"]  # Optional: tool whitelist
git_hash: abc1234            # Required: version tracking
---
```

## Agent Patterns

### 1. Review Agents (code-reviewer, test-analyzer)
- **Model**: inherit (usually Sonnet/Opus)
- **Tools**: Read, Bash, Glob, Grep (no modifications)
- **Output**: Structured reports with confidence scores ≥80

### 2. Tool Execution Agents (tool-validator)
- **Model**: haiku (fast)
- **Tools**: All tools (including Bash)
- **Purpose**: Run actual dev tools (pyright, ruff, eslint)

### 3. Auto-Fix Agents
- **Model**: haiku (fast)
- **Tools**: Include Edit
- **Purpose**: Modify files to fix simple issues

### 4. Blocking/Governance Agents (adr-guardian)
- **Model**: inherit (Opus for authority)
- **Tools**: Restricted (no Bash)
- **Authority**: Can BLOCK work with verdicts

## Invocation Methods

### 1. Via Commands (Primary)
```bash
/requirements-framework:pre-commit  # Runs: tool-validator, code-reviewer, silent-failure-hunter
```

### 2. Via Natural Language (Skills)
Agent descriptions trigger on matching phrases

### 3. Programmatically (Hooks)
Auto-satisfy mechanism invokes agents when skills complete

## Example Agent: comment-cleaner

```yaml
---
name: comment-cleaner
description: Use this agent to remove useless comments...
model: haiku
allowed-tools: ["Read", "Edit", "Glob", "Grep", "Bash"]
git_hash: uncommitted
---

You are a comment cleanup specialist...

## Step 1: Get Staged Files
git diff --cached --name-only

## Step 2: Analyze Comments
[Detect useless comments]

## Step 3: Auto-Fix
Use Edit tool to remove
```

## Command Orchestration

Commands coordinate multiple agents (see `plugin/commands/pre-commit.md`):

```markdown
## Step 1: Get scope (staged/unstaged files)
## Step 2: Parse arguments (which agents to run)
## Step 3: Execute agents (sequential or parallel)
## Step 4: Aggregate results
## Step 5: Provide verdict
```

## Version Tracking

All agents include `git_hash`:
- `abc1234` - Committed, no changes
- `abc1234*` - Has uncommitted changes
- `uncommitted` - Never committed

Update with: `./update-plugin-versions.sh`

## Related Files

- `plugin/agents/*.md` - Agent definitions
- `plugin/.claude-plugin/plugin.json` - Agent registration
- `plugin/commands/*.md` - Commands that orchestrate agents
