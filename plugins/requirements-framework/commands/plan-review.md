---
name: plan-review
description: "Validate plan against ADRs, TDD, and SOLID principles, identify preparatory refactoring, then generate atomic commit strategy"
argument-hint: "[plan-file]"
allowed-tools: ["Bash", "Glob", "Grep", "Read", "Task"]
git_hash: 71ee5ae
---

# Plan Review Command

> **For thorough multi-perspective review with agent cross-validation, use `/arch-review` instead.**
> This command is a lightweight alternative that runs agents sequentially without cross-validation.

Automated plan validation and commit planning workflow. This command:
1. Validates the plan against Architecture Decision Records (auto-fixes violations)
2. Validates TDD readiness (auto-adds testing strategy if missing)
3. Validates SOLID principles adherence (auto-adds SOLID considerations if missing)
4. Identifies preparatory refactoring opportunities (auto-adds refactoring section if needed)
5. Generates an atomic commit strategy (appends to plan file)
6. Auto-satisfies `adr_reviewed`, `tdd_planned`, `solid_reviewed`, and `commit_plan` requirements

**Arguments:** "$ARGUMENTS"
- Optional: provide a specific plan file path (recommended when multiple plans exist)

## Deterministic Execution Workflow

You MUST follow these steps in exact order. This is a blocking workflow - each step must complete before the next.

### Step 1: Locate the Plan File

First preference: explicit argument. Fallback: auto-discover latest plan (project-local first, then global):

```bash
# If user passed an argument, use it directly
PLAN_FILE="$ARGUMENTS"

# Trim surrounding whitespace and optional quotes
PLAN_FILE=$(echo "$PLAN_FILE" | sed 's/^ *//; s/ *$//; s/^"//; s/"$//')

# Expand "~/" prefix for user-provided paths
if [ -n "$PLAN_FILE" ] && [ "${PLAN_FILE#~/}" != "$PLAN_FILE" ]; then
  PLAN_FILE="$HOME/${PLAN_FILE#~/}"
fi

# If no argument provided, auto-discover
if [ -z "$PLAN_FILE" ]; then
  PLAN_FILE=$(ls -t .claude/plans/*.md 2>/dev/null | head -1)
  if [ -z "$PLAN_FILE" ]; then
    PLAN_FILE=$(ls -t ~/.claude/plans/*.md 2>/dev/null | head -1)
  fi
fi
echo "$PLAN_FILE"
```

If no plan file found (PLAN_FILE is empty):
- Output: "No plan file found in .claude/plans/ or ~/.claude/plans/"
- Output: "Create a plan in plan mode first, then run this command."
- **STOP** - do not proceed to other steps

If plan file found:
- Verify file exists and is readable. If not, output: "Plan file not found or unreadable: [PLAN_FILE]" and **STOP**
- Store the path as PLAN_FILE
- Output: "Found plan file: [PLAN_FILE]"
- If this is not the intended plan, **STOP** and rerun with an explicit path argument

### Step 2: Run ADR Guardian - BLOCKING GATE

This step validates the plan against ADRs and auto-fixes violations where possible.

1. Use the Task tool to launch:
   - `subagent_type`: "requirements-framework:adr-guardian"
   - `prompt`: Include the following context:
     ```
     Review the plan file at [PLAN_FILE] against all project ADRs.

     IMPORTANT: You have Edit tool access. If you find ADR violations that can be
     auto-fixed, edit the plan file directly to fix them, then re-validate.

     Only output APPROVED if the plan passes (after any auto-fixes).
     Output BLOCKED if there are unfixable violations.
     ```

2. Wait for agent completion

3. Parse the agent output for verdict:
   - If **APPROVED**: Continue to Step 3
   - If **BLOCKED**:
     - Output the full agent response (explains what needs manual fixing)
     - **STOP** - do not proceed to commit planning
   - If **ADR REQUIRED**:
     - Output the full agent response (explains what ADR is needed)
     - **STOP** - do not proceed to commit planning

### Step 3: Run TDD Validator - BLOCKING GATE

After ADR validation passes, verify the plan includes TDD elements.

1. Use the Task tool to launch:
   - `subagent_type`: "requirements-framework:tdd-validator"
   - `prompt`: Include the following context:
     ```
     Review the plan file at [PLAN_FILE] for TDD readiness.

     IMPORTANT: You have Edit tool access. If TDD elements are missing but
     the plan is clear enough, add them directly to the plan file.

     Check for:
     1. A Testing Strategy / Test Plan section
     2. Test types identified per feature/component
     3. TDD sequence (write tests first)

     Output APPROVED if the plan has TDD elements (after any auto-fixes).
     Output BLOCKED if the plan is too vague to determine testing approach.
     ```

2. Wait for agent completion

3. Parse the agent output for verdict:
   - If **APPROVED**: Continue to Step 4
   - If **BLOCKED**:
     - Output the full agent response (explains what needs to be added)
     - **STOP** - do not proceed to commit planning

### Step 4: Run SOLID Reviewer - BLOCKING GATE

After TDD validation passes, verify the plan follows SOLID design principles.

