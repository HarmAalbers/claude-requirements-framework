# Development Workflow

This document explains how to develop, test, and maintain the Claude Code Requirements Framework.

## Architecture Overview

### The plugin is the runtime

Hooks fire through the **self-contained plugin**, not through a deployed copy under
`~/.claude/hooks/`. Hook registration lives in a single source of truth:

```
plugins/requirements-framework/hooks/hooks.json
```

Every entry resolves its script via `${CLAUDE_PLUGIN_ROOT}` (e.g.
`${CLAUDE_PLUGIN_ROOT}/hooks/check-requirements.py`). **Installing the plugin is what
activates the hooks.** There is no separate deployed runtime directory that Claude Code
loads hooks from.

> **Legacy note:** older docs described a "two-location system" — a git repo that synced to
> `~/.claude/hooks/` via a `sync.sh` script. That flow and the `sync.sh` script have been
> **removed**. There is no `~/.claude/hooks/` runtime directory; the plugin is the only runtime.

### What `install.sh` does (and does not do)

`install.sh` **only**:
- runs `uv sync` to materialize the dev environment,
- symlinks the `req` CLI (`hooks/requirements-cli.py` → `~/.local/bin/req`),
- sets up the statusline, and
- offers to add `export ENABLE_TOOL_SEARCH=true` to your shell rc (idempotent).

It does **not** copy hook scripts into `~/.claude/hooks/` and does **not** write a `hooks`
block into `~/.claude/settings.json`. To activate lifecycle hooks, install the plugin.

### uv is required (ADR-021)

Every Python entrypoint — the `req` CLI, the lifecycle hooks, and all build/test tooling —
resolves its interpreter and dependencies through **`uv`**. The single source of truth is
`pyproject.toml` + `uv.lock`. Nothing relies on the ambient `python3`.

```bash
# One-time: sync the uv-managed environment (core PyYAML + dev group: pydantic, jinja2, ruff)
uv sync

# The heavy [llm] extra is opt-in
uv sync --extra llm
```

At runtime the hooks and CLI **self-bootstrap**: if the ambient python lacks `PyYAML` and
`uv` is on PATH, `hooks/lib/_bootstrap.py` re-execs the process once under
`uv run --no-project --with PyYAML`. When deps are already present this is zero overhead.

**Always run tooling via `uv run`** so the synced env is guaranteed. Never invoke a bare
`python3` for framework tooling.

## Development Workflow

Edit in the repository, run tests via `uv`, and use Stacked Git for atomic commits.

```bash
# 1. Make changes in the repository
cd ~/Tools/claude-requirements-framework
$EDITOR hooks/lib/config.py   # or any file

# 2. Run the test suite (uv-managed interpreter)
uv run python hooks/test_requirements.py

# 3. Lint (pinned ruff, matches CI)
uv run ruff check .

# 4. Commit atomically via Stacked Git (see below)
stg new my-change
stg refresh
```

### Version control: Stacked Git (`stg`)

This project uses **Stacked Git** for all local commit authoring — **never `git commit`
directly**. `stg init` is per-branch (`master` is already initialized); every new topic
branch needs its own `stg init`.

```bash
git checkout -b feat/your-branch
stg init

stg new <patch-name>   # create an empty patch (opens editor for the description)
# ... edit files ...
stg refresh            # fold working-tree changes into the top patch
stg new <next-patch>   # start the next logical patch on top
```

| Task                         | Command                  |
|------------------------------|--------------------------|
| List patch stack             | `stg series`             |
| Show top patch diff          | `stg show`               |
| Pop top patch (keep changes) | `stg pop`                |
| Re-apply popped patch        | `stg push`               |
| Amend a non-top patch        | `stg edit <patch>`       |
| Rename a patch               | `stg rename <old> <new>` |
| Delete a patch               | `stg delete <patch>`     |

`git push` works unchanged — stg patches are ordinary git commits. Keep patches atomic
(one logical change each), and when a patch touches plugin files, bump
`plugins/requirements-framework/.claude-plugin/plugin.json` **inside the same patch**.

### Test-Driven Development

```bash
# 1. Write tests in the repository
$EDITOR hooks/test_requirements.py

# 2. Run tests (RED — should fail)
uv run python hooks/test_requirements.py

# 3. Implement the feature
$EDITOR hooks/lib/requirements.py

# 4. Run tests (GREEN — should pass)
uv run python hooks/test_requirements.py

# 5. Commit via stg once green
```

## The Workflow Backbone (ADR-022, typed 7-node)

