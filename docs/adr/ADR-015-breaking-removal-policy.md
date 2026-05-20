# ADR-015: Breaking-Removal Policy for Deprecated Commands and Agents

## Status

Approved (2026-05-20)

## Context

The requirements framework reached version 3.4.2 with a handful of public commands, agents, and config values that had been superseded by newer team-based equivalents. The deprecated artifacts (`/plan-review`, `/quality-check`, `code-simplifier` agent, `briefing_format: rich` config value) were marked deprecated in their `description:` frontmatter via commits `3ca0bde` and `bdd0dc1` on master, with the intent of deletion at a future point.

The original Step 07 simplification plan called for a **2-week soak period** between deprecation marking and actual deletion. The intent: catch surprises where the deprecated path was load-bearing in a way nobody had documented, and give users time to migrate before a hard break.

Two facts collided when the deletion pass was scheduled:

1. **Internal coupling discovered during arch-review.** A multi-agent architecture review of the deletion plan surfaced that the deprecated artifacts were still actively coupled to surviving commands and hooks — not only as documentation references, but as runtime spawn calls. Cross-validated findings (compat-checker + tdd-validator + codex-arch-reviewer) showed that `code-simplifier` was spawned by `/deep-review` and `/pre-commit`, that `handle-plan-exit.py` hardcoded a `/plan-review` user-facing directive, and that `briefing_format: rich` had references in `messages.py`, `message_validator.py`, and `config.py` beyond the obvious dispatcher in `handle-session-start.py`.

2. **The soak period itself becomes a hazard once coupling is known.** If the deprecated artifacts continue to exist for two more weeks while the framework's own internal commands and hooks continue to reference them, the accumulation of accidental dependencies grows, not shrinks. The soak's value is in catching unknown external coupling; it has no value when the internal coupling is now visible and actionable.

This ADR captures the resulting policy decisions.

## Decision

### Policy 1 — Breaking removals happen at major version boundaries

The requirements framework follows semantic versioning. **Public artifacts marked deprecated in a minor or patch release are removed at the next major version boundary.** The cadence is: *deprecated-in-minor → removed-at-major*.

"Public artifacts" includes: commands (`/foo`), named agents (`some-agent`), public config values (`hooks.foo.bar`), and named entries in the plugin manifest (`plugin.json` agents/skills/commands arrays).

