# ADR-019: Stop-Hook Observability — Vendored Hook, Fail-Hard Opt-In

## Status

Approved (2026-06-07)

## Context

R5 adds full-content session tracing of Claude Code turns to the self-hosted Langfuse
instance (`http://localhost:3000`). The design (`.claude/plans/2026-06-07-r5-stop-hook-observability-design.md`)
ships two layers:

- **Layer 1 (content backbone):** a Stop hook registered as the second `Stop` entry in the
  plugin's `hooks.json`. A stdlib wrapper (`hooks/langfuse-trace.py`) gates on
  `TRACE_TO_LANGFUSE=true` and delegates to a vendored upstream script
  (`hooks/_langfuse_hook.py`, from `langfuse/Claude-Observability-Plugin`) that reads the
  transcript JSONL incrementally and pushes turn/generation/tool observations to Langfuse.
- **Layer 2 (operational telemetry):** Claude Code's native OTEL beta traces, pure env-var
  config written by `scripts/setup_langfuse_tracing.py`, structural-only (no content).

Three tensions had to be resolved, each cutting against an established framework position:

1. **Failure policy.** The framework's core design principle is *fail-open*: errors in
   infrastructure hooks never block work (`CLAUDE.md` Design Principles; every lifecycle
   hook follows it). But an observability hook the user has *explicitly opted into* that
   fails silently means silently losing the data the user asked for — the failure mode the
   loud-failure rule for scripts was written to prevent.
2. **Dependency isolation.** The upstream hook requires the Langfuse Python SDK v4
   (`_otel_tracer`, `_create_observation_from_otel_span` internals), while this repo's V3
   review stack deliberately pins `langfuse>=3.0` (v3 idioms; see ADR-016 and
   `references/sdk-upgrade.md`). Installing v4 globally would break the pin.
3. **Runtime prerequisites.** The isolation mechanism (`uv run --script` with PEP 723
   inline deps) makes `uv` a runtime dependency — but the framework plugin loads in every
   project on the machine, most of which will never opt in.

## Decision

### Decision 1 — Fail-hard exception for opt-in observability hooks

**The fail-open principle applies to infrastructure hooks the user did not ask for.
Observability hooks the user explicitly opted into fail HARD by default — a visible
one-line stderr warning + exit 1.**

Precisely:

- **Gate closed** (`TRACE_TO_LANGFUSE` ≠ `"true"`): silent exit 0, no subprocess, no
  dependencies touched. The fail-open principle holds in full — projects that never opt
  in cannot be affected by any failure in this stack.
- **Gate open + failure** (uv missing, dependency resolve offline, Langfuse down,
  subprocess crash, default 45s timeout): one clear line to stderr + **exit 1**. The turn ends
  normally; the user sees that a trace was lost.
