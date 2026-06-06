#!/usr/bin/env python3
"""Test suite for hooks/lib/llm/templates.py (Step 16).

Covers:
    - render(text, **vars) basic substitution
    - StrictUndefined raises on missing variable (loud-failure contract)
    - {% if %}/{% for %} control flow
    - Custom `repr` filter (replaces Python's {scope!r} pattern)
    - autoescape=False (prompts are text, not HTML)
    - keep_trailing_newline=True (LLM-significant whitespace preservation)
    - Environment configuration (FileSystemLoader pointing at prompts/)

Include tests are deferred to test_prompts.py (Patch 4) once real partials
exist; here we exercise the engine surface only.

Run with: python3 tests/test_templates.py
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

from jinja2 import StrictUndefined, UndefinedError

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


# ---------- render() basic substitution ----------


def test_render_substitutes_variable(r: TestRunner) -> None:
    out = templates.render("Hello {{ name }}!", name="world")
    r.test("variable substituted", out == "Hello world!")


def test_render_returns_string(r: TestRunner) -> None:
    out = templates.render("static text", foo="unused")
    r.test("returns str type", isinstance(out, str))


def test_render_with_no_vars(r: TestRunner) -> None:
    out = templates.render("no variables here")
    r.test("static template renders unchanged", out == "no variables here")


# ---------- StrictUndefined ----------


def test_missing_variable_raises(r: TestRunner) -> None:
    try:
        templates.render("Hello {{ missing }}!")
        r.test("missing var raises UndefinedError", False, "no exception")
    except UndefinedError:
        r.test("missing var raises UndefinedError", True)


def test_missing_variable_in_conditional_raises(r: TestRunner) -> None:
    # StrictUndefined raises even inside {% if %} blocks — forces explicit
    # `is defined` checks for optional sections.
    try:
        templates.render("{% if missing %}x{% endif %}")
        r.test("missing var in {% if %} raises (StrictUndefined contract)", False,
               "no exception — Environment likely not using StrictUndefined")
    except UndefinedError:
        r.test("missing var in {% if %} raises (StrictUndefined contract)", True)


def test_is_defined_check_works(r: TestRunner) -> None:
    # The canonical workaround for optional sections with StrictUndefined
    out = templates.render(
        "{% if missing is defined and missing %}x{% else %}y{% endif %}"
    )
    r.test("`is defined` guard renders else-branch", out == "y")


# ---------- repr filter ----------


def test_repr_filter_quotes_string(r: TestRunner) -> None:
    out = templates.render("scope={{ scope | repr }}", scope="unstaged")
    r.test("repr filter quotes string like Python {!r}", out == "scope='unstaged'")


def test_repr_filter_on_dict(r: TestRunner) -> None:
    out = templates.render("{{ d | repr }}", d={"a": 1})
    r.test("repr filter on dict matches Python repr", out == "{'a': 1}")


# ---------- control flow ----------


def test_if_block(r: TestRunner) -> None:
    out = templates.render(
        "{% if x %}yes{% else %}no{% endif %}", x=True
    )
    r.test("{% if %} truthy branch", out == "yes")
    out = templates.render(
        "{% if x %}yes{% else %}no{% endif %}", x=False
    )
    r.test("{% if %} falsy branch", out == "no")


def test_for_loop(r: TestRunner) -> None:
    out = templates.render(
        "{% for n in nums %}{{ n }}{% endfor %}",
        nums=[1, 2, 3],
    )
    r.test("{% for %} iterates", out == "123")


# ---------- environment configuration ----------


def test_no_autoescape(r: TestRunner) -> None:
    # Prompts are text, not HTML. autoescape must be OFF or we'd escape <,>,&
    out = templates.render("{{ s }}", s="<diff>a & b</diff>")
    r.test("autoescape OFF preserves raw HTML-like chars", out == "<diff>a & b</diff>")


def test_keep_trailing_newline(r: TestRunner) -> None:
    # LLM-significant whitespace — trailing newlines should survive
    out = templates.render("line\n", )
    r.test("trailing newline preserved", out.endswith("\n"))


def test_env_uses_strict_undefined(r: TestRunner) -> None:
    # Direct introspection — verifies the Environment is configured correctly,
    # not just that one specific call raises.
    r.test(
        "templates._ENV.undefined is StrictUndefined",
        templates._ENV.undefined is StrictUndefined,
    )


def test_env_filesystem_loader_points_at_prompts_dir(r: TestRunner) -> None:
    from jinja2 import FileSystemLoader
    r.test(
        "templates._ENV.loader is FileSystemLoader",
        isinstance(templates._ENV.loader, FileSystemLoader),
    )
    expected = (REPO_ROOT / "hooks" / "lib" / "llm" / "prompts").resolve()
    actual = Path(templates._ENV.loader.searchpath[0]).resolve()  # type: ignore[union-attr]
    r.test(
        "FileSystemLoader searchpath is hooks/lib/llm/prompts",
        actual == expected,
        f"expected {expected}, got {actual}",
    )


def main() -> int:
    print("Running templates tests...")
    r = TestRunner()

    test_render_substitutes_variable(r)
    test_render_returns_string(r)
    test_render_with_no_vars(r)

    test_missing_variable_raises(r)
    test_missing_variable_in_conditional_raises(r)
    test_is_defined_check_works(r)

    test_repr_filter_quotes_string(r)
    test_repr_filter_on_dict(r)

    test_if_block(r)
    test_for_loop(r)

    test_no_autoescape(r)
    test_keep_trailing_newline(r)
    test_env_uses_strict_undefined(r)
    test_env_filesystem_loader_points_at_prompts_dir(r)

    return r.summary()


if __name__ == "__main__":
    sys.exit(main())
