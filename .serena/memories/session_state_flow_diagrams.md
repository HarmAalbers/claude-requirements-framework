# Session & State Persistence: Flow Diagrams

## 1. COMPLETE SESSION LIFECYCLE

```
┌─────────────────────────────────────────────────────────────────────┐
│ SESSION STARTS (SessionStart Hook)                                  │
└─────────────────────────────────────────────────────────────────────┘
                                ↓
        ┌───────────────────────────────────────────┐
        │ 1. Parse session_id from stdin            │
        │ 2. Normalize to 8-char format             │
        │ 3. Load config (.claude/requirements.yaml)│
        └───────────────────────────────────────────┘
                                ↓
        ┌───────────────────────────────────────────┐
        │ 4. Clean stale sessions from registry      │
        │    (remove ppids that don't exist)        │
        └───────────────────────────────────────────┘
                                ↓
        ┌───────────────────────────────────────────┐
        │ 5. Update ~/.claude/sessions.json:        │
        │    {                                       │
        │      "abc123": {                           │
        │        "ppid": 12340,                      │
        │        "project_dir": "/path",            │
        │        "branch": "feature/auth",          │
        │        "started_at": 1234567890,          │
        │        "last_active": 1234567890          │
        │      }                                     │
        │    }                                       │
        └───────────────────────────────────────────┘
                                ↓
        ┌───────────────────────────────────────────┐
        │ 6. Initialize session metrics file        │
        │    (.git/requirements/sessions/abc123.json)│
        └───────────────────────────────────────────┘
                                ↓
        ┌───────────────────────────────────────────┐
        │ 7. Load state: .git/requirements/         │
        │              feature-auth.json            │
        └───────────────────────────────────────────┘
                                ↓
        ┌───────────────────────────────────────────┐
        │ 8. Migrate session keys                    │
        │    (UUID → 8-char normalization)          │
        └───────────────────────────────────────────┘
                                ↓
        ┌───────────────────────────────────────────┐
        │ 9. Check requirement satisfaction for     │
        │    CURRENT session (abc123)               │
        │                                            │
        │ for commit_plan:                          │
        │   sessions["abc123"] exists?              │
        │   sessions["abc123"].satisfied = true?    │
        │                                            │
        │ Result: NOT SATISFIED (first time)        │
        └───────────────────────────────────────────┘
                                ↓
        ┌───────────────────────────────────────────┐
        │ 10. Inject status into context            │
        │     Shows: commit_plan ⬜ NOT satisfied   │
        │     Action: Run `/arch-review`            │
        └───────────────────────────────────────────┘
                                ↓
┌─────────────────────────────────────────────────────────────────────┐
│ USER WORKS IN SESSION (can edit, run tools, etc.)                   │
└─────────────────────────────────────────────────────────────────────┘
                                ↓
        ┌───────────────────────────────────────────┐
        │ User runs: /arch-review                   │
        │            (PostToolUse hook triggers)    │
        └───────────────────────────────────────────┘
                                ↓
        ┌───────────────────────────────────────────┐
        │ PostToolUse Hook (auto-satisfy-skills):   │
        │ 1. Extract skill: 'arch-review'           │
        │ 2. Load config                            │
        │ 3. Look up mapping:                       │
        │    arch-review → [commit_plan, ...]      │
        │ 4. For each requirement:                  │
        │    reqs.satisfy(req_name,                 │
        │                 scope='session',          │
        │                 method='skill')           │
        │ 5. Save state:                            │
        │    sessions["abc123"].satisfied = true    │
        └───────────────────────────────────────────┘
                                ↓
        ┌──────────────────────────────────────────────────────┐
        │ State file now contains:                             │
        │ {                                                    │
        │   "requirements": {                                  │
        │     "commit_plan": {                                 │
        │       "scope": "session",                            │
        │       "sessions": {                                  │
        │         "abc123": {  // ← Current session            │
        │           "satisfied": true,                         │
        │           "satisfied_at": 1234567895,               │
        │           "satisfied_by": "skill",                   │
        │           "metadata": {"skill": "arch-review"}       │
        │         }                                            │
        │       }                                              │
        │     }                                                │
        │   }                                                  │
        │ }                                                    │
        └──────────────────────────────────────────────────────┘
                                ↓
        ┌───────────────────────────────────────────┐
        │ User continues work, makes changes        │
        └───────────────────────────────────────────┘
                                ↓
        ┌───────────────────────────────────────────┐
        │ Claude finishes → Stop Hook triggered     │
        └───────────────────────────────────────────┘
                                ↓
        ┌───────────────────────────────────────────┐
        │ Stop Hook (handle-stop.py):               │
        │ 1. Check stop_hook_active flag            │
        │    (is this a second attempt?)            │
        │ 2. Load config and state                  │
        │ 3. For each requirement:                  │
        │    - Was it triggered this session?       │
        │    - Is it satisfied?                     │
        │ 4. If unsatisfied, BLOCK and show guide   │
        │    If all satisfied, ALLOW STOP           │
        │ 5. Optionally emit session review prompt  │
        └───────────────────────────────────────────┘
                                ↓
        ┌───────────────────────────────────────────┐
        │ All satisfied → Allow Claude to stop      │
        └───────────────────────────────────────────┘
                                ↓
┌─────────────────────────────────────────────────────────────────────┐
│ SESSION ENDS (SessionEnd Hook)                                      │
└─────────────────────────────────────────────────────────────────────┘
                                ↓
        ┌───────────────────────────────────────────┐
        │ 1. Remove from registry:                  │
        │    Delete sessions["abc123"] from         │
        │    ~/.claude/sessions.json                │
        │                                            │
        │ 2. Session data PERSISTS in:              │
        │    .git/requirements/feature-auth.json    │
        │                                            │
        │ 3. Config check (clear_session_state?):   │
        │    Default: false → KEEP session data     │
        └───────────────────────────────────────────┘
                                ↓
        ┌──────────────────────────────────────────────────────┐
        │ State file still has:                                │
        │ {                                                    │
        │   "requirements": {                                  │
        │     "commit_plan": {                                 │
        │       "scope": "session",                            │
        │       "sessions": {                                  │
        │         "abc123": {  // ← STILL HERE!               │
        │           "satisfied": true,                         │
        │           ...                                        │
        │         }                                            │
        │       }                                              │
        │     }                                                │
        │   }                                                  │
        │ }                                                    │
        └──────────────────────────────────────────────────────┘
                                ↓
┌─────────────────────────────────────────────────────────────────────┐
│ NEW SESSION STARTS on SAME BRANCH (SessionStart Hook)              │
└─────────────────────────────────────────────────────────────────────┘
                                ↓
        ┌───────────────────────────────────────────┐
        │ 1. New session_id generated: "def456"     │
        │ 2. Update registry with new session       │
        │ 3. Load state:                            │
        │    .git/requirements/feature-auth.json    │
        │    ↓                                       │
        │    Sees requirement commit_plan with:     │
        │    sessions: {                            │
        │      "abc123": { satisfied: true, ...},   │
        │      // "def456" DOESN'T EXIST YET        │
        │    }                                       │
        └───────────────────────────────────────────┘
                                ↓
        ┌───────────────────────────────────────────┐
        │ 4. Check satisfaction for NEW session:    │
        │    sessions["def456"] exists?             │
        │    → NO → NOT SATISFIED!                  │
        │                                            │
        │ Note: Old session abc123 data unaffected  │
        └───────────────────────────────────────────┘
                                ↓
        ┌───────────────────────────────────────────┐
        │ 5. Display status:                        │
        │    commit_plan ⬜ NOT satisfied           │
        │    adr_reviewed ⬜ NOT satisfied          │
        │    Action: Run `/arch-review` again       │
        └───────────────────────────────────────────┘
                                ↓
        ┌───────────────────────────────────────────┐
        │ 6. User runs /arch-review again           │
        │    Auto-satisfy writes to NEW session:    │
        │    sessions["def456"].satisfied = true    │
        └───────────────────────────────────────────┘
                                ↓
        ┌──────────────────────────────────────────────────────┐
        │ Final state file has BOTH sessions satisfied:        │
        │ {                                                    │
        │   "requirements": {                                  │
        │     "commit_plan": {                                 │
        │       "scope": "session",                            │
        │       "sessions": {                                  │
        │         "abc123": { "satisfied": true, ... },        │
        │         "def456": { "satisfied": true, ... }         │
        │       }                                              │
        │     }                                                │
        │   }                                                  │
        │ }                                                    │
        └──────────────────────────────────────────────────────┘
```

