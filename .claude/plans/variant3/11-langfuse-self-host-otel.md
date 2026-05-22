# Step 11 — Self-host Langfuse + Claude Agent SDK observability

> **Revised 2026-05-22** per [ADR-016](../../../docs/adr/ADR-016-v3-claude-agent-sdk-substrate.md). The original Instructor/Anthropic-SDK assumptions are gone; this body is the design validated by the brainstorming session on 2026-05-22 and is what Step 11 actually implements.

## Goal

Stand up a local Langfuse v3 instance and wire OpenInference's Claude Agent SDK instrumentor against it. Every `claude_agent_sdk.query()` and `ClaudeSDKClient` call originating from V3 code is auto-traced. No behavior change for callers; observability is opt-in via env vars.

## Why now (Step 11 is foundational)

The 2026-05-22 spike (`hooks/lib/llm/_spikes/v3_spike.py`) showed 7x latency variance — 80s vs 583s — between two runs of the same workflow on identical inputs. Hypotheses (subprocess contention, Anthropic-side rate limiting under Max auth, invisible internal SDK retries) cannot be distinguished without traces. Without Step 11 in place first, every subsequent V3 step would be tuned against noise.

## Scope

### In scope

- Self-hosted Langfuse v3 + Postgres 16 via `infra/docker-compose.yml`
- `hooks/lib/llm/observability.py` populated — lazy-init OpenInference Claude Agent SDK instrumentor + OTLP exporter
- `hooks/lib/llm/_spikes/v3_langfuse_smoke.py` — runnable visual smoke test
- `tests/test_observability.py` — 6 dep-free unit tests
- README "Local observability" section with manual Langfuse bootstrap walkthrough
- Prep patch removing dead `[llm]` extras (`pydantic-ai`, `instructor`, `anthropic`, `llama-index-embeddings-openai`)

### Out of scope

- Prompt registry mirroring (Step 12)
- Token-cost dashboards (Step 17 territory)
- CI integration for the smoke script
- Cloud-hosted Langfuse
- Tracing of the `anthropic` SDK (no longer used post-ADR-016)

## Validated stack choices