1. Use the Task tool to launch:
   - `subagent_type`: "requirements-framework:solid-reviewer"
   - `prompt`: Include the following context:
     ```
     Review the plan file at [PLAN_FILE] for SOLID principles adherence
     with Python focus.

     IMPORTANT: You have Edit tool access. If SOLID considerations are
     missing but the plan is clear enough, add them directly to the plan file.

     Scale strictness to plan size:
     - 1-2 files: SRP only
     - 3-5 files: SRP + DIP
     - 6+ files: Full SOLID check

     Output APPROVED if the plan follows SOLID principles (after any auto-fixes).
     Output BLOCKED if there are egregious violations that require restructuring.
     ```

2. Wait for agent completion

3. Parse the agent output for verdict:
   - If **APPROVED**: Continue to Step 5 (Refactor Advisor)
   - If **BLOCKED**:
     - Output the full agent response (explains what needs restructuring)
     - **STOP** - do not proceed

### Step 5: Run Refactor Advisor - SEMI-BLOCKING

After SOLID validation passes, identify preparatory refactoring opportunities in the existing codebase.

1. Use the Task tool to launch:
   - `subagent_type`: "requirements-framework:refactor-advisor"
   - `prompt`: Include the following context:
     ```
     Analyze the plan file at [PLAN_FILE] and the existing codebase to identify
     preparatory refactoring opportunities.

     IMPORTANT: You have Edit tool access. Add a "## Preparatory Refactoring"
     section to the plan file with your recommendations.

     Focus on structural improvements to existing code that would make the planned
     change easier to implement. Scale analysis to plan size.

     Output APPROVED if no prep work needed.
     Output REFACTORING RECOMMENDED with specific suggestions if opportunities found.
     Output BLOCKED only in extreme cases (massive duplication, breaking 5+ callers).
     ```

2. Wait for agent completion

3. Parse the agent output for verdict:
   - If **APPROVED**: Continue to Step 6
   - If **REFACTORING RECOMMENDED**: Continue to Step 6 — recommendations are documented in the plan
   - If **BLOCKED**:
     - Output the full agent response (explains what prep work is critical)
     - **STOP** - do not proceed to commit planning

### Step 6: Run Commit Planner

After ADR, TDD, SOLID validation, and refactoring analysis, generate the commit strategy.

1. Use the Task tool to launch:
   - `subagent_type`: "requirements-framework:commit-planner"
   - `prompt`: Include the following context:
     ```
     Analyze the plan file at [PLAN_FILE] and generate an atomic commit strategy.

     IMPORTANT: Use the Edit tool to APPEND the commit plan to the plan file.
     Do not create a separate file.

     After appending, output a brief summary of the commit sequence.
     ```

2. Wait for agent completion

3. Confirm commit plan was appended to the plan file

### Step 7: Output Success Summary

After all agents complete successfully:

```markdown
## Plan Review Complete

**Plan File**: [PLAN_FILE]

### ADR Validation
- Status: APPROVED
- [Any auto-fixes applied]

### TDD Validation
- Status: APPROVED
- [Any auto-fixes applied (e.g., testing strategy section added)]

### SOLID Validation
- Status: APPROVED
- [Any auto-fixes applied (e.g., SOLID considerations section added)]

### Preparatory Refactoring
- Status: [APPROVED / REFACTORING RECOMMENDED]
- [Number of refactorings suggested, or "No prep work needed"]
- [Brief summary of key recommendations if any]

### Commit Strategy
- [Number] commits planned
- [Brief summary from commit-planner]

### Requirements Satisfied
All four planning requirements are now satisfied:
- `adr_reviewed` - Architecture Decision Records validated
- `tdd_planned` - TDD readiness verified
- `solid_reviewed` - SOLID principles validated
- `commit_plan` - Atomic commit strategy created

You can proceed with implementation.

### Next Steps
1. Review the updated plan file with commit sequence
2. Start implementing following the commit order
3. Run `/requirements-framework:pre-commit` before each commit
```

## Error Handling

### If ADR Guardian fails to start:
- Output: "Failed to launch ADR Guardian agent"
- Suggest: Check plugin configuration

### If Commit Planner fails to start:
- Output: "Failed to launch Commit Planner agent"
- Note: ADR validation passed, but commit planning failed
- Suggest: Run commit-planner manually or create commit plan manually

### If plan file becomes corrupted:
- The original plan should be recoverable from the plan file
- Commit plan section is appended at the end with a separator

## Usage

```bash
/requirements-framework:plan-review
/requirements-framework:plan-review .claude/plans/my-plan.md
/requirements-framework:plan-review ~/.claude/plans/stateful-meandering-hopper.md
```

Run this command immediately after exiting plan mode. It will:
1. Find your most recent plan
2. Validate it against ADRs (auto-fixing where possible)
3. Validate TDD readiness (auto-adding testing strategy if needed)
4. Validate SOLID principles (auto-adding considerations if needed)
5. Identify preparatory refactoring opportunities (auto-adding section if needed)
6. Generate an atomic commit strategy
7. Satisfy all four planning requirements

## Integration with Requirements Framework

This command is a **lightweight alternative** to `/arch-review` (the recommended approach).

- Satisfies `adr_reviewed` requirement (session scope)
- Satisfies `tdd_planned` requirement (session scope)
- Satisfies `solid_reviewed` requirement (session scope)
- Satisfies `commit_plan` requirement (session scope)
- The recommended approach (`/arch-review`) uses Agent Teams for cross-validated review with 6 agents working collaboratively

After running this command, Edit/Write tools will no longer be blocked by these planning requirements for the current session.
