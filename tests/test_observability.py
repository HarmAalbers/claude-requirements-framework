#!/usr/bin/env python3
"""Test suite for hooks/lib/llm/observability.py — Step 11.

Follows the framework's TestRunner convention (see tests/test_schemas.py).
Run with: python3 tests/test_observability.py

Dependency-free: these tests never connect to a real Langfuse instance.
They verify env-var handling, ImportError swallowing, idempotency, and
log-once behavior.
"""

import io
import logging
import os
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))


class TestRunner:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.failed_tests: list[tuple[str, str]] = []

    def test(self, name: str, condition: bool, msg: str = ""):
        if condition:
            self.passed += 1
            print(f"  ✓ {name}")
        else:
            self.failed += 1
            self.failed_tests.append((name, msg))
            print(f"  ✗ {name}: {msg}")

    def summary(self) -> int:
        total = self.passed + self.failed
        print(f"\n{self.passed}/{total} passed")
        if self.failed:
            print("\nFailures:")
            for name, msg in self.failed_tests:
                print(f"  {name}: {msg}")
            return 1
        return 0


@contextmanager
def fresh_observability_module():
    """Reload observability with the current env, isolated from other tests.

    Note (R2 dual-import caveat): popping `sys.modules['hooks.lib.llm.observability']`
    is not enough — Python's `from hooks.lib.llm import observability` reads the
    `observability` attribute off the parent package (which keeps a reference to
    the OLD module object even after the sys.modules pop). We must also delete
    that attribute so the next import truly re-executes the module body. Same
    cleanup on the way out.
    """
    import hooks.lib.llm as _parent
    sys.modules.pop("hooks.lib.llm.observability", None)
    if hasattr(_parent, "observability"):
        delattr(_parent, "observability")
    from hooks.lib.llm import observability  # noqa: F401  reload-on-purpose
    try:
        yield observability
    finally:
        sys.modules.pop("hooks.lib.llm.observability", None)
        if hasattr(_parent, "observability"):
            delattr(_parent, "observability")


def test_disabled_when_no_public_key(runner: TestRunner):
    print("\ntest_disabled_when_no_public_key")
    env_without_keys = {k: v for k, v in os.environ.items()
                         if not k.startswith("LANGFUSE_")}
    with patch.dict(os.environ, env_without_keys, clear=True):
        with fresh_observability_module() as obs:
            result = obs.init_observability()
            runner.test(
                "returns None when no env vars",
                result is None,
                f"expected None, got {result!r}",
            )
            # R1: _disabled_logged flips True to suppress log spam on repeat calls
            runner.test(
                "_disabled_logged = True after env-vars-unset path",
                obs._disabled_logged is True,
                f"expected True, got {obs._disabled_logged!r}",
            )
            # R1: _instrumented stays False so a later explicit init (after
            # dotenv loading) can still complete instrumentation.
            runner.test(
                "_instrumented stays False (allows late init after env loads)",
                obs._instrumented is False,
                f"expected False, got {obs._instrumented!r}",
            )


def test_disabled_on_import_error(runner: TestRunner):
    print("\ntest_disabled_on_import_error")
    fake_env = {
        "LANGFUSE_PUBLIC_KEY": "pk-test",
        "LANGFUSE_SECRET_KEY": "sk-test",
        "LANGFUSE_HOST": "http://localhost:3000",
    }
    # Force the openinference import to fail by aliasing it to a missing module
    with patch.dict(os.environ, fake_env, clear=True), \
         patch.dict(sys.modules,
                    {"openinference.instrumentation.claude_agent_sdk": None}):
        with fresh_observability_module() as obs:
            result = obs.init_observability()
            runner.test(
                "returns None when openinference unavailable",
                result is None,
                f"expected None, got {result!r}",
            )
            # R1: ImportError path also uses _disabled_logged guard,
            # NOT a permanent _instrumented flip — allows recovery
            # if user installs the extras later in the same process.
            runner.test(
                "_disabled_logged = True after ImportError",
                obs._disabled_logged is True,
                f"expected True, got {obs._disabled_logged!r}",
            )
            runner.test(
                "_instrumented stays False on ImportError",
                obs._instrumented is False,
                f"expected False, got {obs._instrumented!r}",
            )


def test_init_idempotent(runner: TestRunner):
    print("\ntest_init_idempotent")
    with patch.dict(os.environ, {}, clear=True):
        with fresh_observability_module() as obs:
            obs.init_observability()
            # second call should be a no-op for logging but still NOT
            # set _instrumented (env vars are missing — late init must
            # remain possible).
            obs.init_observability()
            runner.test(
                "_disabled_logged stays True across repeated calls",
                obs._disabled_logged is True,
                f"got {obs._disabled_logged!r}",
            )
            # R1: idempotence MUST NOT extend to instrumented=True on the
            # env-vars-missing path. If a dotenv loader populates env later,
            # a third call should succeed.
            runner.test(
                "_instrumented stays False (late init still allowed)",
                obs._instrumented is False,
                f"got {obs._instrumented!r}",
            )


