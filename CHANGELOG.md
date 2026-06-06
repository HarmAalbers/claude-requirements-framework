# Changelog

All notable changes to the requirements-framework plugin are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [4.15.0] — 2026-06-06

> Consolidated entry for the `4.7.0 → 4.15.0` arc — the V3 LLM platform scaffold
> (Steps 17a–18c) plus the workflow re-enablement and simplification work — landed as
> one `--no-ff` merge of the 177-patch `refactor/step-08-llm-package-scaffold` branch.
> Earlier slices of the same effort already have their own `[4.2.0]`–`[4.6.0]` entries
> below; this entry covers everything since `[4.6.0]` and recaps the platform as a whole.

### ⚠️ Behavior changes (read this)

These change **default live-path behavior for plugin users**. Opt-out keys are listed inline.

- **Brainstorm nudge is now default-ON.** Every substantive first prompt gets a
  `/brainstorming` nudge while the design gate is unsatisfied. It is **mode-independent**
  (fires on `UserPromptSubmit`, not just plan mode) and **deduplicated to once per session**.
  - Opt out: `hooks.prompt_submit.brainstorm_nudge: false` (and the plan-mode path
    `hooks.plan_enter.brainstorm_on_enter: false`).
- **Plan / commit gates changed how and when edits are blocked.** When the
  `design_approved` / `commit_plan` requirements are enabled, they block `Edit`/`Write`
  until satisfied. The gate UX was reworked (proactive, self-explanatory block messages)
  and `commit_plan` is now **evidence-gated** (plan artifact + verdict, not a checkbox).
  - These fire **only when the requirement is enabled** in config — leave them unset/disabled
    to opt out.
- **`stop_only` verification gate.** `verification_evidence` is now enforced at session
  `Stop` (new `stop_only` scope). Fires **only when that requirement is enabled** in config.

### Added — V3 LLM platform (dormant / opt-in scaffolding)

The `hooks/lib/llm/` package landed **tested-but-unwired** — off every live path by default.
The package `__init__.py` is PEP-562 lazy (importing it does not pull in the SDK or pydantic),
and the only live touch-points are config-gated off and fail-open.

- **Structured-output schemas** — Pydantic `ReviewReport`/`Finding` models for SDK
  `output_format` (Step 09).
- **Self-hosted Langfuse observability** — local 5-service dev docker stack + tracing module
  with atexit flush; PII masking explicitly out of scope (single-user, self-hosted) (Step 11).
- **Prompt registry** — `PromptLoader` with TTL caching + version-label rollback, Langfuse-backed
  with `.md.j2` file fallback (Step 12).
- **Qdrant retrieval + session memory** — embedder/retrieval/summarizer modules, SessionEnd write
  + SessionStart read injection. **Off by default** (`hooks.qdrant.enabled`, `hooks.retrieval.enabled`
  = `false`), hard SIGALRM-timeboxed, fail-open (Steps 13–14).
- **Ragas eval harness** — `FindingMatch`/`score_case` + 5 synthetic golden cases + JSONL ledger
  + optional Langfuse score posting (Step 15).
- **Jinja2 prompt-template engine** — `StrictUndefined` render pipeline; **57-file plugin migration**
  to `.md.j2` source-of-truth (25 agents + 11 commands + 21 skills), byte-identical rendered output,
  with a build-time render gate + permanent freshness invariant test (Steps 16/16b/16c).
- **SDK budget tracker** — per-call usage auto-recorded from the `claude.query` wrapper + `req budget`
  CLI; config-gated (Step 17a).
- **Thin `/req` supervisor** — `supervisor.route` phase-name router (Step 18).
- **Multi-worker review fan-out** — coordinator that dispatches N structured-output review workers
  in parallel, semantic aggregation with mechanical-merge fallback, deterministic `tool_gate` pre-flight,
  per-worker error capture (Step 18b).
- **`/v3-review` command** — wires the fan-out into a slash command + `scripts/v3-review`; can satisfy
  `pre_pr_review` via `auto-satisfy-skills.py` **only when the user runs it** (never auto-invoked) (Step 18c).
  - ⚠️ **Cost foot-gun:** `/v3-review` runs at **~$2–12 per run with no per-call cap** (per-call caps are
    Step 17b, unfinished). Treat as opt-in; do not auto-wire.

