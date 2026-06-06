#!/usr/bin/env python3
"""Test suite for hooks/lib/llm/eval.py (Step 15).

Strategy (from the locked Step 15 plan):
    - Pure deterministic logic (FindingMatch, compute_finding_match,
      GoldenCase round-trip) exercised directly with no infra dep.
    - score_case exercised with an injected async `judge` callable so the
      test never imports Ragas or the SDK. The smoke spike exercises the
      real Ragas-backed judge end-to-end.
    - post_to_langfuse mocked via env var presence + a stub client.

If pydantic is missing (no `[llm]` extras), the whole suite skips cleanly.

Run with: python3 tests/test_eval.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

try:
    import pydantic  # noqa: F401
except ImportError:
    print("SKIP: pydantic not installed. `pip install -e '.[llm]'` to enable.")
    sys.exit(0)

from hooks.lib.llm.eval import (
    EvalScore,
    FindingMatch,
    GoldenCase,
    compute_finding_match,
    post_to_langfuse,
    score_case,
)
from hooks.lib.llm.schemas import ReviewFinding, ReviewReport


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
                print(f"  - {name}: {msg}")
            return 1
        return 0


# ---------- fixtures ----------


def _finding(file: str, line: int, category: str, severity: str = "IMPORTANT") -> ReviewFinding:
    return ReviewFinding(
        severity=severity,  # type: ignore[arg-type]
        file=file,
        line=line,
        category=category,  # type: ignore[arg-type]
        title="x" * 20,
        body="some body",
        confidence=0.8,
    )


def _report(findings: list[ReviewFinding]) -> ReviewReport:
    return ReviewReport(
        agent="code-reviewer",
        scope="test",
        findings=findings,
        summary="test summary",
    )


def _case(reference: dict, goal: str = "find the planted bug") -> GoldenCase:
    return GoldenCase(
        id="test_case_001",
        agent="code-reviewer",
        diff_path="golden_set/diffs/001.diff",
        reference_findings=[reference],
        reference_goal=goal,
    )


# ---------- FindingMatch pure logic ----------


def test_finding_match_perfect_score(r: TestRunner) -> None:
    fm = FindingMatch(file_match=True, line_match=True, category_match=True)
    r.test("all three flags True → score 1.0", fm.score == 1.0)


def test_finding_match_partial(r: TestRunner) -> None:
    fm = FindingMatch(file_match=True, line_match=True, category_match=False)
    r.test("two of three → score ≈ 0.67", round(fm.score, 2) == 0.67)


def test_finding_match_zero(r: TestRunner) -> None:
    fm = FindingMatch(file_match=False, line_match=False, category_match=False)
    r.test("all flags False → score 0.0", fm.score == 0.0)


def test_finding_match_single_flag(r: TestRunner) -> None:
    fm = FindingMatch(file_match=True, line_match=False, category_match=False)
    r.test("one of three → score ≈ 0.33", round(fm.score, 2) == 0.33)


# ---------- compute_finding_match against ReviewReport ----------


def test_no_findings_returns_all_false(r: TestRunner) -> None:
    report = _report([])
    fm = compute_finding_match(
        report, {"file": "api/auth.py", "line": 42, "category": "security"}
    )
    r.test("empty report → all flags False", fm.score == 0.0)


def test_exact_match_returns_perfect_score(r: TestRunner) -> None:
    report = _report([_finding("api/auth.py", 42, "security", "CRITICAL")])
    fm = compute_finding_match(
        report, {"file": "api/auth.py", "line": 42, "category": "security"}
    )
    r.test("exact match → score 1.0", fm.score == 1.0)


def test_line_within_tolerance_matches(r: TestRunner) -> None:
    report = _report([_finding("api/auth.py", 44, "security")])
    fm = compute_finding_match(
        report,
        {"file": "api/auth.py", "line": 42, "category": "security"},
        line_tolerance=2,
    )
    r.test("line within ±2 → line_match True", fm.line_match is True)
    r.test("perfect file + line + category → score 1.0", fm.score == 1.0)


def test_line_outside_tolerance_no_line_match(r: TestRunner) -> None:
    report = _report([_finding("api/auth.py", 50, "security")])
    fm = compute_finding_match(
        report,
        {"file": "api/auth.py", "line": 42, "category": "security"},
        line_tolerance=2,
    )
    r.test("line outside ±2 → line_match False", fm.line_match is False)
    r.test(
        "file + category still match → score 0.67",
        round(fm.score, 2) == 0.67,
    )


def test_wrong_file_no_match(r: TestRunner) -> None:
    report = _report([_finding("wrong.py", 42, "security")])
    fm = compute_finding_match(
        report, {"file": "api/auth.py", "line": 42, "category": "security"}
    )
    r.test("wrong file → file_match False", fm.file_match is False)


def test_wrong_category_partial_match(r: TestRunner) -> None:
    report = _report([_finding("api/auth.py", 42, "logic")])
    fm = compute_finding_match(
        report, {"file": "api/auth.py", "line": 42, "category": "security"}
    )
    r.test("wrong category → category_match False", fm.category_match is False)
    r.test(
        "file + line match → score 0.67", round(fm.score, 2) == 0.67
    )


def test_best_match_across_many_findings(r: TestRunner) -> None:
    report = _report([
        _finding("noise1.py", 10, "style"),
        _finding("noise2.py", 20, "performance"),
        _finding("api/auth.py", 42, "security"),
        _finding("noise3.py", 30, "test"),
    ])
    fm = compute_finding_match(
        report, {"file": "api/auth.py", "line": 42, "category": "security"}
    )
    r.test(
        "best-of-N: perfect match present in noisy report → score 1.0",
        fm.score == 1.0,
    )


def test_best_match_prefers_higher_score(r: TestRunner) -> None:
    report = _report([
        _finding("api/auth.py", 100, "logic"),
        _finding("api/auth.py", 42, "logic"),
    ])
    fm = compute_finding_match(
        report, {"file": "api/auth.py", "line": 42, "category": "security"}
    )
    r.test(
        "picks the 0.67 candidate over the 0.33 candidate",
        round(fm.score, 2) == 0.67,
    )


# ---------- GoldenCase loading ----------


def test_golden_case_round_trip(r: TestRunner) -> None:
    case = _case({"file": "x.py", "line": 1, "category": "logic"})
    js = case.model_dump_json()
    parsed = GoldenCase.model_validate_json(js)
    r.test("GoldenCase round-trips through JSON", parsed.id == case.id)
    r.test(
        "reference_findings survive round-trip",
        parsed.reference_findings == case.reference_findings,
    )


def test_golden_case_requires_id(r: TestRunner) -> None:
    try:
        GoldenCase.model_validate(
            {"agent": "x", "diff_path": "y", "reference_findings": [],
             "reference_goal": "z"}
        )
        r.test("missing id raises ValidationError", False, "no exception")
    except Exception:
        r.test("missing id raises ValidationError", True)


# ---------- score_case with injected judge ----------


def test_score_case_without_judge_skips_goal_accuracy(r: TestRunner) -> None:
    case = _case({"file": "api/auth.py", "line": 42, "category": "security"})
    report = _report([_finding("api/auth.py", 42, "security", "CRITICAL")])
    score = asyncio.run(score_case(case, report, judge=None))
    r.test("EvalScore.case_id preserved", score.case_id == case.id)
    r.test(
        "agent_goal_accuracy is None when judge is None",
        score.agent_goal_accuracy is None,
    )
    r.test(
        "finding_match still computed without judge",
        score.finding_match is not None and score.finding_match.score == 1.0,
    )


def test_score_case_with_mock_judge_returns_value(r: TestRunner) -> None:
    case = _case({"file": "api/auth.py", "line": 42, "category": "security"})
    report = _report([_finding("api/auth.py", 42, "security", "CRITICAL")])

    async def fake_judge(rep: ReviewReport, ref: str) -> float:
        return 0.75

    score = asyncio.run(score_case(case, report, judge=fake_judge))
    r.test(
        "agent_goal_accuracy passes through from judge",
        score.agent_goal_accuracy == 0.75,
    )
    r.test(
        "finding_match still computed alongside judge",
        score.finding_match is not None and score.finding_match.score == 1.0,
    )


def test_score_case_judge_failure_fails_open(r: TestRunner) -> None:
    case = _case({"file": "api/auth.py", "line": 42, "category": "security"})
    report = _report([_finding("api/auth.py", 42, "security", "CRITICAL")])

    async def broken_judge(rep: ReviewReport, ref: str) -> float:
        raise RuntimeError("judge exploded")

    score = asyncio.run(score_case(case, report, judge=broken_judge))
    r.test(
        "broken judge → agent_goal_accuracy None (fail-open)",
        score.agent_goal_accuracy is None,
    )
    r.test(
        "broken judge does not block FindingMatch",
        score.finding_match is not None and score.finding_match.score == 1.0,
    )


def test_score_case_records_judge_model(r: TestRunner) -> None:
    case = _case({"file": "x.py", "line": 1, "category": "logic"})
    report = _report([])
    score = asyncio.run(score_case(case, report, judge=None, judge_model="claude-haiku-4-5"))
    r.test("judge_model recorded", score.judge_model == "claude-haiku-4-5")


# ---------- post_to_langfuse ----------


def test_post_to_langfuse_returns_false_without_env(r: TestRunner) -> None:
    saved = os.environ.pop("LANGFUSE_PUBLIC_KEY", None)
    try:
        ok = post_to_langfuse(trace_id="abc", name="finding_match", value=0.67)
        r.test("returns False when env var missing", ok is False)
    finally:
        if saved:
            os.environ["LANGFUSE_PUBLIC_KEY"] = saved


def test_post_to_langfuse_no_trace_id_returns_false(r: TestRunner) -> None:
    os.environ["LANGFUSE_PUBLIC_KEY"] = "fake_key_for_test"
    try:
        ok = post_to_langfuse(trace_id=None, name="finding_match", value=0.67)
        r.test("returns False when trace_id is None", ok is False)
    finally:
        os.environ.pop("LANGFUSE_PUBLIC_KEY", None)


def test_post_to_langfuse_calls_create_score(r: TestRunner) -> None:
    """The client path must call create_score (langfuse v3), not removed score()."""
    import types

    calls: dict = {}

    class FakeLangfuse:
        def create_score(self, **kwargs):
            calls["create_score"] = kwargs

        def score(self, **kwargs):  # the removed v2 API — must not be used
            calls["score"] = kwargs
            raise AttributeError("score() removed in langfuse v3")

        def flush(self):
            calls["flushed"] = True

    fake_mod = types.ModuleType("langfuse")
    fake_mod.Langfuse = FakeLangfuse
    saved_mod = sys.modules.get("langfuse")
    sys.modules["langfuse"] = fake_mod
    os.environ["LANGFUSE_PUBLIC_KEY"] = "fake_key_for_test"
    try:
        ok = post_to_langfuse(trace_id="t1", name="finding_match", value=0.67)
        r.test("returns True on successful create_score", ok is True)
        r.test(
            "create_score called with right kwargs",
            calls.get("create_score")
            == {"trace_id": "t1", "name": "finding_match", "value": 0.67},
            str(calls.get("create_score")),
        )
        r.test("removed score() was NOT called", "score" not in calls)
        r.test("client was flushed", calls.get("flushed") is True)
    finally:
        os.environ.pop("LANGFUSE_PUBLIC_KEY", None)
        if saved_mod is not None:
            sys.modules["langfuse"] = saved_mod
        else:
            sys.modules.pop("langfuse", None)


# ---------- EvalScore serialization ----------


def test_eval_score_json_round_trip(r: TestRunner) -> None:
    score = EvalScore(
        case_id="001",
        finding_match=FindingMatch(file_match=True, line_match=False, category_match=True),
        agent_goal_accuracy=0.85,
        judge_model="claude-haiku-4-5",
        ran_at="2026-05-23T18:00:00+00:00",
    )
    js = score.model_dump_json()
    parsed = EvalScore.model_validate_json(js)
    r.test("EvalScore round-trips through JSON", parsed.case_id == "001")
    r.test(
        "FindingMatch survives round-trip",
        parsed.finding_match is not None
        and abs(parsed.finding_match.score - 2/3) < 1e-9,
    )


def main() -> int:
    print("Running eval tests...")
    r = TestRunner()

    test_finding_match_perfect_score(r)
    test_finding_match_partial(r)
    test_finding_match_zero(r)
    test_finding_match_single_flag(r)

    test_no_findings_returns_all_false(r)
    test_exact_match_returns_perfect_score(r)
    test_line_within_tolerance_matches(r)
    test_line_outside_tolerance_no_line_match(r)
    test_wrong_file_no_match(r)
    test_wrong_category_partial_match(r)
    test_best_match_across_many_findings(r)
    test_best_match_prefers_higher_score(r)

    test_golden_case_round_trip(r)
    test_golden_case_requires_id(r)

    test_score_case_without_judge_skips_goal_accuracy(r)
    test_score_case_with_mock_judge_returns_value(r)
    test_score_case_judge_failure_fails_open(r)
    test_score_case_records_judge_model(r)

    test_post_to_langfuse_returns_false_without_env(r)
    test_post_to_langfuse_no_trace_id_returns_false(r)
    test_post_to_langfuse_calls_create_score(r)

    test_eval_score_json_round_trip(r)

    return r.summary()


if __name__ == "__main__":
    sys.exit(main())
