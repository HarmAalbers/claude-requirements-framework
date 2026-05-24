# V3 dogfood — full-branch run failure (Step 16c)

**Date**: 2026-05-24
**Spike**: `hooks/lib/llm/_spikes/v3_dogfood_spike.py`
**Diff range**: `7c090b4..HEAD` (full Step 16c scope)
**Diff size**: 8472 lines, 364287 chars
**Outcome**: ✗ Worker phase failed with `error_max_turns`

## What happened

The first run of the V3 dogfood spike targeted the full Step 16c diff (`7c090b4..HEAD`). The supervisor phase succeeded cleanly:

```
[supervisor] target=deep-review (29.6s)
  rationale: Phase is `review` with `pre_pr_review` unsatisfied — `/deep-review` is the team-based PR review skill...
```

The code-reviewer worker, however, failed:

```
RuntimeError: code-reviewer failed: subtype='error_max_turns'
```

The SDK exhausted its `max_turns=5` retry budget trying to produce a valid `ReviewReport` for the 364287-char prompt and gave up.

## Why this happened

The code-reviewer worker uses `max_turns=5` (see `hooks/lib/llm/workers/code_reviewer.py:33`). With a 364K-char diff embedded in the rendered Jinja prompt template (`hooks/lib/llm/prompts/code-reviewer.md.j2`), the total prompt approached the model's effective context limit. The model's structured-output retry loop couldn't converge on valid JSON within 5 turns. The SDK terminated with `error_max_turns`, which the worker propagates as `RuntimeError`.

## Diagnostic data

| Metric | Value |
|---|---|
| Diff lines | 8472 |
| Diff chars | 364287 |
| Supervisor cost | $0.30 |
| Worker cost (wasted) | $2.02 |
| Total cost of failure | $2.32 |
| Wall-clock to failure | ~7 minutes |
| max_turns setting | 5 |
| Langfuse session | `v3-dogfood-step-16c-20260524T143553` |

## Spike-side robustness gap (fixed in same patch)

The spike crashed on the worker exception before writing the output JSON artifact. The dogfood goal is to learn what V3 does on real input — including failures — so the spike was hardened to:
- Catch worker exceptions
- Record error type + message in the artifact
- Continue to artifact write + summary print

After the fix, the spike was re-run on a narrower scope (`a6c4f2a..87dd023` — just the housekeeping patch). That run succeeded; output at `2026-05-24-step-16c-housekeeping-v3-output.json`.

## What this means for V3 readiness

**V3 chain has a production-relevant diff-size ceiling that internal tests never exercised.** A real-world `/deep-review`-equivalent on the full Step 16c branch fed 8472 lines to the team-based dispatch (which the existing pipeline handled fine via per-agent diff scope files at `/tmp/review_scope.txt` and `/tmp/review.diff`, plus each agent's own early-exit triage). The V3 single-worker chain cannot replicate this — the entire diff goes into one prompt and either fits or doesn't.

### Concrete next steps (not in scope for this dogfood)

1. **Increase `max_turns`** on the code-reviewer worker to 10+ for large diffs. Cheap; might be enough for diffs in the 200K-char range. Doesn't fix the fundamental context-limit problem.
2. **Implement diff chunking** at the worker level. Split large diffs into <50K-char chunks, run worker N times, aggregate. Adds the multi-worker fan-out that V3 currently lacks.
3. **Adopt the `prepare-diff-scope` pattern from the classical pipeline**: pre-process the diff so the worker only sees changed files relevant to its scope. Reuses existing infrastructure.
4. **Add a diff-size warning at the supervisor** that downstream-routes large reviews to a chunking path. Architectural change; not a quick fix.

### Why we're keeping this run documented

This was the spike's most valuable finding. Internal tests with mocked SDK responses never exposed this ceiling because mocks don't burn tokens. The dogfood revealed a real boundary in ~$2 of wasted budget — cheap insurance against shipping a "V3 review" command that silently fails on real branches.

## Langfuse traces

Even though the worker failed, the OpenInference instrumentation should have emitted spans up to the point of failure. Check:

```
http://localhost:3000/sessions/v3-dogfood-step-16c-20260524T143553
```

The supervisor span should be a complete success; the worker span should show the `error_max_turns` termination.

## Related observability concerns surfaced

Both runs emitted these OpenInference errors at process teardown:

```
Failed to detach context
ValueError: <Token ...> was created in a different Context
RuntimeError: aclose(): asynchronous generator is already running
```

These appear to be benign (spans still reach Langfuse) but indicate the OTel context-management plumbing has issues. Not introduced by Step 16c; pre-existing in the V3 substrate. Worth a separate investigation but does not block dogfood.

## Also: Langfuse prompt-registry 404s

The supervisor and worker both attempted to fetch prompts with `label:production` from the Langfuse registry and got 404s:

```
LangfuseNotFoundError: Prompt not found: 'req-supervisor' with label 'production'
LangfuseNotFoundError: Prompt not found: 'code-reviewer' with label 'production'
```

This is a configuration gap from Step 12 (prompt registry mirror) — the prompts exist in Langfuse but aren't tagged with `production` label. Both calls fell back to local Jinja templates, which is the correct fail-open behavior. Worth verifying the prompts are uploaded with the expected labels.
