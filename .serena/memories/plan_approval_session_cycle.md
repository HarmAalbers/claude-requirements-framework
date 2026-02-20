# Plan Approval → New Session Cycle

## The Complete Story: Planning Session → Implementation Session

This document traces the exact data flow when `/arch-review` satisfies requirements and then a new session begins on the same branch.

---

## Phase 1: Initial State (Before Any Session)

### Files on Disk
```
~/.claude/sessions.json
→ Empty (no active sessions)

.git/requirements/feature-auth.json
→ Empty or minimal state
   {
     "version": "1.0",
     "branch": "feature/auth",
     "requirements": {}
   }
```

---

## Phase 2: Planning Session Starts

### Event: SessionStart Hook Triggered

**Input**:
```json
{
  "session_id": "cad0ac4d-3933-45ad-9a1c-14aec05bb940",
  "hook_event_name": "SessionStart",
  "source": "startup",
  "cwd": "/path/to/repo"
}
```

### Step 1: Normalize Session ID

```python
raw_session = "cad0ac4d-3933-45ad-9a1c-14aec05bb940"
session_id = normalize_session_id(raw_session)
# Result: session_id = "cad0ac4d"
```

### Step 2: Update Session Registry

```python
update_registry("cad0ac4d", "/path/to/repo", "feature/auth")
```

**Registry Before**:
```json
{
  "version": "1.0",
  "sessions": {}
}
```

**Registry After**:
```json
{
  "version": "1.0",
  "sessions": {
    "cad0ac4d": {
      "pid": 45678,
      "ppid": 45670,  // Claude Code process
      "project_dir": "/path/to/repo",
      "branch": "feature/auth",
      "started_at": 1700000000,
      "last_active": 1700000000
    }
  }
}
```

### Step 3: Load Requirement State

```python
reqs = BranchRequirements("feature/auth", "cad0ac4d", "/path/to/repo")
# Loads: .git/requirements/feature-auth.json
# Session ID stored: self.session_id = "cad0ac4d"
```

### Step 4: Check Requirements for CURRENT Session

For each requirement, `is_satisfied(req_name, scope='session')`:

```python
# For commit_plan:
req_state = {
  "scope": "session",
  "sessions": {}  # Empty - first session on this branch
}

if "cad0ac4d" not in sessions:
  return False  # NOT SATISFIED
```

### Step 5: Display Status

**Context Injection** (SessionStart hook output):
```markdown
## Requirements Framework: Session Briefing

Branch: `feature/auth` | Session: `cad0ac4d`

### Quick Start
🚀 **Run `/arch-review`** → satisfies `commit_plan`, `adr_reviewed`, `tdd_planned`, `solid_reviewed`

| Requirement | Status | Triggers | Resolve |
|-------------|--------|----------|---------|
| commit_plan | ⬜ | Edit, Bash | `/arch-review` |
| adr_reviewed | ⬜ | Edit, Bash | `/arch-review` |
| tdd_planned | ⬜ | Edit, Bash | `/arch-review` |
| solid_reviewed | ⬜ | Edit, Bash | `/arch-review` |
```

### State File After Phase 2

```json
{
  "version": "1.0",
  "branch": "feature/auth",
  "requirements": {
    "commit_plan": {
      "scope": "session",
      "sessions": {}  // Still empty!
    },
    "adr_reviewed": {
      "scope": "session",
      "sessions": {}
    },
    "tdd_planned": {
      "scope": "session",
      "sessions": {}
    },
    "solid_reviewed": {
      "scope": "session",
      "sessions": {}
    }
  }
}
```

---

## Phase 3: User Runs `/arch-review` Skill

### Event: User Invokes Skill

**User Action**:
```
Claude: "I'll run /arch-review to plan the implementation"
→ Runs /arch-review skill
```

### Step 1: Skill Execution

The `/arch-review` skill (external to framework) executes in Claude Code.

### Step 2: Skill Completion

When skill completes, **PostToolUse hook** triggers with:

```json
{
  "tool_name": "Skill",
  "tool_input": {
    "skill": "requirements-framework:arch-review"
  },
  "session_id": "cad0ac4d",
  "cwd": "/path/to/repo"
}
```

### Step 3: Auto-Satisfy Hook Execution (auto-satisfy-skills.py)

