# `/req-pause` + `/req-resume` Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use requirements-framework:executing-plans to implement this plan task-by-task.

**Goal:** Add `/req-pause` + `/req-resume` slash commands that suppress the framework's *blocking* gates for a single session, auto-clearing at SessionEnd, while leaving nudges/status and strict-preflight intact.

**Architecture:** A session-keyed marker file `.git/requirements/sessions/<session_id>.paused` (Approach A). A new fail-open `lib/pause.py` owns read/write/clear/banner. Only the two blocking hooks (`check-requirements.py` PreToolUse, `handle-stop.py` Stop) honor it; SessionEnd clears it; the two status injectors show a visible paused banner. CLI `req pause`/`req resume` are the primitives the slash commands wrap.

**Tech Stack:** Python 3 stdlib, PyYAML (config), stg (Stacked Git), existing framework hook/lib modules.

**Approved design:** `.claude/plans/2026-06-13-req-pause-session-disable-design.md`

---

## Conventions for the executor

- **Version control = Stacked Git.** New branch first: `git checkout -b feat/req-pause-session && stg init`. Each "Commit" step = `stg new <name>` (write description) then `stg refresh` as you iterate. **Never `git commit`.**
- **Test harness (IMPORTANT — NOT unittest):** `hooks/test_requirements.py` uses a custom `TestRunner`. Tests are module-level functions `def test_x(runner: TestRunner):` that call `runner.test(name, condition, msg)`, and are executed by being **called explicitly inside `main()`** (just before `return runner.summary()`). There is no `unittest.TestCase` auto-discovery — a `TestCase` subclass would never run. Add your test function AND register it in `main()`.
  - **Lib tests:** import the lib module directly (`import pause`) inside the test fn; use `tempfile.TemporaryDirectory()` + `subprocess.run(['git','init'], cwd=tmp, capture_output=True)` for a scratch repo (model: `test_state_storage_module`).
  - **Hook tests:** hook files are hyphenated and NOT importable — invoke them as subprocesses with JSON on stdin and assert on `result.stdout` / `result.returncode` (model: the `handle-stop.py` test at ~line 2512). Use explicit `session_id` like `"test1234"` and `BranchRequirements(...).mark_triggered(...)` to set up state.
  - Run the whole script: `python3 hooks/test_requirements.py` and read the final `Results: N/M tests passed` line.
- **Plugin bundle sync (use the build script — NOT manual cp):** the bundle `plugins/requirements-framework/hooks/` is a build-copy of repo `hooks/` produced by `python3 scripts/build_plugin_hooks.py`. After editing ANY repo `hooks/**` file (including `requirements-cli.py`, which IS bundled — the earlier "repo-only" note was WRONG), run `python3 scripts/build_plugin_hooks.py` then `python3 scripts/build_plugin_hooks.py --check` (must print "Bundle in sync"). The suite's `test_plugin_hooks_bundle_fresh` fails on drift. `hooks/test_requirements.py` is repo-only (not bundled). Include the regenerated bundle file(s) in the same stg patch.
- **Version bump:** bump `plugins/requirements-framework/.claude-plugin/plugin.json` (minor) in the patch that adds the slash commands.
- **Fail-open is mandatory** in all hook/lib code: any exception ⇒ behave as "not paused"; never raise inside a hook.

---

## Task 1: `lib/pause.py` — marker helper (TDD)

**Files:**
- Create: `hooks/lib/pause.py`
- Test: `hooks/test_requirements.py` (append a `TestSessionPause` class)
- Mirror: `plugins/requirements-framework/hooks/lib/pause.py`

**Step 1: Write the failing test (TestRunner pattern)**

Append this function to `hooks/test_requirements.py`, then register it in `main()` (add `test_session_pause(runner)` just before `return runner.summary()`):

