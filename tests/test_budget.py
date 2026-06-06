#!/usr/bin/env python3
"""Test suite for hooks/lib/llm/budget.py — Step 17a.

Run with: python3 tests/test_budget.py

Mirrors the TestRunner convention from tests/test_observability.py.
No pytest dependency. Uses tempdirs to keep tests isolated from any
real ledger at ~/.claude/requirements-framework/usage/.
"""

import json
import os
import stat
import sys
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

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
def temp_ledger_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


def fake_result(
    cost_usd=0.05,
    input_tokens=1000,
    output_tokens=500,
    duration_ms=12000,
    session_id="sess-abc",
    is_error=False,
    model_usage=None,
):
    """Build a ResultMessage-like object for tests without importing the SDK."""
    return SimpleNamespace(
        total_cost_usd=cost_usd,
        usage={"input_tokens": input_tokens, "output_tokens": output_tokens},
        duration_ms=duration_ms,
        session_id=session_id,
        is_error=is_error,
        model_usage=model_usage,
    )


# ---------- record_dict / record (append behavior) ----------------------------

def test_writes_one_line_per_record(runner):
    print("\n[ledger append]")
    from hooks.lib.llm import budget

    with temp_ledger_dir() as d:
        budget.record_dict({"cost_usd": 0.01, "ts": "2026-05-22T10:00:00Z"},
                           year=2026, month=5, ledger_dir=d)
        budget.record_dict({"cost_usd": 0.02, "ts": "2026-05-22T10:01:00Z"},
                           year=2026, month=5, ledger_dir=d)
        budget.record_dict({"cost_usd": 0.03, "ts": "2026-05-22T10:02:00Z"},
                           year=2026, month=5, ledger_dir=d)

        path = d / "2026-05.jsonl"
        runner.test("file exists", path.exists())
        lines = path.read_text().strip().split("\n")
        runner.test("3 lines written", len(lines) == 3, f"got {len(lines)}")
        for i, line in enumerate(lines):
            obj = json.loads(line)
            runner.test(f"line {i} parses as JSON", isinstance(obj, dict))


def test_record_extracts_from_resultmessage(runner):
    print("\n[record extraction]")
    from hooks.lib.llm import budget

    with temp_ledger_dir() as d:
        result = fake_result(cost_usd=0.0245, input_tokens=1500, output_tokens=800,
                             duration_ms=12340, session_id="sess-xyz")
        now = datetime(2026, 5, 22, 15, 30, 0, tzinfo=timezone.utc)
        budget.record(result, agent="code-reviewer", now=now, ledger_dir=d,
                      enabled=True)

        line = (d / "2026-05.jsonl").read_text().strip()
        obj = json.loads(line)
        runner.test("agent recorded", obj["agent"] == "code-reviewer")
        runner.test("cost recorded", obj["cost_usd"] == 0.0245)
        runner.test("input_tokens recorded", obj["input_tokens"] == 1500)
        runner.test("output_tokens recorded", obj["output_tokens"] == 800)
        runner.test("duration recorded", obj["duration_ms"] == 12340)
        runner.test("session id recorded", obj["sdk_session_id"] == "sess-xyz")
        runner.test("ts is ISO-8601",
                    obj["ts"].startswith("2026-05-22T15:30:00"))


def test_record_handles_none_cost(runner):
    print("\n[record extraction — None cost]")
    from hooks.lib.llm import budget

    with temp_ledger_dir() as d:
        result = fake_result(cost_usd=None)
        budget.record(result, agent="x", ledger_dir=d, enabled=True)
        obj = json.loads((d / f"{datetime.now().strftime('%Y-%m')}.jsonl")
                         .read_text().strip())
        runner.test("None cost preserved as null", obj["cost_usd"] is None)


def test_record_default_agent_is_unknown(runner):
    from hooks.lib.llm import budget

    with temp_ledger_dir() as d:
        budget.record(fake_result(), ledger_dir=d, enabled=True)
        obj = json.loads((d / f"{datetime.now().strftime('%Y-%m')}.jsonl")
                         .read_text().strip())
        runner.test("default agent is 'unknown'", obj["agent"] == "unknown")


