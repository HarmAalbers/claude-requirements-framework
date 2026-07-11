# Brainstorming Skill v2 — Tiered Router + Playbooks (Design)

**Date**: 2026-07-11 · **Status**: Approved · **Approach**: B (skill rewrite + targeted machinery alignment)

## Problem

The brainstorming skill body is ~90% identical to the 2026-02-25 superpowers import; all framework
evolution since (nudge chain, typed backbone, enforcement axis) happened around it, not in it.
Concretely:

- **No right-sizing.** The "Anti-Pattern: Too Simple" section mandates the full 6-step process +
  committed design doc for *everything*. Ceremony never matches stakes — the #1 pain.
- **Redundancy.** The same 6-step flow is stated four times (checklist, dot graph, prose,
  "After the Design").
- **Live contradiction.** `brainstorm_directive()` (hooks/lib/brainstorm.py:42-51) injects
  plan-mode-only instructions ("Do NOT create a separate design document or attempt git commits")
  on every substantive prompt in **every** mode, contradicting the skill's own step 5
  (write doc + commit).
- **Two slugs for one action.** Nudges emit `/brainstorming` (skill); YAML advisory messages and
  docs emit `/brainstorm` (a 3-line command shim nothing programmatic references).
- **Stale prose.** "Requirements Integration" still describes block-mode behavior; default is
  nudge since 5.0.0.
- **Portability break.** The shipped skill hard-references `~/.claude/guidelines/python-architecture.md`
  — a dead pointer on every machine but this one.
- **Unresolved deferred question** (nudge-only design doc): "factor domain-modeling out of
  brainstorming" — never decided during the ADR-022 re-cut.
- **Vagueness gap.** The unimplemented 2026-06-06 vagueness-gate note: on vague prompts Claude
  anchors on a guess after an exploration spree instead of interviewing first.

Upstream (obra/superpowers) has since added four portable improvements: inline spec self-review,
a user-review gate on the committed spec file, upfront scope assessment/decomposition, and a
design-for-isolation section.

## Decisions (user-confirmed)

| Decision | Choice |
|---|---|
| Split shape | By phase **and** depth **and** concern — realized as playbooks |
| Anatomy | **One skill** + `references/*.md` playbooks; short router SKILL.md |
| Gate wiring | One front door; `design_approved` stays the only gate; name stays `brainstorming` (zero wiring churn — auto-satisfy + `is_brainstorm` key off it) |
| #1 success criterion | **Right-sizing** — ceremony matches stakes |
| Light path | Small tier skips the doc **and** the writing-plans handoff; keeps explicit user approval |
| Modes | **Plan mode is not a special case.** Artifact rules are keyed on tier only; the skill never mentions modes. If the harness blocks writes at that moment, write the doc at the first opportunity. |
| Scope | Approach B: prose rewrite + 4 bounded machinery fixes; deeper machinery logged as follow-ups |

## Section 1 — Skill anatomy & tiers

`skills/brainstorming/SKILL.md.j2` becomes a ~60-line (rendered) **router**: triage step, tier
table, invariant rules (one question per message; no implementation before approval — HARD-GATE
reworded for the nudge world), flow stated **once** (checklist form; dot graph and duplicate prose
deleted), pointers to playbooks loaded on demand:

| Playbook | Content |
|---|---|
| `references/triage.md` | Tier heuristics (stakes, blast radius, reversibility, novelty) + **vagueness check**: if goal / constraints / success criterion can't each be stated in one sentence, interview before exploring the repo (absorbs the vagueness-gate intent in prose, zero hook code). Announce the chosen tier in one line. |
| `references/interview.md` | Question craft: approach-anchored questions, multiple-choice preferred, one per message, stop conditions, concern modes (product/requirements vs technical). |
| `references/approaches.md` (`.j2`) | Sketch 2–3 approaches early with a recommendation; lazy-dev `{% include 'RULESET.md' %}` moves here (out of the always-loaded router); upstream: scope decomposition, design-for-isolation, existing-codebase norms. |
| `references/design-writeup.md` | Write-as-you-go conventions; single tier-keyed **artifact matrix** (replaces plan-mode special-casing); upstream inline self-review checklist (placeholders, consistency, scope, ambiguity — fix inline, no re-review); deep-tier user review of the written file. |
| `references/domain-modeling.md` | Resolves the deferred question — domain modeling factored into its own concern playbook: golden three + boundary questions; `~/.claude/guidelines/python-architecture.md` pointer made **conditional** ("if it exists"). |

**Tiers** (chosen at triage, announced, revisable upward):