---

## 2. STATE FILE PERSISTENCE ACROSS SESSIONS

```
Timeline: Session A → End → Session B (same branch)

BEFORE SESSION A STARTS
───────────────────────
.git/requirements/feature-auth.json:
{
  "requirements": {}  // empty
}

~/.claude/sessions.json:
{
  "sessions": {}  // empty
}

┌─────────────────────────────────────────┐
│ SESSION A STARTS (abc123)                │
└─────────────────────────────────────────┘
      ↓
Registry updated:
~/.claude/sessions.json:
{
  "sessions": {
    "abc123": {
      "ppid": 12340,
      "project_dir": "/path",
      "branch": "feature/auth",
      "started_at": T0
    }
  }
}

State loaded (empty):
.git/requirements/feature-auth.json:
{
  "requirements": {}
}

Display: All reqs NOT satisfied
      ↓
User runs /arch-review
      ↓
State updated:
.git/requirements/feature-auth.json:
{
  "requirements": {
    "commit_plan": {
      "scope": "session",
      "sessions": {
        "abc123": {
          "satisfied": true,
          "satisfied_at": T1,
          "satisfied_by": "skill",
          "metadata": {"skill": "arch-review"}
        }
      }
    },
    // ... more requirements
  }
}

┌─────────────────────────────────────────┐
│ SESSION A ENDS                           │
└─────────────────────────────────────────┘
      ↓
Registry updated:
~/.claude/sessions.json:
{
  "sessions": {}  // abc123 REMOVED
}

State file UNCHANGED:
.git/requirements/feature-auth.json:
{
  "requirements": {
    "commit_plan": {
      "scope": "session",
      "sessions": {
        "abc123": {
          "satisfied": true,
          // ↑ STILL HERE!
          ...
        }
      }
    }
  }
}

┌──────────────────────────────────────────────┐
│ SESSION B STARTS on SAME BRANCH (def456)    │
└──────────────────────────────────────────────┘
      ↓
Registry updated:
~/.claude/sessions.json:
{
  "sessions": {
    "def456": {
      "ppid": 12360,
      "project_dir": "/path",
      "branch": "feature/auth",
      "started_at": T2
    }
  }
}

State loaded (with A's data):
.git/requirements/feature-auth.json:
{
  "requirements": {
    "commit_plan": {
      "scope": "session",
      "sessions": {
        "abc123": { "satisfied": true, ... },  // Still here but irrelevant
        // "def456" DOESN'T EXIST YET!
      }
    }
  }
}

Query: is_satisfied('commit_plan', scope='session')
  → Check sessions["def456"]
  → Doesn't exist!
  → Return False

Display: commit_plan ⬜ NOT satisfied
      ↓
User runs /arch-review again
      ↓
State updated:
.git/requirements/feature-auth.json:
{
  "requirements": {
    "commit_plan": {
      "scope": "session",
      "sessions": {
        "abc123": { "satisfied": true, ... },  // Historical
        "def456": {                             // New entry
          "satisfied": true,
          "satisfied_at": T3,
          "satisfied_by": "skill"
        }
      }
    }
  }
}

KEY INSIGHT: Both sessions' data persists in the state file,
             but each session only "sees" its own entry when checking satisfaction.
```

