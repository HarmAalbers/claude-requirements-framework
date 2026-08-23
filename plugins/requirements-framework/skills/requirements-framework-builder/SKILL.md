---
name: requirements-framework-builder
description: This skill should be used when the user asks to "extend requirements framework", "add new requirement type", "create custom strategy", "add custom calculator", "modify framework architecture", "create requirement plugin", or wants to build new requirement strategies. Also triggers on questions about strategy registration, calculator implementation, or auto-satisfaction mappings.
git_hash: aed5c49
---

# Requirements Framework - Extension Guide

Guide for extending and customizing the **Claude Code Requirements Framework**. Use this skill when you need to add new requirement types, create custom strategies, or deeply customize the framework.

**Repository**: https://github.com/HarmAalbers/claude-requirements-framework
**Runtime tooling**: `uv` is required (ADR-021) — run every Python entrypoint via
`uv run`, never a bare `python3`.

> **Plugin-owned runtime.** Hook logic lives in the repo `hooks/` tree and is
> registered by the plugin's `hooks.json` (via `${CLAUDE_PLUGIN_ROOT}`). There is
> no `~/.claude/hooks` deploy and no `sync.sh` step: after editing `hooks/`,
> rebuild the plugin bundle with `uv run python scripts/build_plugin_hooks.py`.

## When to Use This Skill

Invoke this skill when you need to:

| Task | This Skill? | Alternative |
|------|-------------|-------------|
| Add a new requirement type (strategy) | ✅ Yes | - |
| Create custom calculator for dynamic reqs | ✅ Yes | - |
| Modify framework architecture | ✅ Yes | - |
| Understand framework internals | ✅ Yes | - |
| Configure existing requirements | ❌ No | `requirements-framework-usage` |
| Check current status | ❌ No | `requirements-framework-status` |
| Fix bugs / sync changes | ❌ No | `requirements-framework-development` |

**→ For current status metrics**: See `requirements-framework-status` skill

---

## How to Extend the Framework

### Adding a New Requirement Type

To add a custom requirement (e.g., `code_review`, `security_scan`):

#### Step 1: Define in Configuration

```yaml
# .claude/requirements.yaml
requirements:
  code_review:
    enabled: true
    type: blocking      # blocking | dynamic | guard | custom
    scope: session      # session | branch | permanent | single_use
    trigger_tools:
      - Edit
      - Write
      - MultiEdit
    message: |
      📝 **Code Review Required**

      Please review your changes before proceeding.

      **To satisfy**: `req satisfy code_review`
    checklist:
      - "Self-reviewed changes"
      - "No console.log statements"
      - "Error handling present"
```

#### Step 2: For Custom Strategies

If built-in strategies (blocking, dynamic, guard) don't fit, create a custom strategy:

Concrete strategies subclass `RequirementStrategy` (in `hooks/lib/base_strategy.py`)
and implement a single `check()` method. `check()` returns `None` when the
requirement is satisfied (allow the operation) or a `hookSpecificOutput` dict when
it should block/deny. It must **never raise** — fail open on any error.

```python
# hooks/lib/my_strategy.py
from typing import Optional
from base_strategy import RequirementStrategy

class MyCustomStrategy(RequirementStrategy):
    def check(self, req_name: str, config, reqs, context: dict) -> Optional[dict]:
        """Return None if satisfied (allow); a dict to block/deny. Never raise."""
        try:
            if custom_condition_check(context):
                return None  # satisfied → allow
            # Build a denial response (see strategy_utils.create_denial_response)
            from strategy_utils import create_denial_response
            return create_denial_response(req_name, config, reqs, context)
        except Exception:
            return None  # fail open
```

#### Step 3: Register the Strategy

The registry holds a single **instance** per type (concrete classes use the
`…RequirementStrategy` naming):

