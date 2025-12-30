# ADR-007: Deterministic Command Orchestrators

## Status
Approved (2025-12-30)

## Context

The pre-commit and quality-check commands coordinate multiple specialized review agents to provide comprehensive code review before commits and PRs. The initial implementation used natural language instructions in markdown files ("Launch agents...", "Run in parallel...", "Aggregate results...") that Claude interpreted at runtime.

This approach created **non-deterministic execution**:
- Same input could produce different output
- Agent execution order varied
- Parallel mode sometimes executed sequentially
- Critical steps could be skipped
- Result aggregation was inconsistent
- Verdict logic varied between runs

Analysis by expert agents revealed the commands were "95% documentation, 5% executable logic" - they described what SHOULD happen but didn't guarantee it would happen.

## Decision

**Transform orchestrator commands from documentation-style to deterministic step-by-step execution workflows.**

Commands now have explicit, ordered steps that Claude MUST follow:
1. **Explicit bash commands** for scope acquisition and file detection
2. **Defined argument parsing** with clear flag-setting logic
3. **Enforced agent sequencing** with blocking gates and execution order
4. **Structured result aggregation** by severity levels
5. **Clear verdict logic** based on issue counts

## Allowed

**Deterministic workflow pattern for commands**:

```markdown
## Step 1: Identify Changes to Review

Execute these bash commands:
```bash
git diff --cached --name-only > /tmp/review_scope.txt
if [ ! -s /tmp/review_scope.txt ]; then
  git diff --name-only > /tmp/review_scope.txt
fi
```

If empty: Output "No changes" and EXIT

## Step 2: Parse Arguments

If $ARGUMENTS is empty OR contains "tools": RUN_TOOL_VALIDATOR=true
If $ARGUMENTS contains "parallel": PARALLEL_MODE=true

## Step 3: Execute Blocking Gate

If RUN_TOOL_VALIDATOR is true:
  Use Task tool to launch tool-validator
  Wait for completion
  If CRITICAL errors: STOP

## Step 4: Execute Agents

If PARALLEL_MODE is true:
  Launch all agents in SINGLE message with multiple Task calls
Else:
  Launch sequentially

## Step 5: Aggregate Results

Count by severity: CRITICAL_COUNT, IMPORTANT_COUNT

## Step 6: Provide Verdict

If CRITICAL_COUNT > 0: ❌ FIX ISSUES FIRST
Else if IMPORTANT_COUNT > 5: ⚠️ REVIEW RECOMMENDED
Else: ✅ READY
```

**Key patterns**:
- Bash commands in code blocks for deterministic operations
- Explicit conditionals ("If X is true: do Y")
- Clear flag-based state management
- Ordered step numbers that must be followed
- Explicit tool invocations ("Use Task tool to launch...")
- Defined exit conditions
- Severity-based aggregation
- Threshold-based verdicts

**File type detection** (quality-check specific):
```bash
grep -E '(test_|_test\.)' /tmp/scope.txt > /tmp/has_tests.txt
git diff | grep -E '(BaseModel|interface )' > /tmp/has_types.txt
```

Set flags based on detection:
- HAS_TEST_FILES, HAS_TYPE_CHANGES, HAS_COMMENT_CHANGES, HAS_SCHEMA_CHANGES
- Skip agents that don't apply

**Blocking gates**:
- tool-validator MUST run first
- If CRITICAL errors from tool-validator: STOP (don't run AI review)
- Rationale: No point in AI review if objective tools fail

**Parallel execution**:
- Must use: "Launch in SINGLE message with multiple Task calls"
- This enables true parallel execution by Claude Code
- Don't just say "run in parallel" - be explicit

## Prohibited

**Vague instructions that rely on interpretation**:
- ❌ "Launch agents..."  (how? which ones? what order?)
- ❌ "Run in parallel..." (maybe, maybe not)
- ❌ "Aggregate results..." (how? what format?)
- ❌ "Provide recommendation..." (what criteria?)

**Implicit state management**:
- ❌ Assuming Claude remembers which agents ran
- ❌ Assuming Claude knows how to count severity levels
- ❌ Assuming verdicts follow consistent logic

**Non-explicit conditionals**:
- ❌ "If test files modified" (how to detect?)
- ❌ "If Pydantic models changed" (what's the pattern?)
- ❌ "Based on file types" (how to determine?)

## Consequences

### Positive
- ✅ **Reproducible**: Same input produces same output
- ✅ **Testable**: Can verify command behavior
- ✅ **Predictable**: Users know exactly what will happen
- ✅ **Reliable**: Critical steps guaranteed to execute
- ✅ **Debuggable**: Clear execution path when issues occur
- ✅ **Parallel works**: True parallel execution when requested
- ✅ **Smart**: File type detection skips irrelevant agents

### Negative
- ⚠️ **More verbose**: Commands are longer (~200 lines vs ~100)
- ⚠️ **Less flexible**: Harder to adapt workflow on the fly
- ⚠️ **Maintenance**: More explicit logic to maintain

### Tradeoffs
- Sacrificed some flexibility for reliability
- Commands are less elegant but more robust
- More work upfront, less debugging later

## Enforcement

This pattern is enforced by:

1. **Code review** - New commands must follow step-by-step pattern
2. **Testing** - Commands must produce consistent results
3. **This ADR** - Documented pattern for future command development

New orchestrator commands must:
- Use numbered steps (Step 1, Step 2, etc.)
- Execute bash commands explicitly for critical operations
- Define all conditionals clearly
- Specify exact Task tool invocations
- Provide explicit aggregation logic
- Define verdict criteria with thresholds

## Examples

### Before (Non-Deterministic)

```markdown
## Workflow
1. Get changes from `git diff`
2. Parse arguments
3. Launch agents
4. Aggregate results
5. Provide recommendation
```

**Problems**: Each step is vague - Claude must guess how to execute

### After (Deterministic)

```markdown
## Step 1: Get Changes

Execute:
```bash
git diff --cached --name-only > /tmp/scope.txt
```

If /tmp/scope.txt is empty: EXIT

## Step 2: Parse Arguments

If $ARGUMENTS is empty OR contains "tools":
  RUN_TOOL_VALIDATOR=true

## Step 3: Execute Tool Validator

If RUN_TOOL_VALIDATOR is true:
  Use Task tool: subagent_type="pre-pr-review:tool-validator"
  Wait for completion
  If CRITICAL errors: STOP

[etc...]
```

**Benefits**: Every step has explicit instructions - no interpretation needed

## Related ADRs

- **ADR-006**: Plugin-Based Architecture - Established unified plugin structure that these commands live in
- **ADR-004**: Guard Requirement Strategy - Similar pattern of explicit condition checking

## References

- Commit: `57d0c1a` - feat: merge comprehensive pre-PR review toolkit into framework
- Analysis: Opus agent found commands were "95% documentation, 5% executable logic"
- Improvements: pre-commit.md (7-step workflow), quality-check.md (10-step workflow)
- Pattern inspiration: tool-validator agent (rated 10/10 for having explicit bash commands)

## Notes

This pattern emerged from real-world analysis showing that vague instructions led to unreliable behavior. The tool-validator agent succeeded (10/10 rating) because it had explicit bash commands for every tool. Other commands failed because they relied on Claude's interpretation.

The hybrid approach - deterministic orchestration with flexible formatting - preserves Claude's strengths (adaptive output, natural language) while guaranteeing critical operations execute correctly.

This is applicable beyond this framework: any Claude Code command that coordinates complex workflows should use this pattern.