---

## 3. SESSION-SCOPED vs SINGLE-USE vs BRANCH-SCOPED

```
REQUIREMENT LIFECYCLE COMPARISON

Session-Scoped (e.g., commit_plan)
───────────────────────────────────
Session A:
  trigger() → triggered = true
  satisfy() → satisfied = true
    ↓ [SESSION A ENDS]
  Data persists in state file
    ↓ [SESSION B STARTS]
  NEW check: sessions["B"] doesn't exist
  Result: NOT satisfied (re-triggered automatically)
  
Behavior: "Once per session" - must satisfy in EVERY new session


Single-Use (e.g., pre_commit_review)
────────────────────────────────────
Session A:
  trigger() → sessions["A"].triggered = true
  satisfy() → sessions["A"].satisfied = true
  [After git commit completes]
  clear_single_use() → DELETE sessions["A"]
    ↓ [Still same session A]
  Next trigger: sessions["A"] doesn't exist
  Result: Must satisfy again (before NEXT commit)
  
Behavior: "Once per action" - must satisfy before each trigger action


Branch-Scoped (e.g., architecture_reviewed)
──────────────────────────────────────────
Session A:
  trigger() → triggered = true (at requirement root level)
  satisfy() → satisfied = true (at requirement root level)
    ↓ [SESSION A ENDS]
  Data persists in state file at root level
    ↓ [SESSION B STARTS]
  Check: req_state.get('satisfied') = true
  Result: SATISFIED (no per-session checking)
  
Behavior: "Once per branch" - satisfied for all sessions on branch


Permanent (e.g., security_reviewed)
──────────────────────────────────
Session A:
  satisfy() → satisfied = true (at requirement root level)
    ↓ [SESSION A ENDS]
  Data persists
    ↓ [SESSION B STARTS]
  Check: req_state.get('satisfied') = true
  Result: SATISFIED indefinitely
  
Behavior: "One-time" - never resets (unless manually cleared)
```

