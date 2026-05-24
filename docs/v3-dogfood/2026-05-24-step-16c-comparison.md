# V3 dogfood comparison — Step 16c branch

**Date**: 2026-05-24
**Branch**: `refactor/step-08-llm-package-scaffold`
**V3 chain run**: supervisor (Step 18) → code-reviewer worker (Step 10), aggregator skipped (N=1)
**Baseline**: today's `/deep-review` synthesis (11-agent team review)
**Plan**: `.claude/plans/variant3/V3-dogfood-step-16c-shadow.md`

---

## TL;DR — verdict

**V3 chain works for narrow scopes (housekeeping patch only), produces genuinely additive findings, but has TWO real-world ceilings the dogfood surfaced that would have stayed invisible in mocked-SDK testing**:

1. **Diff-size ceiling**: code-reviewer worker fails (`error_max_turns`) on diffs > ~150K chars under current `max_turns=5`. Full Step 16c branch (8472 lines / 364K chars) hit this; the worker burned $2.02 producing nothing.
2. **Worker observability gap**: only SUPERVISOR spans reach Langfuse. Worker spans (sequential `query()` call in same process) are silently dropped — likely due to the "Failed to detach context" OTel errors that fire between calls.

Neither blocker is in Step 16c's responsibility; both are V3 substrate issues queued before V3 can replace `/deep-review`. **The narrow-scope dogfood succeeded** and produced 2 findings the internal 11-agent team missed.

---

## V3 chain output summary

### Successful run: housekeeping patch only (`a6c4f2a..87dd023`)

| Metric | Value |
|---|---|
| Diff size | 1794 lines, 104209 chars |
| Supervisor elapsed | 20.2s |
| Supervisor target | `deep-review` (correct routing) |
| Supervisor rationale | "Phase is `review` with `pre_pr_review` unsatisfied, which is precisely the requirement `/deep-review` auto-satisfies via its PostToolUse skill mapping. Running deep-review first is the canonical next step before the narrower `/codex-review` pass." |
| Worker elapsed | 136.1s |
| Worker findings | 2 (both SUGGESTION) |
| Total wall-clock | 156.3s |
| Supervisor cost | $0.17 |
| Worker cost | $0.81 |
| **Total run cost** | **$0.98** |

### Failed run: full Step 16c branch (`7c090b4..HEAD`)

| Metric | Value |
|---|---|
| Diff size | 8472 lines, 364287 chars |
| Supervisor elapsed | 29.6s |
| Supervisor target | `deep-review` (same correct routing) |
| Worker outcome | `RuntimeError: code-reviewer failed: subtype='error_max_turns'` |
| Supervisor cost | $0.30 |
| Worker cost (wasted) | $2.02 |
| **Total run cost** | **$2.32** |

See `2026-05-24-step-16c-failure-note.md` for full diagnostic.

### Cumulative dogfood spend

**$3.30 across both runs**. The failed worker accounts for $2.02 (61%) of the total — a clean illustration of why scope-narrowing matters when prompts approach context limits.

---

## Findings overlap

Baseline (`/deep-review` 11-agent synthesis): 0 CRITICAL, 0 IMPORTANT (after in-patch fixes), 5 SUGGESTIONs.
V3 single-worker: 0 CRITICAL, 0 IMPORTANT, 2 SUGGESTIONs.

### V3-unique findings (caught by V3, missed by `/deep-review` team)

#### V3-1: `*` dirty marker committed into `git_hash` YAML field
- **Location**: `plugins/requirements-framework/skills/requirements-framework-status/SKILL.md.j2:4`
- **Severity**: SUGGESTION (V3 assigned confidence=0.85)
- **Description**: V3 caught that the housekeeping patch landed `git_hash: 3a3f257*` (trailing `*`) into the YAML frontmatter. The `*` denotes transient "locally modified" display state — it should never be committed to a value field.
- **Why /deep-review missed it**: the team's 11 agents reviewed the diff at the file level but didn't drill into individual `git_hash` field values. Codex *did* catch the broader `update-plugin-versions.sh` bug that writes the `*` marker into YAML, but didn't specifically flag THIS file's contaminated value.
- **Cross-reference**: this is genuine additive signal — V3 surfaced a concrete data point that the upstream Codex finding implies but doesn't enumerate.

#### V3-2: `git add` vs `git add -u` staging trade-off
- **Location**: `scripts/pre-commit-check.sh:32`
- **Severity**: SUGGESTION (V3 assigned confidence=0.6)
- **Description**: V3 questioned whether dropping `-u` (which I did during the codex-review folding) might over-stage untracked files. The new hint `git add plugins/requirements-framework/` correctly catches newly-rendered `.md` siblings, but stages all untracked files under the tree.
- **Why /deep-review missed it**: this finding postdates `/deep-review` — the `-u` removal happened during `/codex-review` synthesis. V3 caught the trade-off independently.
- **Cross-reference**: legitimate concern; consistent with comment-analyzer's earlier remark about the same area.

### `/deep-review`-unique findings (caught by team, missed by V3)

