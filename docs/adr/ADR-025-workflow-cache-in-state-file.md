# ADR-025: Stamp the Resolved Workflow Into the State File

**Status:** Accepted
**Date:** 2026-08-23
**Amends:** ADR-024 — same problem, better mechanism. The re-exec survives as the cache-miss fallback.

## Context

ADR-024 fixed a real defect: `statusline_data.py` ran under a bare `python3` with no PyYAML, so `derive_phase` could not read the project's `workflow:` config and silently fell back to the built-in phase order. A project that renamed its phases saw the default name in its statusline with nothing to indicate why.

It fixed it by calling `_bootstrap.ensure()`, re-execing under `uv` to obtain PyYAML. Measured cost: 35ms → 79ms per render.

ADR-024's own "Alternatives considered" section called the option below *"correct and free at render time, and genuinely the better end state"* — and then rejected it as disproportionate. That is an ADR arguing against its own conclusion. Reviewed, the rejection does not hold: 44ms was weighed against "changes the state schema", but the schema is an internal JSON file this framework owns end to end, adding a key to it is additive, and readers that do not know the key are unaffected.

The framing error was treating this as a dependency-availability problem. It is a **layering** problem. The statusline never needed the config *format* — only the resolved phase list. Parsing YAML on the read path was work in the wrong place, and ADR-024 made that work cheaper to perform rather than removing it.

## Decision

Writers stamp the resolved workflow into the JSON state file they are already writing; readers read it with stdlib `json`.

```jsonc
// .git/requirements/<branch>.json
{
  "requirements": { ... },
  "workflow_cache": {
    "phases": [ {"name": "design", "gate": "design_approved", "skill": "..."}, ... ],
    "default_phase": "design",
    "ship_phase": "ship"
  }
}
```

- **`derive_phase.build_workflow_cache(project_dir)`** projects the resolved config down to exactly the three keys `derive_phase`'s helpers read (`name`, `gate`, `skill`). A projection, not a second copy — anything broader would drift against the config silently.
- **`state_storage.save_state`** stamps it on every write. That is the single choke point for this file, and a writer is by definition a hook process that has already parsed the config, so the marginal cost is one config load on a path that just did one.
- **`derive_phase._resolve_workflow`** prefers the stamp and only falls through to the config cascade on a miss. Every field is re-validated on read: a truncated or hand-edited stamp loses to the fallback rather than driving the phase.
- **`statusline_data.py`** calls `_bootstrap.ensure()` **only on a cache miss**. ADR-024's re-exec is retained precisely where it is still needed — a fresh clone before any hook has fired — and skipped where it is not.

Measured on the real path (bare `python3`, no PyYAML, 12 renders averaged):

| | per render |
|---|---|
| before any of this work | 35 ms |
| ADR-024 (unconditional re-exec) | 79–81 ms |
| **this ADR, cache hit** | **27 ms** |
| this ADR, cache miss | 81 ms |

The cache hit beats the original baseline, because reading a stamped list skips importing `config` and walking the cascade at all — work the statusline was doing even when PyYAML *was* present.

## Consequences

- YAML is off the statusline read path. The correct phase now survives an interpreter with no PyYAML **and** a machine with no `uv` anywhere — a combination ADR-024 could not serve, since its fix depended on uv existing.
- Staleness is bounded by "the next state write", i.e. the next hook that touches requirement state — seconds in practice. A config edit is not visible in the statusline until then. This is the one genuine regression against ADR-024's always-fresh read, and it is why the miss path still resolves live.
- One extra config load per `save_state`. On a path that has already loaded config, and it buys correctness for every reader of that file.
- `hooks/test_requirements.py` covers the projection shape, malformed-stamp rejection, that `save_state` stamps, and the decisive case: the right phase from a subprocess with **no PyYAML in the interpreter and no `uv` on PATH or in `~/.local/bin`**. The complementary test pins the miss behaviour in that same bare environment.

## What ADR-024 got right

The diagnosis, the measurements, and `_find_uv`'s `~/.local/bin` probe all stand — the probe matters for every other hook entrypoint, which still re-exec unconditionally and legitimately. What it got wrong was accepting a cost it had already identified as avoidable, and burying that identification in the paragraph explaining why it would not act on it.
