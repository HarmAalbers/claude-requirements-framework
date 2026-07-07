# Workflow Phase Re-cut — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use requirements-framework:executing-plans to implement this plan task-by-task.

**Goal:** Replace the flat 8-phase workflow with a 7-node **typed backbone** (spine/team/loop/conditional), consolidate ~11 gates → 7, remove double-ownership, as the new framework default with clean gate renames (no compat shims).

**Architecture:** The schema needs almost no new machinery — `config._normalize_phase` already preserves unknown keys (`type`/`loop`/`conditionals` pass through), and `derive_phase`/`resolve_current_phase` walk phases by gate (spine vs team is transparent). The bulk of the work is a **vocabulary migration**: rewrite `WORKFLOW_DEFAULTS` + `PHASE_GATES` + the auto-satisfy map + project/example configs + message files + docs, and update the tests that assert the old vocabulary. New surfacing (loop + conditionals in the conductor) is additive.

**Tech Stack:** Python stdlib + PyYAML; `config.py`, `derive_phase.py`, `auto-satisfy-skills.py`; `req`/`derive_phase --with-skill` conductor; TestRunner harness; `uv run`.

**Depends on:** stacked on `feat/nudge-only-workflow` (uses `resolve_current_phase`, `enforcement: nudge`).

**Test invocation:** `uv run python hooks/test_requirements.py` (baseline 7 known-pre-existing failures). Lint: `uv run ruff check .`. Rebuild bundle after touching hooks: `python3 scripts/build_plugin_hooks.py`. Bump `plugin.json` when plugin files change.

**Gate rename table (single source of truth for the sweep):**
| Old | New |
|-----|-----|
| `adr_reviewed`, `tdd_planned`, `solid_reviewed`, `commit_plan` | `plan_validated` (Validate team) |
| `pre_pr_review` | `pr_reviewed` |
| `pre_push_verification` | `verified` |
| `codex_reviewer` | *(removed — conditional, not a gate)* |
| `design_approved`, `plan_written`, `implementation_done`, `pre_commit_review` | *(unchanged)* |

New default phase names: `design, plan, validate, build, review, verify, ship` (was `design, plan-write, plan-validate, implement, commit-review, review, cleanup, ship`).

---

## Task 1: Rewrite `WORKFLOW_DEFAULTS` to the typed backbone

**Files:** Modify `hooks/lib/config.py` (`WORKFLOW_DEFAULTS`, ~line 918). Test: `hooks/test_requirements.py` (the `get_workflow_phases` / "no workflow → default …" block).

