#!/usr/bin/env python3
"""Tests for hooks.lib.llm.workers.aggregator — Step 10.

The aggregator is exercised via mocked SDK calls. Real LLM judgment (e.g.
±2-line merge accuracy) is validated by the smoke spike, not here.

Run: python3 tests/test_aggregator.py
"""

import asyncio
import json
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


def _import_aggregator_module():
    import importlib
    import hooks.lib.llm.workers.aggregator as mod
    return importlib.reload(mod)


def _report_dict(agent: str, findings: list[dict], summary: str = "x") -> dict:
    return {
        "agent": agent,
        "scope": "HEAD",
        "findings": findings,
        "summary": summary,
    }


def _finding(severity, file, line, category, title, confidence=0.8):
    return {
        "severity": severity,
        "file": file,
        "line": line,
        "category": category,
        "title": title,
        "body": "Body text long enough to look real.",
        "suggested_fix": None,
        "confidence": confidence,
    }


UNIFIED_REPORT = {
    "agent": "review-aggregator",
    "scope": "HEAD",
    "findings": [
        _finding("CRITICAL", "api/auth.py", 11, "security",
                 "SQL injection via concat", confidence=0.95),
    ],
    "summary": "One critical security issue around authentication.",
}


def test_aggregate_degenerate_len_one(runner):
    print("\n[degenerate len-1 input]")
    agg = _import_aggregator_module()

    from hooks.lib.llm.schemas import ReviewReport
    one_report = ReviewReport.model_validate(_report_dict(
        "code-reviewer",
        [_finding("CRITICAL", "x.py", 5, "security", "Bad title here")],
    ))

    captured = {}
    result_msg = SimpleNamespace(
        subtype="success", structured_output=UNIFIED_REPORT)

    async def fake_query(*args, prompt=None, options=None, **kw):
        captured["prompt"] = prompt
        captured["options"] = options
        yield result_msg

    async def run():
        with patch.object(agg, "query", fake_query):
            with patch.object(agg, "ResultMessage", SimpleNamespace):
                return await agg.aggregate([one_report])

    out = asyncio.run(run())
    runner.test("returns ReviewReport", out.agent == "review-aggregator")
    runner.test("input report serialized into prompt",
                "code-reviewer" in (captured["prompt"] or ""))
    runner.test("agent label is review-aggregator",
                getattr(captured["options"], "agent", None)
                == "review-aggregator",
                f"got {getattr(captured['options'], 'agent', '<missing>')!r}")


def test_aggregate_serializes_all_inputs(runner):
    print("\n[len-2 input prompt structure]")
    agg = _import_aggregator_module()
    from hooks.lib.llm.schemas import ReviewReport

    reports = [
        ReviewReport.model_validate(_report_dict(
            "code-reviewer",
            [_finding("IMPORTANT", "a.py", 10, "logic", "Off-by-one error")],
        )),
        ReviewReport.model_validate(_report_dict(
            "appsec-auditor",
            [_finding("CRITICAL", "a.py", 11, "security",
                      "Command injection in shell call")],
        )),
    ]

    captured = {}
    result_msg = SimpleNamespace(
        subtype="success", structured_output=UNIFIED_REPORT)

    async def fake_query(*args, prompt=None, options=None, **kw):
        captured["prompt"] = prompt
        yield result_msg

    async def run():
        with patch.object(agg, "query", fake_query):
            with patch.object(agg, "ResultMessage", SimpleNamespace):
                return await agg.aggregate(reports)

    asyncio.run(run())
    prompt = captured["prompt"] or ""
    runner.test("both agents named in prompt",
                "code-reviewer" in prompt and "appsec-auditor" in prompt)
    runner.test("merge rules included (±2 lines)",
                "2 lines" in prompt or "±2" in prompt or "merge" in prompt
                .lower())
    runner.test("input is valid JSON inside prompt",
                _contains_parseable_json_block(prompt))


