#!/usr/bin/env python3
"""Tests for the solid-reviewer and appsec-auditor workers — Step 18b.

Mocks `query` and `ResultMessage` inside each worker module so no real SDK
calls happen and no real budget ledger is touched. Mirrors the 6-test contract
in tests/test_code_reviewer_worker.py, plus a 7th worker-identity assertion on
the system prompt (arch-review #9) to catch a template/system copy-paste.

Run: python3 tests/test_review_workers.py
"""

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
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
            for name, m in self.failed_tests:
                print(f"  {name}: {m}")
            return 1
        return 0


def _reload(module_path: str):
    import importlib
    mod = importlib.import_module(module_path)
    return importlib.reload(mod)


def _valid_report(agent: str) -> dict:
    return {
        "agent": agent,
        "scope": "HEAD",
        "findings": [
            {
                "severity": "IMPORTANT",
                "file": "api/x.py",
                "line": 12,
                "category": "security" if agent == "appsec-auditor"
                else "complexity",
                "title": "An example finding title here",
                "body": "A concrete one-sentence explanation.",
                "suggested_fix": "Do the safe thing.",
                "confidence": 0.8,
            }
        ],
        "summary": f"One finding from {agent}.",
    }


# (module_path, expected agent label, system-prompt identity substring)
WORKERS = [
    ("hooks.lib.llm.workers.solid_reviewer", "solid-reviewer", "solid-reviewer"),
    ("hooks.lib.llm.workers.appsec_auditor", "appsec-auditor", "appsec-auditor"),
    ("hooks.lib.llm.workers.silent_failure_hunter", "silent-failure-hunter",
     "silent-failure-hunter"),
    ("hooks.lib.llm.workers.test_analyzer", "test-analyzer", "test-analyzer"),
    ("hooks.lib.llm.workers.backward_compatibility_checker",
     "backward-compatibility-checker", "backward-compatibility-checker"),
    ("hooks.lib.llm.workers.type_design_analyzer", "type-design-analyzer",
     "type-design-analyzer"),
]


def test_returns_review_report(runner):
    print("\n[success path]")
    for path, agent, _ in WORKERS:
        worker = _reload(path)
        report_dict = _valid_report(agent)
        result_msg = SimpleNamespace(subtype="success",
                                     structured_output=report_dict)
        captured = {}

        async def fake_query(*args, prompt=None, options=None, **kw):
            captured["prompt"] = prompt
            captured["options"] = options
            yield result_msg

        async def run():
            with patch.object(worker, "query", fake_query):
                with patch.object(worker, "ResultMessage", SimpleNamespace):
                    return await worker.review(diff="--- a/x\n+++ b/x",
                                               scope="HEAD")

        report = asyncio.run(run())
        runner.test(f"{agent}: returns a ReviewReport", report.agent == agent,
                    f"agent={report.agent!r}")
        runner.test(f"{agent}: findings parsed", len(report.findings) == 1,
                    f"got {len(report.findings)}")
        runner.test(f"{agent}: scope round-trips into prompt",
                    "HEAD" in (captured["prompt"] or ""))
        runner.test(f"{agent}: diff included in prompt",
                    "--- a/x" in (captured["prompt"] or ""))


def test_passes_output_format_and_no_tools(runner):
    print("\n[options shape]")
    for path, agent, _ in WORKERS:
        worker = _reload(path)
        result_msg = SimpleNamespace(subtype="success",
                                     structured_output=_valid_report(agent))
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
        runner.test(f"{agent}: allowed_tools is empty list",
                    getattr(opts, "allowed_tools", None) == [])
        of = getattr(opts, "output_format", None)
        runner.test(f"{agent}: output_format is json_schema",
                    isinstance(of, dict) and of.get("type") == "json_schema",
                    f"got {of}")
        runner.test(f"{agent}: output_format schema is for ReviewReport",
                    isinstance(of, dict)
                    and "findings" in of["schema"].get("properties", {}),
                    f"schema keys: {of['schema'].keys() if of else 'none'}")


def test_labels_options_with_agent_name(runner):
    print("\n[agent label for budget]")
    for path, agent, _ in WORKERS:
        worker = _reload(path)
        result_msg = SimpleNamespace(subtype="success",
                                     structured_output=_valid_report(agent))
        captured = {}

        async def fake_query(*args, prompt=None, options=None, **kw):
            captured["options"] = options
            yield result_msg

        async def run():
            with patch.object(worker, "query", fake_query):
                with patch.object(worker, "ResultMessage", SimpleNamespace):
                    return await worker.review(diff="d", scope="s")

        asyncio.run(run())
        runner.test(f"{agent}: options.agent == {agent!r} for budget label",
                    getattr(captured["options"], "agent", None) == agent,
                    f"got {getattr(captured['options'], 'agent', '<missing>')!r}")