**Step 1 — update the failing tests** to the new vocabulary. Find the tests asserting default phase names/gates/skills (search `no workflow → default phase names`, `no workflow → default gates`, `no workflow → resolver skill names`, `defaults equal class constant`). Rewrite expected values to:
```
names:  [design, plan, validate, build, review, verify, ship]
gates:  [design_approved, plan_written, plan_validated, implementation_done, null(review→pr_reviewed... see below), ...]
```
(Exact expected lists per the design doc's schema block.)

**Step 2 — run, verify FAIL:** `uv run python hooks/test_requirements.py 2>&1 | grep -i "no workflow"` → FAIL.

**Step 3 — rewrite `WORKFLOW_DEFAULTS`** to the 7 phases with `type`/`loop`/`conditionals` per the design doc schema:
```python
WORKFLOW_DEFAULTS = {
  "default_phase": "design", "ship_phase": "ship",
  "phases": [
    {"name":"design","type":"spine","gate":"design_approved","skill":"requirements-framework:brainstorming","brainstorm_on_enter":True,"description":"design: explore the problem"},
    {"name":"plan","type":"spine","gate":"plan_written","skill":"requirements-framework:writing-plans","description":"plan: write the executable plan"},
    {"name":"validate","type":"team","gate":"plan_validated","skill":"requirements-framework:arch-review","conditionals":["requirements-framework:codex-review"],"description":"validate: architecture review team"},
    {"name":"build","type":"spine","gate":"implementation_done","skill":"requirements-framework:executing-plans","loop":{"gate":"pre_commit_review","skill":"requirements-framework:pre-commit","on":"commit"},"description":"build: implement the plan"},
    {"name":"review","type":"team","gate":"pr_reviewed","skill":"requirements-framework:deep-review","conditionals":["requirements-framework:codex-review"],"description":"review: code review team"},
    {"name":"verify","type":"spine","gate":"verified","skill":"requirements-framework:verification-before-completion","description":"verify: capture test/build evidence"},
    {"name":"ship","type":"spine","gate":None,"skill":"requirements-framework:finishing-a-development-branch","description":"ship: integrate the branch"},
  ],
}
```

**Step 4 — run, verify PASS.** Also `uv run ruff check hooks/lib/config.py`.

**Step 5 — commit:** `stg new recut-workflow-defaults -m "feat(workflow): typed 7-node backbone as default"` + `stg refresh`.

---

## Task 2: Sync `derive_phase.PHASE_GATES` fallback

**Files:** Modify `hooks/lib/derive_phase.py` (`PHASE_GATES`, `DEFAULT_PHASE`, `SHIP_PHASE`). Test: derive_phase tests (`PHASE_GATES == gated subset of WORKFLOW_DEFAULTS`, `zero-config: N sat → phase`, `with-skill: …`).

**Note:** `PHASE_GATES` is the fail-open fallback and MUST stay the gated subset of `WORKFLOW_DEFAULTS`. New gated spine order:
```python
PHASE_GATES = [("design","design_approved"),("plan","plan_written"),("validate","plan_validated"),("build","implementation_done"),("review","pr_reviewed"),("verify","verified")]
```
(ship is gateless → excluded, matching today's pattern.)

**Steps:** update the derive_phase tests' expected phase/gate/skill values (RED) → rewrite the constants (GREEN) → ruff → commit `recut-derive-phase-fallback`.

---

## Task 3: Consolidate the auto-satisfy map

**Files:** Modify `hooks/auto-satisfy-skills.py` `DEFAULT_SKILL_MAPPINGS`. Test: `test_process_skill_auto_satisfy_mappings`.

**New map:**
```python
'requirements-framework:brainstorming': 'design_approved',
'requirements-framework:writing-plans': 'plan_written',            # drop commit_plan
'requirements-framework:arch-review': 'plan_validated',            # was 4 gates
'requirements-framework:executing-plans': 'implementation_done',
'requirements-framework:pre-commit': 'pre_commit_review',
'requirements-framework:requesting-code-review': 'pre_commit_review',
'requirements-framework:deep-review': 'pr_reviewed',               # rename
'requirements-framework:v3-review': 'pr_reviewed',                 # rename
'requirements-framework:verification-before-completion': 'verified',  # NEW mapping (rename target)
# removed: codex-review (conditional now), test-driven-development->tdd_planned, systematic-debugging kept if desired
```
Update `test_process_skill_auto_satisfy_mappings` expectations (arch-review→'plan_validated' string not list; writing-plans→'plan_written'; deep-review→'pr_reviewed'; add verification→'verified'; remove codex mapping assertion; move codex-review into a "no mapping / conditional" list).

**Steps:** update test (RED) → rewrite map (GREEN) → rebuild bundle → ruff → commit `recut-auto-satisfy-map`.

---

## Task 4: Rewrite project + example configs

**Files:** `.claude/requirements.yaml` (project), `.claude/requirements.local.yaml` (gitignored — this project's workflow section), `examples/*.yaml` (global-requirements etc.).

**Actions (mechanical, no unit test — validated by config-load smoke):**
- Replace the requirement definitions for renamed/removed gates: define `plan_validated` (satisfied_by arch-review), `pr_reviewed` (deep-review), `verified` (verification-before-completion). Remove `adr_reviewed`/`tdd_planned`/`solid_reviewed`/`commit_plan`/`codex_reviewer`/`pre_pr_review`/`pre_push_verification` definitions.
- Rewrite each `workflow:` section to the 7-node typed backbone (type/loop/conditionals).
- Smoke: `uv run python -c "from config import RequirementsConfig; c=RequirementsConfig('.'); assert not c.get_validation_errors(), c.get_validation_errors(); print([p['name'] for p in c.get_workflow_phases()['phases']])"` → prints the 7 names, no errors.

**Commit:** `recut-project-example-configs`.

---

## Task 5: Message files for renamed/removed gates

**Files:** `plugins/requirements-framework/messages/*.yaml` (+ `messages/` cascade if present).

**Actions:** create `plan_validated.yaml`, `pr_reviewed.yaml`, `verified.yaml` (from `_templates.yaml`); delete `pre_pr_review.yaml`, `pre_push_verification.yaml`, `adr_reviewed.yaml`, `solid_reviewed.yaml`, `tdd_planned.yaml`, `codex_reviewer.yaml`, `commit_plan.yaml` if present. Run `req messages validate --fix` to generate any missing from templates. Rebuild bundle. **Commit:** `recut-messages`.

---

## Task 6: Conductor surfaces loop + conditionals

**Files:** `hooks/lib/derive_phase.py` (or the conductor rendering path used by `/req` and `workflow-index`), the `req`-phase CLI, and the phase-nudge directive (`hooks/lib/brainstorm.py::phase_directive`). Test: new `test_conductor_surfaces_loop_and_conditionals`.

**Behavior:**
- When the derived phase is `build`, the conductor/status appends: "Loop: run `/pre-commit` before each commit."
- When the derived phase has `conditionals`, append: "Available here: `/codex-review` …".
- `phase_directive` for a `team` phase notes "(runs a review team)".

**Steps:** write a test that, given a config whose current phase is `build`, the conductor output mentions `/pre-commit`; and a phase with conditionals mentions them (RED) → implement a small helper that reads `loop`/`conditionals` off the resolved phase and renders one advisory line (GREEN) → ruff → commit `recut-conductor-surfacing`.

---

## Task 7: Test-vocabulary migration sweep

**Files:** `hooks/test_requirements.py` (the remaining assertions referencing old vocabulary).

**Strategy (not line-by-line — a guided sweep):**
- `commit_plan` (241 hits) is mostly an *example requirement name* in temp test configs — those DON'T need changing (they define it inline). Only change assertions tied to the DEFAULT workflow / auto-satisfy vocabulary.
- Grep-and-fix the genuine vocabulary assertions: `grep -nE "plan-write|plan-validate|'plan-validate'|pre_pr_review|adr_reviewed|solid_reviewed|codex_reviewer" hooks/test_requirements.py` and update each that asserts default-workflow behavior to the new names.
- Run the full suite after each cluster; target: 7 known-pre-existing failures only, no NEW failures.

**Commit:** `recut-test-migration` (may be several refreshes).

---

## Task 8: Docs + ADR + plugin bump

**Files:** `CLAUDE.md` (workflow section), a new `docs/adr/ADR-0XX-workflow-phase-recut.md`, `plugins/requirements-framework/.claude-plugin/plugin.json` (minor bump), `.claude-plugin/marketplace.json`.

**Actions:** document the typed-node model + gate table; write a short ADR capturing the decision (typed nodes, one-gate-per-team, manual conditionals, clean renames); bump plugin version; keep `update-plugin-versions.sh` git_hash churn in its own chore patch (or leave for CI). Run `uv run ruff check .` and the full suite one final time. **Commit:** `recut-docs-and-bump`.

---

## Notes / risks
- **Interaction with nudge-only:** `resolve_current_phase`/`phase_directive` walk by gate, so they adopt the new vocabulary for free. Verify the nudge integration tests still pass over the new default.
- **`commit_plan` blast radius:** resist a blind rename — most uses are incidental example requirements. Only touch default-workflow/auto-satisfy assertions.
- **Execution size:** this is larger than nudge-only (config + map + configs + messages + conductor + ~300 test-line sweep + docs). Consider `/refactor-orchestrate` or a parallel executing-plans session over subagent-driven, given the mechanical sweep volume.
- **No compat shims:** old gate names are deleted; a project still using them gets validation errors pointing at the new names (that's the intended migration signal).
