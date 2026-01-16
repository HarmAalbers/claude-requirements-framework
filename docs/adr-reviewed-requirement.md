# ADR Reviewed Requirement - Technical Documentation

## Overview

The `adr_reviewed` requirement is a **blocking requirement** that ensures Architecture Decision Records (ADRs) have been reviewed before code changes are made. It acts as an architectural governance checkpoint to maintain consistency with established decisions documented in ADRs.

**Type**: Blocking (manually satisfied)
**Default Scope**: Session
**Trigger Tools**: Edit, Write, MultiEdit
**Status**: Enabled by default in global config

## Purpose

ADRs document important architectural decisions. The `adr_reviewed` requirement ensures that:

- Developers review relevant ADRs before making changes
- New code aligns with existing architectural decisions
- Conflicting implementations are prevented
- Architectural rationale is understood before modifications
- ADRs that need updating are identified

## Default Configuration

Located in `examples/global-requirements.yaml`:

```yaml
adr_reviewed:
  enabled: true
  type: blocking
  scope: session
  trigger_tools:
    - Edit
    - Write
    - MultiEdit
  message: |
    📚 **ADR Review Checkpoint**

    Have you reviewed relevant Architecture Decision Records?

    **Why this matters**:
    - Ensures consistency with existing architectural decisions
    - Prevents conflicting implementations
    - Documents reasoning for future maintainers
    - Maintains architectural integrity

    **To satisfy**: `req satisfy adr_reviewed` after reviewing ADRs
  checklist:
    - "Searched for ADRs related to this change"
    - "Reviewed decision context and rationale"
    - "Confirmed approach aligns with existing ADRs"
    - "Noted any ADRs that need updating"
```

## Configuration Cascade

The requirement can be defined at three levels with cascading overrides:

### 1. Global Configuration
**Location**: `~/.claude/requirements.yaml`
**Purpose**: Personal defaults for all projects
**Visibility**: User-specific

### 2. Project Configuration
**Location**: `.claude/requirements.yaml`
**Purpose**: Team-wide requirements
**Visibility**: Version controlled, shared with team

Example project override:
```yaml
adr_reviewed:
  enabled: true
  scope: session
  message: |
    📚 **Working in cclv2 - Have you reviewed relevant ADRs?**

    ADRs are in: /Users/harm/Work/cclv2/ADR/

    Before making code changes, check if any ADRs are relevant to your work.

    **To satisfy**: `req satisfy adr_reviewed` after reviewing
```

### 3. Local Configuration
**Location**: `.claude/requirements.local.yaml`
**Purpose**: Personal overrides (gitignored)
**Visibility**: Developer-specific

```yaml
adr_reviewed:
  enabled: false  # Temporarily disable for rapid prototyping
```

## Requirement Type: Blocking

### Strategy Implementation

The `adr_reviewed` requirement uses the **BlockingRequirementStrategy** defined in `hooks/lib/blocking_strategy.py`.

**Key Characteristics**:
- **Manual satisfaction required**: Cannot be automatically satisfied by calculations
- **Explicit CLI command needed**: Must run `req satisfy adr_reviewed`
- **Type detection**: Defaults to "blocking" if `type` field is omitted

**Code Reference** (`config.py:1370`):
```python
def get_requirement_type(self, req_name: str) -> RequirementType:
    """Default: 'blocking' for backwards compatibility"""
    return cast(RequirementType, self.get_attribute(req_name, "type", "blocking"))
```

### Check Logic

From `blocking_strategy.py:36-51`:

```python
def check(self, req_name: str, config: RequirementsConfig,
          reqs: BranchRequirements, context: dict) -> Optional[dict]:
    """
    Check if blocking requirement is satisfied.

    Returns:
        None if satisfied
        Dict with denial message if not satisfied
    """
    scope = config.get_scope(req_name)

    if not reqs.is_satisfied(req_name, scope):
        # Not satisfied - create denial response
        return self._create_denial_response(req_name, config, context)

    return None  # Satisfied, allow
```

## Scope: Session

### What Session Scope Means

**Session scope** defines the lifetime and isolation boundaries of requirement satisfaction:

