# ADR-014: Refactor Orchestration via Bundled Skill + Three-Agent Fanout

## Status
Approved (2026-05-18)

## Context

The framework gained access to a new skill, `refactor-orchestration`, that captures a workflow for multi-layer top-down refactors too large for a single session. The skill produces a frozen plan plus an orchestrator-prompt that runs in a fresh `claude` session, dispatching mechanical chunks to a Haiku executor and escalating contradictions to a Sonnet investigator. A final Sonnet analyzer writes a retrospective and grows a learnings ledger via rule-of-three promotion to its own templates.

The skill was initially installed globally at `~/.claude/skills/refactor-orchestration/` with its three agents at `~/.claude/agents/refactor-{executor,investigator,analyzer}.md`. Its own SKILL.md declares a coexistence mapping with `requirements-framework`, framing the plugin as optional.

This ADR records the decision to **adopt the skill as a first-class part of the framework** rather than leave it as a global side-installation.

Key considerations:
1. **Source of truth** — two installation locations risk drift.
2. **Discoverability** — bundling makes `/requirements-framework:refactor-orchestrate` discoverable through standard plugin channels.
3. **Learning loop ownership** — the analyzer's rule-of-three promotion is a novel self-evolving pattern; merging it with the framework's existing `session-learning` system would dilute both.
4. **Routing surface** — auto-detecting "this refactor is large" via heuristics adds magic that's hard to predict and easy to abuse.

## Decision

**Bundle the skill, register its three agents via the plugin manifest (frontmatter `name:` stays bare, namespace applied externally), add a deterministic `/requirements-framework:refactor-orchestrate` command per ADR-007. Keep the skill's tight self-contained design intact.**

### Brainstorm decisions captured

| Question | Decision |
|---|---|
| End-state | Bundled into `plugins/requirements-framework/`. Globals at `~/.claude/` deleted. |
| Routing | Explicit `/requirements-framework:refactor-orchestrate` command (deterministic per ADR-007). No auto-detection from branch_size or touched-file heuristics. |
| Why not Agent Teams | The orchestrator is a sequential pipeline (executor → optional investigator → analyzer). ADR-012's carve-out for sequential pipelines applies — `Task` dispatch is the right primitive, not Agent Teams. |
| Requirements bridging | None. User runs `/arch-review` first by convention. The skill itself satisfies no framework requirements. |
| Learning loop relation | Separate from `session-learning`. Two distinct systems with non-overlapping targets. |
| Source of truth | Plugin only. Agents become available as `requirements-framework:refactor-*` via plugin registration; frontmatter `name:` stays bare per plugin convention. |

### Two-tier learning architecture

The skill's existing single-ledger design extends to two tiers:

- **Global ledger** at `~/.claude/refactor-orchestration/learnings.md` (seeded from a plugin template on first run). Promotes against the 5 plugin buckets: `SKILL.md`, `plan-template.md`, `orchestrator-prompt-template.md`, `refactor-executor.md`, `refactor-investigator.md`.
- **Project ledger** at `.claude/refactor-orchestration/learnings.md` (gitignored by default). Promotes against `.claude/refactor-conventions.md` (gitignored, auto-grown by promotions).

The analyzer's workflow gains a classifier step (between current steps 4 and 5) that tags each observation as global or project, defaulting to project on ambiguity.

The convention sheet is **scoped to refactor-orchestration only** in v1; other framework commands (`/arch-review`, `/writing-plans`, `/brainstorming`) do not read it. Cross-command reuse may be considered in a follow-up after real-use data.

### Three-model-tier fanout (a new framework pattern)

This is the first framework component to formally specify model tiers for its agent fanout:

- `refactor-executor` (Haiku) — mechanical chunk execution
- `refactor-investigator` (Sonnet) — read-only diagnosis of plan-vs-reality contradictions
- `refactor-analyzer` (Sonnet) — retrospective + rule-of-three promotion

Existing framework agents do not pin model tiers; the convention is "use what's available." This skill's reliance on the Haiku/Sonnet split for cost-and-latency tuning is acknowledged as a new pattern. It does NOT propagate to other agents in v1 — only refactor-orchestration uses model pinning.

## Consequences

### Positive

- Single source of truth eliminates drift.
- `/requirements-framework:refactor-orchestrate` becomes discoverable via standard plugin channels.
- ADRs, brainstorm decisions, and the skill artifacts now version together.
- Two-tier learning splits global plugin-template evolution from project-specific convention growth, keeping blast radius proportional to observation scope.

### Negative

- Plugin install becomes a prerequisite for using the skill (previously could run standalone).
- The auto-grown `.claude/refactor-conventions.md` (gitignored) is per-developer state in v1; team adoption requires opt-in commit policy.
- Model-tier pinning creates a precedent that other agents may or may not adopt. ADR-014 explicitly does not prescribe it for other components.
- Two-tier learning tier paths are hardcoded in the analyzer agent's prose (v1 limitation). Adding a third tier (e.g., team-level) would require editing the agent body. A future ADR may model tiers as data (`{scope, ledger_path, promotion_target, approval_policy}`) if the need arises.

### Neutral

- The orchestrator prompt still runs in a fresh `claude` session by paste. This is intrinsic to the skill's design (separation of planning context from execution context) and not affected by bundling.
- No auto-satisfy of framework requirements means the user must explicitly run `/arch-review` if those gates are required for the work. Documented in the command's body and in CLAUDE.md.

## Implementation reference

See `docs/plans/2026-05-18-refactor-orchestration-integration-plan.md`.
