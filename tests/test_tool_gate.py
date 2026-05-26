#!/usr/bin/env python3
"""Tests for hooks.lib.llm.tool_gate — Step 18c.

Mocks `subprocess.run` so no real linters run. Covers: clean → no errors,
linter errors → returned as blocking lines, non-Python files skipped, empty
input → no run, and the fail-LOUD contract (missing binary → RuntimeError,
not a silent skip).

Run: python3 tests/test_tool_gate.py
"""

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from hooks.lib.llm import tool_gate


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


def test_clean_returns_no_errors(runner):
    print("\n[clean → no errors]")

    def fake_run(cmd, capture_output, text):
        return SimpleNamespace(returncode=0, stdout="All checks passed!", stderr="")

    with patch.object(tool_gate.subprocess, "run", fake_run):
        errors = tool_gate.run_tool_gate(["a.py", "b.py"])
    runner.test("no errors on clean run", errors == [], f"got {errors}")


def test_linter_errors_returned(runner):
    print("\n[ruff errors → blocking lines]")

    def fake_run(cmd, capture_output, text):
        return SimpleNamespace(
            returncode=1,
            stdout="a.py:3:1: F401 imported but unused\n", stderr="")

    with patch.object(tool_gate.subprocess, "run", fake_run):
        errors = tool_gate.run_tool_gate(["a.py"])
    runner.test("error line returned", any("F401" in e for e in errors),
                f"got {errors}")


def test_non_python_skipped(runner):
    print("\n[non-Python files skipped]")
    called = {"n": 0}

    def fake_run(cmd, capture_output, text):
        called["n"] += 1
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    with patch.object(tool_gate.subprocess, "run", fake_run):
        errors = tool_gate.run_tool_gate(["README.md", "styles.css"])
    runner.test("no linter invoked when no .py files", called["n"] == 0)
    runner.test("returns empty", errors == [])


def test_empty_input(runner):
    print("\n[empty input]")
    with patch.object(tool_gate.subprocess, "run",
                      lambda *a, **k: SimpleNamespace(returncode=0, stdout="", stderr="")):
        runner.test("empty files → no errors", tool_gate.run_tool_gate([]) == [])


def test_missing_linter_fails_loud(runner):
    print("\n[fail-LOUD: missing linter binary]")

    def fake_run(cmd, capture_output, text):
        raise FileNotFoundError(2, "No such file or directory", "ruff")

    raised = []
    with patch.object(tool_gate.subprocess, "run", fake_run):
        try:
            tool_gate.run_tool_gate(["a.py"])
        except RuntimeError as e:
            raised.append(str(e))
    runner.test("raises RuntimeError when linter missing", len(raised) == 1)
    runner.test("error names the missing linter + fail-loud intent",
                bool(raised) and "ruff" in raised[0] and "not found" in raised[0],
                f"msg={raised[0] if raised else '<none>'}")


def test_pyright_opt_in(runner):
    print("\n[pyright is opt-in, not default]")
    cmds = []

    def fake_run(cmd, capture_output, text):
        cmds.append(cmd[0])
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    with patch.object(tool_gate.subprocess, "run", fake_run):
        tool_gate.run_tool_gate(["a.py"])  # default
        default_cmds = list(cmds)
        cmds.clear()
        tool_gate.run_tool_gate(["a.py"], linters=("ruff", "pyright"))
    runner.test("default runs ruff only", default_cmds == ["ruff"],
                f"got {default_cmds}")
    runner.test("pyright runs when opted in", "pyright" in cmds,
                f"got {cmds}")


if __name__ == "__main__":
    runner = TestRunner()
    test_clean_returns_no_errors(runner)
    test_linter_errors_returned(runner)
    test_non_python_skipped(runner)
    test_empty_input(runner)
    test_missing_linter_fails_loud(runner)
    test_pyright_opt_in(runner)
    sys.exit(runner.summary())
