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

### Status Display Behavior

Guard requirements show **context-aware status** at session start:

- ✅ **Satisfied** when guard condition passes (e.g., NOT on protected branch)
- ⬜ **Unsatisfied** when guard condition fails (e.g., ON protected branch)

This differs from blocking requirements, which only show ✅ when manually satisfied.

#### Example: protected_branch

| Current Branch | Status Display | Reason |
|----------------|----------------|--------|
| feature/auth   | ✅ protected_branch | Not on protected branch → condition passes |
| master         | ⬜ protected_branch | On protected branch → condition fails |
| main           | ⬜ protected_branch | On protected branch → condition fails |

**After `req approve protected_branch` on master:**
| Current Branch | Status Display | Reason |
|----------------|----------------|--------|
| master         | ✅ protected_branch | Manually approved (session scope) |

Users only need to `req approve protected_branch` when on a protected branch and need emergency override.

#### Implementation

The `BranchRequirements.is_guard_satisfied()` method evaluates guard conditions for status display:

```python
def is_guard_satisfied(self, req_name: str, config, context: dict) -> bool:
    """
    Check if a guard requirement's condition is satisfied.

    Returns:
        True if guard condition passes or manually approved
        False if guard condition fails
    """
    # Manual approval takes precedence
    if self.is_satisfied(req_name, scope='session'):
        return True

    # Evaluate guard condition using strategy
    strategy = GuardRequirementStrategy()
    result = strategy.check(req_name, config, self, context)
    return result is None  # None means satisfied
```

The SessionStart hook (`handle-session-start.py`) uses this method for guard requirements:

```python
if req_type == 'guard':
    context = {'branch': branch, 'session_id': session_id, ...}
    satisfied = reqs.is_guard_satisfied(req_name, config, context)
else:
    satisfied = reqs.is_satisfied(req_name, scope)
```

This ensures status display reflects the actual guard condition, not just manual satisfaction.

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

- `hooks/lib/guard_strategy.py` - `GuardRequirementStrategy` class
- `hooks/lib/requirements.py` - `is_guard_satisfied()` method for context-aware status
- `hooks/handle-session-start.py` - Context-aware status display in `format_full_status()`
- `hooks/lib/config.py` - Validation for `guard` type and `guard_type` field
- `hooks/check-requirements.py` - Integration with strategy dispatch
- `hooks/test_requirements.py` - Tests for guard strategy and status display
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
- Test count increased from 161 to 170 tests (167 original + 3 for status display)

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
