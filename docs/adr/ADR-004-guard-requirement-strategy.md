# ADR-004: Guard Requirement Strategy Type

## Status
Accepted

## Date
2025-12-16

## Context

The requirements framework initially supported two strategy types:
- **Blocking**: Requires manual satisfaction via `req satisfy`
- **Dynamic**: Calculated values with thresholds (e.g., branch size limits)

However, some requirements check boolean conditions rather than workflow steps:
- Don't edit protected branches (unless emergency hotfix)
- Don't deploy on Fridays (unless approved)
- Don't modify certain files without approval

These don't fit blocking (no workflow to complete) or dynamic (not a measured value). They're binary conditions that either pass or fail.

ADR-001 removed hardcoded main/master branch skipping in favor of "consistent behavior across all branches." This created a need for an explicit, opt-in mechanism for users who want branch protection.

## Decision

Add a third strategy type: **guard** requirements.

Guards check boolean conditions and block operations that fail the check. They can be temporarily approved (session-scoped) for emergencies.

### Guard Requirement Structure

```yaml
requirements:
  requirement_name:
    enabled: true
    type: guard
    guard_type: [specific_guard_type]  # Required field
    trigger_tools: [Edit, Write]       # When to check
    # guard_type-specific config fields
```

### Approved Guard Types

**`protected_branch`**: Block edits on specified branches
- Config: `protected_branches: [branch_list]`
- Default: `['master', 'main']`

```yaml
protected_branch:
  enabled: true
  type: guard
  guard_type: protected_branch
  protected_branches:
    - master
    - main
```

### Emergency Override Pattern

```bash
req approve protected_branch  # Session-scoped only
```

Approvals expire when the session ends, ensuring protection is restored for the next session.

### Implementation Requirements

1. Guards must **fail-open** on errors (never block due to bugs)
2. Approvals are **session-scoped** (expire when session ends)
3. Guard condition checks must be **stateless**
4. Unknown `guard_type` must fail-open with warning

### Prohibited Patterns

**Do NOT use guards for:**
- Workflow requirements that need completion steps → Use `blocking` type
- Requirements with measured values and thresholds → Use `dynamic` type
- Requirements that need branch-scoped persistence → Use `blocking` type

**Prohibited:**
- Permanent approvals (must expire with session)
- Guards with side effects (only check conditions)
- Guards that require external services (must work offline)
- Hardcoded guard logic outside the strategy pattern

## Implementation

### Files Modified

- `hooks/lib/requirement_strategies.py` - `GuardRequirementStrategy` class
- `hooks/lib/config.py` - Validation for `guard` type and `guard_type` field
- `hooks/check-requirements.py` - Integration with strategy dispatch
- `examples/global-requirements.yaml` - Example configuration

### Strategy Pattern

```python
class GuardRequirementStrategy(RequirementStrategy):
    def check(self, req_name, config, reqs, context):
        # Check if already approved for this session
        if reqs.is_satisfied(req_name, scope='session'):
            return None  # Allow

        # Dispatch to specific guard type handler
        guard_type = config.get_attribute(req_name, 'guard_type', None)
        if guard_type == 'protected_branch':
            return self._check_protected_branch(...)

        return None  # Unknown guard type - fail open
```

## Consequences

### Positive
- Clear separation of condition-based vs. workflow-based requirements
- Session-scoped approvals enable emergency overrides without permanent bypass
- Extensible pattern for adding new guard types
- Aligns with ADR-001 (opt-in protection vs. hardcoded skips)
- Users consciously choose to enable branch protection

### Negative
- Third strategy type adds complexity to the framework
- Users must understand guard vs. blocking distinction
- Approval mechanism requires understanding session scope

### Neutral
- Test count increased from 161 to 167 tests

## Extending with New Guard Types

To add a new guard type (e.g., `readonly_files`):

1. Add handler method in `GuardRequirementStrategy`:
   ```python
   def _check_readonly_files(self, req_name, config, context):
       # Check condition, return denial or None
   ```

2. Add dispatch in `check()` method:
   ```python
   elif guard_type == 'readonly_files':
       return self._check_readonly_files(...)
   ```

3. Add config validation if needed in `config.py`

4. Add tests covering the new guard type

5. Update this ADR with the new guard type

## Related

- ADR-001: Remove Main/Master Branch Skip (this provides the opt-in mechanism)
- ADR-002: Use Claude Code's Native Session ID (session-scoped approvals depend on this)
