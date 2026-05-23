#!/usr/bin/env python3
"""Smoke tests for the bundled Jinja2 partials (Step 16).

These don't test the engine (that's tests/test_templates.py) — they test
that the partial files render to the right content and integrate with the
FileSystemLoader path correctly.

Run with: python3 tests/test_partials.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

try:
    import jinja2  # noqa: F401
except ImportError:
    print("SKIP: jinja2 not installed. `pip install -e '.[llm]'` to enable.")
    sys.exit(0)

from hooks.lib.llm import templates


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


# ---------- safety.j2 ----------


def test_safety_partial_includes(r: TestRunner) -> None:
    out = templates.render("{% include 'partials/safety.j2' %}")
    r.test("safety partial mentions test fixtures rule", "test fixtures" in out)
    r.test("safety partial mentions confidence rule", "confidence" in out)
    r.test("safety partial mentions severity vocabulary",
           "CRITICAL" in out and "IMPORTANT" in out and "SUGGESTION" in out)


def test_safety_partial_no_vars_needed(r: TestRunner) -> None:
    # safety.j2 must render with zero vars — it's pure boilerplate.
    # If it ever references a var, every includer would need to pass it.
    try:
        templates.render("{% include 'partials/safety.j2' %}")
        r.test("safety partial needs no caller vars", True)
    except Exception as exc:
        r.test("safety partial needs no caller vars", False, f"{type(exc).__name__}: {exc}")


# ---------- project_conventions.j2 ----------


def test_project_conventions_renders_empty_without_var(r: TestRunner) -> None:
    out = templates.render("{% include 'partials/project_conventions.j2' %}")
    # No `project_conventions` var passed; `{% if x is defined and x %}` skips.
    # Output should NOT contain the header.
    r.test(
        "no header when project_conventions undefined",
        "Project conventions" not in out,
    )


def test_project_conventions_renders_content_when_var_passed(r: TestRunner) -> None:
    out = templates.render(
        "{% include 'partials/project_conventions.j2' %}",
        project_conventions="Use snake_case for vars. No bare excepts.",
    )
    r.test("header rendered when var passed", "Project conventions" in out)
    r.test("content rendered when var passed", "snake_case" in out)


def test_project_conventions_skips_empty_string(r: TestRunner) -> None:
    out = templates.render(
        "{% include 'partials/project_conventions.j2' %}",
        project_conventions="",
    )
    # Empty string is falsy — `{% if x and x %}` should skip
    r.test(
        "empty string project_conventions skips header",
        "Project conventions" not in out,
    )


# ---------- composition: both partials together ----------


def test_both_partials_compose(r: TestRunner) -> None:
    template = (
        "PROMPT START\n"
        "{% include 'partials/safety.j2' %}\n"
        "{% include 'partials/project_conventions.j2' %}\n"
        "PROMPT END"
    )
    out = templates.render(template, project_conventions="My conventions here.")
    r.test("both partials included", "test fixtures" in out and "My conventions" in out)
    r.test("partial boundaries preserved", "PROMPT START" in out and "PROMPT END" in out)


def main() -> int:
    print("Running partials tests...")
    r = TestRunner()

    test_safety_partial_includes(r)
    test_safety_partial_no_vars_needed(r)
    test_project_conventions_renders_empty_without_var(r)
    test_project_conventions_renders_content_when_var_passed(r)
    test_project_conventions_skips_empty_string(r)
    test_both_partials_compose(r)

    return r.summary()


if __name__ == "__main__":
    sys.exit(main())
