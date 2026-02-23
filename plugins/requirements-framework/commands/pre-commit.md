---
name: pre-commit
description: "Quick code review before committing (code + error handling)"
argument-hint: "[aspects]"
allowed-tools: ["Bash", "Glob", "Grep", "Read", "Task", "TeamCreate", "TeamDelete", "SendMessage", "TaskCreate", "TaskUpdate", "TaskList", "TaskGet"]
git_hash: 71ee5ae
---

# Pre-Commit Review

Run focused code quality checks on unstaged/staged changes before committing.
Uses Agent Teams for cross-validated review when 2+ review agents are enabled.

**Arguments:** "$ARGUMENTS"

**See ADR-012 for design rationale.**

## Default Review (no args):
Run three essential checks:
- **tool-validator** - Execute pyright/ruff/eslint (subagent — deterministic, no debate value)
- **code-reviewer** - CLAUDE.md compliance, bugs, code quality (teammate)
- **silent-failure-hunter** - Error handling audit (teammate)

## Available Aspects:
- **tools** - Execute linting/type-checking tools (tool-validator agent)
- **compat** - Check backward compatibility (backward-compatibility-checker agent)
- **code** - General code quality (code-reviewer agent)
- **errors** - Error handling audit (silent-failure-hunter agent)
- **tests** - Test coverage check (test-analyzer agent)
- **types** - Type design analysis (type-design-analyzer agent)
- **comments** - Comment accuracy (comment-analyzer agent)
- **frontend** - React/frontend best practices (frontend-reviewer agent)
- **simplify** - Code simplification (code-simplifier agent)
- **all** - Run all reviews (includes tools + compat + frontend)
- **parallel** - Backward-compatible no-op (teams are inherently parallel)

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

**RUN_FRONTEND_REVIEWER**=false
- Set to true if: $ARGUMENTS contains "frontend" OR contains "all"

**RUN_CODE_SIMPLIFIER**=false
- Set to true if: $ARGUMENTS contains "simplify" OR contains "all"

Now compute derived values:

**TEAM_AGENT_COUNT** = count of true flags among: RUN_CODE_REVIEWER, RUN_SILENT_FAILURE_HUNTER, RUN_BACKWARD_COMPATIBILITY_CHECKER, RUN_TEST_ANALYZER, RUN_TYPE_DESIGN_ANALYZER, RUN_COMMENT_ANALYZER, RUN_FRONTEND_REVIEWER

**USE_TEAM** = true if TEAM_AGENT_COUNT >= 2

Note: the `parallel` argument is accepted for backward compatibility but is a no-op — teams are inherently parallel.

### Step 3: Execute Tool Validator (if enabled) — BLOCKING GATE (subagent)

This step uses a subagent (not a teammate) because it runs deterministic linters — no debate value.

If RUN_TOOL_VALIDATOR is true:
  1. Use the Task tool to launch subagent_type="requirements-framework:tool-validator"
  2. Wait for completion
  3. Parse the output for CRITICAL severity issues
  4. If CRITICAL tool errors found (pyright errors, ruff errors, eslint errors):
     - Output the tool-validator findings immediately
     - Return verdict: "**FIX TOOL ERRORS FIRST** - Cannot proceed with review until objective tool checks pass"
     - STOP - do not execute any other agents
  5. If no critical errors: Continue to next step

### Step 4: Determine Execution Mode

- If USE_TEAM is true: proceed to Step 5 (team creation)
- If USE_TEAM is false (single review agent): skip to Step 9 (subagent fallback)

### Step 5: Create Review Team

Use TeamCreate:
```
team_name: "pre-commit-{timestamp}"
description: "Cross-validated pre-commit review"
```

Where `{timestamp}` is the current Unix timestamp (use `date +%s` to get it).

Create tasks on the shared task list:

For EACH enabled review agent flag, create a task:
- If RUN_CODE_REVIEWER: **Task**: "Code quality review" — assigned to code-reviewer
- If RUN_SILENT_FAILURE_HUNTER: **Task**: "Error handling audit" — assigned to error-auditor
- If RUN_BACKWARD_COMPATIBILITY_CHECKER: **Task**: "Backward compatibility check" — assigned to compat-checker
- If RUN_TEST_ANALYZER: **Task**: "Test coverage analysis" — assigned to test-analyzer
- If RUN_TYPE_DESIGN_ANALYZER: **Task**: "Type design review" — assigned to type-analyzer
- If RUN_COMMENT_ANALYZER: **Task**: "Comment accuracy review" — assigned to comment-analyzer
- If RUN_FRONTEND_REVIEWER: **Task**: "Frontend best practices review" — assigned to frontend-reviewer

Then create a synthesis task:
- **Task**: "Cross-validate and synthesize findings" — blocked by all review tasks above, assigned to lead