```python
# hooks/lib/strategy_registry.py
from blocking_strategy import BlockingRequirementStrategy
from dynamic_strategy import DynamicRequirementStrategy
from guard_strategy import GuardRequirementStrategy
from my_strategy import MyCustomStrategy

STRATEGIES = {
    'blocking': BlockingRequirementStrategy(),
    'dynamic':  DynamicRequirementStrategy(),
    'guard':    GuardRequirementStrategy(),
    'my_custom': MyCustomStrategy(),  # Add here
}
```

#### Step 4: Test and rebuild the plugin bundle

```bash
cd ~/Tools/claude-requirements-framework
uv run python hooks/test_requirements.py        # run the suite (uv required)
uv run ruff check .                             # lint (matches CI)
uv run python scripts/build_plugin_hooks.py     # rebuild the plugin hook bundle
```

### Creating a Dynamic Calculator

For requirements that auto-calculate conditions:

Calculators subclass `RequirementCalculator` (in `hooks/lib/calculator_interface.py`).
`calculate()` returns `None` to skip (fail-open) or a dict with the required keys
`value` (numeric, compared against warn/block thresholds) and `summary` (a
one-line human-readable string). It must never raise.

```python
# hooks/lib/code_complexity_calculator.py
from typing import Optional
from calculator_interface import RequirementCalculator

class CodeComplexityCalculator(RequirementCalculator):
    """Calculate code complexity for dynamic requirements."""

    def calculate(self, project_dir: str, branch: str, **kwargs) -> Optional[dict]:
        try:
            import subprocess
            result = subprocess.run(
                ['grep', '-r', 'TODO', project_dir, '-c'],
                capture_output=True, text=True,
            )
            todo_count = int(result.stdout.strip() or 0)
            return {
                'value': todo_count,
                'summary': f'{todo_count} TODO comment(s)',
            }
        except Exception:
            return None  # fail open — never block on calculator errors

# Discovery alias — the dynamic strategy imports lib.<calculator> and reads
# the module-level `Calculator` symbol. This name is REQUIRED.
Calculator = CodeComplexityCalculator
```

There is **no central `CALCULATORS` registry** (and no `requirement_strategies.py`).
The dynamic strategy loads a calculator by name: the `calculator:` config field
names the module under `hooks/lib/`, and the strategy does
`importlib.import_module("lib.<name>")` then `getattr(module, "Calculator")`.
So wiring up the calculator above is just: drop the file in `hooks/lib/`, expose
the `Calculator` alias, and reference it by module name in config.

Configure:

```yaml
requirements:
  code_complexity:
    enabled: true
    type: dynamic
    calculator: code_complexity_calculator   # → lib/code_complexity_calculator.py
    thresholds:
      warn: 10
      block: 20
    message: "Too many TODOs ({value})"
```

### Adding Auto-Satisfaction

Link skills to requirements:

```python
# hooks/auto-satisfy-skills.py  — current ADR-022 gate vocabulary
DEFAULT_SKILL_MAPPINGS: dict[str, str | list[str]] = {
    'requirements-framework:pre-commit':   'pre_commit_review',   # Build-loop gate
    'requirements-framework:deep-review':  'pr_reviewed',         # Review team
    'requirements-framework:v3-review':    'pr_reviewed',
    'requirements-framework:arch-review':  'plan_validated',      # Validate team (ONE gate, was 4)
    'requirements-framework:brainstorming': 'design_approved',
    'requirements-framework:writing-plans': 'plan_written',
    'requirements-framework:executing-plans': 'implementation_done',
    'requirements-framework:verification-before-completion': 'verified',
    'my-plugin:my-skill': 'my_requirement',  # Add mapping
}
```

> **Gate vocabulary (ADR-022).** The live gates are `design_approved`,
> `plan_written`, `plan_validated`, `implementation_done`, `pr_reviewed`,
> `verified` (ship is gateless). The old `commit_plan` / `adr_reviewed` /
> `tdd_planned` / `solid_reviewed` folded into `plan_validated`; `pre_pr_review`
> → `pr_reviewed`; `pre_push_verification` → `verified`; `codex_reviewer` is no
> longer a gate. There are **no backward-compat aliases** — a config naming a
> retired gate fails validation.