### Added / Changed — workflow & re-enablement

- **Per-project configurable workflow order** — new `workflow:` config section defining phase order,
  consumed by `/req` and the plan-enter hook; `req-phase` conductor reads it.
- **Config-driven supervisor** — LLM surfaces mirror the `workflow:` section (phase-name routing).
- **Brainstorm-on-`UserPromptSubmit`** — the mode-independent nudge path (see behavior changes above).
- **State-write concurrency hardening** — state-file read-modify-write serialized with unique temp writes
  to prevent corruption under parallel hook invocations.
- **Self-contained plugin** — hooks build-copied into the plugin tree and registered via a single source
  (`hooks.json` / `${CLAUDE_PLUGIN_ROOT}`); `install.sh` no longer copies hook scripts or writes a `hooks`
  block into `~/.claude/settings.json` — it sets up only the `req` CLI, statusline, and shell env. Hooks
  activate via `/plugin install …` or `claude --plugin-dir`.
- **README rewritten** for the plugin-owned hook model (drops the stale "installer copies hooks to
  `~/.claude/hooks/`" / two-location `sync.sh` deploy guidance).

### Fixed

- **Stop-gate deadlock** — a blocked action no longer traps the session at `Stop` (the gate could
  leave the session unable to complete).
- **`PermissionRequest` deny shape** — hook now emits the correct deny payload.
- **Guard-aware unsatisfied check** — prompt-submit + subagent-start no longer misreport guard
  requirements as unsatisfied.
- **CI llm-deps** — `.github/workflows/ci.yml` installs `pydantic` + `jinja2` (not the full `.[llm]`
  extra) so the V3-importing tests run green instead of crashing the runner with `ModuleNotFoundError`.
- **OTel teardown noise** — benign `Failed to detach context` shutdown messages suppressed;
  `_run_async` reverted to plain `asyncio.run()` to kill teardown chatter.
- **Jinja2 `keep_trailing_newline`** confirmed load-bearing for the byte-identical render invariant
  (see `[4.6.0]` notes).
- **`ReviewReport.summary` 500-char cap removed** — the constraint propagated into the SDK
  `output_format` schema and rejected every worker response on large diffs (see `[4.6.0]` dogfood note).

### Internal / housekeeping

- Plugin bumped **4.6.0 → 4.15.0**.
- Main test suite grew to **1445** tests (`hooks/test_requirements.py`).
- **~273 V3 unit tests** under `tests/` (schemas, workers, fan-out, eval, memory, templates, budget) —
  **not yet CI-gated**; the CI job runs only `hooks/test_requirements.py`.
- Dead `ruff_check.py` hook + its runtime references deleted.
- Steps 17b/19/20 remain inert plan docs under `.claude/plans/variant3/` — merged as roadmap history,
  no implementation code.

## [4.6.0] — 2026-05-24

### Changed

- **Step 16c — Plugin commands and skills converted to Jinja2 templates (source format change only; rendered output is byte-identical).** All 11 commands in `plugins/requirements-framework/commands/` and all 21 skills in `plugins/requirements-framework/skills/*/SKILL.md` now have `.md.j2` source-of-truth alongside their existing `.md` rendered siblings. Completes the Step 16b conversion to cover every dispatched prompt under `plugins/requirements-framework/`. Claude Code continues to dispatch the `.md` files unchanged; the `.md.j2` files are what you edit.
- **`DEVELOPMENT.md`** — section renamed "Plugin Agent Authoring (Step 16b)" → "Plugin Prompt Authoring (Steps 16b + 16c)" to reflect the broader scope (25 agents + 11 commands + 21 skills). Adds a scope note on `{% include %}` loader-root boundaries between build-time plugin templates and runtime worker templates (codex-arch-reviewer finding).
- **`scripts/render_prompts.py`** — docstring step reference updated to "Steps 16b–16c" so the script's self-description matches reality (solid-reviewer cosmetic note).
- **Plugin bumped 4.5.0 → 4.6.0.** Rendered `.md` output is byte-identical to v4.5.0 for every file; source-format change only.

### Added

- **`tests/test_render_prompts.py::test_all_plugin_md_files_have_j2_source`** — permanent regression guard for the "every dispatched plugin `.md` has a `.md.j2` source" invariant. Asserts every `.md` under `agents/`, `commands/`, and `skills/*/SKILL.md` has a `.md.j2` sibling (excluding `README.md`, `ATTRIBUTION.md`, and the 3 documented refactor-orchestration template files). Replaces a previously-manual shell check with machine-enforced coverage. Cross-validated arch-review finding (tdd-validator + adr-guardian).

### Fixed

- **`scripts/pre-commit-check.sh`** error-path remediation hint no longer hardcodes `agents/*.md` — covers the whole plugin tree so a stale command or skill template triggers the correct staging command. Cross-validated arch-review finding (codex-arch-reviewer + refactor-advisor).
- **`update-plugin-versions.sh`** skill-discovery loops used lowercase `skill.md` patterns that silently matched zero files on case-sensitive filesystems (Linux/CI). Fixed to `SKILL.md` / `SKILL.md.j2` per the Anthropic skill-file convention. Caught by codex-review-agent during Step 16c /codex-review; macOS APFS case-insensitivity had been hiding the bug locally.
- **`plugins/requirements-framework/skills/requirements-framework-status/SKILL.md.j2`** component-inventory table updated 12→11 commands and 20→21 skills to match repo reality. Caught by codex-review-agent.
- **`plugins/requirements-framework/.claude-plugin/plugin.json`** `description` field updated from "19 development skills" to "21 development skills" to match repo reality.
- **`scripts/pre-commit-check.sh`** staging hint changed from `git add -u plugins/requirements-framework/` to `git add plugins/requirements-framework/` so newly-rendered `.md` siblings (untracked on first render of a new `.md.j2`) are also staged.

### Notes

- **No new partials extracted in Step 16c.** Empirical scan across all 32 files (11 commands + 21 skills) found no byte-identical kernels qualifying for shared extraction under Step 16b's discoverability rule. The recurring `> **Workflow position**: invoked by /req X` line in commands and the `# <Skill Name>` / `## Overview` structure in skills are *naming patterns*, not content kernels — extraction would require parameterised macros which Step 16b explicitly avoided.
- **Zero Jinja2 syntax collisions detected.** Pre-conversion `grep -E '\{\{|\{%'` across all 32 files returned zero matches; no file required `{% raw %}{% endraw %}` wrapping (contrast with Step 16b's frontend-reviewer JSX surprise). Every conversion was a pure verbatim copy with MD5-verified byte-identical render.
- **Three refactor-orchestration template files explicitly excluded** (`orchestrator-prompt-template.md`, `plan-template.md`, `retrospective-template.md`). They are skill-internal scaffolding read via `Read` at runtime — not dispatched prompts. Their `<placeholder>` syntax is meant for human filling. Converting would add file-pair maintenance for zero benefit.
- **`keep_trailing_newline=True` is load-bearing for the byte-identical render invariant.** Empirically verified during /codex-review (2026-05-24): the flag IS active in the `Environment.from_string()` code path that `hooks/lib/llm/templates.render()` uses. With the flag set, `from_string('hello\n').render()` returns `'hello\n'`; without it, the same input returns `'hello'` (Jinja2's default behavior strips one trailing newline). Removing the flag would silently strip trailing newlines from every rendered plugin `.md` file, breaking byte-identical render and producing a noisy diff across all 57 files. An earlier /arch-review note incorrectly claimed the flag was "inert in the string-render path" — that was wrong; `Path.read_text()` preserves the source newline and `keep_trailing_newline=True` is what preserves it through render.

### Known Limitations

- **`update-plugin-versions.sh` cross-plugin coupling**: the script walks every plugin tree in the repo (requirements-framework AND github-issues-plugin), so a housekeeping run for one plugin incidentally refreshes hashes in the other. In Step 16c the workaround is to manually revert any unintended `github-issues-plugin/` hash changes after the run. Scoping the version updater per-plugin is a backlog item.
- **`update-plugin-versions.sh` writes `*` marker into YAML**: when the script runs against a file with uncommitted modifications, it writes the `*` "modified locally" marker directly into the `git_hash:` YAML field instead of treating it as transient display state. Workaround: ensure the file is committed/refreshed before re-running the version updater. Backlog item.

### Changed (V3 dogfood follow-up, 2026-05-24)

- **`ReviewReport.summary` no longer has `Field(max_length=500)`**. The constraint propagated into the Anthropic SDK's `output_format` JSON schema, causing server-side validation to reject every worker response on large real diffs ("/summary: must NOT have more than 500 characters"). The model burned its `max_turns=5` retry budget producing schema-rejected outputs and the worker terminated with `error_max_turns`. Surfaced empirically by the V3 dogfood's full Step 16c branch run (`7c090b4..HEAD`, 8472 lines / 364K chars), which was rerun post-fix and succeeded ($1.96, 112.5s, 3 findings). Inline comment on `hooks/lib/llm/schemas.py:48` documents the rationale. Downstream consumers (aggregator, ledger storage, dogfood artifacts) must tolerate variable-length summaries — the prompt-level "1-3 sentence" guidance remains the authoritative constraint.

## [4.5.0] — 2026-05-24

### Changed

- **Step 16b — Plugin agents converted to Jinja2 templates (source format change only; rendered output is byte-identical).** All 25 plugin agents in `plugins/requirements-framework/agents/` now have a `.md.j2` source-of-truth alongside their existing `.md` rendered sibling. Claude Code continues to dispatch the `.md` file unchanged; the `.md.j2` is the file you edit.
- **`diff_scope_load.j2` partial** lands under `hooks/lib/llm/prompts/partials/`. 13 diff-scope review agents (`appsec-auditor`, `backward-compatibility-checker`, `code-reviewer`, `code-simplifier`, `codex-review-agent`, `comment-analyzer`, `compliance-auditor`, `frontend-reviewer`, `silent-failure-hunter`, `tenant-isolation-auditor`, `test-analyzer`, `tool-validator`, `type-design-analyzer`) reference it via `{% include 'partials/diff_scope_load.j2' %}`. MD5-verified byte-identical kernel across all 13 agents (`09f3eb3c657bc4397091348edbc95e58`) — single source of truth for the `Execute: prepare-diff-scope ...` boilerplate.
- **`update-plugin-versions.sh`** extended to discover `.md.j2` source files, skip rendered `.md` siblings whose `.md.j2` source exists (preserves git_hash semantics), and re-invoke `scripts/render_prompts.py` after hash updates to keep rendered output fresh.
- **`scripts/pre-commit-check.sh`** new — invokes `render_prompts.py --check` and fails the commit if any `.md` sibling is stale vs its `.md.j2` source. See DEVELOPMENT.md for install instructions.
- **Plugin bumped 4.4.0 → 4.5.0.** Rendered `.md` output is byte-identical to v4.4.0 for every agent; this is a source-format change only.

### Added

- **`tests/test_render_prompts.py`** (14 tests) — covers the 4 CLI modes of `scripts/render_prompts.py` (render, dry-run, check-fresh, check-stale), error paths (missing include, undefined runtime variable), and the zero-variable build-time contract for every `.md.j2` under `plugins/requirements-framework/`.
- **`tests/test_partials.py` extended** (6 → 16 tests) — new coverage for `diff_scope_load.j2` kernel, boundary-newline contract at include sites, no-vars contract, and nonexistent-partial negative test (TemplateNotFound).

### Notes

- **Only 1 of 5 candidate partials qualified for extraction.** Empirical kernel analysis during Patch 2 found that `severity_vocabulary`, `review_output_format`, `claude_md_loading`, and `critical_rules_tail` each lacked a byte-identical kernel across multiple agents (per-agent customization is genuine, not duplicated boilerplate). The plan's discoverability rule — "we never edit an agent's substantive text to fit a partial" — kept those 4 candidates inline. Future extraction may become viable as the agent corpus evolves; the test infrastructure landed in Patch 2 will protect any later additions.
- **`frontend-reviewer.md.j2` requires `{% raw %}{% endraw %}` markers** around one prose line (a React rule mentioning JSX `style={{...}}`) so Jinja2 doesn't try to parse the JSX double-brace as a template expression. This regression was caught immediately by `tests/test_render_prompts.py::test_plugin_templates_have_no_runtime_vars` — exactly the failure mode that test was designed to surface.
- **`.md` is now a build artifact**, not a hand-editable file. Editing the `.md` directly will be reverted on the next `./sync.sh deploy` or `scripts/render_prompts.py` run. Authors edit `.md.j2`; rendering produces the `.md` sibling.

## [4.4.0] — 2026-05-23

### Added

- **Step 16 — Jinja2 prompt template engine (phase 1: V3 + render plumbing).** First phase of a phased migration of all 60 prompt-like files in the project to Jinja2 (3 V3 worker prompts in this step; 25 plugin agents in Step 16b; 11 commands + 21 skills in Step 16c). This step ships the engine, converts the 3 V3 worker prompts, and stands up the build-time render plumbing that 16b/16c will consume.
- **`hooks/lib/llm/templates.py`** — Jinja2 Environment with `StrictUndefined`, custom `repr` filter (replaces Python's `{scope!r}`), and a `render(text, **vars)` helper. 16 tests.
- **3 V3 worker prompts converted to `.md.j2`**: `code-reviewer`, `review-aggregator`, `req-supervisor`. Old `.txt` files deleted (no backwards-compat shims, per project convention).
- **2 partials** under `prompts/partials/` designed for plugin agent reuse in Step 16b: `safety.j2` (universal review safety rules) and `project_conventions.j2` (optional CLAUDE.md head injection). 10 tests.
- **`load_prompt(name, *, label="production", **vars)` API** — replaces the previous `load_prompt(name).format(...)` pattern. Workers stop calling `.format()`; the loader fetches raw text from Langfuse (or `.md.j2` file fallback) and renders via `templates.render()` before returning. `label` is a reserved kwarg, not a template variable.
- **`scripts/render_prompts.py`** — build-time renderer for plugin `.md.j2` sources to `.md` siblings. Supports `--dry-run` and `--check` (for pre-commit). No-op for Step 16 (no plugin `.md.j2` exist yet); plumbing for Step 16b's first plugin agent migration.
- **`sync.sh deploy` extensions**: now globs `.md.j2` and `.j2` alongside `.py`/`.txt` in the recursive `hooks/lib/` deploy, cleans the prompts subtree before copy (kills orphan `.txt` files from the rename), and invokes `render_prompts.py` against the plugin tree before copying.
- **`scripts/sync_prompts_to_langfuse.py`** updated to glob `*.md.j2` and correctly strip both suffixes when registering Langfuse prompt names. Docstring carries the research grounding ([Langfuse FAQ](https://langfuse.com/faq/all/using-external-templating-libraries), [Discussion #4315](https://github.com/orgs/langfuse/discussions/4315), [Issue #1912](https://github.com/langfuse/langfuse/issues/1912)).
- **Smoke spike** at `hooks/lib/llm/_spikes/v3_jinja2_smoke.py` — loud-fail, no SDK calls. Renders all 3 prompts, asserts expected substrings appear, verifies StrictUndefined raises on missing vars, optional Langfuse round-trip when env present.

### Notes

- **Langfuse Playground compatibility loss is intentional and documented.** Templates with `{% %}` blocks can't be auto-rendered in the Playground; Langfuse's UI variable detection only sees top-level alphanumeric `{{ var }}`. Per the Langfuse FAQ, client-side rendering is the maintainer-blessed pattern — TTL caching + version-label rollback story (Step 12) remains intact.
- **The retrieval slot** (`{% if retrieved %}...{% endfor %}` in code-reviewer) is deferred until a worker actually reads `retrieval.json` (Step 14 only writes it for SessionStart injection today).
- **Step 16b is queued next** — converting 25 plugin agents using the same engine + render pipeline. Step 16c follows with commands + skills.

## [4.3.0] — 2026-05-23

### Added

- **Step 15 — Ragas eval harness + minimal golden set.** Closes the eval gap that has gated Step 20 (Sonnet pinning). `hooks/lib/llm/eval.py` exposes `GoldenCase`/`FindingMatch`/`EvalScore` Pydantic models, a deterministic `compute_finding_match` (file exact + line ±2 + category exact, best-of-N), and an async `score_case` that accepts an injected judge callable so tests stay Ragas-free.
- **Persistent `ClaudeSDKClient` judge** wired through `scripts/run_eval.py` — opens the SDK subprocess once per cycle and reuses it for every judge call, amortizing the ~7s startup cost across the run (5-case Haiku cycle measured at 288s wall-clock vs ~350s with per-call `query()`).
- **5 hand-authored synthetic golden cases** under `golden_set/cases/` covering security/CRITICAL (SQL injection), performance/IMPORTANT (N+1), logic/IMPORTANT (off-by-one), style/SUGGESTION (`Any` return), complexity/SUGGESTION (deep nesting). Each case has a matching unified-format `.diff` under `golden_set/diffs/`.
- **JSONL ledger** at `.git/requirements/eval/<timestamp>_<branch>.jsonl` — one `EvalScore` per line, well-formed Pydantic JSON, suitable for diffing across runs.
- **Optional Langfuse score posting** via `post_to_langfuse(trace_id, name, value)` — env-gated by `LANGFUSE_PUBLIC_KEY`, fail-open.
- **Loud-fail smoke spike** at `hooks/lib/llm/_spikes/v3_ragas_eval_smoke.py` — hard-fails if extras missing, golden set missing, or median `FindingMatch < 0.50` (proves the harness produces real signal).
- **30 new tests** in `tests/test_eval.py` — pure-helper + judge-mock + Langfuse-mock coverage.

### Notes

- The "Ragas judge" is currently a direct prompt-and-parse via `ClaudeSDKClient`, not a `BaseRagasLLM` adapter. Same idea (LLM judges agent output against a reference goal), simpler wiring. Upgrade to a real Ragas adapter is a deliberate future patch if v1's scoring proves insufficiently variant.
- No pre-PR gate, no nightly cron. Threshold automation comes after ≥3 cycles of human-confirmed baseline — wiring it now would be regression-detection theatre.
- `ToolCallAccuracy` deferred — code-reviewer doesn't use tools.

## [4.2.0] — 2026-05-23

### Added

- **Step 14 — SessionStart retrieval pipeline.** Closes the read side of the Step 13 Qdrant + local-embeddings loop. `hooks/lib/llm/memory.py` exposes `write_retrieval_json(branch, query, top_k, timeout_s, out_dir)` and `render_retrieval(hits, max_hits, min_score)`. On `SessionStart`, when `hooks.retrieval.enabled: true`, the hook embeds a heuristic query (branch + last 3 commit subjects), persists hits to `.git/requirements/retrieval-<branch>.json`, and prepends a compact "Similar prior sessions" markdown block to the injected briefing.
- **Hard SIGALRM timeout (default 1.5s)** on the SessionStart retrieval call so a hung Qdrant never blocks CLI startup.
- **Smoke spike** at `hooks/lib/llm/_spikes/v3_retrieval_pipeline_smoke.py` — loud-fail end-to-end verification against real Qdrant + `BAAI/bge-small-en-v1.5`.
- **26 new tests** in `tests/test_memory.py` (pure helpers + in-memory Qdrant round-trip + timeout path).
- **Config block** `hooks.retrieval.{enabled, top_k, max_hits, min_score, timeout_s}` (off by default).

### Notes

- LlamaIndex `Memory` composition (the original Step 14 plan) is deferred until a downstream consumer (worker/supervisor) needs a chat-message-shaped `Memory` object rather than a rendered string. Today, no consumer does — Step 18 supervisor takes a prompt string.
- Statusline retrieval tag is also deferred — SessionStart context injection is the only consumer this step.

## [4.0.0] — 2026-05-20

### Removed

- **Command `/plan-review`** — superseded by `/arch-review` (team-based, cross-validated) and `/req plan` (conductor). Marked deprecated in `3ca0bde`; removed here.
- **Command `/quality-check`** — superseded by `/deep-review` (cross-validated team review) and `/req review` (conductor). Marked deprecated in `3ca0bde`; removed here.
- **Config value `hooks.session_start.briefing_format: rich`** — `compact` has been the default since Step 01; the `rich` code path is removed from the dispatcher, `messages.py`/`message_validator.py`/`config.py`. Setting `briefing_format: rich` post-4.0 emits a deprecation warning and falls back to `compact`.

### Deprecated (carried into 4.0, scheduled for removal in 4.1+)

- **Agent `code-simplifier`** — marked DEPRECATED in `3ca0bde`. Retained in 4.0 because `/deep-review` and `/pre-commit` still actively spawn it; removal requires restructuring those commands first. Scheduled for removal in a future minor release after 4.0.

### Changed

- Plugin major version bumped to 4.0.0. The deprecated paths were introduced in `bdd0dc1` (workflow-position notes) and flagged in `3ca0bde` (deprecation marking); both commits are on master. The 2-week soak originally gating this removal was skipped per user decision on 2026-05-20 (clean break preferred over incremental accumulation of accidental dependencies).

### Migration

Update muscle memory and any local scripts:

| Old | New |
|---|---|
| `/plan-review` | `/arch-review` |
| `/quality-check` | `/deep-review` |
| `briefing_format: rich` | Remove the key entirely — `compact` is the default |

There is no compatibility shim. The 4.0.0 boundary is intentional.

---

## [3.0.0] — 2026-04-22

### Breaking
- **All 13 diff-based review agents now read pre-computed scope files** instead of running their own `git diff` in Step 1. They expect `/tmp/review_scope.txt` (changed files) and `/tmp/review.diff` (unified diff), either pre-computed by the invoking command (`/deep-review`, `/quality-check`) or auto-populated via `${CLAUDE_PLUGIN_ROOT}/scripts/prepare-diff-scope --ensure`. Consumers invoking review agents directly via the Task tool with a custom pre-populated `/tmp/code_review.diff` must migrate to the new paths.
- Affected agents: `code-reviewer`, `tool-validator`, `silent-failure-hunter`, `test-analyzer`, `type-design-analyzer`, `comment-analyzer`, `code-simplifier`, `backward-compatibility-checker`, `frontend-reviewer`, `codex-review-agent`, `tenant-isolation-auditor`, `appsec-auditor`, `compliance-auditor`.

### Added
- `hooks/lib/diff_scope.py` — unified review-scope resolution supporting empty/branch/range/PR# arguments, with 28 unit tests.
- `plugins/requirements-framework/scripts/prepare-diff-scope` — bash wrapper invoked by commands and agents.
- `hooks.diff_scope.base` config key (default `origin/master`) — override base ref for branch-vs-base resolution.
- `/deep-review` and `/quality-check` accept branch name, git range (`a..b` / `a...b`), or PR number (`1234` / `#1234`) as arguments.

### Fixed
- `--diff-filter` now includes `D` (deletions), so staged `git rm` is no longer silently skipped.
- Base ref is validated before diffing — missing `origin/master` no longer produces an empty scope silently.

### Developer
- New test file `hooks/test_diff_scope.py` with 30 tests using fixture git repos plus a fake-gh shim for PR-path tests.
- Plugin-version guard test ensures that when `diff_scope.py` is present the plugin version is ≥ 3.0.0.

### Known limitations
- `/quality-check` no longer reaches the `parallel` dispatch shortcut (the first positional arg is now consumed as the scope). Will be resolved in a follow-up by moving parallel-mode to a flag or env var.

### Internal
- Plugin wrapper script lives inside the plugin at `scripts/prepare-diff-scope` so commands can reference it via `${CLAUDE_PLUGIN_ROOT}/scripts/prepare-diff-scope`.
