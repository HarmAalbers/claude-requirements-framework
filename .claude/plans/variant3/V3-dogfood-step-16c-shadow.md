# V3 Dogfood — Shadow run against Step 16c branch

> **For Claude:** REQUIRED SUB-SKILL: Use requirements-framework:executing-plans to implement this plan task-by-task.

**Goal:** Run the V3 supervisor → code-reviewer worker → aggregator chain (Steps 10+18) against this branch's actual diff (`7c090b4..HEAD`, 32 patches, ~7500 diff lines), capture structured output, and produce a side-by-side markdown report comparing V3 findings against today's `/deep-review` team output. **Shadow mode**: zero changes to existing review pipelines.

**Architecture:** A new spike script `hooks/lib/llm/_spikes/v3_dogfood_spike.py` adapts the existing `v3_spike.py` end-to-end pattern. The fixture diff is replaced by `git diff 7c090b4..HEAD` read at runtime, and aggregator output is written to a structured JSON artifact instead of stdout. **Langfuse instrumentation is mandatory** (user requirement 2026-05-24): the spike hard-fails at startup if `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, or `LANGFUSE_HOST` is missing. Trace IDs from the run are captured in the JSON artifact for the comparison report. A separate markdown report combines the V3 artifact with a manually-captured baseline of today's `/deep-review` synthesis and includes a dedicated Langfuse observability section.

**Tech Stack:** Existing — `claude_agent_sdk`, `hooks.lib.llm.{supervisor,workers.code_reviewer,workers.aggregator,schemas,budget,observability}`, `pydantic` for typed I/O. No new dependencies. The spike inherits the Max-auth + budget ledger + Langfuse instrumentation already proven by `v3_supervisor_smoke.py` and `v3_code_reviewer_smoke.py`. **Langfuse Docker compose must be running** (verified healthy at `http://localhost:3000/api/public/health`) — the spike refuses to run without it per the project's `feedback-loud-smoke-spikes` memory.

---

## Why now

Today we landed Step 16c with three rounds of review (`/arch-review` → `/deep-review` → `/codex-review`). The third round caught a CRITICAL fact-claim error the internal 11-agent team missed — empirical evidence that external AI review is genuinely additive. But all three reviews used the **classical** Claude Code subagent dispatch chain. The V3 substrate (Steps 10 supervisor + worker + aggregator, Step 11 observability, Step 12 prompt registry, Step 16/16b/16c templates, Step 17a budget, Step 18 supervisor) has been built and validated **in isolation** but never exercised end-to-end against a real branch diff under real interactive conditions.

The four-layer test pyramid analysis surfaced today shows we have ~1321 unit/integration tests + 11 smoke spikes + a Ragas eval harness with 5 synthetic cases, but **zero Layer 4 dogfooding**. This patch closes that gap minimally: one V3 chain run on one real branch, side-by-side with today's known-good `/deep-review` output.

## Scope decisions (locked 2026-05-24)

| Decision | Choice | Reason |
|---|---|---|
| Mode | Shadow (standalone script, no wiring into existing commands) | Zero risk to existing workflow; user-confirmed |
| Comparison method | Side-by-side markdown report (subjective qualitative read) | Reuses existing /deep-review output without re-running; user-confirmed |
| Input scope | This branch (`7c090b4..HEAD`, 32 Step 16c patches) | Same scope as today's /deep-review — direct comparison; user-confirmed |
| V3 chain composition | Supervisor → code-reviewer worker → aggregator (single worker) | Only worker built today; multi-worker fan-out is out of scope |
| Baseline source | Today's /deep-review synthesis captured manually from conversation | Saves a Max-budget re-run; the findings are well-documented above |
| Eval-harness integration | Out of scope | Step 15 Ragas harness uses synthetic cases — dogfooding real diffs is a different use case; keep them separate |
| Building new workers | Out of scope | Multi-worker fan-out is a separate question; dogfood is "does the single chain we have work?" |
| Making V3 the default | Out of scope | This is shadow mode only; `/req` Markdown stays primary per ADR-016 |
| **Langfuse observability** | **REQUIRED** (user explicit ask 2026-05-24) | Loud-fail at startup if env vars missing; capture trace IDs in JSON artifact; dedicate report section to spans/links |

