# Blocking Requirements Flow

> Complete lifecycle of blocking requirements from trigger to satisfaction

## Hook Entry Point: `check-requirements.py`

**Hook Type**: PreToolUse
**Triggers on**: Edit, Write, Bash (with command patterns)
**Returns**: Allow (exit 0) or Deny (exit 1 + message)

## Complete Flow

```
1. User: git commit -m "msg"
   ↓
2. PreToolUse hook fires (check-requirements.py)
   ↓
3. Trigger matching: git\s+commit matches requirement pattern
   ↓
4. Mark triggered: reqs.mark_triggered('pre_commit_review', 'single_use')
   ↓
5. Strategy check: BlockingRequirementStrategy.check()
   ↓
6a. NOT SATISFIED → Denial response with message → BLOCKED
6b. SATISFIED → None returned → ALLOWED
   ↓
7. If allowed: Bash executes git commit
   ↓
8. PostToolUse: clear-single-use.py fires
   ↓
9. Clear requirement: reqs.clear_single_use('pre_commit_review')
   ↓
10. Next commit: Requirement not satisfied → BLOCKED again
```

## Strategy Pattern

**Location**: `hooks/lib/blocking_strategy.py`

```python
class BlockingRequirementStrategy(RequirementStrategy):
    def check(self, req_name, config, reqs, context):
        scope = config.get_scope(req_name)
        if not reqs.is_satisfied(req_name, scope):
            return self._create_denial_response(...)
        return None  # Allow
```

## Trigger Matching

**Location**: `hooks/lib/config_utils.py:19-77`

Supports two formats:

### Simple (tool name)
```yaml
trigger_tools:
  - Edit
```

### Complex (tool + regex pattern)
```yaml
trigger_tools:
  - tool: Bash
    command_pattern: "git\\s+(commit|cherry-pick)"
```

## Requirement Scopes

| Scope | Clears When | Use Case |
|-------|------------|----------|
| **session** | Session ends | One-time setup per session |
| **single_use** | After trigger completes | Every commit needs review |
| **branch** | Manual clear or branch delete | Feature-level gates |
| **permanent** | Manual clear only | Project-wide requirements |

## State Storage: `.git/requirements/[branch].json`

```json
{
  "version": "1.0",
  "branch": "feature/auth",
  "requirements": {
    "pre_commit_review": {
      "scope": "single_use",
      "sessions": {
        "session-id": {
          "triggered": true,
          "satisfied": true,
          "satisfied_at": 1705000000,
          "satisfied_by": "skill"
        }
      }
    }
  }
}
```

## Satisfaction Methods

### 1. Via Skill (Auto)
```bash
/requirements-framework:pre-commit  # Runs agents
# auto-satisfy-skills.py fires → satisfies requirement
```

### 2. Via CLI (Manual)
```bash
req satisfy pre_commit_review --session abc123
```

### 3. Programmatic
```python
reqs.satisfy('pre_commit_review', scope='single_use', method='auto')
```

## Message Deduplication

**Location**: `hooks/lib/blocking_strategy.py:95-106`

Prevents spam from parallel tool calls:
- First occurrence: Full detailed message
- Within 5 seconds: Brief "⏸️ waiting..." message
- Cache key: `{project}:{branch}:{session}:{req_name}`

## Configuration Cascade

**Priority** (highest to lowest):
1. `.claude/requirements.local.yaml` (gitignored, personal)
2. `.claude/requirements.yaml` (project, version controlled)
3. `~/.claude/requirements.yaml` (global defaults)

## Related Files

- `hooks/check-requirements.py` - PreToolUse hook entry point
- `hooks/lib/blocking_strategy.py` - Blocking requirement implementation
- `hooks/lib/requirements.py:150` - `is_satisfied()` method
- `hooks/lib/requirements.py:413` - `clear_single_use()` method
- `hooks/lib/config_utils.py:19` - `matches_trigger()` function
- `hooks/clear-single-use.py` - PostToolUse hook for clearing