---

## 4. REGISTRY MANAGEMENT

```
Session Registry Lifecycle
──────────────────────────

~/.claude/sessions.json structure:
{
  "version": "1.0",
  "sessions": {
    // Key = session_id (8-char normalized)
    "abc12345": {
      "pid": 12345,           // Hook subprocess PID
      "ppid": 12340,          // Claude Code session PID ← used for alive check
      "project_dir": "/path/to/project",
      "branch": "feature/auth",
      "started_at": 1234567890,
      "last_active": 1234567895
    }
  }
}

Key Design Decisions:
1. ppid used for alive check (not pid)
   - pid is the short-lived hook subprocess
   - ppid is the actual Claude Code session (persists)

2. Registry is EPHEMERAL
   - Only tracks CURRENT sessions
   - Old sessions removed when they end
   - Clean up happens on next session start

3. Registration is fail-open
   - Registry errors never block work
   - Missing registry returns empty
   - Write errors logged but don't fail hook

Stale Session Cleanup Flow:
──────────────────────────
SessionStart Hook:
  1. Read registry
  2. For each session:
       if not is_process_alive(session.ppid):
         mark as stale
  3. Delete stale entries
  4. Update with current session

Result: Dead sessions removed automatically,
        fresh sessions added.
```

---

## 5. SESSION ID NORMALIZATION

```
Session ID Format Evolution & Migration

PROBLEM (Before fix):
────────────────────
CLAUDE_SESSION_ID env var provides: "cad0ac4d-3933-45ad-9a1c-14aec05bb940"
PPID fallback generates: "abc123ab"

Same session, DIFFERENT keys in state!
  sessions["cad0ac4d-3933-..."] = satisfied
  sessions["abc123ab"] = not satisfied
  ↓
  State mismatch - same session has two entries

SOLUTION:
────────
normalize_session_id(raw_id) → always 8-char hex format

Examples:
  "cad0ac4d-3933-45ad-9a1c-14aec05bb940"  → "cad0ac4d"
  "cad0ac4d393345ad9a1c14aec05bb940"      → "cad0ac4d"
  "abc123ab"                               → "abc123ab"
  ""                                       → generates new ID

Applied at:
  1. SessionStart hook: normalize_session_id(input_data['session_id'])
  2. Registry operations: normalize_session_id() before storing
  3. BranchRequirements init: self.session_id = normalize_session_id(session_id)
  4. State loading: _migrate_session_keys() converts old keys

Migration Process:
──────────────────
Old state:
{
  "commit_plan": {
    "sessions": {
      "cad0ac4d-3933-45ad-9a1c-14aec05bb940": { "satisfied": true }
    }
  }
}
      ↓
_migrate_session_keys() runs on load
      ↓
New state:
{
  "commit_plan": {
    "sessions": {
      "cad0ac4d": { "satisfied": true }  // ← Migrated key
    }
  }
}

Conflict handling:
If BOTH old and new format exist:
  "cad0ac4d-3933-..." AND "cad0ac4d"
  → Keep the one with newer timestamp
  → Delete the old format key
  → Idempotent: safe to run on every load
```

---

## 6. FILE LOCKING & ATOMIC WRITES

