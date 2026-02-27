---
name: deep-review
description: "Cross-validated team-based code review with agent debate"
argument-hint: ""
allowed-tools: ["Bash", "Glob", "Grep", "Read", "Task", "TeamCreate", "TeamDelete", "SendMessage", "TaskCreate", "TaskUpdate", "TaskList", "TaskGet"]
git_hash: fd3589d
---

# Deep Review — Cross-Validated Team-Based Code Review

Team-based review where agents cross-validate findings and produce a unified verdict.

**See ADR-012 for design rationale.**

## Deterministic Execution Workflow

You MUST follow these steps in exact order. Do not skip steps or interpret - execute as written.

### Step 1: Identify Changes to Review

Execute these bash commands:

```bash
git diff --cached --name-only --diff-filter=ACMR > /tmp/deep_review_scope.txt 2>&1
if [ ! -s /tmp/deep_review_scope.txt ]; then
  git diff --name-only --diff-filter=ACMR > /tmp/deep_review_scope.txt 2>&1
fi
```

If /tmp/deep_review_scope.txt is empty: Output "No changes to review" and **EXIT**.

### Step 2: Check Conditional Agent Availability

```bash
which codex 2>/dev/null
```

Set flag:
- **HAS_CODEX** = true if `which codex` succeeds (exit code 0)

```bash
grep -qE '\.(tsx|jsx|css|scss)$' /tmp/deep_review_scope.txt 2>/dev/null
```

Set flag:
- **HAS_FRONTEND** = true if the grep succeeds (frontend files found in scope)

### Step 3: Run Tool Validator (BLOCKING GATE — subagent)

This step uses a subagent (not a teammate) because it runs deterministic linters.

1. Use the Task tool to launch:
   - `subagent_type`: "requirements-framework:tool-validator"
   - `prompt`: "Run tool validation (pyright, ruff, eslint) on the changes. Report any CRITICAL issues."

2. Wait for completion

3. If CRITICAL tool errors found:
   - Output the tool-validator findings
   - Output: "**FIX TOOL ERRORS FIRST** - Cannot proceed with team review until objective checks pass"
   - **STOP** - do not create team

### Step 4: Create Review Team

Use TeamCreate to create the team:
```
team_name: "deep-review-{timestamp}"
description: "Cross-validated code review"
```

Where `{timestamp}` is the current Unix timestamp (use `date +%s` to get it).

Create tasks on the shared task list — core agents always run, conditional agents run when applicable:

1. **Task**: "Code quality review" — assigned to code-reviewer
2. **Task**: "Error handling audit" — assigned to silent-failure-hunter
3. **Task**: "Test coverage analysis" — assigned to test-analyzer
4. **Task**: "Backward compatibility check" — assigned to backward-compatibility-checker
5. **Task**: "Type design analysis" — assigned to type-design-analyzer
6. **Task**: "Comment accuracy check" — assigned to comment-analyzer
7. **Task**: "Code simplification analysis" — assigned to code-simplifier
8. **Task**: "Codex AI review" — assigned to codex-reviewer, ONLY if HAS_CODEX is true
9. **Task**: "Frontend best practices review" — assigned to frontend-reviewer, ONLY if HAS_FRONTEND is true
10. **Task**: "Cross-validate and synthesize findings" — blocked by all above tasks, assigned to lead

### Step 5: Spawn Teammates

For each review task (NOT the synthesis task), spawn a teammate via the Task tool.

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

**Teammates to spawn** (all in a SINGLE message for parallel execution):

1. `subagent_type`: "requirements-framework:code-reviewer", `name`: "code-reviewer"
2. `subagent_type`: "requirements-framework:silent-failure-hunter", `name`: "error-auditor"
3. `subagent_type`: "requirements-framework:test-analyzer", `name`: "test-analyzer"
4. `subagent_type`: "requirements-framework:backward-compatibility-checker", `name`: "compat-checker"
5. `subagent_type`: "requirements-framework:type-design-analyzer", `name`: "type-analyzer"
6. `subagent_type`: "requirements-framework:comment-analyzer", `name`: "comment-analyzer"
7. `subagent_type`: "requirements-framework:code-simplifier", `name`: "code-simplifier"
8. `subagent_type`: "requirements-framework:codex-review-agent", `name`: "codex-reviewer" — ONLY if HAS_CODEX is true
9. `subagent_type`: "requirements-framework:frontend-reviewer", `name`: "frontend-reviewer" — ONLY if HAS_FRONTEND is true

Each teammate prompt must include the diff context: "Review the following changed files: [file list from scope]"

### Step 6: Wait for Review Tasks

Monitor the task list until all review tasks (except the synthesis task) are complete:
- Use TaskList periodically to check progress
- Teammates will send findings via automatic message delivery
- Allow up to 120 seconds per teammate

If a teammate fails to complete within timeout:
- Note the gap in the final report
- Proceed with available findings (fail-open)

### Step 7: Cross-Validation Phase (Lead)

Read all teammate findings received via messages. Apply these **domain-specific cross-validation rules** (see ADR-013):

**Location matching**: Same file within 10-line proximity = "same location".