def test_raises_on_error_subtype(runner):
    print("\n[error subtype]")
    for path, agent, _ in WORKERS:
        worker = _reload(path)
        err_msg = SimpleNamespace(
            subtype="error_max_structured_output_retries",
            structured_output=None)

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
        runner.test(f"{agent}: raises RuntimeError on error subtype",
                    len(raised) == 1)
        runner.test(f"{agent}: error prefix carries the agent name",
                    bool(raised) and raised[0].startswith(f"{agent} failed:"),
                    f"msg={raised[0] if raised else '<none>'}")


def test_raises_when_no_result_message(runner):
    print("\n[no ResultMessage]")
    for path, agent, _ in WORKERS:
        worker = _reload(path)

        class Distinct:
            pass

        async def fake_query(*args, prompt=None, options=None, **kw):
            yield SimpleNamespace(some="thing")

        raised = []

        async def run():
            with patch.object(worker, "query", fake_query):
                with patch.object(worker, "ResultMessage", Distinct):
                    try:
                        await worker.review(diff="d", scope="s")
                    except RuntimeError as e:
                        raised.append(str(e))

        asyncio.run(run())
        runner.test(f"{agent}: raises when no ResultMessage seen",
                    len(raised) == 1)
        runner.test(f"{agent}: error mentions 'no ResultMessage'",
                    bool(raised) and "no ResultMessage" in raised[0],
                    f"msg={raised[0] if raised else '<none>'}")


def test_raises_on_empty_success(runner):
    print("\n[success subtype but empty structured_output]")
    for path, agent, _ in WORKERS:
        worker = _reload(path)
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
        runner.test(f"{agent}: raises on empty success", len(raised) == 1)
        runner.test(f"{agent}: message names empty structured_output",
                    bool(raised) and "empty structured_output" in raised[0],
                    f"msg={raised[0] if raised else '<none>'}")


def test_skips_non_result_messages(runner):
    print("\n[non-result messages ignored before result]")
    for path, agent, _ in WORKERS:
        worker = _reload(path)
        result_msg = SimpleNamespace(subtype="success",
                                     structured_output=_valid_report(agent))

        async def fake_query(*args, prompt=None, options=None, **kw):
            yield "not-a-result"
            yield "not-a-result"
            yield result_msg

        async def run():
            with patch.object(worker, "query", fake_query):
                with patch.object(worker, "ResultMessage", SimpleNamespace):
                    return await worker.review(diff="d", scope="s")

        report = asyncio.run(run())
        runner.test(f"{agent}: consumes pre-result messages and still returns",
                    report.agent == agent)


def test_system_prompt_identity(runner):
    """7th contract test (arch-review #9): a copy-paste of the code-reviewer
    system/template into another worker must be caught — each worker's system
    prompt must name its own identity."""
    print("\n[worker identity in system prompt]")
    for path, agent, identity in WORKERS:
        worker = _reload(path)
        captured = {}

        async def fake_query(*args, prompt=None, options=None, **kw):
            captured["options"] = options
            yield SimpleNamespace(subtype="success",
                                  structured_output=_valid_report(agent))

        async def run():
            with patch.object(worker, "query", fake_query):
                with patch.object(worker, "ResultMessage", SimpleNamespace):
                    return await worker.review(diff="d", scope="s")

        asyncio.run(run())
        sysprompt = getattr(captured["options"], "system_prompt", "") or ""
        runner.test(f"{agent}: system prompt names its own identity",
                    identity in sysprompt,
                    f"{identity!r} not in system_prompt={sysprompt!r}")
        runner.test(f"{agent}: system prompt is not the code-reviewer's",
                    "code-reviewer" not in sysprompt,
                    "system prompt leaked 'code-reviewer' identity")


if __name__ == "__main__":
    runner = TestRunner()
    test_returns_review_report(runner)
    test_passes_output_format_and_no_tools(runner)
    test_labels_options_with_agent_name(runner)
    test_raises_on_error_subtype(runner)
    test_raises_on_empty_success(runner)
    test_raises_when_no_result_message(runner)
    test_skips_non_result_messages(runner)
    test_system_prompt_identity(runner)
    sys.exit(runner.summary())