✅ **Must be satisfied once per Claude Code session**
✅ **Persists for the current session only**
✅ **Automatically cleared when session ends** (by default)
✅ **Separate from other sessions on the same branch**
✅ **Each terminal window running Claude Code = separate session**

### Why Session Scope?

Session scope is ideal for `adr_reviewed` because:

1. **Daily reminder**: Forces ADR review at the start of each work session
2. **Context changes**: Different sessions may work on different features
3. **Session isolation**: Multiple concurrent Claude sessions maintain independent state
4. **Not too burdensome**: Only once per session, not per commit

### State Storage

State is persisted in `.git/requirements/[branch].json` with session-specific tracking:

```json
{
  "requirements": {
    "adr_reviewed": {
      "scope": "session",
      "sessions": {
        "abc12345": {
          "satisfied": true,
          "timestamp": 1234567890,
          "method": "cli",
          "metadata": {},
          "triggered": true
        },
        "xyz67890": {
          "satisfied": false,
          "timestamp": 1234567891,
          "triggered": true
        }
      }
    }
  }
}
```

**Key fields**:
- `satisfied`: Boolean satisfaction state
- `timestamp`: Unix timestamp when satisfied
- `method`: How satisfied (`cli`, `skill`, `auto`)
- `metadata`: Optional extra data
- `triggered`: Whether requirement was triggered this session

### Branch-Level Override

Users can satisfy at branch level to apply to all sessions:

```bash
req satisfy adr_reviewed --branch
```

This creates branch-level satisfaction that applies to current and future sessions on that branch.

## Lifecycle & Hook Integration

The `adr_reviewed` requirement integrates with all six hooks in the session lifecycle:

### 1. SessionStart Hook

**File**: `hooks/handle-session-start.py`
**Purpose**: Context injection and session registration

**Actions**:
- Cleans up stale session entries from registry
- Registers current session in global registry (`~/.claude/sessions.json`)
- Injects full requirements status into Claude's context
- Shows: `⬜ **adr_reviewed** (session scope)` if unsatisfied

**Output to Claude**:
```
📋 **Requirements Framework Status**

  ⬜ **commit_plan** (session scope)
  ⬜ **adr_reviewed** (session scope)
  ⬜ **protected_branch** (session scope)
  ...
```

### 2. PreToolUse Hook (Main Enforcement)

**File**: `hooks/check-requirements.py`
**Purpose**: Block Edit/Write/MultiEdit operations when unsatisfied

**Execution Flow** (lines 177-349):

```
1. Parse stdin JSON (tool_name, tool_input, session_id)
2. Early setup (load config, initialize logger)
3. Skip checks if:
   - CLAUDE_SKIP_REQUIREMENTS env var set
   - Tool is read-only (Read, Glob, Grep)
   - File is a plan file (.claude/plans/)
   - No project context or config
   - Framework disabled
4. Update session registry (for CLI discovery)
5. For each enabled requirement:
   a. Check if tool matches trigger_tools
   b. Mark requirement as triggered (for Stop hook)
   c. Get strategy for requirement type
   d. Execute strategy.check()
   e. Collect unsatisfied requirements
6. If any unsatisfied: emit batched denial response
7. Else: allow operation (exit 0)
```

**Trigger Matching** (line 274):
```python
triggers = config.get_triggers(req_name)
if not matches_trigger(tool_name, tool_input, triggers):
    continue
```

**Strategy Dispatch** (lines 282-310):
```python
# Get strategy for requirement type (blocking, dynamic, etc.)
req_type = config.get_requirement_type(req_name)
strategy = STRATEGIES.get(req_type)

# Execute strategy to check requirement
context = {
    'project_dir': project_dir,
    'branch': branch,
    'session_id': session_id,
    'tool_name': tool_name,
}

response = strategy.check(req_name, config, reqs, context)
if response:
    # Strategy returned a block/deny response - collect it
    unsatisfied.append((req_name, req_config))
```

**Batched Denial** (lines 338-346):
Multiple unsatisfied requirements are combined into a single message:

```
**Unsatisfied Requirements**

The following requirements must be satisfied before making changes:

- **commit_plan** (session scope)
  📋 **No commit plan found for this session**
  ...

- **adr_reviewed** (session scope)
  📚 **ADR Review Checkpoint**
  ...

**Current session**: `abc12345`

💡 **To satisfy all requirements at once**:
```bash
req satisfy commit_plan adr_reviewed --session abc12345
```
```

### 3. PostToolUse Hook - Auto-Satisfy

**File**: `hooks/auto-satisfy-skills.py`
**Purpose**: Auto-satisfy requirements when specific skills complete

**Configuration Support**:
```yaml
adr_reviewed:
  satisfied_by_skill: 'adr-guardian'
```

**Execution Flow** (lines 74-168):

```
1. Parse stdin JSON (check if Skill tool completed)
2. Skip if not Skill tool
3. Load project config
4. Build skill→requirement mappings:
   - Default mappings (requirements-framework:*)
   - Config-based mappings (satisfied_by_skill field)
5. If skill matches a requirement:
   a. Get requirement scope
   b. Call reqs.satisfy(req_name, scope, method='skill')
   c. Log auto-satisfaction
```

**Mapping Building** (lines 48-71):
```python
def get_skill_requirement_mappings(config: RequirementsConfig) -> dict:
    """Build skill → requirement mapping from configuration."""
    mappings = {}

    for req_name in config.get_all_requirements():
        if not config.is_requirement_enabled(req_name):
            continue

        skill_name = config.get_attribute(req_name, 'satisfied_by_skill')
        if skill_name and isinstance(skill_name, str):
            mappings[skill_name] = req_name

    return mappings
```

**Auto-Satisfaction** (lines 152-155):
```python
# Satisfy the requirement
reqs = BranchRequirements(branch, session_id, project_dir)
reqs.satisfy(req_name, scope, method='skill', metadata={'skill': skill_name})
```

### 4. PostToolUse Hook - Clear Single-Use

**File**: `hooks/clear-single-use.py`
**Purpose**: Clear single_use requirements after trigger commands complete

**Note**: Does not affect `adr_reviewed` since it uses session scope, not single_use scope.

This hook is relevant for requirements like `pre_commit_review` that need to be satisfied before each commit.

### 5. PostToolUse Hook - Plan Exit

**File**: `hooks/handle-plan-exit.py`
**Purpose**: Show requirements status after exiting plan mode

**Actions**:
- Triggered after ExitPlanMode tool completes
- Shows full requirements status proactively
- Reminds Claude about unsatisfied requirements before Edit attempts

### 6. Stop Hook (Verification)

**File**: `hooks/handle-stop.py`
**Purpose**: Verify triggered requirements before allowing Claude to stop

**Execution Flow** (lines 43-150):

```
1. Parse stdin JSON
2. CRITICAL: Check stop_hook_active flag
   - If true: exit immediately (prevent infinite loops)
3. Load project config
4. Skip if verification disabled
5. Get verify_scopes (default: ['session'])
6. For each enabled requirement:
   a. Skip if scope not in verify_scopes
   b. Skip if not triggered this session ← KEY CHECK
   c. For guard requirements: evaluate condition
   d. For blocking/dynamic: check is_satisfied()
   e. Collect unsatisfied requirements
7. If unsatisfied: emit block response
8. Else: allow stop
```

**Triggered vs. Satisfied** (lines 115-117):
```python
# Only check requirements that were triggered this session
# (research-only sessions skip requirements they never triggered)
if not reqs.is_triggered(req_name, scope):
    logger.debug("Skipping untriggered requirement", requirement=req_name, scope=scope)
    continue
```

This is critical: if you only use Read/Glob/Grep in a session (research only), `adr_reviewed` won't be triggered and won't block the Stop hook.

**Block Response** (lines 136-149):
```python
if unsatisfied:
    logger.info("Blocking stop - requirements unsatisfied", requirements=unsatisfied)

    req_list = ', '.join(unsatisfied)
    response = {
        "decision": "block",
        "reason": (
            f"⚠️ **Requirements not satisfied**: {req_list}\n\n"
            "Please satisfy these requirements before finishing, or use "
            "`req satisfy <name>` to mark them complete."
        )
    }
    emit_json(response)
```

