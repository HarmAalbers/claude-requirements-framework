# Design: R5 Observability Hardening

**Date:** 2026-06-08
**Status:** Design approved (brainstorming complete) — feeds `/writing-plans`.
**Origin:** Langfuse error-analysis of a traced Claude Code session
(`solarmonkey-app` project `cmq51xsu50012nz08lb28so5h`, session `3de54086`).
A 34-agent workflow produced 24 verified-grounded findings; this design acts on
the observability subset (Buckets 1+2). Bucket 3 (agent behavior) is deferred.

## Problem

R5 (Langfuse Stop-hook observability, shipped to master in plugin 4.16.0,
ADR-019) traces every Claude Code turn, but the data is incomplete for **every**
opted-in project — not just solarmonkey-app:

1. **Cost reads $0.** Langfuse has no model definition for `claude-opus-4-8`
   (or the `[1m]` variant) / `claude-haiku-4-5`, so `calculatedTotalCost=0` on
   all R5 generations despite fully-populated `usageDetails` (incl. cache
   breakdown). Real cost of the analyzed session ≈ **$0.68** (see pricing note).
2. **Double tracing.** Each turn is traced twice — R5 Stop-hook traces
   (`Claude Code - Turn N`, token+content complete) AND Layer-2 OTEL beta traces
   (`claude_code.interaction`). The Layer-2 generations are **hollow**:
   `usageDetails={}`, `promptTokens=0`, no input/output content (token counts are
   trapped as strings in `metadata.attributes`), and TOOL observations have
   null input/output. Layer-2 adds noise and 2× trace volume without carrying
   data R5 lacks — except `ttft_ms` (1.4–3.2s, in OTEL metadata) and native CC
   interaction/timing spans.
3. **Missing enrichment.** R5 traces lack `userId`, `release`, and project
   `tags` — all available in the transcript / OTEL resourceAttributes.

These are framework feature-gaps, so the fix is productized into the R5 setup
path and backfilled to existing projects, not patched per-project.

### Pricing note (corrects a workflow finding)

The analysis agent assumed Opus at $15/$75 per MTok (old Opus 3 / 4.0–4.5
pricing) → $2.04. **Verified via the claude-api skill, Opus 4.8 is $5/$25**, so
the real session cost is ~$0.68. Authoritative per-MTok pricing for the model
definitions (cache write = 1.25× input, cache read = 0.1× input):

| Model (regex)         | input | output | cache write | cache read |
|-----------------------|-------|--------|-------------|------------|
| `claude-opus-4-8.*`   | 5.00  | 25.00  | 6.25        | 0.50       |
| `claude-haiku-4-5.*`  | 1.00  | 5.00   | 1.25        | 0.10       |
| `claude-sonnet-4-6.*` | 3.00  | 15.00  | 3.75        | 0.30       |

(Sonnet included because this framework's own V3 workers run Sonnet after
Step 20.)

## Decisions (locked in brainstorming)

- **Scope:** observability hardening (Buckets 1+2). Bucket 3 deferred (inherent
  agent behavior; revisit only if it recurs).
- **Tracing model:** R5 is the single enriched source of truth. **Layer-2 OTEL
  is turned off.** Accepted trade: lose `ttft` and native `claude_code.interaction`
  spans (unless ttft is recoverable from the transcript — see below).
- **Productize, then backfill** — fix the R5 feature for all projects, then
  re-run setup for solarmonkey-app + this repo.

## Approach (① Productize into the R5 feature)

### 1. `scripts/sync_langfuse_models.py` (new)
Idempotent model-pricing sync, sibling to `sync_prompts_to_langfuse.py` /
`sync_golden_set_to_langfuse.py`. `POST /api/public/models` for the three regex
`match_pattern`s above, each with input/output **and** the two cache usage-type
price tiers (`cache_read_input_tokens`, `cache_creation_input_tokens`). Loads
creds the same stdlib way as its siblings. `--check` lists current model defs.

> **Plan-phase verification (the one unconfirmed API detail):** confirm
> Langfuse v3's `/api/public/models` request shape for per-usage-type cache
> pricing — the exact price-key names for `cache_read_input_tokens` /
> `cache_creation_input_tokens`. Documentation-first per the langfuse skill.

### 2. `scripts/setup_langfuse_tracing.py` (3 edits)
- On `--write`, invoke the model sync so every newly-onboarded project gets
  correct cost automatically.
- **Drop the 6 Layer-2 keys** from `_build_env_block`: the env block goes
  11 → 5 keys (`TRACE_TO_LANGFUSE`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`,
  `LANGFUSE_HOST`, `CC_LANGFUSE_MAX_CHARS`). Removed:
  `CLAUDE_CODE_ENABLE_TELEMETRY`, `CLAUDE_CODE_ENHANCED_TELEMETRY_BETA`,
  `OTEL_TRACES_EXPORTER`, `OTEL_EXPORTER_OTLP_PROTOCOL`,
  `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_EXPORTER_OTLP_HEADERS`.
- **Prune** the now-removed OTEL keys from an existing `settings.local.json` on
  write (clean removal, no shim — matches the project's no-backwards-compat rule).

### 3. Vendored `_langfuse_hook.py` enrichment (`# VENDOR-PATCH`)
Set on the trace: `userId` (from transcript account id), `release` (CC version),
project `tag`. Keep the existing `claude-code` tag. `ttft` stays a flagged
**investigate-feasibility** item — it lived in the dropped Layer-2 metadata;
recovering per-call timing from the transcript is unverified. If infeasible,
ttft is lost (accepted).

### 4. ADR-019 + docs + version
Supersede ADR-019's "Layer 2 OTEL beta traces" section (record the removal +
rationale), document the model-pricing sync and enrichment, update the CLAUDE.md
R5 section, bump plugin (minor).

### 5. Backfill
Re-run `setup_langfuse_tracing.py --write` for **solarmonkey-app** and **this
framework repo**: registers the models (idempotent) and strips their OTEL keys.
Existing traces gain cost retroactively once the model defs exist.

## Testing / acceptance
- `sync_langfuse_models.py` unit-tested (mocked POST) under `tests/`.
- `setup_langfuse_tracing.py` env-block test updated for 5 keys + the prune path.
- Full framework suite + `render_prompts.py --check` + `build_plugin_hooks.py --check`
  green. (Vendored-hook change re-mirrors into the plugin bundle.)
- Live check: re-run setup against solarmonkey-app → confirm cost populates on
  the existing session and no new `claude_code.interaction` traces appear on the
  next turn.

## Out of scope / deferred
- Bucket 3 (agent behavior: parallel tool batching, anti-over-search,
  AskUserQuestion-rejection handling, enabling gates in solarmonkey-app).
- `ttft` if transcript recovery proves infeasible.
- Layer-2 / OTEL native dashboards (we are removing Layer-2).

## Rejected alternatives
- **One-off fix for solarmonkey-app only** — gaps recur per project; nothing
  lands in the framework.
- **Keep both tracing layers** — 2× volume + permanent hollow traces for data
  R5 already carries.
- **Layer-2 only + await upstream fixes** — gives up R5's working cost/content
  data for an uncertain upstream timeline.
