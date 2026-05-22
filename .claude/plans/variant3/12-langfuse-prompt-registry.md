# Step 12 — Mirror first prompt to Langfuse registry

## Goal

Take ONE agent prompt (the `code-reviewer.txt` from Step 10) and mirror it to Langfuse's Prompt Management. Tag, version, and rollback are now first-class. Other prompts stay file-based until Step 16.

## Why this one

The pilot agent should also be the pilot prompt. Proves the registry → loader → render path on a single asset before scaling.

## Files touched

- `hooks/lib/llm/prompts.py` (new — PromptLoader)
- `scripts/sync_prompts_to_langfuse.py` (new — one-shot mirror)
- `hooks/lib/llm/workers/code_reviewer.py` — read prompt from PromptLoader instead of disk

## Validated APIs

From [Langfuse prompt management docs](https://langfuse.com/docs/prompts/get-started):

```python
from langfuse import Langfuse

langfuse = Langfuse()

# Create
langfuse.create_prompt(
    name="code-reviewer",
    type="text",
    prompt="Review the following diff: {{ diff }}",
    labels=["production"],
    config={"model": "claude-sonnet-4-6", "temperature": 0.0},
)

# Fetch (cached by default; refresh every ~60s)
prompt_obj = langfuse.get_prompt("code-reviewer", label="production")
compiled = prompt_obj.compile(diff="...")
```

The `prompt_obj.compile()` call expands `{{ var }}` placeholders. For Jinja2-style logic (loops, conditionals) we add a `prompt_type="chat"` and use a custom renderer (Step 16).

## Implementation

### PromptLoader
```python
# hooks/lib/llm/prompts.py
"""Two-tier prompt loader: Langfuse first, file fallback."""
import os
from pathlib import Path
from functools import lru_cache

try:
    from langfuse import Langfuse
    _langfuse = Langfuse() if os.getenv("LANGFUSE_PUBLIC_KEY") else None
except ImportError:
    _langfuse = None

_FILE_ROOT = Path(__file__).parent / "prompts"


@lru_cache(maxsize=32)
def load_prompt(name: str, label: str = "production") -> str:
    """Return the raw prompt text for the given name. Cached for 60s by Langfuse."""
    if _langfuse:
        try:
            return _langfuse.get_prompt(name, label=label).prompt
        except Exception:
            pass  # fall through to file
    return (_FILE_ROOT / f"{name}.txt").read_text()
```

### Sync script
```python
# scripts/sync_prompts_to_langfuse.py
"""One-shot: read prompts/*.txt and create them in Langfuse with labels."""
from pathlib import Path
from langfuse import Langfuse

lf = Langfuse()
for p in Path("hooks/lib/llm/prompts").glob("*.txt"):
    lf.create_prompt(
        name=p.stem,
        type="text",
        prompt=p.read_text(),
        labels=["production"],
    )
    print(f"synced: {p.stem}")
```

### Wire the wrapper
```python
# hooks/lib/llm/workers/code_reviewer.py — change one line
from hooks.lib.llm.prompts import load_prompt
_PROMPT_TEMPLATE = load_prompt("code-reviewer")  # was: file read
```

## Example workflow

1. Author edits `prompts/code-reviewer.txt` in git → commit
2. CI runs `python scripts/sync_prompts_to_langfuse.py` → new version in Langfuse
3. Production label still points at the previous version
4. Promote in Langfuse UI when ready → next `load_prompt` cache miss picks it up

## Acceptance

- [x] `langfuse.get_prompt("code-reviewer", label="production").prompt` matches the file content — proved by `tests/test_prompts.py::test_langfuse_path_when_client_available` (mocked) + `v3_prompt_loader_smoke.py` Step 2 (live)
- [x] If Langfuse is unreachable, `load_prompt` falls back to file silently — proved by `test_langfuse_exception_falls_back_to_file` and `test_langfuse_disabled_when_keys_missing` / `test_langfuse_disabled_when_import_fails`
- [x] Editing the file and re-syncing creates a new Langfuse version (visible in UI) — `scripts/sync_prompts_to_langfuse.py` calls `lf.create_prompt(...)` per file; Langfuse's own dedup-on-content semantics produce new versions only when text changes
- [x] Rollback in Langfuse UI (label switch) takes effect within cache TTL (~60s) — preserved by NOT wrapping `load_prompt` in `lru_cache` (deviation from original plan; see `prompts.py` design notes)

## Landing notes (2026-05-22)

Step 12 landed as **3 stacked stg patches** on `refactor/step-08-llm-package-scaffold`:

1. `step-12-prompt-loader` — new `hooks/lib/llm/prompts.py` + extracted `prompts/{code-reviewer,review-aggregator}.txt` + 12 tests
2. `step-12-wire-workers` — workers call `load_prompt(name).format(...)` instead of holding inline constants (-42/+4 lines)
3. `step-12-sync-script-and-smoke` — `scripts/sync_prompts_to_langfuse.py` + `_spikes/v3_prompt_loader_smoke.py` + README entry

Deviations from this plan as originally written:
- **Two prompts mirrored** instead of one — Step 10 shipped both code-reviewer and aggregator; both became registry candidates.
- **`lru_cache` removed** — the plan literally specified `@lru_cache(maxsize=32)` but that defeats Langfuse's own ~60s TTL refresh and breaks Acceptance #4.
- **Lazy singleton client** — replaces the plan's eager module-level `Langfuse() if os.getenv(...)` construction, so dotenv-loaded keys still work and constructor exceptions don't kill imports.

1407/1407 tests pass (12 new prompts + 1290 framework + 105 other V3).

## Rollback

- Switch `load_prompt` to always read from file (one-line config flag)
- Or delete the Langfuse prompt — the loader falls back to file

## Effort

0.5 day

## Depends on

Step 11.

## Honest scope note

Langfuse prompt management supports JSON-typed chat prompts. The text-typed form used here is the simplest. Step 16 introduces Jinja2 rendering on top.
