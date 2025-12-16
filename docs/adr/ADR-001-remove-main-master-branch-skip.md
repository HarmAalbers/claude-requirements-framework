# ADR-001: Remove Main/Master Branch Skip

## Status
Accepted

## Date
2024-12-16

## Context

The requirements framework originally skipped all requirement checks when on `main` or `master` branches. The rationale was:
- Protected branches shouldn't need planning requirements
- Direct commits to main/master are rare and often hotfixes

However, this created problems:
1. **Inconsistent enforcement**: Users working directly on main (e.g., in personal projects or during initial setup) had no guardrails
2. **Session registry gaps**: The early return meant sessions on main/master weren't registered, breaking CLI discovery
3. **Confusion**: Different behavior on different branches was unexpected

## Decision

Remove the main/master branch skip from `check-requirements.py` and `handle-stop.py`. Requirements are now enforced on all branches equally.

### Affected Files
- `hooks/check-requirements.py` - Removed skip logic
- `hooks/handle-stop.py` - Removed skip logic
- `hooks/test_requirements.py` - Removed `test_main_master_skip` test

### What Still Skips on Main/Master
- `lib/branch_size_calculator.py` - Still skips, but for a valid reason: can't calculate diff size when there's no base branch to compare against

## Consequences

### Positive
- Consistent behavior across all branches
- Session registry works correctly on all branches
- Users on main/master still get workflow reminders

### Negative
- Users who want different behavior on main/master must configure it explicitly via local config:
  ```yaml
  # .claude/requirements.local.yaml
  enabled: false  # Disable on this branch
  ```

### Neutral
- Test count reduced from 148 to 147 (removed obsolete test)

## Alternatives Considered

1. **Make it configurable**: Add `skip_branches: [main, master]` config option
   - Rejected: Adds complexity, and most users want consistent behavior

2. **Keep the skip but fix registry**: Register sessions even when skipping
   - Rejected: Still creates confusing inconsistent behavior

## Related
- ADR-002: Use Claude Code's Native Session ID
