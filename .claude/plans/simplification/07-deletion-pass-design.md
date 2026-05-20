# Step 07 — Deletion-pass design (refines `07-deprecation-cleanup.md`)

## Context

The original Step 07 plan executed in two phases:

1. **Marking pass** (commit `3ca0bde` on master) — added `DEPRECATED — …` prefixes to the `description:` frontmatter of `/plan-review`, `/quality-check`, and the `code-simplifier` agent.
2. **Deletion pass** — explicitly deferred in the original plan: *"Effort: 0.5 day for the marking pass. Actual deletion: future release."*

This document defines the deletion pass. The 2-week soak originally gating the deletion is **skipped per user decision on 2026-05-20**. The rationale: the deprecated paths are also still referenced from internal docs and the auto-satisfy hook map, so keeping them around for two weeks gives them another two weeks to accumulate accidental dependencies. Clean break is preferred.

## Decisions made during brainstorming

| Question | Decision | Rationale |
|---|---|---|
| Plugin version after deletion | **4.0.0** (major bump) | Semver-correct for breaking removal of public commands/agents. Matches the deprecation messages' "future major release" wording. |
| Release notes location | **`CHANGELOG.md` at repo root** | Standard Keep-a-Changelog format. Starts the changelog at 4.0.0; prior history references `git log`. |
| `briefing_format: rich` fallback | **Delete unconditionally** | Step 01 already made `compact` the default; the `rich` branch is by definition deprecated. Consistent with the 4.0 clean-break posture. No audit step needed. |
| Tracking issues per item | **Skipped** | The original plan asked for them to enforce a "deprecate-then-delete-later" cadence. We are doing both in this branch, so the tracking-issue ceremony is redundant. |
| MEMORY.md dedupe pass | **In scope** | Cleanup item from the original plan; small effort, fits the "finish remaining items" bucket. |

## Architecture

This change is **subtractive only** for plugin/code, **additive** only for documentation (CHANGELOG, memory update).

### What gets deleted

| Path | Why |
|---|---|
| `plugins/requirements-framework/commands/plan-review.md` | Overlaps with `/arch-review`; deprecated. |
| `plugins/requirements-framework/commands/quality-check.md` | Overlaps with `/deep-review`; deprecated. |
| `plugins/requirements-framework/agents/code-simplifier.md` | Overlaps with `code-reviewer` per audit; deprecated. |
| Rich-format briefing code path in `hooks/handle-session-start.py` (and helpers) | `compact` is the only public format; `rich` is dead. |
| Tests covering only the deleted paths | Atomic with the code they test. |
| Auto-satisfy mappings in `hooks/auto-satisfy-skills.py` pointing at `/plan-review` or `/quality-check` | Dead mappings. |
| `code-simplifier.md` entry in the `agents:` array of `plugin.json` | Manifest must match disk. |
| References in `CLAUDE.md` and `README.md` to the deleted commands/agent | Documentation honesty. |

### What gets added

| Path | Content |
|---|---|
| `CHANGELOG.md` (new, repo root) | Keep-a-Changelog. Sections: `### Removed`, `### Changed`, `### Migration`. Starts at 4.0.0. |
| Memory update at `~/.claude/projects/.../memory/refactor-current-status.md` | Records Steps 03–07 merged to master, soak skipped 2026-05-20, V3 Step 08 next. |

## Patch sequence (atomic stg patches)

