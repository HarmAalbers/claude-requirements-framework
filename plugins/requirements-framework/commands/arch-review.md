---
name: arch-review
description: "Multi-perspective team-based architecture review with agent debate and commit planning"
argument-hint: "[plan-file-path]"
allowed-tools: ["Bash", "Glob", "Grep", "Read", "Task", "TeamCreate", "TeamDelete", "SendMessage", "TaskCreate", "TaskUpdate", "TaskList", "TaskGet"]
git_hash: 71ee5ae
---

# Architecture Review — Team-Based Multi-Perspective Assessment

Team-based architecture review where agents debate architectural implications of a plan and generate an atomic commit strategy.
Satisfies all 4 planning requirements: `commit_plan`, `adr_reviewed`, `tdd_planned`, `solid_reviewed`.

**See ADR-012 for design rationale.**

## Deterministic Execution Workflow

You MUST follow these steps in exact order. Do not skip steps or interpret - execute as written.

### Step 1: Locate Plan File

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

### Step 2: Locate Project ADRs

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

### Step 3: Create Architecture Team

Use TeamCreate:
```
team_name: "arch-review-{timestamp}"
description: "Multi-perspective architecture review with commit planning"
```

Where `{timestamp}` is the current Unix timestamp.

Create tasks on the shared task list:

1. **Task**: "ADR compliance review" — assigned to adr-guardian
2. **Task**: "Breaking change analysis" — assigned to backward-compatibility-checker
3. **Task**: "Testability assessment" — assigned to tdd-validator
4. **Task**: "SOLID principles review" — assigned to solid-reviewer
5. **Task**: "Preparatory refactoring analysis" — assigned to refactor-advisor
6. **Task**: "Atomic commit strategy" — assigned to commit-planner
7. **Task**: "Synthesize architectural assessment" — blocked by all above, assigned to lead

### Step 4: Spawn Teammates

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

**solid-reviewer teammate**:
- `subagent_type`: "requirements-framework:solid-reviewer"
- `name`: "solid-reviewer"
- `prompt`: Include plan file content and instruction:
  "Assess this plan for SOLID principles violations with Python focus. Scale strictness to plan size (1-2 files: SRP only, 3-5: SRP+DIP, 6+: full SOLID). Share findings via SendMessage with severity levels. Mark task complete when done."

**refactor-advisor teammate**:
- `subagent_type`: "requirements-framework:refactor-advisor"
- `name`: "refactor-advisor"
- `prompt`: Include plan file content and instruction:
  "Analyze this plan and the existing codebase to identify preparatory refactoring opportunities — structural improvements to existing code that would make the planned change easier to implement. Add a '## Preparatory Refactoring' section to the plan file using the Edit tool. Share findings via SendMessage with severity levels. Mark task complete when done."

**commit-planner teammate**:
- `subagent_type`: "requirements-framework:commit-planner"
- `name`: "commit-planner"
- `prompt`: Include plan file content and instruction:
  "Analyze this plan and generate an atomic commit strategy. Break the implementation into small, focused, independently-testable commits. For each commit: title, files changed, what to test. Append the commit strategy to the plan file using the Edit tool. Share a summary via SendMessage. Mark task complete when done."

Launch all teammates in a SINGLE message (parallel execution).

### Step 5: Wait for Reviews

Monitor task list until all review tasks complete:
- Use TaskList periodically
- Allow up to 120 seconds per teammate
- If a teammate times out, note the gap and proceed

### Step 6: Synthesis (Lead)

Read all teammate findings. Perform architectural synthesis:

1. **Cross-reference ADR findings with breaking changes**:
   - If ADR guardian flags a decision violation AND compat-checker confirms a breaking change: escalate to CRITICAL
   - If ADR guardian finds no relevant ADR for a new pattern: recommend new ADR

2. **Validate TDD coverage of breaking changes**:
   - If compat-checker identifies breaking changes AND tdd-validator finds no test plan for those changes: flag as CRITICAL gap

3. **Cross-reference SOLID findings**:
   - If solid-reviewer flags DIP violation AND tdd-validator finds untestable components: escalate to CRITICAL
   - If solid-reviewer flags SRP violation AND compat-checker finds wide blast radius: escalate to CRITICAL
   - If adr-guardian approves but solid-reviewer raises concern: note but don't escalate (ADR takes precedence)

4. **Cross-reference refactoring findings**:
   - If solid-reviewer flags violation in same region as refactor-advisor suggestion: corroborate — "SOLID issue confirms refactoring need"
   - If tdd-validator finds test gap in code targeted for refactoring: escalate refactoring priority — "Harden Before Depending applies"
   - If compat-checker identifies breaking change addressable via preparatory refactoring: note opportunity — "Prep refactoring can ease migration"
   - If refactor-advisor suggests prep commits: note that commit-planner should sequence them before feature commits

5. **Produce unified verdict**:
   - **APPROVED**: Plan aligns with ADRs, breaking changes are acceptable and tested
   - **BLOCKED**: Unresolvable ADR violations or untested breaking changes
   - **ADR_REQUIRED**: Plan introduces new patterns needing documented decisions

### Step 7: Auto-satisfy

If verdict is APPROVED:
- Run: `req satisfy commit_plan adr_reviewed tdd_planned solid_reviewed --session [current_session_id]`
- Output: "All 4 planning requirements satisfied (commit_plan, adr_reviewed, tdd_planned, solid_reviewed)"

### Step 8: Cleanup

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
- solid-reviewer: [status]
- refactor-advisor: [status]
- commit-planner: [status]

## ADR Compliance
[Findings from adr-guardian, cross-referenced with other agents]

## Breaking Changes
[Findings from backward-compatibility-checker]

## Testability
[Findings from tdd-validator, cross-referenced with breaking changes]

## SOLID Principles
[Findings from solid-reviewer, cross-referenced with other agents]

## Preparatory Refactoring
[Findings from refactor-advisor, cross-referenced with SOLID/TDD/compat findings]

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

## Comparison with /plan-review (Lightweight Alternative)

| Aspect | /arch-review (recommended) | /plan-review (lightweight) |
|--------|---------------------------|---------------------------|
| Execution | Agent Teams (collaborative) | Subagents (sequential) |
| Agents | ADR guardian + compat-checker + TDD validator + SOLID reviewer + refactor-advisor + commit planner | ADR guardian + commit planner |
| Cross-validation | Agents cross-reference findings | None |
| Focus | Holistic architecture assessment + commit strategy | ADR compliance + commit strategy |
| Satisfies | `commit_plan`, `adr_reviewed`, `tdd_planned`, `solid_reviewed` | Same 4 requirements |
| Cost | Higher (more thorough) | Lower (faster) |
