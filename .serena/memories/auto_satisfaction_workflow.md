# Auto-Satisfaction Workflow

> How skills automatically satisfy requirements when they complete successfully

## Overview

The auto-satisfaction mechanism eliminates manual `req satisfy` commands by automatically marking requirements as satisfied when mapped skills complete.

## Core Flow

```
User runs skill → Skill completes → PostToolUse hook fires →
Lookup skill-to-requirement mapping → Call reqs.satisfy() → Save state
```

## Key File: `hooks/auto-satisfy-skills.py`

**Hook Type**: PostToolUse (fires after Skill tool completes)
**Always returns**: Exit code 0 (fail-open design)

## Mapping System

### 1. Built-in Defaults (lines 42-46)
```python
DEFAULT_SKILL_MAPPINGS = {
    'requirements-framework:pre-commit': 'pre_commit_review',
    'requirements-framework:quality-check': 'pre_pr_review',
    'requirements-framework:codex-review': 'codex_reviewer',
}
```

### 2. Config-Based (via `satisfied_by_skill` field)
```yaml
pre_commit_review:
  satisfied_by_skill: 'requirements-framework:pre-commit'
```

**Merge strategy**: Config extends defaults (not replaces)

## State Persistence

**Location**: `.git/requirements/[branch].json`

**After satisfaction**:
```json
{
  "requirements": {
    "pre_commit_review": {
      "scope": "single_use",
      "sessions": {
        "session-id": {
          "satisfied": true,
          "satisfied_at": 1702345678,
          "satisfied_by": "skill",
          "metadata": {"skill": "requirements-framework:pre-commit"}
        }
      }
    }
  }
}
```

## Complete Example: Pre-Commit Review

1. `git commit` → **BLOCKED** (requirement not satisfied)
2. `/requirements-framework:pre-commit` → Agents run, skill completes
3. `auto-satisfy-skills.py` fires → Maps skill to `pre_commit_review` → Calls `reqs.satisfy()`
4. `git commit` → **SUCCESS** (requirement satisfied)
5. `clear-single-use.py` fires → Clears single_use scope
6. Next `git commit` → **BLOCKED** again (scope cleared)

## Configuration

Add to any requirement:
```yaml
my_requirement:
  satisfied_by_skill: 'my-custom-skill'  # Links skill to requirement
```

## Related Files

- `hooks/auto-satisfy-skills.py` - PostToolUse hook (skill completion)
- `hooks/clear-single-use.py` - PostToolUse hook (clears after trigger)
- `hooks/lib/requirements.py:340` - `BranchRequirements.satisfy()` method
- `hooks/lib/config.py:1370` - Config attribute access
