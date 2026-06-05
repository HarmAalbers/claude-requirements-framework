"""Deterministic pre-flight lint gate for `/v3-review`.

Step 18c. Mirrors `/deep-review`'s blocking tool-validator step (ADR-013): run
cheap deterministic linters on the changed files and refuse to spend on N
parallel LLM workers if the code doesn't even lint.

`run_tool_gate(files)` returns the blocking error lines (empty == clean). The
entry layer aborts before fan-out when the list is non-empty.

Fail-LOUD (arch-review #5 + the loud-smoke-spikes rule): if a configured linter
binary is missing, this RAISES `RuntimeError` rather than silently skipping —
a gate that quietly does nothing is worse than no gate.

Default linter set is **ruff only**. Pyright is supported (`linters=("ruff",
"pyright")`) but excluded by default: this repo resolves `hooks.lib.*` via a
runtime `sys.path` insert, so a file-scoped `pyright` run reports spurious
`reportMissingImports` errors that would block every review. Ruff is the
repo's actually-enforced linter for the V3 review path.
"""

from __future__ import annotations

import subprocess
from collections.abc import Sequence

# linter name → command prefix (the changed files are appended).
_LINTER_CMDS: dict[str, list[str]] = {
    "ruff": ["ruff", "check"],
    "pyright": ["pyright"],
}

_DEFAULT_LINTERS = ("ruff",)


def _python_files(files: Sequence[str]) -> list[str]:
    return [f for f in files if f.endswith(".py")]


_TIMEOUT_SECONDS = 60


def _run_linter(name: str, files: list[str]) -> list[str]:
    # `--` ends option parsing so a path beginning with '-' can't be read as a
    # linter flag (argument-injection hardening, self-review).
    cmd = _LINTER_CMDS[name] + ["--"] + files
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=_TIMEOUT_SECONDS)
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"tool-gate: '{name}' not found — install it or fix PATH. "
            f"The gate fails loud rather than skipping a check."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"tool-gate: '{name}' timed out after {_TIMEOUT_SECONDS}s — "
            f"failing loud rather than hanging before LLM spend."
        ) from exc
    if proc.returncode == 0:
        return []
    combined = (proc.stdout or "") + (proc.stderr or "")
    lines = [ln for ln in combined.splitlines() if ln.strip()]
    # A non-zero exit with NO output (signal kill, internal panic, redirected
    # output) must not look like a clean pass (self-review #4): synthesize a
    # line so the caller still blocks.
    if not lines:
        return [f"{name}: exited {proc.returncode} with no output"]
    return lines


def run_tool_gate(
    files: Sequence[str],
    linters: Sequence[str] = _DEFAULT_LINTERS,
) -> list[str]:
    """Run the deterministic lint gate over the changed Python `files`.

    Args:
        files: changed file paths (non-Python entries are ignored).
        linters: linter names to run; defaults to `("ruff",)`. Pass
            `("ruff", "pyright")` to include type-checking where the project's
            import resolution makes that meaningful.

    Returns:
        Blocking error lines across all linters (empty list == gate passed).

    Raises:
        RuntimeError: if a configured linter binary is missing (fail-loud).
        KeyError: if an unknown linter name is requested.
    """
    py = _python_files(files)
    if not py:
        return []
    errors: list[str] = []
    for name in linters:
        errors += _run_linter(name, py)
    return errors


__all__ = ["run_tool_gate"]
