# Step 17b — re-spec: pre-run budget guard + per-worker cap for `/v3-review`

**Date:** 2026-06-07 · supersedes the relevant half of `variant3/17-token-budget-enforcement.md`
(which is stale — see "Why re-spec"). **Status: SPEC — awaiting approval before build.**

## Why re-spec (the original 17b plan is stale)
The 2026-05-22 plan enforced per-prompt token caps (`render_with_budget` drops `examples`/`retrieval` slots) in the **`check-requirements.py` PreToolUse hook** on **`Task`** tool calls. Three problems, now that we have live data ($6.84 run, `error_max_turns`):
1. **Wrong enforcement point** — `/v3-review` is a standalone Python process (`review_cli → fanout → query()`), never a `Task` tool call, so the PreToolUse hook never sees it.
2. **Inert lever** — "drop examples/retrieval slots" assumes populated slots; retrieval is deferred and the real input bloat is the diff itself.
3. **Models the wrong failure** — the live problems were a per-run total, a runaway worker (`error_max_turns`), and the monthly pool — none of which the original plan addresses.

## Locked decisions (interview, 2026-06-07)
- **Scope:** pre-run budget **guard** + per-worker **cap**. No auto model/scope degradation (that's Step 20-adjacent).
- **Behavior:** **warn + confirm** (soft); a config flag can harden to block. Matches 17a's soft-warning ethos.
- **Spend path:** **V3 `/v3-review` only** — enforce in `review_cli`/`fanout`/`claude.query`. NOT the framework PreToolUse/Task path.

## Builds on 17a (done)
17a = post-hoc monthly ledger (`~/.claude/requirements-framework/usage/<YYYY-MM>.jsonl`), `total_cost_usd` per call, pool `$100/mo` (Max 5x), warn@75/crit@95, `req budget status|tail`, `summarize()`/`project_eom()`/`check_thresholds()`.

## A. Pre-run budget guard (in `review_cli.run_review`, before `fanout_review`)
1. `remaining = monthly_limit − month-to-date` (reuse 17a `summarize(load_month(...))`).
2. `est = estimate_run_cost(diff, worker_count)` — **v1 estimate:** `tokens(diff) × worker_count × $/token_rate`, where:
   - `tokens(diff)` = `tiktoken` on `/tmp/review.diff` if available, else `len/4` heuristic (fail-open).
   - `$/token_rate` = **calibrated from the 17a ledger** (recent total `$` ÷ total input-tokens) if history exists, else a conservative built-in default. The estimate is deliberately rough — it catches "this will blow the pool," not bill-accurate.
3. **Always print** a one-line budget banner before the run: `budget: est ~$X · pool remaining $Y · N workers`.
4. If `est > remaining` (or `> per_run_cap_usd` when set): **warn + confirm** — print the overage and require a `y/N` (interactive, since it runs via `!` foreground) or `--yes` to bypass. `enforce: block` makes it refuse instead of prompt.

## B. Per-worker cap (in `workers/_base.run_worker` / `fanout`)
- Set `max_turns = per_worker_max_turns` explicitly on each worker's `ClaudeAgentOptions` (this is the SDK knob that produced `error_max_turns` — make it a config value, not the SDK default).
- A worker hitting the cap: **keep proceed-with-survivors** (already there) but classify+report it as a **cap hit** (not an opaque failure) in the footer, and flag the run as "degraded (N/M workers capped)".
- *(Deferred, optional)* per-worker input-token ceiling (skip/trim a worker whose estimated input exceeds it). Out of scope for v1 unless wanted.

## C. Config (extend 17a's `budget` block; all fail-open)
```yaml
budget:
  monthly_limit_usd: 100        # 17a (existing)
  enforce: warn                 # warn | block        (17b; default warn)
  per_run_cap_usd: null         # optional hard per-run ceiling (null = pool-only)
  per_worker_max_turns: 30      # SDK max_turns per worker  (tune from live data)
```

## D. Touch points
- `hooks/lib/llm/budget.py` — add `remaining(now)` + `estimate_run_cost(diff, workers)` (+ ledger-rate calibration). Pure, fail-open, tiktoken optional.
- `hooks/lib/llm/review_cli.py` — pre-run banner + guard/confirm before `fanout_review`; `--yes` flag.
- `hooks/lib/llm/workers/_base.py` (+ `fanout.py`) — thread `per_worker_max_turns` into `ClaudeAgentOptions`; classify cap hits.
- `hooks/lib/llm/render.py` (footer) — surface "degraded (capped)" + the budget banner.
- `_load_budget_config()` in `requirements-cli.py` — read the new keys.
- Tests under `tests/` (estimate math, remaining(), guard decision, cap classification) — light-dep, skip if SDK absent.

## E. Acceptance
- [ ] Under budget → prints the banner, proceeds, no prompt.
- [ ] Over budget → warns + requires confirm (or `--yes`); `enforce: block` refuses.
- [ ] `estimate_run_cost` calibrates from ledger when history exists; falls back to default on run-1; works without tiktoken.
- [ ] A worker exceeding `per_worker_max_turns` is reported as a cap hit; run completes with survivors; footer flags "degraded".
- [ ] Every budget path fail-open: a budget error never crashes or blocks a review.

## Open implementation choices (flag if you disagree — else I proceed as written)
1. **Estimate = tiktoken(diff) × workers × ledger-calibrated rate.** Alternatives: SDK `count_tokens` (precise, adds a call/latency per run) or pure historical avg-$/worker (ignores diff size). I chose the hybrid: diff-sensitive + self-calibrating.
2. **Per-worker cap = `max_turns`** (SDK-native, exactly what bit us). A mid-stream $-ceiling is harder (needs streaming cost) → deferred.
3. **Confirm UX = interactive `y/N` + `--yes`** (works because `/v3-review` runs foreground via `!`).
4. **Default `per_worker_max_turns: 30`** is a placeholder — we'll tune from the next live run's data.

## Effort & sequencing
~1 day equivalent (delegated). Pairs with the deferred **Step 20 (sonnet pinning)** — together: 17b bounds spend, 20 lowers per-token cost. Does NOT depend on the generated-file scope filter (parked Task #4) but benefits from it (smaller diff → cheaper estimate).