def test_record_disabled_is_noop(runner):
    print("\n[config gating]")
    from hooks.lib.llm import budget

    with temp_ledger_dir() as d:
        budget.record(fake_result(), agent="x", ledger_dir=d, enabled=False)
        files = list(d.iterdir())
        runner.test("no files written when disabled", len(files) == 0,
                    f"got files: {files}")


def test_unwritable_dir_does_not_raise(runner):
    """Fail-open: any I/O error swallowed (logged) without raising."""
    from hooks.lib.llm import budget

    # Path under /proc on linux or /System on macOS would be unwritable, but
    # using a path-that-cannot-be-created is the portable way: pass a path
    # whose parent does not exist AND chmod the tempdir to read-only.
    with tempfile.TemporaryDirectory() as tmp:
        bad = Path(tmp) / "ledger"
        bad.mkdir()
        # remove all write permission
        bad.chmod(stat.S_IRUSR | stat.S_IXUSR)
        try:
            try:
                budget.record(fake_result(), agent="x", ledger_dir=bad,
                              enabled=True)
                runner.test("unwritable dir does not raise", True)
            except Exception as e:
                runner.test("unwritable dir does not raise", False,
                            f"raised {type(e).__name__}: {e}")
        finally:
            # restore so cleanup works
            bad.chmod(stat.S_IRWXU)


# ---------- load_month / summarize -------------------------------------------

def test_load_month_yields_records(runner):
    print("\n[load_month]")
    from hooks.lib.llm import budget

    with temp_ledger_dir() as d:
        for cost in (0.01, 0.02, 0.03):
            budget.record_dict({"cost_usd": cost}, year=2026, month=5,
                               ledger_dir=d)
        records = list(budget.load_month(2026, 5, ledger_dir=d))
        runner.test("yields 3 records", len(records) == 3)
        runner.test("preserves cost", [r["cost_usd"] for r in records]
                    == [0.01, 0.02, 0.03])


def test_load_month_missing_file_is_empty(runner):
    from hooks.lib.llm import budget

    with temp_ledger_dir() as d:
        records = list(budget.load_month(2026, 5, ledger_dir=d))
        runner.test("missing file → empty list", records == [])


def test_load_month_skips_malformed_lines(runner):
    from hooks.lib.llm import budget

    with temp_ledger_dir() as d:
        path = d / "2026-05.jsonl"
        path.write_text('{"cost_usd": 0.01}\nnot-json-at-all\n'
                        '{"cost_usd": 0.02}\n')
        records = list(budget.load_month(2026, 5, ledger_dir=d))
        runner.test("2 valid records (malformed skipped)", len(records) == 2)


def test_summarize_basics(runner):
    print("\n[summarize]")
    from hooks.lib.llm import budget

    records = [
        {"cost_usd": 0.01, "agent": "a"},
        {"cost_usd": 0.02, "agent": "a"},
        {"cost_usd": 0.05, "agent": "b"},
    ]
    s = budget.summarize(records)
    runner.test("mtd sum correct", abs(s["mtd_usd"] - 0.08) < 1e-9,
                f"got {s['mtd_usd']}")
    runner.test("call count correct", s["call_count"] == 3)
    top = dict(s["top_agents"])
    runner.test("agent a total", abs(top["a"] - 0.03) < 1e-9)
    runner.test("agent b total", abs(top["b"] - 0.05) < 1e-9)


def test_summarize_skips_missing_cost(runner):
    from hooks.lib.llm import budget

    records = [
        {"cost_usd": 0.01, "agent": "a"},
        {"cost_usd": None, "agent": "a"},  # in-flight or errored call
        {"agent": "b"},                      # missing field entirely
    ]
    s = budget.summarize(records)
    runner.test("mtd ignores None and missing", abs(s["mtd_usd"] - 0.01) < 1e-9,
                f"got {s['mtd_usd']}")
    runner.test("call_count counts all rows", s["call_count"] == 3,
                f"got {s['call_count']}")


def test_summarize_empty(runner):
    from hooks.lib.llm import budget

    s = budget.summarize([])
    runner.test("empty mtd", s["mtd_usd"] == 0.0)
    runner.test("empty count", s["call_count"] == 0)
    runner.test("empty top_agents", list(s["top_agents"]) == [])


# ---------- projection -------------------------------------------------------

