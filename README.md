# Claude Code Requirements Framework

A hook-based system for enforcing a development workflow in Claude Code. It ships as a **self-contained plugin**: install the plugin and its lifecycle hooks gate your work through a typed 7-node workflow — Design → Plan → Validate → Build → Review → Verify → Ship — so critical steps (design, planning, architecture review, code review, verification) happen before code lands.

## Features

- **🔒 PreToolUse gate**: Blocks file modifications until the current phase's requirement is satisfied
- **🛑 Stop gate**: Verifies session-scoped requirements before Claude finishes (prevents incomplete work)
- **🚀 SessionStart context**: Injects full requirement status at session start
- **🧭 Typed 7-node workflow (ADR-022)**: Design → Plan → Validate → Build → Review → Verify → Ship, each with its own gate and skill/command
- **🎯 Four scopes**: `session`, `branch`, `permanent`, `single_use`
- **⚡ `req` CLI**: One command to inspect and drive requirements (`req status`, `req satisfy`, `req enable`, …)
- **📦 Config cascade**: global → project → local, with `local` winning
- **🔌 Rich plugin**: 24 agents, 16 commands, 21 skills for review, planning, and orchestration
- **🧪 Comprehensive test suite** run under `uv`

## Runtime Model: Self-Contained Plugin

The framework runs entirely from the installed plugin. There is **no separate `~/.claude/hooks` deploy step and no two-location sync** — those are gone.

- Hook registration is owned by `plugins/requirements-framework/hooks/hooks.json`, which wires every lifecycle hook via `${CLAUDE_PLUGIN_ROOT}`.
- `install.sh` only sets up the **host-side tooling**: the `req` CLI, the phase-aware statusline, and shell env. It does **not** copy hook scripts anywhere or write a `hooks` block into your settings.
- **Installing the plugin is what activates the hooks.**

## Quick Start

### 1. Install the host tooling

```bash
git clone https://github.com/HarmAalbers/claude-requirements-framework ~/Tools/claude-requirements-framework
cd ~/Tools/claude-requirements-framework
./install.sh
```

