# ADR-016: V3 on Claude Agent SDK Substrate

## Status

Approved (2026-05-22)

## Context

The original variant3 roadmap (`.claude/plans/variant3/`, drafted spring 2026) layered eight production-grade LLM-platform capabilities on top of the simplified framework: structured output, observability, retrieval, memory, eval, prompt registry, templating, and budgeting. The plan's central assumptions were:

1. Workers call `instructor.from_anthropic(anthropic.Anthropic())` for structured output with tool-use forcing.
2. The supervisor is a PydanticAI agent with `@agent.tool` handoffs.
3. Embeddings come from OpenAI's `text-embedding-3-small`.
4. The user has Anthropic API access alongside Claude Code.

Two factors made those assumptions wrong:

**Factor 1 — Auth reality.** The user has Claude Max only (no Anthropic API key). Direct `anthropic.Anthropic()` calls fail with `AuthenticationError` at the SDK level. Max provides Claude.ai + Claude Code usage; it does not provide API credits. The `instructor` path was a dead end.

**Factor 2 — SDK ships native structured output.** Between the original plan's drafting and 2026-05-22, Anthropic released `claude-agent-sdk` v0.2.82 with first-class `output_format` support. Passing `ClaudeAgentOptions(output_format={"type": "json_schema", "schema": Pydantic.model_json_schema()})` causes the SDK to validate model output against the schema internally, retry on mismatch, and surface success/failure via `ResultMessage.subtype`. This is the functional equivalent of Instructor's `response_model`, delivered as a substrate primitive.

Together these mean the V3 platform can ride on Claude Code's auth and the SDK's native primitives — but the plan must be re-derived around them.

A third factor surfaced from validation work this session: **aggregating worker outputs is naturally an agent task, not a Python dedup utility.** A spike's mechanical `(file, line, category)` key was both too coarse (collapsed three distinct security issues at one line into a single row) and too fine (missed the same `/tmp` bug reported at line 17 by one agent and line 18 by another). Replacing the Python dedup with an aggregator agent reading typed `ReviewReport` objects produced semantically correct merges plus a narrative summary, at negligible extra cost ($0.03/run).

And a fourth factor emerged from running the spike: **performance variance under load is large and unexplained.** Two consecutive runs of the same workflow on the same diff with the same prompts produced wildly different latencies (workers in parallel: 60s vs 375s; total flow: 80s vs 583s). Without observability we cannot distinguish "good run" from "bad run" — meaning Step 11 (Langfuse + Agent SDK instrumentation) must precede the substantive workers, not follow them.

## Decision

**V3 is rebuilt on the `claude-agent-sdk` substrate with native `output_format` as the structured-output primitive, an aggregator agent as the worker-composition mechanism, and observability + token budgeting prioritized before substantive worker construction.**

### Concrete substrate choices

| Layer | Before | After (this ADR) |
|---|---|---|
| Auth | `anthropic.Anthropic()` + API key from `console.anthropic.com` | `claude_agent_sdk.query()` + Max auth via bundled CLI subprocess |
| Structured output | `instructor.from_anthropic(...).create(response_model=...)` | `query(options=ClaudeAgentOptions(output_format={"type": "json_schema", "schema": Pydantic.model_json_schema()}))` |
| Worker composition | Python dedup keyed on `(file, line, category)` | Aggregator agent reads `list[ReviewReport]` JSON, returns unified `ReviewReport` |
| Supervisor runtime | PydanticAI `Agent` with `@agent.tool` handoffs | Thin Python script calling `query(output_format=HandoffResult.model_json_schema())` |
| Embeddings | OpenAI `text-embedding-3-small` | Local `sentence-transformers` (`BAAI/bge-small-en-v1.5`, ~33MB) |
| Batch eval call site | `query()` per example | `ClaudeSDKClient` persistent connection across the golden set |
| Pyproject `[llm]` extras | `instructor`, `anthropic`, `pydantic-ai` | `claude-agent-sdk`, `sentence-transformers`, `onnxruntime` (PydanticAI dropped) |

### Revised step ordering