The release notes (`CHANGELOG.md` under the corresponding major version's `### Removed` section) must:
- Name each removed artifact.
- Cite the deprecation-marking commit.
- Provide a migration target.
- State that no compatibility shim is provided.

### Policy 2 — Soak periods are NOT mandatory when internal coupling is known

The 2-week soak period was a precautionary heuristic to catch unknown external coupling. When the framework's *own* internal commands, hooks, or skills still reference the deprecated artifact at deprecation-marking time, the soak's value is inverted: it gives the deprecated artifact more time to accumulate accidental internal dependencies.

**Override condition (applies to this branch):** If a `/arch-review` cross-validated review identifies internal coupling between the deprecated artifact and a surviving artifact, the soak period MAY be skipped at the user's discretion. The decision and rationale must be recorded in the CHANGELOG.md entry for the major-bump release.

The soak period remains the default for cases where:
- The deprecated artifact has no identified internal coupling at deprecation time.
- External consumers of the artifact are known to exist (e.g., a published plugin used by other projects).
- The deprecation period was intended to allow time for documentation migration in third-party docs.

### Policy 3 — Lightweight alternatives may be removed when superseded at no user cost

ADR-012 originally prohibited removing `/plan-review` and `/quality-check`, on the rationale that users who preferred lower token cost should always have a working option. This prohibition is **superseded by this ADR** under the following decision criterion:

**A lightweight alternative may be removed when its replacement matches or improves on the lightweight version's primary virtue (low token cost or simple execution) at no user-facing cost increase.**

In the specific case of `/plan-review` and `/quality-check`:
- `/req plan` (conductor) dispatches to `/arch-review` for plan validation. The `/req` conductor itself is lightweight; the heavier team-based review only runs when explicitly invoked.
- `/req review` similarly dispatches to `/deep-review`. The lightweight nature of the user-facing command is preserved.
- The "two paths" cognitive load — knowing when to choose lightweight vs. team-based — is itself a non-trivial user cost that the unification eliminates.

Removing the lightweight alternatives is therefore a net user-experience improvement, not a regression. ADR-012's prohibition (written before `/req` existed) is overridden.

### Policy 4 — Deferred removals are CHANGELOG-documented

If a deprecated artifact cannot be removed at the next major-version boundary (e.g., because surviving artifacts still depend on it and the dependency-restructuring is too large to fit in the major-bump branch), the deferral must be documented in the major-bump's CHANGELOG under a `### Deprecated` section, including:
- The artifact name.
- The reason for deferral (specific dependency).
- The target release for removal.

In the 4.0.0 release shipping with this ADR, `code-simplifier` is deferred under this policy. The dependencies are `/deep-review` and `/pre-commit`'s subagent spawn calls plus the cross-validation rules in `/deep-review.md`; restructuring those is scheduled for 4.1+.

## Consequences

### Positive

- **Predictable removal cadence.** Users and contributors know that deprecated-in-3.x will be removed in 4.0, deprecated-in-4.x will be removed in 5.0. No ambiguity.
- **No accidental accumulation of dead code paths.** Without a removal policy, deprecated artifacts tend to persist indefinitely because every individual deletion is "scary." A scheduled removal at major boundaries makes the deletion routine.
- **Internal coupling forces planning conversations.** Policy 4 means deferred removals are visible in CHANGELOG, prompting follow-up planning for the next major.
- **ADR-012's lightweight-alternative prohibition is no longer a blocker.** The framework can converge on team-based primary paths without violating its own corpus.

### Negative

- **Major-version churn is concentrated.** Users hit multiple breaking changes at once when upgrading across a major boundary. Mitigation: clear `CHANGELOG.md` migration tables.
- **Soak-skip override can be misused.** Future contributors might invoke Policy 2's override condition without a corresponding arch-review having actually identified internal coupling. Mitigation: the override requires CHANGELOG.md rationale; reviewers can verify.

### Neutral

- The 2-week soak is preserved as the default for cases without identified internal coupling. This ADR narrows when soaks are needed, not whether they exist as a tool.

## Affected Artifacts (initial application, 4.0.0)

This ADR's first application is the Step 07 deletion pass shipping in plugin v4.0.0:

| Artifact | Status | Reason |
|---|---|---|
| Command `/plan-review` | Removed | Deprecated in `3ca0bde`; superseded by `/arch-review` + `/req plan`. |
| Command `/quality-check` | Removed | Deprecated in `3ca0bde`; superseded by `/deep-review` + `/req review`. |
| Config `briefing_format: rich` | Removed (code path); deprecation-warning fallback | Deprecated in 3.x; `compact` is the only honored value in 4.0+. |
| Agent `code-simplifier` | **Deferred** (per Policy 4) | Deprecated in `3ca0bde` but still actively spawned by `/deep-review` and `/pre-commit`. Scheduled for removal in 4.1+ after those commands are restructured. |
| ADR-012 prohibition on removing lightweight alternatives | Superseded | See Policy 3. ADR-012 amendment in same release. |

## Related ADRs

- [[ADR-006]] — Plugin-Based Architecture. Component counts updated alongside this removal.
- [[ADR-007]] — Deterministic Command Orchestrators. `/quality-check` was a canonical example; reference updated to `/deep-review`.
- [[ADR-012]] — Agent Teams Integration. Amended in the same release to remove the lightweight-alternative prohibition.

## Decider

Harm Aalbers (user) — decision recorded 2026-05-20 via `/arch-review` of the Step 07 deletion-pass plan, with cross-validated team findings documented in `.claude/plans/simplification/07-deletion-pass-implementation-plan.md`.
