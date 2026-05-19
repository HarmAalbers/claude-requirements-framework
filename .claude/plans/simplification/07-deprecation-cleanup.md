# Step 07 — Deprecation cleanup

## Goal

After Steps 01–06 are deployed and used for ≥2 weeks, remove dead code paths and tighten defaults. **No new functionality — only removal.**

## Why last

Don't remove anything until the new path is proven in real use. Two-week soak period catches surprises (e.g., a command whose old verbose briefing was load-bearing in a way nobody documented).

## What to look at

| Candidate for removal | Risk | Action |
|---|---|---|
| `hooks.session_start.briefing_format: rich` fallback | If anyone re-enabled it, breaks them | Audit logs; remove only if usage = 0 |
| Inline `using-requirements-framework` skill body in hooks | None (replaced in Step 01) | Confirm removed; delete dead template strings |
| `/plan-review` command | Overlaps with `/arch-review` | Mark deprecated in description; remove in next major |
| `/quality-check` command | Overlaps with `/deep-review` | Same as above |
| `code-simplifier` agent | Overlaps with `code-reviewer` per audit | Mark deprecated; keep working for one release |
| Duplicate `MEMORY.md` entries | None | Run a one-shot dedupe pass |

## Implementation

1. For each candidate, run `grep -r "<name>" .` to find references.
2. If references are only internal docs + one consumer command, ok to deprecate.
3. Add `(deprecated; use /req review)` to the command's `description` frontmatter.
4. Open a tracking issue per item; do not delete in this step.
5. In one release after deprecation marking, delete.

## Example

`/plan-review` today says:
```
description: "Validate plan against ADRs, TDD, and SOLID principles, identify preparatory refactoring, then generate atomic commit strategy"
```

After Step 07:
```
description: "DEPRECATED — use /arch-review (team-based) or /req plan (conductor). Will be removed in 4.0."
```

## Acceptance

- [ ] Each candidate has either: been removed, been marked deprecated, OR been justified to keep with a reason in `docs/`.
- [ ] No regressions in `python3 hooks/test_requirements.py`
- [ ] One release-notes entry summarizing the cleanup
- [ ] Plugin version bumped in `plugins/requirements-framework/.claude-plugin/plugin.json`

## Rollback

Each removal is a separate commit. Revert per-commit if needed.

## Effort

0.5 day for the marking pass. Actual deletion: future release.

## Depends on

Steps 01–06 deployed and used for at least 2 weeks.

## Honest scope note

This step is mostly about **discipline**, not code. The discipline is "we do not carry deprecated paths forever." Without this step, simplification work erodes back as people add scope to the deprecated paths because they still exist.