```
Registry Client Thread Safety
────────────────────────────

Read Operation:
┌─────────────────────────────┐
│ 1. Open ~/.claude/sessions.json for reading
│ 2. Acquire shared lock (fcntl.LOCK_SH)
│ 3. Read and parse JSON
│ 4. Release lock (fcntl.LOCK_UN)
│ 5. Return data
│                              │
│ If error at any step:        │
│   Log warning               │
│   Return empty registry     │
│   (fail-open)               │
└─────────────────────────────┘

Write Operation (Atomic Pattern):
┌──────────────────────────────────────┐
│ 1. Create temp file: sessions.tmp    │
│ 2. Open temp for writing             │
│ 3. Acquire exclusive lock (LOCK_EX)  │
│ 4. Write JSON to temp file           │
│ 5. Call fsync() (flush to disk)      │
│ 6. Release lock (LOCK_UN)            │
│ 7. Atomic rename: temp → actual      │
│    (POSIX guarantees this is atomic)│
│                                      │
│ If error at any step:                │
│   Delete temp file                   │
│   Log warning                        │
│   Return False (but don't raise)     │
│   (fail-open)                        │
└──────────────────────────────────────┘

Read-Modify-Write Operation:
┌────────────────────────────────────────┐
│ 1. Read registry (shared lock)          │
│ 2. Apply update function to copy       │
│ 3. If update function returns None:    │
│      Skip write (no changes)           │
│    Else:                               │
│      Write updated registry (exclusive) │
│                                        │
│ Prevents race conditions from separate │
│ read/write calls                       │
└────────────────────────────────────────┘

Concurrency Example:
───────────────────
Two processes updating registry simultaneously:

Process A:                      Process B:
─────────────────              ─────────────────
1. Read (shared lock)
2. Modify data                 1. Read (shared lock)
3. Write (exclusive lock)
   ... writing ...
4. Rename complete       →     2. Modify data
                               3. Write (exclusive lock)
                                  [blocked until A's exclusive lock released]
                               4. Rename complete

Result: Both writes succeed without corruption,
        because exclusive locks serialize the writes.
```

---

## 7. CONFIG CASCADE & SCOPE CONTROL

```
Configuration Flow
──────────────────

Config Cascade (priority: highest to lowest):
1. ~/.claude/requirements.yaml (global)
2. <project>/.claude/requirements.yaml (project, version controlled)
3. <project>/.claude/requirements.local.yaml (local, gitignored)

Example: commit_plan scope setting

Global (~/.claude/requirements.yaml):
────────────────────────────────────
requirements:
  commit_plan:
    enabled: true
    scope: session        # ← Default

Project (.claude/requirements.yaml):
──────────────────────────────────
requirements:
  commit_plan:
    scope: branch        # ← Override to branch-scoped

Local (.claude/requirements.local.yaml):
──────────────────────────────
requirements:
  commit_plan:
    scope: session      # ← Override back to session-scoped

Result: Local wins, so scope = 'session'

Session-Scoped Requirement Check:
─────────────────────────────────
is_satisfied('commit_plan', scope='session'):
  if self.session_id not in req_state.get('sessions', {}):
    return False
  return sessions[self.session_id].get('satisfied', False)

Branch-Scoped Requirement Check:
───────────────────────────────
is_satisfied('commit_plan', scope='branch'):
  return req_state.get('satisfied', False)

Stop Verification Control:
─────────────────────────
hooks:
  stop:
    verify_requirements: true    # Enable Stop verification
    verify_scopes: ['session']   # Only check session-scoped
                                 # Could also be: ['session', 'branch']
                                 #                ['session', 'branch', 'permanent']

So if two branch-scoped reqs are unsatisfied but only session-scoped
are configured for verification, branch reqs won't block the stop.
```

---

## 8. THE CRITICAL LOOP: Why Re-triggering Happens

```
Why Session-Scoped Requirements Re-Trigger on New Session

Scenario: Working on feature/auth branch

Session 1 (abc123):
──────────────────
Start:
  commit_plan satisfied? → sessions["abc123"] doesn't exist → NO
  
During session:
  Run /arch-review
  Auto-satisfy:
    sessions["abc123"].satisfied = true
  
Stop hook:
  commit_plan satisfied? → sessions["abc123"].satisfied = true → YES
  Allow stop
  
END Session 1
  state file still has sessions["abc123"] = satisfied
  registry removes "abc123" entry


Session 2 (def456) - SAME BRANCH:
──────────────────────────────────
Start:
  Load state file (has old session abc123)
  
  Checking commit_plan:
    scope = 'session'
    sessions = {
      "abc123": { satisfied: true }  # ← OLD session
      // "def456" NOT IN DICT YET
    }
    
    is_satisfied('commit_plan', scope='session'):
      if self.session_id not in sessions:  # def456 not in dict
        return False  # ← Because NO def456 entry
      
  Result: commit_plan NOT satisfied
  Display: "Need to run /arch-review again"
  
During session 2:
  User runs /arch-review again
  Auto-satisfy creates:
    sessions["def456"].satisfied = true
  
Final state file:
  {
    "commit_plan": {
      "sessions": {
        "abc123": { satisfied: true },  # Historical
        "def456": { satisfied: true }   # Current
      }
    }
  }

DESIGN INTENT:
──────────────
This forces re-planning each session because:
1. Plans get stale (new context from previous session)
2. Each session should validate against current state
3. Prevents "satisfied it once, never again" anti-pattern
4. Ensures freshness for planning-critical requirements

Alternative: Could have branch-scoped requirements
  scope: branch
  → Once satisfied, satisfied for ALL sessions on branch
  → Single plan covers entire feature branch lifetime
  
But for critical requirements like commit_plan,
session-scoped enforces re-validation each session.
```

