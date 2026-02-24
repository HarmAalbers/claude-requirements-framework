---
name: quality-check
description: "Comprehensive quality review before creating PR"
argument-hint: "[parallel]"
allowed-tools: ["Bash", "Glob", "Grep", "Read", "Task"]
git_hash: 3f13d85
---

# Pre-PR Quality Check

> **For cross-validated review with agent debate, use `/deep-review` instead.**
> This command is a lightweight alternative that runs agents independently without cross-validation.

Comprehensive code quality review before creating a pull request. This runs ALL review agents to ensure your code is ready for PR.

**Mode:** "$ARGUMENTS" (use 'parallel' for faster execution)

## This runs ALL 9 agents:

1. **tool-validator** ⚡ NEW - Execute pyright/ruff/eslint (catches CI errors)
2. **backward-compatibility-checker** ⚡ NEW - Detects breaking schema changes
3. **code-reviewer** - CLAUDE.md compliance, bugs, general code quality
4. **silent-failure-hunter** - Error handling audit, silent failure detection
5. **test-analyzer** - Test coverage quality and completeness
6. **type-design-analyzer** - Type invariants and encapsulation (if types changed)
7. **comment-analyzer** - Comment accuracy and documentation (if comments changed)
8. **frontend-reviewer** - React/frontend best practices and a11y (if frontend files changed)
9. **code-simplifier** - Final polish for clarity and maintainability

## Deterministic Execution Workflow

You MUST follow these steps in exact order. This is a comprehensive review - execute all steps precisely.

### Step 1: Identify Changes to Review

Execute these bash commands:

```bash
git diff --cached --name-only --diff-filter=ACMR > /tmp/pr_review_scope.txt 2>&1
if [ ! -s /tmp/pr_review_scope.txt ]; then
  git diff --name-only --diff-filter=ACMR > /tmp/pr_review_scope.txt 2>&1
fi
```

If /tmp/pr_review_scope.txt is empty: Output "No changes to review" and EXIT.

### Step 2: Detect File Types and Set Applicability Flags

Execute these detection commands to determine which agents apply:

```bash
# Check for test files
grep -E '(test_|_test\.py|\.test\.|\.spec\.)' /tmp/pr_review_scope.txt > /tmp/has_tests.txt 2>&1

# Check for type definitions in the diff
git diff --cached | grep -E '(class.*BaseModel|interface |type |dataclass|TypedDict|NamedTuple)' > /tmp/has_types.txt 2>&1

# Check for comment changes
git diff --cached --unified=0 | grep -E '^[+].*#|^[+].*//|^[+].*"""' > /tmp/has_comments.txt 2>&1

# Check for schema/model changes (Pydantic, database models)
git diff --cached | grep -E '(BaseModel|Field\(|Column\(|Table\(|alembic)' > /tmp/has_schemas.txt 2>&1

# Check for frontend files
grep -E '\.(tsx|jsx|css|scss)$' /tmp/pr_review_scope.txt > /tmp/has_frontend.txt 2>&1 || true
```

Set applicability flags based on detection results:
- **HAS_TEST_FILES** = true if /tmp/has_tests.txt is not empty
- **HAS_TYPE_CHANGES** = true if /tmp/has_types.txt is not empty
- **HAS_COMMENT_CHANGES** = true if /tmp/has_comments.txt is not empty
- **HAS_SCHEMA_CHANGES** = true if /tmp/has_schemas.txt is not empty
- **HAS_FRONTEND_FILES** = true if /tmp/has_frontend.txt is not empty

### Step 3: Parse Execution Mode

Arguments received: "$ARGUMENTS"

**PARALLEL_MODE**=false
- Set to true if: $ARGUMENTS contains "parallel"

### Step 4: Execute Tool Validator - BLOCKING GATE (ALWAYS RUNS FIRST)

This step is REQUIRED and MUST run before any other agents:

1. Use the Task tool to launch subagent_type="requirements-framework:tool-validator"
2. Pass context: File list from /tmp/pr_review_scope.txt
3. Wait for completion
4. Parse output for CRITICAL severity issues

If CRITICAL tool errors found:
  - Output tool-validator findings immediately
  - Return verdict: "❌ **FIX TOOL ERRORS FIRST** - pyright/ruff/eslint must pass before AI review"
  - STOP - do not execute any other agents

If no critical errors: Continue to Step 5

### Step 5: Execute Backward Compatibility Checker (if applicable)

If HAS_SCHEMA_CHANGES is true:
  1. Use the Task tool to launch subagent_type="requirements-framework:backward-compatibility-checker"
  2. Wait for completion
  3. Store results for aggregation

If HAS_SCHEMA_CHANGES is false:
  - Skip this agent (not applicable)

### Step 6: Execute Core Review Agents (ALWAYS RUN)

The following agents ALWAYS run (they apply to all code):
- requirements-framework:code-reviewer
- requirements-framework:silent-failure-hunter

**Execution mode**:

If PARALLEL_MODE is true:
  - Launch BOTH agents in a SINGLE message with multiple Task tool calls
  - Wait for both to complete

If PARALLEL_MODE is false:
  - Launch code-reviewer, wait for completion
  - Launch silent-failure-hunter, wait for completion

