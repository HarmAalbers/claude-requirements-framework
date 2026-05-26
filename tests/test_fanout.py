#!/usr/bin/env python3
"""Tests for hooks.lib.llm.workers.fanout — Step 18b.

Mocks the worker fns (injected via `workers=`), and patches the module-level
`aggregate` and `review_session` so no SDK calls happen. Covers: success,
partial failure (survivors aggregated), all-fail RuntimeError, and the same
session_id binding across every worker AND the aggregator (arch-review #11).

Run: python3 tests/test_fanout.py
"""

import asyncio
import sys
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from hooks.lib.llm.schemas import ReviewReport
from hooks.lib.llm.workers import fanout


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


def _report(agent: str) -> ReviewReport:
    return ReviewReport.model_validate({
        "agent": agent,
        "scope": "HEAD",
        "findings": [],
        "summary": f"report from {agent}",
    })


def _make_worker(agent: str):
    async def review(diff, scope):
        return _report(agent)
    return review


def _make_failing_worker(exc: Exception):
    async def review(diff, scope):
        raise exc
    return review


def _patches(recorded_sessions: list, aggregate_calls: list):
    """Patch review_session (recording (session_id, worker)) and aggregate
    (recording the reports it received, returning a unified report)."""

    @contextmanager
    def fake_review_session(session_id, worker):
        recorded_sessions.append((session_id, worker))
        yield

    async def fake_aggregate(reports):
        aggregate_calls.append(list(reports))
        return _report("review-aggregator")

    return (
        patch.object(fanout, "review_session", fake_review_session),
        patch.object(fanout, "aggregate", fake_aggregate),
    )


def test_success_all_three(runner):
    print("\n[success: 3 workers -> aggregate gets 3]")
    recorded, agg_calls = [], []
    workers = {
        "code-reviewer": _make_worker("code-reviewer"),
        "solid-reviewer": _make_worker("solid-reviewer"),
        "appsec-auditor": _make_worker("appsec-auditor"),
    }
    p_session, p_agg = _patches(recorded, agg_calls)

    async def run():
        with p_session, p_agg:
            return await fanout.fanout_review("diff", "HEAD", workers=workers)

    result = asyncio.run(run())
    runner.test("returns FanoutResult", isinstance(result, fanout.FanoutResult))
    runner.test("aggregate called once with 3 reports",
                len(agg_calls) == 1 and len(agg_calls[0]) == 3,
                f"agg_calls={[len(c) for c in agg_calls]}")
    runner.test("survivor_count == 3", result.survivor_count == 3,
                f"got {result.survivor_count}")
    runner.test("report is the aggregator's unified report",
                result.report.agent == "review-aggregator")
    runner.test("session_id is non-empty", bool(result.session_id))
    runner.test("no worker_errors when all succeed",
                result.worker_errors == {}, f"got {result.worker_errors}")


def test_partial_failure(runner):
    print("\n[partial: 1 of 3 fails -> aggregate gets 2]")
    recorded, agg_calls = [], []
    workers = {
        "code-reviewer": _make_worker("code-reviewer"),
        "solid-reviewer": _make_failing_worker(RuntimeError("boom")),
        "appsec-auditor": _make_worker("appsec-auditor"),
    }
    p_session, p_agg = _patches(recorded, agg_calls)

    async def run():
        with p_session, p_agg:
            return await fanout.fanout_review("diff", "HEAD", workers=workers)

    result = asyncio.run(run())
    runner.test("aggregate called with 2 survivors",
                len(agg_calls) == 1 and len(agg_calls[0]) == 2,
                f"agg_calls={[len(c) for c in agg_calls]}")
    runner.test("survivor_count == 2", result.survivor_count == 2,
                f"got {result.survivor_count}")
    survivors = {r.agent for r in agg_calls[0]}
    runner.test("the failed worker is excluded",
                survivors == {"code-reviewer", "appsec-auditor"},
                f"survivors={survivors}")
    runner.test("failed worker recorded in worker_errors",
                "solid-reviewer" in result.worker_errors,
                f"worker_errors={result.worker_errors}")
    runner.test("worker_errors message carries the exception text",
                "boom" in result.worker_errors.get("solid-reviewer", ""),
                f"worker_errors={result.worker_errors}")
    runner.test("survivors NOT in worker_errors",
                "code-reviewer" not in result.worker_errors
                and "appsec-auditor" not in result.worker_errors)


