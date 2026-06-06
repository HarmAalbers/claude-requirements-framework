#!/usr/bin/env python3
"""Tests for hooks.lib.llm.tracing.review_session — Step 18b.

`tracing.py` is stateless with a deferred import, so both paths are exercised
purely by manipulating sys.modules — no module reload needed (arch-review #10
note: the fresh_observability_module dance only applied while review_session
lived in the stateful observability.py).

Run: python3 tests/test_tracing.py
"""

import sys
import types
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from hooks.lib.llm import tracing


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
            for name, m in self.failed_tests:
                print(f"  {name}: {m}")
            return 1
        return 0


def test_noop_when_openinference_absent(runner):
    """Setting sys.modules['openinference.instrumentation'] = None makes the
    deferred `from ... import using_attributes` raise ImportError; the CM must
    swallow it and still run the body."""
    print("\n[fail-open no-op]")
    ran = {"body": False}
    with patch.dict(sys.modules, {"openinference.instrumentation": None}):
        with tracing.review_session("sess-1", "code-reviewer"):
            ran["body"] = True
    runner.test("body runs even when openinference import fails", ran["body"])


def test_binds_session_and_tags_when_present(runner):
    print("\n[binds attributes]")
    captured = {}

    @contextmanager
    def fake_using_attributes(**kwargs):
        captured.update(kwargs)
        yield

    fake_mod = types.ModuleType("openinference.instrumentation")
    fake_mod.using_attributes = fake_using_attributes

    body_ran = {"v": False}
    with patch.dict(sys.modules,
                    {"openinference.instrumentation": fake_mod}):
        with tracing.review_session("sess-xyz", "appsec-auditor"):
            body_ran["v"] = True

    runner.test("body runs inside the binding", body_ran["v"])
    runner.test("session_id propagated",
                captured.get("session_id") == "sess-xyz",
                f"got {captured.get('session_id')!r}")
    runner.test("worker tag present",
                "worker:appsec-auditor" in captured.get("tags", []),
                f"tags={captured.get('tags')!r}")
    runner.test("feature tag present",
                "feature:review" in captured.get("tags", []),
                f"tags={captured.get('tags')!r}")


def test_tags_reflect_worker_name(runner):
    """Different worker names produce different worker:<name> tags."""
    print("\n[per-worker tag]")
    captured = {}

    @contextmanager
    def fake_using_attributes(**kwargs):
        captured.update(kwargs)
        yield

    fake_mod = types.ModuleType("openinference.instrumentation")
    fake_mod.using_attributes = fake_using_attributes

    with patch.dict(sys.modules,
                    {"openinference.instrumentation": fake_mod}):
        with tracing.review_session("s", "aggregator"):
            pass
    runner.test("aggregator tag reflects the name",
                "worker:aggregator" in captured.get("tags", []),
                f"tags={captured.get('tags')!r}")


if __name__ == "__main__":
    runner = TestRunner()
    test_noop_when_openinference_absent(runner)
    test_binds_session_and_tags_when_present(runner)
    test_tags_reflect_worker_name(runner)
    sys.exit(runner.summary())
