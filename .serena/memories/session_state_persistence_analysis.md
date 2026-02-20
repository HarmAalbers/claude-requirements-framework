# Requirements Framework: Session & State Persistence Analysis

## Overview
The requirements framework uses a two-location architecture with sophisticated session and state persistence. Requirements are tracked per-branch in `.git/requirements/[branch].json`, while sessions are tracked in a global registry at `~/.claude/sessions.json`.

---

## 1. SESSION LIFECYCLE

### Session Creation & Registry
**File**: `hooks/lib/session.py`

- **Session ID Format**: 8-character hex (normalized from full UUIDs)
  - Full UUIDs like `cad0ac4d-3933-45ad-9a1c-14aec05bb940` are normalized to `cad0ac4d`
  - Ensures consistent format across `CLAUDE_SESSION_ID` env var and PPID fallback

- **Registry Location**: `~/.claude/sessions.json` (global, all projects)

- **Registry Structure**:
  ```json
  {
    "version": "1.0",
    "sessions": {
      "abc12345": {
        "pid": 12345,            // hook subprocess PID
        "ppid": 12340,           // Claude Code session process ID (used for alive check)
        "project_dir": "/path/to/project",
        "branch": "feature/auth",
        "started_at": 1234567890,
        "last_active": 1234567895
      }
    }
  }
  ```

### Registry Lifecycle

1. **SessionStart Hook** (`handle-session-start.py`):
   - Cleans stale sessions (checks if ppid is still alive)
   - Updates registry with current session: `update_registry(session_id, project_dir, branch)`
   - Initializes session metrics file
   - Auto-registers project in upgrade discovery registry

2. **SessionEnd Hook** (`handle-session-end.py`):
   - Removes session from registry: `remove_session_from_registry(session_id)`
   - **Does NOT clear session-scoped requirement state by default**
     - Controlled by config: `hooks.session_end.clear_session_state` (default: False)
     - This is the KEY design decision: session state survives session end!

3. **Stale Session Cleanup**:
   - Automatic in `update_registry()` - removes entries where ppid is dead
   - Manual via `cleanup_stale_sessions()` 
   - Uses `is_process_alive(ppid)` which calls `os.kill(pid, 0)` without sending signal

### Thread-Safe Registry Operations
**File**: `hooks/lib/registry_client.py`

- **Atomic Read-Modify-Write**: Uses exclusive file locking (fcntl)
- **Fail-Open Design**: Registry errors never block hooks (always return empty registry)
- **Atomic Writes**: Temp file → fsync → atomic rename (POSIX guarantee)

---

## 2. STATE STORAGE

### State File Organization

**Location**: `.git/requirements/[branch-name].json` (automatically gitignored)
- In worktrees: uses COMMON git directory to share state across worktrees
- Fallback: `[project]/.git/requirements/` for non-git directories

**State File Schema**:
```json
{
  "version": "1.0",
  "branch": "feature/auth",
  "project": "/path/to/project",
  "created_at": 1234567890,
  "updated_at": 1234567890,
  "requirements": {
    "commit_plan": {
      "scope": "session",
      "sessions": {
        "abc123": {
          "satisfied": true,
          "satisfied_at": 1234567890,
          "satisfied_by": "skill",
          "metadata": {"skill": "plan-review"},
          "expires_at": null
        }
      }
    },
    "pre_commit_review": {
      "scope": "single_use",
      "sessions": {
        "abc123": {
          "satisfied": true,
          "triggered": true,
          "triggered_at": 1234567890,
          "satisfied_at": 1234567891,
          "satisfied_by": "skill"
        }
      }
    },
    "permanent_req": {
      "scope": "permanent",
      "satisfied": true,
      "satisfied_at": 1234567890,
      "satisfied_by": "cli"
    }
  }
}
```

### Key Design: Session Keys Within Branch State

**Critical Insight**: State files are keyed by **branch**, but within each requirement, there's a **nested session dictionary**.

Example flow:
1. Branch `feature/auth` has state file: `.git/requirements/feature-auth.json`
2. Within that file, requirement `commit_plan` has:
   ```
   sessions: {
     "abc123": { satisfied: true, ... },  // Session 1
     "def456": { satisfied: false, ... }  // Session 2
   }
   ```
