# Nudge-Only Workflow Conductor — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use requirements-framework:executing-plans to implement this plan task-by-task.

**Goal:** Turn the requirements framework from a wall into a guide — nothing ever denies an Edit/commit/Stop; a proactive once-per-phase nudge chain (generalizing the brainstorm nudge) walks Claude through the whole workflow, and every gate downgrades to an advisory.

**Architecture:** One new global config axis `enforcement: block | nudge` (default `block`). In `nudge` mode the two blocking hooks (`check-requirements.py` PreToolUse, `handle-stop.py` Stop) allow instead of deny, surfacing the existing messages as advisory context. The proactive nudge in `handle-prompt-submit.py` stops being brainstorm-only: it calls `derive_phase_and_skill()` and nudges the current phase's skill, deduped by `(session, phase)`. A soft `implementation_done` marker gives the gateless `implement` phase a gate so the chain nudges "write the code" before "review".

**Tech Stack:** Python stdlib + PyYAML; existing strategy/config/derive_phase modules; TestRunner harness in `hooks/test_requirements.py` (NOT unittest); `uv run` for all execution.

**Deploy note:** This session runs the marketplace bundle, so hook changes are inert until relaunch with `claude --plugin-dir ~/Tools/claude-requirements-framework/plugin`. Run `./sync.sh deploy` + relaunch before live-testing. Bump `plugins/requirements-framework/.claude-plugin/plugin.json` in any patch touching plugin files.

**Test invocation:** `uv run python hooks/test_requirements.py` (green baseline = 1537/1544; 7 pre-existing failures to ignore). Lint: `uv run ruff check .`

---

## Task 1: `enforcement` config getter (block | nudge)

**Files:**
- Modify: `hooks/lib/config.py` — concrete getter near `strict_preflight_enabled` (~line 1268) AND the delegating Protocol wrapper (~line 397).
- Test: `hooks/test_requirements.py` — new `test_enforcement_mode(runner)`.

**Step 1: Write the failing test**

```python
def test_enforcement_mode(runner):
    import tempfile, os
    from config import RequirementsConfig
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, ".claude"), exist_ok=True)
        # default = block when unset
        cfg = RequirementsConfig(d)
        runner.test("enforcement defaults to block", cfg.enforcement() == "block")
        # explicit nudge honored
        with open(os.path.join(d, ".claude", "requirements.yaml"), "w") as f:
            f.write("version: '1.0'\nenabled: true\nenforcement: nudge\n")
        cfg2 = RequirementsConfig(d)
        runner.test("enforcement reads nudge", cfg2.enforcement() == "nudge")
        # unknown value falls back to block (fail-safe)
        with open(os.path.join(d, ".claude", "requirements.yaml"), "w") as f:
            f.write("version: '1.0'\nenabled: true\nenforcement: banana\n")
        cfg3 = RequirementsConfig(d)
        runner.test("enforcement unknown -> block", cfg3.enforcement() == "block")
```

Register in `main()` next to `test_config_module(runner)`.

**Step 2: Run to verify it fails**

Run: `uv run python hooks/test_requirements.py 2>&1 | grep -i enforcement`
Expected: FAIL — `AttributeError: 'RequirementsConfig' object has no attribute 'enforcement'`.

**Step 3: Minimal implementation**

Concrete class (mirror `strict_preflight_enabled`, ~line 1268 in `config.py`):

```python
    def enforcement(self) -> str:
        """Enforcement mode: 'block' (default) or 'nudge'.

        Top-level key `enforcement`, mirroring `strict_preflight`/`enabled`.
        Any value other than the literal 'nudge' fails safe to 'block' so a
        typo can never silently disable all gates.
        """
        return "nudge" if self._config.get("enforcement") == "nudge" else "block"
```