- **Floor: NEVER exit 2.** A Stop hook exiting 2 blocks the Stop event and forces Claude
  to continue the turn — observability must never obstruct work, only report its own
  failure. Exit codes are restricted to 0 and 1 on every path, including the vendored
  script (which runs in a subprocess, so even a hard crash cannot propagate past the
  wrapper's policy).
- **Override:** `CC_LANGFUSE_FAIL_OPEN=true` restores silent fail-open behavior
  (exit 0; emit-turn failures are still logged at INFO level to
  `~/.claude/state/langfuse_hook.log`; wrapper-level failures are not logged
  anywhere; `CC_LANGFUSE_DEBUG=true` adds verbose debug lines) for users who
  prefer best-effort tracing.

Rationale: opt-in observability silently failing means silently losing data the user
explicitly asked for. A visible one-line warning is user feedback, not obstruction. This
mirrors the existing carve-out for smoke/spike scripts (hard-fail loudly on missing
prereqs) while keeping library code and non-opted-in paths strictly fail-open.

### Decision 2 — Vendored-upstream-code pattern

**Upstream hook code is vendored at an exact pinned commit, with local modifications
marked and counted, and excluded from this repo's lint domain.**

The pattern, applied to `hooks/_langfuse_hook.py`
(vendored from `langfuse/Claude-Observability-Plugin@1266914dc235dab485ed0640573047644dd39ce8`):

- **Pin discipline.** The file carries a provenance header naming the source repo, source
  path, exact upstream commit SHA, and vendor date. This extends ADR-016's pinning
  discipline for third-party compose files ("pin to a specific commit SHA, not a branch;
  the fetched file MUST carry a header comment naming the source repo and SHA") from
  infra files to vendored code.
- **`# VENDOR-PATCH` hunk convention.** Every local modification is marked with a
  `# VENDOR-PATCH` comment naming its hunk letter. The header enumerates the hunks and
  includes a **coverage-count line** for the fail-hard hunk (currently: 5 patched failure
  points — import guard, missing creds, client init, emit loop, unexpected exception).
  The count must be re-verified on every re-vendor so a refactored upstream cannot
  silently drop a patched failure point.
- **Re-vendor procedure.** Updates are deliberate, never floating: (1) fetch upstream at
  the new pinned commit to a scratch path, (2) diff the scratch copy against the current
  vendored file to locate the VENDOR-PATCH hunks, then re-apply them, (3) re-verify the
  coverage count, (4) update the provenance header fields (commit SHA, vendor date),
  (5) rebuild the plugin mirror (`scripts/build_plugin_hooks.py`). Note that the vendored
  code depends on the SDK-internal attributes `_otel_tracer`, `_otel_span`, and
  `_create_observation_from_otel_span` — verify all three still exist on re-vendor.
- **PEP 723 + `uv run --script` isolation.** The vendored script declares
  `dependencies = ["langfuse>=4,<5"]` inline and runs under `uv run --script` in an
  ephemeral environment. The repo's deliberately pinned `langfuse>=3.0` (V3 stack,
  ADR-016) is untouched — the two SDK majors never share an environment. The `<5` ceiling
  exists because the hook uses SDK v4 internals; a v5 release requires a conscious
  re-vendor, not a silent resolve.
- **Ruff exemption.** Vendored code is not our style domain — linting it would only
  generate diff noise against upstream and make re-vendoring harder. `ruff.toml` excludes
  `hooks/_langfuse_hook.py` via `extend-exclude` with `force-exclude = true` (so the
  exclusion holds even when files are passed to ruff explicitly, as the /v3-review tool
  gate does). The vendored file is also not unit-tested — it is a vendor drop; updates
  are re-vendor diffs against the recorded upstream commit.

### Decision 3 — uv as a runtime prerequisite for opted-in projects only

**`uv` is required on PATH only in projects that set `TRACE_TO_LANGFUSE=true`. The
gate-closed path is stdlib-only and dependency-free.**

- The registered hook command is the stdlib wrapper (`hooks/langfuse-trace.py`). With the
  gate closed it exits 0 before any subprocess or import beyond the standard library —
  projects that never opt in need nothing installed and pay only one stdlib Python
  startup per Stop event.
- With the gate open and `uv` missing, the wrapper applies Decision 1: a loud exit-1
  stderr warning naming the missing prerequisite (silenced by `CC_LANGFUSE_FAIL_OPEN=true`).
- `scripts/setup_langfuse_tracing.py --write` warms the uv cache at opt-in time so the
  first traced turn does not pay the dependency-resolve latency inside the hook's default
  45s subprocess timeout.

### Coexistence with the V3 review stack

Layer 2 (native OTEL beta traces) and the V3 review stack's OpenInference instrumentation
(`hooks/lib/llm/observability.py`, ADR-016 Step 11) both export OTLP traces to the same
Langfuse instance, from **parallel, non-overlapping env-var namespaces**:

- Layer 2 uses the **generic** keys: `OTEL_EXPORTER_OTLP_ENDPOINT`,
  `OTEL_EXPORTER_OTLP_HEADERS`, `OTEL_EXPORTER_OTLP_PROTOCOL` (set per-project by
  `setup_langfuse_tracing.py`).
- The V3 stack uses the **signal-specific** keys: `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`,
  `OTEL_EXPORTER_OTLP_TRACES_HEADERS`, `OTEL_EXPORTER_OTLP_TRACES_PROTOCOL` (set
  programmatically by `observability.py`).

Per the OTLP exporter spec, signal-specific keys win over generic keys when both are
present — so in a V3 review process, `observability.py`'s configuration takes precedence
without clobbering the project-level Layer 2 env. Both pipelines coexist; neither needs
to know about the other. **Revisit this section if either side is refactored** to change
its env-var namespace (e.g., a future `observability.py` switch to generic keys would
create a real conflict).

A known, accepted overlap: a `/v3-review` run shows up twice in Langfuse — once via its
own OpenInference traces, once inside the Stop-hook turn trace. The two are not linked
(single-user deployment; accepted in the R5 design).

### Stop-hook chain semantics

`langfuse-trace.py` is the second `Stop` entry in the plugin's `hooks.json`, after
`handle-stop.py` (requirement verification). Claude Code currently (observed v2.x,
2026-06) runs hooks in the same matcher **in parallel**, which has three consequences
worth recording:

- **A turn blocked by `handle-stop.py` may still be traced.** Requirement verification
  exiting 2 (block the stop) does not suppress the tracing hook — the trace reflects the
  turn as it ran, including the block.
- **Re-fired Stop events do not duplicate traces.** When a blocked stop causes the Stop
  event to fire again later, the vendored script's incremental watermark state
  (`~/.claude/state/langfuse_state.json`) plus message-id dedup (assistant messages by
  `message.id`, tool results by `tool_use_id`; latest wins) ensure already-pushed
  observations are not re-emitted.
- **`langfuse-trace.py` never blocks the chain.** Exit codes 0/1 only (Decision 1's
  floor); the tracing entry cannot interfere with requirement verification's verdict.

## Consequences

### Positive

- **Lost traces are visible.** An opted-in user finds out the moment tracing breaks
  (Langfuse down, uv missing, schema drift surfacing as a runtime error) instead of
  discovering a gap in the data days later.
- **The langfuse v3 pin survives.** V4-requiring upstream code runs without touching the
  V3 stack's deliberately pinned SDK — no migration forced, no dual-pin conflict.
- **Zero footprint for non-opted-in projects.** The plugin can ship the hook machine-wide;
  the gate-closed path is inert and dependency-free.
- **Re-vendoring is mechanical.** The provenance header + VENDOR-PATCH convention +
  coverage count turn "update the upstream hook" into a checklist, not an archaeology
  exercise.

### Negative

- **A second failure-policy regime to remember.** Contributors must now distinguish
  fail-open (infrastructure hooks, library code) from fail-hard (opt-in observability,
  smoke/spike scripts). Mitigation: the wrapper and this ADR are the only places the
  policy lives; the floor (never exit 2) is shared.
- **Vendored code drifts from upstream.** Until re-vendored, upstream fixes don't arrive.
  The exact-SHA pin makes the drift measurable but not self-healing.
- **uv becomes a soft machine dependency.** Any project that opts in inherits the
  prerequisite; the loud warning makes this discoverable but not avoidable.
- **Stop-event latency.** Every Stop in an opted-in project pays the wrapper + subprocess
  cost (bounded by the default 45s timeout, under Claude Code's 60s hook ceiling).
- **Trace accumulation with no TTL.** Traces accumulate in the self-hosted ClickHouse with
  no TTL — set a Langfuse data-retention policy or purge periodically if traced sessions
  may contain sensitive work content.

## Related ADRs and artifacts

- ADR-016: V3 on Claude Agent SDK substrate — the langfuse v3 pin this design isolates
  against, and the SHA-pinning discipline Decision 2 extends.
- `.claude/plans/2026-06-07-r5-stop-hook-observability-design.md` — approved design with
  the full decision log and architecture diagrams.
- `hooks/langfuse-trace.py` — stdlib wrapper (gate + failure policy).
- `hooks/_langfuse_hook.py` — vendored upstream hook (provenance header at top).
- `scripts/setup_langfuse_tracing.py` — opt-in env-block generator (`--write`).
- `tests/test_langfuse_trace_hook.py` — dep-free wrapper tests (incl. never-exit-2
  invariant).
- `ruff.toml` — vendored-file exclusion + `force-exclude` rationale.

## Decider

Harm Aalbers (user) — decisions confirmed 2026-06-07 during the R5 brainstorming session
(recorded in the design doc's "Decisions" section); fail-hard amendment A6 and coexistence
amendments A7-i/ii from the arch-review of the implementation plan.