- **Small** — localized, reversible, few files: 1–2 questions max, single recommended approach
  inline (a few sentences), explicit user OK. No doc; no writing-plans handoff; proceed directly
  (nudge world makes the skipped plan gate harmless).
- **Standard** — feature-sized: full flow, design artifact, writing-plans handoff.
- **Deep** — multi-subsystem/architectural: standard + upfront scope-decomposition check (may
  split into sub-designs, each with its own design→plan cycle) + user reviews the committed
  design file + domain-modeling playbook when OO/domain code is involved.

## Section 2 — The flow (reordered, mode-agnostic)

1. **Triage** — tier + vagueness check + concern mix; announce tier. Mis-tiering recoverable:
   re-triage upward mid-flow, say so, continue.
2. **Anchor peek** — minimal targeted context read, just enough to sketch credible approaches.
   Not an exploration spree; deeper reads happen on demand later.
3. **Approaches early** — 2–3 candidates with a recommendation *before* the deep interview.
   Pivot of the redesign: questions emerge from trade-off deltas, not generic interviewing.
4. **Interview, write-as-you-go** — one question per message, multiple-choice preferred; each
   settled answer lands in the artifact (standard/deep) or running summary (small) immediately;
   explore code between questions only as needed.
5. **Self-review** — upstream inline checklist; fix inline, no re-review loop.
6. **Approval** — small: inline OK; standard: section-by-section; deep: user additionally reviews
   the written file.
7. **Terminal** — small proceeds directly; standard/deep invoke
   `requirements-framework:writing-plans`, passing the tier.

**Edge handling**: rejected section → revise that section only. Multi-subsystem discovery →
decompose into sub-designs, sequence with the user. Interview stalls ("you decide" repeatedly) →
stop asking, present recommended design, get one approval.

## Section 3 — Machinery, verification, patches

**Machinery fixes (bounded):**

1. `hooks/lib/brainstorm.py` — `brainstorm_directive()` rewritten mode-agnostic: drop
   "all inside plan mode" and the "Do NOT create a separate design document or attempt git
   commits" instruction; artifact rules live solely in the skill. Update pinned tests
   (hooks/test_requirements.py ~10627, 10831, 10897) + new pin: directive contains no
   mode-specific phrasing. Rebuild bundle.
2. Delete `commands/brainstorm.md` + `.md.j2`; unify every surface on `/brainstorming`:
   plugin README, workflow-index, skill-catalog, requirements-framework-usage, root README,
   PLUGIN-INSTALLATION, and the `design_approved` message in `examples/global-requirements.yaml`.
   No compat shim; user configs referencing the old slug are theirs to update.
3. Portability: conditional guidelines pointer in `domain-modeling.md`; add ponytail credit to
   `ATTRIBUTION.md` (currently only an HTML comment in the skill body).
4. Router rewrite naturally replaces the stale block-mode "Requirements Integration" text.

**Template mechanics**: only `approaches.md` needs a `.j2` source (RULESET include); other
playbooks are plain `.md`. Implementation check: verify `render_prompts.py` globs `references/`
subdirs; if not, one-line glob extension.

**Verification**: `uv run python hooks/test_requirements.py` (green local = 1483/1488),
`uv run ruff check .`, `render_prompts.py --check`, `build_plugin_hooks.py`, live smoke in a
fresh session (nudge text and skill flow agree end-to-end). Version bump **5.0.2 → 5.1.0**.

> **Addendum (2026-07-12, during execution):** shipped as **6.0.0**, not 5.1.0 — removing the
> user-facing `/brainstorm` command is breaking per house precedent (v4.0.0 command removals),
> so the `feat!:` patch carries a major bump + CHANGELOG migration entry.

**Patch plan** (stg on `feat/brainstorming-v2`):

- **p1** skill rewrite: router SKILL.md.j2 + 5 playbooks + rendered outputs + version bump
- **p2** mode-agnostic directive + test updates + bundle rebuild
- **p3** delete command + slug unification
- **p4** chore: adjacent doc-rot (req.md stale phase list omitting verify; skill-catalog retired
  gates `commit_plan`/`tdd_planned`; PLUGIN-INSTALLATION wrong `/pre-commit` gate)

## Follow-ups (explicitly out of scope)

- Gate-flip at actual approval time (today `design_approved` satisfies at skill load).
- Remove plan-enter hook redundancy + `brainstorm_on_enter` vestige.
- Re-nudge-after-branching marker mismatch (session marker suppresses nudge after per-branch
  gate re-arms).
- Hook-level vagueness routing (the 2026-06-06 design note).
- Teach `writing-plans` to right-size from the tier brainstorming passes it.
