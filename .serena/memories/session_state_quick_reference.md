# Quick Reference: Session & State Persistence

## Core Data Structures

### Session Registry
**File**: `~/.claude/sessions.json`  
**Lifecycle**: Ephemeral (current sessions only)  
**Updated by**: SessionStart (add/update), SessionEnd (remove)  
**Format**:
```json
{
  "version": "1.0",
  "sessions": {
    "abc12345": {
      "pid": 12345,
      "ppid": 12340,
      "project_dir": "/path",
      "branch": "feature/auth",
      "started_at": 1234567890,
      "last_active": 1234567895
    }
  }
}
```

### Requirement State File
**File**: `.git/requirements/[branch].json`  
**Lifecycle**: Persistent (survives session end)  
**Updated by**: Auto-satisfy hooks, CLI commands  
**Structure**:
```json
{
  "version": "1.0",
  "branch": "feature/auth",
  "requirements": {
    "requirement_name": {
      "scope": "session|branch|single_use|permanent",
      "sessions": {               // Only for session/single_use
        "abc123": {
          "satisfied": true,
          "triggered": true,
          "satisfied_at": 1234567890,
          "satisfied_by": "skill|cli|approval",
          "expires_at": null
        }
      },
      "satisfied": true,          // Only for branch/permanent
      "satisfied_at": 1234567890,
      "satisfied_by": "skill|cli"
    }
  }
}
```

## Key Files & Their Roles

| File | Purpose | Lifecycle |
|------|---------|-----------|
| `~/.claude/sessions.json` | Registry of active sessions | Ephemeral |
| `.git/requirements/[branch].json` | State for a branch | Persistent |
| `.git/requirements/sessions/[sid].json` | Session metrics/learning | Persistent |
| `~/.claude/requirements.yaml` | Global config (cascade source 1) | Persistent (user home) |
| `.claude/requirements.yaml` | Project config (cascade source 2) | Persistent (repo) |
| `.claude/requirements.local.yaml` | Local overrides (cascade source 3) | Gitignored |

## Scope Cheat Sheet

| Scope | Cleared When | Storage | Example |
|-------|--------------|---------|---------|
| **session** | NEW session on same branch | `sessions[sid]` dict | `commit_plan` |
| **branch** | Manual clear only | Root level | `architecture_reviewed` |
| **single_use** | Trigger action completes | `sessions[sid]` (then deleted) | `pre_commit_review` |
| **permanent** | Never auto-cleared | Root level | `security_audit_passed` |

## Core Classes & Methods

### BranchRequirements (hooks/lib/requirements.py)
```python
# Initialize
reqs = BranchRequirements(branch, session_id, project_dir)

# Check satisfaction
reqs.is_satisfied(req_name, scope='session')  # Bool

# Check if triggered this session
reqs.is_triggered(req_name, scope='session')  # Bool

# Mark triggered (when requirement's trigger fires)
reqs.mark_triggered(req_name, scope='session')

# Satisfy (record as satisfied)
reqs.satisfy(req_name, scope='session', method='skill', 
             metadata={'skill': 'arch-review'})

# Clear single-use for current session only
reqs.clear_single_use(req_name)  # Returns bool

# Clear completely
reqs.clear(req_name)
```

### Session (hooks/lib/session.py)
```python
# Get normalized session ID
session_id = normalize_session_id(raw_id)

# Update registry with current session
update_registry(session_id, project_dir, branch)

# Remove from registry
remove_session_from_registry(session_id)

# Get all active sessions
active = get_active_sessions(project_dir=None, branch=None)

# Clean stale sessions
count = cleanup_stale_sessions()
```

### RegistryClient (hooks/lib/registry_client.py)
```python
client = RegistryClient(Path.home() / '.claude' / 'sessions.json')

# Atomic read
registry = client.read()

# Atomic write
client.write(registry_dict)

# Atomic read-modify-write
client.update(lambda reg: modified_registry or None)
```

## Hook Responsibilities

### SessionStart
- Clean stale sessions from registry
- Update registry with current session
- Initialize session metrics
- Load state and check requirement satisfaction for NEW session
- Inject status into context

### SessionEnd
- Remove from registry
- Optionally clear session state (default: NO, keep it)

### PreToolUse (check-requirements.py)
- Load config
- Check if tool is blocked by unsatisfied requirements
- Mark requirements as triggered

### PostToolUse (auto-satisfy-skills.py)
- Detect skill completion
- Look up skill → requirements mapping
- Satisfy all mapped requirements for CURRENT session
- Record in session metrics

### PostToolUse (clear-single-use.py)
- Detect trigger commands (e.g., git commit)
- Clear single_use requirements for CURRENT session

### Stop (handle-stop.py)
- Check stop_hook_active flag (prevent loops)
- For each requirement:
  - Was it triggered this session?
  - Is it satisfied?
- BLOCK if any unsatisfied triggered requirements
- ALLOW if all satisfied

### SessionEnd (handle-session-end.py)
- Remove from registry (always)
- Optionally clear session state (controlled by config, default: false)

## Data Flow: Key Insight

```
Session registry (~/.claude/sessions.json)
    ↓
    Tracks CURRENT sessions
    ↓
    Cleaned up when sessions end

Requirement state (.git/requirements/[branch].json)
    ↓
    Persists across sessions
    ↓
    Each session has its own entry in sessions[sid] dict
    ↓
    New session sees: sessions[old_sid] data, but not sessions[new_sid]
    ↓
    Result: Requirements re-trigger for NEW session
```