`install.sh` (requires `uv` on PATH) runs `uv sync`, installs the global config to `~/.claude/requirements.yaml`, creates the `req` CLI at `~/.local/bin/req`, registers the statusline (only if you don't already have a custom one), and adds `ENABLE_TOOL_SEARCH=true` to your shell rc.

### 2. Install the plugin (this activates the hooks)

**From the GitHub marketplace (recommended):**

```text
# In a Claude Code session:
/plugin marketplace add HarmAalbers/claude-requirements-framework
/plugin install requirements-framework@requirements-framework
```

**For development (live reload from your clone):**

```bash
claude --plugin-dir ~/Tools/claude-requirements-framework/plugins/requirements-framework
```

### 3. Verify

```text
# In a new session, type the command prefix to autocomplete:
/requirements-framework:

# Check the installed version:
/plugin list
# Should show: requirements-framework@4.31.0
```

For deeper installation and troubleshooting reference:
- **[Plugin Installation Guide](docs/PLUGIN-INSTALLATION.md)**
- **[Plugin README](plugins/requirements-framework/README.md)**

### Token efficiency: on-demand tool loading

`install.sh` enables on-demand tool loading by adding `export ENABLE_TOOL_SEARCH=true` to your shell rc (requires Claude Code v2.0.74+). This makes Claude Code load tool schemas lazily via `ToolSearch` instead of dumping every deferred-tool description into the initial system prompt, trimming several thousand tokens per new session. The append is idempotent; decline at the prompt to skip. (It does *not* shrink the "Available agent types" block — that's driven by `plugin.json`.)

## Project Setup

After installing, scaffold requirements for a project:

```bash
cd /your/project
req init                       # interactive wizard
req init --yes --preset relaxed  # non-interactive
```

`req init` detects context (global vs. project, with/without an existing global config) and offers presets: `advanced` (all features), `inherit` (rely on global defaults), `relaxed` (baseline), `strict` (full enforcement), `minimal` (framework on, no requirements). It writes `.claude/requirements.yaml` (or `.claude/requirements.local.yaml` for strict-mode compliance via `/req-init`).

## The Workflow (ADR-022 typed 7-node backbone)

The default workflow (`WORKFLOW_DEFAULTS` in `hooks/lib/config.py`) is a typed backbone. Each phase has a `type`, a gate, and a skill or orchestrating command. `spine` nodes nudge one skill; `team` nodes nudge one orchestrating command that fans out agents and satisfies one gate on completion.

```
Design → Plan → Validate → Build → Review → Verify → Ship
[spine]  [spine] [TEAM]    [spine]  [TEAM]   [spine]  [spine]
                                    +loop (in Build)
```

| Node       | Type  | Gate                 | Skill / Command                              |
|------------|-------|----------------------|----------------------------------------------|
| design     | spine | `design_approved`    | `/brainstorming`                             |
| plan       | spine | `plan_written`       | `/writing-plans`                             |
| validate   | team  | `plan_validated`     | `/arch-review` *(cond: `/codex-review`)*     |
| build      | spine | `implementation_done`| `/executing-plans` *(loop: `/pre-commit` → `pre_commit_review` per commit)* |
| review     | team  | `pr_reviewed`        | `/deep-review` *(cond: `/codex-review`)*     |
| verify     | spine | `verified`           | `/verification-before-completion`            |
| ship       | spine | — (gateless)         | `/finishing-a-development-branch`            |

**Gate consolidation.** ADR-022 folded the older gate zoo into the seven names above. The retired names and their replacements:

| Retired gate                                          | Now                                    |
|-------------------------------------------------------|----------------------------------------|
| `commit_plan`, `adr_reviewed`, `tdd_planned`, `solid_reviewed` | `plan_validated` (one Validate-team gate) |
| `pre_pr_review`                                       | `pr_reviewed`                          |
| `pre_push_verification`                               | `verified`                             |
| `codex_reviewer`                                      | conditional side-quest (no gate)       |

There are **no backward-compat shims** — a config still naming an old gate gets a validation error pointing at the new name.

> **YAML footgun:** inside a `loop`, quote the trigger key (`"on": commit`) — a bare `on:` parses as boolean `True` under YAML 1.1.

## Using the `req` CLI

The `req` command is the primary interface — prefer it over hand-editing YAML.

```bash
# Inspect
req status                      # current phase + requirement state for this project
req list                        # list all requirements
req sessions                    # active Claude Code sessions

# Drive
req satisfy plan_validated      # mark a gate satisfied for the current session
req clear plan_validated        # clear it
req enable pr_reviewed          # enable a requirement
req satisfy verified --branch   # satisfy for the whole branch
req satisfy design_approved --ttl 3600   # satisfy for 1 hour
req satisfy plan_written --session abc12345  # target a specific session

# Session control
req pause                       # pause blocking gates for this session (auto-resumes at session end)
req resume

# Diagnostics
req doctor                      # verify install: req CLI, plugin config, project config
req logging --level debug --local
```

Scoped satisfaction matters: satisfying a `branch`-scope requirement with `--session` (or vice versa) won't clear the block. Use `req status` to see each requirement's scope.

## Requirement Scopes

| Scope        | Behavior                                              | Use case                          |
|--------------|-------------------------------------------------------|-----------------------------------|
| `session`    | Cleared when the Claude Code session ends             | Per-session phase gates           |
| `branch`     | Persists across sessions on the same branch           | Branch-linked review/verification |
| `permanent`  | Never auto-cleared                                     | One-time project setup            |
| `single_use` | Cleared after its trigger command completes (re-armed)| Per-commit `pre_commit_review` loop |

## Configuration System

### 3-level cascade

1. **Global** — `~/.claude/requirements.yaml` (defaults for all projects)
2. **Project** — `.claude/requirements.yaml` (shared, committed to repo)
3. **Local** — `.claude/requirements.local.yaml` (personal overrides, gitignored)

Priority is **local > project > global**.

### Example: project config

```yaml
# .claude/requirements.yaml
version: "1.0"
inherit: true   # merge with global config

requirements:
  plan_validated:
    enabled: true
    type: blocking
    scope: single_use
    satisfied_by_skill: 'requirements-framework:arch-review'

  verified:
    enabled: true
    scope: branch
```

### Example: local override

```yaml
# .claude/requirements.local.yaml (gitignored)
requirements:
  plan_validated:
    enabled: false   # temporarily disable for myself
```

### Guard and dynamic requirement types

Beyond the workflow gates, the framework supports:

**Guard** — checks a condition rather than requiring manual satisfaction:

```yaml
requirements:
  protected_branch:
    enabled: true
    type: guard
    guard_type: protected_branch
    protected_branches: [master, main]
```

**Dynamic** — computed by a calculator, not manually satisfied:

```yaml
requirements:
  branch_size_limit:
    enabled: true
    type: dynamic
    calculator: branch_size_calculator
    scope: session
    thresholds:
      warn: 250   # log warning (non-blocking)
      block: 400  # block with denial message
    cache_ttl: 60
    approval_ttl: 3600   # 1 hour approval via `req approve`
```

### Project-specific skills (`satisfied_by_skill`)

Connect any project skill to auto-satisfy a requirement when it completes:

```yaml
requirements:
  architecture_review:
    enabled: true
    type: blocking
    scope: single_use
    trigger_tools:
      - tool: Bash
        command_pattern: 'gh\s+pr\s+create'
    satisfied_by_skill: 'architecture-guardian'  # your project skill name
```

Plugin skills use the namespaced form (`'requirements-framework:arch-review'`); project skills use the bare name from their frontmatter.

### Logging and console output

```yaml
logging:
  level: info               # debug | info | warning | error
  destinations: [file]      # stdout | file
  file: ~/.claude/requirements.log
console:
  level: warning            # non-JSON console output (default: silent)
  destinations: [stderr]    # stdout | stderr | file
```

### Hook configuration

```yaml
hooks:
  session_start:
    inject_context: true       # ON by default
  stop:
    verify_requirements: true  # ON by default
    verify_scopes: [session]   # which scopes the Stop gate checks
  session_end:
    clear_session_state: false # OFF by default
```

## Session Lifecycle (17 hooks across 12 events)

The plugin registers 17 hook commands across 12 events via `plugins/requirements-framework/hooks/hooks.json` (the authoritative source). The core gating flow:

```
🚀 SessionStart ──► clean stale sessions, inject full requirement status
   │
   │  WORK LOOP
   │  🔒 PreToolUse (Edit/Write/Bash/…) ──► block if the current gate is unsatisfied
   │
🛑 Stop ──► verify session-scoped requirements; block finish if incomplete
   │
🧹 SessionEnd ──► remove session from registry, optional state cleanup
```

| Hook            | When                       | Can block | Purpose                                        |
|-----------------|----------------------------|-----------|------------------------------------------------|
| SessionStart    | Session starts/resumes     | No        | Inject context, prune stale sessions           |
| PreToolUse      | Before Edit/Write/Bash/…   | Yes       | Block modifications until the gate is satisfied|
| Stop            | Claude about to finish     | Yes       | Verify session-scoped requirements             |
| SessionEnd      | Session ends               | No        | Cleanup                                        |

The full set also includes `UserPromptSubmit`, `PermissionRequest`, several `PostToolUse` hooks (auto-satisfy skills, clear single-use, git events, plan enter/exit), `PostToolUseFailure`, `SubagentStart`, `PreCompact`, a second `Stop` hook (Langfuse trace, opt-in), `TeammateIdle`, and `TaskCompleted`. See `DEVELOPMENT.md` for the complete hook lifecycle.

### Stop hook behavior

Enabled by default. Checks session-scoped requirements, uses a `stop_hook_active` flag to prevent infinite continuation loops, and shows which requirements still need satisfaction. Disable with `hooks.stop.verify_requirements: false`.

## Plugin Components

The plugin bundles **24 agents, 16 commands, and 21 skills**.

> **Authoring note:** plugin agents/commands use a two-file pattern — `<name>.md.j2` (Jinja2 source you edit) and `<name>.md` (rendered output Claude Code dispatches). Run `uv run python scripts/render_prompts.py` after editing a `.md.j2`. See DEVELOPMENT.md.

### Key commands

- `/requirements-framework:brainstorm` — design-first exploration (Design phase)
- `/requirements-framework:write-plan` — produce an executable plan (Plan phase)
- `/requirements-framework:arch-review` — team-based architecture review; satisfies `plan_validated` (Validate phase)
- `/requirements-framework:execute-plan` — execute a plan with checkpoints (Build phase)
- `/requirements-framework:pre-commit [aspects]` — fast pre-commit review; satisfies the `pre_commit_review` build loop
- `/requirements-framework:deep-review` — cross-validated team code review; satisfies `pr_reviewed` (Review phase)
- `/requirements-framework:codex-review [focus]` — AI-powered review via OpenAI Codex (conditional side-quest)
- `/requirements-framework:refactor-orchestrate` — multi-layer top-down refactor workflow
- `/req` — workflow conductor: derives the current phase and dispatches to the matching skill/command

### Representative agents

**Review suite:** `code-reviewer`, `silent-failure-hunter`, `test-analyzer`, `type-design-analyzer`, `comment-analyzer`, `tool-validator`, `backward-compatibility-checker`, `frontend-reviewer`.
**Architecture / workflow:** `adr-guardian`, `solid-reviewer`, `tdd-validator`, `commit-planner`, `refactor-advisor`, `codex-review-agent`, `codex-arch-reviewer`.
**Refactor orchestration:** `refactor-executor` (Haiku), `refactor-investigator` (Sonnet), `refactor-analyzer` (Sonnet).
**Security / compliance:** `appsec-auditor`, `tenant-isolation-auditor`, `compliance-auditor`.

### Skills

Skills cover the whole workflow (`brainstorming`, `writing-plans`, `executing-plans`, `verification-before-completion`, `finishing-a-development-branch`), engineering practice (`test-driven-development`, `systematic-debugging`, `using-git-worktrees`), review (`requesting-code-review`, `receiving-code-review`), and framework meta-work (`requirements-framework-usage`, `-builder`, `-development`, `-status`, `session-learning`, `writing-skills`).

## Agent Teams (ADR-012)

Team-based review is the primary review approach: agents collaborate, cross-validate findings, and produce a unified verdict.

```yaml
hooks:
  agent_teams:
    enabled: true                # on by default
    keep_working_on_idle: false
    validate_task_completion: false
    max_teammates: 5
    fallback_to_subagents: true
```

## State Storage

Branch state lives in `.git/requirements/[branch].json`:

```json
{
  "version": "1.0",
  "branch": "feature/auth",
  "requirements": {
    "plan_validated": {
      "scope": "single_use",
      "sessions": {
        "abc12345": { "satisfied": true, "satisfied_at": 1702345678, "satisfied_by": "cli" }
      }
    }
  }
}
```

Sessions are tracked in `~/.claude/sessions.json`; the CLI auto-detects the current session and prunes stale ones by PID validation.

## Development

> **`uv` is required.** Every Python entrypoint — the `req` CLI, the hooks, and all build/test tooling — resolves through `uv` (single source of truth: `pyproject.toml` + `uv.lock`). Never call bare `python3` for tooling.

```bash
# One-time: sync the uv-managed environment
uv sync

# Run the test suite
uv run python hooks/test_requirements.py

# Lint (pinned ruff, matches CI)
uv run ruff check .
```

### Plugin bundle

The repo `hooks/` tree is the single source of truth. The copies under `plugins/requirements-framework/hooks/` are **build artifacts** so a marketplace / `--plugin-dir` install is self-contained. After editing any hook or `lib/` module, rebuild the bundle:

```bash
uv run python scripts/build_plugin_hooks.py          # mirror hooks/ → plugin tree
uv run python scripts/build_plugin_hooks.py --check   # report drift (wired into the tests)
```

There is **no user "deploy" step** and nothing is copied into `~/.claude/hooks/`. Reload by restarting the session or running `claude --plugin-dir …`.

### Plugin version bumps

Every change touching plugin files (agents, commands, skills, hooks) must bump `plugins/requirements-framework/.claude-plugin/plugin.json` in the same change (semver: patch/minor/major). Update component `git_hash` fields with `./update-plugin-versions.sh`.

### TDD workflow

1. Write tests in `hooks/test_requirements.py`
2. Run (RED): `uv run python hooks/test_requirements.py`
3. Implement
4. Rebuild bundle + run (GREEN)
5. Commit

## Local Observability (V3, opt-in)

V3 LLM calls can be traced into a self-hosted Langfuse instance, and each Claude Code turn can be traced via a bundled Stop hook. This is **opt-in per project** and inert everywhere else. See ADR-019 and the `langfuse` skill / `scripts/setup_langfuse_tracing.py` for setup. With no env vars set, nothing traces and no errors are raised.

## Strict Global Preflight (ADR-020, opt-in)

An opt-in, **fail-closed** adoption gate. When `strict_preflight: true` is set in `~/.claude/requirements.yaml`, a globally-installed plugin blocks work in any non-compliant project until it's configured (`.claude/requirements.local.yaml` with ≥1 enabled requirement, valid Langfuse env, `uv` on PATH) or opted out (`/req-optout`). OFF by default. Emergency bailout: `RF_STRICT_OFF=true`. See ADR-020.

## Troubleshooting

**Hooks not firing** — hooks are registered by the plugin, not by a hand-written `hooks` block in settings. Confirm the plugin is installed (`/plugin install requirements-framework@requirements-framework`) or run with `claude --plugin-dir …`. Verify the bundle is in sync: `uv run python scripts/build_plugin_hooks.py --check`.

**`Edit(*)` / `Write(*)` in `permissions.allow`** bypass hooks — remove those wildcards.

**`req` not found** — add `~/.local/bin` to PATH.

**Requirement satisfied but still blocking** — usually a scope mismatch (satisfied `--session` but the requirement is `branch` scope, or vice versa) or an expired TTL. Check `req status` for the scope and re-satisfy with the matching flag.

**Skip temporarily** — `export CLAUDE_SKIP_REQUIREMENTS=1`, or `req pause` for the session, or set `enabled: false` in `.claude/requirements.local.yaml`.

**Diagnostics** — `req doctor`; logs at `~/.claude/requirements.log` (`tail -f`); tests via `uv run python hooks/test_requirements.py`.

## Architecture Decision Records

Key decisions live in `docs/adr/`. Notable: ADR-011 (externalized messages), ADR-012 (agent teams), ADR-019 (Stop-hook observability), ADR-020 (strict global preflight), ADR-021 (uv standardization), ADR-022 (typed 7-node workflow backbone).

## Contributing

1. Fork and branch (this repo authors commits via Stacked Git — see CLAUDE.md).
2. Write tests first (TDD).
3. Rebuild the bundle and test: `uv run python scripts/build_plugin_hooks.py && uv run python hooks/test_requirements.py`
4. Ensure the bundle is in sync: `uv run python scripts/build_plugin_hooks.py --check`
5. Bump `plugin.json` if plugin files changed, then open a PR.

## License

MIT License — see LICENSE.