```python
# Extract skill name
skill_name = "requirements-framework:arch-review"

# Look up mapping
DEFAULT_SKILL_MAPPINGS = {
  'requirements-framework:arch-review': 
    ['commit_plan', 'adr_reviewed', 'tdd_planned', 'solid_reviewed']
}

req_names = ['commit_plan', 'adr_reviewed', 'tdd_planned', 'solid_reviewed']

# For each requirement:
for req_name in req_names:
  scope = 'session'  # From config
  reqs.satisfy(req_name, scope='session', 
               method='skill', 
               metadata={'skill': 'arch-review'})
```

### Step 4: Satisfy Logic for Session-Scoped Requirement

For each requirement, `satisfy(req_name, scope='session', ...)`:

```python
def satisfy(self, req_name, scope='session', method='skill', metadata=None, ttl=None):
  req_state = self._get_req_state(req_name)
  req_state['scope'] = scope
  now = int(time.time())
  
  if scope == 'session':
    # Create nested session dict if needed
    if 'sessions' not in req_state:
      req_state['sessions'] = {}
    
    # Create entry for current session
    if self.session_id not in req_state['sessions']:
      req_state['sessions'][self.session_id] = {}
    
    # Satisfy for THIS session
    session_state = req_state['sessions'][self.session_id]
    session_state['satisfied'] = True
    session_state['satisfied_at'] = now
    session_state['satisfied_by'] = method
    session_state['metadata'] = metadata
    session_state['expires_at'] = None
  
  self._save()  # Write to .git/requirements/feature-auth.json
```

### Step 5: State File After Auto-Satisfy

```json
{
  "version": "1.0",
  "branch": "feature/auth",
  "updated_at": 1700000005,
  "requirements": {
    "commit_plan": {
      "scope": "session",
      "sessions": {
        "cad0ac4d": {
          "satisfied": true,
          "satisfied_at": 1700000005,
          "satisfied_by": "skill",
          "metadata": {"skill": "requirements-framework:arch-review"},
          "expires_at": null
        }
      }
    },
    "adr_reviewed": {
      "scope": "session",
      "sessions": {
        "cad0ac4d": {
          "satisfied": true,
          "satisfied_at": 1700000005,
          "satisfied_by": "skill",
          "metadata": {"skill": "requirements-framework:arch-review"},
          "expires_at": null
        }
      }
    },
    "tdd_planned": {
      "scope": "session",
      "sessions": {
        "cad0ac4d": {
          "satisfied": true,
          "satisfied_at": 1700000005,
          "satisfied_by": "skill",
          "metadata": {"skill": "requirements-framework:arch-review"},
          "expires_at": null
        }
      }
    },
    "solid_reviewed": {
      "scope": "session",
      "sessions": {
        "cad0ac4d": {
          "satisfied": true,
          "satisfied_at": 1700000005,
          "satisfied_by": "skill",
          "metadata": {"skill": "requirements-framework:arch-review"},
          "expires_at": null
        }
      }
    }
  }
}
```

### Step 6: Session Metrics Updated

File: `.git/requirements/sessions/cad0ac4d.json`
```json
{
  "session_id": "cad0ac4d",
  "project_dir": "/path/to/repo",
  "branch": "feature/auth",
  "created_at": 1700000000,
  "last_updated": 1700000005,
  "tool_uses": 1,
  "skills_used": 1,
  "requirements_satisfied": {
    "commit_plan": {
      "satisfied_at": 1700000005,
      "satisfied_by": "skill:requirements-framework:arch-review"
    },
    "adr_reviewed": { ... },
    "tdd_planned": { ... },
    "solid_reviewed": { ... }
  }
}
```

---

## Phase 4: Planning Session Ends

### Event: SessionEnd Hook Triggered

**Input**:
```json
{
  "session_id": "cad0ac4d",
  "hook_event_name": "SessionEnd",
  "reason": "user_finished",
  "cwd": "/path/to/repo"
}
```

### Step 1: Remove from Registry

```python
remove_session_from_registry("cad0ac4d")
```

**Registry Before**:
```json
{
  "sessions": {
    "cad0ac4d": { ... }
  }
}
```

**Registry After**:
```json
{
  "sessions": {}  // cad0ac4d REMOVED
}
```

