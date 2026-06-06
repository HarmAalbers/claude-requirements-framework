# ADR-017: Multi-Worker Review Fan-out Coordination Pattern

## Status

Approved (2026-05-25)

## Context

[ADR-016](ADR-016-v3-claude-agent-sdk-substrate.md) established the V3 substrate:
`claude-agent-sdk` with native `output_format`, an aggregator agent for worker composition,
and a thin Python supervisor for routing. Steps 09–18 built the primitives — schemas, the
single-worker call shape (`workers/code_reviewer.py`), Langfuse boundary instrumentation,
the prompt loader, the budget ledger, the aggregator agent, and the supervisor router.

The 2026-05-24 dogfood ran a single worker over a full ~8900-line branch diff: 100% precision
against the 11-agent `/deep-review` team, but only 40% recall (expected for N=1). The verdict
was explicit: **multi-worker fan-out is the only remaining gap before V3 can replace
`/deep-review` for production reviews.**

The fan-out architecture was already proven end-to-end in `hooks/lib/llm/_spikes/v3_spike.py`
(supervisor + 2 parallel workers + aggregator). Step 18b productionizes it. ADR-016 recorded
*why* the substrate is the SDK; it did not record the *coordination design* — how N workers are
dispatched, how partial failure is handled, where observability session boundaries live, and
why aggregation is an agent. Those decisions were made implicitly across several steps and the
spike. This ADR records them in one place so the next person (adding worker #4, or rewiring
`/deep-review`) inherits the rationale rather than re-deriving it.

## Decision

**Review fan-out is coordinated by a thin async function (`workers/fanout.py::fanout_review`)
that dispatches N pure-transform workers in parallel, binds the whole run into one Langfuse
session, proceeds with survivors on partial failure, and composes results through the
aggregator agent.**

### 1. Workers are pure transforms

Each worker is `async review(diff, scope) -> ReviewReport` with `allowed_tools=[]` — no file
I/O, no shell, no network beyond the SDK call. The coordinator owns all I/O (diff resolution,
result handling). This keeps workers independently testable (mocked SDK) and trivially
parallelizable, and means a worker can be mirrored to the Langfuse prompt registry without
side effects.

### 2. The coordinator owns the observability session boundary

`fanout_review` generates one `session_id` (uuid4) per run and binds every worker call **and**
the aggregator call into it via a usage-time helper (`tracing.py::review_session`), tagging each
with `worker:<name>` / `feature:review`. Without this, Step 11's boundary instrumentation emits
N+1 unrelated AGENT traces that cannot be grouped after the fact. Session binding is the
coordinator's responsibility because it is the first layer that knows N calls belong together —
not the worker (which sees only itself) and not `observability.py` (which is setup-time, sees a
single `query()`).

`review_session` lives in a **separate `tracing.py` module**, not `observability.py`:
`init_observability()` is setup-time (idempotent, once-per-process, manages provider/atexit
state); `review_session` is usage-time (fail-open, called per worker). Different lifecycles and
failure modes → different modules.

### 3. Partial failure proceeds with survivors

`asyncio.gather(return_exceptions=True)`: a worker that raises is logged and dropped; the run
aggregates whatever returned. The run raises `RuntimeError` only if **all** workers fail. This
matches the framework's fail-open design principle — one transient SDK hiccup must not waste the
other workers' cost or block the review. The coordinator never swallows silently: every dropped
worker is logged with its exception.

### 4. Aggregation is an agent, not Python

Inherited from ADR-016 and recorded here for completeness: mechanical `(file, line, category)`
dedup is both too coarse (collapses distinct issues at one line) and too fine (misses the same
issue at adjacent lines). The aggregator agent reads typed `list[ReviewReport]` and returns a
unified `ReviewReport` with semantic merges and a narrative summary, for ~$0.03/run.

### 5. The coordinator returns `FanoutResult`, not a bare `ReviewReport`

`fanout_review` returns `FanoutResult(report, session_id, survivor_count)`. The `session_id` is
generated inside the coordinator and is needed programmatically by the smoke (to print the
Langfuse URL) and by Step 17b (cost attribution). Putting it on `ReviewReport` would pollute the
per-worker structured-output schema contract with infrastructure metadata, so it goes on a
coordinator-level result type instead.

## Consequences

**Positive:**
- Recall scales with worker count toward `/deep-review` parity, while each worker stays a small,
  independently-evaluable unit (Step 15 Ragas harness can score them individually).
- One filterable Langfuse session per review run makes the cost/latency analysis that Step 17b
  and Step 20 depend on tractable.
- The worker set is a dependency-injected parameter, so adding worker #4 is a new module + one
  registry-dict entry, not a coordinator rewrite.

**Negative / accepted:**
- **Cost scales with N**: ~$2/worker on a full-branch diff → ~$6 for the 3-worker pilot, ~$22 if
  expanded to 11. Step 17b per-call budget enforcement is the mitigation; this step *produces*
  the multi-worker cost data 17b needs.
- **Parallel `query()` teardown race**: ADR-016 empirically observed
  `aclose(): asynchronous generator is already running` under concurrent `asyncio.gather` + bare
  `query()`, suggesting `ClaudeSDKClient` is a sturdier fan-out primitive. The pilot proceeds with
  `gather` (validated by `v3_spike.py`); migrating to `ClaudeSDKClient` is carried forward as a
  follow-up if the race proves load-bearing at scale.

## Relationship to ADR-012 (Agent Teams)

ADR-012 designates the team-based `/deep-review` as the *primary recommended* review approach.
This fan-out is an SDK-substrate alternative doing the same job via a different mechanism. Step
18b is **additive and CLI-only** — `/deep-review` is unchanged. Whether V3 fan-out eventually
*replaces* the Agent Teams substrate for `/deep-review` is deferred; if that replacement is
pursued it warrants its own ADR, as it would be a breaking architectural shift.

## Relationship to ADR-013 (Standardized Agent Output Format)

The `solid-reviewer` / `appsec-auditor` **plugin** agents emit ADR-013 markdown. The V3 **workers**
of the same name emit `ReviewReport` JSON via `output_format`. The severity vocabulary
(`CRITICAL` / `IMPORTANT` / `SUGGESTION`) is shared, so the two are parallel representations, not a
conflict. The JSON path is additive; the plugin agents are unchanged for now.

## Reversibility

`git revert` (or `stg delete`) of the Step 18b patches removes `fanout.py`, `tracing.py`, and the
two new workers. The `code_reviewer.py` → `_base.py` extraction is behavior-preserving, so it can
remain independently. Nothing user-facing changes (CLI-only entry), so revert has no external
blast radius.
