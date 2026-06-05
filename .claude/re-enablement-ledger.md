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
| R3 | Plugin review commands (/deep-review, /arch-review) | 🟡 ready to dogfood | plugin self-contained + loadable; needs a live --plugin-dir session |
| R4 | /v3-review LIVE (budget rung) | ⬜ | — |
| R5 | Observability / Langfuse | ⬜ | — |
| R6 | Eval harness + golden set | ⬜ | — |
| R7 | Retrieval / memory / Qdrant | ⬜ | — |
| aux | Obsidian, session-learning | ⬜ | — |

### R1 enhancement — evidence-gated commit_plan (`step-2-evidence-gated-commit-plan`, plugin 4.9.0)

From the cross-session investigation: `commit_plan` was a **checkbox** (boolean flag; auto-satisfy
fired even on a BLOCKED review; `req satisfy` = labelled bypass). Cross-session blocking was already
fine (session-scoped + `single_session_per_project` disabled). Built per user decisions
(time-based `replan_ttl`; require `## Verdict APPROVED`):

- **Gate** (`plan_evidence.py` + `blocking_strategy.py`): a satisfied flag now ALSO requires a recent
  `.claude/plans/*.md` with `## Commit Plan` + a `## Verdict` section containing `APPROVED`. Fail-open;
  back-compat no-op when no `evidence` config.
- **Producer** (`/arch-review`): persists `.claude/plans/<date>-<slug>.md` with those markers, only
  when actually APPROVED (BLOCKED/ADR_REQUIRED leave the gate closed).
- **`replan_ttl`** so a branch plan expires; `config.get_ttl()` + auto-satisfy passes it.

**Controlled dogfood (4/4):** (1) unset+no-plan → BLOCK; (2) **flag SET but no plan doc → STILL BLOCK**
(cli_bypass / verdict-blind auto-satisfy neutralised); (3) flag + `APPROVED` artifact → ALLOW;
(4) verdict flipped to BLOCKED → BLOCK again. 1343/1343 hermetic; bundle + render fresh.

**Not yet armed live** (the live sandbox still runs the simpler R1 `scope: session` checkbox). Arming
evidence-gating live needs a real `.claude/plans/*.md` (the evidence) authored first to avoid a
lockout, then flipping `.claude/requirements.local.yaml` to `scope: branch` + the `evidence`/`replan_ttl`
block.

---

## R3 — Plugin review commands — 🟡 READY TO DOGFOOD (2026-06-05)

Unblocked by the self-contained plugin (task #3). Verified offline: a **bundled** hook
(`plugins/requirements-framework/hooks/check-requirements.py`) runs standalone and imports its
**bundled** `lib/` (returned a correct DENY) — build-copy genuinely works. Plugin manifest sane
(4.9.0, 25 agents, `./commands/` + `./skills/`); `arch-review`/`deep-review`/`v3-review` commands
present; `hooks.json` resolves all 16 commands to existing `${CLAUDE_PLUGIN_ROOT}/hooks/*.py`.

**Sandbox reconfigured for R3:** the `hooks` block was removed from `.claude/settings.local.json` so
the plugin's `hooks.json` is the SOLE hook source in a `--plugin-dir` session (no double-fire).
`.claude/requirements.local.yaml` (requirement config) stays.

**Graduation gate (needs a live session — user action):** launch
`claude --plugin-dir /Users/harm/Tools/claude-requirements-framework/plugins/requirements-framework`
from this repo, then confirm: (1) the SessionStart briefing appears (plugin hooks fired), (2) `/arch-review`
and `/deep-review` are available, (3) an Edit is gated by `commit_plan` (bundled hook fired via
`${CLAUDE_PLUGIN_ROOT}`), (4) `/arch-review` (or `req satisfy`) clears it, (5) no `exit 127` / missing-
script hook errors. Report keep/drop/fix.

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