The default workflow (`WORKFLOW_DEFAULTS` in `hooks/lib/config.py`) is a **typed 7-node
backbone**, not a flat checklist. Each node carries a `type` and, where relevant, a `loop`
or `conditionals`.

```
Design → Plan → Validate → Build → Review → Verify → Ship
[spine] [spine] [TEAM]    [spine] [TEAM]   [spine] [spine]
                                   +loop (in Build)
```

| Node     | Type  | Gate                  | Skill / Command                          |
|----------|-------|-----------------------|------------------------------------------|
| design   | spine | `design_approved`     | `/brainstorming`                         |
| plan     | spine | `plan_written`        | `/writing-plans`                         |
| validate | team  | `plan_validated`      | `/arch-review` *(cond: `/codex-review`)* |
| build    | spine | `implementation_done` | `/executing-plans` *(loop: `/pre-commit` → `pre_commit_review` per commit)* |
| review   | team  | `pr_reviewed`         | `/deep-review` *(cond: `/codex-review`)* |
| verify   | spine | `verified`            | `/verification-before-completion`        |
| ship     | spine | — (gateless)          | `/finishing-a-development-branch`         |

- **spine** nodes nudge one skill; the gate is auto-satisfied when that skill completes.
- **team** nodes nudge one orchestrating command that fans out its agents and satisfies
  ONE gate on completion.
- A **loop** is a `single_use` gate declared on a node and re-armed by `clear-single-use`
  (Build re-arms `pre_commit_review` on every commit).
- **conditionals** are optional side-quests surfaced as "available here" — no gate, no
  auto-fire.

### Current gate vocabulary

The live gates are exactly:

```
design_approved  plan_written  plan_validated  implementation_done  pr_reviewed  verified
```

(`ship` is gateless.)

The old gates `commit_plan`, `adr_reviewed`, `tdd_planned`, `solid_reviewed`,
`pre_pr_review`, `pre_push_verification`, and `codex_reviewer` are **retired** — folded
into the 7-node set (e.g. the four plan-time gates collapsed into `plan_validated`;
`pre_pr_review` → `pr_reviewed`; `pre_push_verification` → `verified`; `codex_reviewer` is
now a conditional side-quest, not a gate). There are **no compat shims**: a config that
still names an old gate gets a validation error pointing at the new name.

### Auto-satisfaction mappings

`hooks/auto-satisfy-skills.py` maps completed skills/commands to the gate they satisfy:

| Skill / command                          | Gate satisfied        |
|------------------------------------------|-----------------------|
| `brainstorming`                          | `design_approved`     |
| `writing-plans`                          | `plan_written`        |
| `arch-review`                            | `plan_validated`      |
| `executing-plans`                        | `implementation_done` |
| `pre-commit` / `requesting-code-review`  | `pre_commit_review`   |
| `deep-review` / `v3-review`              | `pr_reviewed`         |
| `verification-before-completion`         | `verified`            |

> **YAML footgun:** in a `loop`, quote the trigger key (`"on": commit`) — a bare `on:`
> parses as boolean `True` under YAML 1.1.

## Configuration Cascade

Config is merged across three layers, local winning:

1. **Global**: `~/.claude/requirements.yaml`
2. **Project**: `.claude/requirements.yaml` (version controlled)
3. **Local**: `.claude/requirements.local.yaml` (gitignored — highest priority)

### Requirement scopes

| Scope        | Behavior                                            |
|--------------|-----------------------------------------------------|
| `session`    | Cleared when the Claude Code session ends           |
| `branch`     | Persists across sessions on the same branch         |
| `permanent`  | Never auto-cleared                                  |
| `single_use` | Cleared after the trigger command completes         |

### Requirement types (strategy pattern)

Requirement behavior is dispatched through a strategy registry. The three types are
`blocking`, `dynamic`, and `guard` (see ADR-004 for guard). See the File Structure section
for the concrete strategy modules.

## File Structure

