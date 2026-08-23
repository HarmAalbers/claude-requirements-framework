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
| `phase`    | Derived workflow phase: `design`, `plan`, `validate`, `build`, `review`, `verify`, `ship`, or `?` when outside a git repo |
| `ctx N%`   | Input-side context window usage reported by Claude Code     |
| `$cost`    | Session cost in USD                                          |
| `N req⬜`   | Count of triggered-but-unsatisfied requirements             |

The pause field reads the session-scoped marker
`<git-common-dir>/requirements/sessions/<session_id>.paused` (the same marker
`hooks/lib/pause.py` writes). The statusline normalizes the JSON `session_id`
exactly like `normalize_session_id()` — strip dashes, first 8 hex chars — so it
matches the marker key. Fail-open: any error → no pause field.

## Phase derivation

`hooks/lib/derive_phase.py` walks the ordered list of gating requirements
(the ADR-022 typed 7-node backbone in `WORKFLOW_DEFAULTS`, `hooks/lib/config.py`)
and returns the first phase whose gate is *not* satisfied:

| Phase      | Gating requirement                          | Skill/command                                                             |
|------------|---------------------------------------------|---------------------------------------------------------------------------|
| `design`   | `design_approved`                           | `/brainstorming`                                                          |
| `plan`     | `plan_written`                              | `/writing-plans`                                                         |
| `validate` | `plan_validated`                            | `/arch-review`                                                           |
| `build`    | `implementation_done`                       | `/executing-plans` (loop: `/pre-commit` → `pre_commit_review` per commit) |
| `review`   | `pr_reviewed`                               | `/deep-review`                                                           |
| `verify`   | `verified`                                  | `/verification-before-completion`                                       |
| `ship`     | *(gateless — everything above satisfied)*   | `/finishing-a-development-branch`                                        |

`ship` carries no gate, so it is transparent to derivation: the phase resolves
to `ship` only once every gate above is satisfied.

Planning is split into two phases because two skills clear the two planning
gates: `/writing-plans` flips `plan_written` (advances `plan` → `validate`),
then the `/arch-review` team flips `plan_validated` (advances `validate` →
`build`). Under ADR-022 the former four validate-phase gates
(`commit_plan` / `adr_reviewed` / `tdd_planned` / `solid_reviewed`) are
consolidated into the single `plan_validated` gate.

The statusline runs without a session ID, so a requirement counts as
"satisfied" if **any session** has satisfied it, *or* if there is a
branch-level satisfaction record. This matches the
`workflow-index` skill's definitions.

The same logic is reusable from Python: `derive_phase(Path(state_file))`.

## Performance

Warm execution runs in ~200–300ms on macOS, dominated by Python interpreter
startup (`statusline_data.py` collapses two CLI calls into one). Since ADR-024
that file also calls `_bootstrap.ensure()`, which re-execs under `uv` when the
ambient `python3` cannot import PyYAML — measured at +44ms, and skipped
entirely when PyYAML is already importable. Provisioning the interpreter the
statusline actually uses removes that cost. This is
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
    "command": "bash ~/.claude/rf-statusline.sh"
  }
}
```

That file is a launcher the installer generates. It carries no framework logic
— it reads `~/.claude/plugins/installed_plugins.json`, finds the installed
plugin and `exec`s its `statusline.sh`:

```bash
root=$(jq -r '.plugins["requirements-framework@requirements-framework"][]?.installPath // empty' \
          "$registry" 2>/dev/null |
       while IFS= read -r candidate; do
           if [ -f "$candidate/statusline.sh" ]; then printf '%s' "$candidate"; break; fi
       done)
[ -n "$root" ] && exec bash "$root/statusline.sh" "$@"
cat > /dev/null 2>&1   # not installed: render nothing rather than error
```

The indirection exists because neither obvious path works. Claude Code installs
plugins into a **version-numbered** directory
(`~/.claude/plugins/cache/requirements-framework/requirements-framework/<version>/`)
that moves on every update, so a path written at install time goes stale. And a
path into your **clone** would render whatever branch happens to be checked
out, including unfinished edits, and only works on a machine that cloned the
repo. The launcher is the one path that stays valid, because it resolves the
other two at run time.

The installer writes this when `statusLine` is absent, or when it still names
either superseded path (the old `~/.claude/plugins/<name>/` layout, or a clone).
Anything else is treated as your own statusline and left alone.

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
