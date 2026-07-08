# Requirements Framework

A standalone requirements-management system for Claude Code that nudges (and, where you want it, enforces) a development workflow before code lands. It ships as a self-contained Claude Code **plugin**: install it once and its lifecycle hooks, `req` CLI, agents, commands, and skills come along.

## Overview

The framework lets you define workflow **gates** — design approved, plan written, plan validated, code reviewed, work verified — and have Claude Code observe them as you move through a change. Gates are satisfied by running the matching skill/command (mostly automatically) or, when needed, by hand via the `req` CLI.

**Key features**
- Typed 7-node workflow backbone (Design → Plan → Validate → Build → Review → Verify → Ship) — see ADR-022.
- Session-, branch-, permanent-, and single-use-scoped requirements.
- Three-layer config cascade (global → project → local); a local-only project is fully recognized.
- Fail-open by default: an error in a hook never blocks your work. (An opt-in strict mode inverts this — see below.)
- Plan files are whitelisted, so writing a plan is never blocked by a gate that requires the plan.
- Plugin-owned runtime: no manual hook deployment, no `sync.sh`.

## Runtime model (plugin-owned)

The framework runs entirely from the installed plugin. Hook registration is the plugin's responsibility: the single source of truth is

```
plugins/requirements-framework/hooks/hooks.json
```

which registers every lifecycle hook via `${CLAUDE_PLUGIN_ROOT}`. There is **no** copy of hooks under `~/.claude/hooks/` and **no** `sync.sh` deploy step — those are legacy. Install (or update) the plugin and the hooks are live.

### Install

```
/plugin marketplace add HarmAalbers/claude-requirements-framework
/plugin install requirements-framework@requirements-framework
```

Enable per-marketplace auto-update so pushes to `master` land at session startup.

### `uv` is required (ADR-021)

Every Python entrypoint — the `req` CLI, the hooks, and all build/test tooling — resolves its interpreter and dependencies through **`uv`** (single source of truth: `pyproject.toml` + `uv.lock`). Nothing relies on the ambient `python3`.

```bash
uv sync                                   # materialize the managed .venv
uv run python hooks/test_requirements.py  # run the test suite
uv run ruff check .                        # lint (pinned ruff, matches CI)
```

At runtime the hooks self-bootstrap: if the ambient Python lacks `PyYAML` and `uv` is on PATH, they re-exec once under `uv run --no-project --with PyYAML` (zero overhead when deps are already present).

## The workflow: typed 7-node backbone (ADR-022)

The default workflow (`WORKFLOW_DEFAULTS` in `hooks/lib/config.py`) is a typed backbone, not a flat list. Each node carries a `type` and, where relevant, a `loop` or `conditionals`.

```
Design → Plan → Validate → Build → Review → Verify → Ship
[spine] [spine] [TEAM]    [spine] [TEAM]   [spine] [spine]
                                   +loop (per commit, in Build)
```

| Node       | Type   | Gate                  | Skill / Command                                  |
|------------|--------|-----------------------|--------------------------------------------------|
| `design`   | spine  | `design_approved`     | `/brainstorming`                                 |
| `plan`     | spine  | `plan_written`        | `/writing-plans`                                 |
| `validate` | team   | `plan_validated`      | `/arch-review` *(conditional: `/codex-review`)*  |
| `build`    | spine  | `implementation_done` | `/executing-plans` *(loop: `/pre-commit` → `pre_commit_review` per commit)* |
| `review`   | team   | `pr_reviewed`         | `/deep-review` *(conditional: `/codex-review`)*  |
| `verify`   | spine  | `verified`            | `/verification-before-completion`                |
| `ship`     | spine  | — (gateless)          | `/finishing-a-development-branch`                 |

