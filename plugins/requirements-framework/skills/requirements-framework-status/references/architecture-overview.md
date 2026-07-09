# Architecture Overview

Design patterns, strategies, and architectural decisions in the Requirements Framework.

## Core Architecture

### Plugin-Owned Runtime

The active runtime is the **plugin**. Lifecycle hooks are registered by the
plugin's `hooks.json` (resolved via `${CLAUDE_PLUGIN_ROOT}`) — nothing is copied
into `~/.claude/hooks`, and there is no repo↔deploy `sync.sh` step.

```
Repository (source of truth)
~/Tools/claude-requirements-framework/
├── hooks/                       # hook logic + core library (lib/)
│   ├── *.py                     # lifecycle handlers
│   └── lib/*.py                 # BranchRequirements API, strategies, config
├── scripts/
│   ├── build_plugin_hooks.py    # build-copy: hooks/ → plugin bundle
│   └── render_prompts.py        # render *.md.j2 → *.md
└── plugins/requirements-framework/
    ├── .claude-plugin/plugin.json   # manifest (version, component paths)
    ├── hooks/hooks.json             # single source of truth for hook registration
    ├── hooks/                       # build-copy of hooks/ (includes requirements-cli.py)
    ├── agents/  commands/  skills/  # rendered plugin components
```

- **Repository `hooks/`**: git-controlled source of truth for all hook logic.
- **Plugin bundle** (`plugins/.../hooks/`): a build-copy produced by
  `scripts/build_plugin_hooks.py`. Never hand-edit it — edit `hooks/` and rebuild.
- **Registration**: `plugins/requirements-framework/hooks/hooks.json` wires every
  lifecycle event to a bundled script through `${CLAUDE_PLUGIN_ROOT}`.
- **Runtime tooling**: `uv` is required (ADR-021). Every entrypoint — the `req`
  CLI, the hooks, and all build/test tooling — resolves through `uv run`. Never
  invoke a bare `python3`.

---

## Session Lifecycle

### Hook Execution Order

Registered hooks span 9 lifecycle events (see `hooks.json` for the concrete
script → event wiring):

```
SessionStart (handle-session-start.py)
   → Clean stale sessions, update registry, inject full status into context

UserPromptSubmit (handle-prompt-submit.py)
   → Inject compact requirement status; brainstorm nudge (mode-independent)

PreToolUse (check-requirements.py) - on Edit/Write/Bash/EnterPlanMode/ExitPlanMode
   → Load config (global → project → local cascade)
   → Check requirements against session/branch state; allow or block

PostToolUse (multiple hooks)
   → auto-satisfy-skills.py: auto-satisfy gates when workflow skills complete
   → clear-single-use.py:    clear single_use gates after Bash triggers (loop re-arm)
   → handle-git-events.py:   track git commit/push + gh pr create (WIP metrics)
   → handle-plan-enter.py:   brainstorm auto-invoke on EnterPlanMode
   → handle-plan-exit.py:    show requirement status after ExitPlanMode

PostToolUseFailure (handle-tool-failure.py)
   → Track failure patterns; suggest a review after repeated failures

SubagentStart (handle-subagent-start.py)
   → Inject requirement context into review subagents

PreCompact (handle-pre-compact.py)
   → Save requirement state + session metrics before compaction

Stop (handle-stop.py)
   → Check stop_hook_active (prevent loops!); verify session gates; block if unsatisfied
   → langfuse-trace.py: opt-in observability Stop hook (ADR-019)

SessionEnd (handle-session-end.py)
   → Remove session from registry; optional state cleanup
```

---

## Configuration Cascade

Configurations merge in order, with later files overriding earlier ones:

```
1. Global (~/.claude/requirements.yaml)
   │
   ↓ (merge if inherit=true)
   │
2. Project (.claude/requirements.yaml)
   │  - Version controlled
   │  - Team shared settings
   │
   ↓ (always merge)
   │
3. Local (.claude/requirements.local.yaml)
      - Gitignored
      - Personal overrides
```

Priority: **local > project > global**.

### Merge Behavior

```yaml
# Global
requirements:
  plan_validated:
    enabled: true
    scope: single_use
    message: "Global message"

# Project (inherit: true)
requirements:
  plan_validated:
    checklist:          # Added (new field)
      - "Item 1"
  verified:             # Added (new requirement)
    enabled: true

# Effective result:
requirements:
  plan_validated:
    enabled: true       # From global
    scope: single_use   # From global
    message: "Global"   # From global
    checklist:          # From project
      - "Item 1"
  verified:             # From project
    enabled: true
```

---

## Workflow Backbone (ADR-022)

The default workflow is a typed 7-node backbone, not a flat checklist. Each node
carries a `type` (`spine` or `team`) and, where relevant, a `loop` or
`conditionals`:

```
Design → Plan → Validate → Build → Review → Verify → Ship
[spine] [spine] [TEAM]    [spine] [TEAM]   [spine] [spine]
```