### Step 7: Execute Conditional Review Agents (based on applicability)

Build a list of agents to run based on flags:

**Conditional agents** (only launch if applicable):
- If HAS_TEST_FILES is true: requirements-framework:test-analyzer
- If HAS_TYPE_CHANGES is true: requirements-framework:type-design-analyzer
- If HAS_COMMENT_CHANGES is true: requirements-framework:comment-analyzer
- If HAS_FRONTEND_FILES is true: requirements-framework:frontend-reviewer

**Execution mode**:

If PARALLEL_MODE is true:
  - Launch all applicable agents in a SINGLE message with multiple Task tool calls
  - Wait for all to complete

If PARALLEL_MODE is false:
  - Launch each agent sequentially in this order:
    1. test-analyzer (if applicable)
    2. type-design-analyzer (if applicable)
    3. comment-analyzer (if applicable)

### Step 8: Execute Code Simplifier - FINAL POLISH (ALWAYS RUNS LAST)

This step is REQUIRED and MUST run after all review agents complete:

1. Use the Task tool to launch subagent_type="requirements-framework:code-simplifier"
2. Wait for completion
3. Code simplifier polishes code that has passed all other reviews

### Step 9: Aggregate Results from All Agents

After all agents complete, aggregate their findings:

1. **Count by severity across all agents** (all agents use ADR-013 standard format):
   - CRITICAL_COUNT = total CRITICAL issues
   - IMPORTANT_COUNT = total IMPORTANT issues
   - SUGGESTION_COUNT = total SUGGESTION issues

2. **Group by severity, then by agent**:
   - Preserve which agent found each issue
   - Include file:line references for all issues

3. **Track agents run**:
   - List which agents executed
   - Note which agents were skipped (and why)

### Step 10: Provide Comprehensive Verdict

Based on aggregated counts, provide ONE of these verdicts:

If CRITICAL_COUNT > 0:
  **Verdict**: ❌ **FIX ISSUES FIRST**
  - List all critical issues with checkboxes
  - Provide specific file:line references
  - Recommend: Fix all critical issues and run quality-check again

Else if IMPORTANT_COUNT > 8:
  **Verdict**: ⚠️ **SIGNIFICANT ISSUES FOUND**
  - Too many important issues for a clean PR
  - Recommend: Address major issues before creating PR
  - List top important issues

Else if IMPORTANT_COUNT > 0:
  **Verdict**: ⚠️ **MINOR ISSUES FOUND**
  - Can create PR but reviewer will likely request changes
  - Consider fixing important issues now to avoid review cycles
  - List important issues

Else:
  **Verdict**: ✅ **READY FOR PR**
  - Code meets quality standards
  - All agents passed
  - Safe to create pull request

### Agent Applicability Matrix

| Agent | Condition | Always/Conditional |
|-------|-----------|-------------------|
| tool-validator | Always runs FIRST | REQUIRED |
| backward-compatibility-checker | HAS_SCHEMA_CHANGES | Conditional |
| code-reviewer | Always runs | REQUIRED |
| silent-failure-hunter | Always runs | REQUIRED |
| test-analyzer | HAS_TEST_FILES | Conditional |
| type-design-analyzer | HAS_TYPE_CHANGES | Conditional |
| comment-analyzer | HAS_COMMENT_CHANGES | Conditional |
| frontend-reviewer | HAS_FRONTEND_FILES | Conditional |
| code-simplifier | Always runs LAST | REQUIRED |

## Output Format:

```markdown
# Pre-PR Quality Check Summary

## Scope
- Files reviewed: X
- Agents run: [list]

## Critical Issues (must fix before PR)
- [agent]: Issue description [file:line]

## Important Issues (should fix)
- [agent]: Issue description [file:line]

## Suggestions (nice to have)
- [agent]: Suggestion [file:line]

## Strengths
- [What's well done in this code]

## Verdict
✅ READY FOR PR
or
❌ FIX ISSUES FIRST
  - [ ] Fix critical issue 1
  - [ ] Fix critical issue 2
  - [ ] Run quality-check again
```

## Usage:

```bash
/requirements-framework:quality-check           # Sequential (thorough)
/requirements-framework:quality-check parallel  # Parallel (faster)
```

## TDD Workflow Integration:

This command is the final gate before creating a PR:

1. Write failing test ✓
2. `/requirements-framework:pre-commit tests` - Verify test quality ✓
3. Write implementation ✓
4. `/requirements-framework:pre-commit tools code errors` - Check implementation + tools ✓
5. Refactor ✓
6. **`/requirements-framework:quality-check`** ← You are here (runs ALL 9 agents)
7. Create PR

**Agent Execution Order**:
1. tool-validator (objective - pyright/ruff)
2. backward-compatibility-checker (schema changes)
3. code-reviewer, silent-failure-hunter, test-analyzer (parallel)
4. type-design-analyzer, comment-analyzer, frontend-reviewer (parallel if applicable)
5. code-simplifier (final polish)

## Tips:

- Run this BEFORE creating the PR, not after
- Address all critical issues - they're blockers
- Important issues should be fixed if feasible
- Suggestions are at your discretion
- Re-run after fixing issues to verify
- Use `parallel` when you're confident and want speed
