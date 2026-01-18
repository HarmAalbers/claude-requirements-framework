# Hook Lifecycle

> The six hooks and when they fire in the requirements framework

## Complete Hook Chain

```
SessionStart → PreToolUse → [Tool Executes] → PostToolUse → Stop → SessionEnd
```

## 1. SessionStart: `handle-session-start.py`

**Fires**: When Claude Code session begins
**Purpose**: Clean stale sessions, register current session, inject status

**Actions**:
- Update session registry with current session ID
- Clean expired/stale sessions from state
- Inject full requirements status into context

## 2. PreToolUse: `check-requirements.py`

**Fires**: Before Edit, Write, Bash, EnterPlanMode, ExitPlanMode
**Purpose**: Block operations if requirements not satisfied

**Flow**:
1. Load config (cascade: global → project → local)
2. Check if tool/command matches trigger patterns
3. Mark requirement as triggered
4. Get strategy (blocking/dynamic/guard)
5. Call strategy.check()
6. Return allow (0) or deny (1 + message)

**Triggers Plan Mode**: ExitPlanMode enables ADR validation at planning time

## 3. PostToolUse: `auto-satisfy-skills.py`

**Fires**: After Skill tool completes
**Purpose**: Auto-satisfy requirements when review skills finish

**Mappings**:
```python
'requirements-framework:pre-commit' → 'pre_commit_review'
'requirements-framework:quality-check' → 'pre_pr_review'
'requirements-framework:codex-review' → 'codex_reviewer'
```

**Action**: `reqs.satisfy(req_name, scope, method='skill', metadata={...})`

## 4. PostToolUse: `clear-single-use.py`

**Fires**: After certain Bash commands complete
**Purpose**: Clear single_use requirements after trigger

**Example**: After `git commit` succeeds, clears `pre_commit_review` so next commit requires review again

## 5. PostToolUse: `handle-plan-exit.py`

**Fires**: After ExitPlanMode tool completes
**Purpose**: Show requirements status proactively before implementation

**Action**: Displays current requirement states to remind user what needs satisfaction

## 6. Stop: `handle-stop.py`

**Fires**: When Claude finishes/stops
**Purpose**: Verify session-scoped requirements before allowing stop

**Safety**: Checks `stop_hook_active` flag to prevent infinite loops

**Can Block**: Prevents session end if requirements unsatisfied (configurable)

## 7. SessionEnd: `handle-session-end.py`

**Fires**: When Claude Code session ends
**Purpose**: Cleanup - remove session from registry

**Optional**: Can clear session state (configurable)

## Hook Configuration

**Location**: Hook configs in `~/.claude/requirements.yaml`

Example:
```yaml
hooks:
  check_requirements:
    enabled: true
    stop_hook:
      enabled: true  # Allow stop hook to block
```

## Execution Order Example

**User workflow**:
```
1. Session starts → SessionStart hook
2. User edits file → PreToolUse blocks (adr_reviewed not satisfied)
3. User runs /adr-guardian → Skill completes → PostToolUse (auto-satisfy)
4. User edits file → PreToolUse allows (requirement now satisfied)
5. User commits → PreToolUse blocks (pre_commit_review not satisfied)
6. User runs /pre-commit → Skill completes → PostToolUse (auto-satisfy)
7. User commits → PreToolUse allows → Bash executes → PostToolUse (clear-single-use)
8. Claude stops → Stop hook verifies session requirements
9. Session ends → SessionEnd cleanup
```

## Related Files

- `hooks/handle-session-start.py` - SessionStart hook
- `hooks/check-requirements.py` - PreToolUse hook
- `hooks/auto-satisfy-skills.py` - PostToolUse (skill completion)
- `hooks/clear-single-use.py` - PostToolUse (single-use clearing)
- `hooks/handle-plan-exit.py` - PostToolUse (plan exit)
- `hooks/handle-stop.py` - Stop hook
- `hooks/handle-session-end.py` - SessionEnd hook
- `hooks/lib/session.py` - Session registry management
