#!/usr/bin/env python3
"""Tests for hooks.lib.llm.workers.code_reviewer — Step 10.

Mocks `query` and `ResultMessage` inside the worker module so no real SDK
calls happen and no real budget ledger is touched. Mirrors the mocking
pattern from tests/test_claude_wrapper.py.

Run: python3 tests/test_code_reviewer_worker.py
"""

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

# Optional heavy dep: the V3 worker / claude-wrapper modules this suite exercises
# eager-import the Claude Agent SDK. CI installs only the light llm extras
# (pyyaml/pydantic/jinja2), so skip cleanly instead of crashing when the SDK is
# absent — mirrors the optional-dep skip pattern in hooks/test_requirements.py.
try:
    import claude_agent_sdk  # noqa: F401
except ModuleNotFoundError as e:
    print(f"   ⊘ skipped: optional dep absent ({e.name})")
    sys.exit(0)


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


def _import_worker_module():
    import importlib
    import hooks.lib.llm.workers.code_reviewer as mod
    return importlib.reload(mod)


VALID_REPORT = {
    "agent": "code-reviewer",
    "scope": "HEAD",
    "findings": [
        {
            "severity": "CRITICAL",
            "file": "api/auth.py",
            "line": 11,
            "category": "security",
            "title": "SQL injection via string concat",
            "body": "Username is concatenated directly into the query.",
            "suggested_fix": "Use parameterized queries.",
            "confidence": 0.95,
        }
    ],
    "summary": "One critical SQL injection in authenticate().",
}


def test_review_returns_review_report(runner):
    print("\n[success path]")
    worker = _import_worker_module()
    result_msg = SimpleNamespace(
        subtype="success", structured_output=VALID_REPORT)
    captured = {}

    async def fake_query(*args, prompt=None, options=None, **kw):
        captured["prompt"] = prompt
        captured["options"] = options
        for m in [result_msg]:
            yield m

    async def run():
        with patch.object(worker, "query", fake_query):
            with patch.object(worker, "ResultMessage", SimpleNamespace):
                return await worker.review(diff="--- a/x\n+++ b/x",
                                           scope="HEAD")

    report = asyncio.run(run())
    runner.test("returns a ReviewReport", report.agent == "code-reviewer",
                f"agent={report.agent!r}")
    runner.test("findings parsed", len(report.findings) == 1,
                f"got {len(report.findings)}")
    runner.test("scope round-trips into prompt",
                "HEAD" in (captured["prompt"] or ""))
    runner.test("diff included in prompt",
                "--- a/x" in (captured["prompt"] or ""))


def test_review_passes_output_format_and_no_tools(runner):
    print("\n[options shape]")
    worker = _import_worker_module()
    result_msg = SimpleNamespace(
        subtype="success", structured_output=VALID_REPORT)
    captured = {}

    async def fake_query(*args, prompt=None, options=None, **kw):
        captured["options"] = options
        yield result_msg

    async def run():
        with patch.object(worker, "query", fake_query):
            with patch.object(worker, "ResultMessage", SimpleNamespace):
                return await worker.review(diff="d", scope="s")

    asyncio.run(run())
    opts = captured["options"]
    runner.test("allowed_tools is empty list",
                getattr(opts, "allowed_tools", None) == [])
    of = getattr(opts, "output_format", None)
    runner.test("output_format is json_schema",
                isinstance(of, dict) and of.get("type") == "json_schema",
                f"got {of}")
    runner.test("output_format schema is for ReviewReport",
                isinstance(of, dict)
                and "findings" in of["schema"].get("properties", {}),
                f"schema keys: {of['schema'].keys() if of else 'none'}")


def test_review_labels_options_with_agent_name(runner):
    print("\n[agent label for budget]")
    worker = _import_worker_module()
    result_msg = SimpleNamespace(
        subtype="success", structured_output=VALID_REPORT)
    captured = {}

    async def fake_query(*args, prompt=None, options=None, **kw):
        captured["options"] = options
        yield result_msg

    async def run():
        with patch.object(worker, "query", fake_query):
            with patch.object(worker, "ResultMessage", SimpleNamespace):
                return await worker.review(diff="d", scope="s")

    asyncio.run(run())
    runner.test("options.agent == 'code-reviewer' for budget label",
                getattr(captured["options"], "agent", None) == "code-reviewer",
                f"got {getattr(captured['options'], 'agent', '<missing>')!r}")


