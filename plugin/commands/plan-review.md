---
name: plan-review
description: "Validate plan against ADRs and create atomic commit strategy"
argument-hint: ""
allowed-tools: ["Bash", "Glob", "Grep", "Read", "Task"]
git_hash: uncommitted
---

# Plan Review Command

Automated plan validation and commit planning workflow. This command:
1. Validates the plan against Architecture Decision Records (auto-fixes violations)
2. Creates an atomic commit strategy (appends to plan file)
3. Auto-satisfies `adr_reviewed` and `commit_plan` requirements

## Deterministic Execution Workflow

You MUST follow these steps in exact order. This is a blocking workflow - each step must complete before the next.

### Step 1: Locate the Plan File

Find the most recent plan file in `~/.claude/plans/`:

```bash
ls -t ~/.claude/plans/*.md 2>/dev/null | head -1
```

If no plan file found:
- Output: "No plan file found in ~/.claude/plans/"
- Output: "Create a plan in plan mode first, then run this command."
- **STOP** - do not proceed to other steps

If plan file found:
- Store the path as PLAN_FILE
- Output: "Found plan file: [PLAN_FILE]"

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

### Step 3: Run Commit Planner

After ADR validation passes, create the commit strategy.

1. Use the Task tool to launch:
   - `subagent_type`: "requirements-framework:commit-planner"
   - `prompt`: Include the following context:
     ```
     Analyze the plan file at [PLAN_FILE] and create an atomic commit strategy.

     IMPORTANT: Use the Edit tool to APPEND the commit plan to the plan file.
     Do not create a separate file.

     After appending, output a brief summary of the commit sequence.
     ```

2. Wait for agent completion

3. Confirm commit plan was appended to the plan file

### Step 4: Output Success Summary

After both agents complete successfully:

```markdown
## Plan Review Complete

**Plan File**: [PLAN_FILE]

### ADR Validation
- Status: APPROVED
- [Any auto-fixes applied]

### Commit Strategy
- [Number] commits planned
- [Brief summary from commit-planner]

### Requirements Satisfied
Both `adr_reviewed` and `commit_plan` requirements are now satisfied.
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
```

Run this command after exiting plan mode. It will:
1. Find your most recent plan
2. Validate it against ADRs (auto-fixing where possible)
3. Create an atomic commit strategy
4. Satisfy both planning requirements

## Integration with Requirements Framework

This command is designed to work with the requirements framework:
- Satisfies `adr_reviewed` requirement (session scope)
- Satisfies `commit_plan` requirement (session scope)
- Both requirements use `satisfied_by_skill: 'requirements-framework:plan-review'`

After running this command, Edit/Write tools will no longer be blocked by these requirements for the current session.