---

## 9. Clear-Single-Use Hook Behavior

```
Single-Use Requirement Clearing

Scenario: pre_commit_review (single_use scope)

Session A:
──────────
Initial state:
  {
    "pre_commit_review": {
      "scope": "single_use",
      "sessions": {}
    }
  }

Trigger (Edit tool used):
  mark_triggered('pre_commit_review', scope='single_use')
  ↓
  {
    "pre_commit_review": {
      "scope": "single_use",
      "sessions": {
        "abc123": {
          "triggered": true,
          "triggered_at": T1
        }
      }
    }
  }

User runs /pre-commit review:
  Auto-satisfy:
  {
    "pre_commit_review": {
      "scope": "single_use",
      "sessions": {
        "abc123": {
          "triggered": true,
          "triggered_at": T1,
          "satisfied": true,
          "satisfied_at": T2
        }
      }
    }
  }

User runs: git commit
  clear-single-use.py hook triggered:
    1. Check scope = 'single_use'? YES
    2. Delete sessions["abc123"]
  ↓
  {
    "pre_commit_review": {
      "scope": "single_use",
      "sessions": {}  # ← CLEARED
    }
  }

Next edit in same session:
  mark_triggered() again
  ↓
  {
    "pre_commit_review": {
      "scope": "single_use",
      "sessions": {
        "abc123": {
          "triggered": true,  # New entry
          "triggered_at": T3
        }
      }
    }
  }
  
  Is satisfied? → sessions["abc123"] has no 'satisfied' key → NO
  Must satisfy again before next commit

KEY: Sessions dict is emptied, not preserved
     Session-scoped requirements preserve (by design)
```

---

## 10. Stop Hook: Triggered Check + Satisfied Check

```
Stop Hook Verification Logic

When Claude tries to stop, Stop hook runs:

┌──────────────────────────────────────────────┐
│ For each enabled requirement:                 │
└──────────────────────────────────────────────┘
          ↓
    ┌─────────────────────┐
    │ Is it triggered?    │
    │ (was it used in     │
    │  this session?)     │
    └─────────────────────┘
          ↓
    ┌─────────────────────┐
    │ NO → Skip           │ (Don't need to satisfy if not used)
    │ YES → Check         │ (Must satisfy if was triggered)
    └─────────────────────┘
          ↓
    ┌────────────────────────┐
    │ Is it satisfied?       │
    │ (correct state?)       │
    └────────────────────────┘
          ↓
    ┌─────────────────────┐
    │ YES → Continue      │ (Good to stop)
    │ NO → BLOCK          │ (Not allowed to stop)
    └─────────────────────┘


Example: Session with multiple requirements

State:
{
  "commit_plan": {
    "scope": "session",
    "sessions": {
      "abc123": {
        "triggered": true,      # Used in this session
        "satisfied": true       # ✓ Satisfied
      }
    }
  },
  "pre_commit_review": {
    "scope": "single_use",
    "sessions": {
      "abc123": {
        "triggered": true,      # Used in this session
        "satisfied": false      # ✗ NOT satisfied
      }
    }
  },
  "permanent_audit": {
    "scope": "permanent",
    "triggered": false,         # Not used this session
    "satisfied": true           # Irrelevant
  }
}

Stop Hook Processing:

commit_plan:
  Triggered? sessions["abc123"].triggered = true → YES
  Satisfied? sessions["abc123"].satisfied = true → YES
  Result: ✓ OK

pre_commit_review:
  Triggered? sessions["abc123"].triggered = true → YES
  Satisfied? sessions["abc123"].satisfied = false → NO
  Result: ✗ UNSATISFIED - ADD TO BLOCK LIST

permanent_audit:
  Triggered? req_state.triggered = false → NO
  Result: Skip (not used this session)

Final Decision:
  unsatisfied = ['pre_commit_review']
  BLOCK STOP with message:
    "Unsatisfied Requirements: pre_commit_review
     Run: /pre-commit
     Fallback: req satisfy pre_commit_review"
```