**Fallback**: If TeamCreate fails and `hooks.agent_teams.fallback_to_subagents` is true (default), log the error and skip to Step 9 (subagent fallback).

### Step 6: Spawn Teammates

For each review task, spawn a teammate via the Task tool.

**Standard preamble for ALL teammate prompts** (include at the top of each prompt):
```
You MUST use the standard output format from ADR-013. All findings must use:
- ### CRITICAL: [title] — for blocking issues
- ### IMPORTANT: [title] — for significant concerns
- ### SUGGESTION: [title] — for improvements
Each finding must have Location, Description, Impact, and Fix fields.
End with ## Summary containing counts and Verdict (ISSUES FOUND | APPROVED).
Share your findings via SendMessage to the team lead when done.
Mark your task as complete using TaskUpdate.
```

Each teammate gets:
- `team_name`: the team name from Step 5
- `subagent_type`: matching the agent (e.g., "requirements-framework:code-reviewer")
- `name`: descriptive name (e.g., "code-reviewer", "error-auditor", "compat-checker", "test-analyzer", "type-analyzer", "comment-analyzer", "frontend-reviewer")
- `prompt`: Standard preamble + diff context + review focus

Launch ALL teammates in a SINGLE message with multiple Task tool calls (parallel execution).

### Step 7: Wait for Review Tasks

Monitor the task list until all review tasks (except the synthesis task) are complete:
- Use TaskList periodically to check progress
- Teammates will send findings via automatic message delivery
- Allow up to 120 seconds per teammate

If a teammate fails to complete within timeout:
- Note the gap in the final report
- Proceed with available findings (fail-open)

### Step 8: Cross-Validation Phase (Lead)

Read all teammate findings received via messages. Apply **domain-specific cross-validation rules** (subset of ADR-013, based on active agents):

**Location matching**: Same file within 10-line proximity = "same location".

**Apply these rules only when BOTH referenced agents are active teammates**:

| Rule | Agents | Condition | Action |
|------|--------|-----------|--------|
| Error handling quality | code-reviewer + silent-failure-hunter | Both flag same region | Escalate to CRITICAL |
| Error handling specialist | code-reviewer vs silent-failure-hunter | Only sfh flags | Trust specialist (keep sfh severity) |
| Documentation drift | code-reviewer + comment-analyzer | Code change + comment issue same location | Corroborate with note |
| Untested bugs | test-analyzer + code-reviewer | Bug + no tests for same function | Escalate both to CRITICAL |
| Type safety breaks | type-design-analyzer + backward-compat | Weak types + breaking change | Escalate to CRITICAL |
| Suppressed breaks | silent-failure-hunter + backward-compat | Breaking change + silent suppression | Escalate to CRITICAL |
| Untested components | frontend-reviewer + test-analyzer | Component issue + no component tests | Escalate both to CRITICAL |
| Frontend + error handling | frontend-reviewer + silent-failure-hunter | a11y/error boundary gap in same region | Escalate to CRITICAL |
| Frontend + code quality | frontend-reviewer + code-reviewer | Both flag same component region | Corroborate with note |
| Frontend + types | frontend-reviewer + type-design-analyzer | Props type issue + component issue | Corroborate |
| Frontend + breaking changes | frontend-reviewer + backward-compat | Breaking prop change + component | Escalate to CRITICAL |

After applying rules:
1. **Deduplicate**: Merge findings about the same location
2. **Group**: Organize by file and severity (CRITICAL first)
3. **Note corroborations**: Mark which agents confirmed each finding

### Step 9: Code Simplifier + Subagent Fallback

**Code Simplifier** (if RUN_CODE_SIMPLIFIER is true):
  1. Use the Task tool to launch subagent_type="requirements-framework:code-simplifier"
  2. This MUST run after all other agents complete
  3. Code simplifier polishes code that has passed review
  4. Add any simplification suggestions to the report

**Subagent Fallback** — handles cases where team mode was not used:
- If USE_TEAM was false (single review agent): run the single enabled review agent as a subagent
- If TeamCreate failed in Step 5: run all enabled review agents as subagents (sequential)

### Step 10: Aggregate and Verdict

Count findings across all sources (team + subagent):
- **CRITICAL_COUNT** = number of CRITICAL issues
- **IMPORTANT_COUNT** = number of IMPORTANT issues
- **SUGGESTION_COUNT** = number of SUGGESTION issues

Provide ONE verdict:

If CRITICAL_COUNT > 0:
  **Verdict**: "FIX ISSUES FIRST"
  - List all critical issues with corroboration status
  - Do not commit until resolved

Else if IMPORTANT_COUNT > 5:
  **Verdict**: "REVIEW IMPORTANT ISSUES"
  - Consider fixing before commit
  - Proceeding is possible but not recommended