## Files touched

**Created (5 new files):**

1. `.claude/plans/variant3/V3-dogfood-step-16c-shadow.md` — this plan
2. `docs/v3-dogfood/2026-05-24-step-16c-baseline.md` — captured `/deep-review` synthesis from today's conversation
3. `hooks/lib/llm/_spikes/v3_dogfood_spike.py` — the shadow runner
4. `docs/v3-dogfood/2026-05-24-step-16c-v3-output.json` — structured V3 aggregator output
5. `docs/v3-dogfood/2026-05-24-step-16c-comparison.md` — side-by-side report + qualitative analysis

**Modified:**
- `~/.claude/projects/.../memory/refactor-current-status.md` — note that V3 has been dogfooded once (informal "Layer 4" milestone)

**Untouched:**
- `hooks/lib/llm/` modules — the spike imports them as-is, zero changes
- Existing spikes — left alone
- The 25/11/21 .md.j2 templates from Steps 16b/16c — not modified
- `/req`, `/deep-review`, `/arch-review` commands — not modified

## Patch breakdown (5 atomic patches)

| # | Patch name | What |
|---|---|---|
| 1 | `step-V3dogfood-plan` | This plan doc |
| 2 | `step-V3dogfood-baseline-capture` | `docs/v3-dogfood/2026-05-24-step-16c-baseline.md` — manual transcription of today's /deep-review findings into structured markdown (CRITICAL=0, IMPORTANT=2, SUGGESTION=~5, all the agent-specific findings) |
| 3 | `step-V3dogfood-spike-script` | `hooks/lib/llm/_spikes/v3_dogfood_spike.py` — supervisor→worker→aggregator on real diff, writes JSON output |
| 4 | `step-V3dogfood-run-and-capture` | Execute the spike against `7c090b4..HEAD`, commit the resulting `docs/v3-dogfood/2026-05-24-step-16c-v3-output.json` artifact |
| 5 | `step-V3dogfood-comparison-report` | `docs/v3-dogfood/2026-05-24-step-16c-comparison.md` — side-by-side analysis + memory pointer update |

## Per-patch procedure

### Patch 1: Plan doc
Already this file. Commit via stg new + git add + stg refresh.

### Patch 2: Baseline capture (estimated 15 min)
Manually transcribe today's `/deep-review` findings into a structured markdown doc with:
- Top-level summary (verdict: READY; 0 CRITICAL, 2 IMPORTANT (both resolved in-patch), ~5 SUGGESTIONs)
- Per-agent findings table (one row per agent, severity counts, key finding)
- Cross-validated findings section (the DEVELOPMENT.md triple-corroboration, the keep_trailing_newline CRITICAL from /codex-review)
- Same format the V3 output report will use, so side-by-side comparison is clean

### Patch 3: Spike script (estimated 30 min)
Adapt `v3_spike.py`:
- Replace `BUGGY_DIFF` constant with `subprocess.run(['git', 'diff', '7c090b4..HEAD'])`
- Replace stdout JSON dump with explicit write to `docs/v3-dogfood/<date>-step-16c-v3-output.json`
- Keep the existing supervisor + worker + aggregator wiring untouched
- Keep budget ledger labeling so `req budget tail` shows the dogfood run
- **Langfuse env vars REQUIRED**: validate `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST` at startup; exit 1 with remediation instructions if any are missing (loud-fail per `feedback-loud-smoke-spikes`)
- **Langfuse health-check REQUIRED**: probe `${LANGFUSE_HOST}/api/public/health` at startup; exit 1 if unreachable
- **Capture trace IDs**: extract the OpenInference trace ID from each SDK call result and include in the JSON artifact alongside the ReviewReport
- Add a `--dry-run` flag for testing without burning Max budget (still validates env + health)

