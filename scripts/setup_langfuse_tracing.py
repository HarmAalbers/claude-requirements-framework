#!/usr/bin/env python3
"""Opt a project into R5 Langfuse tracing by generating its env block.

Generates the 5-key Layer-1 env block (``TRACE_TO_LANGFUSE`` Stop hook +
credentials + ``CC_LANGFUSE_MAX_CHARS``) that points Claude Code at the
self-hosted Langfuse instance, and either prints it as JSON (default)
or merges it into the project's gitignored ``.claude/settings.local.json``
(``--write``). The former Layer-2 native-OTEL beta-trace keys are no longer
emitted; on ``--write`` any of those deprecated keys present in an existing
settings file are PRUNED (clean removal, no shim — see ADR-019).

In ``--write`` mode the script also warms the uv cache for the vendored
``hooks/_langfuse_hook.py`` so the first real Stop-hook run doesn't pay
dependency-resolution latency, and registers project-scoped model-price
definitions (``sync_langfuse_models.register_models``) so traces get
non-zero cost. A model-sync failure only warns — creds are already
written and the sync can be re-run. Pass ``--skip-model-sync`` to suppress
it (used by the test suite to stay offline).

Credentials are resolved from the process environment first, falling back
to ``infra/.env`` in the current working directory (per-key precedence:
env wins).

Loud-failure stance: unlike the fail-open library/hook code this script
exercises, setup scripts HARD-FAIL on missing prerequisites — every
missing credential is named on stderr and the exit code is nonzero, and
an unreachable Langfuse host (unless ``--skip-ping``) is fatal. The one
deliberate exception: a failed uv cache warm only warns loudly, because
by then the credentials are already written and tracing will still work.

Design doc: .claude/plans/2026-06-07-r5-stop-hook-observability-design.md

Usage:
    python3 scripts/setup_langfuse_tracing.py              # print env block
    python3 scripts/setup_langfuse_tracing.py --write      # write settings
    python3 scripts/setup_langfuse_tracing.py --skip-ping  # skip health check
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

REQUIRED_VARS = ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_HOST")
SETTINGS_RELPATH = Path(".claude") / "settings.local.json"

# Layer-2 native-OTEL beta-trace keys, removed in R5 hardening (ADR-019). These
# are PRUNED from an existing settings file on --write — clean removal, no shim.
# This is an EXACT-NAME set: it deliberately does NOT match the V3 review stack's
# signal-specific OTEL_EXPORTER_OTLP_TRACES_* keys (different namespace), so a
# prefix match must never be substituted here.
_DEPRECATED_ENV_KEYS = frozenset(
    {
        "CLAUDE_CODE_ENABLE_TELEMETRY",
        "CLAUDE_CODE_ENHANCED_TELEMETRY_BETA",
        "OTEL_TRACES_EXPORTER",
        "OTEL_EXPORTER_OTLP_PROTOCOL",
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "OTEL_EXPORTER_OTLP_HEADERS",
    }
)


def _resolve_creds():
    """Resolve the three Langfuse credentials: process env, then infra/.env.

    Hard-fails (exit 1) naming EVERY missing variable on stderr.
    Returns a fully-populated dict keyed by REQUIRED_VARS; hard-exits before
    returning if any are missing.

    4th hand-rolled infra/.env reader (stdlib-only constraint; siblings:
    sync_prompts_to_langfuse.py, sync_golden_set_to_langfuse.py,
    review_cli.py). Extraction trigger RETIRED: sync_langfuse_models.py REUSES
    this function (imports it) rather than adding a 5th reader.
    """
    creds = {}
    env_file = Path.cwd() / "infra" / ".env"
    file_vars = {}
    if env_file.is_file():
        try:
            env_file_text = env_file.read_text()
        except OSError as exc:
            print(f"ERROR: cannot read/write {env_file}: {exc}", file=sys.stderr)
            sys.exit(1)
        for line in env_file_text.splitlines():
            line = line.strip().removeprefix("export ")
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            file_vars[key] = value

    for var in REQUIRED_VARS:
        value = os.environ.get(var) or file_vars.get(var)
        if value:
            creds[var] = value

    missing = [var for var in REQUIRED_VARS if var not in creds]
    if missing:
        print(
            "ERROR: missing required Langfuse credentials "
            "(set in environment or infra/.env):",
            file=sys.stderr,
        )
        for var in missing:
            print(f"  - {var}", file=sys.stderr)
        sys.exit(1)
    return creds


def _ping(host):
    """Hard-fail if the Langfuse host doesn't answer its health endpoint."""
    url = f"{host.rstrip('/')}/api/public/health"
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            if response.status >= 400:
                raise OSError(f"HTTP {response.status}")
    except Exception as exc:
        print(
            f"ERROR: Langfuse at {host} is not reachable ({exc}).\n"
            "Hint: start it with `docker compose -f infra/docker-compose.yml up -d`",
            file=sys.stderr,
        )
        sys.exit(1)


