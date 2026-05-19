# Step 05 — `/req` conductor command

## Goal

A single slash command that derives the current phase from requirement state and dispatches to the right existing skill/command. No new agents, no new dependencies, just a thin router.

## Why now

This is the structural simplification. Once it exists, every existing command can become an alias (Step 06), and the user has one thing to remember: `/req`.

## Files touched

- `plugins/requirements-framework/commands/req.md` (new)
- `hooks/lib/derive_phase.py` (new; small pure-function module)
- `hooks/test_requirements.py` — add tests for `derive_phase`

## Implementation

### `hooks/lib/derive_phase.py`

```python
"""Pure function: requirement state -> phase name."""
import json
import sys
from pathlib import Path

PHASES = ["design", "plan", "implement", "review", "ship"]
REQUIREMENT_FOR_PHASE = {
    "design": "design_approved",
    "plan": "plan_written",
    "implement": "verification_evidence",
    "review": "pre_pr_review",
}

def derive_phase(state: dict) -> str:
    """Return the first unsatisfied phase in pipeline order. Default 'ship'."""
    for phase in PHASES[:-1]:
        req = REQUIREMENT_FOR_PHASE[phase]
        if not state.get("requirements", {}).get(req, {}).get("satisfied", False):
            return phase
    return "ship"

if __name__ == "__main__":
    path = Path(sys.argv[1])
    state = json.loads(path.read_text()) if path.exists() else {}
    print(derive_phase(state))
```

### `req.md` command

```markdown
---
name: req
description: "Workflow conductor — derives current phase and dispatches to the right existing command. Run with no args to be guided; or pass a phase: design, plan, implement, review, refactor, ship."
argument-hint: "[phase]"
allowed-tools: ["Bash", "Read"]
git_hash: uncommitted
---

# Req Conductor

## Step 1: Resolve phase

If "$ARGUMENTS" is one of `design|plan|implement|review|refactor|ship`, use that.
Otherwise derive the phase by running:
`python3 $CLAUDE_PLUGIN_ROOT/hooks/lib/derive_phase.py .git/requirements/$(git rev-parse --abbrev-ref HEAD).json`

## Step 2: Dispatch

Look up the phase in this table and tell the user which command you are invoking, then invoke it:

| Phase | Command |
|-------|---------|
| design | `/brainstorm` |
| plan | `/arch-review` |
| implement | `/execute-plan` |
| review | `/deep-review` |
| refactor | `/refactor-orchestrate` |
| ship | report status; suggest `/codex-review` then PR creation |

## Step 3: After dispatch

Do nothing more. The target command/skill takes over from here.
```

## Example

**Session moment**: phase derived as `review`, user types `/req`.

**Conductor output**:
> Phase is **review**. Invoking `/deep-review`.

Then `/deep-review` runs as today, recruits 13 agents, produces report. `auto-satisfy-skills.py` flips `pre_pr_review`. Next session's derived phase is `ship`.

## Acceptance

- [ ] `python3 hooks/lib/derive_phase.py /tmp/empty.json` prints `design`
- [ ] After `req satisfy design_approved`, derive prints `plan`
- [ ] Unit tests cover all 5 phase transitions
- [ ] `/req` with no args produces a single human-readable line + one command invocation
- [ ] `/req review` (with arg) skips derivation and goes straight to review

## Rollback

Delete `req.md` and `derive_phase.py`. Aliases (Step 06) still work since they point to the original commands.

## Effort

1 day

## Depends on

None for the command itself. Step 04 (`workflow-index`) provides the documentation surface; Step 03 (statusline) consumes `derive_phase.py`.

## Honest scope note

This is **not** a PydanticAI supervisor. It's a deterministic dispatch table in Markdown + a 30-line Python helper. The supervisor pattern from research is the right *eventual* shape, but introducing PydanticAI is out of scope for the simplification step. Today's Markdown command is enough to validate the workflow shape before we commit to the dependency.