**Loop Prevention** (line 57):
```python
# If stop_hook_active is True, Claude already continued once due to this hook
# We MUST NOT block again or we'll loop forever
if input_data.get('stop_hook_active', False):
    return 0
```

### 7. SessionEnd Hook

**File**: `hooks/handle-session-end.py`
**Purpose**: Cleanup when session ends

**Actions**:
- Removes session from global registry (`~/.claude/sessions.json`)
- **Does NOT clear state by default** (satisfaction persists in `.git/requirements/`)
- Optional clearing via `hooks.session_end.clear_session_state: false` (default)

**Note**: Session-scoped requirements naturally become inactive when the session ends, even though the state remains on disk. New sessions won't inherit the old session's satisfaction state.

## CLI Commands

### req satisfy

Mark the requirement as satisfied.

**Auto-detect session** (recommended):
```bash
req satisfy adr_reviewed
```

Output:
```
✨ Auto-detected Claude session: abc12345
✅ Satisfied 'adr_reviewed' for feature-branch (session scope)
```

**Explicit session**:
```bash
req satisfy adr_reviewed --session abc12345
```

**Branch-level satisfaction** (all sessions):
```bash
req satisfy adr_reviewed --branch
```

Output:
```
🌿 Using branch-level satisfaction for: feature-branch
✅ Satisfied 'adr_reviewed' at branch level for feature-branch
   ℹ️  All current and future sessions on this branch are now satisfied
```

**Multiple requirements**:
```bash
req satisfy commit_plan adr_reviewed
```

Output:
```
✅ Satisfied 2 requirement(s)
   Session: abc12345
   Branch: feature-branch
```

**Implementation** (`requirements-cli.py:425-574`):

```python
def cmd_satisfy(args) -> int:
    """Satisfy a requirement."""
    # Check git repo
    # Branch-level mode detection (--branch flag)
    # Smart session detection:
    #   1. Explicit --session flag
    #   2. Auto-detect from registry
    # Load config
    # Parse metadata
    # Initialize requirements manager
    # For each requirement:
    #   - Check if exists in config
    #   - Handle based on type (blocking vs dynamic)
    #   - Use configured scope or force branch scope
    #   - Call reqs.satisfy()
```

### req status

View current requirements status.

**Basic usage**:
```bash
req status
```

Output:
```
📋 **Requirements Status**

**Project**: /Users/harm/Tools/project
**Branch**: feature-branch
**Session**: abc12345

**Requirements**:
  ✅ commit_plan (session)
  ⬜ adr_reviewed (session) ← NOT SATISFIED
  ✅ protected_branch (guard)
  ✅ branch_size_limit (dynamic)

💡 To satisfy: req satisfy adr_reviewed
```

**Session-specific**:
```bash
req status --session abc12345
```

**Focused mode** (only unsatisfied):
```bash
req status --focused
```

Output:
```
⚠️  **Unsatisfied Requirements**

  ⬜ adr_reviewed (session scope)

💡 To satisfy: req satisfy adr_reviewed --session abc12345
```

### req config

View or modify requirement configuration.

**View config**:
```bash
req config adr_reviewed
```

Output:
```yaml
adr_reviewed:
  enabled: true
  type: blocking
  scope: session
  trigger_tools:
    - Edit
    - Write
    - MultiEdit
  message: |
    📚 **ADR Review Checkpoint**
    ...
  checklist:
    - "Searched for ADRs related to this change"
    ...
```

**Enable/disable**:
```bash
req config adr_reviewed --enable
req config adr_reviewed --disable
```

**Change scope**:
```bash
req config adr_reviewed --scope branch     # Branch-level
req config adr_reviewed --scope permanent  # Never cleared
```

**Set custom fields** (writes to `.local.yaml`):
```bash
req config adr_reviewed --set adr_path=/docs/adr
req config adr_reviewed --set custom_field="value"
```

**Change message**:
```bash
req config adr_reviewed --message "Custom message text"
```

### req clear

Clear a requirement's satisfaction state.

**Basic usage**:
```bash
req clear adr_reviewed
```

**Session-specific**:
```bash
req clear adr_reviewed --session abc12345
```

**Branch-level**:
```bash
req clear adr_reviewed --branch
```

