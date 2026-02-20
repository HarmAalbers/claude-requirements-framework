# Deep Exploration Summary: Session & State Persistence

## Mission Completed

This exploration deeply investigated how the requirements framework handles sessions and state persistence, with focus on understanding the cycle where `/arch-review` satisfies requirements and then a new session begins on the same branch.

## Documents Created

1. **session_state_persistence_analysis.md** (12 sections, 400+ lines)
   - Complete architecture overview
   - Detailed data structures and lifecycle
   - All scope types explained
   - Skill-to-requirement mapping
   - Fail-open design principles
   - Session ID normalization

2. **session_state_flow_diagrams.md** (10 sections with ASCII diagrams)
   - Complete session lifecycle diagram
   - State file persistence across sessions
   - Scope comparison matrix
   - Registry management flow
   - Session ID normalization process
   - File locking & atomic writes
   - Config cascade & scope control
   - Re-triggering explanation
   - Single-use clearing behavior
   - Stop hook verification logic

3. **session_state_quick_reference.md** (Concise reference)
   - Core data structures
   - Key files & roles
   - Scope cheat sheet
   - Core classes & methods
   - Hook responsibilities
   - Data flow summary
   - Critical design decisions
   - Common workflows
   - Debugging tips
   - Code location reference

4. **plan_approval_session_cycle.md** (Complete traced workflow)
   - Phase-by-phase walkthrough of complete cycle
   - Planning session start → end
   - Plan approval via `/arch-review`
   - Implementation session start → end
   - Exact JSON state at each phase
   - Why new sessions see unsatisfied state
   - Design rationale for re-triggering

## Key Findings

### 1. Two-Location Architecture

**Session Registry** (`~/.claude/sessions.json`):
- Global, tracks CURRENT sessions only
- Ephemeral (cleaned up when sessions end)
- Used for: CLI auto-detection, session warnings, multi-session detection
- Thread-safe with atomic read-modify-write operations

**Requirement State** (`.git/requirements/[branch].json`):
- Per-branch, persistent across sessions
- Contains nested session dictionaries within requirements
- Survives session end by design (NOT cleared by default)
- Allows multi-session tracking on same branch

### 2. The Critical Design: Session-Scoped Requirements Survive

**What happens**:
1. Planning session `abc123` satisfies `commit_plan`
   → Stored as: `sessions["abc123"].satisfied = true`

2. Session ends
   → Registry entry removed
   → **State file entry PERSISTS** (intentional)

3. New session `def456` starts on same branch
   → Loads state file (sees `sessions["abc123"].satisfied = true`)
   → Checks `sessions["def456"]` → DOESN'T EXIST
   → Result: NOT satisfied (for new session)

4. User sees: "commit_plan NOT satisfied - Run `/arch-review`"

**Why**: Forces re-evaluation each session (prevents stale plans)

### 3. Session-Scoped Requirements: The Four Key Requirements

These re-trigger after `/arch-review` creates a new session:

- `commit_plan` (session) - Plan created and approved
- `adr_reviewed` (session) - ADRs reviewed against plan
- `tdd_planned` (session) - TDD approach documented
- `solid_reviewed` (session) - SOLID principles reviewed

All satisfied by: `/arch-review` or `/plan-review` skill

### 4. The Complete Data Flow

```
State File Contains:
{
  "commit_plan": {
    "scope": "session",
    "sessions": {
      "abc123": { satisfied: true },  // Old session data
      "def456": { satisfied: true }   // New session data
    }
  }
}

Checking:
- Session abc123: sees sessions["abc123"] → satisfied ✓
- Session def456: sees sessions["def456"] → satisfied ✓
- Session ghi789: sessions["ghi789"] doesn't exist → NOT satisfied ✗
```

Each session gets its own entry. New sessions don't inherit old sessions' state.

### 5. Session ID Normalization

**Fixed Bug**: UUIDs vs 8-char IDs causing state mismatch

