---
name: arch-review
description: "Multi-perspective team-based architecture review with agent debate"
argument-hint: "[plan-file-path]"
allowed-tools: ["Bash", "Glob", "Grep", "Read", "Task", "TeamCreate", "TeamDelete", "SendMessage", "TaskCreate", "TaskUpdate", "TaskList", "TaskGet"]
git_hash: uncommitted
---

# Architecture Review — Team-Based Multi-Perspective Assessment

Team-based architecture review where agents debate architectural implications of a plan.
Requires `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` environment variable.
Falls back to `/plan-review` when Agent Teams are not enabled.

**See ADR-012 for design rationale.**

## Deterministic Execution Workflow

You MUST follow these steps in exact order. Do not skip steps or interpret - execute as written.

### Step 1: Check Agent Teams Availability

```bash
echo $CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS
```

If the value is NOT "1":
- Output: "Agent Teams not enabled. Running /plan-review instead."
- Execute `/requirements-framework:plan-review` and **EXIT**
- Do NOT proceed to Step 2

### Step 2: Locate Plan File

Check `$ARGUMENTS` for an explicit path first, then auto-discover:

```bash
# Check for explicit argument
if [ -n "$ARGUMENTS" ]; then
  PLAN_FILE="$ARGUMENTS"
fi

# Auto-discover if no argument
if [ -z "$PLAN_FILE" ] || [ ! -f "$PLAN_FILE" ]; then
  PLAN_FILE=$(ls -t .claude/plans/*.md 2>/dev/null | head -1)
fi
if [ -z "$PLAN_FILE" ] || [ ! -f "$PLAN_FILE" ]; then
  PLAN_FILE=$(ls -t ~/.claude/plans/*.md 2>/dev/null | head -1)
fi
```

If no plan file found:
- Output: "No plan file found. Create a plan in plan mode first, then run this command."
- **EXIT**

Output: "Found plan file: [PLAN_FILE]"

Read the plan file content for use in teammate prompts.

### Step 3: Locate Project ADRs

```bash
# Find ADR directory
ADR_DIR=""
if [ -d "docs/adr" ]; then
  ADR_DIR="docs/adr"
elif [ -d "adr" ]; then
  ADR_DIR="adr"
fi
```

If ADR_DIR found, list the ADR files for teammate context. Otherwise note "No ADR directory found."

### Step 4: Create Architecture Team

Use TeamCreate:
```
team_name: "arch-review-{timestamp}"
description: "Multi-perspective architecture review"
```

Where `{timestamp}` is the current Unix timestamp.

Create tasks on the shared task list:

1. **Task**: "ADR compliance review" — assigned to adr-guardian
2. **Task**: "Breaking change analysis" — assigned to backward-compatibility-checker
3. **Task**: "Testability assessment" — assigned to tdd-validator
4. **Task**: "Synthesize architectural assessment" — blocked by all above, assigned to lead

### Step 5: Spawn Teammates

For each review task (NOT the synthesis task), spawn a teammate:

**adr-guardian teammate**:
- `subagent_type`: "requirements-framework:adr-guardian"
- `name`: "adr-guardian"
- `prompt`: Include plan file content, ADR directory listing, and instruction:
  "Review this plan against all project ADRs. Check for violations, missing ADRs, and compliance gaps. Share findings via SendMessage with severity levels. Mark task complete when done."

**backward-compatibility-checker teammate**:
- `subagent_type`: "requirements-framework:backward-compatibility-checker"
- `name`: "compat-checker"
- `prompt`: Include plan file content and instruction:
  "Analyze this plan for breaking changes: renamed fields, removed APIs, changed schemas, migration needs. Share findings via SendMessage with severity levels. Mark task complete when done."

**tdd-validator teammate**:
- `subagent_type`: "requirements-framework:tdd-validator"
- `name`: "tdd-validator"
- `prompt`: Include plan file content and instruction:
  "Assess the testability of this plan: Does it include test strategy? Are breaking changes covered by tests? Does the TDD sequence account for all components? Share findings via SendMessage. Mark task complete when done."

Launch all teammates in a SINGLE message (parallel execution).

### Step 6: Wait for Reviews

Monitor task list until all review tasks complete:
- Use TaskList periodically
- Allow up to 120 seconds per teammate
- If a teammate times out, note the gap and proceed

### Step 7: Synthesis (Lead)

Read all teammate findings. Perform architectural synthesis:

1. **Cross-reference ADR findings with breaking changes**:
   - If ADR guardian flags a decision violation AND compat-checker confirms a breaking change: escalate to CRITICAL
   - If ADR guardian finds no relevant ADR for a new pattern: recommend new ADR

2. **Validate TDD coverage of breaking changes**:
   - If compat-checker identifies breaking changes AND tdd-validator finds no test plan for those changes: flag as CRITICAL gap

3. **Produce unified verdict**:
   - **APPROVED**: Plan aligns with ADRs, breaking changes are acceptable and tested
   - **BLOCKED**: Unresolvable ADR violations or untested breaking changes
   - **ADR_REQUIRED**: Plan introduces new patterns needing documented decisions

### Step 8: Auto-satisfy

If verdict is APPROVED:
- Run: `req satisfy adr_reviewed --session [current_session_id]`
- Output: "adr_reviewed requirement satisfied"

### Step 9: Cleanup

1. Send shutdown_request to all remaining teammates
2. Wait briefly for responses
3. Use TeamDelete to clean up team resources

## Output Format

```markdown
# Architecture Review — Team Assessment

## Plan
[Plan file path and summary]

## Team
- adr-guardian: [status]
- backward-compatibility-checker: [status]
- tdd-validator: [status]

## ADR Compliance
[Findings from adr-guardian, cross-referenced with other agents]

## Breaking Changes
[Findings from backward-compatibility-checker]

## Testability
[Findings from tdd-validator, cross-referenced with breaking changes]

## Cross-Validated Findings
- [Findings confirmed or disputed across agents]

## Verdict
[APPROVED / BLOCKED / ADR_REQUIRED]

## Recommendations
- [Specific actions to resolve any issues]
```

## Usage

```bash
/requirements-framework:arch-review                    # Auto-discover plan
/requirements-framework:arch-review path/to/plan.md    # Explicit plan file
```

## Key Differences from /plan-review

| Aspect | /plan-review | /arch-review |
|--------|-------------|--------------|
| Execution | Subagents (sequential) | Agent Teams (collaborative) |
| Agents | ADR guardian + commit planner | ADR guardian + compat-checker + TDD validator |
| Cross-validation | None | Agents cross-reference findings |
| Focus | ADR compliance + commit strategy | Holistic architecture assessment |
| Cost | Lower | Higher |
| Prerequisite | None | `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` |
| Fallback | N/A | `/plan-review` |