**Multiple requirements**:
```bash
req clear commit_plan adr_reviewed
```

### req approve (Dynamic Requirements)

Note: `req approve` is for dynamic requirements only (e.g., `branch_size_limit`). For `adr_reviewed`, use `req satisfy` instead.

## Integration with ADR Guardian Agent

The framework includes an `adr-guardian` agent for automated ADR compliance checking.

**Location**: `plugin/agents/adr-guardian.md`

**Capabilities**:
- Reviews plans against ADRs before implementation
- Validates code compliance with architectural decisions
- Issues **BLOCKING** verdicts for violations
- Proposes new ADRs when needed
- Discovers ADR locations automatically

**ADR Discovery Order**:
1. `/docs/adr/` (common convention)
2. `/ADR/` (legacy convention)
3. `/docs/architecture/decisions/`
4. `/.adr/`
5. `/architecture/adr/`

**Auto-Satisfaction Configuration**:

```yaml
adr_reviewed:
  enabled: true
  scope: session
  satisfied_by_skill: 'adr-guardian'
```

When configured with `satisfied_by_skill`, running the adr-guardian agent automatically satisfies the requirement.

**Workflow Example**:
```
1. Claude attempts Edit → blocked by adr_reviewed
2. User/Claude runs adr-guardian agent
3. Agent reviews ADRs and provides verdict
4. auto-satisfy-skills hook marks adr_reviewed satisfied
5. User/Claude can now Edit files
```

## Message Deduplication

The blocking strategy includes TTL-based deduplication to prevent spam from parallel tool calls.

**Implementation** (`blocking_strategy.py:98-107`):

```python
# Deduplication check to prevent spam from parallel tool calls
if self.dedup_cache:
    cache_key = f"{context['project_dir']}:{context['branch']}:{session_id}:{req_name}"

    if not self.dedup_cache.should_show_message(cache_key, message, ttl=5):
        # Suppress verbose message - show minimal indicator instead
        minimal_message = f"⏸️ Requirement `{req_name}` not satisfied (waiting...)"
        return create_denial_response(minimal_message)

# Show full message (first time or after TTL expiration)
return create_denial_response(message)
```

**Behavior**:
- First denial: Full message with checklist and instructions
- Subsequent denials within 5 seconds: Minimal indicator `⏸️`
- After 5 seconds: Full message shown again

This prevents console spam when multiple Edit calls happen in quick succession.

## State Management

### BranchRequirements Class

**Location**: `hooks/lib/requirements.py`

**Key Methods**:

#### `is_satisfied(req_name: str, scope: str) -> bool`

**Purpose**: Check if requirement is satisfied
**Lines**: 150-193

```python
def is_satisfied(self, req_name: str, scope: str = 'session') -> bool:
    """
    Check if requirement is satisfied.

    Handles different scopes and TTL expiration. Also checks for branch-level
    overrides that apply to all sessions (set via `req satisfy --branch`).
    """
    req_state = self._get_req_state(req_name)
    now = time.time()

    # Check for branch-level override first
    if scope in ('session', 'single_use') and req_state.get('satisfied', False):
        # Branch-level satisfaction exists - check TTL if present
        ttl = req_state.get('ttl')
        if ttl is not None:
            timestamp = req_state.get('timestamp', 0)
            if now - timestamp > ttl:
                return False  # Expired
        return True  # Branch-level satisfied

    # Session/single_use: check specific session
    if scope in ('session', 'single_use'):
        sessions = req_state.get('sessions', {})
        if self.session_id not in sessions:
            return False

        session_state = sessions[self.session_id]
        if not session_state.get('satisfied', False):
            return False

        # Check TTL if present
        ttl = session_state.get('ttl')
        if ttl is not None:
            timestamp = session_state.get('timestamp', 0)
            if now - timestamp > ttl:
                return False  # Expired

        return True

    # Branch/permanent: check at requirement level
    elif scope in ('branch', 'permanent'):
        if not req_state.get('satisfied', False):
            return False

        # Check TTL if present
        ttl = req_state.get('ttl')
        if ttl is not None:
            timestamp = req_state.get('timestamp', 0)
            if now - timestamp > ttl:
                return False  # Expired

        return True

    # Unknown scope defaults to not satisfied
    return False
```

