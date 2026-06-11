# Design: Strict Global Preflight (fail-closed adoption gate)

**Date:** 2026-06-11
**Status:** Design approved (brainstorming complete) — feeds `/write-plan`.
**Branch:** `feat/strict-global-preflight`

## Problem

The framework is installed nowhere machine-wide (uninstalled 2026-06-05), so day-to-day
projects don't load it unless launched with `--plugin-dir`. Worse, even when loaded, the
framework is **fail-open and inert when unconfigured**: a project with no requirements
config produces no gates and no error — just silence. This bit us concretely: a real
adoption attempt in `solarmonkey-app` ran 2 sessions / 41 turns / ~$55 with **only R5
observability active and the gated workflow completely absent** — no session metrics, no
registry entry, no gate ever fired — and nothing told the user. (Evidence: trace content
had zero framework fingerprints; `.git/requirements/sessions/` empty across all worktrees.)

The user wants the inverse of silent inertness: **the plugin installed globally so it loads
in every project, and a loud, blocking failure whenever a project isn't correctly set up**
(missing/invalid `requirements.local.yaml`, wrong Langfuse env, missing `uv`, …).

## Decisions (locked in brainstorming)

1. **Global install from GitHub** (not the local dev checkout): `/plugin marketplace add
   HarmAalbers/claude-requirements-framework` + `/plugin install
   requirements-framework@requirements-framework`. Caches from GitHub into
   `~/.claude/plugins/cache/…`, independent of `~/Tools/claude-requirements-framework`.
   **No double-execution** with the dev copy: when launched with `--plugin-dir`, the local
   copy *overrides* the marketplace copy for that session (only one set of hooks runs).
2. **Auto-update on master pushes.** Server side already done (`publish.yml` bumps version +
   syncs `marketplace.json` every push). Client side is opt-in: enable per-marketplace
   auto-update (UI toggle, or `extraKnownMarketplaces.<name>.autoUpdate: true` in
   `~/.claude/settings.json`). Updates apply at session startup; `autoUpdatesChannel: latest`
   already set.
3. **Strict-by-default everywhere.** Every project must be compliant or it blocks. Exceptions
   opt OUT, not in.
4. **Block on everything (fail-closed).** Any non-compliance — config OR Langfuse OR uv —
   refuses to let the user edit/bash until fixed or opted out. The deliberate inverse of the
   framework's fail-open core, scoped to strict mode (precedent: R5 opt-in fail-hard,
   ADR-019).
5. **Escape hatch (minimal, surgical).** Always allowed regardless of preflight state, and
   taking precedence over ALL gates (the new preflight AND the existing workflow gates):
   editing `.claude/requirements.local.yaml`, creating the opt-out sentinel, and the
   `req`/init/optout actions. Everything else blocked. This breaks the lock-yourself-out
   deadlock (you can always reach compliance or opt out) — and would also have prevented the
   friction we hit writing solarmonkey's config.
6. **Opt-out sentinel:** `.claude/.rf-optout` → project goes fully inert (today's behavior).
   Gitignore it (personal) or commit it (team says "not a framework repo").
7. **Structural Langfuse check only** in the blocking gate (5-key block present, no stale
   Layer-2 keys, non-empty creds). NOT reachability / model-registration — a network check
   in a blocking gate would lock the user out whenever Langfuse hiccups. Reachability/cost
   stays the existing R5 trace-time warning.
8. **Two safety mechanisms (non-negotiable for a fail-closed global gate):**
   - **Global master switch** `strict_preflight: true|false` in `~/.claude/requirements.yaml`
     — the whole strict regime toggles in one place.
   - **Emergency env kill-switch** `RF_STRICT_OFF=true` — instantly disables strict mode
     **without editing any config**, the guaranteed bailout if a preflight bug locks the user
     out of everything.

## Compliance definition (all must hold, else block)

1. `.claude/requirements.local.yaml` exists, parses as YAML, and has ≥1 enabled requirement.
2. Langfuse env structurally valid: the 5 Layer-1 keys present, none of the 6 deprecated
   Layer-2 keys present, creds non-empty.
3. `uv` resolvable on PATH.

A project is exempt from all of the above if `.claude/.rf-optout` exists, or the global
master switch is off, or `RF_STRICT_OFF=true`.

## Architecture

- **SessionStart preflight** (extend `handle-session-start.py` or a new
  `handle-preflight.py`): when strict mode is on and the project is not opted out, compute
  the compliance verdict, render a loud briefing listing each failed invariant + its exact
  fix command, and persist the verdict to session state (cached so PreToolUse needn't
  re-validate every call).
- **Fail-closed PreToolUse gate** (a new strategy / branch in `check-requirements.py`): if
  the cached verdict is non-compliant, BLOCK every Edit/Write/MultiEdit/Bash — UNLESS the
  call is on the escape allowlist (writes to `.claude/requirements.local.yaml` or
  `.claude/.rf-optout`; `req`/init/optout invocations). The allowlist short-circuits the
  entire requirement check, not just the preflight.
- **`/req-init` and `/req-optout` slash-commands** (plugin commands, so they ride the
  marketplace install with no `install.sh`): scaffold a `requirements.local.yaml` and create
  the opt-out sentinel respectively.
- **Switches:** master switch read from the global config; kill-switch read from env at the
  top of both the preflight and the gate (env wins, evaluated first, fail-safe).

## Testing / acceptance

- Unit: compliance evaluator (each invariant pass/fail; opt-out; master switch; kill-switch
  precedence) under `tests/` (repo TestRunner, no network — mock PATH/env/files).
- Unit: escape allowlist (config + sentinel writes + req commands allowed when
  non-compliant; everything else blocked).
- Fail-safe: a thrown exception inside the preflight must NOT hard-block (the kill-switch and
  a guarded evaluator prevent global lockout) — explicit regression test.
- Acceptance: in a temp git repo, a strict session blocks an arbitrary edit, allows writing
  `requirements.local.yaml`, and unblocks once compliant; `.rf-optout` makes it inert;
  `RF_STRICT_OFF=true` disables instantly.
- Full suite + `render_prompts.py --check` + `build_plugin_hooks.py --check` green; plugin
  version bumped (new commands/hooks → minor).

## Risks / honest caveats

- **Day-one friction is real:** every repo you open locks until configured or opted-out;
  expect to `touch .rf-optout` a lot at first.
- **Fail-closed is fragile by nature:** a preflight bug could block all work everywhere. The
  env kill-switch + a defensively-guarded evaluator are the mitigations, but this inverts the
  framework's core principle and is the riskiest thing in the design.
- **Escape allowlist is security-sensitive:** it must be tight (exact paths/commands) so
  "always allowed" can't be abused to bypass the gate for arbitrary edits.

## Out of scope / deferred

- Functional Langfuse checks (reachability, model registration) in the blocking gate — stays
  a trace-time warning.
- The earlier `--plugin-dir` launcher / adoption-ladder design (superseded by global install).
- Tiered/warn-only failure modes (rejected in favor of block-on-everything).
