# R5 — Full Claude Code Observability via Langfuse Stop Hook (Design)

**Date:** 2026-06-07
**Status:** APPROVED (brainstorming complete; next: writing-plans)
**Research basis:** `.claude/plans/2026-06-07-claude-code-max-langfuse-observability-research.md` (§6 recommended architecture)

## Decisions (confirmed with user — do not re-ask)

1. **Scope:** machine-wide, opt-in per project. Hook ships everywhere the plugin loads but is inert unless the project sets `TRACE_TO_LANGFUSE=true`.
2. **Delivery:** vendor upstream `langfuse_hook.py` into this repo (not the upstream marketplace plugin, not a manual `~/.claude/hooks` install).
3. **Registration:** bundled into the framework plugin — second `Stop` entry in `plugins/requirements-framework/hooks/hooks.json`. Machine-wide coverage arrives when/where the plugin is installed; today that's this repo (`--plugin-dir`).
4. **Creds:** per-project gitignored `.claude/settings.local.json` `env` block (pure upstream contract; no cred-loading code in the hook).
5. **Layers:** BOTH — Stop hook (content backbone) AND native OTEL beta traces (operational telemetry, structural-only).
6. **SDK isolation:** stdlib wrapper → `uv run` with PEP 723 inline deps (`langfuse>=4,<5`), insulating the global `langfuse==3.0.1` pin (V3 stack; pinned deliberately).
7. **Failure mode:** fail-HARD by default when tracing is enabled — exit 1 + stderr (visible warning, turn still ends; never exit 2, which would block the Stop). Per-project override `CC_LANGFUSE_FAIL_OPEN=true` → silent log-and-continue. Gate-closed projects: always silent exit 0.

## Architecture

### Layer 1 — content backbone (Stop hook)

```
Claude Code turn ends
  → Stop event → plugin hooks.json (2nd Stop entry)
    → hooks/langfuse-trace.py            (stdlib wrapper: gate + failure policy)
      → uv run hooks/_langfuse_hook.py   (vendored upstream, PEP 723: langfuse>=4,<5)
        → reads transcript JSONL incrementally (state: ~/.claude/state/langfuse_state.json)
        → pushes "Claude Code – Turn N" → "Claude Generation N" → "Tool: <name>"
          to self-hosted Langfuse (http://localhost:3000)
```

**New files** (source of truth in repo `hooks/`, mirrored into the plugin by `scripts/build_plugin_hooks.py`):

