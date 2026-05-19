# Step 20 — Pin `model: sonnet` on review agents

## Goal

Add `model: sonnet` to the 20 review agents that currently inherit the orchestrator's model. Reduces cost on `/deep-review` and `/arch-review` runs (which would otherwise run 13 / 7 Opus-powered agents).

## Why last

Costs nothing in tokens but reduces dollars. Easiest landing point after all the V3 structural work is in place. Also: best informed by the eval data from Step 15 — if any agent loses quality on Sonnet, leave it unpinned.

## Files touched

20 agent `.md` files under `plugins/requirements-framework/agents/`.

Excluded (already pinned):
- `comment-cleaner.md` (haiku)
- `import-organizer.md` (haiku)
- `refactor-executor.md` (haiku)
- `refactor-investigator.md` (sonnet)
- `refactor-analyzer.md` (sonnet)

## Implementation

Mechanical edit. For each unpinned agent, add `model: sonnet` to frontmatter:

```yaml
---
name: code-reviewer
model: sonnet     # ← add
description: ...
allowed-tools: [...]
git_hash: ...
---
```

Use `./update-plugin-versions.sh` to refresh git_hash fields after the bulk edit.

## Validated assumption

From Claude Code plugin docs: the `model` field in agent frontmatter takes precedence over orchestrator default. Confirmed by inspection of the 5 already-pinned agents in the codebase.

## Example cost change

`/deep-review` recruits 13 agents on a typical PR:
- Before: 13 × Opus 4.7 × ~8000 tokens ≈ **costly**
- After: 13 × Sonnet 4.6 × ~8000 tokens ≈ **~5–7x cheaper**

For routine code review where Opus reasoning isn't earning its premium, this is straight savings.

## Acceptance

- [ ] All 20 target agents have `model: sonnet` in frontmatter
- [ ] `./update-plugin-versions.sh --check` shows no missed updates
- [ ] After a `/deep-review` run on a known-bug fixture, the Ragas score (from Step 15) stays within ±0.05 of pre-pin baseline
- [ ] No test failures
- [ ] Cost per `/deep-review` invocation (from Langfuse) drops by the expected ~5x

## Rollback

Remove the `model: sonnet` lines if quality regression is observed in Ragas scores.

## Effort

0.5 day

## Depends on

Step 15 (eval) — so you can measure whether quality regressed after pinning.

## Honest scope note

If any specific agent's Ragas score drops noticeably (>0.1) after switching to Sonnet, unpin it. The point is cost-efficiency without quality loss — not blanket downgrade. Track per-agent quality on the Langfuse dashboard.

## Final result of V3

After this step, the framework is:

- **Reproducible**: every prompt is versioned in Langfuse; rollback is a label switch
- **Observable**: every Claude call is a Langfuse span with cost, latency, schema
- **Evaluable**: nightly Ragas runs scored against a golden set
- **Version-controlled**: prompts as templates in git; mirrored to Langfuse
- **Retrieval-augmented**: each session starts with the top-3 similar prior sessions
- **Cost-rational**: Sonnet on review agents; Haiku on mechanical agents; Opus only on the supervisor

That is the production-grade LLM platform for software engineering Variant 3 was designed to deliver.