def _build_env_block(creds):
    """Build the 5-key Layer-1 env block (TRACE_TO_LANGFUSE Stop hook + creds).

    Layer-2 native-OTEL beta-trace keys are no longer emitted (ADR-019); R5 is
    the single enriched trace source.
    """
    pk = creds["LANGFUSE_PUBLIC_KEY"]
    sk = creds["LANGFUSE_SECRET_KEY"]
    host = creds["LANGFUSE_HOST"].rstrip("/")
    return {
        "TRACE_TO_LANGFUSE": "true",
        "LANGFUSE_PUBLIC_KEY": pk,
        "LANGFUSE_SECRET_KEY": sk,
        "LANGFUSE_HOST": host,
        "CC_LANGFUSE_MAX_CHARS": "100000",
    }


def _write_settings(env_block):
    """Merge env_block into .claude/settings.local.json (cwd-relative)."""
    settings_path = Path.cwd() / SETTINGS_RELPATH
    settings = {}
    if settings_path.is_file():
        problem = None
        try:
            settings = json.loads(settings_path.read_text())
        except OSError as exc:
            print(f"ERROR: cannot read/write {settings_path}: {exc}", file=sys.stderr)
            sys.exit(1)
        except json.JSONDecodeError as exc:
            problem = str(exc)
        if problem is None and not isinstance(settings, dict):
            problem = "top-level is not an object"
        if problem is not None:
            print(
                f"ERROR: existing {settings_path} is not valid JSON "
                f"({problem}) — fix or delete it, then re-run",
                file=sys.stderr,
            )
            sys.exit(1)
    merged_env = dict(settings.get("env", {}))
    merged_env.update(env_block)
    # Prune the deprecated Layer-2 OTEL keys (exact-name match only — must not
    # touch the V3 stack's OTEL_EXPORTER_OTLP_TRACES_* namespace).
    for key in _DEPRECATED_ENV_KEYS:
        merged_env.pop(key, None)
    settings["env"] = merged_env
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        settings_path.write_text(json.dumps(settings, indent=2) + "\n")
    except OSError as exc:
        print(f"ERROR: cannot read/write {settings_path}: {exc}", file=sys.stderr)
        sys.exit(1)
    return settings_path


def _warm_uv_cache():
    """Pre-resolve the Stop hook's uv script deps; loud warning on failure."""
    uv = shutil.which("uv")
    if uv is None:
        print(
            "WARNING: uv not found on PATH — cache not warmed; "
            "first traced turn will resolve dependencies",
            file=sys.stderr,
        )
        return
    repo_root = Path(__file__).resolve().parent.parent
    hook = repo_root / "hooks" / "_langfuse_hook.py"
    env = dict(os.environ, CC_LANGFUSE_FAIL_OPEN="true")
    print("Warming uv cache for the Stop hook...")
    try:
        subprocess.run(
            [uv, "run", "--script", str(hook)],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            env=env,
            timeout=120,
            check=True,
        )
    except Exception as exc:
        hint = ""
        stderr_text = getattr(exc, "stderr", None)
        if isinstance(stderr_text, bytes):
            stderr_text = stderr_text.decode("utf-8", errors="replace")
        if isinstance(stderr_text, str) and stderr_text.strip():
            hint = f"\n  uv stderr: ...{stderr_text.strip()[-200:]}"
        print(
            f"WARNING: uv cache warm failed ({exc}). Credentials are written "
            "and tracing will still work, but the first Stop-hook run will "
            f"resolve dependencies on the fly. Re-run manually:\n"
            f"  uv run --script {hook}{hint}",
            file=sys.stderr,
        )
        return
    print("uv cache warmed (Stop hook dependencies resolved).")


def _sync_models(creds):
    """Register project-scoped model-price defs; warn (never fatal) on failure.

    Creds are already written by this point, so a sync failure must not abort
    setup — it only warns, and the sync can be re-run. Mirrors the uv-cache-warm
    stance.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from sync_langfuse_models import LangfuseModelSyncError, register_models

    print("Registering project-scoped model-price definitions...")
    try:
        actions = register_models(creds)
    except LangfuseModelSyncError as exc:
        print(
            f"WARNING: model-price sync failed ({exc}). Credentials are written "
            "and tracing will still work, but trace cost may read $0 until the "
            "models are registered. Re-run manually:\n"
            "  python3 scripts/sync_langfuse_models.py",
            file=sys.stderr,
        )
        return
    for line in actions:
        print(f"  {line}")
    print("Model-price definitions registered.")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--write",
        action="store_true",
        help="merge the env block into .claude/settings.local.json",
    )
    parser.add_argument(
        "--skip-ping",
        action="store_true",
        help="skip the Langfuse health check",
    )
    parser.add_argument(
        "--skip-model-sync",
        action="store_true",
        help="skip registering project-scoped model-price definitions",
    )
    args = parser.parse_args()

    creds = _resolve_creds()
    if not args.skip_ping:
        _ping(creds["LANGFUSE_HOST"])
    env_block = _build_env_block(creds)

    if args.write:
        settings_path = _write_settings(env_block)
        print(
            f"Wrote {len(env_block)} env vars to {SETTINGS_RELPATH} "
            f"({settings_path})"
        )
        _warm_uv_cache()
        if not args.skip_model_sync:
            _sync_models(creds)
    else:
        print(json.dumps({"env": env_block}, indent=2))
        print(
            "Paste the block above (which contains your credentials) into your "
            "project's .claude/settings.local.json (or re-run with --write).\n"
            "NOTE: model-price definitions were NOT registered (print mode). "
            "Run with --write to register them, or cost will read $0 on traces.",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