**Node types**
- **spine** nudges one skill; its gate is auto-satisfied when that skill completes.
- **team** nudges one orchestrating command that fans out its agents and satisfies exactly one gate on completion. Phase derivation walks by gate, so team-vs-spine is transparent.
- A **loop** is a `single_use` gate declared on a node (Build's `pre_commit_review`) and re-armed after each triggering command by the `clear-single-use` hook.
- **conditionals** are optional side-quests surfaced as "available here" — no gate, no auto-fire (e.g. `/codex-review`).

### Current gate vocabulary

Only these gates exist in the default backbone:

```
design_approved, plan_written, plan_validated,
implementation_done, pr_reviewed, verified
```

(plus the Build loop's `pre_commit_review`). Ship is gateless.

**Consolidated / retired gates.** Earlier versions used a larger, flatter set. These names are gone — there are **no backward-compat aliases**. A config that still names one of them produces a validation error pointing at the replacement:

| Retired gate                                        | Replacement                          |
|-----------------------------------------------------|--------------------------------------|
| `commit_plan`, `adr_reviewed`, `tdd_planned`, `solid_reviewed` | folded into `plan_validated` (Validate team) |
| `pre_pr_review`                                      | `pr_reviewed`                        |
| `pre_push_verification`                             | `verified`                           |
| `codex_reviewer`                                    | removed as a gate — now a conditional side-quest |

**YAML footgun.** Inside a `loop`, quote the trigger key (`"on": commit`); a bare `on:` parses as boolean `True` under YAML 1.1.

## Quick start

```bash
cd /your/project
req status                 # see current gate state for this session/branch
req satisfy plan_validated # mark a gate satisfied by hand (usually automatic)
```

In normal use you don't satisfy gates by hand — you run the matching skill/command and the corresponding `PostToolUse` hook auto-satisfies the gate. `req satisfy` is the manual escape hatch.

## Configuration cascade

Three layers merge, later layers winning:

1. **Global** — `~/.claude/requirements.yaml`
2. **Project** — `.claude/requirements.yaml` (version-controlled, code-reviewed)
3. **Local** — `.claude/requirements.local.yaml` (gitignored, personal overrides)

Local wins over project, which wins over global. A project that has **only** a `.claude/requirements.local.yaml` is fully recognized — the CLI and hooks treat it as configured (`project_has_config()`), so `/req-init` scaffolding a local-only file is enough.

### Example project config

```yaml
version: "1.0"
inherit: true
enabled: true

requirements:
  plan_validated:
    enabled: true
    type: blocking
    scope: session
    trigger_tools: [Edit, Write, MultiEdit]
    satisfied_by_skill: requirements-framework:arch-review
    checklist:
      - Plan reviewed against ADRs
      - SOLID principles checked
      - TDD strategy documented
      - Atomic commit boundaries planned
```

## Requirement scopes

| Scope        | Behavior                                                        |
|--------------|----------------------------------------------------------------|
| `session`    | Cleared when the Claude Code session ends.                     |
| `branch`     | Persists across sessions on the same branch.                  |
| `permanent`  | Never auto-cleared (until you clear it).                       |
| `single_use` | Cleared after its trigger command completes (loop gates re-arm). |

## Presets (`req init`)

`req init` scaffolds a config. It is context-aware and offers presets:

| Preset     | Contents                                                                                          | Use case                                         |
|------------|--------------------------------------------------------------------------------------------------|--------------------------------------------------|
| `advanced` | `plan_validated` + `protected_branch` guard + `branch_size_limit` (dynamic) + `pr_reviewed` (+ optional `github_ticket`) | Global showcase of every requirement type        |
| `strict`   | `plan_validated` (blocking, session) + `protected_branch` guard; Stop-hook verification on        | Teams wanting enforcement                        |
| `relaxed`  | `plan_validated` only (session scope)                                                             | Standalone projects / trying the framework       |
| `minimal`  | Framework enabled, no requirements                                                                | "I'll configure it myself"                        |
| `inherit`  | Empty, `inherit: true`                                                                            | Projects deferring to global config              |

**Context-aware defaults:** running `req init` in `~/.claude/` defaults to `advanced`; in a project with a global config it defaults to `inherit`; in a project without a global config it defaults to `relaxed`.

```bash
req init                    # interactive wizard
req init --yes              # non-interactive
req init --preset strict
req init --local            # write .claude/requirements.local.yaml only
req init --preview          # print config, write nothing
```

Note that `advanced` disables the deprecated `pre_commit_review` requirement — the `/pre-commit` command remains available for voluntary use and as the Build-loop skill, but is not an enforced gate.

## `req` CLI (the user interface)

```bash
req status                       # gate state for this session/branch
req satisfy <gate>               # mark a gate satisfied (manual)
req satisfy <gate> --session ID  # target an explicit session
req enable <req>                 # enable a configured requirement
req clear <gate> | req clear --all
req approve <guard>              # one-session override of a guard (e.g. protected_branch)
req list                         # tracked branches
req sessions                     # active sessions
req prune                        # clean up stale state

req logging --level debug --local          # configure logging
req messages validate [--fix]              # validate externalized messages
req upgrade scan | status | recommend      # cross-project feature adoption
req pause / req resume                      # pause/resume blocking gates (session only)
```

Some gates are safe for Claude to run itself (`req pause`, `req enable`); satisfying a gate by hand is the manual escape hatch when a skill's auto-satisfaction didn't fire.

## Checklists

Any requirement may carry an optional `checklist`. When a blocking requirement holds up an edit, the checklist renders inside the block message as a visual reminder. Checklists follow the same cascade as the rest of config — a later layer can override the whole list, and `checklist: []` removes an inherited one. Keep items short (5–10 words), actionable, and few (5–10 max).

## Auto-satisfaction (skills → gates)

Running a workflow skill or command completes its gate automatically. The `auto-satisfy-skills.py` `PostToolUse` hook maps completed skills to gates; the built-in mappings track the ADR-022 vocabulary (e.g. `/arch-review` → `plan_validated`, `/deep-review` → `pr_reviewed`). You can wire your own project skill to a requirement with `satisfied_by_skill: <skill-name>`.

## Plan-file whitelisting

Writing a plan must never be blocked by a gate that requires that plan. The PreToolUse check therefore whitelists plan paths (`~/.claude/plans/*`, `<project>/.claude/plans/*`, anything under `/.claude/plans/`) so plan authoring proceeds regardless of gate state — no chicken-and-egg deadlock.

## Fail-open by default; strict mode is opt-in

The library is **fail-open**: syntax errors, config errors, timeouts, or corrupted state are logged and the operation is allowed. A hook bug can never block your work.

An **opt-in, fail-closed strict preflight** (ADR-020) inverts this for adoption enforcement. When `strict_preflight: true` is set in the **global** config, a globally-installed plugin blocks all edits/bash in any non-compliant project until it's fixed or opted out. Compliance requires a valid local config with ≥1 enabled requirement, a structurally valid Langfuse env block (if tracing), and `uv` on PATH. It is **off by default** and inert until enabled. Escapes always take precedence: `/req-init` to scaffold, `/req-optout` to make a project inert, and the `RF_STRICT_OFF=true` emergency kill-switch.

Structured logs are written to `~/.claude/requirements.log`. Console output is silent by default and configurable per project:

```yaml
console:
  level: warning
  destinations: [stderr]
```

## Permission precedence

Claude Code applies `permissions.allow` **before** hooks:

```
permissions.allow > hooks > user approval
```

A wildcard like `Edit(*)` or `Write(*)` in `~/.claude/settings.local.json` bypasses the framework's hooks entirely. Remove such wildcards if you want gates to run.

## Session lifecycle

The plugin registers a full set of lifecycle hooks (SessionStart context injection, UserPromptSubmit nudges, PreToolUse gate checks, PostToolUse auto-satisfaction and single-use clearing, Stop-time verification, SessionEnd cleanup, plus team/idle, compaction, and observability hooks). See the top-level `CLAUDE.md` for the exhaustive hook-by-hook reference.

## Troubleshooting

**Gates not blocking**
1. Confirm the plugin is installed and enabled (`/plugin`).
2. Check for wildcard permissions in `~/.claude/settings.local.json`.
3. Confirm the project has config: `.claude/requirements.yaml` **or** `.claude/requirements.local.yaml`.
4. Confirm you're on a feature branch, not `main`/`master` (guards target protected branches).
5. Inspect `~/.claude/requirements.log`.

**Plan files still blocked** — verify the path contains `/.claude/plans/`.

**Gate won't clear / wrong session** — `req sessions` to find the session id, then `req satisfy <gate> --session <id>`.

## Further reading

- Top-level `CLAUDE.md` — full hook reference, build/test commands, and subsystem docs.
- `docs/adr/` — architecture decision records, including:
  - ADR-011 — externalized YAML messages
  - ADR-012 — agent teams integration
  - ADR-020 — strict global preflight
  - ADR-022 — typed 7-node workflow backbone (this workflow model)
- `plugins/requirements-framework/README.md` — plugin architecture (agents, commands, skills).

---

**Built for better Claude Code workflows.**