def test_logs_disabled_message_once(runner: TestRunner):
    print("\ntest_logs_disabled_message_once")
    log_stream = io.StringIO()
    handler = logging.StreamHandler(log_stream)
    handler.setLevel(logging.INFO)

    obs_logger = logging.getLogger("hooks.lib.llm.observability")
    obs_logger.addHandler(handler)
    obs_logger.setLevel(logging.INFO)

    try:
        with patch.dict(os.environ, {}, clear=True):
            with fresh_observability_module() as obs:
                obs.init_observability()
                obs.init_observability()
        log_output = log_stream.getvalue()
        disabled_count = log_output.count("Langfuse observability disabled")
        runner.test(
            "logs the disabled message exactly once",
            disabled_count == 1,
            f"expected 1, got {disabled_count} (output: {log_output!r})",
        )
    finally:
        obs_logger.removeHandler(handler)


def test_module_import_triggers_init(runner: TestRunner):
    print("\ntest_module_import_triggers_init")
    # R1: subprocess isolates from main test process module cache.
    # With no LANGFUSE_* env: import must succeed, _disabled_logged must
    # be True (log emitted once), _instrumented must STAY FALSE (so any
    # caller that loads env later can still init successfully).
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from hooks.lib.llm import observability; "
            "assert observability._disabled_logged is True, "
            "    f'_disabled_logged={observability._disabled_logged}'; "
            "assert observability._instrumented is False, "
            "    f'_instrumented={observability._instrumented}'",
        ],
        cwd=REPO_ROOT,
        env={k: v for k, v in os.environ.items()
             if not k.startswith("LANGFUSE_")},
        capture_output=True,
        text=True,
    )
    runner.test(
        "subprocess imports cleanly without LANGFUSE env vars (R1 flags correct)",
        result.returncode == 0,
        f"stdout={result.stdout!r} stderr={result.stderr!r}",
    )


def test_logs_init_failure_with_traceback_only_when_debug_set(runner: TestRunner):
    print("\ntest_logs_init_failure_with_traceback_only_when_debug_set")
    # This test forces a failure AFTER the OTel provider is built, so it needs
    # the real opentelemetry stack present; absent it, init_observability() bails
    # earlier on the missing-dep ImportError branch and never reaches the
    # traceback path under test. CI installs only the light llm extras, so skip
    # this one case cleanly (the other tests here are genuinely dep-free).
    try:
        import opentelemetry  # noqa: F401
    except ModuleNotFoundError as e:
        print(f"   ⊘ skipped: optional dep absent ({e.name})")
        return
    fake_env = {
        "LANGFUSE_PUBLIC_KEY": "pk-test",
        "LANGFUSE_SECRET_KEY": "sk-test",
        "LANGFUSE_HOST": "http://localhost:3000",
    }

    def force_raise_during_init(*_a, **_kw):
        raise RuntimeError("simulated init failure")

    log_stream = io.StringIO()
    handler = logging.StreamHandler(log_stream)
    obs_logger = logging.getLogger("hooks.lib.llm.observability")
    obs_logger.addHandler(handler)
    obs_logger.setLevel(logging.INFO)

    try:
        # First: no debug flag → no traceback.
        # R2 caveat: `fresh_observability_module` returns a fresh module
        # object (we delete the parent's attribute to force a real re-
        # execution of the module body), so `patch.object` must be applied
        # to the freshly-loaded module — patching the dotted path BEFORE
        # the reload would target the discarded module.
        with patch.dict(os.environ, fake_env, clear=True):
            with fresh_observability_module() as obs:
                with patch.object(obs, "_install_claude_sdk_instrumentor",
                                   force_raise_during_init):
                    # R1: reset BOTH flags so this test isolates from the
                    # module-import auto-init that just ran during reload
                    # (which hit ImportError or success depending on whether
                    # `openinference` extras are installed in the current
                    # env — the patched call must be the one that exercises
                    # the LANGFUSE_DEBUG branch we are asserting on).
                    obs._disabled_logged = False
                    obs._instrumented = False
                    obs.init_observability()
        no_debug_output = log_stream.getvalue()
        runner.test(
            "without LANGFUSE_DEBUG: no 'Traceback' in log",
            "Traceback" not in no_debug_output,
            f"got: {no_debug_output!r}",
        )

        # Second: LANGFUSE_DEBUG=1 → traceback included
        log_stream.truncate(0)
        log_stream.seek(0)
        with patch.dict(os.environ, {**fake_env, "LANGFUSE_DEBUG": "1"}, clear=True):
            with fresh_observability_module() as obs:
                with patch.object(obs, "_install_claude_sdk_instrumentor",
                                   force_raise_during_init):
                    obs._disabled_logged = False
                    obs._instrumented = False
                    obs.init_observability()
        debug_output = log_stream.getvalue()
        runner.test(
            "with LANGFUSE_DEBUG=1: 'Traceback' present in log",
            "Traceback" in debug_output,
            f"got: {debug_output!r}",
        )
    finally:
        obs_logger.removeHandler(handler)


