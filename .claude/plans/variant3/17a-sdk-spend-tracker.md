# Step 17a — SDK monthly spend tracker

## Goal

Build a passive, append-only ledger of every `claude-agent-sdk` `query()` call's
cost (USD) and tokens, plus a `req budget status` CLI that projects monthly burn
against the Agent SDK credit pool. **Soft warnings only** in this step — no
blocking, no per-call enforcement.

## Why now (re-prioritized from the 2026-05-19 plan)

ADR-016 surfaced a billing change effective **2026-06-15**: Max subscribers get a
separate Agent SDK credit pool ($100/mo for Max 5x, $200/mo for Max 20x). Workers
(Step 10) will be called frequently by `/deep-review` and `/arch-review`, and
could exhaust the pool in days without cost visibility. We need a meter before
we scale worker calls — not after.

Step 10 (Agent SDK `output_format` wrapper + aggregator agent) is the planned
next worker pilot. 17a unblocks 10 by giving us **observable cost data on the
existing manual SDK calls** before we automate any further.

## Scope split from the original Step 17 plan

The 2026-05-19 plan bundled two concerns:

| Concern | Lands in | Why split |
|---|---|---|
| **Monthly $-rate against the SDK credit pool** | Step 17a (this plan) | Reactive — uses `ResultMessage.total_cost_usd` already exposed by the SDK. Independent of templates. |
| **Per-call token caps + degradation ladder** | Step 17b (deferred) | Requires the Jinja2 templates from Step 16 to have rendering slots to drop. Pre-call estimation needs tiktoken proxy. |

Step 17b's plan stays in `17-token-budget-enforcement.md` (renamed and amended;
see `17-token-budget-enforcement.md` for the original text preserved as history).

## Validated capability from `claude-agent-sdk`

`ResultMessage` (verified via live import 2026-05-22):

```python
@dataclass
class ResultMessage:
    subtype: str
    duration_ms: int
    duration_api_ms: int
    is_error: bool
    num_turns: int
    session_id: str
    stop_reason: str | None = None
    total_cost_usd: float | None = None   # ← SDK calculates this for us
    usage: dict[str, Any] | None = None   # ← input/output token counts
    result: str | None = None
    structured_output: Any = None
    model_usage: dict[str, Any] | None = None
    permission_denials: list[Any] | None = None
    deferred_tool_use: DeferredToolUse | None = None
    errors: list[str] | None = None
    api_error_status: int | None = None
    uuid: str | None = None
```

**Key insight:** we do not maintain a pricing table. The SDK already has one
and exposes the result via `total_cost_usd`. We just record it.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ V3 callers (spikes, future workers, future tests)           │
│   from hooks.lib.llm.claude import query                    │
└────────────────────────────────┬────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────┐
│ hooks/lib/llm/claude.py (existing thin wrapper, EDITED)     │
│                                                             │
│   async def query(prompt, options=None):                    │
│       agent = _agent_label(options)                         │
│       async for msg in _sdk_query(prompt, options):         │
│           if isinstance(msg, ResultMessage):                │
│               budget.record(msg, agent=agent)               │
│           yield msg                                         │
└────────────────────────────────┬────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────┐
│ hooks/lib/llm/budget.py (NEW)                               │
│                                                             │
│   record(result, agent) → appends one JSONL line            │
│   load_month(yyyy_mm) → iterator over ledger lines          │
│   summarize(now) → {mtd_usd, projected_eom_usd, ...}        │
│   check_thresholds(summary, config) → list[Warning]         │
└────────────────────────────────┬────────────────────────────┘
                                 │
                                 ▼
   ~/.claude/requirements-framework/usage/2026-05.jsonl
   (append-only, one line per query() call)
