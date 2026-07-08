# Requirements Framework Plugin

Workflow enforcement, agent-team code review, and session tooling for Claude Code.

**Version:** 4.31.0

## Overview

This is a **self-contained plugin**. It bundles the lifecycle hooks, the `req`
CLI, and a catalog of agents, commands, and skills that guide a change from
first idea to merged branch. Hooks watch your edits/commits and nudge you toward
the next step of a typed 7-node workflow; commands and skills do the work at
each step.

**What's inside (verified on disk):**

- **24 agents** — reviewers, auditors, and refactor workers invoked by commands or Agent Teams.
- **16 commands** — orchestrators for each workflow phase plus `req` management.
- **21 skills** — natural-language capabilities: the workflow phase skills, framework help, and session learning.

### Runtime model (self-contained)

Hook registration is owned by the plugin. The single source of truth is
`hooks/hooks.json`, which registers every lifecycle hook via
`${CLAUDE_PLUGIN_ROOT}`. There is **no** `~/.claude/hooks` deploy step and **no**
`sync.sh` in the plugin runtime — installing the plugin activates the hooks
directly. All Python entrypoints run through **`uv`** (ADR-021); nothing relies
on the ambient `python3`.

## Installation

### Marketplace (recommended)

```
/plugin marketplace add HarmAalbers/claude-requirements-framework
/plugin install requirements-framework@requirements-framework
```

Enable per-marketplace auto-update so `master` pushes land at session startup.

### Dev / live-reload

Point Claude Code at the plugin directory to iterate with live reload:

```bash
claude --plugin-dir ~/Tools/claude-requirements-framework/plugins/requirements-framework
```

Prerequisite for either path: **`uv` on PATH**. The hooks self-bootstrap their
dependencies through `uv run`.

## Workflow Backbone (ADR-022, typed 7-node)

The default workflow is a typed 7-node backbone, not a flat checklist:

```
Design → Plan → Validate → Build → Review → Verify → Ship
[spine] [spine] [TEAM]    [spine] [TEAM]   [spine] [spine]
                                   +loop (in Build)
```

- **spine** nodes nudge one skill; the skill auto-satisfies the node's gate.
- **team** nodes nudge one orchestrating command that fans out its agents and satisfies one gate.
- **loop** is a `single_use` gate re-armed each commit.
- **conditionals** are optional side-quests surfaced as "available here" — no gate, no auto-fire.

| Node     | Type  | Gate                  | Skill / Command                                             |
|----------|-------|-----------------------|------------------------------------------------------------|
| design   | spine | `design_approved`     | `/brainstorm` (`brainstorming` skill)                      |
| plan     | spine | `plan_written`        | `/write-plan` (`writing-plans` skill)                      |
| validate | team  | `plan_validated`      | `/arch-review` *(cond: `/codex-review`)*                   |
| build    | spine | `implementation_done` | `/execute-plan` *(loop: `/pre-commit` → `pre_commit_review` per commit)* |
| review   | team  | `pr_reviewed`         | `/deep-review` *(cond: `/codex-review`)*                   |
| verify   | spine | `verified`            | `verification-before-completion` skill                     |
| ship     | spine | — (gateless)          | `finishing-a-development-branch` skill                     |

> **Gate vocabulary note.** The active gates are `design_approved`,
> `plan_written`, `plan_validated`, `implementation_done`, `pr_reviewed`, and
> `verified` (ship is gateless). The older gates `commit_plan`, `adr_reviewed`,
> `tdd_planned`, `solid_reviewed`, `pre_pr_review`, `pre_push_verification`, and
> `codex_reviewer` are **retired** — `plan_validated` consolidates the four
> Validate-team gates, `pr_reviewed` replaces `pre_pr_review`, `verified`
> replaces `pre_push_verification`, and Codex is now a conditional side-quest
> rather than a gate. A config that still names a retired gate gets a validation
> error pointing at the new name.

Not sure where you are? Run **`/req`** with no arguments — the conductor derives
the current phase and dispatches to the matching skill or command.

## Commands (16)

### Workflow orchestrators

