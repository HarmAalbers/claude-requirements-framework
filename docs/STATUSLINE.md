# Phase-aware statusline

A one-line, always-visible status injected into Claude Code's status bar. It
turns the question "what should I do next?" into something you can *see*
instead of asking the model.

## Format

```
[⏸ paused] [phase] [ctx N%] [$cost] [N req⬜]
```

| Field      | Meaning                                                      |
|------------|--------------------------------------------------------------|
| `⏸ paused` | Shown ONLY when this session has paused the framework (`/req-pause`). Prefixes the line so the gates-off state is never silently forgotten. Absent otherwise. |
| `phase`    | Derived workflow phase: `design`, `plan-write`, `plan-validate`, `implement`, `review`, `ship`, or `?` when outside a git repo |
| `ctx N%`   | Input-side context window usage reported by Claude Code     |
| `$cost`    | Session cost in USD                                          |
| `N req⬜`   | Count of triggered-but-unsatisfied requirements             |

The pause field reads the session-scoped marker
`<git-common-dir>/requirements/sessions/<session_id>.paused` (the same marker
`hooks/lib/pause.py` writes). The statusline normalizes the JSON `session_id`
exactly like `normalize_session_id()` — strip dashes, first 8 hex chars — so it
matches the marker key. Fail-open: any error → no pause field.

## Phase derivation

`hooks/lib/derive_phase.py` walks an ordered list of gating requirements and
returns the first that is *not* satisfied:

| Phase           | Gating requirement       |
|-----------------|--------------------------|
| `design`        | `design_approved`        |
| `plan-write`    | `plan_written`           |
| `plan-validate` | `solid_reviewed`         |
| `implement`     | `verification_evidence`  |
| `review`        | `pre_pr_review`          |
| `ship`          | everything above satisfied |

Planning is split into two phases because two skills are needed to clear all planning gates: `/write-plan` flips `plan_written` (advances `plan-write` → `plan-validate`), then `/arch-review` flips `commit_plan` / `adr_reviewed` / `tdd_planned` / `solid_reviewed` together (advances `plan-validate` → `implement`).

The statusline runs without a session ID, so a requirement counts as
"satisfied" if **any session** has satisfied it, *or* if there is a
branch-level satisfaction record. This matches the
`workflow-index` skill's definitions.

The same logic is reusable from Python: `derive_phase(Path(state_file))`.

## Performance

Warm execution runs in ~200–300ms on macOS, dominated by Python interpreter
startup (`statusline_data.py` collapses two CLI calls into one). This is
below the perceptible-lag threshold for a statusline that refreshes on a
timer; it is comfortably above the aspirational 100ms target named in the
original plan. Switching to pure jq would cut runtime to ~50ms at the cost
of duplicating the phase-mapping in two languages — not worth it while the
same mapping is needed in Python for the `/req` conductor.

## Installation

`./install.sh` registers the statusline in `~/.claude/settings.json`:

```json
{
  "statusLine": {
    "type": "command",
    "command": "~/.claude/plugins/requirements-framework/statusline.sh"
  }
}
```

The installer only writes this when `statusLine` is absent — your custom
statusline, if any, is preserved.

## Customization

To use your own statusline, edit `~/.claude/settings.json` directly. The
script is plain bash and accepts the JSON Claude Code emits on stdin:

- `.workspace.current_dir` — cwd, used to find the git branch
- `.context_window.used_percentage` — context %
- `.session.cost_usd` — session cost

To extend the line (e.g., add a git-dirty marker), copy
`statusline.sh` to your own location, modify it, and point the
`command` at your copy.

## Failure modes

The script is fail-open: any error degrades a single field to `?` rather
than failing the whole line. If you see `[?]` somewhere unexpectedly:

| Symptom                | Likely cause                                |
|------------------------|---------------------------------------------|
| `[? req⬜]`             | Outside a git repo, or no `.git/requirements/` state |
| `[design]` always      | `derive_phase.py` couldn't read the state file |
| Blank statusline       | `jq` or `python3` missing on `$PATH`        |

## Related

- `hooks/lib/derive_phase.py` — pure function returning the phase name
- `hooks/lib/count_unsatisfied.py` — pure function returning the count
- `hooks/lib/statusline_data.py` — combined CLI used by `statusline.sh`
- `plugins/requirements-framework/skills/workflow-index/SKILL.md` — the
  human-readable map of phases the model uses when guiding the user