| # | Patch name | Files | Notes |
|---|---|---|---|
| 0 | `design-step-07-deletion-pass` | This file | (Already created.) |
| 1 | `update-status-memory-mid-deletion` | `refactor-current-status.md` (memory) | Sets pointer to "deletion in progress." |
| 2 | `delete-plan-review-command` | `commands/plan-review.md` + `CLAUDE.md` + `README.md` + auto-satisfy mappings | Single-command removal. |
| 3 | `delete-quality-check-command` | `commands/quality-check.md` + docs + auto-satisfy mappings | Single-command removal. |
| 4 | `delete-code-simplifier-agent` | `agents/code-simplifier.md` + `plugin.json` agents array + docs | Touches plugin.json (manifest sync). |
| 5 | `delete-rich-briefing-format` | `hooks/handle-session-start.py` + helpers + tests | Code-path removal. |
| 6 | `bump-version-4.0.0` | `plugin.json` version field | Per CLAUDE.md, version bump goes in the patch that justifies it. Bundling at the end keeps individual deletion patches independently revertible without a version-bump ripple. |
| 7 | `add-changelog` | `CHANGELOG.md` | First entry covers the full 4.0.0 surface. |
| 8 | `memory-dedupe` | This project's `MEMORY.md` (if duplicates exist) | Cleanup item. |
| 9 | `update-status-memory-final` | `refactor-current-status.md` (memory) | Step 07 complete; V3 Step 08 next. |

Each patch passes `python3 hooks/test_requirements.py` before the next stacks on top.

## Verification strategy

- Test suite (currently 1279/1279) must pass after every `stg refresh`.
- After patch #5 (rich-format deletion), grep the whole tree for any lingering `rich` references in briefing-related code paths.
- After patch #4 (code-simplifier deletion), confirm plugin manifest loads cleanly via `./sync.sh deploy` and a fresh `claude` session smoke test.
- `/verification-before-completion`, `/deep-review`, and `/codex-review` run at the top of the stack before merge.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Cross-references missed (a skill/agent silently references `/plan-review` or `code-simplifier`) | Grep before each deletion patch; the deletion is a separate commit so any breakage is easy to bisect. |
| `plugin.json` agents-array order is load-bearing | Visual diff before commit; `./sync.sh deploy` runs the plugin and would surface a load error. |
| Briefing tests still exercise the `rich` path | Delete those tests atomically with the code in patch #5. |
| Auto-satisfy mapping prune accidentally removes still-needed mapping | Grep mapping keys before pruning. |
| MEMORY.md dedupe touches something that wasn't a true duplicate | Manual diff; one-line entries pointing at different files are not duplicates even if subjects look similar. |

## Migration messaging (CHANGELOG content)

```markdown
## [4.0.0] — 2026-05-20

### Removed
- Command `/plan-review` — superseded by `/arch-review` (team-based) and `/req plan` (conductor).
- Command `/quality-check` — superseded by `/deep-review` (cross-validated team review).
- Agent `code-simplifier` — superseded by `code-reviewer` per agent-audit findings.
- Config value `hooks.session_start.briefing_format: rich` — superseded by `compact` (now the only value).

### Migration
Update muscle memory and any local scripts:
- `/plan-review` → `/arch-review`
- `/quality-check` → `/deep-review`
- `code-simplifier` → `code-reviewer`
- `briefing_format: rich` → remove the key entirely; `compact` is the default.

There is no shim. The 4.0.0 boundary is intentional: deprecated paths landed in 3.x marking commits (`3ca0bde`, `bdd0dc1`) on master and are removed cleanly here.
```

## Acceptance criteria

- [ ] All deleted files removed from `git ls-files`.
- [ ] `plugin.json` version = `4.0.0`.
- [ ] `CHANGELOG.md` exists at repo root with the 4.0.0 entry.
- [ ] `python3 hooks/test_requirements.py` — zero regressions.
- [ ] `./sync.sh deploy` succeeds and a fresh `claude` session loads the plugin without errors.
- [ ] `/verification-before-completion`, `/deep-review`, `/codex-review` all green at top of stack.
- [ ] `refactor-current-status.md` memory updated to reflect Step 07 complete and V3 Step 08 next.

## Rollback

Each removal is its own stg patch. `stg pop` (without losing the changes) or `git revert <sha>` cleanly undoes a single deletion. The version bump and CHANGELOG patches sit on top so they can be popped first if the rollback is broader than one file.
