# R5 Stop-Hook Observability Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use requirements-framework:executing-plans to implement this plan task-by-task.

**Goal:** Every Claude Code turn in opted-in projects lands as a full-content trace in the self-hosted Langfuse, via a vendored upstream Stop hook bundled in the framework plugin, plus a structural OTEL beta-trace layer.

**Architecture:** A stdlib wrapper (`hooks/langfuse-trace.py`) is the registered Stop-hook command — it gates on `TRACE_TO_LANGFUSE=true` and delegates to a vendored upstream script (`hooks/_langfuse_hook.py`) via `uv run` with isolated `langfuse>=4,<5` deps (the global python pins langfuse v3 for the V3 stack — never bump it). Fail-hard by default (stderr + exit 1, never exit 2), `CC_LANGFUSE_FAIL_OPEN=true` reverts to silent. Layer 2 is pure env config. See approved design: `.claude/plans/2026-06-07-r5-stop-hook-observability-design.md`.

**Tech Stack:** Python 3 stdlib (wrapper), uv + PEP 723 (isolation), langfuse SDK v4 (vendored script only), Claude Code hooks (Stop), Langfuse self-hosted v3 at `http://localhost:3000`.

**Conventions that apply to every task:**
- Branch `feat/r5-stop-hook-observability` is active; design doc already committed as patch `r5-design-doc`.
- **Stacked Git only**: `stg new <name> -m "<msg>"` → edit → `git add <files>` → `stg refresh`. NEVER `git commit`.
- `tests/` is **NOT pytest** — script-style `TestRunner` files run directly: `python3 tests/test_<name>.py` (copy the convention from `tests/test_observability.py`).
- After ANY edit under `hooks/`: run `python3 scripts/build_plugin_hooks.py` and include the mirrored `plugins/requirements-framework/hooks/**` files in the same patch.
- Plugin version: bump `plugins/requirements-framework/.claude-plugin/plugin.json` AND `.claude-plugin/marketplace.json` from `4.15.10` → `4.16.0` exactly once (Task 4), in the patch that touches `hooks.json`.
- Hermetic full suite: `HOME=$(mktemp -d) PYTHONDONTWRITEBYTECODE=1 python3 hooks/test_requirements.py`.

---

### Task 1: Vendor the upstream hook script

**Files:**
- Create: `hooks/_langfuse_hook.py`
- Modify: `ruff.toml` (extend-exclude)
- Create (mirror): `plugins/requirements-framework/hooks/_langfuse_hook.py` (via build script)

**Step 1: Start the patch**

```bash
stg new r5-vendor-hook -m "feat(observability): vendor upstream langfuse_hook.py (pinned 1266914)"
```

**Step 2: Fetch the pinned upstream file**

```bash
gh api 'repos/langfuse/Claude-Observability-Plugin/contents/hooks/langfuse_hook.py?ref=1266914dc235dab485ed0640573047644dd39ce8' \
  --jq '.content' | base64 -d > hooks/_langfuse_hook.py
wc -c hooks/_langfuse_hook.py   # expect: 28120
```

**Step 3: Apply the four VENDOR-PATCH hunks**

(a) Replace the file's opening (shebang + docstring) so the file starts with:

```python
#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = ["langfuse>=4,<5"]
# ///
"""
Claude Code -> Langfuse hook

VENDORED from langfuse/Claude-Observability-Plugin
  source: hooks/langfuse_hook.py
  commit: 1266914dc235dab485ed0640573047644dd39ce8
  vendored: 2026-06-07
Local modifications are marked with `# VENDOR-PATCH`:
  (a) this PEP 723 header (runs under `uv run --script`, isolating
      langfuse v4 from the repo's global langfuse v3 pin)
  (b) LANGFUSE_HOST accepted as alias for LANGFUSE_BASE_URL
  (c) this provenance header
  (d) fail-hard policy: upstream returns 0 on every failure; we emit
      stderr + exit 1 unless CC_LANGFUSE_FAIL_OPEN=true
To update: re-fetch from upstream at a new pinned commit and re-apply
the VENDOR-PATCH hunks (diff against this file to find them).
"""
```

(b) In `main()`, the host line currently reads:

```python
    host = _opt("LANGFUSE_BASE_URL") or _opt("CC_LANGFUSE_BASE_URL") or "https://us.cloud.langfuse.com"
```

Replace with:

```python
    host = _opt("LANGFUSE_BASE_URL") or _opt("CC_LANGFUSE_BASE_URL") or _opt("LANGFUSE_HOST") or "https://us.cloud.langfuse.com"  # VENDOR-PATCH (b)
```

(d-helper) Directly below the `MAX_CHARS` block near the top, insert:

```python
# VENDOR-PATCH (d): fail-hard policy.
FAIL_OPEN = _opt("CC_LANGFUSE_FAIL_OPEN").lower() == "true"

def _fail(msg: str) -> int:
    """Failure policy: loud by default, silent when CC_LANGFUSE_FAIL_OPEN=true."""
    if FAIL_OPEN:
        debug(f"fail-open: {msg}")
        return 0
    print(f"langfuse-trace: {msg}", file=sys.stderr)
    return 1
```

NOTE: `_fail` uses `debug()` which is defined later in the file — that is fine
(called at runtime, not import time) — but `_opt` must already be defined; it is
(the `MAX_CHARS` block uses it).

(d-1) The import guard at the top currently reads:

```python
try:
    from langfuse import Langfuse, propagate_attributes
    from opentelemetry import trace as otel_trace_api
except Exception:
    sys.exit(0)
```

Replace the `except` body — it runs before `_fail` exists, so inline the policy:

```python
except Exception as e:  # VENDOR-PATCH (d)
    if (os.environ.get("CLAUDE_PLUGIN_OPTION_CC_LANGFUSE_FAIL_OPEN") or os.environ.get("CC_LANGFUSE_FAIL_OPEN") or "").lower() == "true":
        sys.exit(0)
    print(f"langfuse-trace: langfuse SDK import failed: {e!r}", file=sys.stderr)
    sys.exit(1)
```

(d-2) In `main()`, apply `_fail` to the swallow-points (each is a small, findable hunk):

| Upstream code | Replace with |
|---|---|
| `if not public_key or not secret_key:`<br>`    return 0` | `if not public_key or not secret_key:`<br>`    return _fail("tracing enabled but LANGFUSE_PUBLIC_KEY/SECRET_KEY unset")  # VENDOR-PATCH (d)` |
| `    langfuse = Langfuse(public_key=..., secret_key=..., host=host)`<br>`except Exception:`<br>`    return 0` | keep the call; change handler to:<br>`except Exception as e:`<br>`    return _fail(f"Langfuse client init failed: {e!r}")  # VENDOR-PATCH (d)` |
| `except Exception as e:`<br>`    debug(f"Unexpected failure: {e}")`<br>`    return 0` | `except Exception as e:`<br>`    return _fail(f"unexpected failure: {e!r}")  # VENDOR-PATCH (d)` |

Inside the per-turn emit loop, count failures. After `ss.turn_count += emitted` / state save, before the success `info(...)`/`return 0`, add:

```python
            if emit_failures:  # VENDOR-PATCH (d)
                return _fail(f"{emit_failures}/{emitted} turn(s) failed to emit (see {LOG_FILE})")
```

with `emit_failures = 0` initialized next to `emitted = 0` and `emit_failures += 1` in the existing `except Exception as e:` handler around `emit_turn(...)`.

Leave all other fail-open paths (missing payload, missing transcript, lock timeout) at `return 0` — those are normal no-work conditions, not failures.

**Step 4: Exclude vendor file from ruff**

In `ruff.toml`, change:

```toml
extend-exclude = ["plugins/requirements-framework/hooks"]
```

to:

```toml
extend-exclude = [
    "plugins/requirements-framework/hooks",
    # Vendored upstream code (langfuse/Claude-Observability-Plugin) — not our style domain.
    "hooks/_langfuse_hook.py",
]
```

**Step 5: Smoke the vendored script under uv isolation**

```bash
# No creds + fail-open → silent exit 0 (and proves uv resolves langfuse v4):
echo '{}' | CC_LANGFUSE_FAIL_OPEN=true uv run --script hooks/_langfuse_hook.py; echo "exit=$?"
# Expected: exit=0, no output

# No creds + default fail-hard → loud exit 1:
echo '{}' | uv run --script hooks/_langfuse_hook.py; echo "exit=$?"
# Expected: stderr "langfuse-trace: tracing enabled but LANGFUSE_PUBLIC_KEY/SECRET_KEY unset", exit=1

# Global pin untouched:
python3 -c "import langfuse; print(langfuse.__version__)"   # Expected: 3.0.1
```

**Step 6: Mirror into plugin and commit**

```bash
python3 scripts/build_plugin_hooks.py
git add hooks/_langfuse_hook.py ruff.toml plugins/requirements-framework/hooks/_langfuse_hook.py
stg refresh
```

---

### Task 2: Wrapper tests (RED)

**Files:**
- Create: `tests/test_langfuse_trace_hook.py`

The wrapper under test is `hooks/langfuse-trace.py` (created in Task 3). Tests invoke it
as a subprocess with a controlled env and a **fake `uv`** executable on PATH, so they are
dependency-free and never touch the network or real uv.

**Step 1: Start the patch**

```bash
stg new r5-wrapper -m "feat(observability): langfuse-trace Stop-hook wrapper (gate + uv isolation + fail policy)"
```

(Tests and implementation are one logical change; the patch stays open across Tasks 2–3.)

**Step 2: Write the failing tests**

Create `tests/test_langfuse_trace_hook.py` following the `TestRunner` convention of
`tests/test_observability.py` (shebang, docstring, TestRunner class or import-by-copy,
`sys.exit(runner.summary())` at the end):

```python
#!/usr/bin/env python3
"""Test suite for hooks/langfuse-trace.py — R5 Stop-hook wrapper.

Follows the framework's TestRunner convention (see tests/test_observability.py).
Run with: python3 tests/test_langfuse_trace_hook.py

Dependency-free: invokes the wrapper as a subprocess with a fake `uv` on
PATH. Never touches the network, real uv, or a Langfuse instance.
"""

import json
import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WRAPPER = REPO_ROOT / "hooks" / "langfuse-trace.py"
PAYLOAD = json.dumps({"session_id": "s1", "transcript_path": "/tmp/t.jsonl"})


class TestRunner:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.failed_tests = []

    def test(self, name, condition, msg=""):
        if condition:
            self.passed += 1
            print(f"  ✓ {name}")
        else:
            self.failed += 1
            self.failed_tests.append((name, msg))
            print(f"  ✗ {name}: {msg}")

    def summary(self):
        print(f"\n{self.passed} passed, {self.failed} failed")
        return 1 if self.failed else 0


def make_fake_uv(dir_path: Path, exit_code=0, record_to=None, sleep=0):
    """Create an executable fake `uv` that records argv+stdin and exits as told."""
    record = f'cat > "{record_to}/stdin.txt"; printf \'%s\\n\' "$@" > "{record_to}/args.txt"' if record_to else "cat > /dev/null"
    body = f"#!/bin/sh\n{record}\nsleep {sleep}\nexit {exit_code}\n"
    uv = dir_path / "uv"
    uv.write_text(body)
    uv.chmod(uv.stat().st_mode | stat.S_IEXEC)
    return uv


def run_wrapper(env_overrides, payload=PAYLOAD, path_dirs=None, timeout=30):
    env = {
        "PATH": os.pathsep.join(path_dirs or []) + os.pathsep + "/usr/bin:/bin",
        "HOME": env_overrides.pop("HOME", tempfile.mkdtemp()),
    }
    env.update(env_overrides)
    return subprocess.run(
        [sys.executable, str(WRAPPER)],
        input=payload, capture_output=True, text=True, env=env, timeout=timeout,
    )


def main():
    r = TestRunner()
    print("hooks/langfuse-trace.py — Stop-hook wrapper")

    # 1. Gate closed → silent exit 0, uv never invoked
    with tempfile.TemporaryDirectory() as td:
        rec = Path(td) / "rec"; rec.mkdir()
        make_fake_uv(Path(td), record_to=rec)
        p = run_wrapper({}, path_dirs=[td])
        r.test("gate closed: exit 0", p.returncode == 0, f"rc={p.returncode} err={p.stderr}")
        r.test("gate closed: silent", p.stdout == "" and p.stderr == "", f"out={p.stdout!r} err={p.stderr!r}")
        r.test("gate closed: uv not spawned", not (rec / "args.txt").exists())

    # 2. Gate closed: TRACE_TO_LANGFUSE present but not "true" → still inert
    p = run_wrapper({"TRACE_TO_LANGFUSE": "1"}, path_dirs=[])
    r.test("gate needs exactly 'true'", p.returncode == 0 and p.stderr == "", f"rc={p.returncode}")

    # 3. Gate open, uv missing → fail-hard: stderr + exit 1
    with tempfile.TemporaryDirectory() as empty:
        p = run_wrapper({"TRACE_TO_LANGFUSE": "true"}, path_dirs=[empty])
        r.test("uv missing: exit 1", p.returncode == 1, f"rc={p.returncode}")
        r.test("uv missing: stderr names uv", "uv" in p.stderr, f"err={p.stderr!r}")

    # 4. Gate open, uv missing, FAIL_OPEN → silent exit 0
    with tempfile.TemporaryDirectory() as empty:
        p = run_wrapper({"TRACE_TO_LANGFUSE": "true", "CC_LANGFUSE_FAIL_OPEN": "true"}, path_dirs=[empty])
        r.test("uv missing + fail-open: exit 0", p.returncode == 0, f"rc={p.returncode} err={p.stderr}")

    # 5. Gate open, fake uv exit 0 → exit 0; correct invocation; stdin forwarded
    with tempfile.TemporaryDirectory() as td:
        rec = Path(td) / "rec"; rec.mkdir()
        make_fake_uv(Path(td), exit_code=0, record_to=rec)
        p = run_wrapper({"TRACE_TO_LANGFUSE": "true"}, path_dirs=[td])
        args = (rec / "args.txt").read_text().split("\n") if (rec / "args.txt").exists() else []
        r.test("happy path: exit 0", p.returncode == 0, f"rc={p.returncode} err={p.stderr}")
        r.test("happy path: uv run --script", args[:2] == ["run", "--script"], f"args={args}")
        r.test("happy path: targets vendored script", args[2].endswith("_langfuse_hook.py") if len(args) > 2 else False, f"args={args}")
        r.test("happy path: stdin forwarded", (rec / "stdin.txt").read_text() == PAYLOAD if (rec / "stdin.txt").exists() else False)

    # 6. Fake uv exit 1 (vendored script failed) → wrapper exit 1, stderr passthrough
    with tempfile.TemporaryDirectory() as td:
        make_fake_uv(Path(td), exit_code=1)
        p = run_wrapper({"TRACE_TO_LANGFUSE": "true"}, path_dirs=[td])
        r.test("subprocess failure: exit 1", p.returncode == 1, f"rc={p.returncode}")

    # 7. Fake uv exit 1 + FAIL_OPEN → exit 0
    with tempfile.TemporaryDirectory() as td:
        make_fake_uv(Path(td), exit_code=1)
        p = run_wrapper({"TRACE_TO_LANGFUSE": "true", "CC_LANGFUSE_FAIL_OPEN": "true"}, path_dirs=[td])
        r.test("subprocess failure + fail-open: exit 0", p.returncode == 0, f"rc={p.returncode}")

    # 8. Never exit 2 — even when the subprocess exits 2
    with tempfile.TemporaryDirectory() as td:
        make_fake_uv(Path(td), exit_code=2)
        p = run_wrapper({"TRACE_TO_LANGFUSE": "true"}, path_dirs=[td])
        r.test("never exit 2", p.returncode != 2, f"rc={p.returncode}")
        r.test("subprocess exit 2 maps to 1", p.returncode == 1, f"rc={p.returncode}")

    # 9. Timeout: fake uv sleeps past wrapper timeout → kill, policy applies
    #    Wrapper must honor CC_LANGFUSE_TIMEOUT_SECONDS (test sets 1; prod default 45).
    with tempfile.TemporaryDirectory() as td:
        make_fake_uv(Path(td), sleep=5)
        p = run_wrapper(
            {"TRACE_TO_LANGFUSE": "true", "CC_LANGFUSE_TIMEOUT_SECONDS": "1"},
            path_dirs=[td], timeout=10,
        )
        r.test("timeout: exit 1", p.returncode == 1, f"rc={p.returncode}")
        r.test("timeout: stderr mentions timeout", "timed out" in p.stderr, f"err={p.stderr!r}")

    sys.exit(r.summary())


if __name__ == "__main__":
    main()
```

**Step 3: Run to verify it fails**

```bash
python3 tests/test_langfuse_trace_hook.py
```

Expected: immediate failures (wrapper file does not exist yet → every `run_wrapper`
subprocess fails / `WRAPPER` missing). RED confirmed.

---

### Task 3: Wrapper implementation (GREEN)

**Files:**
- Create: `hooks/langfuse-trace.py` (mode 755, like sibling hooks)
- Create (mirror): `plugins/requirements-framework/hooks/langfuse-trace.py` (via build script)

**Step 1: Write the wrapper**

```python
#!/usr/bin/env python3
"""Stop-hook wrapper: ship the turn to Langfuse via the vendored uv-isolated hook.

Registered in the plugin's hooks.json as a second Stop entry (independent of
handle-stop.py). Inert unless the project opts in with TRACE_TO_LANGFUSE=true
in its .claude/settings(.local).json env block — the inert path is stdlib-only
and exits 0 silently.

