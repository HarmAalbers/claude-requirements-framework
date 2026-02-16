---
name: deep-review
description: "Cross-validated team-based code review with agent debate"
argument-hint: ""
allowed-tools: ["Bash", "Glob", "Grep", "Read", "Task", "TeamCreate", "TeamDelete", "SendMessage", "TaskCreate", "TaskUpdate", "TaskList", "TaskGet"]
git_hash: 6550a98
hooks:
  SubagentStart:
    - matcher: "*"
      hooks:
        - type: prompt
          prompt: "Inject context: This review agent is part of /deep-review (cross-validated team review). Focus on thoroughness, cross-cutting concerns, and finding issues other reviewers might miss. Context: $ARGUMENTS"
          model: haiku
          once: true
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

### Step 2: Detect File Types and Set Applicability Flags

```bash
# Check for test files
grep -E '(test_|_test\.py|\.test\.|\.spec\.)' /tmp/deep_review_scope.txt > /tmp/has_tests.txt 2>&1

# Check for type/schema changes
grep -E '(types?\.(py|ts)|schema|interface|protocol|\.d\.ts)' /tmp/deep_review_scope.txt > /tmp/has_types.txt 2>&1

# Check for schema/API changes
grep -E '(schema|model|migration|api|endpoint)' /tmp/deep_review_scope.txt > /tmp/has_schemas.txt 2>&1
```

Set flags:
- **HAS_TEST_FILES** = true if /tmp/has_tests.txt is non-empty
- **HAS_TYPE_CHANGES** = true if /tmp/has_types.txt is non-empty
- **HAS_SCHEMA_CHANGES** = true if /tmp/has_schemas.txt is non-empty

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

Create tasks on the shared task list:

1. **Task**: "Code quality review" — assigned to code-reviewer
2. **Task**: "Error handling audit" — assigned to silent-failure-hunter
3. **Task**: "Test coverage analysis" — ONLY if HAS_TEST_FILES is true, assigned to test-analyzer
4. **Task**: "Backward compatibility check" — ONLY if HAS_SCHEMA_CHANGES is true, assigned to backward-compatibility-checker
5. **Task**: "Cross-validate and synthesize findings" — blocked by all above tasks, assigned to lead

### Step 5: Spawn Teammates

For each review task (NOT the synthesis task), spawn a teammate via the Task tool:

Each teammate gets:
- `team_name`: the team name from Step 4
- `subagent_type`: matching the agent (e.g., "requirements-framework:code-reviewer")
- `name`: descriptive name (e.g., "code-reviewer", "error-auditor")
- `prompt`: Include:
  - The diff context: "Review the following changed files: [file list from scope]"
  - Their review focus: specific to the agent type
  - Instruction: "Share your key findings via SendMessage to the team lead when done. Mark your task as complete using TaskUpdate."
  - Instruction: "Report findings with severity levels: CRITICAL, IMPORTANT, SUGGESTION"

Launch all teammates in a SINGLE message with multiple Task tool calls (parallel execution).

### Step 6: Wait for Review Tasks

Monitor the task list until all review tasks (except the synthesis task) are complete:
- Use TaskList periodically to check progress
- Teammates will send findings via automatic message delivery
- Allow up to 120 seconds per teammate

If a teammate fails to complete within timeout:
- Note the gap in the final report
- Proceed with available findings (fail-open)

### Step 7: Cross-Validation Phase (Lead)

Read all teammate findings received via messages. Perform cross-validation:

1. **Deduplicate**: Identify findings about the same code location from different agents
2. **Corroborate**: If 2+ agents flag the same issue:
   - Mark as "Corroborated by [agent names]"
   - Escalate severity by one level (SUGGESTION → IMPORTANT, IMPORTANT → CRITICAL)
3. **Dispute**: If one agent flags an issue and another explicitly contradicts it:
   - Note the disagreement
   - Keep the higher severity but mark as "Disputed"
4. **Group**: Organize findings by file and severity

### Step 8: Code Simplifier (FINAL POLISH — subagent)

Use a subagent (not teammate) for the final polish:

1. Use the Task tool to launch:
   - `subagent_type`: "requirements-framework:code-simplifier"
   - `prompt`: "Review the changed files for simplification opportunities."

2. Wait for completion
3. Add any simplification suggestions to the report

### Step 9: Aggregate and Verdict

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

### Step 10: Cleanup

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
- test-analyzer: [status, if applicable]
- backward-compatibility-checker: [status, if applicable]

## Corroborated Findings (confirmed by 2+ agents)
- [SEVERITY] [description] — confirmed by [agent1, agent2] [file:line]

## Individual Findings
### Critical Issues (X found)
- [agent]: Issue description [file:line]

### Important Issues (X found)
- [agent]: Issue description [file:line]

### Suggestions (X found)
- [agent]: Suggestion [file:line]

## Disputed Findings
- [description] — [agent1] says X, [agent2] says Y

## Code Simplification
- [suggestions from code-simplifier]

## Verdict
[READY / REVIEW RECOMMENDED / FIX ISSUES FIRST]
```

## Usage

```bash
/requirements-framework:deep-review
```

## Comparison with /quality-check (Lightweight Alternative)

| Aspect | /deep-review (recommended) | /quality-check (lightweight) |
|--------|---------------------------|------------------------------|
| Execution | Agent Teams (collaborative) | Subagents (sequential/parallel) |
| Cross-validation | Agents debate and corroborate | None (independent findings) |
| Output | Unified verdict with corroboration | Aggregated list |
| Satisfies | `pre_pr_review` | Same |
| Cost | Higher (more thorough) | Lower (faster) |
