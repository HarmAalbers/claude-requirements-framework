# ADR-009: Agent Auto-Fix for Plan Validation

## Status
Approved (2026-01-18)

## Context

The adr-guardian agent validates implementation plans against Architecture Decision Records (ADRs). Previously, any ADR violation required manual intervention - even for minor, unambiguous issues like wrong directory paths or missing required sections.

This created workflow friction:
1. User exits plan mode with a plan
2. adr-guardian identifies a minor violation (e.g., wrong path per ADR)
3. Agent outputs BLOCKED with fix instructions
4. User manually edits the plan
5. User re-runs validation
6. Process repeats for each violation

Many violations have obvious, unambiguous fixes that the agent could apply directly, streamlining the workflow significantly.

## Decision

**Agents that validate plans (not code) may have Edit tool access to auto-fix violations when the fix is unambiguous.**

The adr-guardian agent now includes `Edit` in its `allowed-tools` and can:
1. Identify ADR violations in plan files
2. Assess whether each violation has an unambiguous fix
3. Apply fixes directly to the plan file
4. Re-validate after fixing
5. Only output APPROVED after all violations are resolved (manually or via auto-fix)

## Allowed

**Auto-fixable violations** (agent may edit plan directly):
- Wrong directory paths when ADR specifies correct location
- Missing required sections that have standard templates
- Naming convention violations with clear correct alternatives
- Pattern mismatches where ADR specifies the allowed pattern

**Auto-fix workflow**:
1. Identify violation and assess fixability
2. Use Edit tool to modify plan file
3. Document the change in agent output ("Auto-Fix Applied" section)
4. Re-validate the modified plan
5. Continue checking for other violations

**Required output format** when auto-fixing:
```markdown
## Auto-Fix Applied

**Original Violation**: [What was wrong]
**ADR Reference**: ADR-XXX Section Y
**Fix Applied**: [What was changed]
**Location**: [File path and section]

[Continue with normal validation...]
```

## Prohibited

**Never auto-fix**:
- Code files (auto-fix is for plans only)
- Ambiguous violations with multiple valid resolutions
- Violations that would change the plan's intent or scope
- Fundamental architectural conflicts (these require user decision)

**Never silent**:
- All auto-fixes MUST be documented in the agent output
- User must be able to see what was changed and why

**Never assume**:
- If unsure whether a fix is correct, output BLOCKED and explain
- User decision required for anything ambiguous

## Consequences

### Positive
- Faster workflow for minor violations
- Reduced back-and-forth between validation and manual editing
- Plans can reach APPROVED state more quickly
- Maintains quality while reducing friction

### Negative
- Agent can modify user's plan files (requires trust)
- Risk of incorrect fixes if assessment wrong
- More complex agent logic (fixability assessment)

### Mitigations
- All fixes documented in output (auditable)
- Only plans (not code) can be auto-fixed
- Conservative approach: when in doubt, BLOCK instead of fix
- Re-validation after fix catches incorrect fixes

## Implementation

### Agent Configuration
```yaml
# In plugin/agents/adr-guardian.md frontmatter
allowed-tools: ["Read", "Edit", "Glob", "Grep"]
```

### Assessment Logic
The agent assesses fixability based on:
1. **Clarity**: Is there exactly one correct resolution?
2. **Scope**: Does the fix only affect the specific violation?
3. **Intent**: Does the fix preserve the plan's original intent?

If all three are true → auto-fix
If any is false → BLOCK with instructions

### Integration with plan-review Command
The plan-review command passes context to adr-guardian indicating auto-fix is available:
```
IMPORTANT: You have Edit tool access. If you find ADR violations that can be
auto-fixed, edit the plan file directly to fix them, then re-validate.
```

## Related ADRs

- **ADR-006**: Plugin-Based Architecture - Defines agent structure and tool permissions
- **ADR-007**: Deterministic Command Orchestrators - plan-review orchestrates adr-guardian

## References

- Commit: `5148041` - feat: Add automated plan-review workflow
- Agent: `plugin/agents/adr-guardian.md`
- Command: `plugin/commands/plan-review.md`
