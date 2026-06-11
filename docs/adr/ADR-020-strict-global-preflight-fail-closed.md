# ADR-020: Strict Global Preflight — Opt-In, Fail-Closed Adoption Gate

## Status

Approved (2026-06-11).

## Context

The framework's core design principle is *fail-open*: errors in infrastructure hooks
never block work (`CLAUDE.md` Design Principles; every lifecycle hook follows it). A
companion property is *inert-when-unconfigured*: a project with no requirements config
produces no gates and no error — just silence. Together these make the framework safe to
ship machine-wide, but they also create a failure mode the user explicitly does not want:
**a globally-installed plugin that silently does nothing in a misconfigured project, with
no signal that anything is wrong.**

This bit us concretely. A real adoption attempt in `solarmonkey-app` ran **2 sessions /
41 turns / ~$55 with only R5 observability active and the gated workflow completely
absent** — no session metrics, no registry entry, no gate ever fired — and nothing told
the user. (Evidence: trace content had zero framework fingerprints; the
`.git/requirements/sessions/` directory was empty across all worktrees.) The framework was
loaded but inert, and its own fail-open/inert-when-unconfigured design guaranteed there
would be no complaint.

The user wants the inverse of silent inertness: the plugin installed globally so it loads
in every project, and a **loud, blocking failure whenever a project isn't correctly set
up** (missing/invalid `requirements.local.yaml`, wrong Langfuse env, missing `uv`). This
deliberately inverts the framework's fail-open core — which is only acceptable if the
inversion is opt-in, narrowly scoped, and carries a guaranteed bailout. ADR-019 set the
precedent: opt-in observability is allowed to break the fail-open rule (fail-hard by
default) precisely because the user opted in. This ADR extends that precedent from
"report your own failure" to "block all work until compliant."

## Decision

### Decision 1 — Opt-in via a single master switch (default OFF)

Strict mode is governed by `strict_preflight: true` in the global
`~/.claude/requirements.yaml` (read through the normal config cascade,
`config.strict_preflight_enabled()`). **The default is `false` — the entire strict regime
is inert until explicitly turned on.** A globally-installed plugin therefore changes
nothing for any project until the user deliberately flips one key. This mirrors ADR-019's
`TRACE_TO_LANGFUSE`-gated opt-in: the dangerous behavior is dormant until the user asks
for it.

### Decision 2 — Strict-by-default-where-active; exceptions opt OUT

Once the master switch is on, **every** project is governed and must be compliant or it
blocks. Exceptions opt out, not in, via a per-project sentinel: `.claude/.rf-optout` makes
a project fully inert (today's behavior — no gates, no error). Gitignore it (personal
"this repo isn't ready") or commit it (team statement "this is not a framework repo"). The
asymmetry is intentional: with strict mode the whole point is that *forgetting* to
configure a project is loud, so silence must be the explicitly-chosen state.

### Decision 3 — Block on everything (fail-closed PreToolUse)

Any non-compliance — config OR Langfuse OR uv — refuses to let the user Edit/Write/Bash
until fixed or opted out. A new guarded branch in `hooks/check-requirements.py` consults
the evaluator before the normal requirement loop and, when strict mode is active and the
project is non-compliant, emits a `permissionDecision: "deny"` payload for every tool call
not on the escape allowlist. This is the deliberate inverse of the framework's fail-open
core, **scoped to strict mode only** — outside strict mode (the default), nothing here
runs.

### Decision 4 — Compliance = three structural invariants

A project is compliant iff **all three** hold:

1. `.claude/requirements.local.yaml` exists, parses as YAML, and has ≥1 enabled
   requirement.