```
~/Tools/claude-requirements-framework/
├── hooks/                              # Source of truth for all hook scripts + the CLI
│   ├── check-requirements.py          # PreToolUse: requirement enforcement
│   ├── handle-session-start.py        # SessionStart: context injection, registry
│   ├── handle-prompt-submit.py        # UserPromptSubmit: compact status, brainstorm nudge
│   ├── handle-plan-enter.py           # PostToolUse(EnterPlanMode): brainstorm auto-invoke
│   ├── handle-plan-exit.py            # PostToolUse(ExitPlanMode): status surfacing
│   ├── auto-satisfy-skills.py         # PostToolUse(Skill): auto-satisfy gates
│   ├── clear-single-use.py            # PostToolUse: clear/re-arm single_use gates
│   ├── handle-git-events.py           # PostToolUse: WIP git metrics tracking
│   ├── handle-tool-failure.py         # PostToolUseFailure: failure pattern tracking
│   ├── handle-subagent-start.py       # SubagentStart: review-agent context injection
│   ├── handle-pre-compact.py          # PreCompact: save state before compaction
│   ├── handle-stop.py                 # Stop: requirement verification
│   ├── handle-session-end.py          # SessionEnd: registry cleanup
│   ├── handle-teammate-idle.py        # TeammateIdle: team progress (ADR-012)
│   ├── handle-task-completed.py       # TaskCompleted: team task gates (ADR-012)
│   ├── langfuse-trace.py              # Stop-hook Langfuse wrapper (ADR-019)
│   ├── _langfuse_hook.py              # VENDORED upstream Langfuse hook
│   ├── requirements-cli.py            # `req` command implementation
│   ├── test_requirements.py           # Main test suite
│   ├── test_branch_size_calculator.py # Branch-size calculator tests
│   ├── test_diff_scope.py             # Diff-scope tests
│   └── lib/                           # Core library
│       ├── _bootstrap.py              # uv self-bootstrap (re-exec under uv run)
│       ├── requirements.py            # Core BranchRequirements API
│       ├── config.py                  # Config cascade + WORKFLOW_DEFAULTS
│       ├── state_storage.py           # JSON state in .git/requirements/[branch].json
│       ├── session.py                 # Session tracking
│       ├── registry_client.py         # Session registry client
│       ├── project_registry.py        # Cross-project registry (req upgrade)
│       ├── feature_catalog.py         # Feature catalog (req upgrade)
│       ├── derive_phase.py            # Phase derivation from gate state
│       ├── count_unsatisfied.py       # Unsatisfied-gate counting
│       ├── plan_evidence.py           # Plan evidence tracking
│       ├── preflight.py               # Strict global preflight (ADR-020)
│       ├── pause.py                   # req pause/resume
│       ├── ruleset_marker.py          # Ruleset markers
│       ├── wip_tracker.py             # WIP tracking
│       ├── statusline_data.py         # Statusline data provider
│       ├── brainstorm.py              # Brainstorm nudge logic
│       ├── strategy_registry.py       # Strategy dispatch
│       ├── base_strategy.py           # Abstract strategy base
│       ├── blocking_strategy.py       # Blocking requirement type
│       ├── dynamic_strategy.py        # Dynamic requirement type
│       ├── guard_strategy.py          # Guard requirement type (ADR-004)
│       ├── strategy_utils.py          # Strategy helpers
│       ├── branch_size_calculator.py  # Branch diff size
│       ├── calculation_cache.py       # Calculation caching
│       ├── calculator_interface.py    # Calculator abstraction
│       ├── message_dedup_cache.py     # TTL dedup for parallel calls
│       ├── messages.py                # MessageLoader (ADR-011)
│       ├── message_validator.py       # Message validation
│       ├── git_utils.py               # Git utilities
│       ├── config_utils.py            # Config helpers
│       ├── hook_utils.py              # Shared hook helpers
│       ├── colors.py / console.py     # CLI output
│       ├── logger.py                  # Structured JSON logging
│       ├── progress.py                # Progress/timing instrumentation
│       ├── interactive.py             # Interactive prompts
│       ├── feature_selector.py        # Feature selection
│       ├── init_presets.py            # Init presets
│       ├── session_metrics.py         # Session metrics collection
│       ├── learning_updates.py        # Learning updates + rollback
│       ├── obsidian.py                # Obsidian CLI integration
│       ├── diff_scope.py              # Diff-scope computation for review agents
│       ├── llm/                       # V3 SDK review stack (opt-in [llm] extra)
│       │   ├── claude.py, budget.py, embedder.py, eval.py, memory.py
│       │   ├── observability.py, prompts/ (runtime templates + partials/)
│       └── lazy_dev/                  # Ruleset (rules.py, RULESET.md)
├── plugins/requirements-framework/    # The self-contained plugin (runtime)
│   ├── .claude-plugin/plugin.json     # Plugin manifest (version lives here)
│   ├── hooks/                         # BUILD-COPY of hooks/ + hooks.json (registration)
│   ├── agents/                        # 24 agents (<name>.md.j2 + rendered <name>.md)
│   ├── commands/                      # 16 commands (.md.j2 + .md)
│   └── skills/                        # 21 skills (<name>/SKILL.md)
├── scripts/                           # Build & ops tooling
│   ├── build_plugin_hooks.py          # Rebuild plugin hooks/ from hooks/
│   ├── render_prompts.py              # Render plugin .md.j2 → .md
│   ├── pre-commit-check.sh            # Optional stale-render guard
│   ├── setup_langfuse_tracing.py      # Langfuse opt-in (ADR-019)
│   ├── sync_langfuse_models.py        # Model-price registry
│   ├── sync_prompts_to_langfuse.py    # Prompt sync
│   ├── sync_golden_set_to_langfuse.py # Eval golden-set sync
│   ├── run_eval.py                    # V3 eval runner
│   └── bootstrap_qdrant.py            # Qdrant bootstrap (retrieval)
├── tests/                             # Pytest-style tests (render, partials, diff-scope)
├── examples/                          # Example config files
├── docs/adr/                          # Architecture Decision Records
├── install.sh                         # Sets up req CLI, statusline, shell env, uv sync
└── README.md
```

