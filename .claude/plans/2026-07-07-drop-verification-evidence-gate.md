# Drop `verification_evidence` Gate — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use requirements-framework:executing-plans to implement this plan task-by-task.

**Goal:** Remove the auto-satisfied `verification_evidence` Stop-hook gate from the requirements-framework product and both active local configs, keeping the `/verification-before-completion` skill as guidance-only.

**Architecture:** Delete one shipped requirement across config template, message file, phase-ladder defaults (`config.py` + the byte-for-byte-synced `derive_phase.py`), and the skill→gate auto-satisfy map. The `implement` workflow phase becomes gateless (`gate: None`) — transparent to phase derivation (derive_phase.py:172-174), so the `req` conductor derives plan-validate → review directly. Update ~20 test sites, rebuild the plugin bundle, bump the plugin version.

**Tech Stack:** Python stdlib + PyYAML; custom `TestRunner` in `hooks/test_requirements.py` (not unittest); `stg` for atomic patches; `uv run` for all Python; `scripts/build_plugin_hooks.py` + `scripts/render_prompts.py` for the bundle.

**Design doc:** `.claude/plans/2026-07-07-drop-verification-evidence-gate-design.md`

**Baseline before starting:** `uv run python hooks/test_requirements.py` → 1537/1544 (7 known pre-existing failures ignored). `uv run ruff check .` → clean.

---

## Patch 1: Local configs (this repo)

**Files:**
- Modify: `.claude/requirements.local.yaml` (delete `verification_evidence:` block ~:35; `implement` phase `gate:` → `null` ~:72)

**Step 1:** Delete the `verification_evidence:` requirement block.
**Step 2:** In the `workflow.phases` list, change the `implement` entry `gate: verification_evidence` → `gate: null`.
**Step 3:** Sanity: `uv run python -c "import yaml; yaml.safe_load(open('.claude/requirements.local.yaml'))"` → no error.
**Step 4:** Commit.
```bash
stg new local-config -m "chore(config): drop verification_evidence from this repo's local config"
stg refresh -- .claude/requirements.local.yaml
```
> Note: `~/Work/solarmonkey-app/.claude/requirements.local.yaml` gets the identical two edits **out-of-band** (gitignored, different repo) — NOT part of any patch here. Apply it after the branch lands, or now via a direct edit; it is not version-controlled from this repo.

---

## Patch 2: Product source + skill doc

**Files:**
- Modify: `examples/global-requirements.yaml` (delete `verification_evidence:` block ~:407-428; delete/repair the stale `verification_evidence` comment ~:309)
- Delete: `messages/verification_evidence.yaml`
- Modify: `hooks/lib/derive_phase.py:44` — remove the `("implement", "verification_evidence")` tuple from `PHASE_GATES`
- Modify: `hooks/lib/config.py:943` — `implement` phase `"gate": "verification_evidence"` → `"gate": None`
- Modify: `hooks/auto-satisfy-skills.py:58` — delete the `'requirements-framework:verification-before-completion': 'verification_evidence',` line
- Modify: `plugins/requirements-framework/skills/verification-before-completion/SKILL.md.j2` — rewrite "Requirements Integration" section: the skill is guidance-only and no longer auto-satisfies any requirement (remove the `handle-stop.py` / gate claim).