def test_projection_midmonth(runner):
    print("\n[projection]")
    from hooks.lib.llm import budget

    # 15 days into a 31-day month → projection ≈ mtd * (31/15)
    now = datetime(2026, 5, 16, 0, 0, 0, tzinfo=timezone.utc)
    proj = budget.project_eom(30.0, now)
    expected = 30.0 * (31 / 15)
    runner.test("midmonth linear projection",
                abs(proj - expected) < 0.01, f"got {proj}, expected {expected}")


def test_projection_first_hour_returns_mtd(runner):
    from hooks.lib.llm import budget

    now = datetime(2026, 5, 1, 0, 30, 0, tzinfo=timezone.utc)
    proj = budget.project_eom(1.0, now)
    runner.test("first hour returns mtd unchanged", proj == 1.0,
                f"got {proj}")


def test_projection_end_of_month(runner):
    from hooks.lib.llm import budget

    # Last second of May → projection ≈ mtd
    now = datetime(2026, 5, 31, 23, 59, 59, tzinfo=timezone.utc)
    proj = budget.project_eom(100.0, now)
    runner.test("end of month ≈ mtd", abs(proj - 100.0) < 1.0,
                f"got {proj}")


def test_projection_handles_february(runner):
    """Sanity: 28-day February without leap year."""
    from hooks.lib.llm import budget

    now = datetime(2026, 2, 14, 0, 0, 0, tzinfo=timezone.utc)
    proj = budget.project_eom(10.0, now)
    # 13 full days + a tiny bit elapsed; total 28 days
    expected = 10.0 * (28 / 13)
    runner.test("february projection", abs(proj - expected) < 0.5,
                f"got {proj}, expected {expected}")


# ---------- thresholds -------------------------------------------------------

def test_threshold_ok(runner):
    print("\n[thresholds]")
    from hooks.lib.llm import budget

    cfg = {"monthly_limit_usd": 100, "warn_threshold_pct": 75,
           "critical_threshold_pct": 95}
    alerts = budget.check_thresholds({"projected_eom_usd": 50.0}, cfg)
    runner.test("under warn → no alerts", alerts == [], f"got {alerts}")


def test_threshold_warn(runner):
    from hooks.lib.llm import budget

    cfg = {"monthly_limit_usd": 100, "warn_threshold_pct": 75,
           "critical_threshold_pct": 95}
    alerts = budget.check_thresholds({"projected_eom_usd": 80.0}, cfg)
    runner.test("over warn → 1 alert", len(alerts) == 1, f"got {alerts}")
    runner.test("warn level", alerts[0]["level"] == "warn",
                f"got {alerts[0]}")


def test_threshold_critical(runner):
    from hooks.lib.llm import budget

    cfg = {"monthly_limit_usd": 100, "warn_threshold_pct": 75,
           "critical_threshold_pct": 95}
    alerts = budget.check_thresholds({"projected_eom_usd": 99.0}, cfg)
    runner.test("over critical → 1 alert", len(alerts) == 1, f"got {alerts}")
    runner.test("critical level", alerts[0]["level"] == "critical",
                f"got {alerts[0]}")


def test_threshold_defaults_when_unconfigured(runner):
    """No config → sensible defaults so we still surface burn."""
    from hooks.lib.llm import budget

    alerts = budget.check_thresholds({"projected_eom_usd": 90.0}, {})
    runner.test("defaults applied (90 > 75% of 100)", len(alerts) >= 1,
                f"got {alerts}")


if __name__ == "__main__":
    runner = TestRunner()

    test_writes_one_line_per_record(runner)
    test_record_extracts_from_resultmessage(runner)
    test_record_handles_none_cost(runner)
    test_record_default_agent_is_unknown(runner)
    test_record_disabled_is_noop(runner)
    test_unwritable_dir_does_not_raise(runner)

    test_load_month_yields_records(runner)
    test_load_month_missing_file_is_empty(runner)
    test_load_month_skips_malformed_lines(runner)

    test_summarize_basics(runner)
    test_summarize_skips_missing_cost(runner)
    test_summarize_empty(runner)

    test_projection_midmonth(runner)
    test_projection_first_hour_returns_mtd(runner)
    test_projection_end_of_month(runner)
    test_projection_handles_february(runner)

    test_threshold_ok(runner)
    test_threshold_warn(runner)
    test_threshold_critical(runner)
    test_threshold_defaults_when_unconfigured(runner)

    sys.exit(runner.summary())
