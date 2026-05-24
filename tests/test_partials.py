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


# ---------- diff_scope_load.j2 (Step 16b) ----------

# Byte-identical kernel verified across all 13 diff-scope review agents at
# Patch 2 authoring time (MD5 09f3eb3c657bc4397091348edbc95e58). Per-agent
# acceptance gate enforces this match at Patches 4..28 conversion time.
_DIFF_SCOPE_KERNEL = (
    "Execute: `${CLAUDE_PLUGIN_ROOT}/scripts/prepare-diff-scope --ensure`\n"
    "\n"
    "Read `/tmp/review_scope.txt` (list of changed files, one per line) and\n"
    "`/tmp/review.diff` (unified diff). If the scope file is empty, output\n"
    '"No review scope provided" and EXIT.\n'
)


def test_diff_scope_load_renders_kernel(r: TestRunner) -> None:
    out = templates.render("{% include 'partials/diff_scope_load.j2' %}")
    # keep_trailing_newline=True preserves the final \n in the partial file.
    r.test(
        "diff_scope_load partial renders the validated byte-identical kernel",
        out == _DIFF_SCOPE_KERNEL,
        f"got {out!r}",
    )


def test_diff_scope_load_needs_no_caller_vars(r: TestRunner) -> None:
    # The partial must render with zero vars — StrictUndefined would raise
    # at render time if it accidentally referenced one. This guards future
    # edits from breaking every includer at once.
    try:
        templates.render("{% include 'partials/diff_scope_load.j2' %}")
        r.test("diff_scope_load needs no caller vars", True)
    except Exception as exc:
        r.test(
            "diff_scope_load needs no caller vars",
            False,
            f"{type(exc).__name__}: {exc}",
        )


def test_diff_scope_load_boundary_newlines(r: TestRunner) -> None:
    # Refactor-advisor Gap 1: pin the exact whitespace contract at include
    # boundaries. Without this, a typo in the partial's trailing newline
    # could silently drift the rendered .md output across all 13 agents.
    out = templates.render(
        "BEFORE\n{% include 'partials/diff_scope_load.j2' %}\nAFTER"
    )
    r.test(
        "diff_scope_load preserves the BEFORE prefix exactly",
        out.startswith("BEFORE\n"),
        repr(out[:32]),
    )
    r.test(
        "diff_scope_load preserves the AFTER suffix exactly",
        out.endswith("\nAFTER"),
        repr(out[-32:]),
    )
    # Partial ends with \n + literal \n after %} + literal \n before AFTER
    # produces "EXIT.\n\n\nAFTER" — that's two blank lines visually.
    # Includers in plugin agents put the include on its own line followed
    # by the next paragraph directly (no extra blank) to land at one blank
    # line. See Patch 4 pilot for the canonical site pattern.
    r.test(
        'diff_scope_load ends its content with EXIT.\\n (the trailing kernel byte)',
        '"No review scope provided" and EXIT.\n' in out,
        repr(out),
    )


# ---------- negative tests (Step 16b) ----------


def test_nonexistent_partial_raises(r: TestRunner) -> None:
    # If an agent template references a partial that doesn't exist, we want
    # a loud failure at render time, not a silent empty include. Jinja2
    # raises TemplateNotFound — assert that contract.
    try:
        templates.render("{% include 'partials/__does_not_exist__.j2' %}")
        r.test(
            "nonexistent partial raises TemplateNotFound",
            False,
            "render returned without raising",
        )
    except Exception as exc:
        # jinja2.exceptions.TemplateNotFound is the expected type.
        ok = type(exc).__name__ == "TemplateNotFound"
        r.test(
            "nonexistent partial raises TemplateNotFound",
            ok,
            f"unexpected exception type: {type(exc).__name__}: {exc}",
        )


# ---------- composition: all partials together ----------


def test_partials_compose(r: TestRunner) -> None:
    template = (
        "PROMPT START\n"
        "{% include 'partials/safety.j2' %}\n"
        "{% include 'partials/diff_scope_load.j2' %}\n"
        "{% include 'partials/project_conventions.j2' %}\n"
        "PROMPT END"
    )
    out = templates.render(template, project_conventions="My conventions here.")
    r.test(
        "all partials included",
        "test fixtures" in out
        and "prepare-diff-scope" in out
        and "My conventions" in out,
    )
    r.test(
        "partial boundaries preserved",
        "PROMPT START" in out and "PROMPT END" in out,
    )


def main() -> int:
    print("Running partials tests...")
    r = TestRunner()

    test_safety_partial_includes(r)
    test_safety_partial_no_vars_needed(r)
    test_project_conventions_renders_empty_without_var(r)
    test_project_conventions_renders_content_when_var_passed(r)
    test_project_conventions_skips_empty_string(r)
    test_diff_scope_load_renders_kernel(r)
    test_diff_scope_load_needs_no_caller_vars(r)
    test_diff_scope_load_boundary_newlines(r)
    test_nonexistent_partial_raises(r)
    test_partials_compose(r)

    return r.summary()


if __name__ == "__main__":
    sys.exit(main())