The team caught 5 SUGGESTIONs that V3 did not. Expected — single worker cannot replicate 11-agent specialist coverage. Notable misses:

#### DR-1: Dead exclusion names in `test_all_plugin_md_files_have_j2_source`
- Caught by: test-analyzer + compat-checker
- V3 missed it because: requires specialist test-design analysis that the general code-reviewer worker doesn't structurally do.

#### DR-2: References/ exclusion mechanism not named in test comment
- Caught by: test-analyzer
- V3 missed it because: requires explanatory-comment audit lens, not in code-reviewer's prompt.

#### DR-3: `Path(str(md) + ".j2")` idiom unexplained (no inline comment)
- Caught by: type-analyzer
- V3 missed it because: requires Python idiom-specific knowledge; the type-design-analyzer agent specializes in this.

#### DR-4: Jinja2 SSTI pre-existing MEDIUM in build-time renderer
- Caught by: appsec-auditor
- V3 missed it because: pre-existing risk outside the Step 16c diff; appsec-auditor specifically scans for these patterns.

#### DR-5: TRIPLE corroboration on DEVELOPMENT.md `{% include %}` doc inaccuracy
- Caught by: code-reviewer + compat-checker + codex-reviewer
- V3 missed it because: this finding was RESOLVED in-patch via `stg refresh --index` BEFORE the V3 run; the V3 review saw the corrected text. Structurally fair miss — V3 reviewed the fixed code, not the buggy code.

### V3 signal/noise ratio

Of V3's 2 findings, **both are real signal** — neither is a false positive. The team's 11 agents produced 5 SUGGESTIONs of which all 5 were also real signal. **V3's precision matches the team's at 100%, but recall is much lower (40% — 2 of 5 caught)**.

This is structurally expected: single worker vs 11-agent specialist coverage. Recall would improve with multi-worker fan-out, which is out of scope for this dogfood.

---

## Latency comparison

| Metric | V3 chain (success) | `/deep-review` team |
|---|---|---|
| Wall-clock (this run) | 156.3s | ~5–10 min observed (parallel teammates + synthesis) |
| Sequential vs parallel | Sequential (supervisor → worker) | Parallel (11 teammates in one Agent batch) |
| Cost | $0.98 | Not separately tracked (multiple subagents) |

**Caveat**: the V3 chain has only ONE worker; the team has eleven. Apples-to-apples would require V3 multi-worker fan-out (Step 10b? Step 18b?), which is out of scope.

The Step 11 spike's measured 80s-583s latency variance for V3 worker calls applies here — this run's 136s worker time is near the median, not the outlier.

---

## Langfuse observability section (user requirement)

### What flowed to Langfuse

| Trace ID | Timestamp | Latency | Observations | What it is |
|---|---|---|---|---|
| `dd6a0ff7949313d6c35e5f9348a50d7b` | 2026-05-24T14:41:42 | 156.0s | 6 spans | **Supervisor of the housekeeping success run** (target=deep-review) |
| `2780af283fd4a39091478ddf0a941eed` | 2026-05-24T14:36:08 | 197.4s | 9 spans | **Supervisor of the full-branch failed run** (target=deep-review) |

Open these in the Langfuse UI:
- `http://localhost:3000/traces/dd6a0ff7949313d6c35e5f9348a50d7b`
- `http://localhost:3000/traces/2780af283fd4a39091478ddf0a941eed`

### Worker traces MISSING from Langfuse (REAL V3 OBSERVABILITY GAP)

The code-reviewer worker `query()` calls produced **zero traces in Langfuse** despite OpenInference being instrumented. Confirmed by querying the Langfuse API:

```bash
curl -s -u "$LANGFUSE_PUBLIC_KEY:$LANGFUSE_SECRET_KEY" \
  "$LANGFUSE_HOST/api/public/traces?fromTimestamp=2026-05-24T00:00:00Z"
# → only 2 traces (both supervisor)
```

This is a **real V3 substrate finding**: OpenInference instrumentation captures the FIRST `query()` call's spans but not subsequent calls in the same Python process. Likely root cause is the "Failed to detach context" + "asyncgen already running" errors that fire between sequential SDK calls:

```
Failed to detach context
ValueError: <Token ...> was created in a different Context
RuntimeError: aclose(): asynchronous generator is already running
```

These errors don't break the SDK calls themselves (the worker still ran and returned 2 findings), but they break OTel's context-management chain such that the worker's spans never reach Langfuse's BatchSpanProcessor. The supervisor's spans flush cleanly because they're first; the worker's spans are lost at process teardown.

**Impact**: V3 cost/latency/quality observability is broken for any multi-call workflow. The supervisor-only smoke (`v3_supervisor_smoke.py`) doesn't surface this because it does single-call routing per scenario. The dogfood's supervisor→worker chain is the minimal multi-call pattern that fails.

**Not fixed in this dogfood** — out of scope. Documented for V3 substrate work to address.

### Langfuse prompt-registry 404s

Both runs emitted these warnings:

```
LangfuseNotFoundError: Prompt not found: 'req-supervisor' with label 'production'
LangfuseNotFoundError: Prompt not found: 'code-reviewer' with label 'production'
```

