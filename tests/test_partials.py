#!/usr/bin/env python3
"""Smoke tests for the bundled Jinja2 partials (Step 16).

These don't test the engine (that's tests/test_templates.py) — they test
that the partial files render to the right content and integrate with the
FileSystemLoader path correctly.

Run with: python3 tests/test_partials.py
"""

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


def test_review_report_file_tells_the_agent_to_write_its_own_report(r: TestRunner) -> None:
    # Reports sent through SendMessage arrived cut off; an agent that writes its
    # full report to the path the orchestrator gives loses nothing on the way.
    out = templates.render("{% include 'partials/review_report_file.j2' %}")
    r.test("review_report_file names the REPORT FILE line", "REPORT FILE:" in out, f"got {out!r}")
    r.test("review_report_file says to write the complete report", "complete report" in out)
    r.test("review_report_file limits writing to that one file", "only that file" in out)
    r.test(
        "review_report_file keeps the message short: path, counts, verdict",
        "path" in out and "counts" in out and "verdict" in out,
    )
    r.test(
        "review_report_file falls back to sending the report when no path is given",
        "no REPORT FILE" in out,
    )


def test_review_report_file_needs_no_caller_vars(r: TestRunner) -> None:
    try:
        templates.render("{% include 'partials/review_report_file.j2' %}")
        r.test("review_report_file needs no caller vars", True)
    except Exception as exc:
        r.test("review_report_file needs no caller vars", False, f"{type(exc).__name__}: {exc}")


# Agents that the review commands (deep-review, pre-commit, arch-review,
# codex-review) dispatch and that end in a findings report.
REVIEW_AGENTS = [
    "adr-guardian",
    "appsec-auditor",
    "backward-compatibility-checker",
    "code-reviewer",
    "codex-arch-reviewer",
    "codex-review-agent",
    "comment-analyzer",
    "compliance-auditor",
    "frontend-reviewer",
    "refactor-advisor",
    "sentry-triage",
    "silent-failure-hunter",
    "solid-reviewer",
    "tdd-validator",
    "tenant-isolation-auditor",
    "test-analyzer",
    "tool-validator",
    "type-design-analyzer",
]
AGENTS_DIR = REPO_ROOT / "plugins" / "requirements-framework" / "agents"


def test_review_agents_include_the_report_file_partial(r: TestRunner) -> None:
    for name in REVIEW_AGENTS:
        source = (AGENTS_DIR / f"{name}.md.j2").read_text()
        r.test(
            f"{name} includes review_report_file.j2",
            "{% include 'partials/review_report_file.j2' %}" in source,
        )


def test_review_agents_may_write_their_report(r: TestRunner) -> None:
    # An agent without an allowed-tools line may use every tool already.
    for name in REVIEW_AGENTS:
        source = (AGENTS_DIR / f"{name}.md.j2").read_text()
        tools_line = next(
            (line for line in source.splitlines() if line.startswith("allowed-tools:")), None
        )
        r.test(
            f"{name} may use Write",
            tools_line is None or '"Write"' in tools_line,
            f"got {tools_line!r}",
        )


def test_review_report_file_reply_fits_subagents_and_teammates(r: TestRunner) -> None:
    # adr-guardian and friends run as plain subagents without SendMessage.
    out = templates.render("{% include 'partials/review_report_file.j2' %}")
    r.test("review_report_file covers a final reply", "final message" in out, f"got {out!r}")
    r.test("review_report_file covers a teammate's SendMessage", "SendMessage" in out)


def test_review_output_dir_follows_the_project_docs_layout(r: TestRunner) -> None:
    out = templates.render("{% include 'partials/review_output_dir.j2' %}")
    r.test("review_output_dir reads the project's docs layout", "docs/README.md" in out, f"got {out!r}")
    r.test("review_output_dir mentions a per-ticket reviews folder", "tickets/<KEY>/reviews/" in out)
    r.test("review_output_dir falls back to docs/reviews/", "docs/reviews/<YYYY-MM-DD>-<branch>/" in out)
    r.test("review_output_dir asks when the layout needs a key it cannot find", "ask the user" in out)


def test_review_output_dir_names_the_files(r: TestRunner) -> None:
    out = templates.render("{% include 'partials/review_output_dir.j2' %}")
    r.test("review_output_dir puts the synthesis in RAPPORT.md", "RAPPORT.md" in out)
    r.test("review_output_dir gives each agent agents/<agent-name>.md", "agents/<agent-name>.md" in out)
    r.test("review_output_dir hands each agent a REPORT FILE line", "REPORT FILE:" in out)
    r.test("review_output_dir treats an existing RAPPORT.md as a re-review", "re-review" in out)


def test_review_output_dir_needs_no_caller_vars(r: TestRunner) -> None:
    try:
        templates.render("{% include 'partials/review_output_dir.j2' %}")
        r.test("review_output_dir needs no caller vars", True)
    except Exception as exc:
        r.test("review_output_dir needs no caller vars", False, f"{type(exc).__name__}: {exc}")


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
    test_review_report_file_tells_the_agent_to_write_its_own_report(r)
    test_review_report_file_needs_no_caller_vars(r)
    test_review_agents_include_the_report_file_partial(r)
    test_review_agents_may_write_their_report(r)
    test_review_report_file_reply_fits_subagents_and_teammates(r)
    test_review_output_dir_follows_the_project_docs_layout(r)
    test_review_output_dir_names_the_files(r)
    test_review_output_dir_needs_no_caller_vars(r)
    test_nonexistent_partial_raises(r)
    test_partials_compose(r)

    return r.summary()


if __name__ == "__main__":
    sys.exit(main())