def _contains_parseable_json_block(prompt: str) -> bool:
    """Find the JSON input list (anchored after the 'Input ... (JSON):' marker)."""
    anchor = prompt.find("(JSON):")
    if anchor < 0:
        return False
    start = prompt.find("[", anchor)
    if start < 0:
        return False
    snippet = prompt[start:]
    for end in range(len(snippet), max(0, len(snippet) - 5000), -1):
        try:
            obj = json.loads(snippet[:end])
            if isinstance(obj, list) and obj:
                return True
        except (json.JSONDecodeError, ValueError):
            continue
    return False


def test_aggregate_raises_on_error_subtype(runner):
    print("\n[error_max_structured_output_retries]")
    agg = _import_aggregator_module()
    from hooks.lib.llm.schemas import ReviewReport

    err_msg = SimpleNamespace(
        subtype="error_max_structured_output_retries",
        structured_output=None,
    )

    async def fake_query(*args, prompt=None, options=None, **kw):
        yield err_msg

    raised = []

    async def run():
        with patch.object(agg, "query", fake_query):
            with patch.object(agg, "ResultMessage", SimpleNamespace):
                report = ReviewReport.model_validate(_report_dict(
                    "code-reviewer",
                    [_finding("CRITICAL", "x.py", 1, "security",
                              "Bad title here")],
                ))
                try:
                    await agg.aggregate([report])
                except RuntimeError as e:
                    raised.append(str(e))

    asyncio.run(run())
    runner.test("raises RuntimeError on error subtype", len(raised) == 1)
    runner.test("error mentions subtype",
                bool(raised) and "error_max_structured_output_retries"
                in raised[0])


def test_aggregate_raises_on_empty_input(runner):
    print("\n[empty input is a programming error]")
    agg = _import_aggregator_module()
    raised = []

    async def fake_query(*args, prompt=None, options=None, **kw):
        # Should never be called if input validation fires first
        raised.append("query was called for empty input")
        yield SimpleNamespace(subtype="success", structured_output=UNIFIED_REPORT)

    async def run():
        with patch.object(agg, "query", fake_query):
            with patch.object(agg, "ResultMessage", SimpleNamespace):
                try:
                    await agg.aggregate([])
                except ValueError as e:
                    raised.append(("ValueError", str(e)))

    asyncio.run(run())
    runner.test("raises ValueError on empty input",
                any(isinstance(r, tuple) and r[0] == "ValueError"
                    for r in raised),
                f"raised: {raised}")
    runner.test("query not called on empty input",
                "query was called for empty input" not in raised)


def test_aggregate_options_shape(runner):
    print("\n[options: output_format + no tools]")
    agg = _import_aggregator_module()
    from hooks.lib.llm.schemas import ReviewReport

    captured = {}
    result_msg = SimpleNamespace(
        subtype="success", structured_output=UNIFIED_REPORT)

    async def fake_query(*args, prompt=None, options=None, **kw):
        captured["options"] = options
        yield result_msg

    async def run():
        with patch.object(agg, "query", fake_query):
            with patch.object(agg, "ResultMessage", SimpleNamespace):
                report = ReviewReport.model_validate(_report_dict(
                    "code-reviewer",
                    [_finding("CRITICAL", "x.py", 1, "security",
                              "Bad title here")],
                ))
                return await agg.aggregate([report])

    asyncio.run(run())
    opts = captured["options"]
    runner.test("allowed_tools is empty list",
                getattr(opts, "allowed_tools", None) == [])
    of = getattr(opts, "output_format", None)
    runner.test("output_format is json_schema for ReviewReport",
                isinstance(of, dict) and of.get("type") == "json_schema"
                and "findings" in of["schema"].get("properties", {}))


if __name__ == "__main__":
    runner = TestRunner()
    test_aggregate_degenerate_len_one(runner)
    test_aggregate_serializes_all_inputs(runner)
    test_aggregate_raises_on_error_subtype(runner)
    test_aggregate_raises_on_empty_input(runner)
    test_aggregate_options_shape(runner)
    sys.exit(runner.summary())
