#!/usr/bin/env python3
"""Tests for hooks.lib.llm.workers.rosters.review_workers — Step 18c.

Verifies the roster contents and that importing `rosters` is lazy — the worker
modules must NOT be imported until `review_workers()` is actually called
(arch-review #10). The laziness check runs in a clean subprocess so it isn't
fooled by worker modules other tests already imported into this process.

Run: python3 tests/test_review_roster.py
"""

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from hooks.lib.llm.workers.rosters import review_workers


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


# Final /v3-review roster — 10 workers (code-simplifier excluded: deprecated).
EXPECTED_SEED = {
    "code-reviewer", "solid-reviewer", "appsec-auditor",
    "silent-failure-hunter", "test-analyzer",
    "backward-compatibility-checker", "type-design-analyzer",
    "comment-analyzer", "tenant-isolation-auditor", "compliance-auditor",
}


def test_roster_is_exactly_ten(runner):
    print("\n[roster size]")
    roster = review_workers()
    runner.test("roster has exactly 10 workers", len(roster) == 10,
                f"got {len(roster)}: {sorted(roster)}")
    runner.test("matches expected set", set(roster) == EXPECTED_SEED,
                f"diff={set(roster) ^ EXPECTED_SEED}")


def test_roster_contains_seed_workers(runner):
    print("\n[roster contents]")
    roster = review_workers()
    names = set(roster)
    runner.test("seed workers present", EXPECTED_SEED <= names,
                f"missing {EXPECTED_SEED - names}")
    runner.test("all values are callable",
                all(callable(fn) for fn in roster.values()))


def test_import_is_lazy(runner):
    """Importing `rosters` must not import the worker modules; only calling
    review_workers() should. Checked in a clean subprocess."""
    print("\n[lazy import]")
    script = (
        "import sys; "
        "import hooks.lib.llm.workers.rosters as r; "
        "pre = 'hooks.lib.llm.workers.code_reviewer' in sys.modules; "
        "r.review_workers(); "
        "post = 'hooks.lib.llm.workers.code_reviewer' in sys.modules; "
        "print(f'{pre},{post}')"
    )
    proc = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(REPO_ROOT), capture_output=True, text=True,
    )
    out = proc.stdout.strip()
    runner.test("subprocess ran cleanly", proc.returncode == 0,
                f"stderr={proc.stderr.strip()[-300:]}")
    runner.test("worker NOT imported by `import rosters`, IS after review_workers()",
                out == "False,True", f"got {out!r}")


if __name__ == "__main__":
    runner = TestRunner()
    test_roster_contains_seed_workers(runner)
    test_roster_is_exactly_ten(runner)
    test_import_is_lazy(runner)
    sys.exit(runner.summary())
