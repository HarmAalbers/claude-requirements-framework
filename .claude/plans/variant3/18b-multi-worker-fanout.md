# Step 18b — Multi-worker review fan-out

> **Status: planned 2026-05-25.** Net-new step (no prior variant3 doc). Closes the
> single remaining gap from the 2026-05-24 V3 dogfood verdict: *"Multi-worker fan-out is
> the only remaining gap before V3 can replace `/deep-review` for production reviews."*
> Implements the "Future Step 18 expansion" deferred in
> `18-pydanticai-req-supervisor.md:230` (supervisor owns review fan-out + Langfuse
> session/tag boundary).

## Arch-Review Outcome (2026-05-25) — VERDICT: APPROVED

7-agent team review (adr-guardian, compat-checker, tdd-validator, solid-reviewer,
refactor-advisor, commit-planner, codex-arch-reviewer). No CRITICAL findings, no ADR
violations. Implementable as written; the refinements below are **binding** (fold into the
named patch before `stg refresh`).

**Cross-validated, must-do:**

1. **`_base.run_worker()` must preserve `code_reviewer`'s testable contract** (compat-checker
   + tdd-validator HIGH). The existing `tests/test_code_reviewer_worker.py` does
   `patch.object(code_reviewer, "query")` / `patch.object(code_reviewer, "ResultMessage")`
   and asserts the verbatim error strings `"code-reviewer failed: subtype=..."` /
   `"code-reviewer: no ResultMessage observed"`. So `code_reviewer.py` MUST keep its own
   `query`/`ResultMessage` module-level imports and pass them through to `run_worker`, and
   `run_worker` MUST take an `error_prefix`/label so the exact strings reproduce. Generalizing
   either breaks the unmodified tests. Add an explicit `stg show && python3
   tests/test_code_reviewer_worker.py` green-check to patch 2.

2. **`fanout_review` returns `FanoutResult`, not bare `ReviewReport`** (solid-reviewer MEDIUM
   + codex MEDIUM + commit-planner). `session_id` is generated inside the coordinator; the
   smoke (and Step 17b cost tracker) need it programmatically. Do NOT put it on `ReviewReport`
   (pollutes the per-worker schema contract). Define `@dataclass(frozen=True) FanoutResult(report,
   session_id, survivor_count)` in patch 5.

3. **Lazy `_default_workers()` factory, not module-scope dict** (solid-reviewer + codex
   MEDIUM). Module-scope `_DEFAULT_WORKERS` imports all 3 concrete workers at `import fanout`
   time, defeating the DI param and breaking test isolation. Construct inside the function
   behind `if workers is None`, with deferred imports.

4. **`run_worker` generic over schema** (refactor-advisor + commit-planner). Signature
   `run_worker(*, agent_label, system, prompt, schema: type[T], max_turns=5, query, result_cls)`
   so the same loop serves workers (ReviewReport) AND, later, the supervisor (HandoffResult,
   max_turns=3). Supervisor rewiring stays **deferred** — just don't preclude it.

5. **`review_session` lives in a new `hooks/lib/llm/tracing.py`, not `observability.py`**
   (codex MEDIUM + refactor-advisor). `observability.py` is setup-time (idempotent, once);
   `review_session` is usage-time (fail-open, per-worker). Different failure modes → different
   module. `_base.run_worker()` MUST NOT call `review_session` — session binding is the
   coordinator's responsibility (document this layer boundary in `_base`'s docstring).

**Additive doc work (adr-guardian, IMPORTANT — fold into patch 1):**

6. **Draft ADR-017 — Multi-Worker Review Fan-out Coordination Pattern** recording: workers are
   pure transforms; coordinator owns session binding; partial-failure = proceed-with-survivors;
   aggregator-is-an-agent. None of these are recorded in one place today.
7. **Document the ADR-013 dual-format note**: the `solid-reviewer`/`appsec-auditor` *plugin*
   agents emit ADR-013 markdown; the V3 workers emit `ReviewReport` JSON. State explicitly that
   the JSON path is additive and the plugin agents are unchanged for now.
8. **Add a `## Known limitation` note** (adr-guardian SUGGESTION): ADR-016 empirically flagged
   `aclose(): asynchronous generator is already running` under parallel `asyncio.gather` +
   bare `query()`, suggesting `ClaudeSDKClient` is more robust for fan-out. The pilot proceeds
   with `gather` (validated by `v3_spike.py`) but carries forward `ClaudeSDKClient` as a
   follow-up. Add one forward-pointer sentence on the long-term `/deep-review` (ADR-012)
   relationship.