Else if IMPORTANT_COUNT > 0:
  **Verdict**: "MINOR ISSUES FOUND"
  - Can commit, but review recommended
  - List important issues for context

Else:
  **Verdict**: "READY TO COMMIT"
  - Code meets quality standards
  - Safe to proceed

### Step 11: Cleanup

If a team was created (USE_TEAM was true and TeamCreate succeeded):
1. Send shutdown_request to all remaining teammates via SendMessage
2. Wait briefly for shutdown responses
3. Use TeamDelete to clean up team resources
4. Log and proceed on any cleanup failure — never block on cleanup errors

## Agent Selection Logic:

- If no args or `tools` specified → tool-validator (always subagent, runs first as blocking gate)
- If no args or `code` specified → code-reviewer (teammate when 2+ review agents)
- If no args or `errors` specified → silent-failure-hunter (teammate when 2+ review agents)
- If `compat` specified → backward-compatibility-checker (teammate when 2+ review agents)
- If `tests` specified → test-analyzer (teammate when 2+ review agents)
- If `types` specified → type-design-analyzer (teammate when 2+ review agents)
- If `comments` specified → comment-analyzer (teammate when 2+ review agents)
- If `frontend` specified → frontend-reviewer (teammate when 2+ review agents)
- If `simplify` specified → code-simplifier (always subagent, runs last)
- If `all` specified → all applicable agents (tool-validator + code-simplifier as subagents, rest as teammates)
- If `parallel` specified → backward-compatible no-op (teams are inherently parallel)

## Output Format:

When team mode was used (USE_TEAM=true):

```markdown
# Pre-Commit Review Summary

## Scope
[Files reviewed]

## Team
- code-reviewer: [completed/timed-out]
- silent-failure-hunter: [completed/timed-out]
- [other teammates if applicable]

## Corroborated Findings (confirmed by 2+ agents)
- [SEVERITY] [description] — confirmed by [agent1, agent2] [file:line]

## Critical Issues (X found)
- [agent]: Issue description [file:line]

## Important Issues (X found)
- [agent]: Issue description [file:line]

## Suggestions (X found)
- [agent]: Suggestion [file:line]

## Disputed Findings
- [description] — [agent1] says X, [agent2] says Y

## Code Simplification
- [suggestions from code-simplifier, if enabled]

## Recommendation
[READY TO COMMIT / MINOR ISSUES FOUND / REVIEW IMPORTANT ISSUES / FIX ISSUES FIRST]
```

When subagent fallback was used (USE_TEAM=false or TeamCreate failed):

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
[READY TO COMMIT / MINOR ISSUES FOUND / REVIEW IMPORTANT ISSUES / FIX ISSUES FIRST]
```

## Usage Examples:

```bash
/requirements-framework:pre-commit                    # Default: team (code-reviewer + silent-failure-hunter) + tool-validator subagent
/requirements-framework:pre-commit tools              # Just run linting/type-checking (subagent only)
/requirements-framework:pre-commit code               # Single agent: subagent fallback (no team value)
/requirements-framework:pre-commit code errors        # Team: 2 teammates cross-validate
/requirements-framework:pre-commit compat             # Single agent: subagent fallback
/requirements-framework:pre-commit all                # Team: up to 6 review teammates + tool-validator + code-simplifier subagents
/requirements-framework:pre-commit all parallel       # Same as `all` (parallel is no-op with teams)
/requirements-framework:pre-commit tests types        # Team: 2 teammates cross-validate
/requirements-framework:pre-commit frontend             # Single agent: subagent fallback
/requirements-framework:pre-commit frontend code errors # Team: 3 teammates cross-validate
/requirements-framework:pre-commit tools compat code  # Team if 2+ review agents, else subagent
```

## Comparison with /deep-review

| Aspect | /pre-commit | /deep-review |
|--------|-------------|--------------|
| Scope | Pre-commit changes | All branch changes |
| Default agents | code-reviewer + silent-failure-hunter | code-reviewer + silent-failure-hunter + contextual |
| Satisfies | `pre_commit_review` | `pre_pr_review` |
| Cost | Lower (fewer default agents) | Higher (more agents, broader scope) |
| Cross-validation | Yes (when 2+ review agents) | Always |

## Tips:

- **Start with tools** - catches objective errors (pyright, ruff) before AI analysis
- **Use compat** - when renaming fields or changing schemas
- Run early, run often - catch issues before they compound
- Address critical issues before committing
- Use `simplify` only after code passes other reviews
- For TDD: run `tests` first to verify test quality
- **tools + compat together** catch most CI failures locally
- The default (no args) now uses team cross-validation for higher-quality reviews