## Critical Design Decisions

### 1. Session State Survives Session End
- **What**: `sessions[sid]` dict entries persist in state file
- **Why**: Allows multi-session tracking on same branch
- **Controlled by**: `hooks.session_end.clear_session_state` (default: false)

### 2. New Sessions Get Fresh State Entries
- **What**: New session_id doesn't have entry in `sessions` dict
- **Why**: Enforces "once per session" for session-scoped requirements
- **Result**: commit_plan, etc. must be re-satisfied each session

### 3. Session ID Normalization
- **What**: All session IDs converted to 8-character hex
- **Why**: Fixed bug where UUIDs and generated IDs caused state mismatch
- **Where**: `normalize_session_id()` called everywhere

### 4. Fail-Open Throughout
- **What**: Errors in registry/state never block work
- **Why**: Framework should never break user workflow
- **How**: Errors logged, safe defaults returned

### 5. File Locking for Thread Safety
- **What**: fcntl locks (shared for read, exclusive for write)
- **Why**: Safe concurrent access from multiple hooks
- **Implementation**: RegistryClient, state_storage

### 6. Atomic Writes with Rename
- **What**: Write to temp file, fsync, atomic rename
- **Why**: Guarantee registry/state never left in corrupted state
- **POSIX**: Atomic rename is guaranteed by OS

## Common Workflows

### Workflow 1: Single Session, Plan & Commit
```
1. SessionStart (abc123)
   - Load state, see commit_plan NOT satisfied
   
2. User runs /arch-review
   - Auto-satisfy: sessions["abc123"].satisfied = true
   
3. User edits and commits
   
4. Claude stops
   - Stop hook checks: is commit_plan satisfied? YES
   - Allow stop
   
5. SessionEnd (abc123)
   - Remove from registry
   - State file still has sessions["abc123"] = satisfied
```

### Workflow 2: Two Sessions on Same Branch (Plan + Implement)
```
1. SessionStart (abc123) - Planning session
   - commit_plan NOT satisfied
   - Run /arch-review
   - Auto-satisfy: sessions["abc123"].satisfied = true
   - SessionEnd
   
2. SessionStart (def456) - Implementation session
   - State has sessions["abc123"], but NOT sessions["def456"]
   - commit_plan NOT satisfied (for new session)
   - (Usually accepted to continue implementation)
   - Make changes, run tests, commit
   - SessionEnd
   
3. sessionStart (ghi789) - Another session
   - State has abc123 and def456, but NOT ghi789
   - commit_plan NOT satisfied again
   - (Fresh start for new session on same branch)
```

### Workflow 3: Single-Use Requirement (Pre-commit Review)
```
Session A:
1. Edit code → pre_commit_review triggered
   - sessions["abc123"].triggered = true
   
2. Run /pre-commit
   - Auto-satisfy: sessions["abc123"].satisfied = true
   
3. Git commit
   - clear-single-use hook fires
   - DELETE sessions["abc123"]
   
4. Edit code again
   - New trigger
   - sessions["abc123"] entry re-created (triggered again)
   - Must satisfy again before next commit
```

## Testing & Debugging

### Check Session Registry
```bash
cat ~/.claude/sessions.json | jq
```

### Check Requirement State
```bash
cat .git/requirements/feature-auth.json | jq '.requirements.commit_plan'
```

### Check Session Metrics
```bash
cat .git/requirements/sessions/abc123.json | jq
```

### Check Config Cascade
```bash
req logging --level debug  # Enable debug logging
tail -f ~/.claude/requirements.log
```

### Manually Satisfy
```bash
req satisfy commit_plan --session abc123
```

### Clear a Requirement
```bash
req clear commit_plan
```

## Common Issues & Solutions

### Issue: Requirement says "NOT satisfied" after satisfying
**Likely Cause**: Different session ID  
**Check**: `echo $CLAUDE_SESSION_ID`  
**Solution**: Session IDs differ between sessions. This is expected for session-scoped requirements.

### Issue: State file has multiple sessions but can't find my data
**Likely Cause**: Looking at wrong session ID  
**Check**: 
```bash
cat .git/requirements/feature-auth.json | jq '.requirements.commit_plan.sessions | keys'
```
**Solution**: Each session is a separate entry in the sessions dict.

### Issue: Registry file is empty or corrupted
**Likely Cause**: Registry write failed  
**Check**: Check permissions on `~/.claude/`  
**Solution**: 
```bash
rm ~/.claude/sessions.json  # Will be recreated
```

### Issue: Old session state still in file but can't access it
**Likely Cause**: New session can't see old session's data (by design)  
**Solution**: This is intentional. Session-scoped requirements re-evaluate per session.

## Key Code Locations

| Task | File | Function |
|------|------|----------|
| Normalize session ID | session.py | `normalize_session_id()` |
| Update registry | session.py | `update_registry()` |
| Check satisfaction | requirements.py | `is_satisfied()` |
| Mark triggered | requirements.py | `mark_triggered()` |
| Satisfy requirement | requirements.py | `satisfy()` |
| Clear single-use | requirements.py | `clear_single_use()` |
| Load state | state_storage.py | `load_state()` |
| Save state | state_storage.py | `save_state()` |
| Auto-satisfy on skill | auto-satisfy-skills.py | `main()` |
| Stop verification | handle-stop.py | `main()` |
| Session cleanup | session.py | `cleanup_stale_sessions()` |
