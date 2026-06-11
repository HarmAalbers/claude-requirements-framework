#!/usr/bin/env python3
"""Pure compliance evaluator for strict global preflight (ADR-020).

This module is intentionally PURE and dependency-injectable: every external
dependency (process env, PATH lookup, project directory) is passed in, so the
evaluator can be exercised with no real env / PATH / filesystem-state / network.
The only filesystem touches are existence/read checks under the injected
``project_dir`` (the config file and the opt-out sentinel).

Compliance is the conjunction of three invariants:
  1. ``.claude/requirements.local.yaml`` exists, parses, and declares at least
     one ENABLED requirement.
  2. Langfuse env is structurally valid: all five Layer-1 keys present and
     non-empty, and none of the six deprecated Layer-2 keys present.
  3. ``uv`` is on PATH.

Strict mode is exempt (inert) when kill-switched (``RF_STRICT_OFF=true``), when
the master switch is off (``strict_enabled=False``), or when the project carries
the ``.claude/.rf-optout`` sentinel. Fail-SAFE: callers wrap ``evaluate`` in
try/except and treat any exception as "allow".
"""

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

import yaml

# Five Layer-1 Langfuse env keys (the single-layer R5 design — ADR-019 amend).
LAYER1_KEYS = (
    "TRACE_TO_LANGFUSE",
    "LANGFUSE_PUBLIC_KEY",
    "LANGFUSE_SECRET_KEY",
    "LANGFUSE_HOST",
    "CC_LANGFUSE_MAX_CHARS",
)

# Six deprecated Layer-2 native-OTEL beta keys, removed in R5 hardening.
# NOTE: this is a deliberate parallel of ``_DEPRECATED_ENV_KEYS`` in
# ``scripts/setup_langfuse_tracing.py`` — the two sets must stay identical. The
# duplication is accepted to keep this module free of a script import.
DEPRECATED_L2_KEYS = (
    "CLAUDE_CODE_ENABLE_TELEMETRY",
    "CLAUDE_CODE_ENHANCED_TELEMETRY_BETA",
    "OTEL_TRACES_EXPORTER",
    "OTEL_EXPORTER_OTLP_PROTOCOL",
    "OTEL_EXPORTER_OTLP_ENDPOINT",
    "OTEL_EXPORTER_OTLP_HEADERS",
)

OPTOUT_RELPATH = Path(".claude") / ".rf-optout"
LOCAL_CFG_RELPATH = Path(".claude") / "requirements.local.yaml"

_SETUP_FIX = "python3 scripts/setup_langfuse_tracing.py --write"


@dataclass
class ComplianceResult:
    strict_active: bool  # is strict mode governing this project at all
    compliant: bool  # all invariants pass (only meaningful if strict_active)
    failures: list = field(default_factory=list)  # [(code, human_msg, fix_cmd)]


def is_kill_switched(env=None) -> bool:
    """True when ``RF_STRICT_OFF`` is set to ``true`` (case-insensitive)."""
    env = env if env is not None else os.environ
    return (env.get("RF_STRICT_OFF") or "").lower() == "true"


def is_opted_out(project_dir) -> bool:
    """True when the project carries the ``.claude/.rf-optout`` sentinel."""
    return (Path(project_dir) / OPTOUT_RELPATH).exists()


def evaluate(
    project_dir, *, strict_enabled: bool, env=None, which_fn=shutil.which
) -> ComplianceResult:
    """Top-level verdict.

    Fail-SAFE contract: callers wrap this in try/except and treat exceptions as
    "allow". The kill-switch is checked first so a master-switch / opt-out read
    can never strand a user who set ``RF_STRICT_OFF=true``.
    """
    env = env if env is not None else os.environ
    if is_kill_switched(env) or not strict_enabled or is_opted_out(project_dir):
        return ComplianceResult(strict_active=False, compliant=True)
    failures: list = []
    failures += _check_local_config(project_dir)
    failures += _check_langfuse_env(env)
    failures += _check_uv(which_fn)
    return ComplianceResult(
        strict_active=True, compliant=not failures, failures=failures
    )


def _check_local_config(project_dir) -> list:
    """Validate ``.claude/requirements.local.yaml``: exists, parses, ≥1 enabled."""
    cfg_path = Path(project_dir) / LOCAL_CFG_RELPATH
    if not cfg_path.exists():
        return [("no_config", "no .claude/requirements.local.yaml", "/req-init")]
    try:
        data = yaml.safe_load(cfg_path.read_text())
    except yaml.YAMLError:
        return [
            (
                "bad_config",
                "could not parse .claude/requirements.local.yaml",
                "fix .claude/requirements.local.yaml",
            )
        ]
    if not isinstance(data, dict):
        return [
            (
                "bad_config",
                "could not parse .claude/requirements.local.yaml",
                "fix .claude/requirements.local.yaml",
            )
        ]
    requirements = data.get("requirements") or {}
    if not isinstance(requirements, dict):
        return [
            (
                "bad_config",
                "could not parse .claude/requirements.local.yaml",
                "fix .claude/requirements.local.yaml",
            )
        ]
    enabled = any(
        isinstance(entry, dict) and bool(entry.get("enabled", False))
        for entry in requirements.values()
    )
    if not enabled:
        return [
            (
                "empty_config",
                "requirements.local.yaml has no enabled requirements",
                "/req-init",
            )
        ]
    return []


def _check_langfuse_env(env) -> list:
    """Validate Langfuse env: no deprecated Layer-2 keys, all Layer-1 present."""
    failures: list = []
    if any(key in env for key in DEPRECATED_L2_KEYS):
        failures.append(
            (
                "stale_layer2",
                "deprecated Layer-2 Langfuse keys present",
                _SETUP_FIX,
            )
        )
    if any(not (env.get(key) or "") for key in LAYER1_KEYS):
        failures.append(
            (
                "langfuse_env",
                "Langfuse env incomplete (missing/empty Layer-1 keys)",
                _SETUP_FIX,
            )
        )
    return failures


def _check_uv(which_fn) -> list:
    """Validate that ``uv`` resolves on PATH via the injected ``which_fn``."""
    if which_fn("uv") is None:
        return [("no_uv", "uv not on PATH", "install uv: https://docs.astral.sh/uv/")]
    return []