- Full UUIDs like `cad0ac4d-3933-45ad-9a1c-14aec05bb940` normalized to `cad0ac4d`
- Ensures consistent keys across all code paths
- Automatic migration when loading old state with UUID keys

### 6. File Operations Are Fail-Open

- Registry read error? → Return empty registry (don't raise)
- State write error? → Log warning (don't raise)
- Config load error? → Skip framework (don't raise)
- Locks fail? → Continue anyway (don't raise)

**Philosophy**: Framework should never block user work

### 7. Stop Hook Prevents Incomplete Sessions

When Claude tries to stop:
1. Check if requirements were triggered (used) this session
2. For triggered requirements, check if satisfied
3. If any triggered requirement unsatisfied → BLOCK STOP
4. Special flag (`stop_hook_active`) prevents infinite loops

### 8. Scopes Determine Clearing Behavior

| Scope | Clearing | Storage | Re-triggers |
|-------|----------|---------|-------------|
| session | NEW session | `sessions[sid]` | Yes, each session |
| branch | Manual only | Root level | No, persists |
| single_use | After action | `sessions[sid]` | Yes, after each action |
| permanent | Never | Root level | No, permanent |

### 9. Skill-to-Requirement Mapping

`/arch-review` maps to: `['commit_plan', 'adr_reviewed', 'tdd_planned', 'solid_reviewed']`

When skill completes:
1. PostToolUse hook extracts skill name
2. Looks up mapped requirements from config + defaults
3. Satisfies ALL mapped requirements for CURRENT session
4. Records in session metrics

### 10. Registry vs State Trade-Off

**Registry** (ephemeral):
- Only tracks current sessions
- Cleaned automatically
- Small, lean, fast lookup
- Used for: CLI discovery, session warnings

**State** (persistent):
- Keeps full history
- Never auto-cleaned
- Can grow over time
- Used for: requirement tracking, audit trail

This separation allows lean current session management while maintaining historical data.

---

## Critical Code Paths

### Session Start
1. Normalize session ID
2. Update registry (add new session)
3. Load state file
4. Migrate old session keys if present
5. Check satisfaction for NEW session (sees old data but not new entry)
6. Display status showing what's unsatisfied

### Auto-Satisfy (Skill Completion)
1. Extract skill name from tool_input
2. Load config
3. Look up skill → requirements mapping
4. For each requirement:
   - Get scope from config
   - Call `reqs.satisfy(req_name, scope, method='skill', ...)`
   - This creates/updates `sessions[current_sid]` entry
5. Save state file
6. Record in session metrics

### Stop Hook
1. Check `stop_hook_active` flag (prevent loops)
2. For each requirement:
   - Was it triggered this session?
   - Is it satisfied?
3. If any triggered requirement unsatisfied → BLOCK with resolution guide
4. If all satisfied → ALLOW STOP

### Session End
1. Remove from registry (always)
2. Check config: `clear_session_state`?
3. If true: clear all session-scoped requirements
4. If false (default): leave state file untouched

---

## Common Workflows Explained

### Workflow 1: Single Planning Session
```
SessionStart (abc123)
  → commit_plan NOT satisfied

User runs /arch-review
  → Auto-satisfy creates sessions["abc123"].satisfied = true

User works
  → Edit, commit, etc.

Stop hook
  → commit_plan satisfied? YES → Allow stop

SessionEnd
  → Registry: remove abc123
  → State: keep sessions["abc123"] data
```

### Workflow 2: Plan Then Implement (Two Sessions)
```
Session 1: Planning (abc123)
  → Run /arch-review
  → Satisfies: sessions["abc123"].satisfied = true
  → SessionEnd

Session 2: Implement (def456) on SAME branch
  → Load state (has abc123 data)
  → Check for def456 → NOT FOUND
  → Result: NOT satisfied (force re-plan or accept cached)
  → User can run /arch-review again
  → Or just continue (requirements might not block edits)
```

### Workflow 3: Single-Use Review Before Each Commit
```
Session A:
  1. Edit → pre_commit_review triggered
  2. Run /pre-commit → satisfy
  3. Git commit
     → clear-single-use hook deletes sessions["A"]
  4. Edit again
     → Must satisfy again before next commit
```

---

## Design Rationale

### Why Session State Persists

**Problem**: How do you track planning across sessions on same branch?

**Solution**: Keep state per-session within branch state file
- Old session's data stays in file
- New session creates its own entry
- Each session only "sees" its own entry (isolation)
- No cross-session interference

**Result**: Historical tracking + isolation + fresh starts

### Why Session IDs Need Normalization

**Problem**: Different parts of code generated IDs in different formats
- UUID from env var: `cad0ac4d-3933-...` (36 chars)
- Generated ID from PPID: `abc123ab` (8 chars)
- Same session, different keys → state mismatch

**Solution**: Normalize all to 8-char format
- Idempotent (`normalize_session_id()` safe to call anywhere)
- Automatic migration for old UUID keys
- Consistent across all code paths

### Why Stop Hook Checks Triggered + Satisfied

**Problem**: User might have session that never touched planning requirements

**Solution**: Only verify requirements that were actually used
```python
if not reqs.is_triggered(req_name):
  continue  # Skip (not used this session)
```

**Result**: Research-only sessions don't get blocked by unrelated requirements

### Why Registry Is Separate from State

**Problem**: State file grows unbounded (keeps all history)

**Solution**: Keep registry ephemeral
- Only tracks current sessions
- Cleaned automatically when sessions end
- Used for runtime detection and warnings
- State file used for historical tracking

**Result**: Fast registry lookups + complete history in state

---

## Testing This System

To verify the cycle works:

1. **Create a branch and plan**:
   ```bash
   git checkout -b feature/test
   # Session 1 starts
   # Run /arch-review
   # See: commit_plan ✓ satisfied
   # Exit Claude Code
   ```

2. **Inspect state after session 1**:
   ```bash
   cat .git/requirements/feature-test.json | jq '.requirements.commit_plan.sessions'
   # Should have one session ID with satisfied: true
   ```

3. **Resume same branch in new session**:
   ```bash
   # Session 2 starts
   # See: commit_plan ⬜ NOT satisfied (new session!)
   # Can run /arch-review again, or proceed
   ```

4. **Inspect state after session 2**:
   ```bash
   cat .git/requirements/feature-test.json | jq '.requirements.commit_plan.sessions'
   # Should have TWO sessions, both with satisfied: true
   ```

---

## Potential Extensions

### Branch-Scoped Planning
```yaml
requirements:
  architecture_reviewed:
    enabled: true
    scope: branch  # Not session!
    auto_resolve_skill: arch-review
```

This would satisfy once per branch (not per session).
Good for: architecture decisions, security reviews, compliance checks.

### Approval TTLs
```python
reqs.approve_for_session(req_name, ttl=3600, 
                         metadata={'approved_by': 'user'})
```

Approvals expire after TTL.
Good for: dynamic requirements with thresholds.

### Branch Size Monitoring
```python
branch_size = calculate_branch_size(branch)
if branch_size > config.get_threshold(req_name):
  block_edit(reason="Branch too large")
```

Dynamic requirements that change based on context.

---

## Conclusion

The requirements framework's session and state persistence system is elegant:

1. **Simple data model**: State files keyed by branch, with nested session dicts
2. **Fail-open throughout**: Errors never block work
3. **Thread-safe**: File locking ensures concurrent safety
4. **Atomic writes**: Temp file + fsync + rename prevents corruption
5. **Clear separation**: Registry (ephemeral) vs State (persistent)
6. **Flexible scopes**: session, branch, single_use, permanent
7. **Transparent to users**: Framework handles migration and normalization

The clever part: **New sessions don't see old sessions' data**, which forces re-evaluation each session while preserving historical tracking.

This enables the planning → implementation pattern where plans are fresh for each session but carry forward context and learning across sessions.