| Node     | Type  | Gate                  | Skill / Command                       |
|----------|-------|-----------------------|---------------------------------------|
| design   | spine | `design_approved`     | `/brainstorming`                      |
| plan     | spine | `plan_written`        | `/writing-plans`                      |
| validate | team  | `plan_validated`      | `/arch-review` (cond: `/codex-review`)|
| build    | spine | `implementation_done` | `/executing-plans` (loop: `/pre-commit` → `pre_commit_review`) |
| review   | team  | `pr_reviewed`         | `/deep-review` (cond: `/codex-review`)|
| verify   | spine | `verified`            | `/verification-before-completion`     |
| ship     | spine | — (gateless)          | `/finishing-a-development-branch`     |

The current gate vocabulary is exactly: `design_approved`, `plan_written`,
`plan_validated`, `implementation_done`, `pr_reviewed`, `verified` (ship is
gateless). **Retired** (folded into the above, no compat shims):
`commit_plan`, `adr_reviewed`, `tdd_planned`, `solid_reviewed`,
`pre_pr_review`, `pre_push_verification`, `codex_reviewer`. A config still naming
a retired gate gets a validation error pointing at the new name.

---

## Strategy Pattern

Requirements use a strategy pattern for extensibility. Each requirement `type`
maps to one strategy instance in the registry.

### Strategy Registry

```python
# hooks/lib/strategy_registry.py
from blocking_strategy import BlockingRequirementStrategy
from dynamic_strategy import DynamicRequirementStrategy
from guard_strategy import GuardRequirementStrategy

# Single instance per type (lazy-initialized at module load)
STRATEGIES = {
    'blocking': BlockingRequirementStrategy(),
    'dynamic':  DynamicRequirementStrategy(),
    'guard':    GuardRequirementStrategy(),
}
```

### Strategy Types

| Type | Satisfaction | Condition | Use Case |
|------|--------------|-----------|----------|
| **Blocking** | Manual (`req satisfy`) or skill auto-satisfy | User/skill action | Workflow gates (plan, review) |
| **Dynamic** | Automatic (calculated) | Runtime check | Branch size limits |
| **Guard** | Automatic (condition) | Boolean check | Protected branches |

### Strategy Interface

All concrete strategies subclass `RequirementStrategy` and implement a single
`check()` method (fail-open — never raise):

```python
# hooks/lib/base_strategy.py
from abc import ABC, abstractmethod
from typing import Optional

class RequirementStrategy(ABC):
    @abstractmethod
    def check(self, req_name: str, config, reqs, context: dict) -> Optional[dict]:
        """Check if requirement is satisfied.

        Returns:
            None            → satisfied / allow the operation
            dict (hookSpecificOutput) → blocked or denied
        Raises:
            Never — all strategies must fail-open on errors.
        """
        ...
```

---

## Dynamic Calculators

Dynamic requirements delegate to a calculator loaded **by name** — there is no
central `CALCULATORS` registry. The `calculator:` config field names a module
under `hooks/lib/`; the dynamic strategy imports it via `importlib` and pulls the
module-level `Calculator` symbol:

```python
# dynamic_strategy loads: lib.<config['calculator']>, then getattr(module, 'Calculator')
# e.g. calculator: branch_size_calculator  →  lib/branch_size_calculator.py
```

Each calculator subclasses `RequirementCalculator`:

```python
# hooks/lib/calculator_interface.py
from abc import ABC, abstractmethod
from typing import Optional

class RequirementCalculator(ABC):
    @abstractmethod
    def calculate(self, project_dir: str, branch: str, **kwargs) -> Optional[dict]:
        """Return None to skip (fail-open), else a dict with required keys:
             'value'   (int|float) — compared against warn/block thresholds
             'summary' (str)       — one-line human-readable result
        Never raise.
        """
        ...

# The module must expose a `Calculator` alias for discovery:
Calculator = BranchSizeCalculator
```

---

## State Management

### State Storage Location

```
.git/requirements/
├── feature-auth.json    # Branch: feature/auth
├── feature-api.json     # Branch: feature/api
└── main.json            # Branch: main
```

### State Schema

```json
{
  "version": "1.0",
  "branch": "feature/auth",
  "requirements": {
    "plan_validated": {
      "scope": "single_use",
      "sessions": {
        "abc12345": {
          "satisfied": true,
          "satisfied_at": 1702345678,
          "ttl": null,
          "metadata": {}
        }
      }
    }
  }
}
```

### Session Registry

```json
// ~/.claude/sessions.json
{
  "abc12345": {
    "project": "/Users/harm/Work/myproject",
    "branch": "feature/auth",
    "pid": 12345,
    "started_at": 1702340000
  }
}
```

---

## Fail-Open Design

The framework is designed to **never block Claude** due to internal errors:

```python
def check_requirements(tool_input):
    try:
        return check_all_requirements(tool_input)
    except Exception as e:
        logger.error(f"Hook error: {e}")
        return {"allow": True}  # Fail open
```

### Error Handling Principles

1. **Log all errors** — structured JSON logging to `~/.claude/requirements.log`
2. **Never raise exceptions** — catch and allow the operation
3. **Degrade gracefully** — missing files/configs use defaults
4. **Inform user** — surface an error message when appropriate

> **Exception — strict preflight (ADR-020)**: an opt-in, fail-CLOSED adoption gate
> that deliberately inverts the fail-open default for non-compliant projects. OFF
> by default; kill-switch `RF_STRICT_OFF=true`.

---

## Caching Architecture

### Message Deduplication Cache

```python
# Prevents spam from parallel tool calls
CACHE_TTL = 300  # 5 minutes

def is_duplicate(message_hash) -> bool:
    cache = load_cache()
    if message_hash in cache:
        if time.time() - cache[message_hash] < CACHE_TTL:
            return True  # Suppress duplicate
    cache[message_hash] = time.time()
    save_cache(cache)
    return False
```

### Calculation Cache

```python
# Caches expensive calculations (branch size); default TTL ~60s
def get_branch_size(branch):
    cached = calculation_cache.get(branch)
    if cached and cached.is_valid():
        return cached.value
    size = calculate_branch_diff_size(branch)
    calculation_cache.set(branch, size)
    return size
```

---

## Hook Registration

Hooks are registered by the plugin, keyed on `${CLAUDE_PLUGIN_ROOT}` — not by a
hand-written block in `~/.claude/settings.json`:

```json
// plugins/requirements-framework/hooks/hooks.json (excerpt)
{
  "hooks": {
    "PreToolUse":  [{ "hooks": [{ "type": "command",
                       "command": "${CLAUDE_PLUGIN_ROOT}/hooks/check-requirements.py" }] }],
    "SessionStart":[{ "hooks": [{ "type": "command",
                       "command": "${CLAUDE_PLUGIN_ROOT}/hooks/handle-session-start.py" }] }],
    "PostToolUse": [{ "hooks": [
                       { "type": "command", "command": "${CLAUDE_PLUGIN_ROOT}/hooks/auto-satisfy-skills.py" },
                       { "type": "command", "command": "${CLAUDE_PLUGIN_ROOT}/hooks/clear-single-use.py" }
                     ] }]
  }
}
```

### Hook Input/Output

```python
# Input (from Claude Code, via stdin)
{
  "tool_name": "Edit",
  "tool_input": {"file_path": "/path/to/file.py", "old_string": "...", "new_string": "..."},
  "session_id": "abc12345"
}

# Output (from hook)
{
  "allow": false,                             # or true
  "message": "Requirement not satisfied..."   # optional
}
```

---

## Plugin Architecture

### Manifest (plugin.json)

```json
{
  "name": "requirements-framework",
  "version": "…",                    // bump on any plugin change (semver)
  "description": "Claude Code Requirements Framework",
  "skills": "./skills/",
  "commands": "./commands/",
  "agents": "./agents/"
}
```

### Component Discovery

```
plugins/requirements-framework/
├── .claude-plugin/
│   └── plugin.json          # Manifest
├── hooks/
│   └── hooks.json           # Lifecycle hook registration
├── skills/                  # Auto-discovered
│   └── */SKILL.md
├── commands/                # Auto-discovered
│   └── *.md
└── agents/                  # Auto-discovered
    └── *.md
```

> Plugin component `.md` files are rendered from `.md.j2` templates via
> `scripts/render_prompts.py`. Edit the `.j2`, not the rendered `.md`.

---

## Architecture Decision Records

Read the live range with `ls docs/adr/ADR-*.md`. Recent, load-bearing decisions:

| ADR | Decision | Impact |
|-----|----------|--------|
| ADR-004 | Guard strategy | Condition-based requirements |
| ADR-006 | Plugin architecture | Plugin-owned runtime + registration |
| ADR-011 | Externalized messages | YAML message files, cascade-loaded |
| ADR-012 | Agent Teams | Team-based reviews (validate / review nodes) |
| ADR-019 | Stop-hook observability | Vendored Langfuse Stop hook, opt-in |
| ADR-020 | Strict global preflight | Opt-in, fail-CLOSED adoption gate |
| ADR-021 | uv standardization | All Python runs via `uv run` |
| ADR-022 | Workflow phase re-cut | Typed 7-node backbone, ~11 → 7 gates |

---

## Performance Considerations

1. **Caching** — calculation cache (~60s) + message dedup (~5min)
2. **Lazy loading** — configs and calculators loaded on demand
3. **Minimal I/O** — state files only updated on changes
4. **Async-safe** — file locking for concurrent access
5. **Small payloads** — concise hook responses
6. **uv self-bootstrap** — near-zero overhead when deps are already synced
</content>
</invoke>