The original ordering placed observability (Step 11) and budgeting (Step 17) in the middle of the build. The spike's latency-variance finding (see Empirical Data below) makes this untenable — without traces, we ship a system whose cost we cannot see. New ordering:

```
08 ✓ → 09 ✓ → 11 (observability) → 17 (budget) →
10 (workers + aggregator) → 18 (supervisor) →
13 (retrieval, local) → 14 (memory) → 15 (eval, via ClaudeSDKClient) →
12 (prompt registry) → 16 (Jinja templates) → 19 (dialect plugin) → 20 (Sonnet pinning)
```

The principle: **observability and budgeting are foundational substrate, not features.** The original plan put them in the middle because they were framed as "integrations." After the spike, they are upstream-of-everything.

### What about PydanticAI?

PydanticAI was originally chosen for `@agent.tool` handoff binding and the `Hooks()` capability for tracing. Both motivations weakened:

- `@agent.tool` handoff binding → native `output_format` with `HandoffResult` literal targets is simpler and substrate-supported.
- `Hooks()` capability for tracing → the SDK's native hooks system (PreToolUse/PostToolUse Python functions, see `claude-agent-sdk` README) is more granular and doesn't need a wrapper framework.

PydanticAI is not removed from V3 as an option — but it is no longer load-bearing. The supervisor (Step 18) becomes a ~30-line Python script. Future complexity (multi-step deliberation, complex tool fanout) could re-introduce PydanticAI as a layer above `claude-agent-sdk`, but not as a substrate.

## Empirical data (validation spike, 2026-05-22)

Two runs of `hooks/lib/llm/_spikes/v3_spike.py` on identical inputs:

### Run 1 (mechanical aggregator — earlier draft)

| Phase | Wall time | Notes |
|---|---|---|
| Supervisor (HandoffResult) | 20.09s | output_format succeeded, max_turns=3 sufficient |
| 2 workers in parallel (ReviewReport × 2) | 59.82s | output_format succeeded on both, max_turns=5 |
| Python aggregation (file, line, category) | 0.1ms | mechanical dedup |
| **Total** | **79.90s** | |
| Dedup result | 12 raw → 8 | over-aggregated 3 distinct issues at line 18; missed same-issue at lines 18 vs 20 |

### Run 2 (agent aggregator — final design)

| Phase | Wall time | Notes |
|---|---|---|
| Supervisor (HandoffResult) | 19.51s | consistent with Run 1 |
| 2 workers in parallel (ReviewReport × 2) | **375.01s** | **6.3× slower than Run 1 for identical inputs** |
| Aggregator agent (ReviewReport) | 188.83s | reads 13 worker findings as JSON, produces unified report |
| **Total** | **583.35s** | **7.3× slower than Run 1** |
| Dedup result | 13 raw → 9 | semantically correct: merged adjacent-line duplicates, kept distinct same-line issues, arbitrated severity disagreements, produced narrative summary |
| Side note | `aclose(): asynchronous generator is already running` in stderr during teardown — race between concurrent `asyncio.gather` query calls and SDK cleanup; not a correctness issue but suggests `ClaudeSDKClient` is a more robust pattern than parallel `query()` |

### Cost data

| Operation | Approx tokens | Approx cost (Sonnet) |
|---|---|---|
| Supervisor call | ~5k in + 200 out | ~$0.02 |
| One review worker call | ~3k in + 2k out | ~$0.04 |
| Aggregator agent call | ~10k in + 2k out | ~$0.06 |
| **One full `/deep-review` (5 agents)** | ~120k tokens total | **~$0.30–0.60** |

Post-June-15, 2026 billing means Max 5x users get $100/mo in Agent SDK credits (separate from the interactive subscription pool). That translates to roughly 150–300 `/deep-review` runs per month before the credit pool exhausts. Workable for a personal-development workload, tight for team-shared production.

### Dedup-quality observations

Cases where the **agent aggregator** succeeded and the **mechanical aggregator** failed:

| Finding | code-reviewer | appsec-auditor | Mechanical | Agent |
|---|---|---|---|---|
| SQL injection at line 11 | ✅ | ✅ | ✅ merged | ✅ merged |
| OS command injection in `os.system` | ✅ (line 17) | ✅ (line 16) | ❌ kept as two findings (line mismatch) | ✅ merged with both line refs in body |
| `/tmp/export.csv` predictable path | ✅ (line 18) | ✅ (line 17) | ❌ kept as two | ✅ merged |
| Three distinct issues at line 18 | code-reviewer caught two, appsec one | (same) | ❌ collapsed all three into one row | ✅ kept as three |
| Severity disagreement on plaintext password | rated SUGGESTION | rated IMPORTANT | (no mechanism to arbitrate) | ✅ chose IMPORTANT, documented disagreement in body |
| Narrative summary across the cluster | n/a | n/a | (impossible) | ✅ produced one in 3 sentences |

This is the load-bearing evidence that the aggregator should be an agent.

## Consequences

### Positive

- **V3 runs on the user's existing Max subscription** with no additional billing surface.
- **Schemas from Step 09 survive verbatim** — they're substrate-agnostic.
- **Less third-party dependency surface** — `instructor`, `anthropic` SDK, and PydanticAI all become optional or unused.
- **Better aggregation quality** than the original mechanical plan could have produced.
- **Empirical baseline** for V3 step planning — every future step starts from observed numbers, not estimates.

### Negative

- **Higher latency variance** than originally projected. The 7x swing between runs is unexplained. Step 11 must land first to diagnose.
- **Lock-in to the Agent SDK's evolution** — if Anthropic changes the SDK's API or pricing, V3 is more exposed than the original "use the bare API" design.
- **Per-call subprocess overhead** (~6–12s) is real. For batch operations (Step 15 Ragas eval), `ClaudeSDKClient` is mandatory; this constrains how Step 15 is structured.
- **Five existing variant3 plan documents (10, 11, 13, 15, 18) are partially superseded** and need eventual rewrite. Cost of the pivot.

### Risks to monitor

1. **The latency-variance hypothesis space is open.** Possibilities: subprocess contention, Anthropic-side rate limiting under Max auth, invisible SDK internal retries on `output_format` re-prompting, Anthropic API latency variance. Step 11's observability is the diagnostic.
2. **June 15, 2026 billing transition.** SDK usage moves to a separate $100/mo credit pool for Max 5x. If V3 worker latency stays at the high end (~580s = ~$3.00 per run), the pool covers ~30 runs/month, not 200. Step 17 (token budgeting) becomes critical at this point.
3. **The aggregator agent is now a single point of failure** for review output quality. If it merges too aggressively or too conservatively, the whole `/deep-review` is poorer. Mitigation: Step 15's Ragas eval should score the aggregator specifically.

## Alternatives considered

### Alternative 1: Buy an Anthropic API key

Keep the original `instructor` plan; the user purchases ~$20/mo in API credits to run V3 separately from Max. Rejected: adds a second billing surface; aligns poorly with Max-first philosophy; the SDK's `output_format` makes Instructor's benefits redundant anyway.

### Alternative 2: Hand-rolled prompt-and-parse instead of `output_format`

Use the lower-latency hand-rolled retry loop from the first smoke test (`v3_agent_sdk_smoke.py`). Rejected for workers because `output_format` is the supported path and tests cleaner; accepted for the supervisor (where the schema is tiny and latency matters more) as a future possibility.

### Alternative 3: Pause V3 entirely

Given that the SDK has shipped much of V3's intended capability natively, ask whether V3 is still worth building. Rejected (for now): the simplification phase + Step 09 schemas + Agent SDK substrate covers ~50% of V3's value. The remaining 50% (observability, retrieval, eval, aggregator, supervisor) is still genuinely valuable. Reconsider after Step 11 + Step 15 land — if those don't pay for themselves, the remainder may be droppable.

### Alternative 4: Defer the pivot until Step 10 is being executed

Don't rewrite plans now; absorb the substrate change into each step as it's executed. Rejected because the pivot affects step *ordering* (observability first), not just step contents — and ordering decisions need to be made now to set up future-session context correctly.

## Open questions

