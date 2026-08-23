---
name: brainstorming
description: "Use when facing any creative work - creating features, building components, adding functionality, or modifying behavior, before any implementation begins"
git_hash: 238f03d
---

# Brainstorming Ideas Into Designs

Turn an idea into a design the user has approved — with ceremony that matches the stakes.

<HARD-GATE>
Do NOT write code, scaffold a project, or take any implementation action until the user has approved a design. Every task gets a design; only its SIZE varies with the tier.
</HARD-GATE>

## Step 0 — Triage (always, first)

Read `references/triage.md`. Run its vagueness check, classify the task into a tier, and announce the tier in one line ("Treating this as standard tier — feature-sized, one subsystem").

After announcing, record it: `req tier <small|standard|deep> --session <session-id>` (you MAY run this — it only annotates branch state). On a **small** tier this lets the framework skip the plan/validate nudges once the design is approved (ADR-023): brainstorming completion then also satisfies `plan_written` + `plan_validated`, so a trivial fix isn't nudged through `/writing-plans` + `/arch-review`.

| Tier | Fits when | Interview | Artifact | Terminal |
|------|-----------|-----------|----------|----------|
| **small** | Localized, reversible, few files | 1–2 questions max | A few sentences, inline in conversation | User OK → proceed directly to implementation |
| **standard** | Feature-sized | Full flow | Design doc, committed | Invoke writing-plans |
| **deep** | Multi-subsystem / architectural | Full flow + decomposition check | Design doc, committed; user reviews the file | Invoke writing-plans (per sub-design) |

Mis-tiering is recoverable: if the problem grows mid-flow, re-triage upward, announce it, and continue. Never silently stay in a too-small tier.

## The Flow

Work through these in order, loading each playbook when you reach it:

1. **Triage** — vagueness check + tier (`references/triage.md`)
2. **Anchor peek** — read just enough code to sketch credible approaches; not an exploration spree. Deeper reads happen later, on demand. If the project declares a `sentry:` block in its requirements.yaml, also query Sentry (MCP) for unresolved issues in the area being changed — known production errors are design input.
3. **Approaches early** — 2–3 candidates with a recommendation (`references/approaches.md`)
4. **Interview, write-as-you-go** — one question per message; settled answers land in the artifact immediately (`references/interview.md`, `references/design-writeup.md`)
5. **Self-review** — inline checklist, fix inline (`references/design-writeup.md`)
6. **Approval** — small: inline OK; standard: per-section; deep: user also reviews the written file
7. **Terminal** — small: proceed directly to implementation; standard/deep: invoke `requirements-framework:writing-plans`, telling it the tier

For object-oriented / domain-heavy designs, also work through `references/domain-modeling.md`.

## Invariants (every tier)

- **One question per message** — multiple choice preferred; never a question wall.
- **Approaches before deep interviewing** — questions come from trade-off deltas, not a generic checklist.
- **Write-as-you-go** — a settled answer lands in the artifact immediately (standard/deep) or the running summary (small).
- **No implementation before approval** — the HARD-GATE above.
- **YAGNI ruthlessly** — strike speculative features from every design.
- **Artifact rules are keyed on tier only — never on editor mode.** If file writes are unavailable right now, present the design and write the doc at the first opportunity.

## Edge Rules

- User rejects a section → revise that section only; don't restart the flow.
- Request turns out to be multiple independent subsystems → decompose (`references/approaches.md`), sequence sub-designs with the user.
- User answers "you decide" twice in a row → stop interviewing; present the recommended design and ask for one approval.

## Requirements Integration

Completing this skill satisfies the `design_approved` gate of the workflow's design phase (the framework nudges rather than blocks under the default `enforcement: nudge`). After standard/deep approval, `requirements-framework:writing-plans` is the ONLY skill to invoke next.

If the branch was marked `tier=small` (via `req tier small`, Step 0), completing this skill *also* satisfies `plan_written` + `plan_validated` (recorded as `method: tier`), so the derived phase advances straight to **build** — no plan/validate nudges for a small, localized fix (ADR-023).
