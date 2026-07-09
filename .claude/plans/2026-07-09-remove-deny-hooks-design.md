# Design: Remove the Framework's Last Deny/Reject Hooks

**Date**: 2026-07-09 · **Branch**: `feat/nudge-by-default` · **Status**: Approved

## Motivation

With enforcement now nudge-by-default, the framework's remaining deny/reject
paths are removed whole:

1. **Dangerous-command PermissionRequest hook** (`hooks/handle-permission-request.py`)
   — auto-denies 7 Bash patterns (rm on root, force push, `git clean`, SQL
   DROP/TRUNCATE, …). Denying is its only job; Claude Code's own permission
   dialog already gates every one of these commands, and the hook's deny cannot
   carry a reason message (schema limitation). It pre-empts a dialog the user
   would see anyway.
2. **TaskCompleted hook** (`hooks/handle-task-completed.py`) — its exit-2
   empty-subject rejection is opt-in dead code (`validate_task_completion`
   defaults false everywhere). User decision: delete the *whole* hook, including
   its team_progress.log + session-metrics recording, not just the rejection
   branch.
3. **TeammateIdle hook** (`hooks/handle-teammate-idle.py`) — structural twin of
   TaskCompleted: opt-in exit-2 re-engage branch (`keep_working_on_idle`
   defaults false) plus writes to team_progress.log, which nothing ever reads
   (write-only; its only other writer is the TaskCompleted hook being deleted).
   User decision (scope expansion during brainstorm): remove it too, along with
   the **entire `agent_teams` config section**, whose only consumers are these
   two hooks.

Approach chosen: **clean delete, no replacement** (no advisory demotion, no
disabled-by-default remnant) — per the no-backwards-compat rule.

## Removal surface

| Area | Change |
|------|--------|
| Source hooks | Delete `hooks/handle-permission-request.py`, `hooks/handle-task-completed.py`, `hooks/handle-teammate-idle.py` |
| Registration | Remove `PermissionRequest` + `TaskCompleted` + `TeammateIdle` blocks from `plugins/requirements-framework/hooks/hooks.json` (hand-maintained) |
| Bundle | Delete the bundled `.py` copies; rebuild via `scripts/build_plugin_hooks.py` and verify it does not resurrect them |
| Tests | Remove `test_permission_request_hook`, `test_task_completed_hook`, `test_task_completed_normalizes_session_id` + any teammate-idle tests + `main()` registrations; triage remaining `TaskCompleted`/`TeammateIdle`/`team_progress` references in `hooks/test_requirements.py`. `test_permission_errors_fail_open` is unrelated (file permissions) — untouched. Expected-green count drops accordingly. |
| Config examples | Remove the entire `agent_teams` section (`enabled`, `keep_working_on_idle`, `validate_task_completion`) and the `permission_request` block from `examples/global-requirements.yaml` |
| Docs | README hook table + config sample, `DEVELOPMENT.md`, `docs/PLUGIN-INSTALLATION.md` hook counts/lists; ADR-012 gets a short amendment note ("runtime team hooks removed 2026-07-09"), not a rewrite |

## What deliberately stays

- The team *commands/agents* themselves (`/deep-review`, `/arch-review`, …) —
  only the runtime hooks observing team events are removed.
- Claude Code's native permission dialog as the sole safety net for dangerous
  commands.
- Session metrics in general — only the `team:*:idle` / `task_completed`
  recordings disappear.

## Packaging

Three atomic stg patches on `feat/nudge-by-default` (one per hook, each
self-contained with its registration/tests/docs; the agent_teams config-section
removal rides with the last team-hook patch). Plugin bump `4.32.0 → 4.33.0`
(minor) in the first patch that touches the bundle.

## Migration / error handling

None needed. Both paths were fail-open; unknown hook-config keys in existing
user configs are silently ignored, so stale `validate_task_completion` /
`permission_request` settings are harmless.

## Verification

- `uv run python hooks/test_requirements.py` green (adjusted count)
- `uv run ruff check .`
- `uv run python scripts/build_plugin_hooks.py` idempotent (no resurrected hooks)
- `grep -r "PermissionRequest\|TaskCompleted\|TeammateIdle\|agent_teams\|team_progress"` finds only ADR/plan history
