# V3 Architecture Spikes

Validation artifacts from the 2026-05-22 session that produced [ADR-016](../../../../docs/adr/ADR-016-v3-claude-agent-sdk-substrate.md). These are **runnable proofs** that V3's architecture works end-to-end on Claude Max auth with no Anthropic API key.

The leading underscore on the directory name (`_spikes/`) signals "validation artifact, not production code." These scripts are NOT part of the V3 platform — they're the empirical evidence that V3's design choices are sound.

## Contents

### `v3_spike.py` — canonical end-to-end V3 architecture proof

Demonstrates the full V3 flow in ~190 lines:

1. **Supervisor** call: `query(output_format=HandoffResult.model_json_schema())` returns a typed routing decision.
2. **Two workers in parallel** via `asyncio.gather()`: each calls `query(output_format=ReviewReport.model_json_schema())` with a different focus (general code review vs. security audit). Each returns a typed `ReviewReport`.
3. **Aggregator agent** call: receives `list[ReviewReport]` as JSON in its prompt and returns one unified `ReviewReport` with semantic deduplication, severity arbitration, and a narrative summary.

### Validates

- ✅ Claude Agent SDK works under Max auth (`ANTHROPIC_API_KEY` explicitly absent)
- ✅ Native `output_format` enforces Pydantic schemas with internal retry on validation failure
- ✅ `asyncio.gather` runs two `query()` calls concurrently without explicit conflict (with a known async-generator teardown race documented in ADR-016)
- ✅ The Step 09 schemas (`HandoffResult`, `ReviewReport`) survive end-to-end serialization through the SDK
- ✅ Agent-based aggregation produces semantically correct merges that mechanical key-based dedup cannot

### `v3_code_reviewer_smoke.py` — Step 10 package smoke

Smaller, narrower spike added when Step 10 landed. Validates the package surface (`hooks.lib.llm.workers.review` + `aggregate`) rather than ad-hoc inline functions. Two phases:

1. `review(diff, scope)` over a deliberate-bug diff → typed `ReviewReport`.
2. `aggregate([report])` over the length-1 result → unified `ReviewReport`. The degenerate case is the smallest valid input; Step 18 will exercise length 2+.

Use this as the **post-Step-10 sanity check** before working on dependent code. The big `v3_spike.py` is still the canonical end-to-end proof.

```bash
python3 hooks/lib/llm/_spikes/v3_code_reviewer_smoke.py
# then verify cost telemetry:
req budget tail -n 5
```

Expected: two ledger entries labeled `code-reviewer` and `review-aggregator` from this run.

### `v3_prompt_loader_smoke.py` — Step 12 round-trip

Validates the Langfuse Prompt Management round-trip in three steps:

1. Run `scripts/sync_prompts_to_langfuse.py` to publish `prompts/*.txt`.
2. Call `load_prompt('code-reviewer')` / `load_prompt('review-aggregator')` — should hit Langfuse and match the disk content (or differ if a newer version was promoted in the UI).
3. Clear `LANGFUSE_PUBLIC_KEY` and re-import the loader — should silently fall back to file, producing the `{diff}`-placeholder template.

```bash
python3 hooks/lib/llm/_spikes/v3_prompt_loader_smoke.py
```

Then visit `http://localhost:3000` → Prompts tab to see `code-reviewer` and `review-aggregator` listed with the `production` label.

### Predecessor spikes (merged into v3_spike.py)

Earlier in the same session two smaller smoke tests confirmed individual layers:
- **Hand-rolled prompt-and-parse path** (no `output_format`): proved Max auth + Pydantic post-hoc validation works, ~20s per call.
- **Native `output_format` path** on the installed SDK v0.2.82: proved the SDK's structured-output feature works, ~58s per call (~3x slower than hand-rolled due to internal validation rounds).

The data from those runs is captured in ADR-016's Empirical Data section. `v3_spike.py` covers everything the predecessors did, plus the aggregator-agent layer they didn't reach.

## How to run

```bash
# One-time install (already required for V3 work):
pip3 install --user claude-agent-sdk pydantic

# Run the spike:
python3 hooks/lib/llm/_spikes/v3_spike.py
```

No environment variables needed. Auth flows through `~/.claude/` (the Claude Code CLI's credentials, inherited by the SDK's bundled subprocess).

## Expected output shape

```
================================================================
V3 spike — supervisor + 2 parallel workers + aggregator
================================================================
Auth: Max only (no API key)

PHASE 1: Supervisor routing
----------------------------------------------------------------
  target:    deep-review
  rationale: ...
  elapsed:   ~20s

PHASE 2: Parallel review workers
----------------------------------------------------------------
  ✓ code-reviewer: N finding(s)
  ✓ appsec-auditor: M finding(s)
  elapsed (parallel): 60–375s  ← see latency variance note below

PHASE 3: Aggregation via agent
----------------------------------------------------------------
  (N+M) raw finding(s) → K unified after agent aggregation
  elapsed: ~180s

  Narrative summary (from aggregator):
    ...

  [CRITICAL] api/auth.py:11 (security, conf=1.00)
    ... [flagged by code-reviewer + appsec-auditor]
  ...

================================================================
SPIKE SUMMARY
================================================================
  Supervisor:    ~20s   → HandoffResult
  Workers (∥):   60–375s → 2 × ReviewReport in parallel
  Aggregator:    ~180s  → ReviewReport (unified, with narrative)
  Total:         ~80–580s
```

## Latency variance warning

Observed across two consecutive runs of the spike on identical inputs:

| Run | Workers parallel | Total |
|---|---|---|
| 1 | 59.82s | 79.90s |
| 2 | 375.01s | 583.35s |

**7x variance with no input change.** Hypotheses (untriaged):
1. Subprocess contention from 3 concurrent SDK CLI invocations
2. Anthropic-side rate limiting under Max auth
3. Invisible internal SDK retries on `output_format` re-prompting
4. General API latency variance

Resolving this is the explicit goal of V3 Step 11 (Langfuse + Agent SDK instrumentation), which is now the next V3 step per ADR-016.

## When to re-run

- After any `claude-agent-sdk` upgrade — verify the `output_format` API hasn't broken
- After modifying any V3 schema in `hooks/lib/llm/schemas.py` — verify schemas still serialize cleanly through the SDK
- Before/after Anthropic's June 15, 2026 billing change — measure whether the new SDK credit pool affects latency
- As a sanity check before starting a new V3 step

## Cost per run

Approximately $0.30–$0.60 in Sonnet usage (pre-June-15-2026: counts against normal Claude Code limits; post-June-15: counts against the separate Agent SDK credit pool).

## What this does NOT prove

- Multi-session retrieval (Qdrant) — Step 13 concern, not exercised here
- Langfuse observability — Step 11 concern, not exercised here
- Ragas eval quality scoring — Step 15 concern
- Memory blocks across sessions — Step 14 concern
- Jinja template rendering — Step 16 concern
- Token-budget enforcement — Step 17 concern

Each of those has its own validation work to do when its step lands.