3. When checking `commit_plan` in session `abc123`, the framework looks at `sessions["abc123"].satisfied`
4. When a NEW session starts on same branch, it gets its own entry in `sessions` dict

### State File Thread Safety
- Shared lock (fcntl) for reads
- Exclusive lock for writes
- Atomic write: temp file → fsync → rename
- Fail-open on all I/O errors

---

## 3. REQUIREMENT SCOPES & CLEARING BEHAVIOR

### Scope Definitions

**File**: `hooks/lib/requirements.py` - `BranchRequirements` class

| Scope | Storage | Clearing | Use Case |
|-------|---------|----------|----------|
| **session** | `sessions[session_id]` | Survives session end by design | Planning requirements per session |
| **branch** | Root of requirement state | Never auto-cleared | One-time per branch approvals |
| **single_use** | `sessions[session_id]` | Cleared after trigger action (e.g., git commit) | Must review before EACH commit |
| **permanent** | Root of requirement state | Never cleared | Security reviews, compliance |

### Scope Checking Logic

**Session Scope**:
```python
# is_satisfied(req_name, scope='session')
if scope == 'session':
    sessions = req_state.get('sessions', {})
    if self.session_id not in sessions:
        return False
    return sessions[self.session_id].get('satisfied', False)
```

**Branch Scope**:
```python
# is_satisfied(req_name, scope='branch')
if scope == 'branch':
    return req_state.get('satisfied', False)  # Root level
```

### Branch-Level Override for Session Reqs

Important: Session-scoped requirements can also have a branch-level override:
```python
if scope in ('session', 'single_use') and req_state.get('satisfied', False):
    # Branch-level satisfaction exists - skip session check
    return True
```
This allows `req satisfy --branch commit_plan` to satisfy for ALL sessions.

---

## 4. THE FOUR SESSION-SCOPED REQUIREMENTS

These are the ones that re-trigger after `/arch-review` creates a new session:

### 1. `commit_plan`
- **Scope**: session
- **Purpose**: Requires planning before code changes
- **Satisfied By**: `/arch-review` or `/plan-review` skill
- **Clearing**: Survives session end (stays satisfied in persistent state)
- **When Re-triggered**: When new session starts on same branch after plan approval

### 2. `adr_reviewed`
- **Scope**: session
- **Purpose**: Ensure ADRs are reviewed before changes
- **Satisfied By**: `/arch-review` skill
- **Clearing**: Survives session end
- **When Re-triggered**: New session on same branch

### 3. `tdd_planned`
- **Scope**: session
- **Purpose**: TDD approach documented in plan
- **Satisfied By**: `/arch-review` skill
- **Clearing**: Survives session end
- **When Re-triggered**: New session on same branch

### 4. `solid_reviewed`
- **Scope**: session
- **Purpose**: SOLID principles reviewed in plan
- **Satisfied By**: `/arch-review` skill
- **Clearing**: Survives session end
- **When Re-triggered**: New session on same branch

---

## 5. HOW `/arch-review` SATISFIES REQUIREMENTS

**File**: `hooks/auto-satisfy-skills.py`

### Skill-to-Requirement Mapping

Default mappings:
```python
DEFAULT_SKILL_MAPPINGS = {
    'requirements-framework:pre-commit': 'pre_commit_review',
    'requirements-framework:quality-check': 'pre_pr_review',
    'requirements-framework:codex-review': 'codex_reviewer',
    'requirements-framework:plan-review': ['commit_plan', 'adr_reviewed', 'tdd_planned', 'solid_reviewed'],
    'requirements-framework:deep-review': 'pre_pr_review',
    'requirements-framework:arch-review': ['commit_plan', 'adr_reviewed', 'tdd_planned', 'solid_reviewed'],
}
```

### Satisfaction Flow