```python
def test_session_pause(runner: TestRunner):
    """Session-scoped pause marker (Approach A)."""
    print("\n⏸  Testing session pause marker...")
    import pause
    from session_metrics import get_sessions_dir, ensure_sessions_dir

    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(['git', 'init'], cwd=tmp, capture_output=True)

        runner.test("not paused initially", pause.is_paused('aaaa1111', tmp) is False)
        pause.set_paused('aaaa1111', tmp, reason='manual')
        runner.test("paused after set", pause.is_paused('aaaa1111', tmp) is True)

        pause.clear_paused('aaaa1111', tmp)
        runner.test("not paused after clear", pause.is_paused('aaaa1111', tmp) is False)

        pause.set_paused('aaaa1111', tmp)
        runner.test("session A paused", pause.is_paused('aaaa1111', tmp) is True)
        runner.test("session B not paused", pause.is_paused('bbbb2222', tmp) is False)

        # presence-based -> a garbled marker still counts as paused, never raises
        ensure_sessions_dir(tmp)
        (get_sessions_dir(tmp) / 'cccc3333.paused').write_text('{not json')
        runner.test("garbled marker still paused", pause.is_paused('cccc3333', tmp) is True)

        runner.test("no project dir -> not paused (fail-open)",
                    pause.is_paused('aaaa1111', None) is False)

        try:
            pause.clear_paused('nonexistent', tmp)
            runner.test("clear idempotent (no raise)", True)
        except Exception as e:
            runner.test("clear idempotent (no raise)", False, str(e))

        runner.test("no banner when not paused", pause.paused_banner('dddd4444', tmp) == "")
        pause.set_paused('dddd4444', tmp)
        runner.test("banner present when paused",
                    "paused" in pause.paused_banner('dddd4444', tmp).lower())
```

> `tempfile`, `subprocess`, `os` are already imported at module top (used throughout). `import pause` works because the suite puts `hooks/lib` on `sys.path`.

**Step 2: Run to verify failure**

Run: `python3 hooks/test_requirements.py 2>&1 | grep -iE "session pause|No module named 'pause'"`
Expected: failure — `ModuleNotFoundError: No module named 'pause'` (or the test fn erroring).

**Step 3: Implement `hooks/lib/pause.py`**

```python
"""
Session-scoped pause marker for the requirements framework.

A pause marker temporarily suppresses BLOCKING gates (PreToolUse edit/bash gate
and the Stop verification gate) for ONE session, without touching nudges, status
injection, or strict-preflight. The marker is a presence-based file keyed by
session id, stored next to per-session metrics:

    <git-common-dir>/requirements/sessions/<session_id>.paused

DESIGN: fail-open everywhere. Any error reading/writing the marker is treated as
"not paused" and never raised — a pause bug must never block work nor crash a hook.
Auto-cleared by handle-session-end.py; manually cleared by `req resume`.
"""
import json
from pathlib import Path

try:
    from .session_metrics import get_sessions_dir, ensure_sessions_dir
except ImportError:
    from session_metrics import get_sessions_dir, ensure_sessions_dir


def marker_path(session_id: str, project_dir) -> Path:
    """Path to the pause marker for *session_id* (no existence guarantee)."""
    return get_sessions_dir(project_dir) / f"{session_id}.paused"


def is_paused(session_id: str, project_dir) -> bool:
    """True if a pause marker exists for this session. Fail-open → False."""
    if not project_dir or not session_id:
        return False
    try:
        return marker_path(session_id, project_dir).exists()
    except Exception:
        return False


def set_paused(session_id: str, project_dir, reason: str = "") -> bool:
    """Create the pause marker. Returns True on success, False on failure."""
    if not project_dir or not session_id:
        return False
    try:
        ensure_sessions_dir(project_dir)
        payload = {"paused_at": _now_iso(), "reason": reason or "manual"}
        marker_path(session_id, project_dir).write_text(json.dumps(payload))
        return True
    except Exception:
        return False


def clear_paused(session_id: str, project_dir) -> bool:
    """Remove the pause marker if present. Idempotent. Fail-open → False."""
    if not project_dir or not session_id:
        return False
    try:
        marker_path(session_id, project_dir).unlink(missing_ok=True)
        return True
    except Exception:
        return False


def paused_banner(session_id: str, project_dir) -> str:
    """A one-line visibility banner when paused, else empty string."""
    if is_paused(session_id, project_dir):
        return ("⏸ Framework paused for this session "
                "— run `/req-resume` to re-enable blocking gates.")
    return ""


def _now_iso() -> str:
    """UTC ISO timestamp. Fail-open → empty string (marker presence is enough)."""
    try:
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()
    except Exception:
        return ""
```

**Step 4: Run to verify pass**

Run: `python3 hooks/test_requirements.py 2>&1 | tail -5`
Expected: OK (all tests pass, including the 7 new ones).

**Step 5: Mirror + commit**

```bash
cp hooks/lib/pause.py plugins/requirements-framework/hooks/lib/pause.py
stg new req-pause-01-lib   # desc: "feat(pause): session-scoped pause marker lib (fail-open)"
stg refresh
```