### Step 2: Check clear_session_state Config

```yaml
# Default config
hooks:
  session_end:
    clear_session_state: false  # Don't clear
```

Since `false`, session data is **NOT cleared** from state file.

### State Files After Phase 4

**Registry** (`~/.claude/sessions.json`):
```json
{ "sessions": {} }  // Empty
```

**State** (`.git/requirements/feature-auth.json`):
```json
{
  "requirements": {
    "commit_plan": {
      "scope": "session",
      "sessions": {
        "cad0ac4d": {
          "satisfied": true,  // ← STILL HERE!
          ...
        }
      }
    },
    ...
  }
}
```

**Session Metrics** (`.git/requirements/sessions/cad0ac4d.json`):
```json
{
  "session_id": "cad0ac4d",
  ...
  "requirements_satisfied": { ... }  // ← STILL HERE!
}
```

---

## Phase 5: Implementation Session Starts (SAME BRANCH)

### Event: SessionStart Hook Triggered

**Input**:
```json
{
  "session_id": "8f9a1b2c-3d4e-5f6a-7b8c-9d0e1f2a3b4c",
  "hook_event_name": "SessionStart",
  "source": "startup",
  "cwd": "/path/to/repo"
}
```

### Step 1: Normalize NEW Session ID

```python
raw_session = "8f9a1b2c-3d4e-5f6a-7b8c-9d0e1f2a3b4c"
session_id = normalize_session_id(raw_session)
# Result: session_id = "8f9a1b2c"
# This is DIFFERENT from planning session "cad0ac4d"
```

### Step 2: Update Registry with NEW Session

```python
update_registry("8f9a1b2c", "/path/to/repo", "feature/auth")
```

**Registry After**:
```json
{
  "sessions": {
    "8f9a1b2c": {  // ← NEW session
      "pid": 48765,
      "ppid": 48760,
      "project_dir": "/path/to/repo",
      "branch": "feature/auth",
      "started_at": 1700001000,
      "last_active": 1700001000
    }
  }
}
```

### Step 3: Load Requirement State (with OLD session data)

```python
reqs = BranchRequirements("feature/auth", "8f9a1b2c", "/path/to/repo")
# Loads: .git/requirements/feature-auth.json
# Session ID stored: self.session_id = "8f9a1b2c"
```

**State loaded contains**:
```json
{
  "requirements": {
    "commit_plan": {
      "scope": "session",
      "sessions": {
        "cad0ac4d": {  // ← OLD planning session's data
          "satisfied": true,
          ...
        }
        // "8f9a1b2c" DOESN'T EXIST YET!
      }
    },
    ...
  }
}
```

### Step 4: Run Session Key Migration

```python
def _migrate_session_keys(self):
  # Checks if old UUID format keys exist
  # Converts to 8-char normalized format
  # In this case: no old format keys to migrate
  # (planning session already used 8-char format)
  pass
```

### Step 5: Check Requirements for NEW Session

**For each requirement**, `is_satisfied(req_name, scope='session')`:

```python
def is_satisfied(self, req_name, scope='session'):
  req_state = self._get_req_state(req_name)
  
  if scope == 'session':
    sessions = req_state.get('sessions', {})
    
    # Does current session have an entry?
    if self.session_id not in sessions:  # "8f9a1b2c" not in dict!
      return False
    
    # This line never executes because session doesn't exist
    return sessions[self.session_id].get('satisfied', False)
```

**Result for all four requirements**:
```
commit_plan: NOT satisfied (sessions["8f9a1b2c"] doesn't exist)
adr_reviewed: NOT satisfied
tdd_planned: NOT satisfied
solid_reviewed: NOT satisfied
```

### Step 6: Display Status

**Context Injection**:
```markdown
## Requirements Framework: Session Briefing

Branch: `feature/auth` | Session: `8f9a1b2c`

### Quick Start
🚀 **Run `/arch-review`** → satisfies `commit_plan`, `adr_reviewed`, `tdd_planned`, `solid_reviewed`

| Requirement | Status | Triggers | Resolve |
|-------------|--------|----------|---------|
| commit_plan | ⬜ | Edit, Bash | `/arch-review` |
| adr_reviewed | ⬜ | Edit, Bash | `/arch-review` |
| tdd_planned | ⬜ | Edit, Bash | `/arch-review` |
| solid_reviewed | ⬜ | Edit, Bash | `/arch-review` |
```