1. User runs `/arch-review` skill
2. Skill tool completes → triggers `PostToolUse` hook
3. Hook extracts skill name from input: `extract_skill_name(tool_input)`
4. Hook looks up mapped requirements: `skill_mappings['requirements-framework:arch-review']`
5. For each mapped requirement:
   ```python
   scope = config.get_scope(req_name)  # 'session'
   reqs.satisfy(req_name, scope, method='skill', metadata={'skill': skill_name})
   ```
6. State is saved to `.git/requirements/[branch].json`
7. Session metrics recorded: `metrics.record_requirement_satisfied(req_name, ...)`

**Key Point**: Satisfaction is scoped to CURRENT SESSION only.
- State saved: `sessions[current_session_id].satisfied = True`
- Other sessions on same branch are unaffected

---

## 6. THE CRITICAL DATA FLOW: SESSION END → NEW SESSION

### When Session Ends (SessionEnd Hook)

1. **Session removed from registry**: `remove_session_from_registry(session_id)`
   - Session no longer listed in `~/.claude/sessions.json`

2. **Session-scoped requirement state is NOT cleared** (by default):
   - State in `.git/requirements/feature-auth.json` remains:
     ```json
     "commit_plan": {
       "scope": "session",
       "sessions": {
         "abc123": { "satisfied": true, ... }  // Still here!
       }
     }
     ```

3. **Session metrics still exist**: `.git/requirements/sessions/abc123.json`

### When New Session Starts (SessionStart Hook)

1. **New session_id generated**: e.g., `def456` (different 8-char hex)

2. **Registry updated**: `update_registry(def456, project_dir, branch)`
   - New entry in `~/.claude/sessions.json`

3. **Session state initialized**:
   - State file loaded: `.git/requirements/feature-auth.json`
   - Checked: is `commit_plan` satisfied for NEW session `def456`?
   - Query: `sessions["def456"]` → doesn't exist → NOT satisfied
   - Old session data (`abc123`) remains untouched in state file

4. **Status displayed** showing unsatisfied requirements:
   - `/arch-review` recommended to satisfy the four requirements

### Why Requirements Re-Trigger

This is intentional behavior:
- **Session-scoped** requirements force re-evaluation each session
- Same branch, different session = fresh start
- Prevents "satisfied it once, never again" pattern
- Ensures planning requirements checked before EACH session's work

---

## 7. THE STOP HOOK VERIFICATION

**File**: `hooks/handle-stop.py`

### Requirement Checking at Session End

When Claude tries to stop:

```python
for req_name in config.get_all_requirements():
    scope = req_config.get('scope', 'session')
    
    # Only check if triggered this session
    if not reqs.is_triggered(req_name, scope):
        continue
    
    # Check satisfaction
    if not reqs.is_satisfied(req_name, scope):
        unsatisfied.append(req_name)

if unsatisfied:
    # BLOCK STOP - show resolution guide
    emit_json({"decision": "block", "reason": "..."})
else:
    # ALLOW STOP
    return 0
```

### Critical: stop_hook_active Flag

Prevents infinite loops:
```python
if input_data.get('stop_hook_active', False):
    return 0  # Already continued once - DON'T BLOCK AGAIN
```

If hook blocks, Claude continues → hook runs again with flag set → allows stop.

### Session Learning Prompt

When stop is allowed and session had meaningful activity (>5 tool uses):
- Emits: "Run `/session-reflect` to analyze patterns"
- Recorded in session metrics for future analysis

---

## 8. SINGLE_USE CLEARING

**File**: `hooks/clear-single-use.py`

### Single-Use Requirement Lifecycle

```python
# Triggered by actions (e.g., git commit)
reqs.mark_triggered('pre_commit_review', scope='single_use')

# After user satisfies it
reqs.satisfy('pre_commit_review', scope='single_use', method='skill')

# After the trigger action completes
reqs.clear_single_use('pre_commit_review')  # Clears for THIS session only
```

### Data Flow

1. Marked triggered: `sessions[session_id].triggered = True`
2. Satisfied: `sessions[session_id].satisfied = True`
3. Cleared: `sessions[session_id]` **removed from sessions dict**
4. Next trigger: Must satisfy again (force before EACH action)

---

## 9. STATE MIGRATIONS & SESSION ID NORMALIZATION

### Session ID Normalization