Or configure per-requirement:

```yaml
requirements:
  architecture_review:
    enabled: true
    satisfied_by_skill: 'architecture-guardian'
```

## Existing Requirement Strategies

### Blocking Strategy

Manual satisfaction required. User must run `req satisfy`.

**Use for**: Planning, review checkpoints, approval gates

```yaml
plan_validated:
  type: blocking
  scope: single_use
```

### Dynamic Strategy

Auto-calculates conditions at runtime. Uses calculators.

**Use for**: Metrics, size limits, automated checks

```yaml
branch_size_limit:
  type: dynamic
  threshold: 400
  calculation_cache_ttl: 30
```

### Guard Strategy

Condition must pass. No manual satisfaction possible.

**Use for**: Branch protection, environment checks

```yaml
protected_branch:
  type: guard
  branches: [main, master]
```

## Architecture Overview

### Key Components

```
hooks/
├── check-requirements.py      # PreToolUse hook entry
├── auto-satisfy-skills.py     # PostToolUse: skill → gate auto-satisfy
├── lib/
│   ├── requirements.py        # Core BranchRequirements API
│   ├── config.py              # Configuration cascade + WORKFLOW_DEFAULTS (ADR-022)
│   ├── strategy_registry.py   # Strategy dispatch (STRATEGIES: type → instance)
│   ├── base_strategy.py       # RequirementStrategy ABC (check())
│   ├── blocking_strategy.py   # BlockingRequirementStrategy
│   ├── dynamic_strategy.py    # DynamicRequirementStrategy (loads calculators)
│   ├── guard_strategy.py      # GuardRequirementStrategy
│   ├── calculator_interface.py # RequirementCalculator ABC (calculate())
│   ├── branch_size_calculator.py # Example dynamic calculator
│   ├── state_storage.py       # JSON state persistence
│   └── session.py             # Session tracking
```

### Configuration Cascade

```
Global (~/.claude/requirements.yaml)
    ↓ merge if inherit=true
Project (.claude/requirements.yaml)
    ↓ always merge
Local (.claude/requirements.local.yaml)
```

### State Storage

State persists in `.git/requirements/[branch].json`:

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
          "satisfied_at": 1702345678
        }
      }
    }
  }
}
```

**→ For CLI commands**: See `requirements-framework-usage` skill
**→ For development workflow**: See `requirements-framework-development` skill
**→ For ADRs and status**: See `requirements-framework-status` skill

---

## Troubleshooting

### New Requirement Not Working

1. Check config syntax: `req config my_requirement`
2. Verify enabled: `enabled: true`
3. Check trigger_tools matches your use case
4. Run `req doctor` for diagnostics

### Custom Strategy Not Loading

1. Check file in `hooks/lib/`
2. Verify registered as an **instance** in `strategy_registry.py` (`MyStrategy()`, not `MyStrategy`)
3. Rebuild the plugin bundle: `uv run python scripts/build_plugin_hooks.py`
4. Check for import errors in logs (`~/.claude/requirements.log`)

### Custom Calculator Not Loading

1. Check file in `hooks/lib/` and that it exposes a module-level `Calculator = MyCalculator` alias
2. Confirm the `calculator:` config field matches the module name (minus `.py`)
3. Verify the class subclasses `RequirementCalculator`
4. Rebuild the plugin bundle and check logs

### Tests Failing

```bash
cd ~/Tools/claude-requirements-framework
uv run python hooks/test_requirements.py        # full suite (uv required — ADR-021)
```

## Resources

- **README**: `~/Tools/claude-requirements-framework/README.md`
- **Development Guide**: `DEVELOPMENT.md`
- **ADRs**: `docs/adr/` (ADR-022 workflow backbone, ADR-021 uv, ADR-006 plugin)
- **Build the bundle**: `uv run python scripts/build_plugin_hooks.py`
- **Tests**: `hooks/test_requirements.py`
- **Config examples**: `examples/global-requirements.yaml`, `examples/project-requirements.yaml`
