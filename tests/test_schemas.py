#!/usr/bin/env python3
"""Test suite for hooks/lib/llm/schemas.py — V3 Pydantic output schemas.

Follows the framework's TestRunner convention (see hooks/test_diff_scope.py).
Run with: python3 tests/test_schemas.py

Covers per the Step 09 plan acceptance:
    * valid construction
    * validation errors on missing / invalid fields
    * JSON round-trip
    * Field(...) constraints fire
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from pydantic import ValidationError

from hooks.lib.llm.schemas import (
    HandoffResult,
    PlanIssue,
    PlanReport,
    RefactorVerdict,
    ReviewFinding,
    ReviewReport,
)


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


def _valid_finding() -> ReviewFinding:
    return ReviewFinding(
        severity="CRITICAL",
        file="auth.py",
        line=42,
        category="security",
        title="SQL injection in user lookup",
        body="String-built SQL query allows arbitrary clauses.",
        suggested_fix="Use parameterized query.",
        confidence=0.95,
    )


def test_review_finding_valid(r: TestRunner) -> None:
    f = _valid_finding()
    r.test("ReviewFinding constructs with valid data", f.severity == "CRITICAL")
    r.test("ReviewFinding line preserved", f.line == 42)
    r.test("ReviewFinding suggested_fix preserved", f.suggested_fix is not None)


def test_review_finding_optional_fix(r: TestRunner) -> None:
    f = ReviewFinding(
        severity="SUGGESTION",
        file="x.py",
        line=1,
        category="style",
        title="Naming could be clearer",
        body="Consider renaming.",
        confidence=0.3,
    )
    r.test("ReviewFinding allows omitted suggested_fix", f.suggested_fix is None)


def test_review_finding_missing_required(r: TestRunner) -> None:
    try:
        ReviewFinding(  # type: ignore[call-arg]
            severity="CRITICAL",
            file="x.py",
            line=1,
            category="security",
            # title omitted
            body="b",
            confidence=0.5,
        )
        r.test("ReviewFinding rejects missing title", False, "no ValidationError raised")
    except ValidationError as e:
        r.test("ReviewFinding rejects missing title", "title" in str(e))


def test_review_finding_invalid_severity(r: TestRunner) -> None:
    try:
        ReviewFinding(
            severity="WHENEVER",  # type: ignore[arg-type]
            file="x.py",
            line=1,
            category="security",
            title="A reasonably long title",
            body="b",
            confidence=0.5,
        )
        r.test("ReviewFinding rejects invalid severity", False, "no ValidationError raised")
    except ValidationError:
        r.test("ReviewFinding rejects invalid severity", True)


def test_review_finding_line_constraint(r: TestRunner) -> None:
    try:
        ReviewFinding(
            severity="CRITICAL",
            file="x.py",
            line=0,
            category="security",
            title="A reasonably long title",
            body="b",
            confidence=0.5,
        )
        r.test("ReviewFinding rejects line<1", False, "no ValidationError raised")
    except ValidationError:
        r.test("ReviewFinding rejects line<1", True)


def test_review_finding_confidence_constraint(r: TestRunner) -> None:
    try:
        ReviewFinding(
            severity="CRITICAL",
            file="x.py",
            line=1,
            category="security",
            title="A reasonably long title",
            body="b",
            confidence=1.5,
        )
        r.test("ReviewFinding rejects confidence>1.0", False, "no ValidationError raised")
    except ValidationError:
        r.test("ReviewFinding rejects confidence>1.0", True)


def test_review_finding_title_min_length(r: TestRunner) -> None:
    try:
        ReviewFinding(
            severity="CRITICAL",
            file="x.py",
            line=1,
            category="security",
            title="short",  # < 10 chars
            body="b",
            confidence=0.5,
        )
        r.test("ReviewFinding rejects title shorter than 10 chars", False)
    except ValidationError:
        r.test("ReviewFinding rejects title shorter than 10 chars", True)


def test_review_report_round_trip(r: TestRunner) -> None:
    report = ReviewReport(
        agent="code-reviewer",
        scope="HEAD",
        findings=[_valid_finding()],
        summary="One finding.",
    )
    payload = report.model_dump_json()
    restored = ReviewReport.model_validate_json(payload)
    r.test("ReviewReport JSON round-trip preserves agent", restored.agent == "code-reviewer")
    r.test("ReviewReport JSON round-trip preserves findings count", len(restored.findings) == 1)
    r.test(
        "ReviewReport JSON round-trip preserves nested severity",
        restored.findings[0].severity == "CRITICAL",
    )


def test_plan_issue_and_report(r: TestRunner) -> None:
    issue = PlanIssue(
        severity="IMPORTANT",
        category="adr",
        title="Plan contradicts ADR-014",
        body="See refactor-orchestration bundled-skill ADR.",
        suggested_plan_edit="Reference ADR-014 explicitly.",
    )
    report = PlanReport(
        agent="adr-guardian", issues=[issue], plan_acceptable=False, summary="One ADR conflict."
    )
    r.test("PlanReport composes PlanIssue list", len(report.issues) == 1)
    r.test("PlanReport plan_acceptable flag honored", report.plan_acceptable is False)


def test_plan_issue_invalid_category(r: TestRunner) -> None:
    try:
        PlanIssue(
            severity="CRITICAL",
            category="security",  # type: ignore[arg-type]
            title="t",
            body="b",
        )
        r.test("PlanIssue rejects out-of-set category", False)
    except ValidationError:
        r.test("PlanIssue rejects out-of-set category", True)


def test_refactor_verdict(r: TestRunner) -> None:
    v = RefactorVerdict(
        verdict="DONE",
        chunk_id="chunk-3",
        files_touched=["hooks/lib/llm/schemas.py"],
        notes="Schemas populated.",
    )
    r.test("RefactorVerdict accepts DONE verdict", v.verdict == "DONE")
    r.test("RefactorVerdict next_steps optional", v.next_steps is None)


def test_handoff_result_valid(r: TestRunner) -> None:
    h = HandoffResult(target="arch-review", rationale="Plan phase unsatisfied.")
    r.test("HandoffResult accepts arch-review target", h.target == "arch-review")


def test_handoff_result_ship(r: TestRunner) -> None:
    h = HandoffResult(target="ship", rationale="All session gates satisfied.")
    r.test("HandoffResult accepts ship target", h.target == "ship")


def test_handoff_result_open_target(r: TestRunner) -> None:
    # `target` is an open `str` now (config-driven phases), not a Literal: any
    # custom/non-default phase name validates. The semantic guard (clamping an
    # out-of-vocabulary target back to the input phase) lives in
    # supervisor.route(), not in the schema. So a non-default target is ACCEPTED.
    h = HandoffResult(target="finishing-a-development-branch", rationale="x")
    r.test(
        "HandoffResult accepts an open/custom target string",
        h.target == "finishing-a-development-branch",
    )


def test_handoff_result_writing_plans(r: TestRunner) -> None:
    h = HandoffResult(
        target="writing-plans",
        rationale="Plan-write phase: design ready, plan not yet written.",
    )
    r.test(
        "HandoffResult accepts writing-plans target",
        h.target == "writing-plans",
    )


def test_handoff_result_all_targets_distinct(r: TestRunner) -> None:
    """All 7 workflow targets construct cleanly and round-trip via JSON."""
    targets = [
        "brainstorm",
        "writing-plans",
        "arch-review",
        "execute-plan",
        "deep-review",
        "refactor-orchestrate",
        "ship",
    ]
    all_ok = True
    for t in targets:
        h = HandoffResult(target=t, rationale=f"route to {t}")  # type: ignore[arg-type]
        roundtrip = HandoffResult.model_validate_json(h.model_dump_json())
        if roundtrip.target != t:
            all_ok = False
            break
    r.test(
        "HandoffResult accepts all 7 targets and JSON-round-trips",
        all_ok,
        f"failed on one of {targets}",
    )


def main() -> None:
    r = TestRunner()
    print("ReviewFinding:")
    test_review_finding_valid(r)
    test_review_finding_optional_fix(r)
    test_review_finding_missing_required(r)
    test_review_finding_invalid_severity(r)
    test_review_finding_line_constraint(r)
    test_review_finding_confidence_constraint(r)
    test_review_finding_title_min_length(r)

    print("\nReviewReport:")
    test_review_report_round_trip(r)

    print("\nPlanIssue / PlanReport:")
    test_plan_issue_and_report(r)
    test_plan_issue_invalid_category(r)

    print("\nRefactorVerdict:")
    test_refactor_verdict(r)

    print("\nHandoffResult:")
    test_handoff_result_valid(r)
    test_handoff_result_ship(r)
    test_handoff_result_open_target(r)
    test_handoff_result_writing_plans(r)
    test_handoff_result_all_targets_distinct(r)

    sys.exit(r.summary())


if __name__ == "__main__":
    main()