### Patch 4: Run + capture (estimated 5 min Max budget + 15 min wait)
```bash
python3 hooks/lib/llm/_spikes/v3_dogfood_spike.py 2>&1 | tee /tmp/v3-dogfood.log
git add docs/v3-dogfood/2026-05-24-step-16c-v3-output.json
stg refresh --index
```
Estimated Max budget: similar to one `/deep-review` of 11 internal agents but with only 1 V3 worker → likely 1/5 to 1/10 the cost. Capture `req budget tail -n 5` output for the report.

### Patch 5: Comparison report (estimated 30 min)
Side-by-side markdown with:
- **Findings overlap table**: which CRITICAL/IMPORTANT/SUGGESTION findings each chain caught
- **V3-unique findings**: anything V3 caught that the team missed
- **Team-unique findings**: anything the team caught that V3 missed (expected: many, since team had 11 agents)
- **False-positive comparison**: rough qualitative judgment of finding signal quality
- **Latency & budget**: V3 wall-clock + tokens vs /deep-review's effective wall-clock (rough)
- **Langfuse observability section** (REQUIRED): trace IDs from the run, direct links to `http://localhost:3000/traces/<id>`, summary of span structure (supervisor span → worker span → aggregator span), screenshot or text export of the trace tree, latency breakdown per span
- **Honest verdict**: is V3 ready for replacement-mode dogfooding (Phase 2), or are there structural gaps to fix first?

Update `~/.claude/projects/.../memory/refactor-current-status.md` with a new "Dogfooding milestones" subsection listing this run.

## Acceptance

The dogfood is complete when ALL of the following hold:

1. **Spike runs cleanly**: `python3 hooks/lib/llm/_spikes/v3_dogfood_spike.py` exits 0 against this branch's diff
2. **Structured artifact captured**: `docs/v3-dogfood/2026-05-24-step-16c-v3-output.json` exists, validates against `ReviewReport` schema, and includes trace IDs
3. **Langfuse traces visible**: trace IDs from artifact resolve to live spans at `http://localhost:3000/traces/<id>` (verified by curl + screenshot in the comparison report)
4. **Side-by-side report exists**: `docs/v3-dogfood/2026-05-24-step-16c-comparison.md` with all 7 sections (findings overlap + V3-unique + team-unique + false-positives + latency/budget + Langfuse observability + verdict)
5. **Budget delta documented**: report includes `req budget tail` output showing the dogfood ledger entries
6. **Memory updated**: refactor-current-status references this milestone
7. **Working tree clean** after Patch 5; `stg series` shows 5 new patches on the stack
8. **No regression**: 1321 existing tests still pass

## What this does NOT do

- Does not modify any existing command (`/deep-review`, `/arch-review`, `/req`, etc.)
- Does not change which review path Claude Code uses for any real review
- Does not build new V3 workers (only exercises code-reviewer, the one that exists)
- Does not expand the Step 15 eval golden set (real-bug corpus is a separate "Step 15b")
- Does not commit to a verdict that V3 is "ready" — the comparison report's verdict is a recommendation, not a decision
- Does not satisfy any planning requirements beyond what /arch-review naturally satisfies

## Rollback

Per-patch rollback via `stg goto <patch> && stg delete <patch>`. Whole-step rollback: `stg pop -a $(stg series | grep V3dogfood | awk '{print $2}')`. The `docs/v3-dogfood/` directory and its artifacts can be deleted with `git rm -r docs/v3-dogfood/`. No infrastructure touched; rollback is clean.

## Effort estimate

- Plan: ~15 min (this file)
- Baseline capture: ~15 min (transcription from conversation)
- Spike script: ~30 min (adapt v3_spike.py)
- Run + capture: ~5 min budget + ~15 min wait
- Comparison report: ~30 min (qualitative analysis + write-up)
- **Total: ~2 hours active + 1 Max-budget hit**