Delegating wrapper (~line 397, next to the wrapper's `strict_preflight_enabled`):

```python
    def enforcement(self) -> str:
        return self._config.enforcement()
```

**Step 4: Run to verify it passes**

Run: `uv run python hooks/test_requirements.py 2>&1 | grep -i enforcement`
Expected: PASS (3 assertions).

**Step 5: Commit**

```bash
stg new enforcement-config-getter -m "feat(config): add enforcement block|nudge axis"
stg refresh
```

---

## Task 2: `check-requirements.py` — nudge mode allows + advises

**Files:**
- Modify: `hooks/check-requirements.py` — the `if unsatisfied:` block-emission branch (~line 536).
- Reuse: `create_batched_denial()` (line 131) message text via a thin advisory wrapper.
- Test: `hooks/test_requirements.py` — extend `test_hook_behavior` or add `test_nudge_mode_allows(runner)`.

**Design:** At the block-emission fork, if `config.enforcement() == "nudge"`, DO NOT deny. Instead: (a) emit the same message as a PreToolUse advisory (allow + `additionalContext`), deduped by `(session, phase)` so it surfaces once per phase not per Edit; (b) fall through to the allow path so `triggered_candidates` are marked. Reuse the deny message body by extracting `permissionDecisionReason` from `create_batched_denial(...)` and re-emitting as an allow advisory.

**Step 1: Write the failing test**

```python
def test_nudge_mode_allows(runner):
    # In nudge mode, a triggered-but-unsatisfied requirement must NOT produce a
    # deny response. Drive check_requirements() with enforcement: nudge and assert
    # the emitted decision is not 'deny'.
    import tempfile, os, json, io, contextlib
    # ... set up temp project with enforcement: nudge + one enabled blocking req
    # ... call the module's main/handler with an Edit tool payload
    # ... capture stdout JSON; assert response.get('hookSpecificOutput',{})
    #        .get('permissionDecision') != 'deny'
    runner.test("nudge mode does not deny", decision != "deny")
    runner.test("nudge mode surfaces advisory context", "plan" in advisory_text.lower())
```

(Model the harness on the existing `test_hook_behavior` — reuse its temp-project + stdin-injection helper.)

**Step 2: Run to verify it fails**

Run: `uv run python hooks/test_requirements.py 2>&1 | grep -i "nudge mode"`
Expected: FAIL — currently returns a deny in both modes.

**Step 3: Minimal implementation**

Add a helper near `create_batched_denial`:

```python
def create_batched_advisory(unsatisfied, session_id, project_dir, branch) -> dict:
    """Same message as the denial, but as an ALLOW + advisory context.

    Nudge mode: guide, don't wall. Reuses create_batched_denial's rendered text
    so block/nudge stay in lockstep.
    """
    denial = create_batched_denial(unsatisfied, session_id, project_dir, branch)
    reason = denial.get("hookSpecificOutput", {}).get("permissionDecisionReason", "")
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
            "additionalContext": reason,
        }
    }
```

Fork the emission branch (~line 536):

```python
        if unsatisfied:
            nudge_mode = config.enforcement() == "nudge"
            logger.info(
                "Requirements %s (batched)" % ("advised" if nudge_mode else "blocked"),
                requirements=[r[0] for r in unsatisfied],
                count=len(unsatisfied),
            )
            for req_name, _ in unsatisfied:
                metrics.record_tool_use(tool_name, file=file_path,
                                        blocked=not nudge_mode, requirement=req_name)
                metrics.record_requirement_trigger(req_name, blocked=not nudge_mode)
            metrics.save()

            if nudge_mode:
                # Dedup per (session, phase) so the advisory surfaces once, then
                # fall through to the allow path (mark triggered candidates).
                if _advisory_not_shown(session_id, project_dir):
                    emit_json(create_batched_advisory(unsatisfied, session_id, project_dir, branch))
                    _mark_advisory_shown(session_id, project_dir)
                # DO NOT return — fall through to allow path below.
            else:
                emit_json(create_batched_denial(unsatisfied, session_id, project_dir, branch))
                return 0
```

For `_advisory_not_shown` / `_mark_advisory_shown`, reuse the phase-keyed marker helper built in Task 4 (import from `phase_nudge`), keyed by `(session, current_phase)`. If Task 4 isn't landed yet, stub with a per-session marker and tighten in Task 4.

**Step 4: Run to verify it passes**

Run: `uv run python hooks/test_requirements.py 2>&1 | grep -i "nudge mode"`
Expected: PASS.

**Step 5: Commit**

```bash
stg new check-requirements-nudge-mode -m "feat(hooks): nudge mode allows + advises instead of denying"
stg refresh
```

---

## Task 3: `handle-stop.py` — nudge mode never blocks Stop

**Files:**
- Modify: `hooks/handle-stop.py` — mirror the `is_paused` short-circuit already present.
- Test: `hooks/test_requirements.py` — extend `test_stop_hook` with a nudge-mode case.

**Step 1: Write the failing test**

```python
def test_stop_hook_nudge_mode(runner):
    # With enforcement: nudge, the Stop hook must not block even if a session
    # requirement is unsatisfied. Assert exit/decision is non-blocking.
    runner.test("nudge mode: stop not blocked", not blocked)
```

**Step 2: Run to verify it fails**

Run: `uv run python hooks/test_requirements.py 2>&1 | grep -i "stop not blocked"`
Expected: FAIL — Stop still blocks on unsatisfied session reqs.

**Step 3: Minimal implementation**

Find the existing pause short-circuit in `handle-stop.py` (`from pause import is_paused` / `if is_paused(...)`) and add alongside it:

```python
        # Nudge mode: guidance-only, never block Stop. Mirrors pause suppression.
        try:
            if config.enforcement() == "nudge":
                logger.info("Stop verification skipped (nudge mode)")
                return 0
        except Exception:
            pass  # fail-open
```

(Place immediately after the `is_paused` block so both escape hatches share the same allow path.)

**Step 4: Run to verify it passes**

Run: `uv run python hooks/test_requirements.py 2>&1 | grep -i "stop not blocked"`
Expected: PASS.

**Step 5: Commit**

```bash
stg new stop-hook-nudge-mode -m "feat(hooks): Stop hook honors nudge mode (never blocks)"
stg refresh
```

---

## Task 4: Generalize the brainstorm nudge → phase nudge

**Files:**
- Modify: `hooks/lib/brainstorm.py` → add phase-agnostic directive + `(session, phase)` marker. Keep `brainstorm_directive` as the phase-1 special case; add `phase_directive(phase, skill)` and phase-keyed marker helpers. (Keep the module name to avoid churn; it already owns the nudge.)
- Test: `hooks/test_requirements.py` — `test_phase_nudge(runner)`.

**Step 1: Write the failing test**

```python
def test_phase_nudge(runner):
    import tempfile
    from brainstorm import (phase_directive, phase_nudge_shown,
                            mark_phase_nudge_shown)
    with tempfile.TemporaryDirectory() as d:
        # directive names the phase's slash-skill
        txt = phase_directive("plan-write", "requirements-framework:writing-plans")
        runner.test("phase directive names skill", "/writing-plans" in txt)
        # dedup is per-phase: marking plan-write does not silence review
        mark_phase_nudge_shown("sess1", d, "plan-write")
        runner.test("plan-write marked", phase_nudge_shown("sess1", d, "plan-write"))
        runner.test("review still unmarked", not phase_nudge_shown("sess1", d, "review"))
```

**Step 2: Run to verify it fails**

Run: `uv run python hooks/test_requirements.py 2>&1 | grep -i "phase directive\|plan-write marked\|review still"`
Expected: FAIL — functions don't exist.

**Step 3: Minimal implementation** (in `brainstorm.py`)

```python
def phase_directive(phase: str, skill: str) -> str:
    """Generic 'next step' nudge for any workflow phase.

    The brainstorm/design phase keeps its richer directive (brainstorm_directive);
    every other phase renders this concise form from the configured skill.
    """
    command = "/" + skill.split(":")[-1]
    return f"""\
## Next Step: {phase}

You're in the **{phase}** phase of the workflow. Invoke `{command}` to proceed.

This is a nudge, not a block — you can proceed without it, but the workflow
expects `{command}` here."""


def _phase_marker_path(session_id, project_dir, phase):
    token = _safe_session_token(session_id)
    ptoken = _safe_session_token(phase)
    return get_state_dir(project_dir) / f".phase-nudge-{token}-{ptoken}"


def phase_nudge_shown(session_id, project_dir, phase) -> bool:
    try:
        return _phase_marker_path(session_id, project_dir, phase).exists()
    except Exception:
        return False


def mark_phase_nudge_shown(session_id, project_dir, phase) -> None:
    try:
        p = _phase_marker_path(session_id, project_dir, phase)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.touch()
    except Exception:
        pass
```

**Step 4: Run to verify it passes**

Run: `uv run python hooks/test_requirements.py 2>&1 | grep -i "phase directive\|plan-write marked\|review still"`
Expected: PASS (3 assertions).

**Step 5: Commit**

```bash
stg new phase-nudge-helpers -m "feat(nudge): phase-agnostic directive + per-phase dedup markers"
stg refresh
```

---

## Task 5: Wire the phase nudge into `handle-prompt-submit.py`

**Files:**
- Modify: `hooks/handle-prompt-submit.py` — replace the brainstorm-only nudge block (~lines 178–200) with a phase-driven nudge.
- Test: covered by an integration assertion in `test_phase_nudge` or a new `test_prompt_submit_phase_nudge`.

**Step 1: Write the failing test**

Assert that, given a state file where `design_approved` is satisfied but `plan_written` is not, the prompt-submit nudge emits `/writing-plans` (not `/brainstorming`).

**Step 2: Run to verify it fails**

Expected: FAIL — current code always resolves the brainstorm phase.

**Step 3: Minimal implementation**

Replace the nudge block with:

```python
        # PROACTIVE phase nudge (generalizes the brainstorm nudge across the
        # whole workflow). Derives the current phase + skill and nudges once per
        # phase. The design phase keeps its richer brainstorm directive.
        if (
            prompt
            and config.get_hook_config('prompt_submit', 'brainstorm_nudge', True)
            and _prompt_is_substantive(prompt)
        ):
            from derive_phase import derive_phase_and_skill
            from state_storage import get_state_file  # confirm exact name
            state_file = get_state_file(project_dir, branch)
            phase, skill = derive_phase_and_skill(state_file)
            if skill and not phase_nudge_shown(session_id, project_dir, phase):
                directive = (brainstorm_directive(skill)
                             if phase in ("design",)
                             else phase_directive(phase, skill))
                emit_hook_context("UserPromptSubmit", directive)
                mark_phase_nudge_shown(session_id, project_dir, phase)
                logger.debug("Injected phase nudge", phase=phase, skill=skill)
                return 0
```

Update the import line at top (~line 39) from `brainstorm import (...)` to also import `phase_directive, phase_nudge_shown, mark_phase_nudge_shown`. Verify `state_storage` exposes a state-file resolver; if not, build the path as `Path(project_dir)/'.git'/'requirements'/f'{sanitize(branch)}.json'` using the same sanitizer `derive_phase`/`state_storage` already uses.

**Step 4: Run to verify it passes**

Run: `uv run python hooks/test_requirements.py 2>&1 | grep -i "phase nudge"`
Expected: PASS.

**Step 5: Commit**

```bash
stg new prompt-submit-phase-nudge -m "feat(hooks): prompt-submit nudges the current phase's skill (full-workflow chain)"
stg refresh
```

---

## Task 6: Soft `implement` marker

**Files:**
- Modify: `hooks/auto-satisfy-skills.py` — add mapping in `DEFAULT_SKILL_MAPPINGS` (~line 46).
- Modify: `.claude/requirements.local.yaml` — add `implementation_done` requirement + set `implement.gate`.
- Test: `hooks/test_requirements.py` — `test_implement_marker_mapping(runner)`.

**Step 1: Write the failing test**

```python
def test_implement_marker_mapping(runner):
    from importlib import import_module
    mod = import_module("auto-satisfy-skills".replace("-", "_"))  # or load by path
    m = mod.DEFAULT_SKILL_MAPPINGS
    runner.test("execute-plan flips implementation_done",
                m.get("requirements-framework:execute-plan") == "implementation_done"
                or "implementation_done" in (m.get("requirements-framework:executing-plans") or []))
```

(If the module can't be imported by name due to the hyphen, load via `importlib.util.spec_from_file_location` on `hooks/auto-satisfy-skills.py` — mirror however existing tests load hyphenated hook modules.)

**Step 2: Run to verify it fails**

Expected: FAIL — no such mapping.

**Step 3: Minimal implementation**

In `DEFAULT_SKILL_MAPPINGS`:

```python
    'requirements-framework:execute-plan': 'implementation_done',
    'requirements-framework:executing-plans': 'implementation_done',
```

In `.claude/requirements.local.yaml`, add under `requirements:`:

```yaml
  implementation_done:
    enabled: true
    type: blocking          # marker only; nudge mode never blocks on it
    scope: session
    trigger_tools: [Edit, Write, MultiEdit]
    auto_resolve_skill: "requirements-framework:execute-plan"
    satisfied_by_skill: "requirements-framework:execute-plan"
```

And change the workflow `implement` phase gate:

```yaml
    - { name: implement, gate: implementation_done, skill: "requirements-framework:executing-plans" }
```

**Step 4: Run to verify it passes**

Run: `uv run python hooks/test_requirements.py 2>&1 | grep -i "implementation_done"`
Expected: PASS.

**Step 5: Commit**

```bash
stg new implement-marker -m "feat(workflow): soft implement marker so nudge chain covers implementation"
stg refresh
```

---

## Task 7: Opt the project into nudge mode

**Files:**
- Modify: `.claude/requirements.local.yaml` — add top-level `enforcement: nudge`.

**Step 1–4:** Config-only; no unit test (behavior covered by Tasks 2/3). Verify by inspection:

```yaml
enabled: true
version: '1.0'
enforcement: nudge
strict_preflight: true
```

Manual smoke after deploy + relaunch: on `master`, an Edit is allowed (advisory shown once); Stop is not blocked; each phase nudges its skill once.

**Step 5: Commit**

```bash
stg new opt-into-nudge -m "chore(config): opt this project into enforcement: nudge"
stg refresh
```

---

## Task 8: Full verification + deploy + plugin bump

**Files:**
- Modify: `plugins/requirements-framework/.claude-plugin/plugin.json` — minor version bump (new feature).

**Steps:**
1. `uv run python hooks/test_requirements.py` — expect green baseline + all new tests passing (ignore the 7 known pre-existing failures).
2. `uv run ruff check .` — must pass (CI runs pinned ruff; local TestRunner does not lint).
3. Bump plugin version (minor). Run `./update-plugin-versions.sh` to refresh `git_hash` fields; keep that churn in its own chore patch.
4. `./sync.sh status` then `./sync.sh deploy`.
5. Relaunch: `claude --plugin-dir ~/Tools/claude-requirements-framework/plugin` and smoke-test the live nudge chain.

**Commit:**

```bash
stg new plugin-bump-nudge-only -m "chore(plugin): bump version for nudge-only workflow"
stg refresh
```

---

## Notes / risks

- **Marker proliferation:** phase markers accumulate in `.git/requirements/` like the existing `.brainstorm-nudge-*`. Acceptable (they're empty files); a future cleanup could sweep them at SessionEnd.
- **Double-surfacing:** proactive phase nudge (prompt-submit) + reactive advisory (PreToolUse) can both mention the same skill in one turn. Per-phase dedup on each keeps it to at most one of each; tune if noisy.
- **Backward-compat:** every change is gated on `enforcement == "nudge"`; the global default stays `block`, so other projects are byte-for-byte unaffected. No deprecated aliases (per project convention).
- **Phase re-cut (Approach B)** remains deferred — see `project-phase-recut-backlog` memory and design doc's Deferred section. Do NOT start it here.