| File | Role |
|------|------|
| `hooks/langfuse-trace.py` | Thin python3-stdlib wrapper, the registered hook command. Reads stdin payload; exits 0 silently unless `TRACE_TO_LANGFUSE=true`; checks `uv` on PATH; pipes payload into `uv run --script _langfuse_hook.py` with a 45s subprocess timeout (under CC's 60s hook ceiling); applies the failure policy (decision 7). |
| `hooks/_langfuse_hook.py` | Vendored upstream `langfuse_hook.py` (pinned: `langfuse/Claude-Observability-Plugin@1266914`), unmodified except `# VENDOR-PATCH`-marked hunks: (a) PEP 723 header `dependencies = ["langfuse>=4,<5"]`, (b) accept `LANGFUSE_HOST` as alias for `LANGFUSE_BASE_URL`, (c) vendor header recording upstream source URL + commit + vendor date, (d) fail-hard policy — upstream's `main()` returns 0 on *every* failure path (missing creds, init failure, emit failures, unexpected exceptions), so decision 7 requires converting those swallow-points to stderr + exit 1 unless `CC_LANGFUSE_FAIL_OPEN=true`. Excluded from ruff (vendor code, not our style domain). |

`hooks.json` gains one `Stop` entry pointing at the wrapper. Independent of the existing `handle-stop.py` entry (requirement verification) — no interaction. Plugin version bump: **minor** (`plugin.json` + `marketplace.json` in the same patch).

### Layer 2 — operational telemetry (native OTEL beta traces)

Pure env-var config, no code. Per opted-in project:

```
CLAUDE_CODE_ENABLE_TELEMETRY=1
CLAUDE_CODE_ENHANCED_TELEMETRY_BETA=1
OTEL_TRACES_EXPORTER=otlp
OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:3000/api/public/otel
OTEL_EXPORTER_OTLP_HEADERS=Authorization=Basic <b64(pk:sk)>,x-langfuse-ingestion-version=4
```

Spans: `claude_code.interaction` → `claude_code.llm_request` (tokens, TTFT, stop_reason) → `claude_code.tool`.

- **Structural-only** — no `OTEL_LOG_*` content gates (content arrives in full via Layer 1; 60KB-capped span-attr duplication is noise).
- No metrics/logs exporters — Langfuse ingests the traces signal only.
- **Best-effort/beta**: a Claude Code update may break span names/attrs; Layer 1 is unaffected.

### Configuration wiring (both layers)

Everything lives in each opted-in project's gitignored `.claude/settings.local.json` `env` block:

| Var | Value |
|-----|-------|
| `TRACE_TO_LANGFUSE` | `"true"` (master gate, Layer 1) |
| `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` | from `infra/.env` (this repo) |
| `LANGFUSE_HOST` | `http://localhost:3000` |
| `CC_LANGFUSE_MAX_CHARS` | `100000` (5× upstream default 20k) |
| `CC_LANGFUSE_FAIL_OPEN` | unset (= fail-hard default); `"true"` to silence |
| `CC_LANGFUSE_DEBUG` | optional, verbose logging |
| + the six OTEL vars above | Layer 2 |

**Setup generator:** new `scripts/setup_langfuse_tracing.py` — sources creds from `infra/.env` when run in this repo (else from existing env), computes the base64 Basic header, **prints** the ready-to-paste env block; `--write` merges into `.claude/settings.local.json` (creating if absent). Hard-fails on missing creds or unreachable Langfuse (`--skip-ping` to bypass) — per the loud-failure rule for scripts.

This repo is the first opted-in consumer.

## Error handling

- Gate closed (`TRACE_TO_LANGFUSE` ≠ `"true"`): silent exit 0, no subprocess, no deps touched — the inert path costs one stdlib python startup.
- Gate open + failure (uv missing, resolve offline, Langfuse down, subprocess crash, timeout): **default** → clear one-line message to stderr + exit 1 (visible warning; turn ends normally). With `CC_LANGFUSE_FAIL_OPEN=true` → log to `~/.claude/state/langfuse_hook.log` + exit 0.
- **Never exit 2** (would block the Stop event and force Claude to continue).
- 45s subprocess timeout → kill, then failure policy applies.
- Vendored script runs in a subprocess; even a hard crash can't propagate past the wrapper's policy.

## Testing

- **Dep-free script-style tests** `tests/test_langfuse_trace_hook.py` (run per-file, like ci.yml; NOT pytest):
  - gate closed → exit 0, no subprocess spawn
  - `uv` absent + gate open → exit 1 + stderr message (default); exit 0 with `CC_LANGFUSE_FAIL_OPEN=true`
  - gate open → correct `uv run --script` invocation, stdin payload forwarded (subprocess mocked)
  - subprocess nonzero/timeout → failure policy honored
  - never-exit-2 invariant
- Vendored `_langfuse_hook.py` is **not** unit-tested — vendor drop; updates are re-vendor diffs against the recorded upstream commit.
- `build_plugin_hooks.py --check` covers plugin-mirror freshness automatically.
- **Manual verification (completion evidence):** opt this repo in, run a real turn, confirm `Claude Code – Turn N` trace via `langfuse-cli`; confirm a `claude_code.interaction` span arrives (Layer 2).

## Known limitations & risks (accepted)

| Item | Posture |
|------|---------|
| Stop-hook traces vs V3 fan-out OpenInference traces are not linked — `/v3-review` shows up twice | Accepted (single-user) |
| No cost figures until a model-price mapping is added in the Langfuse UI | Optional follow-up, manual |
| JSONL / Stop-payload schema drift breaks Layer 1 | Now LOUD by default (exit-1 warning) for runtime failures; silent only for schema-garbling — periodic spot-check |
| Beta-OTEL span names/attrs change on CC update | Layer 2 is best-effort; Layer 1 unaffected |
| Upstream hook uses SDK v4 internals (`_otel_tracer`, `_create_observation_from_otel_span`) | Pin `<5`; re-vendor consciously |

## Out of scope

- PII masking (explicit project decision).
- Bumping the project's `langfuse` v3 Python SDK pin (isolation makes it unnecessary; see `references/sdk-upgrade.md` for the future migration).
- Proxy interception / Agent-SDK instrumentation routes (rejected by research: ToS risk / OAuth-incompatible).
- Batch backfill of historical `~/.claude/projects/**/*.jsonl` transcripts (research §5.3; possible follow-up).
