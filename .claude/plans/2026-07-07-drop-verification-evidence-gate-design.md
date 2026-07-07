# Design: Remove the `verification_evidence` gate

**Date:** 2026-07-07
**Branch:** `chore/drop-verification-evidence-gate`
**Status:** Approved (design ratified from live design conversation)

## Decision

Remove the auto-satisfied Stop-hook *gate* `verification_evidence` from the
requirements-framework product **and** from both active local configs.

**Keep** the `/verification-before-completion` *skill* — it remains a usable
discipline skill. It simply no longer auto-satisfies a requirement. Its
"Requirements Integration" section is rewritten to reflect that.

## Rationale (settled with user)

The gate's only unique value is **claim-time honesty** — blocking completion
claims (e.g. "the suite is green") made without fresh verification evidence,
including trusting a subagent's "it's green" report.

But **"Stop" is the only proxy Claude Code gives for a completion claim**, so a
`session`-scoped, `stop_only` gate re-fires at **every turn-end**. During
subagent-heavy sessions the agent ends its turn to wait on background work many
times, and each turn-end re-trips the gate — nagging that cannot be distinguished
from a genuine "I'm done" stop.

Options weighed and rejected:
- **Evidence-driven** (auto-satisfy on a real test run, re-arm on edit) — keeps
  the value, kills the nag, but moderate build.
- **Move to `git commit`** — cheap, but changes what it guards (commits, not
  chat claims) and loses the subagent-trust case.
- **Keep as-is + `/req-pause`** — full coverage, manual cost.

User chose **drop entirely at full product scope**: accept that claim discipline
is owned by the operator; rely on `pre_commit_review` / `pre_pr_review` /
`codex_reviewer` (which already fire on commit / `gh pr create`) for quality gating.

## Change set

| Layer | File | Edit |
|-------|------|------|
| Local | `.claude/requirements.local.yaml` (this repo) | delete `verification_evidence:` block; `implement` phase gate → `null` |
| Local | `~/Work/solarmonkey-app/.claude/requirements.local.yaml` | same two edits (separate, not committed to this repo) |
| Product | `examples/global-requirements.yaml` | delete block (~:407) + stale comment (~:309) |
| Product | `messages/verification_evidence.yaml` | delete file |
| Product | `hooks/lib/derive_phase.py` | drop `("implement", "verification_evidence")` → implement phase becomes gateless |
| Product | `hooks/lib/config.py` | drop gate from default phase ladder |
| Product | `hooks/auto-satisfy-skills.py` | drop `verification-before-completion → verification_evidence` mapping |
| Product | `skills/verification-before-completion/SKILL.md(.j2)` | rewrite "Requirements Integration" section (skill no longer satisfies a gate) |
| Tests | `hooks/test_requirements.py` (~20 sites) | delete gate-specific assertions; repoint fixture ladders to a neutral gate name |
| Bundle | 10 `plugins/requirements-framework/…` copies | regenerate via build scripts |
| Version | `plugins/requirements-framework/.claude-plugin/plugin.json` | minor bump (removes a shipped default) |

## Test strategy (TDD)

The ~20 test sites split in two:
- **(a) Assertions *about* the gate** — mapping exists (:10214), template has
  `session`/`stop_only`/triggers-on-Edit (:10287–10297), message file exists
  (:10321). These are **deleted** (RED-by-removal is the intent).
- **(b) `derive_phase` fixtures that merely *use* `"verification_evidence"`** as an
  arbitrary `implement`-phase gate name (:12256–12667). Repoint to a neutral
  placeholder so they still exercise phase-derivation logic.

GREEN = `uv run python hooks/test_requirements.py` back to baseline (1537/1544;
7 known pre-existing failures ignored). Plus `uv run ruff check .`.

## Atomic stg patches

1. Local configs (this repo) — delete block + repoint phase gate.
2. Product source + skill doc — the source removals above.
3. Test updates — delete (a), repoint (b).
4. Bundle rebuild + `plugin.json` version bump.
5. `git_hash` churn from `update-plugin-versions.sh` — separate chore patch.

Deploy via `./sync.sh deploy` + `./sync.sh status` after. solarmonkey-app local
edit is applied out-of-band (gitignored, different repo).

## Risk

Low. No ADR references `verification_evidence`. A gateless `implement` phase in
`derive_phase` just means that phase never blocks (advisory) — the intended
outcome. Main effort is mechanical test churn.