```

**Why wrap in `claude.py`** (not budget.py directly):

- `claude.py` already exists as the V3-mandated import choke point (R7 from
  Step 11 arch-review). It's the natural place to intercept.
- Avoids relying on every V3 caller to remember `budget.record(...)` after
  each call — same rationale as Step 11's observability auto-init.
- Recording is non-blocking (single JSONL append, ~microseconds) and
  fail-open (errors swallow to stderr per project convention).

## Ledger format

`~/.claude/requirements-framework/usage/<YYYY-MM>.jsonl`, one record per line:

```json
{
  "ts": "2026-05-22T15:30:00.123Z",
  "session_id": "baccc8cb-...",
  "agent": "code-reviewer",
  "models": {"claude-sonnet-4-6": {"input": 1500, "output": 800}},
  "input_tokens": 1500,
  "output_tokens": 800,
  "cost_usd": 0.0245,
  "duration_ms": 12340,
  "is_error": false,
  "repo": "/Users/harm/Tools/claude-requirements-framework",
  "sdk_session_id": "0a1b..."
}
```

- **`agent`** comes from `ClaudeAgentOptions.system_prompt` (parsed) or an
  explicit kwarg the caller passes. When unknown, recorded as `"unknown"`.
- **`models`** mirrors `ResultMessage.model_usage` when present; collapses to
  `{}` for single-model calls where only `usage` is populated.
- **One file per calendar month** keeps the ledger from growing unbounded and
  makes month-aligned queries cheap (no parsing across files).
- **Global scope** (`~/.claude/...`), not per-repo. The SDK credit pool is per
  user account, not per repo.

## Configuration

```yaml
# requirements.yaml — new top-level block
budgets:
  sdk_pool:
    enabled: true                # Gates ledger writes AND warnings
    monthly_limit_usd: 100       # Default Max 5x; bump to 200 for Max 20x
    warn_threshold_pct: 75       # Soft warning fires here
    critical_threshold_pct: 95   # Louder warning here (still soft in 17a)
    timezone: "Europe/Amsterdam" # Used to align "month" boundaries
```

Cascade through global → project → local same as other requirement config
(`config.py` already handles this — no new loader logic needed).

## CLI

```
$ req budget status
SDK pool — month-to-date (2026-05)
─────────────────────────────────────────
  Spend so far:        $34.20
  Projected EOM:       $52.30  (52% of $100 limit)
  Days elapsed:        22 / 31
  Calls recorded:      147
  Top agents (by $):
    code-reviewer       $18.50  (42 calls)
    deep-review-team    $11.20  ( 9 calls)
    arch-review-team    $ 4.50  ( 5 calls)

Status: OK — projection well below 75% warn threshold.
```

```
$ req budget status --month 2026-06
# Same as above, but for explicit month
```

```
$ req budget tail [-n 20]
# Tails the current month's ledger (newest first), human-readable
```

```
$ req budget warn-if-over
# Returns non-zero exit + prints warning if projection crosses warn_threshold_pct.
# Designed for use in handle-prompt-submit.py / handle-session-start.py later.
```

Implementation: extend `hooks/requirements-cli.py` with a `budget` subparser
that dispatches to functions in `hooks/lib/llm/budget.py`.

## Files touched

| Path | Change | Lines (est.) |
|---|---|---|
| `hooks/lib/llm/budget.py` | NEW | ~150 |
| `hooks/lib/llm/claude.py` | EDIT — wrap `query()` and `ClaudeSDKClient` with usage capture | ~30 |
| `hooks/requirements-cli.py` | EDIT — add `budget` subcommand dispatch | ~40 |
| `hooks/lib/config.py` | EDIT — add `BudgetsConfigDict` (TypedDict, `total=False`) and reference from `RequirementsConfigData` | ~15 |
| `tests/test_budget.py` | NEW | ~120 |
| `examples/global-requirements.yaml` | EDIT — show the new `budgets:` block | ~10 |
| `docs/adr/ADR-016-v3-claude-agent-sdk-substrate.md` | EDIT — append "Step 17a landed" note in Operational notes | ~5 |

## Budget projection math

Simple linear extrapolation from elapsed fraction of month. **Stdlib only** —
the project's only non-stdlib dependency is PyYAML, so we use `calendar.monthrange`
to find month length without pulling in `python-dateutil`:

```python
import calendar
from datetime import datetime, timedelta

def project_eom(mtd_usd: float, now: datetime) -> float:
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    days_in_month = calendar.monthrange(now.year, now.month)[1]
    next_month_start = month_start + timedelta(days=days_in_month)
    elapsed_s = (now - month_start).total_seconds()
    total_s   = (next_month_start - month_start).total_seconds()
    if elapsed_s < 3600:  # < 1h into month → projection is meaningless
        return mtd_usd
    return mtd_usd * (total_s / elapsed_s)