---

## Task 2: `req pause` / `req resume` CLI subcommands (TDD)

**Files:**
- Modify: `hooks/requirements-cli.py` — add `cmd_pause`, `cmd_resume`; register subparsers near `clear` (line ~3524); add to COMMANDS dict (line ~3714).
- Test: `hooks/test_requirements.py` (new `test_cli_pause_resume(runner)` fn, registered in `main()`)
- (no plugin mirror — CLI is repo-only)

**Step 1: Write the failing test (TestRunner pattern)**

Add this function and register it in `main()`:

```python
def test_cli_pause_resume(runner: TestRunner):
    """`req pause` / `req resume` round-trip the marker for an explicit session."""
    print("\n⏸  Testing req pause/resume CLI...")
    import pause
    cli = os.path.join(os.path.dirname(__file__), 'requirements-cli.py')

    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["git", "init"], cwd=tmp, capture_output=True)
        r = subprocess.run(['python3', cli, 'pause', '--session', 'dddd4444'],
                           cwd=tmp, capture_output=True, text=True)
        runner.test("cli pause rc 0", r.returncode == 0, r.stderr)
        runner.test("cli pause sets marker", pause.is_paused('dddd4444', tmp) is True)

        r = subprocess.run(['python3', cli, 'resume', '--session', 'dddd4444'],
                           cwd=tmp, capture_output=True, text=True)
        runner.test("cli resume rc 0", r.returncode == 0, r.stderr)
        runner.test("cli resume clears marker", pause.is_paused('dddd4444', tmp) is False)
```

**Step 2: Run to verify failure**

Run: `python3 hooks/test_requirements.py 2>&1 | grep -iE "req pause/resume|cli pause"`
Expected: FAIL — `invalid choice: 'pause'`.

**Step 3: Implement**

Add command functions (near `cmd_clear`, before `main()`):

```python
def _resolve_pause_session(args) -> str | None:
    """Explicit --session, else registry auto-detect. None on failure."""
    if getattr(args, 'session', None):
        return args.session
    try:
        return get_session_id()
    except SessionNotFoundError:
        return None


def cmd_pause(args) -> int:
    """Pause blocking gates for the current session (does NOT bypass strict)."""
    import pause as pause_lib
    project_dir = get_project_dir()
    if not is_git_repo(project_dir):
        out(error("❌ Not in a git repository"), file=sys.stderr)
        return 1
    session_id = _resolve_pause_session(args)
    if not session_id:
        out(error("❌ No session detected. Pass --session <id>."), file=sys.stderr)
        return 1
    if pause_lib.set_paused(session_id, project_dir, reason=getattr(args, 'reason', '') or ''):
        out(success(f"⏸ Framework paused for session {session_id}."))
        out(dim("   Blocking gates are off for this session. Run `req resume` (or /req-resume) to re-enable."))
        out(dim("   Note: strict-preflight is NOT bypassed; use RF_STRICT_OFF for that."))
        return 0
    out(error("❌ Could not write pause marker"), file=sys.stderr)
    return 1


def cmd_resume(args) -> int:
    """Resume (clear pause) for the current session."""
    import pause as pause_lib
    project_dir = get_project_dir()
    if not is_git_repo(project_dir):
        out(error("❌ Not in a git repository"), file=sys.stderr)
        return 1
    session_id = _resolve_pause_session(args)
    if not session_id:
        out(error("❌ No session detected. Pass --session <id>."), file=sys.stderr)
        return 1
    pause_lib.clear_paused(session_id, project_dir)
    out(success(f"▶ Framework resumed for session {session_id}."))
    return 0
```

Register subparsers (after the `clear` parser block, ~line 3528):

```python
    pause_parser = subparsers.add_parser('pause', help='Pause blocking gates for this session')
    pause_parser.add_argument('--session', '-s', metavar='ID', help='Explicit session ID (8 chars)')
    pause_parser.add_argument('--reason', '-r', help='Optional reason note')

    resume_parser = subparsers.add_parser('resume', help='Resume blocking gates for this session')
    resume_parser.add_argument('--session', '-s', metavar='ID', help='Explicit session ID (8 chars)')
```

Add to the COMMANDS dispatch dict (~line 3714):

```python
        'pause': cmd_pause,
        'resume': cmd_resume,
```

