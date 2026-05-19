# Step 06 — Migrate existing commands to aliases

## Goal

Keep all current commands working (`/deep-review`, `/arch-review`, `/brainstorm`, etc.) but recast them as **thin aliases** that document their place in the `/req` workflow. No behavior change for users who type them directly.

## Why now

After Step 05, the conductor exists. Users who already know `/deep-review` don't need to relearn. But discoverability shifts to `/req`, and the alias notes the relationship so newcomers see one map, not twelve.

## Files touched

- `plugins/requirements-framework/commands/brainstorm.md` — already a wrapper, add note
- `plugins/requirements-framework/commands/write-plan.md` — already a wrapper, add note
- `plugins/requirements-framework/commands/execute-plan.md` — already a wrapper, add note
- `plugins/requirements-framework/commands/arch-review.md` — large body, add header note
- `plugins/requirements-framework/commands/plan-review.md` — large body, add header note
- `plugins/requirements-framework/commands/deep-review.md` — large body, add header note
- `plugins/requirements-framework/commands/quality-check.md` — add header note
- `plugins/requirements-framework/commands/pre-commit.md` — add header note
- `plugins/requirements-framework/commands/codex-review.md` — add header note
- `plugins/requirements-framework/commands/commit-checks.md` — add header note
- `plugins/requirements-framework/commands/session-reflect.md` — add header note
- `plugins/requirements-framework/commands/refactor-orchestrate.md` — add header note

## Implementation

For each command, add a single-line header note immediately under the frontmatter, e.g.:

```markdown
---
name: deep-review
...
---

> **Workflow position**: invoked by `/req review`. Run directly to override conductor.

# Deep Review ...
```

The note is < 30 tokens, costs nothing to skip if Claude already knows what command was invoked.

## Example

User runs `/deep-review` directly: same behavior as today. The header note is a comment for human readers and Claude.

User runs `/req`: conductor derives `review`, invokes `/deep-review` which still has its full body. Identical outcome.

## Acceptance

- [ ] All 12 existing commands still pass their own existing usage
- [ ] Each command file has the "Workflow position" header note
- [ ] `req status` continues to work
- [ ] `./sync.sh deploy` is run; deployed copies match repo

## Rollback

Strip the header notes — they have no functional effect.

## Effort

1 day (12 mechanical edits + verification).

## Depends on

Step 05 (`/req` must exist for the note to point at it meaningfully).
