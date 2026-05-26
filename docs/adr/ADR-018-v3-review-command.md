# ADR-018: `/v3-review` — SDK Fan-out Exposed as an Additive Review Command

## Status

Approved (2026-05-26)

## Context

[ADR-016](ADR-016-v3-claude-agent-sdk-substrate.md) established the V3 substrate;
[ADR-017](ADR-017-multi-worker-review-fanout.md) recorded the multi-worker fan-out
coordination pattern, validated end-to-end by Step 18b's live smoke ($2.84, 3 workers,
one Langfuse session, accurate findings). 18b was deliberately CLI-smoke-only — it proved
the machinery but exposed no user-facing entry point.

[ADR-012](ADR-012-agent-teams-integration.md) designates the **team-based `/deep-review`**
(Claude Code Agent Teams) as the *primary recommended* review approach. The open question
ADR-017 flagged: *"Whether V3 fan-out eventually replaces the Agent Teams substrate for
`/deep-review` is deferred; if that replacement is pursued it warrants its own ADR."*

This ADR resolves that question for now: **fan-out is exposed as a new, additive command,
not as a replacement.**

## Decision

**Add `/v3-review`: a plugin command that runs the SDK fan-out over a diff at parity with
`/deep-review`'s reviewer roster, renders the unified report into the ADR-013 markdown
format, and satisfies `pre_pr_review`. The team-based `/deep-review` is left unchanged.**

### Why additive, not a replacement

- **No ADR-012 breakage.** `/deep-review` remains the documented primary path; `/v3-review`
  is an opt-in alternative. Users and the `/req` conductor keep working unchanged.
- **Spend containment.** At ~11 workers the fan-out costs roughly $8-12/run, and Step 17b
  (per-call budget caps) is not yet landed. Making fan-out its *own* command means it is
  never the silent default — invoking it is an explicit, bounded choice. Replacing
  `/deep-review`'s body would make $8-12 the default review cost before caps exist.
- **Reversibility.** A new command is `git revert`-able with zero blast radius on the
  existing review path.
- **Shared gate is intentional, not a demotion.** Both `/deep-review` and `/v3-review`
  satisfy `pre_pr_review`. This is deliberate: the gate expresses *review quality was
  performed*, not *which substrate performed it*. Offering an SDK path to the same gate does
  not dilute ADR-012's "primary recommended" designation of the team path — a user simply
  chooses their substrate; both clear the gate legitimately.

## Known limitation — corroboration-rule divergence (not just a deferred refinement)

`/deep-review`'s team lead applies an explicit cross-validation rule table (ADR-013): when
specific agent pairs flag the same region, severity is *escalated* (e.g. code-reviewer +
silent-failure-hunter on the same lines → CRITICAL; bug + no-tests → both CRITICAL). The
fan-out aggregator does something related but different: it merges findings by semantic
similarity / location proximity and attributes sources, but has **no agent-pair escalation
logic**. 

Consequence: for the same diff, `/v3-review` may surface as **IMPORTANT** a finding that
`/deep-review` would **escalate to CRITICAL**. This is a genuine precision difference at the
severity margin, not merely a presentation gap. It is acceptable for v1 because the aggregator
still produces qualitatively comparable *coverage* (the same underlying issues are reported),
and rule-based escalation reduces false-negatives only at the margin — but it means
"parity" is at the coverage/gate level, not bit-for-bit on severity. Porting the corroboration
rule table is deferred (see plan §Deferred); until then this divergence stands and is the
reason a reviewer might see a CRITICAL from `/deep-review` that `/v3-review` rated IMPORTANT.

### Parity choices

- **10-worker roster** mirrors `/deep-review`'s always-on reviewers (code-reviewer,
  silent-failure-hunter, test-analyzer, backward-compatibility-checker, type-design-analyzer,
  comment-analyzer, tenant-isolation-auditor, appsec-auditor, compliance-auditor) **plus**
  `solid-reviewer` as a bonus SOLID perspective. The deprecated `code-simplifier` (overlaps
  code-reviewer; slated for removal) is **excluded** — building a new worker for an agent being
  removed isn't worth it. Each worker is a pure `output_format` delegate to `_base.run_worker`.
- **Deterministic tool-gate first.** Like `/deep-review` Step 3, a ruff/pyright pre-flight
  blocks the run on CRITICAL tool errors *before* spending on 11 parallel LLM calls —
  "don't review code that doesn't lint." This is a subprocess step, not a fan-out worker.
- **ADR-013 markdown output + `pre_pr_review` satisfaction** so `/v3-review` is a genuine
  drop-in: same report shape, same verdict rule (CRITICAL>0 → FIX ISSUES FIRST; IMPORTANT>5
  → REVIEW RECOMMENDED; else READY), same gate.

### Deferred

- `codex-review-agent` (Codex CLI substrate, not `output_format`) and `frontend-reviewer`
  (conditional on `.tsx/.css`) — kept out of v1 to preserve a single worker pattern.
- `/deep-review`'s explicit cross-validation **corroboration rule table** — the fan-out
  aggregator already does semantic merge + source attribution, so v1 renders the unified
  report directly. Porting the rule-based escalation is a later refinement, not a v1 gap.

## When to use which

- **`/deep-review`** (team): the default; broadest substrate; corroboration rule table; no
  per-run $ cost beyond normal Claude Code usage.
- **`/v3-review`** (fan-out): when you want typed/structured output, one filterable Langfuse
  session per run, per-agent cost attribution, and the eval-harness-scoreable worker pattern
  — accepting the ~$8-12 SDK spend and the `aclose()` parallel-teardown noise (ADR-017).

## Consequences

**Positive:** the proven fan-out becomes usable; structured output + observability + eval
become available for real reviews; the team path is untouched and remains the safe default.

**Negative / accepted:** two review commands to maintain; ~$8-12/run with no caps until 17b
(bounded by opt-in invocation); the aggregator now digests up to 11 reports (larger input —
watched for the empty-success/size edge fixed in 18b); the `aclose()` teardown race is more
likely at N=11 (non-fatal, ADR-017).

## Reversibility

Revert the Step 18c patches: removes `/v3-review`, the entry script, renderer, tool-gate,
the 8 new workers, and the auto-satisfy mapping. `/deep-review` and all of 18b are
unaffected. The `plugin.json` bump reverts with the command.

## Related ADRs

- **ADR-012** (Agent Teams) — designates team `/deep-review` as primary; this command is the
  additive SDK alternative, not a replacement.
- **ADR-013** (Standardized Agent Output Format) — `/v3-review` renders the same markdown
  shape; the corroboration *escalation* rules are the known divergence above.
- **ADR-016** (V3 Agent SDK substrate) and **ADR-017** (fan-out coordination) — the substrate
  and coordinator this command exposes.
