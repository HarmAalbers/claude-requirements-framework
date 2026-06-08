#!/usr/bin/env python3
"""Test suite for hooks/langfuse-trace.py — R5 Stop-hook wrapper.

Follows the framework's TestRunner convention (see tests/test_observability.py).
Run with: python3 tests/test_langfuse_trace_hook.py

Dependency-free: invokes the wrapper as a subprocess with a fake `uv` on
PATH. Never touches the network, real uv, or a Langfuse instance.
"""

import json
import os
import shutil
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
    record = (
        f'cat > "{record_to}/stdin.txt"; printf \'%s\\n\' "$@" > "{record_to}/args.txt"'
        if record_to
        else "cat > /dev/null"
    )
    body = f"#!/bin/sh\n{record}\nsleep {sleep}\nexit {exit_code}\n"
    uv = dir_path / "uv"
    uv.write_text(body)
    uv.chmod(uv.stat().st_mode | stat.S_IEXEC)
    return uv


def run_wrapper(env_overrides, payload=PAYLOAD, path_dirs=None, timeout=30):
    env_overrides = dict(env_overrides)  # non-mutating copy before any pop
    components = [str(d) for d in (path_dirs or []) if d] + ["/usr/bin", "/bin"]
    env = {
        "PATH": os.pathsep.join(components),
        "HOME": env_overrides.pop("HOME", tempfile.mkdtemp()),
    }
    env.update(env_overrides)
    return subprocess.run(
        [sys.executable, str(WRAPPER)],
        input=payload, capture_output=True, text=True, env=env, timeout=timeout,
    )


