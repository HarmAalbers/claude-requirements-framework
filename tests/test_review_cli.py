#!/usr/bin/env python3
"""Tests for hooks.lib.llm.review_cli.run_review — Step 18c.

Patches the module-level `run_tool_gate` and `fanout_review` so the three
branches are exercised without real linters or SDK calls (arch-review #1):
gate-abort (no fan-out), all-workers-fail message, and a successful render.

Run: python3 tests/test_review_cli.py
"""

import asyncio
import sys
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from hooks.lib.llm import review_cli
from hooks.lib.llm.schemas import ReviewReport
from hooks.lib.llm.workers.fanout import FanoutResult


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


def _report():
    return ReviewReport.model_validate({
        "agent": "review-aggregator", "scope": "HEAD",
        "findings": [{
            "severity": "IMPORTANT", "file": "a.py", "line": 3,
            "category": "logic", "title": "A long enough finding title",
            "body": "desc.", "suggested_fix": "fix.", "confidence": 0.8,
        }],
        "summary": "one important finding",
    })


def test_gate_abort_skips_fanout(runner):
    print("\n[tool-gate block → abort, no fan-out]")
    fanout_called = {"v": False}

    async def fake_fanout(*a, **k):
        fanout_called["v"] = True
        raise AssertionError("fan-out must not run when the gate blocks")

    async def run():
        with patch.object(review_cli, "run_tool_gate",
                          lambda files: ["a.py:1:1: F401 unused import"]), \
                patch.object(review_cli, "fanout_review", fake_fanout):
            return await review_cli.run_review("diff", "HEAD", ["a.py"], {})

    md = asyncio.run(run())
    runner.test("fan-out NOT called", fanout_called["v"] is False)
    runner.test("abort verdict present", "FIX TOOL ERRORS FIRST" in md)
    runner.test("gate error surfaced", "F401" in md)


def test_all_workers_fail_message(runner):
    print("\n[all workers fail → human-readable message]")

    async def fake_fanout(diff, scope, workers=None):
        raise RuntimeError("fanout_review: all workers failed")

    async def run():
        with patch.object(review_cli, "run_tool_gate", lambda files: []), \
                patch.object(review_cli, "fanout_review", fake_fanout):
            return await review_cli.run_review("diff", "HEAD", ["a.py"], {})

    md = asyncio.run(run())
    runner.test("FAILED header", "V3 Review — FAILED" in md)
    runner.test("suggests narrower scope", "narrower scope" in md)


def test_success_renders_report_with_footer(runner):
    print("\n[success → rendered report + session footer]")

    async def fake_fanout(diff, scope, workers=None):
        return FanoutResult(_report(), "sess-abc", 9,
                            {"compliance-auditor": "RuntimeError: empty"})

    async def run():
        with patch.object(review_cli, "run_tool_gate", lambda files: []), \
                patch.object(review_cli, "fanout_review", fake_fanout):
            return await review_cli.run_review("diff", "HEAD", ["a.py"], {})

    md = asyncio.run(run())
    runner.test("renders the finding", "A long enough finding title" in md)
    runner.test("verdict present", "**Verdict**:" in md)
    runner.test("session_id in footer", "session_id: sess-abc" in md)
    runner.test("survivor ratio in footer", "survivors: 9/10" in md,
                f"footer missing ratio: {md[-120:]!r}")
    runner.test("failed worker shown via renderer",
                "Workers that did not complete" in md)


def test_aggregator_failure_does_not_inflate_ratio(runner):
    print("\n[aggregator failure → degraded section, honest ratio]")

    async def fake_fanout(diff, scope, workers=None):
        # all 10 workers survived; the aggregator itself failed → fallback
        return FanoutResult(_report(), "sess-agg", 10, {},
                            "RuntimeError: aggregator failed")

    async def run():
        with patch.object(review_cli, "run_tool_gate", lambda files: []), \
                patch.object(review_cli, "fanout_review", fake_fanout):
            return await review_cli.run_review("diff", "HEAD", ["a.py"], {})

    md = asyncio.run(run())
    runner.test("ratio is 10/10 (aggregator NOT counted as a worker)",
                "survivors: 10/10" in md, f"footer: {md[-120:]!r}")
    runner.test("aggregator-degraded section shown",
                "## Aggregator degraded" in md)


if __name__ == "__main__":
    runner = TestRunner()
    test_gate_abort_skips_fanout(runner)
    test_all_workers_fail_message(runner)
    test_success_renders_report_with_footer(runner)
    test_aggregator_failure_does_not_inflate_ratio(runner)
    sys.exit(runner.summary())