When tracing is enabled the policy is FAIL-HARD by default: any failure (uv
missing, resolve error, vendored-script failure, timeout) prints one line to
stderr and exits 1 — visible warning, the turn still ends. Never exits 2
(that would block the Stop event). CC_LANGFUSE_FAIL_OPEN=true reverts to
silent log-and-continue. Design: .claude/plans/2026-06-07-r5-stop-hook-observability-design.md
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

VENDORED = Path(__file__).resolve().parent / "_langfuse_hook.py"
DEFAULT_TIMEOUT_SECONDS = 45  # under Claude Code's 60s hook ceiling


def _env(name: str) -> str:
    """Read a plugin userConfig value with a plain-env fallback (upstream's _opt)."""
    return os.environ.get(f"CLAUDE_PLUGIN_OPTION_{name}") or os.environ.get(name) or ""


def _fail(msg: str) -> int:
    if _env("CC_LANGFUSE_FAIL_OPEN").lower() == "true":
        return 0
    print(f"langfuse-trace: {msg}", file=sys.stderr)
    return 1


def main() -> int:
    if _env("TRACE_TO_LANGFUSE") != "true":
        return 0  # gate closed: silent, dependency-free

    payload = sys.stdin.read()

    uv = shutil.which("uv")
    if uv is None:
        return _fail("TRACE_TO_LANGFUSE=true but `uv` not found on PATH")

    try:
        timeout = int(_env("CC_LANGFUSE_TIMEOUT_SECONDS") or DEFAULT_TIMEOUT_SECONDS)
    except ValueError:
        timeout = DEFAULT_TIMEOUT_SECONDS

    try:
        proc = subprocess.run(
            [uv, "run", "--script", str(VENDORED)],
            input=payload, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return _fail(f"vendored hook timed out after {timeout}s")
    except Exception as e:
        return _fail(f"failed to launch vendored hook: {e!r}")

    if proc.returncode != 0:
        # Vendored script already wrote its own stderr line; map any nonzero
        # (including a hypothetical 2) to 1 so the Stop event is never blocked.
        return _fail(f"vendored hook exited {proc.returncode}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

Then: `chmod 755 hooks/langfuse-trace.py`.

Note the double-fail edge in test 6/8: the vendored script's stderr passes through
(stderr is not captured), and the wrapper adds its own line — acceptable; both are
one-liners.

**Step 2: Run tests to verify they pass**

```bash
python3 tests/test_langfuse_trace_hook.py
```

Expected: all ~16 assertions PASS.

**Step 3: Mirror into plugin, run full suites**

```bash
python3 scripts/build_plugin_hooks.py
ruff check hooks/langfuse-trace.py tests/test_langfuse_trace_hook.py
HOME=$(mktemp -d) PYTHONDONTWRITEBYTECODE=1 python3 hooks/test_requirements.py   # expect all green
```

**Step 4: Commit**

```bash
git add hooks/langfuse-trace.py tests/test_langfuse_trace_hook.py plugins/requirements-framework/hooks/langfuse-trace.py
stg refresh
stg series   # r5-design-doc, r5-vendor-hook, r5-wrapper
```

---

### Task 4: Register the Stop hook + plugin version bump

**Files:**
- Modify: `plugins/requirements-framework/hooks/hooks.json` (Stop block, ~line 75)
- Modify: `plugins/requirements-framework/.claude-plugin/plugin.json` (version)
- Modify: `.claude-plugin/marketplace.json` (version)

**Step 1: Start the patch**

```bash
stg new r5-register-hook -m "feat(observability): register langfuse-trace Stop hook; bump plugin to 4.16.0"
```

**Step 2: Add the Stop entry**

In `plugins/requirements-framework/hooks/hooks.json`, the `"Stop"` block currently has one
hook (`handle-stop.py`). Add a second element to its inner `"hooks"` array:

```json
"Stop": [
  {
    "matcher": "*",
    "hooks": [
      {
        "type": "command",
        "command": "${CLAUDE_PLUGIN_ROOT}/hooks/handle-stop.py",
        "statusMessage": "Verifying requirements..."
      },
      {
        "type": "command",
        "command": "${CLAUDE_PLUGIN_ROOT}/hooks/langfuse-trace.py",
        "statusMessage": "Tracing turn to Langfuse..."
      }
    ]
  }
],
```

**Step 3: Bump versions (minor — new feature)**

In `plugins/requirements-framework/.claude-plugin/plugin.json`: `"version": "4.15.10"` → `"version": "4.16.0"`.
In `.claude-plugin/marketplace.json`: same `4.15.10` → `4.16.0`.

(If the version has moved past 4.15.10 by execution time — auto-bump CI does this — bump
minor from whatever is current.)

**Step 4: Validate + commit**

```bash
python3 -c "import json; json.load(open('plugins/requirements-framework/hooks/hooks.json')); print('hooks.json OK')"
python3 scripts/build_plugin_hooks.py --check    # expect: in sync
git add plugins/requirements-framework/hooks/hooks.json plugins/requirements-framework/.claude-plugin/plugin.json .claude-plugin/marketplace.json
stg refresh
```

---

### Task 5: Setup generator script + tests

**Files:**
- Create: `scripts/setup_langfuse_tracing.py`
- Create: `tests/test_setup_langfuse_tracing.py`

**Step 1: Start the patch**

```bash
stg new r5-setup-script -m "feat(observability): setup_langfuse_tracing.py env-block generator"
```

**Step 2: Write the failing tests**

Create `tests/test_setup_langfuse_tracing.py` (TestRunner convention; subprocess-invoke the
script with controlled env/cwd in temp dirs). Cover, at minimum:

1. **Loud failure**: no creds in env and no `infra/.env` in cwd → exit nonzero, stderr names the missing variables (this is a script, not library code — hard-fail per project rule).
2. **Happy path (`--skip-ping`)**: with `LANGFUSE_PUBLIC_KEY=pk-lf-x LANGFUSE_SECRET_KEY=sk-lf-y LANGFUSE_HOST=http://localhost:3000` in env → stdout is a JSON object containing ALL of: `TRACE_TO_LANGFUSE`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST`, `CC_LANGFUSE_MAX_CHARS` (`"100000"`), `CLAUDE_CODE_ENABLE_TELEMETRY`, `CLAUDE_CODE_ENHANCED_TELEMETRY_BETA`, `OTEL_TRACES_EXPORTER`, `OTEL_EXPORTER_OTLP_PROTOCOL`, `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_EXPORTER_OTLP_HEADERS`.
3. **Correct Basic header**: `OTEL_EXPORTER_OTLP_HEADERS` == `Authorization=Basic ` + `base64("pk-lf-x:sk-lf-y")` + `,x-langfuse-ingestion-version=4`; endpoint == `LANGFUSE_HOST` + `/api/public/otel`.
4. **`infra/.env` sourcing**: cwd contains `infra/.env` with the three vars, none in process env → same happy output (proves the repo-local convenience path).
5. **`--write` merge**: temp cwd with an existing `.claude/settings.local.json` containing `{"permissions": {...}, "env": {"EXISTING": "x"}}` → after `--write`, file still has `permissions` and `EXISTING`, plus all new env keys; file is valid JSON.
6. **`--write` create**: temp cwd without `.claude/` → file created with just the `env` block.
7. **No secrets on stdout in `--write` mode** (prints a confirmation line + file path, not the keys).

Run: `python3 tests/test_setup_langfuse_tracing.py` — expected: FAIL (script missing). RED.

**Step 3: Implement the script**

`scripts/setup_langfuse_tracing.py` (stdlib-only: `argparse`, `base64`, `json`, `os`, `pathlib`, `sys`, `urllib.request`):

- Resolve creds: process env first; else parse `infra/.env` from cwd (simple `KEY=VALUE` lines, ignore comments/blank, strip optional quotes — same shape `set -a; source` accepts). Missing any of the three → print every missing name to stderr, `sys.exit(1)`.
- Ping (default on): `urllib.request.urlopen(f"{host}/api/public/health", timeout=5)` — any error → stderr message including the host and the hint to start `docker compose -f infra/docker-compose.yml up -d`, `sys.exit(1)`. `--skip-ping` bypasses.
- Build the env dict exactly as the design's table (Layer 1 + Layer 2; omit `CC_LANGFUSE_FAIL_OPEN` and `CC_LANGFUSE_DEBUG` — those are manual opt-ins).
- Default mode: `json.dumps({"env": {...}}, indent=2)` to stdout with a leading `#`-comment-free paste hint on stderr.
- `--write`: read `.claude/settings.local.json` if present (else `{}`), deep-merge only the `env` key (new values win), write back with `indent=2` + trailing newline, create `.claude/` if needed. Print `wrote N env vars to .claude/settings.local.json` (no secret values).

**Step 4: Run tests to verify they pass**

```bash
python3 tests/test_setup_langfuse_tracing.py        # expect all PASS
ruff check scripts/setup_langfuse_tracing.py tests/test_setup_langfuse_tracing.py
```

**Step 5: Commit**

```bash
git add scripts/setup_langfuse_tracing.py tests/test_setup_langfuse_tracing.py
stg refresh
```

---

### Task 6: Documentation

**Files:**
- Modify: `CLAUDE.md` (new section after "Obsidian CLI Integration")
- Modify: `.claude/skills/langfuse/SKILL.md` (key-files table + setup pointer)

**Step 1: Start the patch**

```bash
stg new r5-docs -m "docs(observability): document Stop-hook Langfuse tracing"
```

**Step 2: Add a CLAUDE.md section**

Insert after the Obsidian section, mirroring its tone/length:

```markdown
## Langfuse Session Tracing (R5)

Every Claude Code turn in an opted-in project is traced to the self-hosted Langfuse
(`http://localhost:3000`) via a bundled Stop hook, plus structural OTEL beta-trace
telemetry. Opt-in per project; inert everywhere else.

### Enable (per project)

```bash
python3 scripts/setup_langfuse_tracing.py --write   # creds from env or infra/.env
# restart the Claude Code session to pick up the env block
```

Writes `TRACE_TO_LANGFUSE=true` + creds + OTEL config into the project's gitignored
`.claude/settings.local.json`.

### Architecture

- `hooks/langfuse-trace.py` — stdlib Stop-hook wrapper: gate + failure policy.
- `hooks/_langfuse_hook.py` — VENDORED upstream (langfuse/Claude-Observability-Plugin@1266914),
  runs under `uv run` with isolated `langfuse>=4,<5` (the repo's global langfuse v3 pin is
  untouched). Update by re-vendoring at a new pinned commit; hunks marked `# VENDOR-PATCH`.
- **Fail-hard by default** when tracing is enabled: failures print a one-line stderr warning
  and exit 1 (never 2 — the Stop event is never blocked). Set `CC_LANGFUSE_FAIL_OPEN=true`
  in the project env to silence. Debug log: `~/.claude/state/langfuse_hook.log`
  (`CC_LANGFUSE_DEBUG=true` for verbose).

Design: `.claude/plans/2026-06-07-r5-stop-hook-observability-design.md`.
```

**Step 3: Update the langfuse skill**

In `.claude/skills/langfuse/SKILL.md`, add two rows to the key-files table:

```markdown
| `hooks/langfuse-trace.py` | Stop-hook wrapper tracing every CC turn to Langfuse (R5). Fail-hard default, `CC_LANGFUSE_FAIL_OPEN` override. |
| `hooks/_langfuse_hook.py` | Vendored upstream hook (SDK v4 via uv isolation — exempt from the project's v3 pin). |
```

and a sentence under "This Project's Langfuse Setup" noting session tracing exists and how
to enable it (`scripts/setup_langfuse_tracing.py --write`).

NOTE: check whether `.agents/skills/langfuse` is a symlink to `.claude/skills/langfuse`
(`ls -la .agents/skills/`). If it is a real copy, apply the same edit there.

**Step 4: Commit**

```bash
git add CLAUDE.md .claude/skills/langfuse/SKILL.md   # + .agents copy if real
stg refresh
```

---

### Task 7: Opt this repo in + end-to-end verification

**REQUIRED SUB-SKILL before claiming done:** `requirements-framework:verification-before-completion`.

**Step 1: Generate and write the env block**

```bash
python3 scripts/setup_langfuse_tracing.py --write
# Expected: "wrote 11 env vars to .claude/settings.local.json"
# If it hard-fails with Langfuse unreachable: docker compose -f infra/docker-compose.yml up -d, retry.
cat .claude/settings.local.json   # eyeball: env block present, keys look sane
git check-ignore .claude/settings.local.json && echo "gitignored OK"
```

**Step 2: Live verification — hand to the user**

The hook only fires in a *restarted* session with the new env. Ask the user to:

1. Restart their Claude Code session in this repo (so settings.local.json env loads).
2. Run any trivial turn (e.g. "echo hi via Bash").
3. Then verify ingestion (either the user or a fresh session can run):

```bash
set -a; source infra/.env; set +a; export LANGFUSE_BASE_URL="$LANGFUSE_HOST"
npx langfuse-cli api trace list --limit 5
# Expected: a "Claude Code – Turn N" trace with a recent timestamp.
```

4. Layer 2 check in the same listing or the Langfuse UI (`http://localhost:3000`):
   a `claude_code.interaction` span/trace from the same window. If Layer 2 shows nothing,
   record it as a known-beta gap (design accepts this) — do NOT fail the task on Layer 2 alone.

**Step 3: Negative-path spot check (fail-hard is real)**

With the docker stack stopped (`docker compose -f infra/docker-compose.yml stop langfuse-web`),
run one turn: the session should show a visible `langfuse-trace:` warning, and the turn must
still complete. Restart the stack afterwards (`... up -d`).

**Step 4: Full suite + sync status**

```bash
HOME=$(mktemp -d) PYTHONDONTWRITEBYTECODE=1 python3 hooks/test_requirements.py
for f in tests/test_*.py; do python3 "$f" || echo "FAILED: $f"; done
python3 scripts/build_plugin_hooks.py --check
./update-plugin-versions.sh && ./update-plugin-versions.sh --verify
./sync.sh status
```

All green expected. If `update-plugin-versions.sh` changed `git_hash` frontmatter, fold into
the touched patches (`stg refresh` on the relevant patch via `stg edit`/`stg refresh -p`).

**Step 5: Wrap up the branch**

```bash
stg series    # r5-design-doc, r5-vendor-hook, r5-wrapper, r5-register-hook, r5-setup-script, r5-docs
git push -u origin feat/r5-stop-hook-observability
```

Then follow the normal review chain before PR: `/deep-review` (pre_pr_review) and
`/codex-review` per the session's requirement gates, and
`requirements-framework:finishing-a-development-branch` for merge mechanics
(gh account note: switch to `HarmAalbers` only to merge, then back to `SolarHarm`).

---

## Preparatory Refactoring

> Advisory analysis (Fowler: "first refactor to make the change easy"). Findings are
> proportionate to R5's small additive footprint. Nothing here is a blocker.

### Finding 1 — `_load_dotenv` is copy-pasted three times (ADVISORY)

**Severity:** Low

Three independent implementations of the same `_load_dotenv` function exist:

| File | Function | Notes |
|------|----------|-------|
| `hooks/lib/llm/review_cli.py` | `_load_dotenv()` | soft-dep on python-dotenv; scans `infra/.env` then `.env` |
| `scripts/sync_prompts_to_langfuse.py` | `_load_dotenv()` | identical logic, identical docstring, same soft-dep comment |
| `hooks/lib/llm/_spikes/v3_langfuse_smoke.py` | `_load_dotenv_files()` | same logic, different name |

R5's `scripts/setup_langfuse_tracing.py` (Task 5) will add a **fourth** copy to source
creds from `infra/.env`. The plan's Task 5 Step 3 already specifies the pattern explicitly
("simple `KEY=VALUE` lines, ignore comments/blank, strip optional quotes — same shape
`set -a; source` accepts"), so the executor is aware of the pattern.

**Recommended action (before Task 5):** Extract to `scripts/_env_utils.py` (or
`hooks/lib/langfuse_env.py` if it needs to be importable from hooks). However, given:
- R5 is a small feature, not a large refactor
- `setup_langfuse_tracing.py` is stdlib-only by design (no extra imports)
- The existing copies are not bugs, just mild duplication

**Verdict:** Do NOT block on this. Note the fourth copy in Task 5's code comment so the
next refactor pass has a clear extraction target. If the executor is already editing
`scripts/`, an opportunistic extraction is welcome; otherwise, skip.

---

### Finding 2 — `_env()` helper is new (no existing parallel in hooks/) (INFORMATIONAL)

**Severity:** Informational only

The plan's `hooks/langfuse-trace.py` introduces a private `_env()` helper:

```python
def _env(name: str) -> str:
    """Read a plugin userConfig value with a plain-env fallback (upstream's _opt)."""
    return os.environ.get(f"CLAUDE_PLUGIN_OPTION_{name}") or os.environ.get(name) or ""
```

Existing hooks in `hooks/*.py` do NOT use the `CLAUDE_PLUGIN_OPTION_*` prefix pattern at
all — they read env vars directly via `os.environ.get(...)`. This is the first hook to
follow the plugin-userConfig precedence convention.

**This is intentional by design** (the wrapper must mirror the vendored script's `_opt`
precedence so they always agree). No change needed; the docstring in the plan already
explains why. Nothing to extract to `hooks/lib/` — the pattern is local to the two
langfuse files.

---

### Finding 3 — `ruff.toml` `extend-exclude` change is straightforward (INFORMATIONAL)

**Severity:** Informational only

Task 1 Step 4 changes `extend-exclude` from a string to an array. The existing value
`"plugins/requirements-framework/hooks"` is a single string scalar in `ruff.toml`; TOML
arrays of strings are fully compatible. The change is minimal and non-breaking. No
preparatory work needed.

**Verify** after editing that `force-exclude = true` is still present (it's on the line
below and the `extend-exclude` edit touches only that block). The plan's Step 4 shows the
correct final state.

---

### Finding 4 — `tests/` convention is consistent; new test file fits cleanly (INFORMATIONAL)

**Severity:** Informational only

`tests/test_observability.py` is the correct template for `tests/test_langfuse_trace_hook.py`.
The plan's Task 2 Step 2 reproduces the `TestRunner` class verbatim — this is the established
pattern (copy-by-convention; not extracted to a shared base). No action needed.

---

### Summary

| Finding | Severity | Action |
|---------|----------|--------|
| `_load_dotenv` copied 3× → 4× after R5 | Low | Note in Task 5 comment; opportunistic extraction only |
| `_env()` is new, intentionally first of its kind | Informational | No action; docstring explains |
| `extend-exclude` string→array | Informational | Verify `force-exclude` line still present after edit |
| `TestRunner` copy-by-convention | Informational | No action; follow the established pattern |

No blocking preparatory refactors identified. R5 is additive; the existing hook entry-point
conventions (`parse_hook_input`, `early_hook_setup` in `hooks/lib/hook_utils.py`) are not
relevant to `langfuse-trace.py`, which intentionally stays stdlib-only and outside the
requirements framework stack.

---

## Risks & gotchas for the executor

- **NEVER `git commit`** — stg only. **NEVER launch `/v3-review` or other SDK fan-outs via Bash.**
- `hooks.json` is plugin-owned and hand-maintained — `build_plugin_hooks.py` must never report it as drift (it's in `PLUGIN_OWNED`).
- The vendored file is excluded from ruff but NOT from `build_plugin_hooks.py` mirroring — both copies must stay byte-identical (the `--check` invariant enforces this).
- First real `uv run` resolves langfuse v4 into uv's cache (needs network once). Task 1 Step 5 front-loads this so the live hook never pays it.
- `CC_LANGFUSE_TIMEOUT_SECONDS` exists primarily so tests don't sleep 45s; don't document it as a user knob beyond a code comment.
- Upstream env precedence is `CLAUDE_PLUGIN_OPTION_<NAME>` then `<NAME>` — the wrapper's `_env()` mirrors this so wrapper and vendored script always agree on the gate and policy.
- If the auto-bump CI moved the plugin version past 4.15.10, bump minor from current instead.

---

## Commit Plan

The plan's proposed patch sequence (`r5-vendor-hook`, `r5-wrapper`, `r5-register-hook`,
`r5-setup-script`, `r5-docs`) is validated and retained exactly. Two patches already exist
on the stack (`r5-design-doc`, `r5-impl-plan`). The five new patches below complete the
feature.

> **Stacked Git only** — every patch uses `stg new … -m "…"` → edit → `stg refresh`.
> Plugin mirror rule: any edit under `hooks/` must include the mirrored
> `plugins/requirements-framework/hooks/**` copy (via `build_plugin_hooks.py`) in the
> **same** `stg refresh` call.

---

### Patch 1 — `r5-vendor-hook`

**Title:** `feat(observability): vendor upstream langfuse_hook.py (pinned 1266914)`

**Files changed:**
- `hooks/_langfuse_hook.py` — new file; fetched from upstream commit `1266914`, four
  VENDOR-PATCH hunks applied (PEP 723 header, `LANGFUSE_HOST` alias, provenance comment,
  fail-hard policy).
- `ruff.toml` — extend `extend-exclude` to include `"hooks/_langfuse_hook.py"` so the
  vendored third-party code is never linted. Current value is a single-string element
  `["plugins/requirements-framework/hooks"]`; change to a two-element array.
- `plugins/requirements-framework/hooks/_langfuse_hook.py` — byte-identical mirror via
  `python3 scripts/build_plugin_hooks.py`.

**What to test:**
```bash
# Smoke: fail-open (no creds) — exit 0, no output
echo '{}' | CC_LANGFUSE_FAIL_OPEN=true uv run --script hooks/_langfuse_hook.py; echo "exit=$?"

# Fail-hard (no creds) — exit 1, one stderr line naming the missing keys
echo '{}' | uv run --script hooks/_langfuse_hook.py; echo "exit=$?"

# Global langfuse v3 pin untouched
python3 -c "import langfuse; print(langfuse.__version__)"  # must print 3.x

# Mirror integrity
python3 scripts/build_plugin_hooks.py --check  # expect: in sync
```

**Standalone-testable:** yes — vendored script runs independently under `uv run --script`.

---

### Patch 2 — `r5-wrapper`

**Title:** `feat(observability): langfuse-trace Stop-hook wrapper (gate + uv isolation + fail policy)`

**Files changed:**
- `tests/test_langfuse_trace_hook.py` — new file; 9 test groups (~16 assertions) covering
  gate-closed, `TRACE_TO_LANGFUSE` value strictness, uv-missing fail-hard, uv-missing
  fail-open, happy path (invocation shape + stdin forwarding), subprocess failure,
  subprocess failure + fail-open, exit-2 remap to exit-1, and timeout.
- `hooks/langfuse-trace.py` — new file (mode 755); stdlib-only wrapper: env gate →
  stdin read → `shutil.which("uv")` → `subprocess.run(uv run --script …, timeout=…)` →
  failure policy. Never exits 2.
- `plugins/requirements-framework/hooks/langfuse-trace.py` — byte-identical mirror via
  build script.

**What to test:**
```bash
# TDD red to green
python3 tests/test_langfuse_trace_hook.py  # expect all PASS

# Style
ruff check hooks/langfuse-trace.py tests/test_langfuse_trace_hook.py

# Full suite must stay green
HOME=$(mktemp -d) PYTHONDONTWRITEBYTECODE=1 python3 hooks/test_requirements.py

# Mirror integrity
python3 scripts/build_plugin_hooks.py --check
```

**Standalone-testable:** yes — tests use a fake `uv` on PATH; no network, no real uv, no
Langfuse instance required.

**Dependency:** logically requires `r5-vendor-hook` on the stack (the wrapper delegates to
`hooks/_langfuse_hook.py`), but the test suite is fully hermetic — it never invokes the
vendored script directly.

---

### Patch 3 — `r5-register-hook`

**Title:** `feat(observability): register langfuse-trace Stop hook; bump plugin to 4.16.0`

**Files changed:**
- `plugins/requirements-framework/hooks/hooks.json` — add a second element to the `"Stop"`
  inner `"hooks"` array: `command: "${CLAUDE_PLUGIN_ROOT}/hooks/langfuse-trace.py"`,
  `statusMessage: "Tracing turn to Langfuse..."`. Current Stop block has exactly one hook
  (`handle-stop.py`); the new entry is appended after it.
- `plugins/requirements-framework/.claude-plugin/plugin.json` — `"version"` bumped to
  `4.16.0` (current: `4.15.10`; minor bump for new feature). If CI auto-bump has moved the
  version past `4.15.10`, bump minor from whatever is current.
- `.claude-plugin/marketplace.json` — same version bump to `4.16.0`.

**Note:** `hooks.json` is plugin-owned and hand-maintained. `build_plugin_hooks.py` must not
report it as drift (`PLUGIN_OWNED` list). No `hooks/` source file is touched in this patch,
so the build-script mirror rule does **not** apply here.

**What to test:**
```bash
# JSON validity
python3 -c "import json; json.load(open('plugins/requirements-framework/hooks/hooks.json')); print('OK')"

# Build-script reports in sync (hooks.json is PLUGIN_OWNED, no drift expected)
python3 scripts/build_plugin_hooks.py --check

# Version bump landed
python3 -c "import json; print(json.load(open('plugins/requirements-framework/.claude-plugin/plugin.json'))['version'])"
python3 -c "import json; ps=json.load(open('.claude-plugin/marketplace.json'))['plugins']; print(next(p['version'] for p in ps if p['name']=='requirements-framework'))"
```

**Standalone-testable:** yes — JSON validation is mechanical; no runtime required.

**This is the patch that owns the plugin version bump.** No other patch in this sequence
should touch `plugin.json` or `marketplace.json`.

---

### Patch 4 — `r5-setup-script`

**Title:** `feat(observability): setup_langfuse_tracing.py env-block generator`

**Files changed:**
- `tests/test_setup_langfuse_tracing.py` — new file; 7 scenarios: loud failure on missing
  creds, happy path with `--skip-ping`, correct Basic auth header and OTEL endpoint,
  `infra/.env` sourcing, `--write` merge preserving existing keys, `--write` create from
  empty, no secrets on stdout in `--write` mode.
- `scripts/setup_langfuse_tracing.py` — new file; stdlib-only (`argparse`, `base64`, `json`,
  `os`, `pathlib`, `sys`, `urllib.request`). Resolves creds from env then `infra/.env`,
  optionally pings `/api/public/health`, builds the full env dict (Layer 1 + Layer 2),
  outputs JSON or merges into `.claude/settings.local.json` with `--write`.

**No hooks/ files are touched — build-script mirror rule does not apply.**

**What to test:**
```bash
# TDD red to green
python3 tests/test_setup_langfuse_tracing.py  # expect all PASS

# Style
ruff check scripts/setup_langfuse_tracing.py tests/test_setup_langfuse_tracing.py
```

**Standalone-testable:** yes — tests use temp dirs; skip ping or supply fake creds. Network
not required for the test suite.

---

### Patch 5 — `r5-docs`

**Title:** `docs(observability): document Stop-hook Langfuse tracing`

**Files changed:**
- `CLAUDE.md` — new "## Langfuse Session Tracing (R5)" section inserted after "## Obsidian
  CLI Integration". Covers opt-in steps, architecture (wrapper → vendored script → uv
  isolation), fail-hard policy, and design pointer.
- `.claude/skills/langfuse/SKILL.md` — two rows added to the key-files table
  (`langfuse-trace.py` and `_langfuse_hook.py`); one sentence under "This Project's Langfuse
  Setup" describing R5 and linking to `setup_langfuse_tracing.py --write`.
- `.agents/skills/langfuse/SKILL.md` — **same edits** as the `.claude/` copy; confirmed as
  a real directory (not a symlink), so it must be updated independently.

**No hooks/ files are touched — build-script mirror rule does not apply.**

**What to test:**
```bash
# Markdown fence-balance check
python3 -c "
import sys
for path in ['CLAUDE.md', '.claude/skills/langfuse/SKILL.md', '.agents/skills/langfuse/SKILL.md']:
    txt = open(path).read()
    opens = txt.count('\`\`\`')
    if opens % 2 != 0:
        sys.exit(f'{path}: unbalanced code fences ({opens})')
print('fences OK')
"
```

**Standalone-testable:** yes — documentation-only; no runtime required.

---

### Summary table

| Patch | Short title | New files | Modified files | Independently testable |
|---|---|---|---|---|
| `r5-vendor-hook` | Vendor langfuse_hook.py | `hooks/_langfuse_hook.py`, `plugins/.../hooks/_langfuse_hook.py` | `ruff.toml` | Yes — `uv run --script` smoke |
| `r5-wrapper` | Stop-hook wrapper + tests | `hooks/langfuse-trace.py`, `tests/test_langfuse_trace_hook.py`, `plugins/.../hooks/langfuse-trace.py` | — | Yes — fake-uv test suite |
| `r5-register-hook` | Register hook + version bump | — | `hooks/hooks.json`, `plugin.json`, `marketplace.json` | Yes — JSON validation |
| `r5-setup-script` | Setup script + tests | `scripts/setup_langfuse_tracing.py`, `tests/test_setup_langfuse_tracing.py` | — | Yes — temp-dir test suite |
| `r5-docs` | Documentation | — | `CLAUDE.md`, `.claude/skills/langfuse/SKILL.md`, `.agents/skills/langfuse/SKILL.md` | Yes — fence-balance check |

### Invariants across all patches

1. **Never `git commit`** — `stg new` + `stg refresh` only.
2. **Mirror rule**: any `hooks/` edit → run `python3 scripts/build_plugin_hooks.py` and
   include the `plugins/requirements-framework/hooks/**` mirror file in the same `stg refresh`.
3. **Plugin version bump exactly once**: in `r5-register-hook`, which is the patch that
   touches `hooks.json` (the observable plugin-behavior change). No other patch touches
   `plugin.json` or `marketplace.json`.
4. **Global langfuse v3 untouched**: the vendored script runs under `uv run --script` with
   its own isolated `langfuse>=4,<5`; never imported by the repo's Python env.
5. **Never exit 2**: the wrapper clamps any nonzero subprocess exit to `1` — the Stop event
   must never be blocked by the tracing hook.

---

## Review Amendments (arch-review 2026-06-07)

Binding amendments from the team review — the executor MUST apply these on top of the task
text above. None changes the architecture; all are folded into existing patches.

**A1 — 4th smoke test: `emit_failures` path** *(tdd-validator MEDIUM, corroborated by
codex)*. In Task 1 Step 5 (patch `r5-vendor-hook`), add a smoke that exercises the new
emit-loop failure counting: run the vendored script with fake creds
(`LANGFUSE_PUBLIC_KEY=pk-lf-x LANGFUSE_SECRET_KEY=sk-lf-y LANGFUSE_HOST=http://127.0.0.1:1`,
unreachable port) and a real stdin payload pointing at a tiny hand-written transcript JSONL
(one user + one assistant line) → expect exit 1 and a stderr line matching
`N/N turn(s) failed to emit`. With `CC_LANGFUSE_FAIL_OPEN=true` → exit 0.

**A2 — VENDOR-PATCH coverage count + cross-sync comments** *(solid-reviewer MEDIUM-1 ×
codex LOW)*. (i) Add to the vendored file's provenance docstring:
`VENDOR-PATCH (d) coverage: 5 patched failure points (import guard, missing creds, client
init, emit loop, unexpected exception) — re-verify this count on every re-vendor.`
(ii) Both `_fail()` definitions (wrapper and vendored) get a cross-reference comment:
`# Mirrors <other file>'s _fail() — keep semantics in sync (process boundary prevents sharing).`

**A3 — wrapper double-stderr comment** *(codex MEDIUM-1, unique finding — accepted
behavior, document it)*. In the wrapper, where nonzero subprocess exit maps to `_fail(...)`,
add: `# Intentional double line on vendored failure: the vendored script explains WHAT
failed, this line records THAT the hook chain failed and the exit code. stderr is
deliberately not captured.`

**A4 — setup script: within-module SRP decomposition** *(solid-reviewer MEDIUM-2)*.
`scripts/setup_langfuse_tracing.py` is structured as four helpers + orchestrator:
`_resolve_creds()` (env → `infra/.env`), `_ping(host)`, `_build_env_block(creds)` (incl.
base64 header), `_write_settings(env_block)` (merge logic); `main()` only sequences them.
Same file, no new modules. Tests may target helpers directly where that removes subprocess
overhead (keep at least the loud-failure and `--write` cases as subprocess-level tests).

**A5 — warm the uv cache from `--write`** *(codex LOW-1)*. At the end of a successful
`--write`, the setup script runs
`uv run --script <repo>/hooks/_langfuse_hook.py < /dev/null` with
`CC_LANGFUSE_FAIL_OPEN=true` env and a 120s timeout, so the first traced turn never pays
dependency resolution inside the hook's 45s budget. Print `cache warmed` / a loud warning
if it fails (do not fail the whole setup on warm failure — creds are already written).

**A6 — new ADR-019 in the docs patch** *(adr-guardian MEDIUM-1 + MEDIUM-2 + LOW-1)*.
Task 6 (patch `r5-docs`) additionally creates
`docs/adr/ADR-019-stop-hook-observability-vendored-fail-hard.md` recording: (a) the
fail-hard exception for OPT-IN observability hooks vs the framework's fail-open principle
for infrastructure hooks — incl. the "never exit 2" floor and the `CC_LANGFUSE_FAIL_OPEN`
override; (b) the vendored-upstream-code pattern (pin discipline, `VENDOR-PATCH` hunk
convention, re-vendor procedure, ruff exemption); (c) uv as a runtime prerequisite for
opted-in projects (gate-closed path stays dependency-free) and the PEP 723 isolation of
langfuse v4 from the repo's v3 pin. The CLAUDE.md "Enable" subsection must name `uv` as a
prerequisite.

**A7 — namespace + ordering notes in docs** *(compat-checker HIGH-1, MEDIUM-1, MEDIUM-2)*.
(i) The CLAUDE.md section and ADR-019 must state explicitly: Layer 2 uses the GENERIC
`OTEL_EXPORTER_OTLP_*` env keys while the V3 stack's `observability.py` uses the
signal-specific `OTEL_EXPORTER_OTLP_TRACES_*` keys — parallel, non-overlapping namespaces;
signal-specific wins per OTLP spec, so both coexist; revisit precedence if either is ever
refactored. (ii) Note that `langfuse-trace.py` runs after `handle-stop.py` and only fires
on turns that actually end — turns blocked by requirement verification are not traced
(accepted gap). (iii) In Task 1 Step 4, also update the existing `force-exclude` comment in
`ruff.toml` so it covers both excluded paths.

**Severity disposition:** all CRITICAL: none; all HIGH (1: compat OTEL namespace) resolved
by A7-documentation (no code conflict exists today — key names differ); all MEDIUM resolved
by A1–A7; LOW items either folded in (uv-prereq doc, ruff comment) or consciously accepted
(LANGFUSE_HOST multi-instance precedence, `CLAUDE_PLUGIN_OPTION_` path retained as
upstream-compatible, plugin-version drift caveat already in plan).

---

## Verdict

APPROVED

Reviewed: feat/r5-stop-hook-observability @ 2026-06-07T19:29:33Z

Team verdict (7 reviewers: adr-guardian, compat-checker, tdd-validator, solid-reviewer,
refactor-advisor, commit-planner, codex-arch-reviewer): no CRITICAL findings, no ADR
violations, no breaking changes, no blocking SOLID issues, no blocking preparatory
refactors. The plan is approved as amended by `## Review Amendments` above; the commit
strategy in `## Commit Plan` is binding.