```

**Honest limitation:** linear projection over-estimates if spend is front-loaded
in the month (e.g. heavy refactor week) and under-estimates if back-loaded.
Step 17a documents this; a future iteration could use a trailing-7-day rate
instead. Not worth modeling now — point is to surface burn, not predict to
the dollar.

## Acceptance criteria

- [ ] `query()` called from any V3 caller writes a ledger record automatically
- [ ] Ledger writes are atomic (one `open(..., 'a')` + `write` per record,
      no torn lines under concurrent calls in the same process)
- [ ] `req budget status` shows MTD spend, EOM projection, threshold status
- [ ] Setting `budgets.sdk_pool.enabled: false` silences ledger writes and
      `req budget status` reports "disabled" cleanly
- [ ] Threshold-cross warnings are printed (stderr) but never block
- [ ] All ledger I/O is fail-open: a missing/unwritable ledger dir does not
      raise, just logs to stderr (per `handle-stop.py` precedent)
- [ ] Test suite covers: append correctness, month rollover boundary,
      empty-ledger case, malformed-line robustness, projection math
- [ ] `tests/test_budget.py` runs under existing `TestRunner` (no pytest dep)
- [ ] One spike script `_spikes/v3_budget_smoke.py` proves end-to-end:
      call SDK → ledger appended → `req budget status` shows the spend

## Tests

```python
# tests/test_budget.py — outline

class TestLedgerAppend:
    def test_writes_one_line_per_record(self): ...
    def test_records_have_all_required_fields(self): ...
    def test_unwritable_dir_does_not_raise(self): ...
    def test_concurrent_appends_no_torn_lines(self): ...

class TestSummarize:
    def test_mtd_sum_matches_input(self): ...
    def test_skips_other_months(self): ...
    def test_top_agents_ranked_by_cost(self): ...
    def test_empty_ledger_returns_zeros(self): ...
    def test_malformed_line_is_skipped(self): ...

class TestProjection:
    def test_linear_extrapolation_midmonth(self): ...
    def test_first_hour_returns_mtd_unchanged(self): ...
    def test_end_of_month_projection_equals_mtd(self): ...

class TestThresholds:
    def test_under_warn_returns_ok(self): ...
    def test_over_warn_under_critical_returns_warn(self): ...
    def test_over_critical_returns_critical(self): ...

class TestConfigGating:
    def test_disabled_config_skips_ledger_writes(self): ...
    def test_missing_config_uses_defaults(self): ...
```

## Rollback

- Set `budgets.sdk_pool.enabled: false` in config — ledger writes stop, CLI
  reports "disabled".
- If the wrapper itself breaks `query()` somehow, revert `claude.py` to its
  Step 11 form (commit `5edeee0`). The budget module can remain dormant.

## Effort

**~1.5 days.** Slightly under the original Step 17 estimate (1 day) because
we're cutting the degradation ladder and per-call enforcement; slightly over
because we're adding the CLI surface and tests for projection math.

## Depends on

- Step 11 (observability + `claude.py` wrapper) — already done (`5edeee0`)
- Step 09 (schemas) — not strictly required; ledger uses dicts, not Pydantic
- Step 16 (templates) — **explicitly not required** for 17a

## What we are NOT building in 17a

These belong to 17b (or later):

- Per-call token caps with `render_with_budget(...)` degradation ladder
- `PreToolUse` hook integration for `Task`/`Bash` tool prompt estimation
- Hard-blocking when budget exceeded
- `tiktoken` integration for pre-call estimation
- Agent-level budgets (separate from the global pool tracker)
- Latency budgets (deferred to a possible future step; Step 11's AGENT-only
  span limitation will need subprocess-layer logging separately)

## Honest scope notes

- **Linear projection is naive** — see math section. A trailing-7-day average
  would be more honest. Defer.
- **`ResultMessage.total_cost_usd` may be `None`** on some SDK paths (per the
  type hint). When None, record `cost_usd: null` in the ledger and skip from
  the MTD sum. Don't fail.
- **The wrapper changes `claude.py` from pure-reexport to live-wrapper.** This
  means import-time behavior is unchanged but call-time behavior now has a
  recording side-effect. Plan tests should explicitly cover the case where
  the budget module is missing (graceful degradation).
- **No retro-ledger for past calls.** This is a forward-only meter. Past
  Langfuse spans contain cost data but we won't backfill them; the 17a
  ledger is for new calls onward.

## Related ADRs

- ADR-016 — V3 Claude Agent SDK substrate (the source of the June 15 trigger)