def test_review_raises_on_error_subtype(runner):
    print("\n[error_max_structured_output_retries]")
    worker = _import_worker_module()
    err_msg = SimpleNamespace(
        subtype="error_max_structured_output_retries",
        structured_output=None,
    )

    async def fake_query(*args, prompt=None, options=None, **kw):
        yield err_msg

    raised = []

    async def run():
        with patch.object(worker, "query", fake_query):
            with patch.object(worker, "ResultMessage", SimpleNamespace):
                try:
                    await worker.review(diff="d", scope="s")
                except RuntimeError as e:
                    raised.append(str(e))

    asyncio.run(run())
    runner.test("raises RuntimeError on error subtype", len(raised) == 1)
    runner.test("error mentions subtype",
                bool(raised) and "error_max_structured_output_retries"
                in raised[0],
                f"msg={raised[0] if raised else '<none>'}")


def test_review_raises_on_empty_success(runner):
    print("\n[success subtype but empty structured_output]")
    worker = _import_worker_module()
    empty_msg = SimpleNamespace(subtype="success", structured_output=None)

    async def fake_query(*args, prompt=None, options=None, **kw):
        yield empty_msg

    raised = []

    async def run():
        with patch.object(worker, "query", fake_query):
            with patch.object(worker, "ResultMessage", SimpleNamespace):
                try:
                    await worker.review(diff="d", scope="s")
                except RuntimeError as e:
                    raised.append(str(e))

    asyncio.run(run())
    runner.test("raises RuntimeError on empty success", len(raised) == 1)
    runner.test("message distinguishes empty output from a failed subtype",
                bool(raised) and "empty structured_output" in raised[0],
                f"msg={raised[0] if raised else '<none>'}")
    runner.test("message does NOT mislabel it as 'failed: subtype'",
                bool(raised) and "failed: subtype" not in raised[0],
                f"msg={raised[0] if raised else '<none>'}")


def test_review_raises_when_no_result_message(runner):
    print("\n[no ResultMessage]")
    worker = _import_worker_module()
    non_result = SimpleNamespace(some="thing")

    async def fake_query(*args, prompt=None, options=None, **kw):
        yield non_result
        yield non_result

    raised = []

    class Distinct:
        """Distinct sentinel so isinstance(non_result, Distinct) is False."""
        pass

    async def run():
        with patch.object(worker, "query", fake_query):
            with patch.object(worker, "ResultMessage", Distinct):
                try:
                    await worker.review(diff="d", scope="s")
                except RuntimeError as e:
                    raised.append(str(e))

    asyncio.run(run())
    runner.test("raises RuntimeError when no ResultMessage seen",
                len(raised) == 1)
    runner.test("error mentions 'no ResultMessage'",
                bool(raised) and "no ResultMessage" in raised[0],
                f"msg={raised[0] if raised else '<none>'}")


def test_review_skips_non_result_messages(runner):
    print("\n[non-result messages ignored before result]")
    worker = _import_worker_module()
    non_result = "not-a-result"  # plain str, won't match SimpleNamespace type
    result_msg = SimpleNamespace(
        subtype="success", structured_output=VALID_REPORT)

    async def fake_query(*args, prompt=None, options=None, **kw):
        yield non_result
        yield non_result
        yield result_msg

    async def run():
        with patch.object(worker, "query", fake_query):
            with patch.object(worker, "ResultMessage", SimpleNamespace):
                return await worker.review(diff="d", scope="s")

    report = asyncio.run(run())
    runner.test("review consumes pre-result messages and still returns",
                report.agent == "code-reviewer")


if __name__ == "__main__":
    runner = TestRunner()
    test_review_returns_review_report(runner)
    test_review_passes_output_format_and_no_tools(runner)
    test_review_labels_options_with_agent_name(runner)
    test_review_raises_on_error_subtype(runner)
    test_review_raises_on_empty_success(runner)
    test_review_raises_when_no_result_message(runner)
    test_review_skips_non_result_messages(runner)
    sys.exit(runner.summary())