1. **How fast can `ClaudeSDKClient` make the 3-call flow?** Spike used `query()` for each call (subprocess per call). Worth a follow-up measurement: same flow through one persistent client.
2. **First-attempt success rate for `output_format` on complex schemas?** Spike was n=2 (both succeeded for `ReviewReport`); we lack failure-rate data.
3. **What's the minimum `max_turns` with `output_format`?** Spike used 5 because `max_turns=1` fails. Is 2 sufficient? Affects supervisor latency.
4. **Does `output_format` adversely interact with `allowed_tools=[]`?** Spike allowed it, but worth understanding whether the SDK's internal validation/retry tries to call tools.

## Related ADRs and artifacts

- ADR-012: Agent Teams integration — the parallelism pattern V3 builds on.
- ADR-013: Standardized agent output format — the precedent for typed agent output.
- ADR-014: Refactor orchestration bundled skill — the agent-as-composer pattern V3 generalizes.
- `.claude/plans/variant3/00-overview.md` — revised plan overview pointing at this ADR.
- `hooks/lib/llm/_spikes/` — runnable validation scripts that produced the empirical data above.
- Memory: `refactor-current-status.md`, `refactor-vision-and-roadmap.md` — updated 2026-05-22.

## Operational notes (added 2026-05-22, Step 11)

### Local infra location

V3 dev infrastructure (Docker compose for self-hosted Langfuse, future Qdrant in Step 13, etc.) lives under `infra/` at the repo root. This directory is intentionally committed, not gitignored — the compose file is part of the project's operational contract. Per-user credentials go in `infra/.env` (which IS gitignored); `infra/.env.example` is committed as a template.

### Pinning third-party compose files

When this project vendors an upstream Docker compose file (Step 11 imports Langfuse's), we pin to a specific commit SHA, not a branch. The fetched file MUST carry a header comment naming the source repo and SHA. Updates require a deliberate re-fetch with a new pin. Floating `main`-tracked dependencies are out of scope per the spirit of this ADR (predictable substrate).

Host-port deviations from upstream are permitted only when an upstream port conflicts with another long-running local service. Any such remap MUST be recorded in the compose file's header comment alongside the SHA pin so future readers can distinguish intentional drift from accidental edits.

### Dual-import-path caveat for V3 modules

Two import styles for V3 code coexist in this repo:

1. `hooks/test_requirements.py` puts `hooks/lib/` on `sys.path` and imports as `llm.observability`.
2. V3 tests and spikes under `tests/` and `hooks/lib/llm/_spikes/` put repo root on `sys.path` and import as `hooks.lib.llm.observability`.

Both paths resolve to the same physical files but appear as DIFFERENT `sys.modules` entries when exercised in the same process. V3 modules that hold module-global state (e.g., `observability.py`'s `_disabled_logged` / `_instrumented` flags) must tolerate this by ensuring underlying side effects are themselves idempotent at the library level (OpenInference's `BaseInstrumentor` guard suffices). Do not attempt to reconcile this in Python — it would require canonicalizing `sys.path` across all entry points, which is out of scope.

A related, narrower subtlety surfaced while writing the dep-free unit tests in Step 11: popping `sys.modules['hooks.lib.llm.observability']` is not enough to force a real re-execution of the module body, because Python's `from hooks.lib.llm import observability` reads the `observability` attribute off the parent package — and that attribute keeps a reference to the old module object even after the sys.modules pop. Test code that needs a genuinely fresh module must also `delattr(hooks.lib.llm, "observability")` before re-importing. The `fresh_observability_module()` helper in `tests/test_observability.py` documents and implements this pattern.

### Honest scope of OpenInference instrumentation

OpenInference's upstream docs recommend combining `instrumentation-claude-agent-sdk` with `instrumentation-anthropic` for full child-span coverage of internal Anthropic API calls (retries, `output_format` re-prompting). V3 removed direct Anthropic SDK usage in favor of the bundled CLI subprocess (Max-only, no API key), so we only install the Claude Agent SDK instrumentor. Visible spans therefore cover the outer `query()` boundary only — no breakdown of internal retry or latency subcomponents. Revisit if/when an API-key code path is added.

### Why no separate ADR-017

These four items are operational refinements of this ADR, not new decisions. Recording them inline keeps the substrate's decision boundary in one document.