## Plugin Bundle (build-copy)

`plugins/requirements-framework/hooks/` is a **build-copy** of the repo-root `hooks/`
directory. It is generated, not hand-edited. After changing anything under `hooks/`,
rebuild the bundle:

```bash
# Rebuild the plugin's hooks/ from the source hooks/
uv run python scripts/build_plugin_hooks.py

# Check for drift (CI-style; non-zero exit if out of date)
uv run python scripts/build_plugin_hooks.py --check
```

`requirements-cli.py` IS bundled. Do not edit the copy under
`plugins/requirements-framework/hooks/` directly — edit `hooks/` and rebuild.

## Plugin Prompt Authoring (.md.j2 → .md)

Every dispatched plugin prompt — **24 agents**, **16 commands**, and **21 skills** — uses a
two-file pattern:

| File           | Role                                                        | Edit it?             |
|----------------|-------------------------------------------------------------|----------------------|
| `<name>.md.j2` | Jinja2 source of truth — frontmatter + body + `{% include %}` | **Yes**              |
| `<name>.md`    | Rendered output dispatched at runtime                       | **No** — build artifact |

The invariant "every dispatched plugin `.md` has a `.md.j2` source" is enforced by
`tests/test_render_prompts.py::test_all_plugin_md_files_have_j2_source`. (The three
refactor-orchestration template files are explicitly excluded — they are skill-internal
scaffolding read at runtime, not dispatched prompts.)

### Author flow

1. **Edit `<name>.md.j2`** (the source). Use `{% include 'partials/<name>.j2' %}` to pull
   in shared kernels — currently only `diff_scope_load.j2` qualifies (the diff-scope review
   agents share its byte-identical `prepare-diff-scope` boilerplate).
2. **Render**: `uv run python scripts/render_prompts.py` — writes each `<name>.md` sibling.
   Idempotent; only writes when content changes.
3. **Verify freshness**: `uv run python scripts/render_prompts.py --check` — exit 0 means
   every `.md` matches its source.
4. **Commit both files** (`.md.j2` and `.md`) atomically in the same patch.

### Optional pre-commit render guard

```bash
ln -sf ../../scripts/pre-commit-check.sh .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit
```

The hook runs `render_prompts.py --check` and aborts a commit whose `.md` siblings are
stale, printing the exact remediation command.

### Partials and the loader-root boundary

Partials live under `hooks/lib/llm/prompts/partials/`. Author a new partial only when the
kernel is **byte-identical** across **multiple** templates — never normalize substantive
text to fit a partial. Both the build-time path (`render_prompts.py`) and the runtime
worker path delegate to the same `hooks.lib.llm.templates.render()` function (a module-level
Jinja `Environment` with `FileSystemLoader(hooks/lib/llm/prompts/)`), so `{% include %}`
resolves identically in both.

Plugin `.md.j2` files **cannot** reference runtime variables (`{{ scope }}`, `{% if %}`) —
they render with zero caller context and would crash on `StrictUndefined`. This is enforced
by `tests/test_render_prompts.py::test_plugin_templates_have_no_runtime_vars`. Templates
that genuinely need runtime variables belong under `hooks/lib/llm/prompts/` instead, where
`load_prompt(name, **vars)` resolves them.

## Plugin Component Versioning

All plugin components (agents, commands, skills) carry a `git_hash` field in their YAML
frontmatter showing the last commit that modified the file.

```bash
./update-plugin-versions.sh           # update all git_hash fields
./update-plugin-versions.sh --check   # dry-run (show what would change)
./update-plugin-versions.sh --verify  # verify hashes are current
```

Hash format: `abc1234` (committed clean), `abc1234*` (committed + uncommitted changes),
`uncommitted` (new file). Keep the `git_hash` churn in its own chore patch.

