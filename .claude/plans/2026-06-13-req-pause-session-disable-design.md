# Design: `/req-pause` — disable framework blocking for a single session

**Date:** 2026-06-13
**Status:** APPROVED 2026-06-13 (marker mechanism = Approach A, per-session marker file)

## Problem

There is no way to disable the requirements framework for *just the current
session*. Existing escapes are either persistent (`req disable`, config
`enabled: false`), permanent/per-project (`/req-optout`), or must be set before
launch (`CLAUDE_SKIP_REQUIREMENTS` env var). The user wants an in-Claude command
to pause blocking for the live session, auto-clearing when the session ends.

## Decisions (from clarifying interview)

1. **Scope of suppression:** *Blocking gates only.* Nudges and status injection
   stay (brainstorm nudge, status banners). Suppress only the hard blocks.
2. **Interface:** A **slash command** that **auto-clears at SessionEnd**
   (`/req-pause` + `/req-resume`). Truly single-session.
3. **Strict mode:** `/req-pause` does **NOT** bypass strict-preflight (ADR-020).
   Strict's fail-closed adoption gate stays intact; `RF_STRICT_OFF` remains the
   strict-specific escape. Pause only suppresses the *normal* requirement gates.

## Mechanism

A **session-scoped marker file** keyed by session id:

```
.git/requirements/sessions/<session_id>.paused      # JSON: {paused_at, reason}
```

- Written/removed by a small primitive `req pause` / `req resume` (CLI), which
  the slash commands wrap. Session id resolved via the existing registry lookup
  (`get_session_id()` in `hooks/lib/session.py`) — Claude need not know the id.
- A new helper module `hooks/lib/pause.py` owns: `is_paused(session_id,
  project_dir)`, `set_paused(...)`, `clear_paused(...)`, `marker_path(...)`.
  Fail-open: any error → treated as *not paused* (never blocks work, never
  crashes a hook).

## What honors the marker (blocking gates ONLY)

| Hook | File(s) | Change |
|---|---|---|
| PreToolUse gate | `check-requirements.py` | After the strict-preflight gate and `is_enabled()` check, **before** the requirement loop: `if is_paused(...): return 0`. Strict stays *above* this line, so strict still blocks. |
| Stop gate | `handle-stop.py` | Before the requirement-verification block: `if is_paused(...): return 0`. |
| Auto-clear | `handle-session-end.py` | `clear_paused(session_id, project_dir)` during cleanup. |

## What stays untouched (nudges + status keep firing)

- `handle-prompt-submit.py` — brainstorm nudge + compact status.
- `handle-session-start.py` — full status injection.
- `handle-plan-enter.py` / `handle-plan-exit.py` — brainstorm auto-invoke / status.

**Visibility (safety):** while paused, the *kept* status injection in
`handle-prompt-submit.py` and `handle-session-start.py` prepends a line:
`⏸ Framework paused for this session — run /req-resume to re-enable`.
The framework is never silently off.

## Chicken-and-egg: the pause command must not be self-blocked

The `req pause` Bash invocation could itself be caught by the normal gate. Guard:
in `check-requirements.py`, after the strict gate, detect an exact `req pause` /
`req resume` CLI invocation and `return 0` (tight match, mirrors the escape-hatch
philosophy). Strict gate stays above, so under strict-non-compliant the pause is
still blocked — consistent with decision #3 (use `RF_STRICT_OFF` for strict).

## Dual-copy maintenance

Hooks live in two hand-maintained mirrors (no auto-sync):
- `hooks/` — imported by `test_requirements.py`.
- `plugins/requirements-framework/hooks/` — the runtime copy loaded via
  `--plugin-dir`.

Every hook/lib change (`check-requirements.py`, `handle-stop.py`,
`handle-session-end.py`, `handle-prompt-submit.py`, `handle-session-start.py`,
new `lib/pause.py`) must land in **both** trees. `requirements-cli.py` is
repo-only (run via the `~/.local/bin/req` symlink). Slash commands live only
under `plugins/.../commands/` (`.md` + `.md.j2`).

## Files touched

**New**
- `hooks/lib/pause.py` (+ plugin mirror)
- `plugins/requirements-framework/commands/req-pause.md` (+ `.md.j2`)
- `plugins/requirements-framework/commands/req-resume.md` (+ `.md.j2`)

**Modified**
- `hooks/check-requirements.py` (+ plugin mirror) — pause short-circuit + self-allow
- `hooks/handle-stop.py` (+ plugin mirror) — pause skip
- `hooks/handle-session-end.py` (+ plugin mirror) — clear marker
- `hooks/handle-prompt-submit.py` (+ plugin mirror) — paused status line
- `hooks/handle-session-start.py` (+ plugin mirror) — paused status line
- `hooks/requirements-cli.py` — `pause` / `resume` subcommands
- `hooks/test_requirements.py` — tests
- `plugins/requirements-framework/.claude-plugin/plugin.json` — version bump (minor)

## TDD plan

RED→GREEN in `test_requirements.py`:
1. `pause.set_paused` then `is_paused` → True; `clear_paused` → False.
2. `is_paused` fail-open: unreadable/missing marker dir → False, no raise.
3. Marker is session-scoped: session A paused does not pause session B.
4. (Integration-style) check-requirements returns allow (0) when paused with an
   otherwise-blocking requirement; still blocks under strict-non-compliant.
5. `handle-stop` does not block when paused.
6. `req pause` / `req resume` CLI write/remove the marker for the resolved session.

## Atomic commit breakdown (stg patches)

1. `feat(pause): session-pause marker lib + CLI pause/resume` (lib + CLI + tests)
2. `feat(pause): honor pause marker in PreToolUse + Stop gates` (both hooks + tests)
3. `feat(pause): auto-clear marker at SessionEnd + paused status line` (cleanup + visibility)
4. `feat(pause): /req-pause + /req-resume slash commands` (+ version bump)
5. mirror sync verification (`diff -rq` repo hooks vs plugin hooks)

## Open / non-goals

- Not a `req` CLI *user surface* by intent (interface = slash command); the CLI
  subcommands are the implementation primitive the commands wrap.
- No persistence across sessions (by design — single session only).
- Strict bypass explicitly out of scope (decision #3).
