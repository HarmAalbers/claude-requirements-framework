#!/usr/bin/env python3
"""Stop-hook wrapper: ship the turn to Langfuse via the vendored uv-isolated hook.

Runs as a second Stop entry in the plugin's hooks.json (registered by the
r5-register-hook patch), independent of handle-stop.py. Inert unless the
project opts in with TRACE_TO_LANGFUSE=true
in its .claude/settings(.local).json env block — the inert path is stdlib-only
and exits 0 silently.

When tracing is enabled the policy is FAIL-HARD by default: any failure (uv
missing, resolve error, vendored-script failure, timeout) prints one line to
stderr and exits 1 — visible warning, the turn still ends. Never exits 2
(that would block the Stop event). CC_LANGFUSE_FAIL_OPEN=true reverts to
silent continue (the wrapper itself never logs; the vendored hook's activity
log still records emit failures). Design: .claude/plans/2026-06-07-r5-stop-hook-observability-design.md

Input (stdin JSON, forwarded verbatim to the vendored hook):
    {"session_id": "...", "transcript_path": "..."}   # or sessionId/transcriptPath
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
    """Failure policy: loud by default, silent when CC_LANGFUSE_FAIL_OPEN=true.

    Mirrors hooks/_langfuse_hook.py's _fail() — keep semantics in sync
    (process boundary prevents sharing).
    """
    if _env("CC_LANGFUSE_FAIL_OPEN").lower() == "true":
        return 0
    print(f"langfuse-trace: {msg}", file=sys.stderr)
    return 1


def main() -> int:
    if _env("TRACE_TO_LANGFUSE") != "true":
        return 0  # gate closed: silent, dependency-free

    # sys.stdin.read() essentially never raises; guard exists so an exotic I/O error still honors the failure policy.
    try:
        payload = sys.stdin.read()
    except Exception as e:
        return _fail(f"failed to read hook payload: {e!r}")

    uv = shutil.which("uv")
    if uv is None:
        return _fail("TRACE_TO_LANGFUSE=true but `uv` not found on PATH")

    try:
        timeout = int(_env("CC_LANGFUSE_TIMEOUT_SECONDS") or DEFAULT_TIMEOUT_SECONDS)
    except ValueError:
        timeout = DEFAULT_TIMEOUT_SECONDS
    if timeout <= 0:
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
        # Intentional double line on vendored failure: the vendored script
        # explains WHAT failed, this line records THAT the hook chain failed
        # and the exit code. stderr is deliberately not captured. Any nonzero
        # (including a hypothetical 2) maps to 1 so the Stop event is never
        # blocked.
        return _fail(f"vendored hook exited {proc.returncode}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
