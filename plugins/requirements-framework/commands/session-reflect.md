---
name: session-reflect
description: "Review current session and suggest improvements for future sessions"
argument-hint: "[scope]"
allowed-tools: ["Bash", "Glob", "Grep", "Read", "Write", "Edit", "Task", "AskUserQuestion"]
git_hash: ab4414d
---

# Session Learning Reflection

Analyze the current session to identify patterns, friction points, and improvement opportunities. Updates memories, skills, and commands to make future sessions more efficient.

**Arguments:** "$ARGUMENTS"

## Available Scopes:
- **(default)** - Full analysis with improvement recommendations
- **analyze-only** - Show analysis without applying any changes
- **quick** - Summary statistics only (no agent, fast)

## Deterministic Execution Workflow

Follow these steps in exact order. Do not skip steps.

### Step 1: Gather Session Context

Execute these commands to collect session data:

```bash
# Get project info
PROJECT_DIR=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")

echo "=== Project Context ==="
echo "Project: $PROJECT_DIR"
echo "Branch: $BRANCH"

# Find session ID from registry
echo ""
echo "=== Session Registry ==="
if [ -f ~/.claude/sessions.json ]; then
    cat ~/.claude/sessions.json | python3 -c "
import sys, json
d = json.load(sys.stdin)
sessions = d.get('sessions', {})
for sid, data in sessions.items():
    print(f\"Session {sid}: {data.get('project_dir', 'unknown')} on {data.get('branch', 'unknown')}\")
" 2>/dev/null || echo "Failed to parse registry"
else
    echo "No session registry found"
fi

# Find and display session metrics
echo ""
echo "=== Session Metrics Files ==="
SESSIONS_DIR="${PROJECT_DIR}/.git/requirements/sessions"
if [ -d "$SESSIONS_DIR" ]; then
    ls -la "$SESSIONS_DIR"/*.json 2>/dev/null || echo "No session files"

    # Show most recent session metrics
    LATEST=$(ls -t "$SESSIONS_DIR"/*.json 2>/dev/null | head -1)
    if [ -n "$LATEST" ]; then
        echo ""
        echo "=== Latest Session Metrics ==="
        cat "$LATEST"
    fi
else
    echo "No sessions directory found"
fi
```

If no session metrics found:
- Output "No session metrics available. Run some commands first to collect data."
- EXIT

### Step 2: Check Arguments and Execution Mode

Arguments received: "$ARGUMENTS"

**QUICK_MODE**=false
- Set to true if: $ARGUMENTS contains "quick"

**ANALYZE_ONLY**=false
- Set to true if: $ARGUMENTS contains "analyze-only"

### Step 3: Quick Mode (if enabled)

If QUICK_MODE is true:

Parse the session metrics JSON and output a summary:

```markdown
# Quick Session Summary

| Metric | Value |
|--------|-------|
| Session ID | [id] |
| Duration | [human-readable] |
| Tool Uses | [count] |
| Blocked | [count] ([percentage]%) |
| Requirements Satisfied | [count] |
| Errors | [count] |
| Skills Used | [count] |

## Top Tools
1. [tool]: [count] uses
2. ...

## Requirements Flow
- [req]: [status] (took [time]s)
```

Then EXIT - do not continue to full analysis.

### Step 4: Launch Session Analyzer Agent

If not QUICK_MODE:
  1. Use the Task tool to launch subagent_type="requirements-framework:session-analyzer"
  2. Provide the session metrics JSON as context
  3. Wait for completion
  4. Parse the output for recommendations

The agent will return:
- Session analysis summary
- Detected patterns with confidence scores
- Structured recommendations (JSON)

### Step 5: Present Recommendations to User

Display the analysis results:

```markdown
# Session Learning Report

## Session Summary
[From agent output]

## Detected Patterns
[From agent output - show patterns with HIGH/MEDIUM confidence]

## Recommended Improvements

Select which improvements to apply:
```

If ANALYZE_ONLY is true:
- Show all recommendations
- Output "Analysis complete. Run `/session-reflect` (without analyze-only) to apply changes."
- EXIT

### Step 6: Get User Selection

If there are recommendations with confidence ≥ 0.7:

Use AskUserQuestion to let user select:
- Show each recommendation as an option
- Allow multiple selections
- Include "Skip all" option
- Include "Apply all high-confidence" option

Example question format:
```
Which improvements would you like to apply?
□ Memory: Add TDD workflow pattern (.serena/memories/workflow-patterns.md)
□ Memory: Add ADR-004 reference (.serena/memories/frequently-referenced.md)
□ Skill: Update pre-commit triggers (plugins/.../skills/...)
□ Apply all high-confidence recommendations
□ Skip - just record this session
```

### Step 7: Apply Selected Updates

For each selected recommendation:

**Memory Updates** (target starts with `.serena/memories/`):
1. Check if target file exists
2. If exists: Append new content with timestamp header
3. If new: Create file with recommended content
4. Record change in learning history

Example append format:
```markdown

---
## Session Learning: [date] (Session [id])

[Recommended content]
```

**Skill Updates** (target contains `/skills/`):
1. Read current SKILL.md
2. Add new trigger patterns to description
3. Write updated file
4. Record change

**Command Updates** (target contains `/commands/`):
1. Read current command file
2. Add recommended section/argument
3. Write updated file
4. Record change

### Step 8: Record Learning History

After applying changes, update the learning history:

```bash
# Create learning history if it doesn't exist
HISTORY_FILE="${PROJECT_DIR}/.git/requirements/learning_history.json"
mkdir -p "$(dirname "$HISTORY_FILE")"

# The history file tracks all updates for rollback
```

Record each applied change with:
- timestamp
- session_id
- update type (memory/skill/command)
- target file
- action (create/append/update)
- content_hash (SHA256 of new content)
- previous_content_hash (for rollback)

### Step 9: Output Summary

After all updates applied:

```markdown
# Session Learning Complete

## Applied Updates
| # | Type | Target | Action |
|---|------|--------|--------|
| 1 | Memory | workflow-patterns.md | Created |
| 2 | Memory | frequently-referenced.md | Appended |

## Learning History
Changes recorded in `.git/requirements/learning_history.json`
Use `req learning rollback [id]` to undo any change.

## Next Steps
- These improvements will be available in your next session
- Run `/session-reflect quick` anytime for a quick status check
- The Stop hook will remind you to reflect before ending future sessions
```

## Output Format:

```markdown
# Session Learning Report

## Session Summary
- **Session ID**: [id]
- **Duration**: [time]
- **Branch**: [branch]
- **Activity**: [tool_count] tool uses, [blocked_count] blocked

## Metrics Overview
[Table of key metrics]

## Detected Patterns
[List of patterns found with confidence levels]

## Recommendations
[Numbered list with selection checkboxes]

## Applied Updates
[List of what was applied]

## Learning History
[Reference to rollback capability]
```

## Usage Examples:

```bash
/session-reflect                    # Full analysis with recommendations
/session-reflect analyze-only       # Analysis without applying changes
/session-reflect quick              # Quick summary statistics only
```

## Tips:

- Run at the end of a productive session to capture learnings
- Use `analyze-only` first to preview what would change
- Use `quick` for fast status checks during sessions
- All changes are recorded and can be rolled back with `req learning rollback`
- Memories are version-controlled in `.serena/memories/`
