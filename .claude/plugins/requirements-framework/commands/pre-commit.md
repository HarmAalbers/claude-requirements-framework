---
description: "Quick code review before committing (code + error handling)"
argument-hint: "[aspects]"
allowed-tools: ["Bash", "Glob", "Grep", "Read", "Task"]
git_hash: 57d0c1a
---

# Pre-Commit Review

Run focused code quality checks on unstaged/staged changes before committing.

**Arguments:** "$ARGUMENTS"

## Default Review (no args):
Run three essential checks:
- **tool-validator** - Execute pyright/ruff/eslint (same as CI)
- **code-reviewer** - CLAUDE.md compliance, bugs, code quality
- **silent-failure-hunter** - Error handling audit

## Available Aspects:
- **tools** - Execute linting/type-checking tools (tool-validator agent) ⚡ NEW
- **compat** - Check backward compatibility (backward-compatibility-checker agent) ⚡ NEW
- **code** - General code quality (code-reviewer agent)
- **errors** - Error handling audit (silent-failure-hunter agent)
- **tests** - Test coverage check (test-analyzer agent)
- **types** - Type design analysis (type-design-analyzer agent)
- **comments** - Comment accuracy (comment-analyzer agent)
- **simplify** - Code simplification (code-simplifier agent)
- **all** - Run all reviews (includes tools + compat)
- **parallel** - Run agents in parallel (faster)

## Deterministic Execution Workflow

You MUST follow these steps in exact order. Do not skip steps or interpret - execute as written.

### Step 1: Identify Changes to Review

Execute these bash commands to get the scope:

```bash
git diff --cached --name-only --diff-filter=ACMR > /tmp/review_scope.txt 2>&1
if [ ! -s /tmp/review_scope.txt ]; then
  git diff --name-only --diff-filter=ACMR > /tmp/review_scope.txt 2>&1
fi
```

Then check the result:
- If /tmp/review_scope.txt is empty: Output "No changes to review" and EXIT
- Otherwise: Read the file list and continue

### Step 2: Parse Arguments and Set Flags

Arguments received: "$ARGUMENTS"

Initialize all flags to false, then set based on arguments:

**RUN_TOOL_VALIDATOR**=false
- Set to true if: $ARGUMENTS is empty OR contains "tools" OR contains "all"

**RUN_CODE_REVIEWER**=false
- Set to true if: $ARGUMENTS is empty OR contains "code" OR contains "all"

**RUN_SILENT_FAILURE_HUNTER**=false
- Set to true if: $ARGUMENTS is empty OR contains "errors" OR contains "all"

**RUN_BACKWARD_COMPATIBILITY_CHECKER**=false
- Set to true if: $ARGUMENTS contains "compat" OR contains "all"

**RUN_TEST_ANALYZER**=false
- Set to true if: $ARGUMENTS contains "tests" OR contains "all"

**RUN_TYPE_DESIGN_ANALYZER**=false
- Set to true if: $ARGUMENTS contains "types" OR contains "all"

**RUN_COMMENT_ANALYZER**=false
- Set to true if: $ARGUMENTS contains "comments" OR contains "all"

**RUN_CODE_SIMPLIFIER**=false
- Set to true if: $ARGUMENTS contains "simplify" OR contains "all"

**PARALLEL_MODE**=false
- Set to true if: $ARGUMENTS contains "parallel"

### Step 3: Execute Tool Validator (if enabled) - BLOCKING GATE

If RUN_TOOL_VALIDATOR is true:
  1. Use the Task tool to launch subagent_type="pre-pr-review:tool-validator"
  2. Wait for completion
  3. Parse the output for CRITICAL severity issues
  4. If CRITICAL tool errors found (pyright errors, ruff errors, eslint errors):
     - Output the tool-validator findings immediately
     - Return verdict: "❌ **FIX TOOL ERRORS FIRST** - Cannot proceed with AI review until objective tool checks pass"
     - STOP - do not execute any other agents
  5. If no critical errors: Continue to next step

### Step 4: Execute Selected Review Agents

Create a list of agents to run based on flags set in Step 2.