#### `satisfy(req_name: str, scope: str, method: str, metadata: dict, ttl: int) -> None`

**Purpose**: Mark requirement as satisfied
**Lines**: 340-402

```python
def satisfy(
    self,
    req_name: str,
    scope: str = 'session',
    method: str = 'manual',
    metadata: Optional[dict] = None,
    ttl: Optional[int] = None
) -> None:
    """Mark requirement as satisfied."""
    req_state = self._get_req_state(req_name)
    req_state['scope'] = scope
    now = int(time.time())

    if scope in ('session', 'single_use'):
        # Session/single_use: store in sessions dict
        if 'sessions' not in req_state:
            req_state['sessions'] = {}

        req_state['sessions'][self.session_id] = {
            'satisfied': True,
            'timestamp': now,
            'method': method,
        }

        if metadata:
            req_state['sessions'][self.session_id]['metadata'] = metadata

        if ttl is not None:
            req_state['sessions'][self.session_id]['ttl'] = ttl

    elif scope in ('branch', 'permanent'):
        # Branch/permanent: store at requirement level
        req_state['satisfied'] = True
        req_state['timestamp'] = now
        req_state['method'] = method

        if metadata:
            req_state['metadata'] = metadata

        if ttl is not None:
            req_state['ttl'] = ttl

    self._save()
```

#### `mark_triggered(req_name: str, scope: str) -> None`

**Purpose**: Mark that requirement was triggered this session
**Lines**: 279-301

```python
def mark_triggered(self, req_name: str, scope: str) -> None:
    """
    Mark that requirement was triggered (not necessarily satisfied).

    Used by Stop hook to distinguish requirements that were checked
    vs. those that were never relevant to this session.
    """
    req_state = self._get_req_state(req_name)

    if scope in ('session', 'single_use'):
        # Session/single_use: store in sessions dict
        if 'sessions' not in req_state:
            req_state['sessions'] = {}

        if self.session_id not in req_state['sessions']:
            req_state['sessions'][self.session_id] = {}

        req_state['sessions'][self.session_id]['triggered'] = True

    elif scope in ('branch', 'permanent'):
        # Branch/permanent: store at requirement level
        req_state['triggered'] = True

    self._save()
```

#### `is_triggered(req_name: str, scope: str) -> bool`

**Purpose**: Check if requirement was triggered this session
**Lines**: 314-338

Used by Stop hook to avoid blocking on requirements that were never relevant to this session.

### State File Format

**Location**: `.git/requirements/[branch].json`

**Full Example**:
```json
{
  "version": "1.0",
  "branch": "feature-branch",
  "last_modified": 1234567890,
  "requirements": {
    "adr_reviewed": {
      "scope": "session",
      "sessions": {
        "abc12345": {
          "satisfied": true,
          "timestamp": 1234567890,
          "method": "cli",
          "metadata": {},
          "triggered": true
        },
        "xyz67890": {
          "satisfied": false,
          "timestamp": 1234567891,
          "triggered": true
        }
      }
    },
    "commit_plan": {
      "scope": "session",
      "satisfied": true,
      "timestamp": 1234567892,
      "method": "skill",
      "metadata": {
        "skill": "requirements-framework:pre-commit"
      }
    }
  }
}
```

## Testing

The framework includes comprehensive test coverage for `adr_reviewed`.

**Test File**: `hooks/test_requirements.py` (544 total tests)

**Key Tests**:

### Test: Status Command Shows adr_reviewed (line 1409)
```python
result = subprocess.run(
    ["python3", str(cli_path), "status", "--session", test_session],
    cwd=tmpdir, capture_output=True, text=True
)
runner.test("Focused shows remaining unsatisfied", "adr_reviewed" in result.stdout, result.stdout)
```

### Test: Batch Blocking Includes adr_reviewed (line 2859)
```python
runner.test("Message contains commit_plan", "commit_plan" in message, f"Message: {message[:200]}")
runner.test("Message contains adr_reviewed", "adr_reviewed" in message, f"Message: {message[:200]}")
runner.test("Message contains batch command hint",
           "req satisfy commit_plan adr_reviewed" in message or
           "req satisfy adr_reviewed commit_plan" in message,
           f"Message: {message[:200]}")
```