**Step 1:** Make all six edits above. For `derive_phase.py`, delete the whole `("implement", "verification_evidence"),` line (implement is now gateless → omitted from PHASE_GATES, exactly as `refactor`/`ship` already are). For `config.py`, keep the `implement` dict but set its gate to `None`.
**Step 2:** Verify the two ladders still agree on their gated subset:
```bash
uv run python -c "
import sys; sys.path.insert(0,'hooks/lib')
from derive_phase import PHASE_GATES
from config import RequirementsConfig
wd=[(p['name'],p['gate']) for p in RequirementsConfig.WORKFLOW_DEFAULTS['phases'] if p['gate']]
assert wd==PHASE_GATES, (wd, PHASE_GATES)
print('gated subset in sync:', PHASE_GATES)
"
```
Expected: prints the 4 remaining gated phases (design, plan-write, plan-validate, review); no AssertionError.
**Step 3:** Edit the `.md.j2` only — the rendered `.md` is regenerated in Patch 4, do NOT hand-edit it.
**Step 4:** Commit.
```bash
stg new product-source -m "feat(req): remove verification_evidence gate from product

Drop the shipped verification_evidence requirement: template block, message
file, phase-ladder default (config.py + synced derive_phase.py), and the
skill->gate auto-satisfy map. The implement phase becomes gateless (advisory);
derivation goes plan-validate -> review. The verification-before-completion
skill stays as guidance-only."
stg refresh -- examples/global-requirements.yaml messages/verification_evidence.yaml hooks/lib/derive_phase.py hooks/lib/config.py hooks/auto-satisfy-skills.py plugins/requirements-framework/skills/verification-before-completion/SKILL.md.j2
```

---

## Patch 3: Tests

**Files:**
- Modify: `hooks/test_requirements.py` (~20 sites)

Two categories (see design doc). Work them by running the suite and fixing what breaks.

**Step 1 (RED):** Run the suite to see what the Patch-2 source changes broke:
```bash
uv run python hooks/test_requirements.py 2>&1 | grep -iE "verification_evidence|FAIL" | head -40
```
Expected: failures at the assertion sites (mapping, template attrs, message-file list, default-ladder derivation).

**Step 2 — delete assertions ABOUT the gate:**
- `:10214-10215` — "verification-before-completion maps to verification_evidence" → delete the assertion.
- `:10287-10297` — the `verification_evidence` scope/`stop_only`/triggers-on-Edit block → delete.
- `:10321` — remove `'verification_evidence.yaml'` from the expected-message-files list.
- `:10270` — remove `'verification_evidence'` from the `new_reqs` list (keep the others).

**Step 3 — repoint derive_phase FIXTURES that USE the name (`:12256-12667`):**
These construct phase ladders/fixtures with `verification_evidence` as an arbitrary `implement` gate. For each, either (a) if the fixture asserts the **default** ladder's behavior, update the expectation to the new gateless-implement reality (implement is skipped → plan-validate derives to review); or (b) if the fixture is testing phase-derivation mechanics with an arbitrary gate name, rename that gate to a neutral placeholder (e.g. `impl_gate`) so the test still exercises the logic without referencing the deleted product gate.
- Pay attention to `:12358` ("build" fixture), `:12462` (default implement fixture), and the phase-sequence assertions at `:12431-12433`, `:12535`, `:12667` — these encode expected derived phases and must reflect that `implement` is no longer a checkpoint.

**Step 4 (GREEN):**
```bash
uv run python hooks/test_requirements.py
```
Expected: back to baseline 1537/1544 (7 known failures). `uv run ruff check .` clean.
**Step 5:** Commit.
```bash
stg new tests -m "test: drop verification_evidence assertions, repoint phase fixtures"
stg refresh -- hooks/test_requirements.py
```

---

## Patch 4: Bundle rebuild + version bump

**Files:**
- Regenerate: 10 `plugins/requirements-framework/…` copies
- Modify: `plugins/requirements-framework/.claude-plugin/plugin.json` (minor bump)

