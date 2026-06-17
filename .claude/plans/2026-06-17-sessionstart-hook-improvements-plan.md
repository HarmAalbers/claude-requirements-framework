# SessionStart Hook Improvements Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use requirements-framework:executing-plans to implement this plan task-by-task.

**Goal:** Make the SessionStart briefing pause-aware (no false "blocked" nag when gates are suppressed), refactor pure side-effects into a best-effort runner, and add a total-failure fallback so a render error degrades to a breadcrumb instead of silence.

**Architecture:** Three independent edits to `hooks/handle-session-start.py`. (#1) Thread a `paused: bool` flag through the format functions; compute it once early in `main()` and skip the strict-preflight block when paused. (#2) Extract the three pure fire-and-forget side-effects (metrics, project-registry, Obsidian) into module-level functions run via a `_best_effort` helper. (#3) Wrap the silent status-format `except` with a fallback line.

**Tech Stack:** Python 3 stdlib, custom `TestRunner` in `hooks/test_requirements.py` (NOT unittest), `stg` for commits, `./sync.sh deploy` to push repo → `~/.claude/hooks`.

**Design doc:** `.claude/plans/2026-06-17-sessionstart-hook-improvements-design.md`

**Conventions (from project memory):**
- Tests use a custom `TestRunner`; register new test functions in `main()` (~line 13093).
- After editing hook code, run `./sync.sh deploy` before running the deployed test suite.
- Plugin change → bump `plugins/requirements-framework/.claude-plugin/plugin.json` version (4.21.0 → 4.22.0) **in the same patch**.
- Use `stg new` / `stg refresh` — never `git commit`. One logical change per patch.

---

## Task 1: Pause-aware format functions (#1)

**Files:**
- Modify: `hooks/handle-session-start.py` — `format_compact_status`, `format_standard_status`, `format_adaptive_status`
- Test: `hooks/test_requirements.py` — new `test_session_start_pause_aware(runner)`

**Step 1: Write the failing test**

Add near the other session-start tests (after `test_session_start_format_tiers`, ~line 7528). Mirror its setup (git init, two unsatisfied requirements, `RequirementsConfig`, `BranchRequirements`). Then:

```python
def test_session_start_pause_aware(runner: TestRunner):
    """Paused sessions show status but omit the 'edits blocked' gating directive."""
    print("\n📦 Testing pause-aware session-start briefing...")
    import importlib.util
    sys.path.insert(0, str(Path(__file__).parent / 'lib'))
    hook_path = Path(__file__).parent / "handle-session-start.py"
    spec = importlib.util.spec_from_file_location("session_start_hook_pause", hook_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    from config import RequirementsConfig
    from requirements import BranchRequirements

    with tempfile.TemporaryDirectory() as tmpdir:
        subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "checkout", "-b", "feature/pause-test"], cwd=tmpdir, capture_output=True)
        os.makedirs(f"{tmpdir}/.claude")
        cfg = {"version": "1.0", "enabled": True, "inherit": False, "requirements": {
            "commit_plan": {"enabled": True, "type": "blocking", "scope": "session",
                            "auto_resolve_skill": "requirements-framework:arch-review"}}}
        with open(f"{tmpdir}/.claude/requirements.yaml", 'w') as f:
            json.dump(cfg, f)
        config = RequirementsConfig(tmpdir)
        reqs = BranchRequirements("feature/pause-test", "s1", tmpdir)

        # NOT paused -> directive present (regression guard)
        active = mod.format_compact_status(reqs, config, "s1", "feature/pause-test", paused=False)
        runner.test("Unpaused compact keeps gating directive",
                    "do NOT attempt Edit/Write/MultiEdit first" in active, f"Got: {active[:300]}")

        # Paused -> status present, directive gone
        paused = mod.format_compact_status(reqs, config, "s1", "feature/pause-test", paused=True)
        runner.test("Paused compact still shows requirement status",
                    "Requirements:" in paused, f"Got: {paused[:300]}")
        runner.test("Paused compact omits gating directive",
                    "do NOT attempt Edit/Write/MultiEdit first" not in paused, f"Got: {paused[:300]}")

        # Same for standard
        std_paused = mod.format_standard_status(reqs, config, "s1", "feature/pause-test", paused=True)
        runner.test("Paused standard omits gating directive",
                    "do NOT attempt Edit/Write/MultiEdit first" not in std_paused, f"Got: {std_paused[:400]}")
```

Register it in `main()` right after the `test_session_start_format_tiers(runner)` line (~13244):

```python
    test_session_start_pause_aware(runner)
```

**Step 2: Run to verify it fails**

Run: `./sync.sh deploy && python3 ~/.claude/hooks/test_requirements.py 2>&1 | grep -A2 pause-aware`
Expected: FAIL — `format_compact_status() got an unexpected keyword argument 'paused'`.

**Step 3: Implement**

In `hooks/handle-session-start.py`:

- `format_compact_status(reqs, config, session_id, branch, paused: bool = False)` — change the unsatisfied-block tail so the `_GATING_DIRECTIVE` line is appended only when `not paused`:

```python
    if unsatisfied:
        lines.append(f"**Fallback**: `req satisfy {' '.join(r['name'] for r in unsatisfied)} --session {session_id}`")
        if not paused:
            lines.append(_GATING_DIRECTIVE)
```

- `format_standard_status(reqs, config, session_id, branch, paused: bool = False)` — same: gate the `_GATING_DIRECTIVE` append behind `if not paused:` (the `unsatisfied_reqs` block near the end).

- `format_adaptive_status(reqs, config, session_id, branch, source, paused: bool = False)` — accept `paused` and forward it to both `format_standard_status(...)` and `format_compact_status(...)` calls.

**Step 4: Run to verify it passes**

Run: `./sync.sh deploy && python3 ~/.claude/hooks/test_requirements.py 2>&1 | grep -E "pause-aware|Paused|Unpaused"`
Expected: all four new assertions PASS.

**Step 5: Commit**

```bash
stg new -m "feat(session-start): pause-aware briefing — omit gating directive when paused" pause-aware-format
stg refresh
```

---

## Task 2: Wire pause flag + skip preflight in main() (#1 cont.)

**Files:**
- Modify: `hooks/handle-session-start.py` — `main()`
- Test: covered by Task 1 at the format layer; the `main()` wiring is verified by the existing subprocess `test_session_start_hook` (smoke — must still pass).

**Step 1: Implement — compute pause once, early**

After the `if not config.is_enabled(): return 0` check (~line 487), compute the flag once (fail-open already built into `is_paused`):

```python
        # Pause state (gates suppressed): drives a pause-aware briefing below.
        try:
            from pause import is_paused as _is_paused
            session_paused = _is_paused(session_id, project_dir)
        except Exception:
            session_paused = False
```

**Step 2: Forward to status**

At the `format_adaptive_status(...)` call (~line 667), pass `paused=session_paused`:

```python
                status = format_adaptive_status(reqs, config, session_id, branch, source, paused=session_paused)
```

**Step 3: Skip strict-preflight nag when paused**

Wrap the strict-preflight block (~lines 685–695) so it is skipped when paused (the gate it warns about is suppressed, so the warning is misleading):

```python
        # --- strict preflight: loud non-compliance briefing (fail-open) ---
        if not session_paused:
            try:
                from preflight import evaluate, format_strict_warning
                ...
            except Exception as e:
                logger.debug("strict preflight briefing skipped", error=str(e))
```

**Step 4: Run the full suite to verify no regression**

Run: `./sync.sh deploy && python3 ~/.claude/hooks/test_requirements.py 2>&1 | tail -5`
Expected: `Results: N/N tests passed`, no failures.

**Step 5: Commit**

```bash
stg new -m "feat(session-start): wire pause flag into main(); skip preflight nag when paused" pause-aware-main
stg refresh
```

---

## Task 3: Best-effort side-effect runner (#2)

**Files:**
- Modify: `hooks/handle-session-start.py` — add `_best_effort` helper + three module-level functions; replace inline blocks 2a (metrics), 2b (project-registry), 2e (Obsidian)
- Test: `hooks/test_requirements.py` — new `test_best_effort_runner(runner)`

> Only the **pure fire-and-forget** blocks move. Blocks that produce context (WIP `wip_summary`, other-sessions warning, retrieval `retrieval_block`, carry-over) stay inline — extracting them would only add plumbing.

**Step 1: Write the failing test**

```python
def test_best_effort_runner(runner: TestRunner):
    """_best_effort swallows exceptions and never raises."""
    print("\n📦 Testing _best_effort runner...")
    import importlib.util
    hook_path = Path(__file__).parent / "handle-session-start.py"
    spec = importlib.util.spec_from_file_location("session_start_hook_be", hook_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    from logger import get_logger
    log = get_logger(base_context={"hook": "test"})

    calls = []
    mod._best_effort("ok-step", lambda: calls.append("ran"), log)
    runner.test("_best_effort runs the callable", calls == ["ran"], f"Got: {calls}")

    def boom():
        raise RuntimeError("kaboom")
    raised = False
    try:
        mod._best_effort("bad-step", boom, log)
    except Exception:
        raised = True
    runner.test("_best_effort swallows exceptions", not raised, "Should not have raised")
```

Register in `main()` after `test_session_start_pause_aware(runner)`.

**Step 2: Run to verify it fails**

Run: `./sync.sh deploy && python3 ~/.claude/hooks/test_requirements.py 2>&1 | grep -E "_best_effort"`
Expected: FAIL — `module ... has no attribute '_best_effort'`.

**Step 3: Implement**

Add near the top-level helpers (after `_GATING_DIRECTIVE`):

```python
def _best_effort(label: str, fn, logger) -> None:
    """Run an opportunistic side-effect; never let it break session start."""
    try:
        fn()
    except Exception as e:
        logger.debug(f"{label} failed (fail-open)", error=str(e))
```

Extract the three pure blocks into module-level functions taking the values they need, e.g.:

```python
def _init_session_metrics(session_id, project_dir, branch, logger):
    from session_metrics import SessionMetrics
    SessionMetrics(session_id, project_dir, branch).save()
    logger.debug("Session metrics initialized")

def _register_project(config, project_dir, logger):
    from project_registry import ProjectRegistry
    from feature_catalog import detect_configured_features
    raw = config.get_raw_config()
    features = detect_configured_features(raw)
    ProjectRegistry().register_project(
        project_dir, [f for f, e in features.items() if e], raw.get("inherit", False))
    logger.debug("Project registered in upgrade registry")

def _log_obsidian_start(config, session_id, project_dir, branch, logger):
    if not config.get_hook_config('obsidian', 'enabled', False):
        return
    from obsidian import ObsidianSessionLogger
    ObsidianSessionLogger(config).on_session_start(session_id, project_dir, branch)
    logger.debug("Obsidian session note created")
```

In `main()`, replace the three inline `try/except` blocks (2a, 2b, 2e) with:

```python
        _best_effort("session metrics", lambda: _init_session_metrics(session_id, project_dir, branch, logger), logger)
        _best_effort("project registry", lambda: _register_project(config, project_dir, logger), logger)
        _best_effort("obsidian session note", lambda: _log_obsidian_start(config, session_id, project_dir, branch, logger), logger)
```

> Behavior parity: the originals logged at `warning` (metrics) / `debug` (registry, obsidian). `_best_effort` logs uniformly at `debug` — acceptable per design (these are best-effort). Note this in the commit body.

**Step 4: Run the full suite**

Run: `./sync.sh deploy && python3 ~/.claude/hooks/test_requirements.py 2>&1 | tail -5`
Expected: all pass, including the existing `test_session_start_hook` smoke.

**Step 5: Commit**

```bash
stg new -m "refactor(session-start): extract pure side-effects into _best_effort runner" best-effort-runner
stg refresh
```

---

## Task 4: Total-failure fallback (#3)

**Files:**
- Modify: `hooks/handle-session-start.py` — the `except` around `format_adaptive_status` (~lines 669–670)
- Test: `hooks/test_requirements.py` — extend `test_session_start_pause_aware` or add a focused assertion via monkeypatching `format_adaptive_status` to raise.

**Step 1: Write the failing test**

Add a small test that forces the formatter to raise and checks the fallback string is emitted. Simplest: unit-test the fallback constant by asserting the `except` appends it. Since the `except` is inside `main()`, test via monkeypatch:

```python
def test_session_start_fallback_on_format_error(runner: TestRunner):
    """A status-render exception degrades to a visible fallback line, not silence."""
    print("\n📦 Testing session-start total-failure fallback...")
    import importlib.util
    hook_path = Path(__file__).parent / "handle-session-start.py"
    spec = importlib.util.spec_from_file_location("session_start_hook_fb", hook_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    runner.test("Fallback constant defined", hasattr(mod, "_BRIEFING_FALLBACK"),
                "Expected module-level _BRIEFING_FALLBACK")
    runner.test("Fallback mentions req status",
                "req status" in getattr(mod, "_BRIEFING_FALLBACK", ""),
                f"Got: {getattr(mod, '_BRIEFING_FALLBACK', None)}")
```

Register in `main()`.

**Step 2: Run to verify it fails**

Run: `./sync.sh deploy && python3 ~/.claude/hooks/test_requirements.py 2>&1 | grep -E "Fallback"`
Expected: FAIL — no `_BRIEFING_FALLBACK`.

**Step 3: Implement**

Add the constant near `_GATING_DIRECTIVE`:

```python
_BRIEFING_FALLBACK = (
    "## Requirements Framework active — run `req status` for details "
    "(briefing failed to render)."
)
```

In `main()`, change the status `except` to append the fallback to `parts`:

```python
            except Exception as e:
                logger.error("Failed to format status", error=str(e))
                parts.append(_BRIEFING_FALLBACK)
```

**Step 4: Run the full suite**

Run: `./sync.sh deploy && python3 ~/.claude/hooks/test_requirements.py 2>&1 | tail -5`
Expected: all pass.

**Step 5: Commit (with version bump)**

```bash
# Bump plugin.json 4.21.0 -> 4.22.0 in this same patch (hooks change)
stg new -m "feat(session-start): visible fallback when briefing render fails; bump plugin 4.22.0" briefing-fallback
stg refresh
```

---

## Task 5: Final verification

**Step 1:** `./sync.sh status` — confirm repo and `~/.claude/hooks` are in sync.

**Step 2:** `python3 hooks/test_requirements.py 2>&1 | tail -5` — full suite green from the repo copy.

**Step 3:** `stg series` — confirm four atomic patches (design-note already landed separately): `pause-aware-format`, `pause-aware-main`, `best-effort-runner`, `briefing-fallback`.

**Step 4:** `./update-plugin-versions.sh` if any plugin component git_hash needs refreshing (hooks aren't plugin components, but run `--check` to be safe), in its own chore patch if it produces churn.

**Step 5:** Review pipeline: `/pre-commit` (code + error handling) then optionally `/deep-review` before merge.

---

## Out of scope (deferred)
- Single-hook multi-host output (Codex/Copilot/Claude) — roadmap B1.
- Statusline-missing nudge — low value.
