# Workflow Backbone Re-cut Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use requirements-framework:executing-plans to implement this plan task-by-task.

**Goal:** Re-cut the workflow backbone to a 6-node spine: verify becomes a per-push loop on build, the three early gates go branch-scoped, and a small-tier triage signal auto-satisfies plan/validate.

**Architecture:** Four independent decisions from the approved design (`2026-07-13-workflow-map-and-critique.md`, Part 4). The `loop` node key is replaced by a `loops` list (breaking, no compat shim — old key hard-errors). Branch scope is config-only (the satisfy path already honors `config.get_scope`). The tier signal is a new branch-level state marker written by a Claude-runnable `req tier` command and read by the auto-satisfy hook.

**Tech Stack:** Python via `uv` (`uv run python hooks/test_requirements.py`), custom TestRunner (register tests in `main()`, NOT unittest), stg patches, plugin bundle rebuilt with `scripts/build_plugin_hooks.py`.

**Version bump:** `loops` schema change is breaking → `plugins/requirements-framework/.claude-plugin/plugin.json` **6.0.1 → 7.0.0**, bumped in the first plugin-touching patch (Task 4); later patches on this branch share the release.

**House rules that bind every task:** never `git commit` (use `stg new`/`stg refresh`); rebuild the bundle in every patch that touches `hooks/`; run `uv run ruff check .` before each refresh (CI lints, local harness doesn't); green local = all-but-5 (the config validation-error group fails locally only).

---

## Phase 1 — Decision B: branch scope for the early gates

### Task 1: Characterization test — branch-scoped auto-satisfy survives a new session

**Files:**
- Modify: `hooks/test_requirements.py` (add test, register in `main()`)

**Step 1: Write the failing test**

Follow the file's existing test conventions (plain functions + asserts, temp git repo fixtures already used by neighboring tests). Test intent:

```python
def test_branch_scoped_gate_survives_session_change():
    """A gate satisfied with scope=branch is satisfied for a DIFFERENT session
    on the same branch (day-2 session must not re-nudge)."""
    # arrange: temp repo + BranchRequirements(branch, session_id='sess-one', ...)
    reqs.satisfy('design_approved', scope='branch', method='skill')
    # act: new BranchRequirements with session_id='sess-two', same branch
    assert reqs2.is_satisfied('design_approved', scope='branch') is True
    # and the nudge resolver's view: resolve_current_phase must NOT return 'design'
```

Also assert the inverse for session scope (`scope='session'` satisfied by sess-one is NOT satisfied for sess-two) so the test pins the distinction.

**Step 2: Run it**

Run: `uv run python hooks/test_requirements.py`
Expected: the branch-scope half likely already PASSES (`requirements.py:221` supports branch scope) — this is a characterization test. If it passes immediately, keep it and move on; RED is not required for pinning existing behavior.

**Step 3: Verify `resolve_current_phase` uses the configured scope**

Read `hooks/lib/brainstorm.py` from line 187 (loop body of `resolve_current_phase`). Confirm it calls `reqs.is_satisfied(gate, scope=<configured scope>)` — not hardcoded `'session'`. If hardcoded: fix it to read `config.get_scope(gate)` and add a test where a branch-scoped satisfied gate is skipped by the nudge resolver for a new session. This is the one code change B might need.

**Step 4: Commit**

```bash
stg new b-branch-scope-tests -m "test: pin branch-scope satisfaction across sessions (decision B)"
stg refresh
```

### Task 2: Flip the three gates to branch scope (config)

**Files:**
- Modify: `.claude/requirements.yaml` — `plan_validated`: `scope: session` → `scope: branch`
- Modify: `.claude/requirements.local.yaml` — `design_approved`, `plan_written`: `scope: session` → `scope: branch`
- Modify: `examples/global-requirements.yaml` — same three gates wherever defined
- Check: `examples/project-requirements.yaml` for the same keys

**Step 1: Edit the four YAML files.** Exact change per gate: `scope: session` → `scope: branch`. Do NOT touch `pre_commit_review`/`pr_reviewed`/`verified` (stay `single_use`) or `implementation_done` (stays `session` — deliberate: day-2 build sessions should re-nudge "continue executing"; recorded in the design doc).

**Step 2: Run the suite.** `uv run python hooks/test_requirements.py`
Expected: all-but-5. If any test pins `scope: session` for these gates in example-config fixtures, update those pins in the same patch — that's the point of the change, not collateral.

**Step 3: Grep for stale scope claims in docs.**

Run: `grep -rn "design_approved\|plan_written\|plan_validated" docs/README-REQUIREMENTS-FRAMEWORK.md docs/PLUGIN-INSTALLATION.md CLAUDE.md | grep -i session`
Update any doc line asserting these are session-scoped.

**Step 4: Commit**

```bash
stg new b-branch-scope-config -m "feat(config): design/plan/validate gates go branch-scoped (decision B)"
stg refresh
```

---

## Phase 2 — Decision A: verify becomes a loop; `loop` → `loops`

### Task 3: TDD the `loops` schema in WorkflowValidator

**Files:**
- Modify: `hooks/test_requirements.py`
- Modify: `hooks/lib/config.py` (`WorkflowValidator.validate`, ~line 775)

**Step 1: Write failing tests**

```python
def test_workflow_validator_rejects_legacy_loop_key():
    """Old singular `loop` key must hard-error and point at `loops` (no shim)."""
    wf = {"phases": [{"name": "build", "gate": "g",
                      "loop": {"gate": "x", "skill": "s", "on": "commit"}}]}
    err = WorkflowValidator().validate(wf, {"g": {}, "x": {}})
    assert err is not None and "loops" in err

def test_workflow_validator_accepts_loops_list():
    wf = {"phases": [{"name": "build", "gate": "g", "loops": [
        {"gate": "x", "skill": "s", "on": "commit"},
        {"gate": "y", "skill": "t", "on": "push"}]}]}
    assert WorkflowValidator().validate(wf, {"g": {}, "x": {}, "y": {}}) is None

def test_workflow_validator_rejects_malformed_loops():
    # loops not a list; entry not a mapping; entry missing non-empty skill;
    # entry gate not in requirements — each returns a descriptive error
    ...
```

Register all in `main()`.

**Step 2: Run to verify they fail**

Run: `uv run python hooks/test_requirements.py`
Expected: FAIL (validator currently ignores both keys).

**Step 3: Implement in `WorkflowValidator.validate`** (inside the per-phase loop, after the `description` check):

```python
if "loop" in entry:
    return (
        f"workflow phase {name!r} uses removed key 'loop'; "
        "use 'loops' (a list of {gate, skill, on} mappings)"
    )
loops = entry.get("loops")
if loops is not None:
    if not isinstance(loops, list):
        return f"workflow phase {name!r} loops must be a list"
    for lidx, loop_entry in enumerate(loops):
        if not isinstance(loop_entry, Mapping):
            return f"workflow phase {name!r} loops[{lidx}] must be a mapping"
        lskill = loop_entry.get("skill")
        if not isinstance(lskill, str) or not lskill:
            return f"workflow phase {name!r} loops[{lidx}] needs a non-empty 'skill'"
        lgate = loop_entry.get("gate")
        if lgate is not None and (
            not isinstance(lgate, str) or lgate not in requirements
        ):
            return (
                f"workflow phase {name!r} loops[{lidx}] gate {lgate!r} "
                "is not a defined requirement"
            )
```

**Step 4: Run tests** — expected: PASS. **Step 5: Commit** — `stg new a-loops-validator -m "feat(workflow): loops list replaces loop key in validator (breaking)"; stg refresh`

### Task 4: Re-cut WORKFLOW_DEFAULTS + brainstorm.py loop rendering

**Files:**
- Modify: `hooks/lib/config.py:911` (`WORKFLOW_DEFAULTS`)
- Modify: `hooks/lib/brainstorm.py:145-149` (`phase_directive`)
- Modify: `hooks/test_requirements.py`
- Modify: `plugins/requirements-framework/.claude-plugin/plugin.json` (**bump 7.0.0**)

**Step 1: Failing tests first**

```python
def test_default_workflow_is_six_nodes_with_two_build_loops():
    phases = RequirementsConfig.WORKFLOW_DEFAULTS["phases"]
    assert [p["name"] for p in phases] == [
        "design", "plan", "validate", "build", "review", "ship"]
    build = next(p for p in phases if p["name"] == "build")
    assert [(l["gate"], l["on"]) for l in build["loops"]] == [
        ("pre_commit_review", "commit"), ("verified", "push")]

def test_phase_directive_renders_multiple_loops():
    cfg = {"loops": [
        {"gate": "pre_commit_review", "skill": "rf:pre-commit", "on": "commit"},
        {"gate": "verified", "skill": "rf:verification-before-completion", "on": "push"}]}
    text = phase_directive("build", "rf:executing-plans", cfg)
    assert "/pre-commit` before each commit" in text
    assert "/verification-before-completion` before each push" in text
```

**Step 2: Run — expected FAIL.**

**Step 3: Implement.**

`WORKFLOW_DEFAULTS`: delete the `verify` phase dict entirely; on the `build` phase replace

```python
"loop": {"gate": "pre_commit_review", "skill": "requirements-framework:pre-commit", "on": "commit"},
```

with

```python
"loops": [
    {"gate": "pre_commit_review", "skill": "requirements-framework:pre-commit", "on": "commit"},
    {"gate": "verified", "skill": "requirements-framework:verification-before-completion", "on": "push"},
],
```

`brainstorm.py` `phase_directive`: replace the single-loop block (`loop = cfg.get('loop') ...`) with:

```python
loops = cfg.get('loops')
if isinstance(loops, list):
    for loop in loops:
        if isinstance(loop, dict) and loop.get('skill'):
            loop_cmd = '/' + str(loop['skill']).split(':')[-1]
            trigger = loop.get('on') or 'commit'
            extra.append(f"Loop: run `{loop_cmd}` before each {trigger}.")
```

**Step 4: Sweep every other `loop` consumer.**

Run: `grep -rn "'loop'\|\"loop\"\|\.loop\b" hooks/ plugins/requirements-framework/hooks/ scripts/ --include="*.py" | grep -v loops | grep -v test_`
Fix each hit to the list form (expected: `brainstorm.py` docstrings, possibly `derive_phase.py` comments only — derivation ignores loops). Also grep command/skill markdown: `grep -rln "loop" plugins/requirements-framework/commands/req.md plugins/requirements-framework/skills/workflow-index/` and fix wording that describes a single loop.

**Step 5: Run suite + lint** — expected: all-but-5, ruff clean. **Step 6:** bump `plugin.json` `"version"` to `7.0.0`; rebuild bundle: `uv run python scripts/build_plugin_hooks.py`; verify render: `uv run python scripts/render_prompts.py --check`.

**Step 7: Commit** — `stg new a-six-node-backbone -m "feat(workflow)!: 6-node spine; verify becomes per-push loop on build (ADR-023)"; stg refresh`

### Task 5: Project config + docs follow the re-cut

**Files:**
- Modify: `.claude/requirements.local.yaml` (`workflow:` section)
- Modify: `CLAUDE.md` (backbone table + diagram)
- Modify: `examples/global-requirements.yaml` / `examples/project-requirements.yaml` (any `workflow:` blocks)
- Create: `docs/adr/ADR-023-six-node-backbone-recut.md`

**Step 1:** In `.claude/requirements.local.yaml`, drop the verify phase line and change the build line to:

```yaml
- { name: build, type: spine, gate: implementation_done, skill: "requirements-framework:executing-plans",
    loops: [ { gate: pre_commit_review, skill: "requirements-framework:pre-commit", "on": commit },
             { gate: verified, skill: "requirements-framework:verification-before-completion", "on": push } ] }
```

(YAML footgun: keep `"on"` quoted.) The `verified` requirement definition in `.claude/requirements.yaml` is unchanged — still `single_use`, still trips on `git push`.

**Step 2:** Update `CLAUDE.md` — 7-node diagram → 6-node with two build loops; table row for verify moves into the build row's loop column; gate vocabulary count note stays 7 (gate set is unchanged — only the *node* went away).

**Step 3:** Write ADR-023 (amends ADR-022): decisions A+B+C, the investigation rationale (verify gate already behaved as a loop; Ship re-runs tests; doc drift), the breaking `loop`→`loops` schema change, rejected alternatives (swap order; keep-and-document; nudge suppression). Reference the design doc.

**Step 4:** Verify live: `uv run python -c "import sys; sys.path.insert(0,'hooks/lib'); from derive_phase import derive_phase; print('ok')"` then run the suite. Because this repo's own config now uses `loops`, an error here means the validator or config merge is broken — the config must NOT be dropped (check `req doctor` output for "Disabled invalid workflow config").

**Step 5: Commit** — `stg new a-config-docs -m "docs+config: adopt 6-node backbone (ADR-023)"; stg refresh`

### Task 6: Fix verify SKILL.md auto-satisfy drift

**Files:**
- Modify: `plugins/requirements-framework/skills/verification-before-completion/SKILL.md:123-125` (and its `.j2` source if one exists — check `ls plugins/requirements-framework/skills/verification-before-completion/`)

**Step 1:** Replace the "Requirements Integration" section text with:

```markdown
## Requirements Integration

Completing this skill auto-satisfies the `verified` gate (single_use — it re-arms
after every `git push`, so run it before each push). In the default workflow it is
the build node's per-push loop.
```

If the rendered file comes from a `.md.j2` template, edit the template and run `uv run python scripts/render_prompts.py` (then `--check`).

**Step 2: Commit** — `stg new a-verify-skill-drift -m "docs(skill): verification-before-completion does auto-satisfy verified"; stg refresh`

---

## Phase 3 — Decision C: tier signal

### Task 7: TDD `set_tier`/`get_tier` on BranchRequirements

**Files:**
- Modify: `hooks/test_requirements.py`
- Modify: `hooks/lib/requirements.py`

**Step 1: Failing tests**

```python
def test_tier_marker_roundtrip_and_branch_persistence():
    reqs.set_tier('small', session_id='sess-one')
    assert reqs.get_tier() == 'small'
    # different session, same branch: tier is a branch-level fact
    assert reqs_sess_two.get_tier() == 'small'

def test_tier_marker_rejects_unknown_value():
    assert reqs.set_tier('gigantic') is False
    assert reqs.get_tier() is None
```

**Step 2: Run — FAIL. Step 3: Implement** in `requirements.py` (methods on `BranchRequirements`, using the same locked read-modify-write helpers `satisfy` uses — find the `_update_state`/flock pattern in that class and reuse it):

```python
VALID_TIERS = ('small', 'standard', 'deep')

def set_tier(self, tier: str, session_id: str | None = None) -> bool:
    """Record the triage tier as a branch-level marker in the state file."""
    if tier not in VALID_TIERS:
        return False
    # inside the class's locked update helper:
    state['tier'] = {'value': tier, 'session': session_id or self.session_id}
    return True

def get_tier(self) -> str | None:
    tier = (self._read_state() or {}).get('tier')
    return tier.get('value') if isinstance(tier, dict) else None
```

(Adapt to the class's actual state-access helpers — mirror how `satisfy` reads/writes; no timestamps needed, YAGNI.)

**Step 4: Run — PASS. Step 5: Commit** — `stg new c-tier-state -m "feat(state): branch-level triage tier marker"; stg refresh`

### Task 8: `req tier` CLI subcommand (Claude-runnable)

**Files:**
- Modify: `hooks/requirements-cli.py` (new `cmd_tier` near `cmd_pause:669`; parser near line 3585)
- Modify: `hooks/test_requirements.py` (CLI-level test if the file has CLI tests — mirror an existing `cmd_*` test; otherwise cover via Task 7's lib tests and a manual check)

**Step 1: Implement** modeled exactly on `cmd_pause` (project-dir + git checks, `--session` resolution):

```python
def cmd_tier(args) -> int:
    """Record the brainstorming triage tier for the current branch.

    Claude MAY run this (like `req pause`): it only annotates state; the
    auto-satisfy hook decides what it means. No tier argument prints the
    current marker.
    """
    project_dir = get_project_dir()
    if not is_git_repo(project_dir):
        out(error("❌ Not in a git repository")); return 1
    branch = get_current_branch(project_dir)
    session_id = _resolve_pause_session(args)  # same resolution as pause
    reqs = BranchRequirements(branch, session_id or 'cli', project_dir)
    if not getattr(args, 'tier', None):
        current = reqs.get_tier()
        out(current or "no tier recorded"); return 0
    if reqs.set_tier(args.tier, session_id=session_id):
        out(success(f"Tier recorded: {args.tier}")); return 0
    out(error(f"❌ Invalid tier {args.tier!r} (small|standard|deep)")); return 1
```

Parser:

```python
tier_parser = subparsers.add_parser('tier', help='Record brainstorming triage tier (small|standard|deep)')
tier_parser.add_argument('tier', nargs='?', choices=['small', 'standard', 'deep'])
tier_parser.add_argument('--session', help='Session ID')
```

Wire `cmd_tier` into the command dispatch (find where `'pause'` maps to `cmd_pause`).

**Step 2: Verify manually**

Run: `uv run python hooks/requirements-cli.py tier small --session test-sess && uv run python hooks/requirements-cli.py tier`
Expected: `Tier recorded: small` then `small`.

**Step 3: Suite + lint + bundle rebuild** (`requirements-cli.py` IS bundled). **Step 4: Commit** — `stg new c-tier-cli -m "feat(cli): req tier records triage tier"; stg refresh`

### Task 9: Auto-satisfy reads the tier on brainstorming completion

**Files:**
- Modify: `hooks/test_requirements.py`
- Modify: `hooks/auto-satisfy-skills.py` (after the satisfy loop, ~line 208)

**Step 1: Failing test** — simulate the hook's satisfy path (the suite likely has existing auto-satisfy tests to mirror; if it only tests helpers, extract the new logic into a testable function):

```python
def test_small_tier_brainstorming_also_satisfies_plan_gates():
    reqs.set_tier('small')
    # invoke the extracted helper with skill='requirements-framework:brainstorming'
    satisfied = apply_tier_shortcut(config, reqs, 'requirements-framework:brainstorming')
    assert set(satisfied) == {'plan_written', 'plan_validated'}
    assert reqs.is_satisfied('plan_written', scope='branch')

def test_standard_tier_does_not_shortcut():
    reqs.set_tier('standard')
    assert apply_tier_shortcut(config, reqs, 'requirements-framework:brainstorming') == []
```

**Step 2: Run — FAIL. Step 3: Implement** as a module-level function in `auto-satisfy-skills.py`, called from `main()` right after the existing satisfy loop:

```python
TIER_SHORTCUT_GATES = ('plan_written', 'plan_validated')

def apply_tier_shortcut(config, reqs, skill_name) -> list[str]:
    """Small-tier design shortcut (ADR-023): when brainstorming completes on a
    branch marked tier=small, the plan/validate gates are satisfied too —
    recorded with method 'tier' so state shows WHY they flipped."""
    if skill_name != 'requirements-framework:brainstorming':
        return []
    if reqs.get_tier() != 'small':
        return []
    satisfied = []
    for gate in TIER_SHORTCUT_GATES:
        if not config.is_requirement_enabled(gate):
            continue
        reqs.satisfy(gate, config.get_scope(gate), method='tier',
                     metadata={'tier': 'small'})
        satisfied.append(gate)
    return satisfied
```

In `main()`: extend `satisfied_reqs` with the result (so logging + metrics + Obsidian all report it).

**Step 4: Run — PASS. Step 5: bundle rebuild, commit** — `stg new c-tier-autosatisfy -m "feat(hooks): small tier auto-satisfies plan gates on brainstorm completion"; stg refresh`

### Task 10: Brainstorming skill records the tier

**Files:**
- Modify: `plugins/requirements-framework/skills/brainstorming/SKILL.md` (+ `.j2` source if present) — Step 0 (Triage)
- Modify: `plugins/requirements-framework/skills/brainstorming/references/triage.md` — "Announce and route"

**Step 1:** In the triage announce instruction, add one line:

```markdown
After announcing the tier, record it: `req tier <small|standard|deep> --session <session-id>`
(you MAY run this — it only annotates state). On a small tier this lets the framework
skip the plan/validate nudges when the design is approved.
```

Also update SKILL.md's "Requirements Integration" section to mention the small-tier shortcut. Re-render if templated (`render_prompts.py`), re-check.

**Step 2: Commit** — `stg new c-tier-skill-text -m "feat(skill): brainstorming triage records tier via req tier"; stg refresh`

---

## Phase 4 — E follow-up + wrap-up

### Task 11: Characterization test for the E asymmetry

**Files:**
- Modify: `hooks/test_requirements.py`

**Step 1:** Write a test documenting current behavior (default `session_end.clear_session_state: False`, per `config.py:873-875`): a session-scoped gate satisfied by a dead session still counts for `derive_phase._is_satisfied` (any-session) but not for `BranchRequirements.is_satisfied` under a new session id. Name it `test_derive_phase_any_session_vs_gating_current_session_asymmetry` with a docstring pointing at the design doc's E section. This is a pin, not a fix — after B, the only backbone gate still exposed is `implementation_done`; fixing is deliberately out of scope.

**Step 2: Run (expect PASS — it pins reality), commit** — `stg new e-asymmetry-pin -m "test: pin derive_phase any-session vs gating current-session asymmetry"; stg refresh`

### Task 12: Final verification sweep

**Step 1:** `uv run python hooks/test_requirements.py` → all-but-5 (the local-only config validation group).
**Step 2:** `uv run ruff check .` → clean.
**Step 3:** `uv run python scripts/render_prompts.py --check` → all fresh.
**Step 4:** `uv run python scripts/build_plugin_hooks.py` → bundle in sync; `git status` must be clean after (if it dirties files, fold them into the owning patch with `stg refresh`).
**Step 5:** Live smoke: `uv run python hooks/requirements-cli.py status` and `req-phase` (statusline path) on this branch — the 6-node workflow must load (no "Disabled invalid workflow config" in logs).
**Step 6:** Update the design doc status line + memory (`refactor-current-status.md`) after merge, not before.

---

## Explicitly out of scope (YAGNI, per design)

- Any edge wiring (TDD loop, receiving-code-review conditional, ship gate) — decision D.
- Fixing the E asymmetry for `implementation_done` (pinned by test, deferred).
- `req tier` permission-allowlist plumbing — `req tier` is additive; users allowlist like `req pause`.
- Migrating other projects' configs — they get the hard error pointing at `loops` (house rule: no shims).
