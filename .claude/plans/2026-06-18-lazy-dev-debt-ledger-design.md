# Lazy-Dev Ladder — Design

**Date:** 2026-06-18
**Status:** Design — pending approval
**Origin:** Adopt ponytail's core lazy-dev value (write less code, the proactive way) into requirements-framework. Scoping via the `lazy-dev-integration-scoping` workflow + user decisions.

## Goal (corrected)

Make the LLM **write less code** by biasing generation toward the least code that works — *before* code is written. Everything the framework already has (`code-simplifier`, `/simplify`, `code-reviewer`, `refactor-advisor`) is **reactive** (cleans up after code exists); nothing biases generation proactively. That proactive bias is ponytail's ladder, and it is genuinely additive.

**Honest caveat on "faster":** less code = fewer output tokens = usually faster + cheaper. But an always-on ruleset adds input tokens every turn, and on terse reasoning models the "deliberate through the rungs" step can cost *more* than the code it saves (ponytail's own benchmark says so). Expect net wins on capable instruction-following models (the Claude family); it is not guaranteed faster on every model/prompt. We keep the injected text compact to minimize the overhead, and it's disableable.

## Decisions (settled with user)

| Decision | Choice |
|----------|--------|
| What | The **ladder ruleset** (not the debt ledger) |
| Placement | **All three**: planning context, code-gen + reviewer agents, always-on main loop |
| Planning skills | **Also embed the ladder literally** in `writing-plans` + `brainstorming` (in addition to hook injection), kept in sync with the canonical source |
| Default | **On by default** (disableable via one config key) |
| Debt ledger | **Deferred** to a later version |
| Deprecated `code-simplifier` | **Retire it** (cleanup, no backwards-compat shims) |
| Intensity levels / Node hooks / statusline / `/review` / `/audit` | **Dropped** |

## The asset: one canonical ruleset

A single compact ruleset file (~15 lines), adapted from ponytail (MIT — credited in-file), in the framework's voice. No intensity levels, no `ponytail:` marker (ledger deferred), no Caveman reference. Contents:

- **The ladder** (stop at the first rung that holds): 1) Does this need to exist? (YAGNI — skip, say so in one line); 2) Stdlib does it? use it; 3) Native platform feature? use it; 4) Installed dependency? use it; 5) One line? one line; 6) Only then: the minimum that works.
- **Never lazy about** (the safety carve-outs, verbatim-critical): input validation at trust boundaries, error handling that prevents data loss, security, accessibility, anything explicitly requested. Between two same-size options, pick the edge-case-correct one (lazy = less code, not the flimsier algorithm).
- **Output discipline**: code first, then at most a couple of lines naming what was skipped and when to add it; don't defend simplifications with prose.

**Single source of truth.** The ruleset lives in exactly one file and is *injected*, never copied into many prompts — so there is no ponytail-style "13 copies + drift-check" problem.

## How the three placements are achieved (hook injection, not per-file copies)

The framework already has the injection seams. One ruleset file, read and injected at three existing hook points (all gated by the new flag):

1. **Always-on main loop** → `handle-session-start.py` injects the full ruleset once at session start, and `handle-prompt-submit.py` injects a compact one-line reminder on substantive prompts (mirrors the existing brainstorm-nudge dual-hook + dedup pattern, so it survives context summarization without re-injecting the full text every turn). → covers the **main loop**, which is also where **planning skills** (`writing-plans`, `brainstorming`) run, so plans inherit the bias.
2. **Subagents** → `handle-subagent-start.py` injects the ruleset into spawned subagents. Today it injects context only for *review* subagents; we broaden it to inject the ladder into code-touching subagents too. → covers the **code-gen + reviewer agents** (executors, code-reviewer, refactor-advisor) without editing each agent's `.md`.

This delivers all three user-selected placements from one source file + three small hook edits — far less surface (and zero drift risk) than embedding the text into ~5+ skill/agent files.

### Plus: literal embedding in the planning skills (user decision)

In addition to hook injection, embed the ladder **literally** into `writing-plans/SKILL.md` and `brainstorming/SKILL.md` so the guidance is visible in-prompt where plans are authored. To avoid copy-drift, prefer a **build-time include**: keep the canonical ruleset as a partial and `{% include %}` it from the skills' `.md.j2` templates so the rendered `.md` is materialized from the single source (like the existing `.md.j2 → .md` pipeline). **If `scripts/render_prompts.py` doesn't support includes**, fall back to a literal paste guarded by a **drift-guard test** (ponytail's `check-rule-copies.js` pattern) that asserts the embedded copies match the canonical ruleset byte-for-byte.

## Config

- `hooks.lazy_dev.enabled` — master switch, **default `true`**. When false, all three injections are skipped (fully inert). Honors the framework's fail-open contract: any error reading/injecting the ruleset → no injection, never blocks.
- (No per-seam sub-flags in v1 — YAGNI.)

## Retire deprecated `code-simplifier`

Remove `plugins/requirements-framework/agents/code-simplifier*`, its `plugin.json` registration, any `auto-satisfy`/command/docs references. Guarded by a test/grep asserting no dangling references remain. (Independent cleanup; the already-deprecated reactive simplifier isn't what delivers the proactive bias, and we're not keeping shims.)

## Architecture & data flow

- One ruleset file (new) → read by 3 hooks → injected as additional context. Stateless; nothing persists in `.git/requirements/`.
- Reuses the existing `emit_hook_context` / additionalContext mechanism and the brainstorm-nudge dedup marker pattern.

## Error handling

- Fail-open everywhere (matches the framework's design principle): missing/unreadable ruleset file, disabled flag, or any exception → simply no injection, session/turn proceeds normally.
- Compact prompt-submit reminder is deduped once per session (shared marker) so it never spams.

## Testing (`hooks/test_requirements.py`, custom `TestRunner`)

- Ruleset file loads; the loader returns the ladder text.
- `hooks.lazy_dev.enabled` default is `true`; when `false`, none of the three hooks inject (assert absence).
- SessionStart injects the full ruleset when enabled; prompt-submit injects the compact reminder and dedupes.
- Subagent-start injects the ladder into a spawned subagent context when enabled.
- **Drift guard**: the ladder embedded in `writing-plans`/`brainstorming` matches the canonical ruleset (skipped only if a build-time include makes it structurally impossible to drift — in which case assert the include resolves).
- Retirement: no dangling `code-simplifier` references.
- Bundle drift / `build --check` green after version bump.

## Plugin / packaging

- Hooks change → bump `plugin.json` (minor: new feature) + rebuild the hook bundle (`scripts/build_plugin_hooks.py`); `update-plugin-versions.sh` git_hash refresh in its own chore patch.
- New ruleset file shipped in the plugin and bundled.

## Risks

- **Behavior change for all users** (on by default): the framework now injects guidance every session. Mitigated by the compact text, the single disable key, and fail-open. Blast radius today is this repo + any project that installs the plugin.
- **Token overhead vs savings** is model-dependent (see caveat above) — compact text keeps overhead low; disable key is the escape hatch.
- Retiring `code-simplifier` is the only removal — guarded by the no-dangling-reference check.

## Deferred (not dropped forever)
- The `rf-debt:` marker + debt-ledger skill/command (the tracking half).
- Intensity levels (lite/full/ultra), `/lazy-review` delete-list, repo-wide `/audit`, any requirement gate.