## Depends on

- Step 10 (supervisor + workers + aggregator wired) — done
- Step 11 (Langfuse observability) — done, **REQUIRED** for this spike per user 2026-05-24 (env vars must be set; localhost:3000 must be healthy)
- Step 12 (prompt loader + load_prompt() wired to workers) — done
- Step 16/16b/16c (Jinja2 templates) — done (the code-reviewer worker reads templated prompts via load_prompt())
- Step 17a (budget ledger) — done, used to track dogfood cost
- Step 18 (supervisor) — done, used to route the initial intent
- A working `/deep-review` baseline — captured today, transcription is the baseline source

## Honest scope notes

- **The comparison will be asymmetric**: V3 chain has 1 worker; /deep-review had 11. We are NOT comparing apples-to-apples — we're checking whether the V3 chain produces *sensible* output on real input. Finding-count parity is not the goal; signal quality is.
- **The baseline is captured manually, not re-run.** This saves Max budget but means the baseline is locked to the synthesis I produced today. If we ever need a regenerable baseline, we'd save `/deep-review`'s structured output during its run (a separate small task; not in this scope).
- **The latency variance from Step 11 (80s vs 583s) might fire during the dogfood run.** If it does, the report should document it as a real-world reproduction of the spike-time observation, not as a defect.
- **The single-shot run is a snapshot.** A real Layer 4 test pyramid would run V3 against many diffs over time. This is the first such snapshot.

## Testing strategy

No new automated tests in this dogfood — the artifacts themselves are the deliverables. Existing test sweep (1321 tests) must still pass after each patch to confirm no infrastructure rot. Pre-existing smoke spikes (`v3_spike.py`, `v3_supervisor_smoke.py`) remain the regression coverage for the V3 chain's internal correctness.

## Risk assessment

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| V3 spike fails to run (import error, SDK auth issue) | Low | Blocks dogfood | Existing smokes already pass under same conditions; if it fails, fix the spike, don't expand scope |
| Latency variance (583s outlier) hits during run | Medium | Long wait, no defect | Set spike timeout to 15 minutes; if it hits, document as data point, not failure |
| V3 finds zero findings on a 7500-line diff | Low-Medium | Suggests V3 chain is too narrow | Expected outcome partially — we're feeding it everything from CHANGELOG prose to Jinja2 verbatim copies. Document the noise/signal ratio. |
| V3 finds something /deep-review missed (false confidence) | Medium | Drives confidence higher than warranted | Apply same triple-corroboration rule to V3 findings before treating them as ground truth |
| V3 cost dwarfs `/deep-review` | Low | Budget concern | Step 17a ledger captures it; if V3 is >2x /deep-review, that's a finding worth its own ADR |
| Branch size limit re-fires | High (already hit twice this session) | Re-approval required | Standing approval covers another 60 min; just satisfy again if needed |

## What I expect to find (predictions, for honesty)

Logging predictions now so the post-run analysis can score them:

1. **V3 will catch fewer findings than /deep-review** (1 worker vs 11 agents). Expected.
2. **V3 will catch the CRITICAL keep_trailing_newline finding** /codex-review caught — only if the code-reviewer worker actually exercises the CHANGELOG prose with enough context. Uncertain.
3. **V3 will NOT catch the cross-validation findings** (DEVELOPMENT.md triple-corroboration) because it doesn't have multiple agents to cross-validate. Expected.
4. **V3 latency will be in the 30–180s range** for a single worker run. Expected.
5. **V3 budget will be $0.05–$0.30** for the run (Step 11 spike data points). Expected.

If predictions 1, 3, 4, 5 hold and 2 holds, the verdict trends positive. If 2 fails AND 1/3 hold, the verdict is "V3 chain works but needs the multi-worker fan-out before it replaces /deep-review."