**Step 1:** Bump `plugin.json` version (minor — removes a shipped default).
**Step 2:** Rebuild the bundle:
```bash
uv run python scripts/build_plugin_hooks.py
uv run python scripts/render_prompts.py
```
**Step 3:** Confirm the gate is gone from the bundle and no stray refs remain:
```bash
grep -rl "verification_evidence" plugins/requirements-framework/ || echo "clean: no verification_evidence in bundle"
```
Expected: `clean` (the only remaining product refs should be none; the skill's own file no longer claims the gate).
**Step 4:** Re-run tests + ruff (bundle copies are import-tested):
```bash
uv run python hooks/test_requirements.py && uv run ruff check .
```
**Step 5:** Commit.
```bash
stg new bundle-version -m "chore(plugin): rebuild bundle without verification_evidence + bump version"
stg refresh -- plugins/ 
```

---

## Patch 5: git_hash churn (separate chore)

**Files:**
- Modify: plugin component frontmatter `git_hash` fields

**Step 1:**
```bash
./update-plugin-versions.sh
```
**Step 2:** Commit the churn on its own so it never mixes with logic patches:
```bash
stg new git-hash-churn -m "chore(plugin): refresh git_hash fields"
stg refresh
```

---

## Finalize

**Step 1:** Deploy + verify sync:
```bash
./sync.sh deploy
./sync.sh status
```
Expected: repo and `~/.claude/hooks` in sync.
**Step 2:** Full series review:
```bash
stg series
```
Expected: `local-config`, `product-source`, `tests`, `bundle-version`, `git-hash-churn` (+ the earlier `design-doc`).
**Step 3:** Review before finishing — run `/pre-commit` (or `/deep-review` for the cross-validated pass). Then use `requirements-framework:finishing-a-development-branch` to decide integration.

---

## Commit Plan (arch-review refined — AUTHORITATIVE)

Supersedes the 5-patch sketch above. Two refinements from review: (a) **merge
source+tests into one green patch** so no committed patch is left RED; (b) add a
**CHANGELOG + upgrade note** for the adopter soft-lockout, and **two positive
tests**.

**Patch 1 — `local-config`** (this repo only; solarmonkey-app edited out-of-band)
- Files: `.claude/requirements.local.yaml`
- Delete `verification_evidence:` block; `implement` phase `gate:` → `null`.
- Test: `uv run python -c "import yaml,io; yaml.safe_load(open('.claude/requirements.local.yaml'))"`.

**Patch 2 — `remove-gate`** (source + tests + docs, kept GREEN)
- Files: `examples/global-requirements.yaml` (delete block + stale comment),
  `messages/verification_evidence.yaml` (delete), `hooks/lib/derive_phase.py`
  (drop the `("implement","verification_evidence")` tuple),
  `hooks/lib/config.py` (implement `"gate": None`),
  `hooks/auto-satisfy-skills.py` (delete `:58` mapping line),
  `plugins/requirements-framework/skills/verification-before-completion/SKILL.md.j2`
  (Requirements Integration → guidance-only),
  `docs/STATUSLINE.md` (update the phase table: `implement` is gateless/advisory;
  ladder = design → plan-write → plan-validate → review),
  `CHANGELOG.md` (add `### Removed` entry + **upgrade note**: "projects that still
  enable `verification_evidence` must remove it from their config — the skill no
  longer auto-satisfies it; a still-enabled gate becomes satisfiable only via
  `req satisfy`/`req-pause`" + the ADR-015 amendment rationale),
  `hooks/test_requirements.py` (delete gate-assertions; repoint/adjust fixtures;
  **ADD** two positive tests).
- **arch-review (adr-guardian) additions:**
  - `docs/adr/ADR-015-breaking-removal-policy.md` — append a short **Amendment
    (2026-07-07)**: requirement-ladder defaults / template requirements are
    internal, session-scoped artifacts (no runtime manifest coupling; user-copied
    templates) and are **exempt from Policy 1's major-boundary cadence** — they may
    be removed in a minor with a CHANGELOG rationale. This is the recorded
    decision authorizing this removal.
  - `.claude/requirements.yaml` (~:217-219) — fix the now-false comment above
    `pre_push_verification` that says it "shares the /verification-before-completion
    satisfier with the stop-only verification_evidence req" (verification_evidence
    no longer exists; `pre_push_verification` auto-satisfies via its own
    `satisfied_by_skill` config, unaffected).
  - Three hand-authored plugin docs that the bundle scripts do NOT regenerate —
    edit directly (or their `.md.j2` where one exists):
    `skills/workflow-index/SKILL.md.j2`,
    `skills/requirements-framework-usage/SKILL.md.j2`,
    `skills/using-requirements-framework/references/skill-catalog.md` (no `.j2` —
    hand-edit). Confirm with `grep -rl verification_evidence plugins/` after Patch 3.
- **New tests to ADD:**
  1. *Gateless-implement transparency:* build a state where `solid_reviewed` is
     satisfied and `pre_pr_review` is not; assert `derive_phase(...)` returns
     `"review"` (implement is skipped, not returned).
  2. *Ladder sync invariant:* assert
     `[(p['name'],p['gate']) for p in RequirementsConfig.WORKFLOW_DEFAULTS['phases'] if p['gate']] == derive_phase.PHASE_GATES`.
- Test: `uv run python hooks/test_requirements.py` GREEN (baseline 1537/1544) +
  `uv run ruff check .` clean. Verify `grep -rl verification_evidence hooks/ examples/ messages/ docs/` returns nothing.

**Patch 3 — `bundle-version`** (bundle rebuild + version bump, ride together)
- Files: 10 `plugins/requirements-framework/…` regenerated copies +
  `plugins/requirements-framework/.claude-plugin/plugin.json` (minor bump).
- Run: `uv run python scripts/build_plugin_hooks.py && uv run python scripts/render_prompts.py`.
- Test: `grep -rl verification_evidence plugins/requirements-framework/` → empty;
  `uv run python hooks/test_requirements.py` GREEN; `uv run ruff check .` clean.

**Patch 4 — `git-hash-churn`** (isolated chore)
- Run `./update-plugin-versions.sh`; `stg refresh`.

**Finalize:** `./sync.sh deploy` + `./sync.sh status`; review via `/pre-commit`;
`requirements-framework:finishing-a-development-branch`.

## Verdict

APPROVED

Review provenance (honest): the arch-review agent team was knocked out by API
529 overload; four dimensions (backward-compat, TDD, SOLID, commit-strategy)
were covered by the lead's solo pass. The **adr-guardian agent recovered on retry
and delivered a real review** — it returned `ADR_REQUIRED` on an ADR-015
(Breaking-Removal Policy) cadence gap: an immediate removal in a minor bump for a
shipped-template artifact. Resolved by user decision (2026-07-07): **amend ADR-015**
to exempt requirement-ladder defaults from Policy 1's major-boundary cadence, plus
a CHANGELOG `### Removed` rationale — both now required deliverables in Patch 2.
adr-guardian's mechanical doc-drift findings (`.claude/requirements.yaml` comment,
three hand-authored skill docs, `docs/STATUSLINE.md`) are folded into Patch 2.
ADR-020 ≥1-enabled threshold confirmed safe (7 reqs remain). With those in, the
removal is APPROVED.

Reviewed: chore/drop-verification-evidence-gate @ 2026-07-07
(lead solo + adr-guardian agent; team degraded by API outage)

## Risks / watch-items

- **Conductor phase gap:** after this change, `/req` derives plan-validate → review with no `implement` checkpoint. Intended (design-accepted), but confirm the statusline/`req status` output reads sensibly with a gateless implement. arch-review should bless this.
- **PHASE_GATES ↔ WORKFLOW_DEFAULTS sync:** the byte-for-byte invariant is now "gated subset matches"; the Step-2 assertion in Patch 2 guards it. Keep both edits in the same patch.
- **CI auto-publish pushback:** first push to origin/master triggers the auto-bump workflow → second push is non-ff. Fetch+rebase if pushing. CI also runs `ruff check .` which the local TestRunner does not.
- **solarmonkey-app** local edit is out-of-band; don't forget it (it's the config that actually nagged the user).
