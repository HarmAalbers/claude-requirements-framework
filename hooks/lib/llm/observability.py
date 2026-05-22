"""Langfuse + OpenInference instrumentation for Claude Agent SDK calls.

Public surface:
    init_observability() -> None  — idempotent on the success path. Reads
        LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY / LANGFUSE_HOST from env.
        If any are unset OR the required extras aren't installed, logs
        once at INFO level and returns WITHOUT permanently disabling — a
        later explicit call (e.g. after dotenv-loading at runtime) can
        still complete instrumentation.

State flags (R1 — arch-review revision):
    _disabled_logged — flips True once we've logged the "disabled" message.
        Prevents log spam on repeat calls when env vars stay unset.
    _instrumented — flips True only AFTER `instrument()` actually ran.
        Drives idempotence for the success path. Stays False after the
        "no env vars" or ImportError paths, allowing late init.

Module-name caveat (R2 — arch-review revision):
    `hooks.lib.llm.observability` and `llm.observability` resolve to the
    same physical file but appear in `sys.modules` as DIFFERENT entries
    when both import paths are exercised in one process — e.g.,
    hooks/test_requirements.py via `sys.path += ['hooks/lib']` vs
    tests/test_observability.py via repo-root sys.path. Each module copy
    has its own _instrumented / _disabled_logged flags. OpenInference's
    own BaseInstrumentor guard prevents double-monkey-patching, so this
    is safe — but the in-Python idempotence guarantee holds only
    per-module-name. Document and accept; do not try to reconcile in
    code.

Auto-init:
    The module body calls init_observability() once at the bottom, so
    `from hooks.lib.llm import observability` is enough to enable tracing
    when env vars are set. Callers may also call init_observability()
    explicitly after loading env from a .env file — both paths are valid.

Honest scope (R10 — arch-review revision):
    We instrument `claude_agent_sdk` only. OpenInference docs recommend
    pairing this with `instrumentation-anthropic` for child-span coverage
    of internal Anthropic API calls (retries, output_format re-prompting),
    but ADR-016 removed direct Anthropic SDK usage in favor of the bundled
    CLI subprocess. The visible spans therefore cover the outer query()
    boundary only — no internal-retry breakdown. Revisit if/when an
    API-key code path is added.

Design: .claude/plans/variant3/11-langfuse-self-host-otel.md
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_disabled_logged = False
_instrumented = False


def _read_langfuse_config() -> tuple[str, str, str] | None:
    """Read the three LANGFUSE_* env vars.

    Returns (public_key, secret_key, host) if all are set, else None.
    Single responsibility: env-reading only. No logging side effects.
    """
    pk = os.getenv("LANGFUSE_PUBLIC_KEY")
    sk = os.getenv("LANGFUSE_SECRET_KEY")
    host = os.getenv("LANGFUSE_HOST")
    if pk and sk and host:
        return pk, sk, host
    return None


def _configure_otel_env(public_key: str, secret_key: str, host: str) -> None:
    """Populate OTLP env vars so `OTLPSpanExporter()` auto-configures from env.

    R9: this is Langfuse's documented integration pattern. We use
    `os.environ.setdefault` so a user who has pre-set their own OTel
    config (e.g., a dual-exporter setup pointing at both Langfuse and
    Phoenix) wins over our defaults.
    """
    from base64 import b64encode

    auth = b64encode(f"{public_key}:{secret_key}".encode()).decode()
    os.environ.setdefault(
        "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
        f"{host.rstrip('/')}/api/public/otel/v1/traces",
    )
    os.environ.setdefault(
        "OTEL_EXPORTER_OTLP_TRACES_HEADERS",
        f"Authorization=Basic {auth}",
    )
    os.environ.setdefault("OTEL_EXPORTER_OTLP_TRACES_PROTOCOL", "http/protobuf")


def _build_tracer_provider() -> Any:
    """Construct a TracerProvider whose OTLP exporter self-configures from env.

    R9: no explicit endpoint / headers / protocol args — they're discovered
    from the env vars set by `_configure_otel_env`. Cuts ~10 lines of manual
    construction and ~6 lines of duplicated string-building.

    R4: returns the provider for the caller to pass explicitly to
    `instrument()`, avoiding reliance on the OTel global.
    """
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
        OTLPSpanExporter,
    )
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    provider = TracerProvider()
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    return provider


def _install_claude_sdk_instrumentor(provider: Any) -> None:
    """Install the Claude Agent SDK instrumentor against the given provider.

    R4: passes `tracer_provider=provider` explicitly rather than relying on
    `trace.set_tracer_provider()` having been called. More robust per
    OpenInference upstream usage.
    """
    from openinference.instrumentation.claude_agent_sdk import (
        ClaudeAgentSDKInstrumentor,
    )
    ClaudeAgentSDKInstrumentor().instrument(tracer_provider=provider)


def init_observability() -> None:
    """Idempotent on the success path. See module docstring."""
    global _disabled_logged, _instrumented
    if _instrumented:
        return

    config = _read_langfuse_config()
    if config is None:
        if not _disabled_logged:
            logger.info(
                "Langfuse observability disabled "
                "(LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY / LANGFUSE_HOST unset)"
            )
            _disabled_logged = True
        return

    try:
        _configure_otel_env(*config)
        provider = _build_tracer_provider()
        _install_claude_sdk_instrumentor(provider)
    except ImportError as exc:
        # R3: no separate probe — let helpers' imports surface here.
        if not _disabled_logged:
            logger.info(
                "Langfuse observability disabled (install with: "
                "pip install -e '.[llm]'). Missing: %s",
                exc.name or exc,
            )
            _disabled_logged = True
        return
    except Exception as exc:  # noqa: BLE001 — intentional: fail-open
        # Per R1, instrumentation didn't run — _disabled_logged guards the
        # log so repeat calls (e.g. once per worker spawn when Langfuse is
        # unreachable) don't spam INFO lines; _instrumented stays False so
        # the next call can retry once the underlying problem is fixed
        # (e.g. Langfuse becomes reachable).
        if not _disabled_logged:
            if os.getenv("LANGFUSE_DEBUG") == "1":
                logger.exception("Langfuse observability failed to initialize")
            else:
                logger.info(
                    "Langfuse observability failed to initialize: %s "
                    "(set LANGFUSE_DEBUG=1 for traceback)",
                    exc,
                )
            _disabled_logged = True
        return

    # ONLY now — after instrument() has actually run — set the success flag.
    _instrumented = True


init_observability()
