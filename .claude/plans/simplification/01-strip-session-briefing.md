# Step 01 — Strip session briefing to <300 tokens

## Goal

Replace the current ~1,500-token requirement table dump in the SessionStart hook with a 3-line briefing. Stop inlining the `using-requirements-framework` skill body twice.

## Why first

Largest single token win. Pure modification of files we own. Reversible in one revert.

## Files touched

- `hooks/handle-session-start.py` — replace verbose briefing with compact version
- `hooks/lib/messages.py` (if briefing template lives there) — update `_status.yaml` template
- `messages/_status.yaml` — add a new `compact` profile if not present

## Implementation

1. Add a new function `build_compact_briefing(state)` that returns at most 4 lines:
   - Line 1: `Phase: <derived> | <N> unsatisfied | Next likely: /req <phase>`
   - Line 2: `Run \`req status --verbose\` for full requirement details`
   - Line 3 (only if a session was recently abandoned): `Resuming branch <X>`
2. Remove the entire "Requirement Definitions" block from the briefing.
3. Remove the entire "Workflow Guide" block.
4. Remove the inlined `using-requirements-framework` skill body. Claude Code already exposes it via the system-reminder skill catalog.
5. Make verbosity configurable via `hooks.session_start.briefing_format: compact|standard|rich` (default `compact`).

## Example

**Before (today)**:
```
## Requirements Framework: Session Briefing
**Project**: ...
... (40+ lines of definitions and tables) ...
```

**After**:
```
Phase: implementing | 3 unsatisfied | Next likely: /req review
Run `req status --verbose` for full requirement details.
```

## Acceptance

- [ ] `python3 hooks/handle-session-start.py < test_fixture.json | wc -c` returns < 600 bytes (≈150 tokens)
- [ ] `using-requirements-framework` skill body no longer appears in hook output
- [ ] `req status --verbose` prints the full table users used to see at session start
- [ ] Existing tests pass: `python3 hooks/test_requirements.py`
- [ ] Setting `hooks.session_start.briefing_format: rich` restores the old behavior

## Rollback

```bash
git revert <commit>
./sync.sh deploy
```

Or set `briefing_format: rich` in `requirements.yaml`.

## Effort

0.5 day

## Depends on

Nothing.