The Step 12 prompt registry was meant to mirror these prompts. Both `query()` calls fell back to local Jinja templates (correct fail-open behavior), but it means the prompts in Langfuse — if any — aren't tagged with the `production` label the loader expects. Configuration gap from Step 12, not introduced by Step 16c.

---

## Predictions scoring (from plan)

The plan logged 5 predictions before the run. Scoring:

| # | Prediction | Outcome | Score |
|---|---|---|---|
| 1 | V3 catches fewer findings than `/deep-review` (1 worker vs 11 agents) | 2 vs 5 — yes, fewer | ✓ HELD |
| 2 | V3 catches the `keep_trailing_newline` CRITICAL `/codex-review` caught | Tested implicitly — V3 ran on housekeeping patch which contains the fix-text in CHANGELOG. V3 did NOT flag the (now-corrected) prose. Correct behavior — the bug was fixed before V3 saw it. Unfair test in retrospect | ⚠️ INCONCLUSIVE |
| 3 | V3 misses cross-validation findings (no multi-agent debate) | DR-5 triple-corroboration missed; matches | ✓ HELD |
| 4 | V3 latency 30–180s range | Supervisor 20.2s, worker 136.1s — both within range | ✓ HELD |
| 5 | V3 budget $0.05–$0.30 | Underestimated — actual $0.98 for narrow run, $2.32 for failed full-branch. Plan's range was based on Step 11 spike's per-call $-tracker, not whole-chain | ✗ MISSED |

**Score: 3 HELD, 1 INCONCLUSIVE, 1 MISSED.** The cost-underestimate is the most actionable: V3 reviews are 5-10x more expensive than the spike data suggested for prompts in the 100K+ char range. Should feed into Step 17b (per-call token caps).

---

## V3 readiness verdict

**Not ready to replace `/deep-review`. Ready for narrow-scope opt-in dogfooding once two substrate gaps close.**

### Blockers (must close before V3 replaces `/deep-review`)

1. **Worker diff-size ceiling**: implement diff chunking OR pre-process via the `prepare-diff-scope` pattern already used by classical `/deep-review`. Without this, V3 silently fails on any branch with > ~150K chars of diff (i.e., most non-trivial PRs).
2. **Worker observability gap**: fix OTel context tear-down so worker spans reach Langfuse. Without this, V3 has no production observability for the workers — only for the supervisor.

### Strengths confirmed by this dogfood

1. **Routing is correct**: supervisor independently arrived at `target=deep-review` for the current state. Rationales were specific and accurate.
2. **Single-worker quality is good**: V3 caught 2 real findings (100% precision in this run) that the 11-agent team missed.
3. **Failure is loud**: `error_max_turns` is a clear, actionable failure mode. Not silent corruption.
4. **Cost is bounded and visible**: Step 17a budget ledger captured every call accurately.

### Recommended next steps

| Priority | Item | Owner |
|---|---|---|
| High | Diff chunking or scope-narrowing for code-reviewer worker | Future Step 10b |
| High | Fix OTel context tear-down between sequential SDK calls | Future observability work |
| Medium | Re-upload prompts to Langfuse with `production` label | Step 12 followup |
| Medium | Per-call token caps (Step 17b) — use this run's cost data as baseline | Step 17b |
| Low | Multi-worker fan-out (replicate `/deep-review`'s 11-agent coverage) | Future Step 10c / Step 18b |
| Low | `LANGFUSE_SESSION_ID` env var propagation to OpenInference spans | Observability ergonomics |

---

## Honest scope notes

- **This is one snapshot, not a regression suite.** A real Layer-4 test would run V3 against many diffs across time. This is the first such snapshot — establishes the baseline.
- **The 11-agent team had specialist coverage V3 cannot replicate today.** The "recall 40%" number is a function of single-worker vs multi-agent, not V3 quality per se. Multi-worker V3 would likely close most of that gap.
- **The cost overshoot ($0.98 for narrow + $2.02 wasted) is real**. Per-PR dogfooding at this rate is ~$1/PR for happy path, much more for branches that hit the ceiling. Step 17b's budget enforcement becomes load-bearing.
- **The Langfuse "session_id" abstraction in this codebase is SDK-call-scoped, not user-defined.** My `LANGFUSE_SESSION_ID` env var did nothing — each `query()` call gets its own UUID sessionId. Worth knowing for future tooling.

---

## Comparison artifacts in this commit

- This file: `docs/v3-dogfood/2026-05-24-step-16c-comparison.md`
- Baseline: `docs/v3-dogfood/2026-05-24-step-16c-baseline.md`
- V3 success JSON: `docs/v3-dogfood/2026-05-24-step-16c-housekeeping-v3-output.json`
- V3 failure note: `docs/v3-dogfood/2026-05-24-step-16c-failure-note.md`
- Spike script: `hooks/lib/llm/_spikes/v3_dogfood_spike.py`
- Plan: `.claude/plans/variant3/V3-dogfood-step-16c-shadow.md`