> Also add `pause,resume` to the top-level usage/help epilog if it enumerates commands.

**Step 4: Run to verify pass**

Run: `python3 hooks/test_requirements.py 2>&1 | tail -5`
Expected: OK.

**Step 5: Commit**

```bash
stg new req-pause-02-cli   # desc: "feat(pause): req pause/resume CLI subcommands"
stg refresh
```

---

## Task 3: Honor pause in PreToolUse gate + self-unblock (TDD)

**Files:**
- Modify: `hooks/check-requirements.py` — insert after `is_enabled()` check (line 382-384), before requirement manager init (line 386). Plus a self-allow for the `req pause`/`req resume` Bash invocation after the strict gate (after line ~298, the `strict_preflight_block` return).
- Mirror: `plugins/requirements-framework/hooks/check-requirements.py`
- Test: `hooks/test_requirements.py`

**Step 1: Write the failing test (subprocess pattern — model the `handle-stop.py` test ~line 2512)**

Add this function and register it in `main()`:

```python
def test_pretooluse_pause(runner: TestRunner):
    """PreToolUse gate: paused session allows otherwise-blocking edits;
    the req pause command itself is never blocked."""
    print("\n⏸  Testing PreToolUse pause short-circuit...")
    import pause
    hook_path = Path(__file__).parent / "check-requirements.py"
    if not hook_path.exists():
        runner.test("check-requirements.py exists", False, "missing")
        return

    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["git", "init"], cwd=tmp, capture_output=True)
        subprocess.run(["git", "checkout", "-b", "feature/test"], cwd=tmp, capture_output=True)
        os.makedirs(f"{tmp}/.claude")
        config = {
            "version": "1.0", "enabled": True, "inherit": False,
            "requirements": {
                "commit_plan": {"enabled": True, "type": "blocking",
                                "scope": "session", "trigger_tools": ["Edit", "Write"],
                                "message": "Plan!"}
            },
        }
        with open(f"{tmp}/.claude/requirements.yaml", "w") as f:
            json.dump(config, f)

        sid = "test1234"
        edit_input = json.dumps({
            "session_id": sid, "tool_name": "Edit",
            "tool_input": {"file_path": f"{tmp}/src.py"},
        })

        # Baseline: unsatisfied + not paused -> BLOCKS
        r = subprocess.run(["python3", str(hook_path)], input=edit_input,
                           cwd=tmp, capture_output=True, text=True)
        runner.test("blocks edit when unsatisfied (baseline)",
                    '"decision"' in r.stdout and "block" in r.stdout, f"Got: {r.stdout}")

        # Paused -> edit ALLOWED (no block emitted, rc 0)
        pause.set_paused(sid, tmp)
        r = subprocess.run(["python3", str(hook_path)], input=edit_input,
                           cwd=tmp, capture_output=True, text=True)
        runner.test("paused allows otherwise-blocking edit",
                    r.returncode == 0 and "block" not in r.stdout, f"Got: {r.stdout}")
        pause.clear_paused(sid, tmp)

        # Self-unblock: `req pause` Bash command is never blocked even when unsatisfied
        bash_input = json.dumps({
            "session_id": sid, "tool_name": "Bash",
            "tool_input": {"command": "req pause --session test1234"},
        })
        r = subprocess.run(["python3", str(hook_path)], input=bash_input,
                           cwd=tmp, capture_output=True, text=True)
        runner.test("req pause command self-allowed",
                    r.returncode == 0 and "block" not in r.stdout, f"Got: {r.stdout}")
```

> Note: this exercises behavior end-to-end through the hook, so it also verifies ordering (self-allow after strict gate; pause short-circuit before the requirement loop). No need to import the hyphenated hook module. If you also want a focused unit check of `is_pause_command`, load it via `importlib.util.spec_from_file_location("check_requirements", hook_path)` — but the subprocess test above is sufficient and is the suite convention.

**Step 2: Run to verify failure**

Run: `python3 hooks/test_requirements.py 2>&1 | grep -iE "PreToolUse pause|paused allows|self-allowed"`
Expected: the "paused allows…" and "self-allowed" assertions FAIL (gate not yet implemented).

**Step 3: Implement**

Add a module-level helper near `should_skip_plan_file` in `check-requirements.py`:

```python
import re as _re
_PAUSE_CMD_RE = _re.compile(
    r'\b(?:req|requirements-cli\.py)\s+(?:pause|resume)\b'
)

def is_pause_command(command: str) -> bool:
    """True if *command* is an exact req pause/resume CLI invocation.

    Tight match so the pause command can never be blocked by the gate it is
    about to disable. Mirrors the strict escape-hatch philosophy.
    """
    if not command:
        return False
    return bool(_PAUSE_CMD_RE.search(command))
```

Self-allow, immediately AFTER the strict-preflight block (after line ~298, before `update_registry`):

```python
        # Self-unblock: never block the pause/resume command itself.
        if tool_name == 'Bash':
            if is_pause_command((tool_input or {}).get('command', '') or ''):
                logger.info("Allowing pause/resume command (self-unblock)")
                return 0
```

Pause short-circuit, AFTER `is_enabled()` (after line 384), BEFORE the requirement manager (line 386):

```python
        # Session pause: suppress BLOCKING gates only (strict gate already ran
        # above and still blocks; nudges/status live in other hooks).
        try:
            from pause import is_paused
            if is_paused(session_id, project_dir):
                logger.info("Requirements paused for session", session=session_id)
                return 0
        except Exception as e:
            logger.debug("pause check failed (fail-open)", error=str(e))
```

**Step 4: Run to verify pass**

Run: `python3 hooks/test_requirements.py 2>&1 | tail -5`
Expected: OK.

**Step 5: Mirror + commit**

```bash
cp hooks/check-requirements.py plugins/requirements-framework/hooks/check-requirements.py
stg new req-pause-03-pretooluse   # desc: "feat(pause): honor pause + self-unblock in PreToolUse gate"
stg refresh
```

---

## Task 4: Honor pause in Stop gate (TDD)

**Files:**
- Modify: `hooks/handle-stop.py` — after `is_enabled()` (line 188-189) and the `verify_requirements` config check (line 192-194), before building `reqs`/`unsatisfied` (line 200). Insert pause check.
- Mirror: `plugins/requirements-framework/hooks/handle-stop.py`
- Test: `hooks/test_requirements.py`

**Step 1: Write the failing test (subprocess pattern — mirror the existing `handle-stop.py` test ~line 2512)**

Add this function and register it in `main()`:

```python
def test_stop_pause(runner: TestRunner):
    """Stop gate: a paused session is not blocked even with an unsatisfied
    triggered requirement."""
    print("\n⏸  Testing Stop pause skip...")
    import pause
    from requirements import BranchRequirements
    hook_path = Path(__file__).parent / "handle-stop.py"
    if not hook_path.exists():
        runner.test("handle-stop.py exists", False, "missing")
        return

    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["git", "init"], cwd=tmp, capture_output=True)
        subprocess.run(["git", "checkout", "-b", "feature/test"], cwd=tmp, capture_output=True)
        os.makedirs(f"{tmp}/.claude")
        config = {
            "version": "1.0", "enabled": True, "inherit": False,
            "hooks": {"stop": {"verify_requirements": True}},
            "requirements": {
                "commit_plan": {"enabled": True, "scope": "session", "message": "Plan!"}
            },
        }
        with open(f"{tmp}/.claude/requirements.yaml", "w") as f:
            json.dump(config, f)

        sid = "test1234"
        BranchRequirements("feature/test", sid, tmp).mark_triggered("commit_plan", "session")
        stop_input = json.dumps({"hook_event_name": "Stop", "stop_hook_active": False,
                                 "session_id": sid})

        # Baseline: unsatisfied triggered req -> Stop BLOCKS
        r = subprocess.run(["python3", str(hook_path)], input=stop_input,
                           cwd=tmp, capture_output=True, text=True)
        runner.test("stop blocks when unsatisfied (baseline)",
                    '"decision": "block"' in r.stdout, f"Got: {r.stdout}")

        # Paused -> Stop does NOT block
        pause.set_paused(sid, tmp)
        r = subprocess.run(["python3", str(hook_path)], input=stop_input,
                           cwd=tmp, capture_output=True, text=True)
        runner.test("paused -> stop not blocked",
                    r.returncode == 0 and '"decision": "block"' not in r.stdout,
                    f"Got: {r.stdout}")
```

**Step 2: Run to verify failure** — the "paused -> stop not blocked" assertion FAILS before the guard exists.

**Step 3: Implement** — insert after line 194 (`verify_requirements` early return), before line 196:

```python
        # Session pause: do not block stop when paused (blocking gate).
        try:
            from pause import is_paused
            if is_paused(session_id, project_dir):
                logger.info("Stop not blocked - session paused", session=session_id)
                return 0
        except Exception as e:
            logger.debug("pause check failed in stop (fail-open)", error=str(e))
```

**Step 4: Run to verify pass** — OK.

**Step 5: Mirror + commit**

```bash
cp hooks/handle-stop.py plugins/requirements-framework/hooks/handle-stop.py
stg new req-pause-04-stop   # desc: "feat(pause): do not block Stop when session paused"
stg refresh
```

---

## Task 5: Auto-clear at SessionEnd (TDD)

**Files:**
- Modify: `hooks/handle-session-end.py` — inside the `try:` cleanup (after the `CLAUDE_SKIP_REQUIREMENTS` early return, near line 70-80), call `clear_paused`.
- Mirror: `plugins/requirements-framework/hooks/handle-session-end.py`
- Test: `hooks/test_requirements.py`

**Step 1: Write the failing test (subprocess pattern)**

Add this function and register it in `main()`:

```python
def test_session_end_clears_pause(runner: TestRunner):
    """SessionEnd auto-clears the pause marker."""
    print("\n⏸  Testing SessionEnd auto-clear...")
    import pause
    hook_path = Path(__file__).parent / "handle-session-end.py"
    if not hook_path.exists():
        runner.test("handle-session-end.py exists", False, "missing")
        return

    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["git", "init"], cwd=tmp, capture_output=True)
        subprocess.run(["git", "checkout", "-b", "feature/test"], cwd=tmp, capture_output=True)
        os.makedirs(f"{tmp}/.claude")
        with open(f"{tmp}/.claude/requirements.yaml", "w") as f:
            json.dump({"version": "1.0", "enabled": True, "inherit": False,
                       "requirements": {}}, f)

        sid = "test1234"
        pause.set_paused(sid, tmp)
        runner.test("paused before session end", pause.is_paused(sid, tmp) is True)

        end_input = json.dumps({"session_id": sid, "hook_event_name": "SessionEnd",
                                "reason": "clear", "cwd": tmp})
        subprocess.run(["python3", str(hook_path)], input=end_input,
                       cwd=tmp, capture_output=True, text=True)
        runner.test("marker cleared after session end", pause.is_paused(sid, tmp) is False)
```

**Step 2: Run to verify failure** — "marker cleared after session end" FAILS before the cleanup is added.

**Step 3: Implement** — in `handle-session-end.py`, within the main `try:` after project_dir is known:

```python
        # Clear any session pause marker (auto-resume on session end).
        try:
            from pause import clear_paused
            clear_paused(session_id, project_dir)
        except Exception:
            pass  # fail-open: cleanup must never crash session end
```

**Step 4: Run to verify pass** — OK.

**Step 5: Mirror + commit**

```bash
cp hooks/handle-session-end.py plugins/requirements-framework/hooks/handle-session-end.py
stg new req-pause-05-sessionend   # desc: "feat(pause): auto-clear pause marker at SessionEnd"
stg refresh
```

---

## Task 6: Visibility banner in status injectors

**Files:**
- Modify: `hooks/handle-session-start.py` — prepend `paused_banner(...)` to the emitted briefing context.
- Modify: `hooks/handle-prompt-submit.py` — prepend `paused_banner(...)` to emitted context (so it shows even when paused).
- Mirror: both plugin copies.
- Test: light — assert `paused_banner` already covered in Task 1; add one integration assertion if the suite drives these hooks.

**Step 1–2 (TDD optional here):** the core behavior (`paused_banner`) is already tested. Add an integration test only if the suite already drives these two hooks' `main()`.

**Step 3: Implement**

In `handle-session-start.py`, where the briefing string is assembled before `emit_hook_context(...)`, prepend:

```python
        try:
            from pause import paused_banner
            _banner = paused_banner(session_id, project_dir)
        except Exception:
            _banner = ""
        if _banner:
            briefing = _banner + "\n\n" + briefing   # adapt var name to local
```

In `handle-prompt-submit.py`, in `main()` after `project_dir`/`session_id` resolved and before/with the context emit, prepend the same banner to whatever context string is emitted (guard so an empty banner changes nothing).

**Step 4: Run** `python3 hooks/test_requirements.py 2>&1 | tail -3` — OK.

**Step 5: Mirror + commit**

