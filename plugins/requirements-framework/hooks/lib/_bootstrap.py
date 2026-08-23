"""Runtime dependency bootstrap: guarantee PyYAML by re-execing under ``uv run``.

Every top-level hook and the ``req`` CLI shebang to ``#!/usr/bin/env python3``,
which resolves to whatever python is first on PATH. If that interpreter lacks
PyYAML the framework would silently fail-open (config never loads, gates vanish
with no signal). This module makes each entrypoint self-heal: if the core
dependency is missing but ``uv`` is available, it re-execs itself once under
``uv run --no-project --with PyYAML``, an isolated, cached environment.

Design:

- **Sentinel check** (``import yaml``) → ZERO overhead when the dep is already
  present (dev ``.venv``, CI ``uv sync``, or a correctly provisioned ambient
  python). No re-exec, no ``uv`` spawn.
- **Self-heals** only when yaml is missing AND ``uv`` exists — the user's
  broken-ambient case. One re-exec; ``RF_UV_BOOTSTRAPPED`` guards against any
  loop (e.g. the pathological case where the resolved env also lacks yaml).
- **``--no-project``** so a hook firing inside some *other* python project (a
  Django repo, say) never triggers a sync of that project's deps — the env is
  isolated to exactly ``--with`` packages.
- **Invocation-agnostic**: works via shebang, ``python file.py``, or the ``req``
  symlink, because the guard lives in the module, not the shebang.
- **Fail-open**: no ``uv`` → return and let the caller proceed (a later import
  may still fail, which the framework already tolerates by design).

Mirrors the uv re-exec idea already used by ``hooks/langfuse-trace.py`` (which
uses PEP-723 script metadata for its heavier, isolated dep set).
"""
import os
import shutil
import sys
from pathlib import Path

_GUARD_ENV = "RF_UV_BOOTSTRAPPED"
_CORE_PACKAGES = ("PyYAML>=6.0",)


def _find_uv():
    """``which("uv")``, falling back to a probe of uv's default install dir.

    GUI-launched sessions (the desktop app, a terminal spawned by launchd)
    inherit a bare PATH without ``~/.local/bin``, which is where the official
    uv installer puts the binary. Without this probe the self-heal silently
    never fires on exactly the machines whose ambient python is broken.

    Mirrors ``hooks/langfuse-trace.py::_find_uv``; that file stays a
    self-contained PEP-723 script and cannot import this module.
    """
    uv = shutil.which("uv")
    if uv is not None:
        return uv
    candidate = Path.home() / ".local" / "bin" / "uv"
    return str(candidate) if os.access(candidate, os.X_OK) else None


def _plan_reexec(packages, *, yaml_present, uv_path, already_bootstrapped, argv):
    """Pure decision function: the argv to exec, or ``None`` to proceed in-process.

    Kept side-effect-free so the re-exec policy is unit-testable without spawning
    a real ``uv`` process.
    """
    if yaml_present or already_bootstrapped or uv_path is None:
        return None
    with_args = []
    for pkg in packages:
        with_args += ["--with", pkg]
    return [uv_path, "run", "--no-project", *with_args, "python", *argv]


def ensure(packages=_CORE_PACKAGES):
    """Re-exec under ``uv run`` iff a core dependency is missing and ``uv`` exists."""
    try:
        import yaml  # noqa: F401 — core-dep sentinel
        yaml_present = True
    except ImportError:
        yaml_present = False

    plan = _plan_reexec(
        packages,
        yaml_present=yaml_present,
        uv_path=_find_uv(),
        already_bootstrapped=os.environ.get(_GUARD_ENV) == "1",
        argv=sys.argv,
    )
    if plan is None:
        return
    os.environ[_GUARD_ENV] = "1"
    os.execvp(plan[0], plan)
