# Re-enablement Ledger

Tracks the incremental, project-scoped re-enablement of the requirements
framework after the 2026-06-05 clean-slate uninstall. One rung at a time; each
rung has a graduation gate (criteria + measurement + keep/drop/fix verdict)
before the next is enabled. See the phased plan in the session that created this.

Legend: ✅ graduated · 🟡 in progress · ⬜ not started · ❌ dropped

| Rung | Capability | Status | Verdict |
|------|------------|--------|---------|
| R1 | Core gating (one requirement) | ✅ graduated | Works end-to-end; no false positives; state integrity holds |
| R2 | Status injection + statusline | ⬜ | — |
| R3 | Plugin review commands (/deep-review, /arch-review) | ⬜ | — |
| R4 | /v3-review LIVE (budget rung) | ⬜ | — |
| R5 | Observability / Langfuse | ⬜ | — |
| R6 | Eval harness + golden set | ⬜ | — |
| R7 | Retrieval / memory / Qdrant | ⬜ | — |
| aux | Obsidian, session-learning | ⬜ | — |

---

## R1 — Core gating — ✅ GRADUATED (2026-06-05)

**Prerequisites (landed first):** state-write concurrency fix (`step-1a`), guard-aware
status (`step-1c`). Both required before trusting the gate's state mechanics.

**Method:** controlled end-to-end demonstration — the repo's actual hook scripts
(`check-requirements.py`, `requirements-cli.py`) run against an isolated temp git
repo (hermetic `HOME`), with a minimal config enabling only `commit_plan`
(blocking, session, triggers on Edit/Write/MultiEdit). No live session armed; no
state written to this repo.

**Graduation gate:** blocks correctly · zero false positives · no state corruption.

**Evidence:**
- Edit while unsatisfied → blocked with `hookSpecificOutput.permissionDecision="deny"`
  and a clear `permissionDecisionReason` (correct PreToolUse shape).
- `req satisfy commit_plan --session <id>` → satisfied.
- Edit again → allowed (empty output).
- `Read` (a non-trigger tool) while unsatisfied → allowed (no false positive).
- State file records `triggered:true` on the block, then `satisfied:true`; the
  atomic unique-temp write from `step-1a` works in the real hook path.
- No-corruption under parallel writers independently verified in `step-1a`
  (12 unit tests + 25/25 separate-process stress).

**Verdict:** Core gating is sound and trustworthy. Graduated.

**Live arming (2026-06-05):** per user choice, the full sandbox WITH the blocking
gate is armed live in this repo via gitignored local config:
- `.claude/settings.local.json` — registers the framework's hooks (full set)
  pointing at this repo's `hooks/*.py` (run via `python3 <abspath>`), so they
  load in the next Claude Code session in this repo.
- `.claude/requirements.local.yaml` — deep-merges onto the committed project
  config to keep ONLY `commit_plan` active (the other 9 requirements disabled),
  honouring the one-at-a-time principle. `branch_size_limit` in particular is
  disabled because this 157-patch branch would otherwise exceed its size
  threshold and block every edit.

To satisfy the gate in a session (the `req` alias is gone post-uninstall):
`python3 hooks/requirements-cli.py satisfy commit_plan --session <id>` (or run
`/arch-review` once the plugin is loaded at R3). To disarm: delete the `hooks`
block from `.claude/settings.local.json` (or `export CLAUDE_SKIP_REQUIREMENTS=1`).

**Live validation against this repo:**
- `settings.local.json` is valid JSON; 10 hook events registered.
- SessionStart briefing renders minimally: `## Requirements: 0/1 satisfied →
  Run /arch-review → commit_plan` (only one requirement — override confirmed).
- The gate is HOT: Claude Code hot-reloaded `settings.local.json` mid-session
  and blocked an Edit on `commit_plan`; `satisfy commit_plan --session <id>`
  cleared it and the Edit proceeded. End-to-end live loop confirmed on a real
  session, not just the temp-repo harness.

**R1-live finding (minor, open):** the inline PreToolUse blocking `message` for
`commit_plan` renders `**Execute**: /{auto_resolve_skill}` literally — the
`{auto_resolve_skill}` placeholder is NOT substituted in the blocking-message
path, even though the SessionStart `_status` template substitutes it correctly
to `/arch-review`. Cosmetic (message still understandable), not reinstall-blocking.
Candidate fix: add `auto_resolve_skill` to the blocking-message substitution map
(or render inline `message` fields through the same placeholder pass). Logged for
a future polish patch.

**Not yet exercised live:** the Stop-hook verification path (block-on-finish for a
triggered-but-unsatisfied session requirement) is covered by the existing unit
suite but was not re-demonstrated here; worth a live check during dogfooding.

**Open question for live dogfooding:** this repo's committed `.claude/requirements.yaml`
enables several blocking requirements at once (commit_plan, adr_reviewed,
tdd_planned, …), all triggering on Edit. A live sandbox should start from a
minimal local override (one requirement) rather than the full set, to honour the
"one at a time" principle.