### Test: Config --set Works (line 3986)
```python
runner.test("config --set runs", result.returncode == 0, result.stderr)

# Verify custom field was written
if local_file.exists():
    content = local_file.read_text()
    runner.test("config --set writes custom field", "/docs/adr" in content or "adr_path" in content,
```

**Run Tests**:
```bash
python3 hooks/test_requirements.py
```

## Design Principles

### 1. Fail-Open Architecture

All hooks follow a fail-open design philosophy:

```python
try:
    # Requirement checking logic
    ...
except Exception as e:
    logger.error("Error checking requirements", error=str(e))
    return 0  # Fail open - don't block work
```

**Rationale**: Errors in the requirements framework should never prevent legitimate work. If config is malformed, hooks fail, or state is corrupted, the framework logs the error and allows operations to proceed.

### 2. Strategy Pattern

The `adr_reviewed` requirement leverages the strategy registry for extensibility.

**Registry** (`strategy_registry.py:19-23`):
```python
STRATEGIES = {
    'blocking': BlockingRequirementStrategy(),
    'dynamic': DynamicRequirementStrategy(),
    'guard': GuardRequirementStrategy(),
}
```

**Benefits**:
- Single dispatch point for all requirement types
- Easy to add new requirement types
- Consistent interface across strategies
- Strategy instances are singletons (performance)

### 3. Triggered vs. Satisfied

The framework distinguishes between:

- **Triggered**: User attempted an Edit/Write operation
- **Satisfied**: Requirement was met

**Why This Matters**:
- Research-only sessions (Read/Glob/Grep) don't trigger requirements
- Stop hook only checks triggered requirements
- Prevents false positives on requirements that weren't relevant

**Example**:
```
Session 1 (research only):
- User runs: Read file.py, Grep pattern, Glob *.py
- adr_reviewed: NOT triggered
- Stop hook: Allows stop (requirement not triggered)

Session 2 (editing):
- User runs: Edit file.py
- adr_reviewed: TRIGGERED, but NOT satisfied
- Stop hook: Blocks stop (requirement triggered but unsatisfied)
```

### 4. Deduplication

TTL-based message deduplication prevents spam from parallel tool calls:

```python
cache_key = f"{project_dir}:{branch}:{session_id}:{req_name}"

if not self.dedup_cache.should_show_message(cache_key, message, ttl=5):
    # Show minimal indicator
    return create_denial_response(f"⏸️ Requirement `{req_name}` not satisfied (waiting...)")
```

### 5. Session Isolation

Each Claude Code session maintains independent state:

- Separate `session_id` for each terminal window
- Session registry tracks all active sessions
- CLI can list and target specific sessions
- No cross-session interference

## Common Usage Patterns

### Pattern 1: Basic Workflow

```bash
# Start Claude Code session
claude

# Claude attempts Edit → blocked by adr_reviewed
# User reviews ADRs, then satisfies requirement
req satisfy adr_reviewed

# Now Claude can Edit files
# Requirement persists for this session
```

### Pattern 2: Auto-Satisfaction via Agent

```yaml
# .claude/requirements.yaml
adr_reviewed:
  satisfied_by_skill: 'adr-guardian'
```

```bash
# Claude runs adr-guardian agent
# auto-satisfy-skills hook automatically marks satisfied
# Claude can now Edit files
```

### Pattern 3: Branch-Level Satisfaction

```bash
# Working on long-lived feature branch
# Satisfy once for all sessions
req satisfy adr_reviewed --branch

# All future sessions on this branch are pre-satisfied
# Useful for ongoing feature work
```

### Pattern 4: Temporary Disable

```yaml
# .claude/requirements.local.yaml
adr_reviewed:
  enabled: false
```

```bash
# Rapid prototyping - disable temporarily
# Remember to re-enable before committing
```

### Pattern 5: Project-Specific ADR Path

```yaml
# .claude/requirements.yaml
adr_reviewed:
  enabled: true
  message: |
    📚 **Review ADRs in /docs/architecture/**

    Project ADRs: /docs/architecture/decisions/

    Satisfy: `req satisfy adr_reviewed`
```

