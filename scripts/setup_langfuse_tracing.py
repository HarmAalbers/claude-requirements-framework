#!/usr/bin/env python3
"""Opt a project into R5 Langfuse tracing by generating its env block.

Generates the 11-key env block (Layer 1: TRACE_TO_LANGFUSE Stop hook;
Layer 2: native OTEL beta traces) that points Claude Code at the
self-hosted Langfuse instance, and either prints it as JSON (default)
or merges it into the project's gitignored ``.claude/settings.local.json``
(``--write``). In ``--write`` mode the script also warms the uv cache for
the vendored ``hooks/_langfuse_hook.py`` so the first real Stop-hook run
doesn't pay dependency-resolution latency.

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
import base64
import json
import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

REQUIRED_VARS = ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_HOST")
SETTINGS_RELPATH = Path(".claude") / "settings.local.json"


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
    """Build the 11-key env block (Layer 1 Stop hook + Layer 2 OTEL beta)."""
    pk = creds["LANGFUSE_PUBLIC_KEY"]
    sk = creds["LANGFUSE_SECRET_KEY"]
    host = creds["LANGFUSE_HOST"].rstrip("/")
    basic = base64.b64encode(f"{pk}:{sk}".encode()).decode()
    return {
        "TRACE_TO_LANGFUSE": "true",
        "LANGFUSE_PUBLIC_KEY": pk,
        "LANGFUSE_SECRET_KEY": sk,
        "LANGFUSE_HOST": host,
        "CC_LANGFUSE_MAX_CHARS": "100000",
        "CLAUDE_CODE_ENABLE_TELEMETRY": "1",
        "CLAUDE_CODE_ENHANCED_TELEMETRY_BETA": "1",
        "OTEL_TRACES_EXPORTER": "otlp",
        "OTEL_EXPORTER_OTLP_PROTOCOL": "http/protobuf",
        "OTEL_EXPORTER_OTLP_ENDPOINT": f"{host}/api/public/otel",
        "OTEL_EXPORTER_OTLP_HEADERS": (
            f"Authorization=Basic {basic},x-langfuse-ingestion-version=4"
        ),
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
    else:
        print(json.dumps({"env": env_block}, indent=2))
        print(
            "Paste the block above (which contains your credentials) into your "
            "project's .claude/settings.local.json (or re-run with --write).",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