**Cross-Validation Rules**:

| Rule | Agents | Condition | Action |
|------|--------|-----------|--------|
| Error handling quality | code-reviewer + silent-failure-hunter | Both flag same region | Escalate to CRITICAL |
| Error handling specialist | code-reviewer vs silent-failure-hunter | Only sfh flags | Trust specialist (keep sfh severity) |
| Documentation drift | code-reviewer + comment-analyzer | Code change + comment issue same location | Corroborate with note |
| Untested bugs | test-analyzer + code-reviewer | Bug + no tests for same function | Escalate both to CRITICAL |
| Type safety breaks | type-design-analyzer + backward-compat | Weak types + breaking change | Escalate to CRITICAL |
| Type + error paths | type-design-analyzer + silent-failure-hunter | Unenforced invariants + error path | Escalate |
| Suppressed breaks | silent-failure-hunter + backward-compat | Breaking change + silent suppression | Escalate to CRITICAL |
| AI corroboration | codex-review-agent + any | Same location | Corroborate with "confirmed by external AI" |
| AI unique finding | codex-review-agent alone | Unique finding | Keep standalone with "verify manually" note |
| Simplification validates concern | code-simplifier + code-reviewer | Simplifier targets reviewer-flagged area | Corroborate: complexity contributes to bug |
| Simplifiable error paths | code-simplifier + silent-failure-hunter | Same region flagged | Note: simplifying may fix error handling |
| Untested components | frontend-reviewer + test-analyzer | Component issue + no component tests | Escalate both to CRITICAL |
| Frontend + error handling | frontend-reviewer + silent-failure-hunter | a11y/error boundary gap in same region | Escalate to CRITICAL |
| Frontend + code quality | frontend-reviewer + code-reviewer | Both flag same component region | Corroborate with note |
| Frontend + types | frontend-reviewer + type-design-analyzer | Props type issue + component issue | Corroborate |
| Frontend + breaking changes | frontend-reviewer + backward-compat | Breaking prop change + component | Escalate to CRITICAL |

After applying rules:
1. **Deduplicate**: Merge findings about the same location
2. **Group**: Organize by file and severity (CRITICAL first)
3. **Note corroborations**: Mark which agents confirmed each finding

### Step 8: Aggregate and Verdict

Count findings across all sources:
- **CRITICAL_COUNT** = number of CRITICAL issues
- **IMPORTANT_COUNT** = number of IMPORTANT issues
- **SUGGESTION_COUNT** = number of SUGGESTION issues

Provide ONE verdict:

If CRITICAL_COUNT > 0:
  **Verdict**: "FIX ISSUES FIRST"
  - List all critical issues with corroboration status

Else if IMPORTANT_COUNT > 5:
  **Verdict**: "REVIEW RECOMMENDED"
  - Summarize important issues

Else:
  **Verdict**: "READY"
  - Code meets quality standards

### Step 9: Cleanup

1. Send shutdown_request to all remaining teammates via SendMessage
2. Wait briefly for shutdown responses
3. Use TeamDelete to clean up team resources

## Output Format

```markdown
# Deep Review — Cross-Validated Report

## Scope
[Files reviewed]

## Team
- code-reviewer: [status]
- silent-failure-hunter: [status]
- test-analyzer: [status]
- backward-compatibility-checker: [status]
- type-design-analyzer: [status]
- comment-analyzer: [status]
- code-simplifier: [status]
- codex-review-agent: [status or "skipped (CLI not available)"]
- frontend-reviewer: [status or "skipped (no frontend files)"]

## Corroborated Findings (confirmed by cross-validation rules)
### CRITICAL: [title] — [rule name]
- **Agents**: [agent1] + [agent2]
- **Location**: `file:line`
- **Description**: What was found and which cross-validation rule applied
- **Fix**: Combined recommendation

## Individual Findings
### CRITICAL: [title] — [agent name]
- **Location**: `file:line`
- **Description**: [finding]
- **Fix**: [recommendation]

### IMPORTANT: [title] — [agent name]
- **Location**: `file:line`
- **Description**: [finding]
- **Fix**: [recommendation]

### SUGGESTION: [title] — [agent name]
- **Location**: `file:line`
- **Description**: [finding]
- **Fix**: [recommendation]

## Summary
- **CRITICAL**: X (Y corroborated)
- **IMPORTANT**: X
- **SUGGESTION**: X
- **Verdict**: READY | REVIEW RECOMMENDED | FIX ISSUES FIRST
```

## Usage

```bash
/requirements-framework:deep-review
```

## Comparison with /quality-check (Lightweight Alternative)

| Aspect | /deep-review (recommended) | /quality-check (lightweight) |
|--------|---------------------------|------------------------------|
| Execution | Agent Teams (collaborative) | Subagents (sequential/parallel) |
| Agents | 7-9 teammates (conditional on file types) | Variable subagents |
| Cross-validation | Domain-specific rules (ADR-013) | None (independent findings) |
| Output | Unified verdict with corroboration | Aggregated list |
| Satisfies | `pre_pr_review` | Same |
| Cost | Higher (more thorough) | Lower (faster) |
