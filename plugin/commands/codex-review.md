---
description: "AI-powered code review using OpenAI Codex"
argument-hint: "[focus]"
allowed-tools: ["Bash", "Task"]
git_hash: 000fe23
---

# Codex AI Code Review

Run OpenAI Codex AI code review on your changes.

**Arguments:** "$ARGUMENTS"
**Focus areas:** security, performance, bugs, style, all (default)

## Deterministic Execution Workflow

You MUST follow these steps in exact order. This ensures consistent, reliable Codex code review execution.

### Step 1: Parse Focus Area Argument

Extract and validate focus area from $ARGUMENTS.

**Valid focus areas**: security, performance, bugs, style, all

**Parsing logic**:

```bash
# Parse focus area (default to "all" if empty or invalid)
FOCUS_AREA="$ARGUMENTS"

# If empty, set to "all"
if [ -z "$FOCUS_AREA" ]; then
  FOCUS_AREA="all"
fi

# Validate against known focus areas
case "$FOCUS_AREA" in
  security|performance|bugs|style|all)
    echo "Focus area: $FOCUS_AREA"
    ;;
  *)
    echo "Unknown focus area '$FOCUS_AREA', defaulting to 'all'"
    FOCUS_AREA="all"
    ;;
esac
```

Store FOCUS_AREA value for Step 2.

### Step 2: Launch Codex Review Agent

Use the Task tool to launch the autonomous codex-review-agent:

**Agent**: codex-review-agent
**Subagent type**: `codex-review-agent`
**Prompt to agent**: "Perform Codex code review with focus area: $FOCUS_AREA"

The agent will autonomously:
1. **Check prerequisites**: Verify Codex CLI installed (`which codex`) and authenticated (`codex login --status`)
2. **Detect scope**: Check for uncommitted changes (`git status --porcelain`) or branch changes
3. **Execute Codex**: Run `codex review --uncommitted` or `codex review --base main` with optional `--focus $FOCUS_AREA`
4. **Parse results**: Extract findings by severity (🔴 Critical, 🟡 Medium, 🟢 Low)
5. **Handle errors**: Provide clear guidance for: not installed, not authenticated, no changes, API errors, rate limits

**Wait for agent completion** before proceeding to Step 3.

### Step 3: Check Agent Exit Status

After agent completes, evaluate whether it succeeded or encountered errors.

**Success conditions** (agent found issues OR no issues found):
- Agent completed review successfully
- Codex CLI ran without critical errors
- Results were parsed and presented

**Failure conditions** (do NOT satisfy requirement):
- Codex CLI not installed
- Not authenticated (user needs to run `codex login`)
- API errors or rate limit exceeded
- Agent encountered unrecoverable error

**Determination**: Based on agent output, determine if review was successful.

If agent output contains:
- "❌ Codex CLI not found" → FAILED (prerequisite not met)
- "🔐 Codex authentication required" → FAILED (prerequisite not met)
- "❌ Codex API Error" → FAILED (API issue)
- "⏱️  Rate Limit Reached" → FAILED (rate limit)
- Any other output with review results → SUCCESS

Set AGENT_SUCCESS flag:
- If successful review: AGENT_SUCCESS=true
- If failed with prerequisite/API error: AGENT_SUCCESS=false

### Step 4: Auto-Satisfy Requirement (Conditional)

**Only satisfy if agent succeeded** (AGENT_SUCCESS=true).

If AGENT_SUCCESS is true:
  ```bash
  req satisfy codex_reviewer
  ```

  Output to user:
  ```
  ✅ Auto-satisfied 'codex_reviewer' requirement
  ```

If AGENT_SUCCESS is false:
  Output to user:
  ```
  ⚠️  Codex review incomplete - requirement NOT satisfied

  **Reason**: Agent encountered an error (see output above)
  **To proceed**: Fix the issue and run `/requirements-framework:codex-review` again
  ```

**Do not run `req satisfy` if agent failed** - this ensures requirements are only satisfied when actual review occurred.

## Integration with Requirements Framework

**Satisfies**: `codex_reviewer` requirement
**Scope**: Configured in project's `.claude/requirements.yaml` (typically single_use or session)
**Auto-satisfaction**: Via `req satisfy codex_reviewer` command after successful agent completion
**Check status**: Run `req status` to verify requirement state

## Integration with Other Commands

This command complements `/requirements-framework:quality-check`:

- **codex-review**: AI-powered perspective (patterns, novel insights, OpenAI Codex analysis)
- **quality-check**: 8 rule-based review agents (systematic, objective, deterministic)
- **Together**: Comprehensive pre-PR coverage

## Usage Examples

```bash
# Review all changes with all focus areas (default)
/requirements-framework:codex-review

# Focus on security vulnerabilities
/requirements-framework:codex-review security

# Focus on performance optimization opportunities
/requirements-framework:codex-review performance

# Focus on potential bugs and logic errors
/requirements-framework:codex-review bugs

# Focus on code style and best practices
/requirements-framework:codex-review style
```

## Error Handling (Autonomous Agent)

The codex-review-agent handles all error cases autonomously - you don't need to implement error handling in this command:

| Error Condition | Agent Response |
|----------------|----------------|
| Codex not installed | Provides installation instructions (`npm install -g @openai/codex` or `brew install`) |
| Not authenticated | Guides user through `codex login` process |
| No changes to review | Reports friendly "no changes to review" message with options |
| API errors | Suggests retry with wait time, checks network/service status |
| Rate limits | Provides wait guidance (5-10 minutes) with retry instructions |
| Empty output | Reports "✅ No Issues Found" (Codex found no problems) |

All error cases result in AGENT_SUCCESS=false in Step 3, preventing requirement satisfaction.

## TDD Workflow Integration

This command fits into the pre-PR workflow:

1. Write failing test ✓
2. `/requirements-framework:pre-commit tests` - Verify test quality ✓
3. Write implementation ✓
4. `/requirements-framework:pre-commit tools code errors` - Check implementation ✓
5. Refactor ✓
6. **`/requirements-framework:codex-review`** ← AI perspective (you are here)
7. `/requirements-framework:quality-check` ← Comprehensive 8-agent systematic review
8. Create PR ✓

## Expected Agent Output Format

The agent will provide structured output like:

```
🤖 Codex AI Code Review Results

📊 Summary:
- Files reviewed: 5
- Total findings: 3 (0 critical, 1 high, 2 medium)

🟡 Medium Severity (2):

  Performance: N+1 query pattern detected
  File: src/api/users.py:45

  Suggestion: Use select_related() to reduce database queries

  Style: Inconsistent naming convention
  File: src/utils/helpers.py:12

  Recommendation: Use snake_case for function names per PEP-8

✅ Review complete! No critical issues found. Ready to proceed!
```

After this output, if successful, the command will output:
```
✅ Auto-satisfied 'codex_reviewer' requirement
```

## Command Design Notes

**Why this is a command (not a skill)**:
- Commands reduce session context pressure vs skill wrappers
- Direct agent invocation (no extra indirection layer)
- Follows ADR-006 unified plugin architecture pattern
- Uses explicit `req satisfy` CLI (not hook-based auto-satisfaction)

**Why deterministic steps**:
- Follows ADR-007 deterministic command orchestrator pattern
- Explicit bash commands for argument parsing
- Clear conditionals for success/failure detection
- Predictable, testable, reliable execution

**Agent autonomy**:
- Agent has `autonomous: true` in frontmatter
- Runs without manual input (prerequisite checks are informational only)
- Proper tool permissions: Bash, Read, Grep, Glob (sufficient for all operations)
