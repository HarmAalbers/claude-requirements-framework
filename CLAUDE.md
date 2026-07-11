# CLAUDE.md

Operational essentials for Claude Code in this repo. Deep detail lives in `DEVELOPMENT.md`, `docs/adr/`, and `plugins/requirements-framework/README.md` — this file stays short on purpose.

## Session Handoff — check FIRST every session

Before anything else, check whether `.claude/handoff.md` exists (gitignored, written by a prior session). If present:

1. Read it in full.
2. Summarize in 2–3 lines: where the prior session stopped + the proposed next step + named alternatives.
3. Ask the user whether to proceed, pick an alternative, or do something else. Do **not** auto-execute.
4. After the user decides, MOVE it to `.claude/handoff.archive/<YYYY-MM-DD-HHMMSS>.md` (`mkdir -p` first) so it never re-prompts — unless the user says "leave it for later."

If absent, don't mention this convention. To hand off to the next session, write `.claude/handoff.md`.

## Version Control: Stacked Git (`stg`)

All local commits go through Stacked Git — **never `git commit` directly**. `stg init` is per-branch (`master` is done; every new branch needs its own).

```bash
git checkout -b feat/your-branch && stg init
stg new <patch-name>     # create an empty patch (use -m "msg" to skip the editor)
# ...edit files...
stg refresh              # fold working-tree changes into the top patch (iterate)
stg new <next-patch>     # start the next atomic patch
```

Common ops: `stg series` (list), `stg show` (top diff), `stg pop`/`stg push`, `stg edit <patch>`, `stg rename`. `git push` works unchanged (patches are ordinary commits).

Rules:
- **Never `git commit`** — always `stg new` + `stg refresh`.
- **One logical change per patch**; do framework work on a **topic branch**, not `master` (gates are per-branch).
- Any change under `plugins/requirements-framework/` must bump `plugins/requirements-framework/.claude-plugin/plugin.json` (semver) in the **same** patch.
- Don't `stg repair` after a raw merge — it can reset the master ref to an ancient commit.

## Build & Test

`uv` is required — every Python entrypoint (the `req` CLI, hooks, tooling) resolves its interpreter + deps through `uv` (`pyproject.toml` + `uv.lock` are the single source of truth). Nothing relies on ambient `python3`.

```bash
uv sync                                          # materialize .venv (PyYAML + dev group: pydantic, jinja2, ruff)
uv run python hooks/test_requirements.py         # test suite
uv run ruff check .                              # lint (pinned, matches CI)
uv run python scripts/render_prompts.py --check  # verify .md.j2 → .md renders
uv run python scripts/build_plugin_hooks.py      # rebuild the plugin bundle (a build-copy)
```

- Hooks/CLI self-bootstrap: if ambient python lacks PyYAML and `uv` is on PATH, `hooks/lib/_bootstrap.py` re-execs once under `uv run --no-project --with PyYAML`.
- 5 pre-existing test failures (the config validation-error group) are **local-environment-only** — they pass in CI, which requires a full `1488/1488`. A green local run reports `1483/1488`.
- CI runs `ruff check .` (pinned) which the local test harness does not — lint can fail CI while tests pass locally.

> **Runtime**: hooks fire via the **plugin** (installed marketplace build, or a `--plugin-dir` dev build for this repo), not a `~/.claude/hooks` deploy. `plugins/requirements-framework/hooks/hooks.json` owns hook registration. The old `sync.sh` two-location model has been removed.

## Configuration Cascade

`~/.claude/requirements.yaml` (global) → `.claude/requirements.yaml` (project, versioned) → `.claude/requirements.local.yaml` (local, gitignored). Deep-merged; local wins. A project with only a `.local.yaml` is still recognized.

## Requirement Scopes

| Scope | Behavior |
|-------|----------|
| `session` | Cleared when the session ends |
| `branch` | Persists across sessions on the same branch |
| `permanent` | Never auto-cleared |
| `single_use` | Cleared after the trigger command completes |

## Workflow Phase Backbone (typed 7-node — ADR-022)

The default workflow (`WORKFLOW_DEFAULTS` in `hooks/lib/config.py`) is a typed 7-node backbone:

```
Design → Plan → Validate → Build → Review → Verify → Ship
[spine] [spine] [TEAM]    [spine] [TEAM]   [spine] [spine]
```

| Node | Type | Gate | Skill / Command |
|------|------|------|-----------------|
| design   | spine | `design_approved`     | `/brainstorming` |
| plan     | spine | `plan_written`        | `/writing-plans` |
| validate | team  | `plan_validated`      | `/arch-review` *(cond: `/codex-review`)* |
| build    | spine | `implementation_done` | `/executing-plans` *(loop: `/pre-commit` → `pre_commit_review` per commit)* |
| review   | team  | `pr_reviewed`         | `/deep-review` *(cond: `/codex-review`)* |
| verify   | spine | `verified`            | `/verification-before-completion` |
| ship     | spine | — (gateless)          | `/finishing-a-development-branch` |

- **spine** nudges one skill (its gate auto-satisfied by that skill); **team** nudges an orchestrating command that fans out agents and satisfies one gate; a **loop** is a `single_use` gate re-armed by `clear-single-use`; **conditionals** are optional side-quests (no gate, no auto-fire).
- Gate vocabulary consolidated ~11 → 7 (ADR-022). No compat shims — a config naming an old gate errors and points at the new name.
- YAML footgun: in a `loop`, quote the trigger key (`"on": commit`) — a bare `on:` parses as boolean `True` under YAML 1.1.
- Skill auto-satisfactions are **per-branch** — run workflow skills *after* `git checkout -b`, else the new branch re-blocks.

## Development Principles

- **Fail-open**: an error in a hook never blocks work (the sole exception is strict preflight, ADR-020, opt-in).
- **TDD**: add tests to `hooks/test_requirements.py` first (RED), implement (GREEN), then commit.
- **Strategy pattern**: requirement types are modular strategies (`hooks/lib/*_strategy.py`).
- **No backwards-compat shims**: delete old config keys/features cleanly, don't keep deprecated aliases.

## Deeper Documentation

- `DEVELOPMENT.md` — comprehensive development guide (hooks lifecycle, lib modules, internals).
- `plugins/requirements-framework/README.md` — the 24 agents / 15 commands / 21 skills.
- `docs/adr/` — design records. Load-bearing ones:
  - ADR-011 message externalization · ADR-012 agent teams · ADR-014 refactor orchestration
  - ADR-019 Stop-hook observability (Langfuse) · ADR-020 strict global preflight · ADR-022 workflow backbone
- **Opt-in features** (off by default; details in their ADR / `DEVELOPMENT.md`): Langfuse tracing (ADR-019), strict global preflight (ADR-020), Obsidian session logging, session learning (`/session-reflect`), cross-project upgrade (`req upgrade`), message externalization (`req messages`, ADR-011), refactor orchestration (`/refactor-orchestrate`, ADR-014), Serena MCP, `ENABLE_TOOL_SEARCH`.