---

## Key Insights

### 1. State File Has BOTH Sessions' Data

After Phase 5 starts, state file contains:
```json
{
  "commit_plan": {
    "sessions": {
      "cad0ac4d": { "satisfied": true, ... },  // OLD session data
      // "8f9a1b2c" doesn't exist yet
    }
  }
}
```

### 2. But NEW Session Can Only See Its Own Entry

When checking satisfaction for `"8f9a1b2c"`:
```python
sessions["8f9a1b2c"]  # KeyError! Not in dict
# → is_satisfied() returns False
```

### 3. WHY This Design?

**Problem it solves**:
- If new session could see old session's satisfied state
- Would never need to re-satisfy (copy data from old session)
- Would break "once per session" requirement pattern

**By making new sessions NOT see old data**:
- Forces re-evaluation each session
- Ensures planning fresh for each session
- Maintains isolation between sessions

### 4. Historical Data Persists

The old session data (`"cad0ac4d"`) stays in the file forever until:
- Manually cleared via `req clear commit_plan`
- Branch is deleted and state cleanup runs
- User manually edits the file

### 5. Registry vs State Trade-Off

| Data | File | Lifecycle |
|------|------|-----------|
| Session registry | `~/.claude/sessions.json` | Ephemeral (cleaned up) |
| Requirement state | `.git/requirements/[branch].json` | Persistent (keeps history) |

Registry is **lean** (only current sessions).  
State is **fat** (keeps all history).

This separation allows:
- Fast session cleanup (registry)
- Long-term requirement history (state)

---

## Data Flow Summary Diagram

```
Plan Session (cad0ac4d)
├─ Starts
│  └─ Registry: add cad0ac4d
│  └─ State: {commit_plan: {sessions: {}}}
│
├─ User runs /arch-review
│  └─ Auto-satisfy hook
│     └─ State: {commit_plan: {sessions: {cad0ac4d: {satisfied: true}}}}
│
└─ Ends
   └─ Registry: remove cad0ac4d
   └─ State: UNCHANGED (still has cad0ac4d's data)

Implementation Session (8f9a1b2c) - SAME BRANCH
├─ Starts
│  └─ Registry: add 8f9a1b2c
│  └─ State loaded: sees cad0ac4d's satisfied data
│  └─ Check for 8f9a1b2c: NOT FOUND
│  └─ Result: NOT satisfied (fresh start)
│
├─ User runs /arch-review again
│  └─ Auto-satisfy hook creates NEW entry
│     └─ State: {commit_plan: {sessions: {
│             cad0ac4d: {satisfied: true},
│             8f9a1b2c: {satisfied: true}
│          }}}
│
└─ Ends
   └─ Registry: remove 8f9a1b2c
   └─ State: UNCHANGED (has both cad0ac4d and 8f9a1b2c)
```

---

## Why This Matters

This design enables the **planning → implementation pattern**:

1. **Planning session**: Run `/arch-review`, create comprehensive plan
2. **Session ends**: Plan is saved (visible in context review/history)
3. **Implementation session**: Fresh start (must validate plan still relevant)
4. **User choice**: Can re-run `/arch-review` to update plan, or accept cached plan

The re-triggering of planning requirements in new sessions ensures:
- ✅ Plan freshness (re-evaluate each session)
- ✅ Context continuity (plan visible in session review)
- ✅ Flexibility (user can satisfy once, or recheck, or update)
- ✅ Isolation (sessions don't interfere with each other)

---

## Alternative: Branch-Scoped Requirements

If requirements were `scope: branch` instead of `scope: session`:

```python
# is_satisfied(req_name, scope='branch')
return req_state.get('satisfied', False)  # Only root level!
```

Would work differently:
- Plan session satisfies: `satisfied = true` at root level
- Implementation session: sees same `satisfied = true`
- Result: Re-run `/arch-review` NOT needed (plan applies to whole branch)

**Use case**: Requirements that apply to entire feature branch lifecycle  
**Example**: `architecture_reviewed` (one architecture review for whole branch)

**Contrast with session**: Requirements that need per-session validation  
**Example**: `commit_plan` (plan gets stale, needs re-validation)
