---
name: codex-review
description: "AI-powered code review using OpenAI Codex"
argument-hint: "[focus]"
allowed-tools: ["Bash", "Task"]
git_hash: 4b624f2
---

> **Workflow position**: a conditional side-quest on the Validate and Review team nodes (ADR-022) — surfaced as *available here*, with no gate of its own. Run directly any time for an independent external AI check.

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

### Step 3: Report Results

After the agent completes, present its findings to the user.

If the agent's output indicates the review could **not** actually run — it contains any of:
- "❌ Codex CLI not found" (prerequisite not met)
- "🔐 Codex authentication required" (prerequisite not met)
- "❌ Codex API Error" (API issue)
- "⏱️  Rate Limit Reached" (rate limit)

then tell the user the review did not complete and they should fix the issue and re-run `/requirements-framework:codex-review`. Otherwise, present the review results normally.

### Step 4: No Gate (Conditional Side-Quest)

Codex review satisfies **no** requirement gate. Under the ADR-022 typed 7-node workflow it is a conditional side-quest surfaced on the Validate and Review team nodes, not a gated step, and `auto-satisfy-skills.py` deliberately maps no requirement to it. There is nothing to `req satisfy` or `req clear` here — just present the findings.

## Integration with Requirements Framework

**Gate**: none — Codex is a conditional side-quest (ADR-022), not a gated step.
**Surfaced by**: the Validate (`/arch-review`) and Review (`/deep-review`) team nodes list it as *available here*; it never auto-fires and never blocks.
**Check status**: Run `req status` to see the current workflow phase.

## Integration with Other Commands

This command complements `/requirements-framework:deep-review`:

- **codex-review**: AI-powered perspective (patterns, novel insights, OpenAI Codex analysis)
- **deep-review**: Cross-validated team-based review (systematic, collaborative debate)
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

When the agent reports a prerequisite/API failure, surface it to the user per Step 3. Codex satisfies no gate (see Step 4), so a failed run leaves the workflow state unchanged — just re-run once the issue is fixed.

## TDD Workflow Integration

This command fits into the pre-PR workflow:

1. Write failing test ✓
2. `/requirements-framework:pre-commit tests` - Verify test quality ✓
3. Write implementation ✓
4. `/requirements-framework:pre-commit tools code errors` - Check implementation ✓
5. Refactor ✓
6. **`/requirements-framework:codex-review`** ← AI perspective (you are here)
7. Create PR ✓

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

No requirement gate flips on completion — Codex is a conditional side-quest (see Step 4).

## Command Design Notes

**Why this is a command (not a skill)**:
- Commands reduce session context pressure vs skill wrappers
- Direct agent invocation (no extra indirection layer)
- Follows ADR-006 unified plugin architecture pattern
- No gate to satisfy — Codex is a conditional side-quest (ADR-022), unlike the gated review commands

**Why deterministic steps**:
- Follows ADR-007 deterministic command orchestrator pattern
- Explicit bash commands for argument parsing
- Predictable, testable, reliable execution

**Agent autonomy**:
- Agent is designed to run without manual input (prerequisite checks are informational only)
- Handles all error cases and edge conditions internally
- Proper tool permissions: Bash, Read, Grep, Glob (sufficient for all operations)