**Smaller TDD/quality items (fold into the relevant patch):**

9. 7th worker test — assert worker-identity in the system prompt (catches copy-paste of the
   code-reviewer template into solid/appsec).
10. `review_session` no-op test must use the `fresh_observability_module()`-style reload + null
    `openinference.instrumentation` (not `openinference`) — applies to the new `tracing.py` test.
11. `test_fanout.py` (d) must assert the aggregator's `review_session` uses the *same*
    `session_id` as the workers (not just "runs under the session").
12. Type the `workers=` param: `dict[str, Callable[[str, str], Awaitable[ReviewReport]]] | None`.
    `_base.run_worker` must **raise, never swallow** (invariant in its docstring), else the
    `isinstance(r, ReviewReport)` survivor filter silently drops failures.

## Goal

Productionize the fan-out pattern already proven end-to-end in
`hooks/lib/llm/_spikes/v3_spike.py`: run N review workers in parallel over one diff,
pipe their typed `ReviewReport`s through the existing aggregator agent, and bind the
whole run into one filterable Langfuse session. Pilot with **3 workers**; entry point is
a **CLI smoke script only** (no user-facing command change this step).

## Why now

Steps 09–18 built every primitive: schemas (09), the worker call-shape (10), Langfuse
boundary instrumentation (11), prompt registry (12), budget recording (17a), the
aggregator agent (10), the supervisor router (18). The single-worker dogfood scored
100% precision but only 40% recall (expected for N=1 vs the 11-agent team). Fan-out is
the consolidation that turns these primitives into a usable review pipeline and produces
the multi-worker cost/latency data Step 17b and Step 20 both depend on.

## Locked scope decisions (2026-05-25 interview)

| # | Decision | Choice |
|---|---|---|
| 1 | Worker count + selection | **Pilot 3**: `code-reviewer` (exists) + `solid-reviewer` (new) + `appsec-auditor` (new) |
| 2 | Entry point | **CLI smoke script only** — additive, like Step 18. No `/deep-review` rewire, no new command |
| 3 | Observability | **session_id + per-worker tags** via OpenInference `using_attributes(session_id=..., tags=["worker:<name>", "feature:review"])` |
| 4 | Prompt sourcing | **Step 10 convention** — `prompts/<agent>.md.j2` loaded via `load_prompt(name)`, Langfuse-mirrorable |
| 5 | Partial failure | **Proceed with survivors** — `asyncio.gather(return_exceptions=True)`; aggregate what returned; abort only if ALL fail (fail-open) |
| 6 | Smoke diff | **Reuse `scripts/prepare-diff-scope`** to write `/tmp/review.diff` — same scope resolution `/deep-review` uses |

## What already exists (do not rebuild)

- `workers/code_reviewer.py:53` — `review(diff, scope) -> ReviewReport` (the worker primitive)
- `workers/aggregator.py:50` — `aggregate(reports: list[ReviewReport]) -> ReviewReport` (handles N≥1, raises on empty)
- `supervisor.py:66` — `route(phase, unsatisfied) -> HandoffResult`
- `observability.py:160` — `init_observability()` (boundary instrumentation only — see gap below)
- `prompts.py:100` — `load_prompt(name, **vars)` (Langfuse-first, `.md.j2` file fallback, Jinja2-rendered)
- `prompts/code-reviewer.md.j2` + `partials/{safety,project_conventions}.j2`
- `claude.py` — budget-recording `query` wrapper; `options.agent = "<label>"` tags the ledger entry

## Gap analysis

1. **Only one worker exists.** `solid-reviewer` and `appsec-auditor` have plugin agents
   (`plugins/.../agents/`) and `.md.j2` prompt sources (Step 16b) but **no structured-output
   worker wrapper** and **no `hooks/lib/llm/prompts/<name>.md.j2`** for the `query()` path.
2. **No session/tag binding surface.** `observability.py` only instruments the `query()`
   boundary. There is no helper to group N calls into one Langfuse session. This is a
   *new public surface*, not just wiring — the Step 18 plan flagged it as the supervisor's
   responsibility (`18-...:13-23`).
3. **No fan-out coordinator.** The parallel-gather + survivor-handling + aggregate pipeline
   lives only inside the spike's `main()`. It needs to become a named, tested function.

## Preparatory refactor (Fowler: make the change easy, then make it)