**Agents to launch** (only if their flag is true):
- pre-pr-review:code-reviewer
- pre-pr-review:silent-failure-hunter
- pre-pr-review:backward-compatibility-checker
- pre-pr-review:test-analyzer
- pre-pr-review:type-design-analyzer
- pre-pr-review:comment-analyzer

**Execution mode**:

If PARALLEL_MODE is true:
  - You MUST launch all selected agents in a SINGLE message with multiple Task tool calls
  - This enables true parallel execution
  - Wait for ALL agents to complete before proceeding

If PARALLEL_MODE is false:
  - Launch agents sequentially, one at a time
  - Wait for each to complete before launching the next
  - Order: code-reviewer → silent-failure-hunter → backward-compatibility-checker → test-analyzer → type-design-analyzer → comment-analyzer

### Step 5: Execute Code Simplifier (if enabled) - ALWAYS LAST

If RUN_CODE_SIMPLIFIER is true:
  1. Use the Task tool to launch subagent_type="pre-pr-review:code-simplifier"
  2. This MUST run after all other agents complete
  3. Code simplifier polishes code that has passed review

### Step 6: Aggregate Results

After all agents complete, aggregate their findings:

1. **Count by severity**:
   - CRITICAL_COUNT = number of CRITICAL issues across all agents
   - IMPORTANT_COUNT = number of IMPORTANT/HIGH issues across all agents
   - SUGGESTION_COUNT = number of SUGGESTION/MEDIUM/LOW issues across all agents

2. **Group by agent**:
   - Preserve which agent found each issue
   - Include file:line references

3. **Format output** using the template in "Output Format" section below

### Step 7: Provide Verdict

Based on aggregated counts, provide ONE of these verdicts:

If CRITICAL_COUNT > 0:
  **Verdict**: ❌ **FIX ISSUES FIRST**
  - List all critical issues
  - Do not commit until resolved

Else if IMPORTANT_COUNT > 5:
  **Verdict**: ⚠️ **REVIEW IMPORTANT ISSUES**
  - Consider fixing before commit
  - Proceeding is possible but not recommended

Else if IMPORTANT_COUNT > 0:
  **Verdict**: ⚠️ **MINOR ISSUES FOUND**
  - Can commit, but review recommended
  - List important issues for context

Else:
  **Verdict**: ✅ **READY TO COMMIT**
  - Code meets quality standards
  - Safe to proceed

## Agent Selection Logic:

- If no args or `tools` specified → tool-validator (runs first - objective checks)
- If no args or `code` specified → code-reviewer
- If no args or `errors` specified → silent-failure-hunter
- If `compat` specified → backward-compatibility-checker
- If `tests` specified → test-analyzer
- If `types` specified → type-design-analyzer
- If `comments` specified → comment-analyzer
- If `simplify` specified → code-simplifier
- If `all` specified → all applicable agents (including tools + compat)
- If `parallel` specified → run selected agents in parallel

## Output Format:

```markdown
# Pre-Commit Review Summary

## Scope
[Files reviewed]

## Critical Issues (X found)
- [agent]: Issue description [file:line]

## Important Issues (X found)
- [agent]: Issue description [file:line]

## Suggestions (X found)
- [agent]: Suggestion [file:line]

## Recommendation
✅ READY TO COMMIT / ❌ FIX ISSUES FIRST
```

## Usage Examples:

```bash
/pre-pr-review:pre-commit                    # Default (tools + code + errors)
/pre-pr-review:pre-commit tools              # Just run linting/type-checking
/pre-pr-review:pre-commit compat             # Just check backward compatibility
/pre-pr-review:pre-commit all                # Comprehensive (all 8 agents)
/pre-pr-review:pre-commit tests types        # Specific aspects
/pre-pr-review:pre-commit tools compat code  # Custom combination
/pre-pr-review:pre-commit all parallel       # Fast comprehensive
```

## Tips:

- **Start with tools** - catches objective errors (pyright, ruff) before AI analysis
- **Use compat** - when renaming fields or changing schemas
- Run early, run often - catch issues before they compound
- Address critical issues before committing
- Use `simplify` only after code passes other reviews
- For TDD: run `tests` first to verify test quality
- **tools + compat together** catch most CI failures locally