def test_aggregator_failure_falls_back_to_mechanical_merge(runner):
    print("\n[aggregator fails -> mechanical merge of survivors]")
    recorded = []
    workers = {
        "code-reviewer": _make_worker("code-reviewer"),
        "appsec-auditor": _make_worker("appsec-auditor"),
    }

    @contextmanager
    def fake_review_session(session_id, worker):
        recorded.append((session_id, worker))
        yield

    async def failing_aggregate(reports):
        raise RuntimeError("aggregator failed: subtype='success'")

    async def run():
        with patch.object(fanout, "review_session", fake_review_session), \
                patch.object(fanout, "aggregate", failing_aggregate):
            return await fanout.fanout_review("diff", "HEAD", workers=workers)

    result = asyncio.run(run())
    runner.test("still returns a FanoutResult (no raise)",
                isinstance(result, fanout.FanoutResult))
    runner.test("report is the labeled fallback",
                result.report.agent == "review-aggregator (fallback)",
                f"agent={result.report.agent!r}")
    runner.test("survivor findings preserved (concatenated)",
                len(result.report.findings)
                == sum(len(_report(a).findings) for a in
                       ("code-reviewer", "appsec-auditor")))
    runner.test("aggregator failure recorded in worker_errors",
                "aggregator" in result.worker_errors,
                f"worker_errors={result.worker_errors}")
    runner.test("survivor_count still reflects the 2 workers",
                result.survivor_count == 2, f"got {result.survivor_count}")


def test_all_fail_raises(runner):
    print("\n[all fail -> RuntimeError]")
    recorded, agg_calls = [], []
    workers = {
        "code-reviewer": _make_failing_worker(RuntimeError("a")),
        "solid-reviewer": _make_failing_worker(RuntimeError("b")),
    }
    p_session, p_agg = _patches(recorded, agg_calls)
    raised = []

    async def run():
        with p_session, p_agg:
            try:
                await fanout.fanout_review("diff", "HEAD", workers=workers)
            except RuntimeError as e:
                raised.append(str(e))

    asyncio.run(run())
    runner.test("raises RuntimeError when all workers fail", len(raised) == 1)
    runner.test("error says all workers failed",
                bool(raised) and "all workers failed" in raised[0],
                f"msg={raised[0] if raised else '<none>'}")
    runner.test("aggregate is NOT called when there are no survivors",
                len(agg_calls) == 0, f"agg_calls={len(agg_calls)}")


def test_same_session_id_across_workers_and_aggregator(runner):
    print("\n[one session_id binds workers + aggregator]")
    recorded, agg_calls = [], []
    workers = {
        "code-reviewer": _make_worker("code-reviewer"),
        "solid-reviewer": _make_worker("solid-reviewer"),
        "appsec-auditor": _make_worker("appsec-auditor"),
    }
    p_session, p_agg = _patches(recorded, agg_calls)

    async def run():
        with p_session, p_agg:
            return await fanout.fanout_review("diff", "HEAD", workers=workers)

    result = asyncio.run(run())
    session_ids = {sid for sid, _ in recorded}
    workers_bound = [w for _, w in recorded]
    runner.test("exactly one distinct session_id used",
                session_ids == {result.session_id},
                f"session_ids={session_ids}, result={result.session_id!r}")
    runner.test("all 3 workers + aggregator were bound (4 enters)",
                len(recorded) == 4, f"recorded={workers_bound}")
    runner.test("aggregator bound under the same session",
                "aggregator" in workers_bound, f"bound={workers_bound}")
    runner.test("each pilot worker bound once",
                set(workers_bound) == {"code-reviewer", "solid-reviewer",
                                       "appsec-auditor", "aggregator"},
                f"bound={workers_bound}")


if __name__ == "__main__":
    runner = TestRunner()
    test_success_all_three(runner)
    test_partial_failure(runner)
    test_aggregator_failure_falls_back_to_mechanical_merge(runner)
    test_all_fail_raises(runner)
    test_same_session_id_across_workers_and_aggregator(runner)
    sys.exit(runner.summary())