## Troubleshooting

### Requirement Not Blocking

**Symptom**: Can Edit files even though adr_reviewed is unsatisfied

**Possible Causes**:
1. Requirement disabled in config
2. Framework disabled via `enabled: false`
3. `CLAUDE_SKIP_REQUIREMENTS` env var set
4. Editing a plan file (automatically skipped)
5. Config file doesn't exist

**Debug**:
```bash
# Check requirement status
req status

# Check config
req config adr_reviewed

# Check if framework enabled
cat .claude/requirements.yaml | grep "enabled:"

# Check environment
echo $CLAUDE_SKIP_REQUIREMENTS

# Enable debug logging
req logging --level debug --local
tail -f ~/.claude/requirements.log
```

### Session Not Auto-Detected

**Symptom**: `req satisfy adr_reviewed` fails to find session

**Possible Causes**:
1. Session not registered in `~/.claude/sessions.json`
2. Registry file corrupted
3. Hook didn't update registry

**Solution**:
```bash
# Use explicit session ID (from Claude)
req satisfy adr_reviewed --session abc12345

# Or use branch-level
req satisfy adr_reviewed --branch

# Check registry
cat ~/.claude/sessions.json
```

### Stop Hook Not Verifying

**Symptom**: Claude stops even though adr_reviewed is unsatisfied

**Possible Causes**:
1. Stop verification disabled in config
2. Requirement wasn't triggered (research-only session)
3. Stop hook config set to skip session scope

**Check**:
```yaml
# .claude/requirements.yaml
hooks:
  stop:
    verify_requirements: true  # Must be true
    verify_scopes: ['session']  # Must include 'session'
```

### Requirement Persists After Session End

**Symptom**: New session shows adr_reviewed as satisfied

**Explanation**: This is expected behavior if:
1. Previous session satisfied at branch level (`--branch`)
2. SessionEnd hook configured to preserve state (default)

**Solution**:
```bash
# Clear branch-level satisfaction
req clear adr_reviewed --branch

# Or clear for specific session
req clear adr_reviewed --session abc12345
```

## Performance Considerations

### Hook Execution Time

PreToolUse hook execution time breakdown:
- Config loading: ~5-10ms
- State loading: ~1-3ms
- Strategy checking: ~1ms
- Total: ~10-15ms per Edit/Write

**Optimizations**:
- Config cached in memory during session
- State file is small JSON (~1-10KB)
- Strategy instances are singletons
- Deduplication cache reduces message generation

### State File Size

State file grows with number of sessions:
- Typical size: 1-5KB
- Max size: ~50KB (hundreds of sessions)
- Automatic cleanup of stale sessions

### Logging Impact

Debug logging adds ~2-5ms per hook call:
```bash
# Production (INFO level)
req logging --level info --local

# Development (DEBUG level)
req logging --level debug --local
```

## Related Documentation

- **Framework Overview**: `docs/README-REQUIREMENTS-FRAMEWORK.md`
- **Development Guide**: `DEVELOPMENT.md`
- **Architecture Decisions**: `docs/adr/`
- **Plugin Installation**: `docs/PLUGIN-INSTALLATION.md`
- **CLI Examples**: `docs/req-init-examples.md`

## Summary

The `adr_reviewed` requirement is a sophisticated, session-scoped blocking requirement that:

1. ✅ **Enforces** ADR review before code modifications
2. ✅ **Blocks** Edit/Write/MultiEdit operations when unsatisfied
3. ✅ **Persists** per session with state in `.git/requirements/`
4. ✅ **Integrates** with all six hooks across the session lifecycle
5. ✅ **Supports** auto-satisfaction via the adr-guardian agent
6. ✅ **Provides** helpful CLI commands and batch operations
7. ✅ **Deduplicates** messages to prevent spam
8. ✅ **Verifies** at Stop hook before allowing session end
9. ✅ **Fails open** on errors to never block legitimate work
10. ✅ **Scales** via configuration cascade (global → project → local)

This requirement exemplifies the framework's design philosophy: lightweight, fail-open enforcement that guides Claude Code toward architectural consistency without creating unnecessary friction.