> **Version bump rule:** every change to the plugin (agents, commands, skills, hooks,
> `plugin.json`) must bump the version in
> `plugins/requirements-framework/.claude-plugin/plugin.json` (semver: patch for fixes,
> minor for features, major for breaking). The current version lives in `plugins/requirements-framework/.claude-plugin/plugin.json`.

## Testing

### Unit tests

```bash
# Run the main suite via the uv-managed interpreter
uv run python hooks/test_requirements.py
```

A green run reports **`1544/1551`**. The **7 remaining failures are pre-existing and
environment-independent** — treat that count as green, not as a regression.

Other suites:

```bash
uv run python hooks/test_branch_size_calculator.py
uv run python hooks/test_diff_scope.py
# Pytest-style suites under tests/ (render, partials, diff-scope)
uv run python -m pytest tests/
```

### Lint

```bash
uv run ruff check .   # pinned ruff, matches CI
```

CI runs `ruff check .` (pinned) in addition to the test suite — lint can fail CI even when
tests pass locally, so run it before pushing.

### Integration testing

Test hooks in a real Claude Code session with the plugin installed. For development, load
the plugin directly from the repo for live reload:

```bash
claude --plugin-dir ~/Tools/claude-requirements-framework/plugin
```

Then, in a project that enables the framework:

```bash
cd ~/some-project
git checkout -b test/hook-testing
# Try to edit a file — a blocking gate should stop it
# Satisfy the gate, then retry:
req satisfy plan_validated
```

## Message Externalization (ADR-011)

Framework messages live in external YAML files with the same cascade as config
(local > project > global):

```
~/.claude/messages/                    # global defaults
<project>/.claude/messages/            # project-specific (version controlled)
<project>/.claude/messages.local/      # local overrides (gitignored)
```

Each requirement's message file has six required fields (`blocking_message`,
`short_message`, `success_message`, `header`, `action_label`, `fallback_text`) plus
`version`. Special files: `_templates.yaml` (defaults by type) and `_status.yaml` (status
briefing formats).

```bash
req messages validate         # validate all message files
req messages validate --fix    # generate missing files from templates
req messages list              # list files with cascade sources
```

Core implementation: `hooks/lib/messages.py` (MessageLoader) and
`hooks/lib/message_validator.py`. See ADR-011 for design rationale.

## Message Deduplication

When Claude issues parallel Write/Edit calls, the same blocking gate can fire many times.
`hooks/lib/message_dedup_cache.py` shows the full message on first occurrence and a compact
"waiting…" indicator for subsequent blocks within a short TTL. Enable debug tracing with
`CLAUDE_DEDUP_DEBUG=1`.

## The `req` CLI

```bash
req status                     # requirement status for the current project/branch
req satisfy <gate>             # manually satisfy a gate
req enable <name>              # enable a requirement
req logging --level debug --local
req messages validate
req upgrade scan | status | recommend   # cross-project feature adoption (ADR-010)
req learning stats | list | rollback N  # session learning
req pause | resume             # pause/resume blocking gates for the session
```

## Contributing

1. Fork and clone.
2. `uv sync` (installer: `./install.sh`).
3. Create a topic branch and `stg init`.
4. Make changes in `hooks/` (source of truth); rebuild the plugin bundle
   (`uv run python scripts/build_plugin_hooks.py`) and render prompts
   (`uv run python scripts/render_prompts.py`) if you touched them.
5. Test and lint:
   `uv run python hooks/test_requirements.py && uv run ruff check .`
6. Bump `plugin.json` if you touched the plugin; keep `git_hash` churn in its own patch.
7. `stg refresh`, push, open a PR.

## Summary

| Action                    | Command                                              |
|---------------------------|------------------------------------------------------|
| Sync dev env              | `uv sync`                                            |
| Run tests                 | `uv run python hooks/test_requirements.py` (green = 1544/1551) |
| Lint                      | `uv run ruff check .`                                |
| Rebuild plugin hooks      | `uv run python scripts/build_plugin_hooks.py`        |
| Check plugin-hook drift   | `uv run python scripts/build_plugin_hooks.py --check`|
| Render plugin prompts     | `uv run python scripts/render_prompts.py`            |
| Check prompt freshness    | `uv run python scripts/render_prompts.py --check`    |
| Commit (atomic)           | `stg new <name>` → `stg refresh`                     |

**Golden rules:** edit `hooks/` (never the plugin build-copy), run everything through
`uv run`, keep patches atomic with `stg`, and bump `plugin.json` whenever the plugin
changes.
