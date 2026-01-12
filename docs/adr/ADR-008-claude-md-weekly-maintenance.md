# ADR-008: CLAUDE.md Weekly Maintenance

## Status
Accepted

## Date
2025-01-12

## Context

CLAUDE.md serves as the primary onboarding document for Claude Code when working with this repository. It contains:
- Build and test commands
- Architecture overview (hooks, lib modules, lifecycle)
- Key component references with file paths
- Development patterns and workflows

During a routine review, several discrepancies were discovered:
1. `requirement_strategies.py` was documented but no longer exists (refactored into modular strategy architecture)
2. `handle-plan-exit.py` hook was missing from the lifecycle documentation
3. Test count was outdated (claimed 447, actual is 68)
4. 10+ library modules added but not documented
5. Plugin architecture not mentioned

These discrepancies accumulated over time as the codebase evolved faster than its documentation.

## Decision

Establish a weekly CLAUDE.md review process:

### Frequency
- Review CLAUDE.md at least once per week
- Best done at session start or when planning significant changes

### Review Checklist
1. **Hook files**: Compare documented hooks against `hooks/*.py`
2. **Library modules**: Compare documented lib files against `hooks/lib/*.py`
3. **Test count**: Verify test count with `grep -c "def test_" hooks/test_requirements.py`
4. **Scripts**: Verify documented scripts exist at repo root
5. **Architecture accuracy**: Ensure patterns described match implementation

### Update Triggers
Beyond weekly reviews, update CLAUDE.md immediately when:
- Adding/removing/renaming hooks
- Refactoring library architecture
- Changing build/test commands
- Modifying configuration cascade

## Consequences

### Positive
- Claude Code always has accurate context about the codebase
- Reduces confusion from stale documentation
- Catches drift before it accumulates
- Forces periodic architecture reflection

### Negative
- Adds maintenance overhead (estimated: 5-10 minutes/week)
- May create frequent small commits to CLAUDE.md

### Neutral
- No code changes required
- Process is manual/honor-system based

## Alternatives Considered

1. **Automated doc generation**: Generate CLAUDE.md from code analysis
   - Rejected: Loses the narrative and "why" explanations that make CLAUDE.md valuable

2. **Pre-commit hook validation**: Check CLAUDE.md references exist
   - Rejected: Only catches missing files, not outdated descriptions or counts

3. **Monthly instead of weekly**: Less frequent reviews
   - Rejected: This codebase evolves rapidly; monthly allows too much drift

## Implementation

No code changes required. This ADR serves as the process documentation.

To verify CLAUDE.md accuracy:
```bash
# Check hook count
ls hooks/*.py | wc -l

# Check lib module count
ls hooks/lib/*.py | wc -l

# Check test count
grep -c "def test_" hooks/test_requirements.py
```

## Related
- CLAUDE.md - The file being maintained
- DEVELOPMENT.md - More detailed development documentation
