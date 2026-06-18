# Design Note: Prompt Vagueness Gate (investigation, pre-plan)

**Date:** 2026-06-06
**Status:** Investigation complete — NOT yet planned/implemented. Feeds into a future
`/writing-plans` cycle. This is a design note, not an approved commit plan.
**Session context:** investigated alongside (but separate from) a parked
`workflow:` tuning of `requirements.local.yaml` (gated `codex-review` phase +
`plan-validate` gate → `commit_plan`).

## Problem

When a session starts and the user types a vague, underspecified prompt
("lets investigate x", "build a feature where the user can do Y"), Claude
Code's default behavior is to read dozens of files and anchor on a guess
instead of asking clarifying questions first.

Why existing mechanisms fail:

1. **CLAUDE.md instructions** ("Always ask clarifying questions") sit at the
   top of a huge system prompt — weak steering by the time the prompt arrives;
   recency wins and the helpfulness drive takes over.
2. **Framework gates fire too late.** `design_approved` blocks the first
   *Edit* — but Read/Grep/Glob/Task are untriggered, so the exploration spree
   happens before any gate speaks. Gating Read is a dead end (it would cripple
   legitimate investigation, and `/brainstorming` itself reads files).
3. **`handle-prompt-submit.py` already intercepts every prompt** (UserPromptSubmit
   fires BEFORE Claude processes it; injected `additionalContext` lands adjacent
   to the prompt — maximum recency salience). It currently only emits a passive
   status reminder. This is the interception point.

## Decisions (user-confirmed 2026-06-06)

| Axis | Choice | Rejected alternatives |
|---|---|---|
| Enforcement | **Directive injection** via `additionalContext` | Hard block (`decision: "block"` — 100% but canned message, FP retyping pain); tiered |
| Detection | **Python lexical heuristic** (free, <1ms, deterministic, unit-testable) | Always-on directive (dulls); LLM classifier (2–5s + SDK $ per prompt, bad for a sync hook) |
| Scope | **`design_approved` unsatisfied AND session prompt count ≤ 2** | design-phase-any-prompt; every-session-unconditional |

Key UX insight: the desired response — *Claude itself* saying "this is unclear,
here's what I need to know" — is the directive-injection row, not the hard
block. The directive lets Claude ask smart, repo-aware questions; a block
replaces them with a static hook message.

## Heuristic (v2, empirically validated)

`is_vague(prompt)` trips when ALL hold:

- `< 15` words (tunable)
- contains a **creation-intent** verb: build, add, create, implement, design,
  investigate, improve, make, write, extend, explore, research, rework, redo,
  migrate, refactor, optimize, feature, lets/let's
- does NOT match a **continuation/dispatch exclusion** (prior context
  disambiguates these): continue, proceed, resume, next, step N, phase N,
  recommendation, suggestion, apply, merge, rebase, push, pull, pr, commit,
  release, retry, rerun, conflicts, cleanup, review, plan, skill(s), agent(s),
  check, run, start, save, test(s); leading yes/ok/sure/no/do it/go ahead
- has NO **specificity marker**: backticks, `file.ext`, paths with `/`,
  snake_case, camelCase, `:line` refs, error/traceback/failed text, URLs

Skip entirely: slash commands, `<bash-input>`/`<command-message>` prompts.

### Mechanical fixes found during validation (fold into v3)

1. `step\s*\d\b` fails on two-digit numbers ("step 18") — boundary lands
   between digits. Use `step\s*\d+`.
2. PascalCase (`HourlyRate`) not caught by the camelCase pattern
   (`\b[a-z]+[A-Z]`) — add `\b[A-Z][a-z]+[A-Z]\w*` alternative.
3. "do (it|them|that|all)" exclusion was anchored to start-of-prompt only —
   "Lets do them all" slipped through. Unanchor it.

## Empirical validation (2026-06-06)

Corpus: first 2 real user prompts of every session transcript on this machine —
**580 prompts** across 26 projects (`~/.claude/projects/*/*.jsonl`).

| Version | Trip rate | Notes |
|---|---|---|
| v1 (broad intent verbs, no exclusions) | 33/588 = **5.6%** | Major FP class: continuation prompts ("lets continue", "create a pr", "yes, apply the fix") |
| v2 (creation verbs + continuation exclusions) | 8/580 = **1.4%** | 2 true positives, 3 regex gaps (fixes above), 3 borderline |
| v3 (projected, with the 3 fixes) | ~5/580 ≈ **0.9%** | Majority genuine |

Borderline residue ("write the driver…", "lets look at the deferred items",
"lets actually live confirm"): vague *lexically* but specific *in context*
(handoff/memory/plan docs). Drives the directive-wording principle below.

## Directive wording principle (two-stage precision)

The lexical heuristic is only a **recall** filter; Claude is the **precision**
layer. The injected directive must include a context escape hatch:

> Treat this prompt as underspecified **unless already-loaded context
> (handoff/memory/plan) explicitly covers it** — in that case proceed.
> Otherwise respond with clarifying questions ONLY this turn: do NOT call
> Read/Grep/Glob/Task/Bash. AskUserQuestion is allowed. Then route through
> `/brainstorming`.

This makes false positives nearly free (one self-check, no lost turn).

**Known tension (resolve at plan time):** the escape hatch gives Claude an
out, and over-trusting its own guess is the original disease. Bias the wording:
"when in doubt, ask" — context must EXPLICITLY cover the prompt, plausibility
is not enough.

False-positive cost asymmetry confirmed the enforcement choice: at ~1% trip
rate a wrong directive costs one sentence of reasoning; a wrong hard block
eats real prompts and forces retyping.

## Implementation sketch (for the future plan)

- Location: `hooks/handle-prompt-submit.py` (+ new helper, e.g.
  `hooks/lib/vagueness.py`, so the heuristic is unit-testable in isolation)
- Conditions: `design_approved` enabled + unsatisfied for session; prompt
  count ≤ 2 (SessionMetrics already tracks `UserPrompt` tool uses); not a
  slash command
- Config block: `hooks.prompt_submit.vagueness_gate`
  (`enabled`, `max_words`, `max_prompts`) — follow HOOK_DEFAULTS pattern in
  `hooks/lib/config.py`
- Directive text externalized per ADR-011 (message YAML system)
- Fail-open everywhere, as all hooks
- Tests in `hooks/test_requirements.py` — include the 8 v2-tripped prompts and
  a sample of continuation prompts from the corpus as fixtures
- Plugin version bump (hook ships in the bundled plugin) — minor (new feature)
- Validation rerun: the corpus-analysis script (in the 2026-06-06 session
  transcript) can be rerun against transcripts to regression-check trip rate
