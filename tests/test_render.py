#!/usr/bin/env python3
"""Tests for hooks.lib.llm.render — Step 18c.

Verdict logic is deterministic over constructed ReviewReports (no mocks).
Covers the IMPORTANT==5 (READY) vs ==6 (REVIEW RECOMMENDED) boundary, CRITICAL
dominance, severity grouping/order, empty findings, headers, and the
worker_errors section.

Run: python3 tests/test_render.py
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from hooks.lib.llm.render import compute_verdict, render_review_markdown
from hooks.lib.llm.schemas import ReviewReport


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


def _finding(severity, title="A sufficiently long finding title", line=1):
    return {
        "severity": severity,
        "file": "api/x.py",
        "line": line,
        "category": "security" if severity == "CRITICAL" else "logic",
        "title": title,
        "body": "Concrete one-sentence description.",
        "suggested_fix": "Do the safe thing.",
        "confidence": 0.8,
    }


def _report(findings, summary="agg summary"):
    return ReviewReport.model_validate({
        "agent": "review-aggregator",
        "scope": "HEAD",
        "findings": findings,
        "summary": summary,
    })


def test_verdict_empty_is_ready(runner):
    print("\n[verdict: empty → READY]")
    runner.test("no findings → READY",
                compute_verdict(_report([])) == "READY")


def test_verdict_critical_dominates(runner):
    print("\n[verdict: any CRITICAL → FIX ISSUES FIRST]")
    findings = [_finding("CRITICAL")] + [_finding("IMPORTANT")] * 10
    runner.test("1 CRITICAL + 10 IMPORTANT → FIX ISSUES FIRST",
                compute_verdict(_report(findings)) == "FIX ISSUES FIRST")


def test_verdict_important_boundary(runner):
    print("\n[verdict: IMPORTANT==5 → READY, ==6 → REVIEW]")
    five = _report([_finding("IMPORTANT", line=i + 1) for i in range(5)])
    six = _report([_finding("IMPORTANT", line=i + 1) for i in range(6)])
    runner.test("exactly 5 IMPORTANT → READY",
                compute_verdict(five) == "READY",
                f"got {compute_verdict(five)}")
    runner.test("6 IMPORTANT → REVIEW RECOMMENDED",
                compute_verdict(six) == "REVIEW RECOMMENDED",
                f"got {compute_verdict(six)}")


def test_markdown_groups_by_severity_in_order(runner):
    print("\n[markdown grouping + order]")
    findings = [
        _finding("SUGGESTION", title="Suggestion finding title here"),
        _finding("CRITICAL", title="Critical finding title here"),
        _finding("IMPORTANT", title="Important finding title here"),
    ]
    md = render_review_markdown(_report(findings))
    ci = md.index("Critical finding")
    ii = md.index("Important finding")
    si = md.index("Suggestion finding")
    runner.test("CRITICAL before IMPORTANT before SUGGESTION",
                ci < ii < si, f"positions c={ci} i={ii} s={si}")
    runner.test("verdict present in Summary",
                "**Verdict**: FIX ISSUES FIRST" in md)
    runner.test("counts present",
                "- **CRITICAL**: 1" in md and "- **IMPORTANT**: 1" in md
                and "- **SUGGESTION**: 1" in md)
    runner.test("ADR-013 finding headers present",
                "### CRITICAL: Critical finding title here" in md)


def test_markdown_empty_findings(runner):
    print("\n[markdown: empty findings]")
    md = render_review_markdown(_report([], summary="nothing to flag"))
    runner.test("READY verdict", "**Verdict**: READY" in md)
    runner.test("summary rendered", "nothing to flag" in md)
    runner.test("all counts zero", "- **CRITICAL**: 0" in md)


def test_markdown_worker_errors_section(runner):
    print("\n[markdown: worker_errors section]")
    md = render_review_markdown(
        _report([_finding("IMPORTANT")]),
        worker_errors={"appsec-auditor": "timed out", "test-analyzer": "empty"},
    )
    runner.test("section header present",
                "## Workers that did not complete" in md)
    runner.test("each failed worker listed",
                "**appsec-auditor**: timed out" in md
                and "**test-analyzer**: empty" in md)
    md_none = render_review_markdown(_report([_finding("IMPORTANT")]))
    runner.test("no section when no worker_errors",
                "Workers that did not complete" not in md_none)


if __name__ == "__main__":
    runner = TestRunner()
    test_verdict_empty_is_ready(runner)
    test_verdict_critical_dominates(runner)
    test_verdict_important_boundary(runner)
    test_markdown_groups_by_severity_in_order(runner)
    test_markdown_empty_findings(runner)
    test_markdown_worker_errors_section(runner)
    sys.exit(runner.summary())