2. Langfuse env structurally valid: the 5 Layer-1 keys present
   (`TRACE_TO_LANGFUSE`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST`,
   `CC_LANGFUSE_MAX_CHARS`), **none** of the 6 deprecated Layer-2 keys present (the set
   removed by the ADR-019 amendment), and creds non-empty.
3. `uv` resolvable on PATH.

### Decision 5 — Structural-only Langfuse check (no network in a blocking gate)

The Langfuse invariant is **purely structural** — key presence/absence and non-emptiness.
It is explicitly **not** a reachability or model-registration check. A network probe inside
a fail-closed gate would lock the user out of all work whenever Langfuse hiccups or the
machine is offline — exactly the global-lockout failure the rest of this design works to
prevent. Functional Langfuse health (reachability, cost/model registration) stays the
existing R5 trace-time warning (ADR-019), where a failure costs a lost trace, not a blocked
session.

### Decision 6 — Surgical escape allowlist, with precedence over ALL gates

A tight allowlist is **always allowed regardless of preflight state and takes precedence
over every gate** (the new preflight AND the existing workflow gates):

- Edit/Write/MultiEdit whose target is exactly `.claude/requirements.local.yaml` or
  `.claude/.rf-optout` (resolved and checked against the project root — path traversal
  outside the project is not allowed).
- Bash invoking `req` init/optout or the `/req-init` / `/req-optout` command paths.

This breaks the lock-yourself-out deadlock: from a blocked state you can *always* reach
compliance (write the config) or opt out (create the sentinel) without first satisfying any
gate. The allowlist is security-sensitive and is matched by exact target path / exact
command pattern — it must stay tight so "always allowed" can never be abused to bypass the
gate for an arbitrary edit.

### Decision 7 — Fail-open → fail-CLOSED inversion, scoped to strict mode

This is the riskiest decision and the reason the rest of the design exists. Inside strict
mode, the framework's fail-open principle is inverted: non-compliance blocks rather than
allows. Per ADR-019's precedent, breaking fail-open is acceptable **only** for behavior the
user explicitly opted into (here, the master switch) and **only** where the alternative —
silent inertness — is the failure the user is trying to eliminate. Everywhere outside
strict mode, fail-open is untouched and remains authoritative.

### Decision 8 — Safety contract: kill-switch + fail-SAFE evaluator

A fail-closed global gate is only acceptable with a guaranteed bailout, so two safety
mechanisms are non-negotiable:

- **Emergency env kill-switch `RF_STRICT_OFF=true`** instantly disables strict mode
  **without editing any config** — checked first, env wins. This is the guaranteed escape
  if a preflight bug ever locks the user out of everything (including the config files the
  escape allowlist protects).
- **Fail-SAFE evaluator.** Both call sites (the PreToolUse gate and the SessionStart
  briefing) wrap the evaluator in `try/except` and treat **any exception as "not strict /
  allow."** A bug inside the preflight can therefore degrade only to the framework's normal
  fail-open behavior — it can never escalate into a global lockout.

The compliance verdict is computed directly in both hooks (no session-state cache): the
checks are cheap, and a stale cache is a worse failure mode than re-evaluating.

## Consequences

### Positive

- **No more silent inertness.** The exact failure that wasted 41 turns in `solarmonkey-app`
  — a loaded-but-inert framework with zero signal — becomes loud and blocking the moment
  strict mode is on.
- **Misconfiguration is impossible to miss.** Every non-compliant invariant is surfaced at
  SessionStart with its exact fix command, and edits stay blocked until it's resolved or
  opted out.
- **Opt-in keeps the blast radius small.** Default-OFF means nothing changes for any project
  until the user flips one global key; the dangerous inversion is dormant by default.
- **Guaranteed bailout.** The kill-switch + fail-safe evaluator mean a preflight bug can
  never globally lock the user out — the worst case degrades to ordinary fail-open.

### Negative

- **Day-one friction is real.** With strict mode on, every repo you open locks until it's
  configured or opted-out; expect to run `/req-optout` (or `touch .claude/.rf-optout`) a lot
  at first.
- **Fail-closed is fragile by nature.** This inverts the framework's core principle and is
  the riskiest thing in the design; the env kill-switch and the defensively-guarded
  (fail-safe) evaluator are the mitigations, but the regime must be treated with care.
- **The escape allowlist is security-sensitive.** "Always allowed, precedence over all
  gates" is a powerful carve-out; it must stay tight (exact paths, exact command patterns,
  project-root-confined) so it can't be abused to bypass the gate for arbitrary edits.
- **A second failure-policy regime to remember.** Contributors must now distinguish
  fail-open (infrastructure hooks, library code — the default), fail-hard (opt-in
  observability, ADR-019), and fail-closed (opt-in strict mode, this ADR). All three are
  opt-in deviations from the fail-open default.

## Related ADRs and artifacts

- ADR-019: Stop-hook observability — the opt-in fail-hard precedent this design extends from
  "report your own failure" to "block work until compliant," and the source of the 5 Layer-1
  / 6 deprecated Layer-2 key sets reused by the Langfuse invariant.
- `hooks/lib/preflight.py` — pure compliance evaluator (`evaluate`, `is_escape_allowed`,
  `is_kill_switched`, `is_opted_out`) and the briefing formatter; dependency-injectable, no
  hook I/O.
- `hooks/check-requirements.py` — fail-closed PreToolUse gate (guarded, fail-safe) with the
  escape allowlist short-circuit.
- `hooks/handle-session-start.py` — loud non-compliance briefing at session start.
- `hooks/lib/config.py` — `strict_preflight_enabled()` master switch.
- `plugins/requirements-framework/commands/req-init.md` / `req-optout.md` — scaffold a
  `requirements.local.yaml` / create the opt-out sentinel.
- `.claude/plans/2026-06-11-strict-global-preflight-{design,plan}.md` — approved design + the
  task-by-task implementation plan.

## Decider

Harm Aalbers (user) — decisions confirmed 2026-06-11 during the strict-global-preflight
brainstorming session (recorded in the design doc's "Decisions" section).
