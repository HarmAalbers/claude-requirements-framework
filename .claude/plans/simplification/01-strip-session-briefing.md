# Step 01 — Strip session briefing to <300 tokens

## Goal

Replace the current ~1,500-token requirement table dump in the SessionStart hook with a 3-line briefing. Stop inlining the `using-requirements-framework` skill body twice.

## Why first

Largest single token win. Pure modification of files we own. Reversible in one revert.

## Files touched (as shipped)

Production code:
- `hooks/handle-session-start.py` — removed bootstrap injection block, removed `injection_mode` shim, removed `auto` mode, removed `format_full_status` deprecated wrapper, simplified `format_adaptive_status` to dispatch on `briefing_format` only
- `hooks/lib/config.py` — clarified `briefing_format` default comment in `HOOK_DEFAULTS`

Tests:
- `hooks/test_requirements.py` — added `test_session_start_briefing_format_config`, added `test_session_start_bootstrap_removed`, dropped legacy-shim and auto-mode test cases

Example configs:
- `.claude/requirements.yaml` — `injection_mode: auto` → `briefing_format: compact`
- `examples/global-requirements.yaml` — same migration + comment block updated
- `hooks/lib/feature_catalog.py` — example YAML uses `briefing_format: compact`

Plugin:
- `plugins/requirements-framework/.claude-plugin/plugin.json` — bumped to 3.1.2

> **Not touched**: `hooks/lib/messages.py` and `messages/_status.yaml`. The original plan speculated these might need updates; the implementation went a different route by tightening `format_compact_status` inline.

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

## Example (as shipped)

**Before** — `format_rich_status` on startup, plus inlined skill body (~1,500+ tokens combined):
```
## Requirements Framework: Session Briefing
**Project**: ...
### Quick Start
🚀 Run /arch-review → satisfies commit_plan, adr_reviewed, ...
### Requirement Definitions
**commit_plan** (blocking, session-scoped) ...
[40+ lines of definitions, scope reference, workflow guide]

You have superpowers.
**Below is the full content of your 'using-requirements-framework' skill — ...**
[~80 lines of skill body]
```

**After** — `format_compact_status` (243 bytes for a 3-requirement fixture):
```
## Requirements: 0/3 satisfied
**Run `/plan-review`** → `commit_plan`
**Run `/arch-review`** → `adr_reviewed`
**req satisfy pre_pr_review** → `pre_pr_review`
**Fallback**: `req satisfy commit_plan adr_reviewed pre_pr_review --session <id>`
```

> The `Phase: ... | Next: /cmd` pipe-separated header was speculated in the original plan but **deferred to Step 03** (`Phase-aware statusline`), which will introduce a shared `hooks/lib/derive_phase.py`. Step 01 keeps the existing `## Requirements: N/M satisfied` header to avoid duplicating phase logic ahead of its proper home.

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

## Preparatory Refactoring (advisory analysis — what was followed)

The refactor-advisor agent produced three recommendations during arch-review. Outcome of each:

| # | Recommendation | Status |
|---|----------------|--------|
| 1 | Do **not** extract formatting to `hooks/lib/briefing_formats.py` before Step 01 | ✅ followed — extraction left for a future step |
| 2 | Extract bootstrap block into `_inject_bootstrap_skill` helper before deleting | ❌ skipped — agents deleted the block directly (commit fcc2d1c); risk paid off, diff was clean |
| 3 | Tighten `format_compact_status` in place rather than adding `build_compact_briefing` | ✅ followed — no parallel function was added |

Full analysis kept below as historical record.

---

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

## Commit Strategy (as shipped)

The arch-review's commit-planner agent designed a 4-commit TDD sequence (kept below as historical record). What actually shipped was 7 commits — the first 4 made directly by team agents during analysis, the last 3 by the team lead following user direction.

### Actual commit log

| # | SHA | Type | Description | Author |
|---|-----|------|-------------|--------|
| 1 | `6921840` | test | add failing tests for briefing_format config and bootstrap removal | agent (during arch-review) |
| 2 | `1a73050` | feat | wire briefing_format config key, default to compact | agent |
| 3 | `fcc2d1c` | feat | remove bootstrap skill body injection (directly, no extract step) | agent |
| 4 | `d2e16ff` | chore | bump version to 3.1.1 | agent |
| 5 | `8400584` | refactor | remove injection_mode shim, auto value, format_full_status | lead (per user "no backwards compat") |
| 6 | `6cfbde9` | docs | realign Step 01 plan with shipped implementation | lead |
| 7 | `d76907a` | chore | bump version to 3.1.2 for cleanup | lead |

### Sequencing summary

| # | Commit | Suite state after |
|---|--------|-------------------|
| 1 | Failing tests added | RED (new tests fail — code still uses old key/has bootstrap) |
| 2 | briefing_format wired | RED (bootstrap still fires) |
| 3 | Bootstrap removed | GREEN (1269/1269) |
| 4 | Version 3.1.1 | GREEN |
| 5 | Legacy surface removed | GREEN (1267/1267 — 2 obsolete tests dropped) |
| 6 | Plan realigned | GREEN |
| 7 | Version 3.1.2 | GREEN |

### Divergences from the agent's plan

1. **Extract-then-delete was skipped.** The commit-planner specced Commit 2 as "extract `_inject_bootstrap_skill` helper" before Commit 3's deletion, to keep the deletion diff small. The agent that implemented went straight to deletion. The resulting diff was clean enough that no separate extraction commit was needed.
2. **`injection_mode` was kept then removed.** The original spec preserved it as a deprecated alias. After landing, the user directed removal — commit `8400584` deleted the shim entirely. See `[[feedback-no-backwards-compat]]` in memory.
3. **Two extra commits at the end** for the cleanup (commit 5), plan realignment (commit 6), and version re-bump (commit 7).

---

### Original 4-commit plan (kept for historical record)

#### Commit 1 — `test: add failing tests for briefing_format config key and no-bootstrap output`
- Extend `test_session_start_format_tiers` with `briefing_format: compact` assertions.
- Add `test_session_start_no_bootstrap_injection` — RED until Commit 3.

#### Commit 2 — `refactor(hook): extract bootstrap injection into _inject_bootstrap_skill helper`
- Move lines 753–793 into a private helper. Behavior unchanged.

#### Commit 3 — `feat(hook): default briefing_format to compact; remove bootstrap skill injection`
- Wire the new config key with `injection_mode` fallback for compatibility.
- Delete the bootstrap helper call.

#### Commit 4 — `chore(plugin): bump plugin version for session-briefing simplification`
- Patch bump.