def test_atexit_handler_registered_on_success_path(runner: TestRunner):
    """Gap 1: success path must arm a shutdown handler so BatchSpanProcessor flushes."""
    print("\ntest_atexit_handler_registered_on_success_path")
    fake_env = {
        "LANGFUSE_PUBLIC_KEY": "pk-test",
        "LANGFUSE_SECRET_KEY": "sk-test",
        "LANGFUSE_HOST": "http://localhost:3000",
    }

    class _StubProvider:
        def __init__(self):
            self.shutdown_called = 0

        def add_span_processor(self, _proc):
            pass

        def shutdown(self):
            self.shutdown_called += 1

    stub = _StubProvider()

    with patch.dict(os.environ, fake_env, clear=True):
        with fresh_observability_module() as obs:
            obs._provider = None
            obs._instrumented = False
            obs._disabled_logged = False
            with patch.object(obs, "_build_tracer_provider", return_value=stub), \
                 patch.object(obs, "_install_claude_sdk_instrumentor"), \
                 patch.object(obs, "atexit") as mock_atexit:
                obs.init_observability()

                runner.test(
                    "success path captures provider into module global",
                    obs._provider is stub,
                    f"got {obs._provider!r}",
                )
                runner.test(
                    "success path registers exactly one atexit handler",
                    mock_atexit.register.call_count == 1,
                    f"got {mock_atexit.register.call_count} register call(s)",
                )
                runner.test(
                    "registered handler is _shutdown_provider_on_exit",
                    mock_atexit.register.call_args[0][0]
                    is obs._shutdown_provider_on_exit,
                    f"got {mock_atexit.register.call_args!r}",
                )

            # Invoke the handler directly — it should call provider.shutdown.
            obs._shutdown_provider_on_exit()
            runner.test(
                "_shutdown_provider_on_exit calls provider.shutdown",
                stub.shutdown_called == 1,
                f"got {stub.shutdown_called} shutdown call(s)",
            )


def test_atexit_handler_swallows_shutdown_errors(runner: TestRunner):
    """Gap 1: atexit pipeline must not blow up on a flaky shutdown."""
    print("\ntest_atexit_handler_swallows_shutdown_errors")

    class _ExplodingProvider:
        def shutdown(self):
            raise RuntimeError("simulated shutdown failure")

    with fresh_observability_module() as obs:
        obs._provider = _ExplodingProvider()
        raised = False
        try:
            obs._shutdown_provider_on_exit()
        except Exception:  # noqa: BLE001 — this is the property we're testing
            raised = True
        runner.test(
            "_shutdown_provider_on_exit swallows provider.shutdown() exceptions",
            raised is False,
            "exception escaped the handler",
        )


def test_atexit_handler_safe_when_provider_unset(runner: TestRunner):
    """Gap 1: handler must no-op when init never reached the success path."""
    print("\ntest_atexit_handler_safe_when_provider_unset")
    with fresh_observability_module() as obs:
        obs._provider = None
        raised = False
        try:
            obs._shutdown_provider_on_exit()
        except Exception:  # noqa: BLE001
            raised = True
        runner.test(
            "_shutdown_provider_on_exit no-ops cleanly when _provider is None",
            raised is False,
            "exception raised on the no-provider path",
        )


def test_detach_noise_filter_drops_only_detach_records(runner):
    import logging as _logging

    from hooks.lib.llm.observability import _DetachNoiseFilter
    f = _DetachNoiseFilter()
    detach = _logging.LogRecord("opentelemetry.context", _logging.ERROR, "p", 1,
                                "Failed to detach context", (), None)
    other = _logging.LogRecord("opentelemetry.context", _logging.ERROR, "p", 1,
                               "some genuine context error", (), None)
    runner.test("drops the benign 'Failed to detach context' record",
                f.filter(detach) is False)
    runner.test("keeps unrelated context errors",
                f.filter(other) is True)


if __name__ == "__main__":
    runner = TestRunner()
    test_disabled_when_no_public_key(runner)
    test_disabled_on_import_error(runner)
    test_init_idempotent(runner)
    test_logs_disabled_message_once(runner)
    test_module_import_triggers_init(runner)
    test_logs_init_failure_with_traceback_only_when_debug_set(runner)
    test_atexit_handler_registered_on_success_path(runner)
    test_atexit_handler_swallows_shutdown_errors(runner)
    test_atexit_handler_safe_when_provider_unset(runner)
    test_detach_noise_filter_drops_only_detach_records(runner)
    sys.exit(runner.summary())
