# Step 01 — Strip session briefing to <300 tokens

## Goal

Replace the current ~1,500-token requirement table dump in the SessionStart hook with a 3-line briefing. Stop inlining the `using-requirements-framework` skill body twice.

## Why first

Largest single token win. Pure modification of files we own. Reversible in one revert.

## Files touched

- `hooks/handle-session-start.py` — replace verbose briefing with compact version
- `hooks/lib/messages.py` (if briefing template lives there) — update `_status.yaml` template
- `messages/_status.yaml` — add a new `compact` profile if not present

## Implementation (as shipped)

**Status: implemented** — see commits 6921840, 1a73050, fcc2d1c, d2e16ff, plus the follow-up cleanup commit that removed the legacy `injection_mode` shim per user direction (no backwards compatibility).

1. **`hooks.session_start.briefing_format` is the only config key.** Values: `compact | standard | rich`. Default `compact`. The hook reads it via `config.get_hook_config('session_start', 'briefing_format', 'compact')` — no shim, no alternate names. Unknown values fall back to `compact` with a warning.
2. **The default for all sources is `compact`.** `format_adaptive_status` no longer routes by source — `briefing_format` is the single source of truth. Source remains a positional argument for backward signature compatibility but is unused.
3. **`format_compact_status` was tightened in place** — no parallel `build_compact_briefing` was added. The existing function already produced ~150 tokens; only the rendering was simplified.
4. **The inlined `using-requirements-framework` skill body is removed unconditionally.** Lines 753–793 of the prior implementation (the bootstrap injection block with its glob fallback into `~/.claude/plugins/cache`) are deleted. Users who want the skill content can invoke it explicitly via the Skill tool — the system-reminder skill catalog still surfaces its name and description.
5. **`format_full_status` (the deprecated wrapper) is deleted** — no callers remained.
6. **All example configs updated**: `.claude/requirements.yaml`, `examples/global-requirements.yaml`, `hooks/lib/feature_catalog.py` now use `briefing_format: compact`.

## Why no backwards compatibility

The user directed (2026-05-19): "we do not need backwards compatibility, I prefer clean code, delete old stuff when needed." This is a single-user framework — there is no external contract to preserve. The `injection_mode` key, the `auto` value, and the deprecated `format_full_status` wrapper were all deleted rather than kept as deprecated aliases. See `[[feedback-no-backwards-compat]]` in memory.

## Arch-review trail

The seven-agent arch-review (adr-guardian, compat-checker, tdd-validator, solid-reviewer, refactor-advisor, commit-planner, codex-arch-reviewer) produced cross-validated findings. The team agents went past their advisory remit and implemented the four primary commits directly during analysis (see Commit Strategy section). The follow-up cleanup commit removed the conservative `injection_mode` shim they had added, on user direction.

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

## Acceptance — verified

- [x] Hook output for a 3-requirement startup fixture: **243 bytes** (acceptance target was < 600). Measured 2026-05-19.
- [x] `using-requirements-framework` skill body absent from hook output — verified by `test_session_start_bootstrap_removed`
- [x] `req status --verbose` still prints the full requirement table — verified manually
- [x] Full test suite passes: **1267/1267** — `python3 hooks/test_requirements.py`
- [x] Setting `briefing_format: rich` restores the rich startup briefing — verified by `test_session_start_briefing_format_config`

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

---

## Preparatory Refactoring

Analysis of `hooks/handle-session-start.py` (~808 lines) against the three questions.

### 1. Extract formatting functions into `hooks/lib/briefing_formats.py`?

**Recommendation: No. Do not extract before Step 01.**

The four functions (`format_compact_status`, `format_standard_status`, `format_rich_status`, `format_adaptive_status`) plus their helpers (`_get_requirement_status_data`, `_shorten_skill_name`, `_group_by_resolve_action`, `_format_quick_start`) are ~420 lines — more than half the file. Extracting them would:

- Produce a module that exists purely for Step 01 to then gut. You'd be doing two diffs where one suffices.
- Introduce a new import path that tests and the hook both reference, then the import disappears when the content shrinks. Net effect: churn with no conceptual gain.
- The functions are not shared with any other hook today. Moving them creates a module boundary that carries no signal (there's no second consumer to justify the seam).

**Tradeoff**: If Step 01 leaves a non-trivial `format_standard_status` and `format_rich_status` intact (because `briefing_format: rich` must restore old behavior), extraction would keep `handle-session-start.py` under ~400 lines. But that's a post-Step-01 concern, not a prerequisite.

**Verdict**: Tight-en in place. Run Step 01 directly against the current file.

---

### 2. Extract the bootstrap skill injection before deleting it?

**Recommendation: Yes, but only as a named helper — not a separate module.**

The bootstrap block (lines 754–793) does four distinct things: constructs a header string, locates the skill file (with a fallback glob), strips frontmatter, and appends to `parts`. It is currently interleaved inside `if inject_context:`, which means the deletion will touch lines 753–793 while also touching the `format_adaptive_status` call on line 748 and the `parts.append(status)` on line 749. That's a 40-line removal that also brushes the neighboring status-injection code — exactly the kind of diff that introduces accidental regression.

**Concrete suggestion**: Extract lines 753–793 into a `_inject_bootstrap_skill(parts, logger)` helper *in the same file* (a one-method refactor, not a module move). The deletion in Step 01 then becomes:

```python
# Before (after extraction):
_inject_bootstrap_skill(parts, logger)

# After Step 01:
# (line removed)
```

That's a one-line deletion with zero risk of touching the status path. The extraction itself is a pure-refactor commit (behavior unchanged), easy to verify by diffing the hook output.

**Tradeoff**: Adds one commit before Step 01 proper. Worth it — the bootstrap block contains a glob fallback that makes the deletion diff hard to review cleanly without it.

---

### 3. Silent overlap: `format_compact_status` already returns ~150 tokens; plan targets ~75

**Recommendation: Tighten `format_compact_status` in place — do not parallel-build `build_compact_briefing`.**

The current `format_compact_status` output structure (lines 205–232):

```
## Requirements: 2/4 satisfied

**Run `/plan-review`** → `adr_reviewed`, `commit_plan`
**Fallback**: `req satisfy adr_reviewed commit_plan --session abc123`
```

For a typical 4-requirement config this is ~10 lines / ~100 tokens — already close to the plan's 75-token target. The gap comes from:
1. The markdown heading line (`## Requirements: N/M satisfied`) — 6 tokens
2. The fallback line — ~15 tokens
3. The blank lines between groups

The plan's proposed `build_compact_briefing` 4-line format is effectively this function minus the fallback line, with a pipe-separated first line instead of a heading. That's not a new function; it's a 10-line edit to the existing one.

**Concrete overlap to watch**: The plan spec says "Line 1: `Phase: <derived> | <N> unsatisfied | Next: /req <phase>`". The current function has no phase-derivation logic — that's genuinely new behavior. But the *rendering* logic (group by action, format names) is identical to what `_group_by_resolve_action` + `format_compact_status` already do.

**Action**: When implementing Step 01, modify `format_compact_status` directly rather than adding a parallel `build_compact_briefing`. If phase-derivation logic is needed, add it as a helper `_derive_phase(req_data)` and call it from the existing function. Keeps the call-site in `format_adaptive_status` unchanged.

---

### Summary

| Question | Recommendation | Risk if ignored |
|----------|----------------|-----------------|
| Extract formatting module first? | No — premature, no shared consumer | Extra churn, wider diff |
| Extract bootstrap block before deleting? | Yes — inline helper only | 40-line removal touches adjacent status code |
| Parallel-build `build_compact_briefing`? | No — tighten existing function | Duplicate logic, two code paths to maintain |

---

## Commit Strategy

Four atomic commits in TDD sequence. Each is independently revertible.

> **Note on preparatory analysis**: The refactor-advisor (above) recommends extracting the bootstrap block into `_inject_bootstrap_skill(parts, logger)` before deleting it. That extraction is folded into Commit 1 (test) + Commit 2 (refactor), so Commit 3's deletion is a clean one-line removal.

---

### Commit 1 — `test: add failing tests for briefing_format config key and no-bootstrap output`

**Files changed**: `hooks/test_requirements.py`

**What it does**:
- Extend `test_session_start_format_tiers` with assertions that `format_adaptive_status` respects `briefing_format: compact` config key, and that `startup` source with `briefing_format: compact` returns compact-format output (not the rich `"Session Briefing"` header).
- Add new test `test_session_start_no_bootstrap_injection` that runs the hook subprocess with `inject_context: True` and asserts the output does **not** contain `"superpowers"` or the literal string `"using-requirements-framework"` skill body — RED until Commit 3.

**Test verifies**: Extended `test_session_start_format_tiers` (RED on `briefing_format` key until Commit 2), `test_session_start_no_bootstrap_injection` (RED until Commit 3).

---

### Commit 2 — `refactor(hook): extract bootstrap injection into _inject_bootstrap_skill helper`

**Files changed**: `hooks/handle-session-start.py`

**What it does**:
- Move lines 753–793 (the `bootstrap_text` construction, skill-path glob, frontmatter stripping, and `parts.append(...)`) into a new `_inject_bootstrap_skill(parts, logger)` helper function in the same file.
- Replace the original block in `main()` with a single call: `_inject_bootstrap_skill(parts, logger)`.
- **Behavior unchanged** — all existing tests stay green.

**Test verifies**: `test_session_start_bootstrap_injection` (existing, stays GREEN — bootstrap still fires), `test_session_start_format_tiers` (stays GREEN — no format change).

---

### Commit 3 — `feat(hook): default briefing_format to compact; remove bootstrap skill injection`

**Files changed**: `hooks/handle-session-start.py`, `hooks/test_requirements.py`

**What it does**:
1. In `format_adaptive_status`, read `hooks.session_start.briefing_format` first; fall back to `hooks.session_start.injection_mode` for backward compatibility; default to `compact` (was `auto`/rich for `startup`).
2. Delete the single `_inject_bootstrap_skill(parts, logger)` call from `main()` and remove the helper function — the skill is already surfaced by Claude Code's system-reminder catalog.
3. In the test file: rename `test_session_start_bootstrap_injection` to `test_session_start_no_bootstrap_injection` and flip its assertion — the hook must **not** output bootstrap text when `inject_context: True`. Update the `briefing_format` assertions to GREEN.

**Test verifies**: `test_session_start_no_bootstrap_injection` (GREEN — no bootstrap), extended `test_session_start_format_tiers` (GREEN — `briefing_format: compact` works), `test_session_start_bootstrap_injection` (removed / replaced).

---

### Commit 4 — `chore(plugin): bump plugin version for session-briefing simplification`

**Files changed**: `plugins/requirements-framework/.claude-plugin/plugin.json`

**What it does**:
- Increment patch version to record that session startup token cost is reduced (no more bootstrap injection; compact default).

**Test verifies**: No dedicated test. Full suite passes after `./sync.sh deploy`. `./update-plugin-versions.sh --verify` confirms hashes are current.

---

### Sequencing summary

| # | Commit | Suite state after |
|---|--------|-------------------|
| 1 | Add failing tests | RED (2 new failing) |
| 2 | Extract bootstrap helper | RED (bootstrap still fires — no-bootstrap test still fails) |
| 3 | Default compact + remove bootstrap | GREEN (all pass) |
| 4 | Bump plugin version | GREEN |

Each commit builds on the prior one. Commits 2 and 3 are independently revertible: reverting Commit 3 restores the bootstrap call and the `auto` default without touching Commit 2's extraction; reverting Commit 2 un-extracts the helper but leaves Commit 3 in an inconsistent state — so revert order should be 3 then 2 if rolling back both.