```bash
cp hooks/handle-session-start.py plugins/requirements-framework/hooks/handle-session-start.py
cp hooks/handle-prompt-submit.py plugins/requirements-framework/hooks/handle-prompt-submit.py
stg new req-pause-06-banner   # desc: "feat(pause): visible paused banner in status injectors"
stg refresh
```

---

## Task 7: Slash commands `/req-pause` + `/req-resume`

**Files:**
- Create: `plugins/requirements-framework/commands/req-pause.md` + `req-pause.md.j2`
- Create: `plugins/requirements-framework/commands/req-resume.md` + `req-resume.md.j2`
- Modify: `plugins/requirements-framework/.claude-plugin/plugin.json` — minor version bump.

**Step 1: Author `req-pause.md`** (model frontmatter on `req-optout.md`):

```markdown
---
name: req-pause
description: "Pause the framework's blocking gates for this session only (auto-resumes at session end)"
argument-hint: "[reason]"
allowed-tools: ["Bash"]
git_hash: uncommitted
---

> **Workflow position**: escape-hatch (session-scoped). Suppresses BLOCKING gates for the current session only. Does NOT bypass strict-preflight (use `RF_STRICT_OFF` for that). Auto-resumes when the session ends.

# Pause the Requirements Framework (this session)

Run the CLI primitive to write the session pause marker:

​```bash
req pause ${ARGUMENTS:+--reason "$ARGUMENTS"}
​```

If `req` is not on PATH, fall back to `python3 hooks/requirements-cli.py pause`.

Then confirm to the user: blocking gates (edit/commit gate + end-of-turn verification) are off for this session; nudges and status still show a `⏸ paused` banner; run `/req-resume` to re-enable, or it clears automatically at session end.
```

**Step 2: Author `req-resume.md`** (analogous, calls `req resume`, `allowed-tools: ["Bash"]`).

**Step 3:** Create the `.md.j2` templates. Check how existing command `.md.j2` files relate to their `.md` (grep `update-plugin-versions.sh` / templating). If `.md` is generated from `.md.j2`, author the `.j2` and regenerate; otherwise author both consistently.

**Step 4: Version bump** — edit `plugin.json` version (minor, e.g. `4.19.1` → `4.20.0`); run `./update-plugin-versions.sh` to refresh `git_hash` fields, and `./sync-versions.sh` to propagate the version to `marketplace.json` + docs.

**Step 5: Commit**

```bash
stg new req-pause-07-commands   # desc: "feat(pause): /req-pause + /req-resume slash commands + version bump"
stg refresh
```

---

## Task 8: Mirror verification + full suite + deploy check

**Step 1: Verify no drift between repo and plugin hooks**

```bash
diff -rq hooks/lib/pause.py plugins/requirements-framework/hooks/lib/pause.py
for f in check-requirements handle-stop handle-session-end handle-session-start handle-prompt-submit; do
  diff -q "hooks/$f.py" "plugins/requirements-framework/hooks/$f.py" || echo "DRIFT: $f"
done
```
Expected: no output (identical).

**Step 2: Full test suite**

Run: `python3 hooks/test_requirements.py`
Expected: OK, total count increased by the new tests.

**Step 3: Smoke the CLI end-to-end** (in a throwaway git dir or this repo with an explicit session):

```bash
req pause --session test1234 && ls .git/requirements/sessions/test1234.paused && req resume --session test1234 && ! ls .git/requirements/sessions/test1234.paused
```
Expected: marker created then removed.

**Step 4: Sync deploy + status**

```bash
./sync.sh status   # expect repo and deployed in sync (note: deployed ~/.claude/hooks may be absent in this env; plugin path is what runs)
```

**Step 5:** No separate commit (verification only). If `update-plugin-versions.sh` changed hashes, fold into the Task 7 patch with `stg refresh`.

---

## Done criteria

- `python3 hooks/test_requirements.py` green with the new `TestSessionPause` cases.
- `req pause` / `req resume` round-trip the marker for the resolved session.
- A paused session: edits/bash allowed, Stop not blocked, `⏸ paused` banner visible, strict still blocks when strict mode is on.
- Marker gone after SessionEnd.
- `diff -rq` shows repo and plugin hook copies identical.
- `plugin.json` version bumped; `marketplace.json`/docs in sync.

## Suggested next step after implementation

Run `/arch-review` on this plan/branch to satisfy `adr_reviewed`, `tdd_planned`, `solid_reviewed`, then `/deep-review` before merge.