**Critical Bug Fix**: UUIDs vs 8-char IDs

Before: CLAUDE_SESSION_ID provided full UUIDs, PPID fallback generated 8-char
- Caused state mismatch: same session, different keys

Now: `normalize_session_id()` standardizes ALL to 8-char format:
```python
def normalize_session_id(session_id: str) -> str:
    # "cad0ac4d-3933-45ad-9a1c-14aec05bb940" → "cad0ac4d"
    # "08345d22" → "08345d22" (idempotent)
    # "" → generates new ID
```

Runs at:
- Session creation
- Registry updates
- State loading (BranchRequirements init)

### State Key Migration

BranchRequirements automatically migrates old full-UUID keys to 8-char:
```python
def _migrate_session_keys(self):
    # One-time migration when loading state
    # Converts all session keys from old format to normalized format
    # Keeps newer timestamp if both exist
    # Runs every load but idempotent and fail-safe
```

---

## 10. FAIL-OPEN DESIGN THROUGHOUT

### Registry Client (RegistryClient)
- JSON decode error? Return empty registry
- I/O error? Return empty registry
- Never blocks, logs warning

### State Storage (state_storage.py)
- Corrupted state file? Return empty state
- Permission denied? Return empty state
- File locking errors? Log and continue

### Session.py
- Registry read fails? get_session_id() raises SessionNotFoundError with helpful message
- But for hooks: session_id always provided by Claude Code

### Hooks (all)
- Config load error? Skip framework
- State save error? Continue (fail-open)
- Status format error? Return 0 (allow proceed)

**Philosophy**: "Hook errors never block user work"

---

## 11. DATA SURVIVAL ACROSS SESSIONS

### What SURVIVES Session End

✅ **Persists in `.git/requirements/[branch].json`**:
- All session-scoped requirement data (by design)
- All branch-scoped requirement data
- All permanent requirement data
- Session metrics in `.git/requirements/sessions/`

✅ **Persists in `~/.claude/sessions.json`**:
- Session registry (but old session removed, new one added)
- Clean history of CURRENT sessions

### What DISAPPEARS

❌ **Cleared when session ends**:
- Session registry entry removed
- Session-scoped requirement "triggered" flag reset (new session won't have it)
- In-memory session context

### Key Asymmetry

**State travels between sessions**, but **session context doesn't**:
- Old session `abc123` satisfied `commit_plan` → stays in state file
- New session `def456` starts → sees unsatisfied state (different session_id)
- Must run `/arch-review` again in new session

---

## 12. CONFIGURATION CONTROL

### Session End Clearing (Optional)

```yaml
hooks:
  session_end:
    clear_session_state: false  # default - KEEP session requirements
```

If enabled: `SessionEnd` hook would call `reqs.clear(req_name)` for all session-scoped reqs.
- Completely removes requirement from state
- Not recommended (breaks workflow)

### Stop Verification Scopes

```yaml
hooks:
  stop:
    verify_requirements: true
    verify_scopes: ['session']  # Only check session-scoped
```

Can also verify: `['session', 'branch']`, `['session', 'branch', 'permanent']`

---

## Summary: The Design Pattern

1. **Branch-based state storage** (`.git/requirements/[branch].json`)
   - Follows branch throughout its lifetime
   - Shared by all sessions working on that branch

2. **Session-scoped requirements** survive by design
   - State stored per-session within branch file
   - Each new session gets fresh entry
   - Enables "once per session" workflows

3. **Registry tracking** for current sessions only
   - `~/.claude/sessions.json` is ephemeral
   - Cleaned up when sessions end
   - Used for CLI auto-detection and session warnings

4. **Normalized session IDs** ensure consistency
   - 8-character hex format everywhere
   - Automatic migration for old UUID keys

5. **Fail-open throughout**
   - Registry/state errors never block work
   - Logged for debugging
   - Graceful degradation

This architecture supports:
- **Re-evaluation each session** (via session-scoped requirements)
- **Cross-session persistence** (via branch-scoped state)
- **Session discovery** (via registry)
- **Thread-safe concurrent access** (via file locking)
- **Data safety** (via atomic writes)
