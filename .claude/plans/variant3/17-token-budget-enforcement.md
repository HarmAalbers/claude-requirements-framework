# Step 17 — Token budget enforcement

## Goal

Add explicit per-worker token budgets enforced in `PreToolUse`. If a rendered prompt exceeds budget, degrade gracefully (drop examples → drop retrieval → fail loudly).

## Why now

We have a rendering pipeline (Step 16). Without budgets, retrieval and examples can balloon a prompt unpredictably.

## Files touched

- `hooks/lib/llm/budget.py` (new)
- `hooks/lib/llm/templates.py` — add `render_with_budget`
- `hooks/check-requirements.py` (the PreToolUse hook) — read planned tool_input, estimate
- `requirements.yaml` — add `budgets:` config block

## Validated APIs

`tiktoken` (standard, well-known):
```python
import tiktoken
enc = tiktoken.encoding_for_model("gpt-4")  # close enough proxy for Claude
n = len(enc.encode(text))
```

Anthropic also exposes a `count_tokens` endpoint as of 2026 — but for offline estimation, tiktoken is accurate within ~5% for Claude.

## Implementation

### Budget config
```yaml
# requirements.yaml addition
budgets:
  phases:
    design: 8000
    plan: 12000
    implement: 4000
    review: 30000     # /deep-review spans 13 agents; needs headroom
    refactor: 16000
    ship: 4000
  agents:
    code-reviewer: 8000
    tool-validator: 2000
    silent-failure-hunter: 6000
    appsec-auditor: 12000
```

### Budget module
```python
# hooks/lib/llm/budget.py
import tiktoken
from pathlib import Path

_enc = tiktoken.encoding_for_model("gpt-4")

def count_tokens(text: str) -> int:
    return len(_enc.encode(text))

def budget_for(phase: str, agent: str | None = None) -> int:
    from hooks.lib.config import load_config
    cfg = load_config().get("budgets", {})
    if agent and agent in cfg.get("agents", {}):
        return cfg["agents"][agent]
    return cfg.get("phases", {}).get(phase, 8000)

def render_with_budget(name: str, budget: int, **vars) -> str:
    from hooks.lib.llm.templates import render
    # Try with everything first; degrade if over budget
    candidates = [vars,
                  {**vars, "examples": []},
                  {**vars, "examples": [], "retrieved": []}]
    for v in candidates:
        text = render(name, budget=budget, **v)
        if count_tokens(text) <= budget:
            return text
    raise ValueError(
        f"Prompt {name!r} exceeds budget {budget} even after degrading."
    )
```

### Hook integration
```python
# hooks/check-requirements.py — add (after existing requirement checks)
if tool_name in ("Task", "Bash") and config.get("budgets", {}).get("enforce", False):
    # For Task tool calls only — Bash budget enforcement is future work
    from hooks.lib.llm.budget import count_tokens, budget_for
    estimated = count_tokens(json.dumps(tool_input))
    phase = derive_phase(state)
    limit = budget_for(phase, agent=tool_input.get("subagent_type"))
    if estimated > limit:
        print(f"WARN: estimated prompt size {estimated} > budget {limit}", file=sys.stderr)
        # Soft mode: log and continue. Hard mode (later): block via exit code 2
```

## Example degradation

A `/deep-review` call where `code-reviewer` budget is 8000 tokens:
- First render: 14,300 tokens (too big — has 3 examples + 5 retrieval hits)
- Drop examples: 11,500 tokens (still too big)
- Drop retrieval: 6,800 tokens (under budget — use this)

Log line: `budget_degrade: code-reviewer 14300→6800 [-examples -retrieved]`

## Acceptance

- [ ] `render_with_budget("code-reviewer", budget=8000, ...)` returns under 8000 tokens for synthetic input
- [ ] Degradation logs which slots were dropped
- [ ] PreToolUse hook emits warnings (not blocks) when budgets are exceeded
- [ ] Setting `budgets.enforce: hard` makes the hook block (return exit code 2)
- [ ] Existing workflows unaffected when `budgets.enforce: false`

## Rollback

Set `budgets.enforce: false`. No code rollback needed.

## Effort

1 day

## Depends on

Step 16.

## Honest scope notes

- The tiktoken `gpt-4` encoder is not exact for Claude but is consistently within ~5%. For exact counts, call `anthropic.beta.messages.count_tokens(...)` at the cost of an API round trip.
- Budget enforcement is informational at first. After a soak period, switch to hard enforcement on selected agents.