| Command | Description |
|---------|-------------|
| `/req` | Workflow conductor — derives the current phase and dispatches to the matching skill/command. Run bare to be guided, or pass an explicit phase. |
| `/brainstorm` | Design-first development: explore requirements before implementation (satisfies `design_approved`). |
| `/write-plan` | Create a detailed implementation plan from requirements or a spec (satisfies `plan_written`). |
| `/arch-review` | Multi-perspective team-based architecture review with agent debate and commit planning (satisfies `plan_validated`). |
| `/execute-plan` | Execute an implementation plan with batch checkpoints and review (satisfies `implementation_done`). |
| `/pre-commit` | Quick pre-commit review (code + error handling); the per-commit Build loop (satisfies `pre_commit_review`). |
| `/deep-review` | Cross-validated team-based code review with agent debate (satisfies `pr_reviewed`). |

### Review add-ons

| Command | Description |
|---------|-------------|
| `/codex-review` | AI-powered code review using the OpenAI Codex CLI (conditional side-quest in Validate/Review). |
| `/v3-review` | SDK fan-out code review (V3) — structured-output review workers + aggregator, rendered as an ADR-013 report. Additive opt-in alternative to `/deep-review` (ADR-018). |
| `/commit-checks` | Auto-fix code quality issues — comment cleanup and import organization. |
| `/refactor-orchestrate` | Multi-layer top-down refactor workflow; produces a validated plan and an orchestrator prompt that runs in a fresh session, dispatching Haiku executor chunks and escalating contradictions to a Sonnet investigator. |

### Session & framework management

| Command | Description |
|---------|-------------|
| `/session-reflect` | Review the current session and suggest improvements for future sessions. |
| `/req-init` | Scaffold `.claude/requirements.local.yaml` for strict-mode compliance. |
| `/req-optout` | Mark the project inert under strict mode via the `.rf-optout` sentinel. |
| `/req-pause` | Pause the framework's blocking gates for this session only (auto-resumes at session end). |
| `/req-resume` | Resume the framework's blocking gates for this session (undo `/req-pause`). |

## Agents (24)

Agents are invoked by the orchestrator commands (often as Agent Teams that
cross-validate findings) or on demand via the Agent tool.

### Plan & architecture review

| Agent | Description |
|-------|-------------|
| `adr-guardian` | Validates plans and code against Architecture Decision Records; can block to prevent architectural drift. |
| `solid-reviewer` | Reviews a plan for SOLID design principles (SRP, OCP, LSP, ISP, DIP). |
| `tdd-validator` | Validates TDD readiness of a plan — testing strategy, test types per feature. |
| `commit-planner` | Builds an atomic commit strategy from a validated plan. |
| `refactor-advisor` | Identifies preparatory refactoring that makes the planned change easier ("first make the change easy, then make the easy change"). |

### Code review & quality

| Agent | Description |
|-------|-------------|
| `code-reviewer` | Reviews code before committing for guideline, style, and best-practice adherence. |
| `silent-failure-hunter` | Hunts swallowed errors and fragile fallbacks in try/catch and error-callback code. |
| `comment-analyzer` | Verifies comments accurately reflect the code they describe. |
| `test-analyzer` | Reviews test coverage quality and completeness for added/modified tests. |
| `type-design-analyzer` | Analyzes new type design for encapsulation and correctness. |
| `tool-validator` | Runs pyright/ruff/eslint on staged changes to catch CI errors locally (fast, blocking gate). |
| `backward-compatibility-checker` | Detects breaking changes in schemas, APIs, and contracts. |
| `frontend-reviewer` | Reviews React/frontend code for best practices, accessibility, and performance. |

### Security & compliance auditors

| Agent | Description |
|-------|-------------|
| `appsec-auditor` | Audits code for OWASP Top 10 application-security vulnerabilities. |
| `tenant-isolation-auditor` | Audits for multi-tenant data-leakage vulnerabilities. |
| `compliance-auditor` | Audits for GDPR/AVG compliance, audit trails, and PII handling. |

### Auto-fix

| Agent | Description |
|-------|-------------|
| `comment-cleaner` | Removes useless comments from staged files. |
| `import-organizer` | Organizes and groups imports in staged Python files (stdlib / third-party / local). |

### External-AI review