| Layer | Choice | Source |
|---|---|---|
| Local Langfuse | `langfuse/langfuse:3` (Docker) | [Langfuse self-hosting docs](https://langfuse.com/self-hosting) |
| Backing store | `postgres:16` (volume-mounted) | Langfuse v3 requirement |
| Instrumentor | `openinference-instrumentation-claude-agent-sdk` only | [Langfuse Claude Agent SDK guide](https://langfuse.com/integrations/frameworks/claude-agent-sdk); ADR-016 ruled out Anthropic SDK direct use |
| Exporter | `opentelemetry-exporter-otlp-proto-http` (already in extras) | Standard OTel HTTP exporter; targets `LANGFUSE_HOST/api/public/otel/v1/traces` |
| Env contract | `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST` | Langfuse-native naming; `init_observability()` derives the OTLP URL + Basic-auth header |
| Init pattern | Lazy: first import of `observability` runs init; `init_observability()` also exported as idempotent explicit call | Honors the `hooks/lib/llm/__init__.py` "no eager third-party imports" rule |

## Architecture & data flow

```
caller code
   │
   │  from hooks.lib.llm.observability import init_observability
   │  init_observability()         # idempotent; module body also calls it on import
   ▼
hooks/lib/llm/observability.py
   ├─► reads LANGFUSE_PUBLIC_KEY / _SECRET_KEY / _HOST
   ├─► if any unset → log_once("observability disabled"), return
   ├─► try import openinference + opentelemetry
   │     ├─ ImportError → log_once("install with: pip install -e '.[llm]'"), return
   │     └─ ok → configure TracerProvider + OTLPSpanExporter(host + auth header)
   ├─► ClaudeAgentSDKInstrumentor().instrument()    # monkey-patches query() + ClaudeSDKClient
   └─► _initialized = True
        │
        ▼
caller does `from claude_agent_sdk import query; async for msg in query(...)`
   │
   │  instrumented wrapper opens span "claude_agent_sdk.query" with attributes:
   │    model, prompt, output_format schema name, input_tokens, output_tokens, cost_usd
   ▼
OTLPSpanExporter batches spans → POST → http://localhost:3000/api/public/otel/v1/traces
   │
   ▼
Langfuse ingests; trace appears in UI under /project/<id>/traces within ~1-5s
```

### Init point convention

Any V3 module that calls `claude_agent_sdk.query()` or instantiates `ClaudeSDKClient` MUST either:

- `from hooks.lib.llm.observability import init_observability; init_observability()` at module top — explicit, recommended.
- `from hooks.lib.llm import observability` — side-effect import; module body runs init.

Skipping both yields untraced calls. The smoke script demonstrates the recommended pattern.

### Failure modes

| Condition | Behavior | Surfaced? |
|---|---|---|
| Env vars unset | Silent skip; instrumentation never installed | One INFO log line per process |
| Extras not installed | `try/except ImportError`; log install hint | One INFO log line per process |
| Langfuse unreachable | OTel exporter buffers + retries with backoff; foreground unaffected | Visible only with `OTEL_LOG_LEVEL=debug` |
| Invalid keys (401) | Exporter logs retry warnings; eventually drops batch | UI shows no traces — discovered visually |
| Double init | `_initialized` flag short-circuits | None |
| Init internals raise | `try/except Exception` swallows; logs failure (full traceback only if `LANGFUSE_DEBUG=1`) | One INFO log line per process |

**Fail-open principle**: every code path that touches Langfuse degrades to "no traces" rather than "raise". Matches existing precedent in `hooks/lib/obsidian.py`.

## Files touched

### Prep patch (`step-11-pyproject-cleanup`)

```
pyproject.toml                      -4 lines (drop pydantic-ai, instructor, anthropic,
                                              llama-index-embeddings-openai)
                                    +1 comment pointing at ADR-016
```

### Observability patch (`step-11-observability-module`)

```
infra/docker-compose.yml            NEW — Langfuse v3 + Postgres 16, port 3000
infra/.env.example                  NEW — placeholders for the three LANGFUSE_* vars
hooks/lib/llm/observability.py      POPULATED — ~40 lines: env read, OTel setup,
                                                instrumentor install, _initialized guard
.gitignore                          +1 line: infra/.env
```

### Smoke + docs patch (`step-11-smoke-and-docs`)

```
hooks/lib/llm/_spikes/v3_langfuse_smoke.py  NEW — ~25 lines, one query() call with
                                                  output_format=ReviewFinding,
                                                  prints UI hint
tests/test_observability.py                 NEW — 6 dep-free tests (see below)
README.md                                   NEW section: "Local observability"
                                                  Manual Langfuse bootstrap walkthrough
```

## Verification

### Layer 1 — existing regression tests (no new wiring needed)

```bash
python3 hooks/test_requirements.py    # must still pass 1290/1290
```

### Layer 2 — new unit tests (no live Langfuse needed)

`tests/test_observability.py` — runs via the project's hand-rolled `TestRunner`:

```
test_disabled_when_no_public_key                     env unset → returns None, sets flag
test_disabled_on_import_error                        monkeypatch openinference → no raise
test_init_idempotent                                 second call returns immediately
test_logs_disabled_message_once                      two calls → one log line
test_module_import_triggers_init                     subprocess `import observability` → no raise
test_logs_init_failure_with_traceback_only_when_debug_set    LANGFUSE_DEBUG flag respected
```

### Layer 3 — manual spike verification

```bash
docker compose -f infra/docker-compose.yml up -d
# Bootstrap Langfuse UI (see README "Local observability"), copy keys
export LANGFUSE_PUBLIC_KEY=pk-... LANGFUSE_SECRET_KEY=sk-... LANGFUSE_HOST=http://localhost:3000

python3 hooks/lib/llm/_spikes/v3_langfuse_smoke.py
# → expects: one Sonnet call, prints "→ Now open http://localhost:3000/traces"

# Visual verification: trace appears within 5s, span attributes include
# model + token counts + cost
```

## Acceptance criteria

- [ ] `docker compose -f infra/docker-compose.yml up -d` starts Langfuse on `localhost:3000`
- [ ] `pyproject.toml [llm]` no longer lists `pydantic-ai`, `instructor`, `anthropic`, `llama-index-embeddings-openai`
- [ ] `python3 tests/test_observability.py` passes 6/6
- [ ] `python3 hooks/test_requirements.py` still passes 1290/1290 (no regression)
- [ ] With env vars set + Langfuse running, smoke script produces a visible trace in the UI
- [ ] With env vars unset, smoke script still completes — `query()` is unaffected, no exception, single INFO log line
- [ ] `from hooks.lib.llm import observability` in a fresh shell never raises
- [ ] README section explains the manual Langfuse bootstrap end-to-end

## Rollback

```bash
# Granular (per-patch) — within the stg stack:
stg pop                                           # smoke + docs
stg pop                                           # observability module
stg pop                                           # pyproject cleanup

# Local Langfuse teardown:
docker compose -f infra/docker-compose.yml down -v   # -v drops the postgres volume
```

## Effort

~1 day, split as: prep patch (10 min), observability module + docker (3-4 hr), smoke + tests + docs (3-4 hr).

## Depends on / blocks

- **Depends on**: Step 08 (LLM package scaffold), Step 09 (Pydantic schemas — for the smoke script's `output_format`)
- **Blocks**: Step 10 (worker pattern needs traces to debug latency), Step 12 (prompt registry rides on Langfuse), Step 17 (token-budget enforcement needs cost data from traces)

## Honest scope notes

- Langfuse's first-run bootstrap is manual (web UI: create user, create project, copy keys). The README walkthrough makes this explicit.
- Trace ingestion has a ~1-5s lag; the smoke script's "open UI" instruction accounts for this implicitly.
- Postgres data volume (`langfuse-db-data`) is preserved across `docker compose down` and lost only with `down -v`. Treat it like a dev database — usable across weeks for latency-drift analysis.
- The OTLP exporter's silent-retry behavior is a feature here. If you ever want loud failure for debugging, set `OTEL_LOG_LEVEL=debug` in your shell.
- Future migration to Langfuse Cloud or a shared team instance is a `LANGFUSE_HOST` change only — no Python code touches.