`code_reviewer.py` is a hardcoded single-purpose module (its own `_SYSTEM`, `_build_options`,
`review`). Adding two more workers verbatim triples ~50 lines of near-identical query-loop +
options-builder boilerplate. **Before** adding workers, extract the shared mechanics into
`workers/_base.py`:

```python
# workers/_base.py
async def run_worker(*, agent_label: str, system: str, prompt: str) -> ReviewReport:
    """Shared worker mechanics: build options, run query, validate ReviewReport.

    Raises RuntimeError on error subtype / no ResultMessage (unchanged semantics).
    """
    ...  # the exact loop currently in code_reviewer.review(), parameterized
```

`code_reviewer.review()` then becomes a thin wrapper that builds its prompt via
`load_prompt("code-reviewer", ...)` and delegates. **No behavior change** —
`tests/test_code_reviewer_worker.py` must stay green unmodified. (Final structure — one
shared helper vs. three standalone modules — is an explicit question for `/arch-review`;
this is the recommended shape.)

## Files touched

| Path | Action |
|---|---|
| `hooks/lib/llm/workers/_base.py` | **new** — `run_worker()` shared helper |
| `hooks/lib/llm/workers/code_reviewer.py` | refactor to delegate to `_base` (no behavior change) |
| `hooks/lib/llm/workers/solid_reviewer.py` | **new** — `review(diff, scope) -> ReviewReport` |
| `hooks/lib/llm/workers/appsec_auditor.py` | **new** — `review(diff, scope) -> ReviewReport` |
| `hooks/lib/llm/prompts/solid-reviewer.md.j2` | **new** — mirrors code-reviewer template |
| `hooks/lib/llm/prompts/appsec-auditor.md.j2` | **new** — mirrors code-reviewer template |
| `hooks/lib/llm/tracing.py` | **new** — usage-time OTel helper `review_session(session_id, worker)` (arch-review #5: separated from setup-time `observability.py`) |
| `hooks/lib/llm/workers/fanout.py` | **new** — `fanout_review(diff, scope, workers)` coordinator |
| `hooks/lib/llm/workers/__init__.py` | export new workers + `fanout_review` |
| `hooks/lib/llm/__init__.py` | re-export `fanout_review` |
| `hooks/lib/llm/_spikes/v3_fanout_smoke.py` | **new** — CLI smoke via `prepare-diff-scope` |
| `tests/test_review_workers.py` | **new** — solid + appsec worker tests (mocked SDK) |
| `tests/test_fanout.py` | **new** — coordinator tests (mocked workers + aggregate) |
| `tests/test_observability.py` | extend — `review_session` no-op + attribute-setting tests |

**No plugin files touched** → **no `plugin.json` bump** (consistent with Steps 17a/18, which
were pure `hooks/lib/llm` and sync.sh-deployed). Confirm with `./sync.sh status` in housekeeping.

## Design detail

### Session/tag binding helper (`tracing.py` — new module per arch-review #5)

```python
from contextlib import contextmanager

@contextmanager
def review_session(session_id: str, worker: str):
    """Bind enclosed query() calls to one Langfuse session + per-worker tag.

    Fail-open: if openinference isn't installed, this is a no-op context
    manager so workers still run (just unbound in the trace UI).
    """
    try:
        from openinference.instrumentation import using_attributes
    except ImportError:
        yield
        return
    with using_attributes(
        session_id=session_id,
        tags=[f"worker:{worker}", "feature:review"],
    ):
        yield
```

`using_attributes` confirmed importable in the current env. Tags follow the exact form
named in `18-...:18`.

### Fan-out coordinator (`workers/fanout.py`)

```python
import asyncio, logging, uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from hooks.lib.llm.tracing import review_session       # arch-review #5: not observability
from hooks.lib.llm.workers.aggregator import aggregate
from hooks.lib.llm.schemas import ReviewReport

WorkerFn = Callable[[str, str], Awaitable[ReviewReport]]


@dataclass(frozen=True)
class FanoutResult:                                     # arch-review #2
    report: ReviewReport
    session_id: str
    survivor_count: int


def _default_workers() -> dict[str, WorkerFn]:          # arch-review #3: lazy
    from hooks.lib.llm.workers import (
        code_reviewer, solid_reviewer, appsec_auditor)
    return {
        "code-reviewer": code_reviewer.review,
        "solid-reviewer": solid_reviewer.review,
        "appsec-auditor": appsec_auditor.review,
    }


async def fanout_review(
    diff: str,
    scope: str = "unstaged",
    workers: dict[str, WorkerFn] | None = None,         # arch-review #12
) -> FanoutResult:
    workers = workers if workers is not None else _default_workers()
    session_id = str(uuid.uuid4())

    async def _bound(name: str, fn: WorkerFn) -> ReviewReport:
        with review_session(session_id, name):
            return await fn(diff, scope)

    results = await asyncio.gather(
        *(_bound(n, fn) for n, fn in workers.items()),
        return_exceptions=True,
    )
    reports = [r for r in results if isinstance(r, ReviewReport)]
    for name, r in zip(workers, results):
        if isinstance(r, Exception):
            logging.getLogger(__name__).warning("worker %s failed: %s", name, r)
    if not reports:
        raise RuntimeError("fanout_review: all workers failed")
    with review_session(session_id, "aggregator"):
        unified = await aggregate(reports)
    return FanoutResult(unified, session_id, len(reports))
```

Returns `FanoutResult` so the smoke (and Step 17b) get `session_id` + `survivor_count`
programmatically without log-parsing. `aggregate()` stays session-unaware (boundary kept clean).

### Smoke (`_spikes/v3_fanout_smoke.py`)

Loud-fail on missing prereqs per the [[feedback-loud-smoke-spikes]] memory: hard-error if
`scripts/prepare-diff-scope` is missing, exits non-zero if `/tmp/review.diff` is empty, and
does **not** silently skip when `claude-agent-sdk` is absent. Prints: per-worker timing,
survivor count, unified findings, total cost (from budget ledger delta), and the `session_id`.

## TDD plan (RED → GREEN per chunk)

- `tests/test_review_workers.py` — for each of solid + appsec: returns `ReviewReport` with
  correct `agent`; `allowed_tools == []`; `output_format` schema is `ReviewReport`;
  `options.agent` label correct for budget; raises on error subtype / no ResultMessage.
  (Mirror `test_code_reviewer_worker.py` exactly — mocked `query`/`ResultMessage`.)
- `tests/test_fanout.py` — (a) success: 3 mocked workers → `aggregate` called with 3
  reports; (b) partial: 1 worker raises → `aggregate` called with 2; (c) all fail →
  `RuntimeError`; (d) same `session_id` propagated to every `review_session` enter
  (assert via a patched `review_session` recording its args); (e) aggregator runs under the
  session too.
- `tests/test_observability.py` (extend) — `review_session` is a no-op CM when
  `openinference` import fails (monkeypatch the import to raise); calls `using_attributes`
  with the expected `session_id` + tags when present (mock `using_attributes`).

All V3 tests run via `python3 tests/test_<x>.py`; framework suite stays green
(`python3 hooks/test_requirements.py`).

## Acceptance

- [ ] `fanout_review(diff, scope)` runs 3 workers in parallel and returns one unified `ReviewReport`
- [ ] One worker failing yields a report aggregated from the survivors (logged, not raised)
- [ ] All workers failing raises `RuntimeError`
- [ ] All worker calls + the aggregator share one `session_id` and carry `worker:<name>` / `feature:review` tags
- [ ] `review_session` is a fail-open no-op when `openinference` is unavailable
- [ ] solid + appsec workers pass the same 6-test contract as `code-reviewer`
- [ ] Live smoke against a real branch diff (via `prepare-diff-scope`) produces a unified report and prints `session_id` + cost; the run appears as ONE session in Langfuse
- [ ] `./sync.sh status` clean; `python3 hooks/test_requirements.py` green

## Patch plan (stacked stg on `refactor/step-08-llm-package-scaffold`)

1. `step-18b-plan-docs` — this doc + `00-overview.md` slot + status-memory note
2. `step-18b-worker-base` — prep-refactor: `_base.run_worker()` + `code_reviewer` delegates (no behavior change)
3. `step-18b-new-workers` — solid + appsec worker modules + prompts + `test_review_workers.py`
4. `step-18b-session-binding` — new `tracing.py` `review_session` + `tests/test_tracing.py`
5. `step-18b-fanout` — `workers/fanout.py` + `test_fanout.py`
6. `step-18b-smoke` — `_spikes/v3_fanout_smoke.py`
7. `step-18b-housekeeping` — exports, `sync.sh status`, DEVELOPMENT.md note, status-memory update

## Deferred (carry forward)

- **`/deep-review` rewire / new command** — entry point stays CLI-only this step (decision #2)
- **Step 17b per-call budget** — fan-out multiplies cost (~$6/run est. for 3 workers); granular
  caps land with 17b. This step *produces* the multi-worker cost data 17b needs.
- **Worker count → 11 (full parity)** — pilot 3 first; expand once parity gain is measured
- **Nested span tree** (aggregator as child of fan-out span) — session+tags chosen over full
  hierarchy for this step (decision #3)
- **Degraded-report marker** — partial failure currently logs only; surfacing "N of M failed"
  in the unified summary is a follow-up

## Depends on

Steps 09 (schemas), 10 (worker primitive + aggregator), 11 (Langfuse boundary), 12 (prompt
loader), 16b (agent `.md.j2` sources), 17a (budget ledger), 18 (supervisor).

## Preparatory Refactoring

_Cross-validated analysis of duplication across `workers/code_reviewer.py`,
`workers/aggregator.py`, and `supervisor.py` — conducted prior to Step 18b implementation._

### Finding 1 — CONFIRMED: `run_worker()` base extraction (plan already proposes this) [HIGH]

The plan's proposed `workers/_base.py:run_worker()` is correct and should proceed as written.
Both `code_reviewer.review()` and `aggregator.aggregate()` share the **identical** query-loop
skeleton (lines 64–70 in each module):

```python
async for msg in query(prompt=prompt, options=options):
    if isinstance(msg, ResultMessage):
        if msg.subtype == "success" and msg.structured_output:
            return Schema.model_validate(msg.structured_output)
        raise RuntimeError(f"<label> failed: subtype={msg.subtype!r}")
raise RuntimeError("<label>: no ResultMessage observed")
```

The only variation is the `Schema` type and the label string in the two `RuntimeError`
messages. Parameterizing these into `run_worker(*, agent_label, system, prompt, schema)`
collapses ~14 lines per module into a single call. `solid_reviewer` and `appsec_auditor` will
need the same skeleton, making the total scope 4 modules → 1 helper.

**Impact if skipped**: adding two workers means three near-identical 14-line loops; any future
bug fix (e.g. handling a third ResultMessage subtype) must be applied in four places.

### Finding 2 — CONFIRMED: supervisor loop is a THIRD duplication but deserves a separate path [MEDIUM]

`supervisor.py:_build_options` + query loop (lines 45–95) is structurally identical to the
workers — same `setattr(options, "output_format", ...)` + same `async for msg in query(...)`
pattern. However, it differs in one load-bearing way:

- Workers produce `ReviewReport` (a concrete schema shared by multiple workers).
- Supervisor produces `HandoffResult` — a *different* schema with a `Literal` target type.
- Supervisor `max_turns=3` vs workers `max_turns=5`.

**Recommendation**: make `run_worker()` generic over the output schema type rather than
hard-coding `ReviewReport`:

```python
# workers/_base.py — revised signature
async def run_worker(
    *,
    agent_label: str,
    system: str,
    prompt: str,
    schema: type[T],           # TypeVar bound to BaseModel
    max_turns: int = 5,
) -> T:
    ...
```

This lets `supervisor.route()` also delegate to `run_worker()`, eliminating the third copy of
the loop. The supervisor becomes a thin wrapper (identical to how `code_reviewer.review()`
becomes thin after the prep-refactor). This is strictly *additive* to the plan's proposed
extraction — just widen the signature before adding the new workers.

**If the arch-review prefers keeping supervisor independent** (it touches a different layer),
accept that — the worker duplication is the higher-value target.

### Finding 3 — CONFIRMED: `_build_options()` setattr dance is copied verbatim [MEDIUM]

All three modules contain this block:

```python
setattr(options, "output_format", {
    "type": "json_schema",
    "schema": SomeSchema.model_json_schema(),
})
try:
    setattr(options, "agent", "<label>")
except (AttributeError, TypeError):
    pass
```

The comment explaining *why* `setattr` is used (SDK version variance + our budget-label
extension) is duplicated across `code_reviewer.py:39–49`, `aggregator.py:39–47`, and
`supervisor.py:54–63`. The `run_worker()` helper already absorbs this naturally if the schema
and agent label are passed as parameters — no separate extraction needed. The comment belongs
once, in `_base.py`.

**Note**: the `try/except (AttributeError, TypeError)` around the `agent` setattr is defensive
against a hypothetical future frozen dataclass — `code_reviewer` has it, `aggregator` has it,
`supervisor` has it. Keep it in `_base.py`; don't silently drop it.

### Finding 4 — JUDGMENT CALL: `review_session()` timing [LOW]

The plan defers `observability.review_session()` to patch `step-18b-session-binding` (patch 4
of 7). This is the correct sequencing: the fanout coordinator (patch 5) imports it, so building
`review_session` first avoids a circular dependency and lets its tests (`test_observability.py`
extension) run green before the fanout is wired.

**One nuance**: the `_base.run_worker()` helper (patch 2) does NOT call `review_session` — that
binding is the fanout coordinator's responsibility (`fanout.py` wraps each `_bound()` call).
This separation is correct: `run_worker()` is a pure query wrapper; session/tag binding is a
caller concern. Confirm this boundary is explicit in `_base.py`'s docstring so future callers
don't accidentally add it there.

### Summary table

| Finding | Severity | Action |
|---|---|---|
| `run_worker()` extraction (code_reviewer + aggregator) | HIGH | Proceed as planned in patch 2 |
| Make `run_worker()` generic to cover supervisor too | MEDIUM | Widen signature in patch 2; wire supervisor in patch 2 or a sub-patch |
| `_build_options` setattr absorbed into `run_worker()` | MEDIUM | Naturally handled by Finding 1+2 — no separate work |
| `review_session` ordering (before fanout, not inside base) | LOW | Sequencing already correct; add a doc note in `_base.py` |

## Atomic Commit Strategy

Branch: `refactor/step-08-llm-package-scaffold` (already `stg init`-ed — confirmed via `stg series`).
The current top patch is `step-V3dogfood-corrections-and-self-critique-fix`. All seven new
patches stack on top.

### Ordering rationale / hazard analysis

The dependency graph is linear with one critical ordering constraint:

```
patch-1 (docs)
  └─ patch-2 (worker-base)          ← _base.run_worker extracted; code_reviewer delegates
       └─ patch-3 (new-workers)     ← solid + appsec import _base; prompts land here too
            └─ patch-4 (session-binding)  ← review_session CM; no worker imports needed
                 └─ patch-5 (fanout)      ← imports solid + appsec (need patch-3) AND
                 |                          review_session (need patch-4) AND aggregate
                 └─ patch-6 (smoke)       ← imports fanout_review (need patch-5)
                      └─ patch-7 (housekeeping)  ← exports + docs + sync check
```

**Hazard 1 — fanout.py imports workers before they exist**: `fanout.py` imports
`solid_reviewer` and `appsec_auditor` directly. Patch-5 therefore **must** land after
patch-3 (new workers) and patch-4 (review_session). The proposed ordering satisfies this.

**Hazard 2 — `workers/__init__.py` exports in patch-7**: `fanout.py` imports modules
directly, not through the lazy `__getattr__` in `workers/__init__.py`. So `__init__.py` can
safely be updated last in patch-7 without breaking patch-5 or patch-6. No hazard.

**Hazard 3 — test files reference not-yet-created modules**: each test file is created in
the same patch as its implementation. `test_review_workers.py` lands in patch-3 (same patch
as the two new workers), `test_fanout.py` in patch-5, and the observability extension in
patch-4. Tests import their subject — ordering must stay as-is.

**Hazard 4 — code_reviewer.review() behavior change**: patch-2 refactors `code_reviewer.py`
to delegate to `_base.run_worker`. The contract (diff→ReviewReport, raises on error subtype /
no ResultMessage) must be bit-identical. `test_code_reviewer_worker.py` is the green gate;
it runs **unmodified** in patch-2 to prove no regression.

**Hazard 5 — generic schema type from Preparatory Refactoring Finding 2**: if `run_worker`
is made generic (TypeVar over BaseModel) to also cover supervisor, widen the signature in
patch-2 only. Do NOT wire supervisor inside patch-2 — that belongs in a separate patch or
a follow-up. Keep patch-2 strictly a no-behavior-change prep refactor for workers.

---

### Patch 1 — `step-18b-plan-docs`

**Files changed**
- `.claude/plans/variant3/18b-multi-worker-fanout.md` — this doc (plan + commit strategy)
- `.claude/plans/variant3/00-overview.md` — slot Step 18b in the overview table
- `/Users/harm/.claude/projects/-Users-harm-Tools-claude-requirements-framework/memory/refactor-current-status.md` — note Step 18b as "in progress"

**Before refresh**: docs only; no code; no test to run.

**stg commands**
```bash
stg new step-18b-plan-docs
# edit/write the above files
stg refresh
```

---

### Patch 2 — `step-18b-worker-base`

**Goal**: prep-refactor — extract shared `run_worker()` into `workers/_base.py`; thin-wrap
`code_reviewer.review()` to delegate. **Zero behavior change.**

**Files changed**
- `hooks/lib/llm/workers/_base.py` — **new**: `run_worker(*, agent_label, system, prompt, schema, max_turns=5) -> T`
  (generic over `BaseModel` subtype per Finding 2; absorbs the `setattr` dance and query loop)
- `hooks/lib/llm/workers/code_reviewer.py` — refactor: `_SYSTEM`, `_build_options`, and the
  query loop move into `_base`; `review()` becomes `load_prompt(...)` + `run_worker(...)` call

**Test before refresh** (must all be GREEN — no test file changes):
```bash
python3 tests/test_code_reviewer_worker.py
python3 hooks/test_requirements.py
```

**stg commands**
```bash
stg new step-18b-worker-base
# write _base.py; refactor code_reviewer.py
stg refresh
```

**Verification gate**: `test_code_reviewer_worker.py` passes with zero changes to the test
file. If any test goes RED, the refactor changed observable behavior — fix before refreshing.

---

### Patch 3 — `step-18b-new-workers`

**Goal**: two new worker modules + their prompts + `test_review_workers.py` (RED → GREEN).

**Files changed**
- `hooks/lib/llm/workers/solid_reviewer.py` — **new**: `review(diff, scope) -> ReviewReport`
  delegating to `_base.run_worker`; agent label `"solid-reviewer"`
- `hooks/lib/llm/workers/appsec_auditor.py` — **new**: `review(diff, scope) -> ReviewReport`
  delegating to `_base.run_worker`; agent label `"appsec-auditor"`
- `hooks/lib/llm/prompts/solid-reviewer.md.j2` — **new**: mirrors `code-reviewer.md.j2` structure
- `hooks/lib/llm/prompts/appsec-auditor.md.j2` — **new**: mirrors `code-reviewer.md.j2` structure
- `tests/test_review_workers.py` — **new**: 6-contract test suite (mirrors
  `test_code_reviewer_worker.py`; parameterized over both solid + appsec)

**Test before refresh** (RED first on new test file; GREEN after implementation):
```bash
python3 tests/test_review_workers.py
python3 tests/test_code_reviewer_worker.py   # regression — must stay green
python3 hooks/test_requirements.py
```

**stg commands**
```bash
stg new step-18b-new-workers
# write prompts, worker modules, then test file
stg refresh
```

---

### Patch 4 — `step-18b-session-binding`

**Goal**: add `review_session(session_id, worker)` context manager to `observability.py` +
extend `test_observability.py` (RED → GREEN).

**Files changed**
- `hooks/lib/llm/observability.py` — add `review_session` context manager (fail-open no-op
  when `openinference` is absent); update `__all__` / module docstring
- `tests/test_observability.py` — extend: add two new test functions:
  - `test_review_session_noop_without_openinference` — monkeypatches the import to raise
    `ImportError`; asserts CM yields without error and `using_attributes` is never called
  - `test_review_session_sets_attributes` — mocks `using_attributes`; asserts called with
    correct `session_id` and `tags=["worker:solid-reviewer", "feature:review"]`

**Test before refresh** (RED first on new tests; GREEN after implementation):
```bash
python3 tests/test_observability.py
python3 hooks/test_requirements.py
```

**stg commands**
```bash
stg new step-18b-session-binding
# add review_session to observability.py; add two test functions to test_observability.py
stg refresh
```

**Note**: `review_session` has NO imports from `workers/` — it lives entirely in
`observability.py`. No coupling to patch-3 contents; could technically land before patch-3,
but placing it after is cleaner reading order.

---

### Patch 5 — `step-18b-fanout`

**Goal**: fan-out coordinator `workers/fanout.py` + `tests/test_fanout.py` (RED → GREEN).

**Files changed**
- `hooks/lib/llm/workers/fanout.py` — **new**: `fanout_review(diff, scope, workers=None) -> FanoutResult`
  (or `-> ReviewReport` if the open question resolves against the tuple; see note below)
  with `asyncio.gather(return_exceptions=True)`, survivor filtering, aggregation, and
  `review_session` binding for each worker + the aggregator
- `tests/test_fanout.py` — **new**: 5-scenario suite (a–e per TDD plan):
  (a) 3 workers → `aggregate` called with 3 reports
  (b) 1 worker raises → `aggregate` called with 2
  (c) all fail → `RuntimeError`
  (d) same `session_id` propagated to every `review_session` invocation (mock records args)
  (e) aggregator also runs inside `review_session`

**Imports inside fanout.py** (all must exist before this patch — confirmed by ordering):
- `hooks.lib.llm.observability.review_session` ← patch-4 ✓
- `hooks.lib.llm.workers.aggregator.aggregate` ← step-10 ✓
- `hooks.lib.llm.workers.code_reviewer` ← step-10 / patch-2 ✓
- `hooks.lib.llm.workers.solid_reviewer` ← patch-3 ✓
- `hooks.lib.llm.workers.appsec_auditor` ← patch-3 ✓

**Test before refresh** (RED → GREEN):
```bash
python3 tests/test_fanout.py
python3 tests/test_review_workers.py    # regression
python3 tests/test_code_reviewer_worker.py  # regression
python3 hooks/test_requirements.py
```

**stg commands**
```bash
stg new step-18b-fanout
# write fanout.py; write test_fanout.py
stg refresh
```

**Open design question** (resolve before writing this patch): should `fanout_review` return a
`FanoutResult(report, session_id)` dataclass rather than bare `ReviewReport`? The smoke script
needs `session_id` to print it. Recommended: yes — add a two-field frozen dataclass to
`fanout.py`; the smoke unpacks it. Does not affect patches 1–4.

---

### Patch 6 — `step-18b-smoke`

**Goal**: CLI smoke script exercising the full fan-out pipeline against a real diff.

**Files changed**
- `hooks/lib/llm/_spikes/v3_fanout_smoke.py` — **new**: loud-fail on missing prereqs (aborts
  if `scripts/prepare-diff-scope` is missing; exits non-zero if `/tmp/review.diff` is empty;
  does not silence `ImportError` for `claude-agent-sdk`); prints per-worker timing, survivor
  count, unified findings, total cost delta (budget ledger delta), and `session_id`

**Test before refresh** (import / syntax check only; no live run in CI):
```bash
python3 -c "import hooks.lib.llm._spikes.v3_fanout_smoke"
python3 hooks/test_requirements.py
```

Live smoke (manual; requires Langfuse running + real diff):
```bash
python3 hooks/lib/llm/_spikes/v3_fanout_smoke.py
```

**stg commands**
```bash
stg new step-18b-smoke
# write v3_fanout_smoke.py
stg refresh
```

---

### Patch 7 — `step-18b-housekeeping`

**Goal**: wire public exports, verify sync, update docs, mark step complete.

**Files changed**
- `hooks/lib/llm/workers/__init__.py` — add `solid_reviewer`, `appsec_auditor`, `fanout_review`
  to `__all__` and `__getattr__` dispatch
- `hooks/lib/llm/__init__.py` — update module docstring to mention Step 18b workers
- `DEVELOPMENT.md` — brief note: Step 18b lands multi-worker fan-out (3 workers, CLI smoke only)
- `/Users/harm/.claude/projects/-Users-harm-Tools-claude-requirements-framework/memory/refactor-current-status.md` — mark Step 18b complete

**Commands to run before refresh** (acceptance gate — all must be green):
```bash
./sync.sh status                          # must be clean (no plugin files touched)
python3 hooks/test_requirements.py
python3 tests/test_review_workers.py
python3 tests/test_fanout.py
python3 tests/test_observability.py
python3 tests/test_code_reviewer_worker.py
```

**stg commands**
```bash
stg new step-18b-housekeeping
# update __init__.py files, DEVELOPMENT.md, memory
stg refresh
```

---

### Full test matrix (run before each `stg refresh`)

| Patch | New tests (RED → GREEN) | Regression gates |
|---|---|---|
| 1 | — (docs only) | — |
| 2 | — (no new test file) | `test_code_reviewer_worker.py`, `hooks/test_requirements.py` |
| 3 | `test_review_workers.py` | `test_code_reviewer_worker.py`, `hooks/test_requirements.py` |
| 4 | `test_observability.py` (2 new fns) | `test_code_reviewer_worker.py`, `hooks/test_requirements.py` |
| 5 | `test_fanout.py` | `test_review_workers.py`, `test_code_reviewer_worker.py`, `hooks/test_requirements.py` |
| 6 | import smoke (syntax) | `test_fanout.py`, `hooks/test_requirements.py` |
| 7 | — (exports + docs) | all 5 test files + `./sync.sh status` + `hooks/test_requirements.py` |