| Agent | Description |
|-------|-------------|
| `codex-review-agent` | Orchestrates the OpenAI Codex CLI for AI-powered code review. |
| `codex-arch-reviewer` | Uses the OpenAI Codex CLI for architecture-focused review (coupling, module dependencies, API surface). Skips silently when Codex is unavailable. |

### Refactor orchestration

| Agent | Description |
|-------|-------------|
| `refactor-executor` | Mechanical chunk executor (Haiku) — implements a referenced plan section exactly, verifies with ruff + an import smoke. |
| `refactor-investigator` | Read-only diagnostician (Sonnet) — diagnoses plan-vs-reality contradictions and returns solution paths. |
| `refactor-analyzer` | Retrospective writer (Sonnet) — reads the transcript/git log, writes a retrospective, and promotes rule-of-three learnings. |

### Session

| Agent | Description |
|-------|-------------|
| `session-analyzer` | Analyzes session metrics to surface patterns, friction points, and improvement opportunities. |

Requires the Codex CLI for `codex-review-agent` / `codex-arch-reviewer`:
`npm install -g @openai/codex`.

## Skills (21)

Skills are triggered by natural language (or the workflow conductor).

### Workflow phase skills

| Skill | Description |
|-------|-------------|
| `brainstorming` | Design-first exploration before any implementation begins (Design phase). |
| `writing-plans` | Turn a spec/requirements into a detailed implementation plan (Plan phase). |
| `executing-plans` | Execute a written plan in a separate session with review checkpoints (Build phase). |
| `verification-before-completion` | Verify work before claiming it complete, committing, or opening a PR (Verify phase). |
| `finishing-a-development-branch` | Decide how to integrate completed work into the main branch (Ship phase). |
| `requesting-code-review` | Request review when completing features or before merging. |
| `receiving-code-review` | Work through review feedback before implementing suggestions. |

### Engineering practice skills

| Skill | Description |
|-------|-------------|
| `test-driven-development` | Write tests before implementation for any feature or bugfix. |
| `systematic-debugging` | Structured investigation before proposing fixes for a bug or failure. |
| `using-git-worktrees` | Isolate feature work in a git worktree. |
| `dispatching-parallel-agents` | Fan out 2+ independent tasks with no shared state. |
| `subagent-driven-development` | Execute independent plan tasks via subagents in the current session. |
| `refactor-orchestration` | Plan and drive a multi-layer top-down refactor as a fresh-session orchestrator dispatching executor chunks. |
| `writing-skills` | Create, edit, and verify skills. |

### Framework help & management

| Skill | Description |
|-------|-------------|
| `using-requirements-framework` | Establish skill discovery and invocation practices at the start of a conversation. |
| `workflow-index` | Map the current phase to the single next command to run ("what next", "where am I", `/req`). |
| `requirements-framework-usage` | Help configuring requirements, the `req` CLI, scopes, and troubleshooting. |
| `requirements-framework-status` | Comprehensive status report of the framework's current state. |
| `requirements-framework-builder` | Extend the framework — new requirement types, strategies, calculators, auto-satisfaction mappings. |
| `requirements-framework-development` | Framework development workflow — bug fixes, TDD for the framework, contributing changes. |
| `session-learning` | Learn from a session to improve future ones — metrics, reflection, `/session-reflect`, `req learning`. |

## Auto-satisfaction

When a review command completes, a PostToolUse hook satisfies the matching gate
automatically:

- `/arch-review` → `plan_validated`
- `/deep-review` → `pr_reviewed`
- `/pre-commit` → `pre_commit_review` (the Build loop gate, re-armed each commit)

The spine skills auto-satisfy their own gates (`brainstorming` → `design_approved`,
`writing-plans` → `plan_written`, etc.).

## The `req` CLI

```bash
req status                 # Current requirement/workflow status
req satisfy <gate>         # Manually satisfy a gate
req logging --level debug  # Configure logging
req learning stats         # Session-learning statistics
req upgrade status         # Feature adoption for this project
```

## Further reading

- `docs/adr/` — Architecture Decision Records (ADR-011 messages, ADR-012 Agent Teams, ADR-019 observability, ADR-020 strict preflight, ADR-021 uv, ADR-022 7-node workflow).
- Root `CLAUDE.md` — full development, testing, and configuration guide.
