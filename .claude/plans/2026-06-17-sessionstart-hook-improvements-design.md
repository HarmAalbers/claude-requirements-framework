# SessionStart Hook Improvements (ponytail-lens)

**Date:** 2026-06-17
**Status:** Design approved
**Scope:** `hooks/handle-session-start.py` + tests + plugin version bump

## Motivation

Comparison against the `ponytail` plugin's `ponytail-activate.js` SessionStart hook
(73 lines, single static-ruleset injection) surfaced three improvements for our
707-line dynamic-state hook. Theirs isn't apples-to-apples — it injects a constant,
ours computes per-branch/session requirement state — so the goal is applying
ponytail's YAGNI/deletion lens to *our* job, not shrinking to their size.

## Changes

### #1 — Pause-aware briefing (correctness fix)

**Problem:** `check-requirements.py:412` skips blocking when a session is paused, but
`handle-session-start.py` still injects `_GATING_DIRECTIVE` ("edits/commits are
blocked…") and the strict-preflight nag regardless of pause. A paused session is told
edits are blocked when they aren't — a direct contradiction with the visible paused
banner.

**Change:** Compute `is_paused(session_id, project_dir)` once, early (right after the
`is_enabled()` check, ~line 487). Thread a `paused: bool` flag into
`format_adaptive_status` → `format_compact_status` / `format_standard_status`.
When paused:
- Still show the paused banner + requirement status table (visibility into what is
  outstanding for when the session resumes).
- **Omit** `_GATING_DIRECTIVE`.
- **Skip** the strict-preflight warning block (current lines 686–695).

**Error handling:** `is_paused` already fail-opens to `False` (any exception → not
paused → current behavior). One extra cheap file-read on the critical path; negligible.

**Decision (user):** "Status, no 'blocked' nag" — keep status table, drop the blocked
directive + preflight nag.

### #2 — Best-effort side-effect runner (refactor, no behavior change)

**Problem:** `main()` is ~280 lines; the critical path (compute status → inject) is
buried under inline `try/except` opportunistic blocks.

**Change:** Extract the **pure fire-and-forget** blocks (session metrics,
project-registry registration, Obsidian session note — they return nothing and feed no
context) into small module-level functions, run via a tiny helper:

```python
def _best_effort(label, fn, logger):
    try:
        fn()
    except Exception as e:
        logger.debug(f"{label} failed (fail-open)", error=str(e))
```

The context-*producing* blocks (WIP summary, other-sessions warning, retrieval,
carry-over) **stay inline** — they feed `parts`, so extracting them would only add
plumbing. (Ponytail rule: no abstraction that isn't pulling weight.) Result: `main()`
shrinks, the status/inject path reads top-to-bottom, behavior identical.

**Scope guard:** structural move only — no logic changes inside any block.

### #3 — Total-failure fallback (tiny robustness)

**Problem:** if `format_adaptive_status` throws (current lines 669–670), we log and
inject *nothing* — silent. Ponytail's hook always emits a usable fallback.

**Change:** in the `except`, append a one-line fallback to `parts`:

> `## Requirements Framework active — run \`req status\` for details (briefing failed to render).`

A rendering bug degrades to a visible breadcrumb, not silence.

## Testing

Extend `hooks/test_requirements.py`:
- (a) paused session → status present, **no** gating directive, **no** preflight block;
  non-paused → directive present (regression guard).
- (b) `_best_effort` swallows exceptions and logs at debug.
- (c) status-format exception → fallback line present in injected context.

TDD: write RED tests first, `./sync.sh deploy`, run, implement, GREEN. Plugin version
bump in `plugins/requirements-framework/.claude-plugin/plugin.json` (hooks change).

## Risk

Low. #1 is the only behavior change and is behind the pause flag (default not-paused =
unchanged). #2 is a pure refactor; #3 is additive.

## Deferred (not in scope)

- Single-hook multi-host output (Codex/Copilot/Claude) — belongs to roadmap item B1.
- Statusline-missing nudge — low value (we already ship a statusline component).