def main():
    # Hermeticity precondition: the "uv missing" tests rely on /usr/bin:/bin
    # NOT containing a real uv. Hard-fail loudly rather than silently hitting
    # the network with the real binary (loud-failure convention).
    if shutil.which("uv", path="/usr/bin:/bin") is not None:
        print(
            "FATAL: a real `uv` exists in /usr/bin:/bin — this suite requires "
            "uv NOT to be installed there, or the 'uv missing' tests would "
            "invoke the real uv and could hit the network.",
            file=sys.stderr,
        )
        sys.exit(1)

    r = TestRunner()
    print("hooks/langfuse-trace.py — Stop-hook wrapper")

    # 1. Gate closed → silent exit 0, uv never invoked
    with tempfile.TemporaryDirectory() as td:
        rec = Path(td) / "rec"
        rec.mkdir()
        make_fake_uv(Path(td), record_to=rec)
        p = run_wrapper({}, path_dirs=[td])
        r.test("gate closed: exit 0", p.returncode == 0, f"rc={p.returncode} err={p.stderr}")
        r.test("gate closed: silent", p.stdout == "" and p.stderr == "", f"out={p.stdout!r} err={p.stderr!r}")
        r.test("gate closed: uv not spawned", not (rec / "args.txt").exists())

    # 2. Gate closed: TRACE_TO_LANGFUSE present but not "true" → still inert
    p = run_wrapper({"TRACE_TO_LANGFUSE": "1"}, path_dirs=[])
    r.test("gate needs exactly 'true'", p.returncode == 0 and p.stderr == "", f"rc={p.returncode}")

    # 2b. Gate open via plugin-prefix variant CLAUDE_PLUGIN_OPTION_TRACE_TO_LANGFUSE=true
    with tempfile.TemporaryDirectory() as td:
        rec = Path(td) / "rec"
        rec.mkdir()
        make_fake_uv(Path(td), exit_code=0, record_to=rec)
        p = run_wrapper({"CLAUDE_PLUGIN_OPTION_TRACE_TO_LANGFUSE": "true"}, path_dirs=[td])
        r.test("plugin-prefix gate: exit 0", p.returncode == 0, f"rc={p.returncode} err={p.stderr}")
        r.test("plugin-prefix gate: uv spawned", (rec / "args.txt").exists(), "args.txt missing")
        _2b_args = (rec / "args.txt").read_text().splitlines() if (rec / "args.txt").exists() else []
        r.test("plugin-prefix gate: uv run --script", _2b_args[:2] == ["run", "--script"], f"args={_2b_args}")

    # 3. Gate open, uv missing → fail-hard: stderr + exit 1
    with tempfile.TemporaryDirectory() as empty:
        p = run_wrapper({"TRACE_TO_LANGFUSE": "true"}, path_dirs=[empty])
        r.test("uv missing: exit 1", p.returncode == 1, f"rc={p.returncode}")
        r.test("uv missing: stderr names uv", "uv" in p.stderr, f"err={p.stderr!r}")

    # 4. Gate open, uv missing, FAIL_OPEN → silent exit 0
    with tempfile.TemporaryDirectory() as empty:
        p = run_wrapper({"TRACE_TO_LANGFUSE": "true", "CC_LANGFUSE_FAIL_OPEN": "true"}, path_dirs=[empty])
        r.test("uv missing + fail-open: exit 0", p.returncode == 0, f"rc={p.returncode} err={p.stderr}")
        r.test("uv missing + fail-open: stderr empty", p.stderr == "", f"err={p.stderr!r}")

    # 5. Gate open, fake uv exit 0 → exit 0; correct invocation; stdin forwarded
    with tempfile.TemporaryDirectory() as td:
        rec = Path(td) / "rec"
        rec.mkdir()
        make_fake_uv(Path(td), exit_code=0, record_to=rec)
        p = run_wrapper({"TRACE_TO_LANGFUSE": "true"}, path_dirs=[td])
        args = (rec / "args.txt").read_text().splitlines() if (rec / "args.txt").exists() else []
        r.test("happy path: exit 0", p.returncode == 0, f"rc={p.returncode} err={p.stderr}")
        r.test("happy path: uv run --script", args[:2] == ["run", "--script"], f"args={args}")
        r.test("happy path: targets vendored script", args[2].endswith("_langfuse_hook.py") if len(args) > 2 else False, f"args={args}")
        r.test("happy path: stdin forwarded", (rec / "stdin.txt").read_text() == PAYLOAD if (rec / "stdin.txt").exists() else False)

    # 6. Fake uv exit 1 (vendored script failed) → wrapper exit 1
    with tempfile.TemporaryDirectory() as td:
        make_fake_uv(Path(td), exit_code=1)
        p = run_wrapper({"TRACE_TO_LANGFUSE": "true"}, path_dirs=[td])
        r.test("subprocess failure: exit 1", p.returncode == 1, f"rc={p.returncode}")
        r.test("subprocess failure: stderr mentions exit code", "exited" in p.stderr, f"err={p.stderr!r}")

    # 7. Fake uv exit 1 + FAIL_OPEN → exit 0
    with tempfile.TemporaryDirectory() as td:
        make_fake_uv(Path(td), exit_code=1)
        p = run_wrapper({"TRACE_TO_LANGFUSE": "true", "CC_LANGFUSE_FAIL_OPEN": "true"}, path_dirs=[td])
        r.test("subprocess failure + fail-open: exit 0", p.returncode == 0, f"rc={p.returncode}")
        r.test("subprocess failure + fail-open: stderr empty", p.stderr == "", f"err={p.stderr!r}")

    # 8. Never exit 2 — even when the subprocess exits 2
    with tempfile.TemporaryDirectory() as td:
        make_fake_uv(Path(td), exit_code=2)
        p = run_wrapper({"TRACE_TO_LANGFUSE": "true"}, path_dirs=[td])
        r.test("never exit 2", p.returncode != 2, f"rc={p.returncode}")
        r.test("subprocess exit 2 maps to 1", p.returncode == 1, f"rc={p.returncode}")

    # 9. Timeout: fake uv sleeps past wrapper timeout → kill, policy applies
    with tempfile.TemporaryDirectory() as td:
        make_fake_uv(Path(td), sleep=5)
        p = run_wrapper(
            {"TRACE_TO_LANGFUSE": "true", "CC_LANGFUSE_TIMEOUT_SECONDS": "1"},
            path_dirs=[td], timeout=10,
        )
        r.test("timeout: exit 1", p.returncode == 1, f"rc={p.returncode}")
        r.test("timeout: stderr mentions timeout", "timed out" in p.stderr, f"err={p.stderr!r}")

    # 10. Bad timeout config falls back to default — subprocess still invoked
    with tempfile.TemporaryDirectory() as td:
        make_fake_uv(Path(td), exit_code=0)
        p = run_wrapper(
            {"TRACE_TO_LANGFUSE": "true", "CC_LANGFUSE_TIMEOUT_SECONDS": "abc"},
            path_dirs=[td],
        )
        r.test("non-numeric timeout: exit 0", p.returncode == 0, f"rc={p.returncode} err={p.stderr}")

    # 11. Zero/negative timeout is clamped to default — no immediate timeout
    with tempfile.TemporaryDirectory() as td:
        make_fake_uv(Path(td), exit_code=0)
        p = run_wrapper(
            {"TRACE_TO_LANGFUSE": "true", "CC_LANGFUSE_TIMEOUT_SECONDS": "0"},
            path_dirs=[td],
        )
        r.test("zero timeout clamped: exit 0", p.returncode == 0, f"rc={p.returncode} err={p.stderr}")

    sys.exit(r.summary())


if __name__ == "__main__":
    main()
