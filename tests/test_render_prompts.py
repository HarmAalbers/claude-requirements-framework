#!/usr/bin/env python3
"""Tests for scripts/render_prompts.py (Step 16b).

Covers the 4 CLI modes (render, dry-run, check-fresh, check-stale), the
error paths the plan's Patch 2 scope calls out (codex Q3/Q5: missing
include, undefined runtime variable), and the zero-variable build-time
contract for plugin templates under `plugins/requirements-framework/`.

The CLI is exercised as a subprocess to test the actual entry-point
behavior (argparse, exit codes, stderr/stdout) — not just the importable
internals.

Run with: python3 tests/test_render_prompts.py
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "render_prompts.py"
PLUGIN_TREE = REPO_ROOT / "plugins" / "requirements-framework"

try:
    import jinja2  # noqa: F401
except ImportError:
    print("SKIP: jinja2 not installed. `pip install -e '.[llm]'` to enable.")
    sys.exit(0)


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        check=False,
    )


class TestRunner:
    def __init__(self) -> None:
        self.passed = 0
        self.failed = 0
        self.failed_tests: list[tuple[str, str]] = []

    def test(self, name: str, condition: bool, msg: str = "") -> None:
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


# ---------- CLI mode: render (default) ----------


def test_render_default_writes_md_sibling(r: TestRunner) -> None:
    with tempfile.TemporaryDirectory() as td:
        src = Path(td) / "demo.md.j2"
        src.write_text("hello world\n")
        result = _run(td)
        r.test(
            "render mode exits 0 on success",
            result.returncode == 0,
            f"exit={result.returncode} stderr={result.stderr!r}",
        )
        target = Path(td) / "demo.md"
        r.test(
            "render mode writes the .md sibling",
            target.exists() and target.read_text() == "hello world\n",
            f"target_exists={target.exists()}",
        )


def test_render_no_sources_is_ok(r: TestRunner) -> None:
    with tempfile.TemporaryDirectory() as td:
        result = _run(td)
        r.test(
            "render mode exits 0 when no .md.j2 under path",
            result.returncode == 0
            and "nothing to render" in result.stdout,
            f"exit={result.returncode} stdout={result.stdout!r}",
        )


# ---------- CLI mode: --dry-run ----------


def test_dry_run_writes_nothing(r: TestRunner) -> None:
    with tempfile.TemporaryDirectory() as td:
        src = Path(td) / "demo.md.j2"
        src.write_text("hello\n")
        result = _run(td, "--dry-run")
        target = Path(td) / "demo.md"
        r.test(
            "dry-run mode exits 0",
            result.returncode == 0,
            f"exit={result.returncode}",
        )
        r.test(
            "dry-run mode does NOT write the .md sibling",
            not target.exists(),
            f"target_exists={target.exists()}",
        )


# ---------- CLI mode: --check (fresh) ----------


def test_check_passes_when_md_matches_source(r: TestRunner) -> None:
    with tempfile.TemporaryDirectory() as td:
        src = Path(td) / "demo.md.j2"
        src.write_text("hello\n")
        # First render to produce a fresh .md
        first = _run(td)
        assert first.returncode == 0, first.stderr
        # Now --check: nothing has changed since the render
        result = _run(td, "--check")
        r.test(
            "--check exits 0 when rendered .md matches source",
            result.returncode == 0,
            f"exit={result.returncode} stderr={result.stderr!r}",
        )


# ---------- CLI mode: --check (stale) ----------


def test_check_fails_when_md_is_missing(r: TestRunner) -> None:
    with tempfile.TemporaryDirectory() as td:
        src = Path(td) / "demo.md.j2"
        src.write_text("hello\n")
        # No prior render, so the .md sibling doesn't exist
        result = _run(td, "--check")
        r.test(
            "--check exits 1 when rendered .md is missing",
            result.returncode == 1,
            f"exit={result.returncode} stdout={result.stdout!r}",
        )
        r.test(
            "--check stale output mentions the script to re-run",
            "render_prompts.py" in result.stdout,
            f"stdout={result.stdout!r}",
        )


def test_check_fails_when_md_is_drifted(r: TestRunner) -> None:
    with tempfile.TemporaryDirectory() as td:
        src = Path(td) / "demo.md.j2"
        src.write_text("hello\n")
        target = Path(td) / "demo.md"
        target.write_text("stale content\n")
        result = _run(td, "--check")
        r.test(
            "--check exits 1 when rendered .md drifts from source",
            result.returncode == 1,
            f"exit={result.returncode}",
        )


# ---------- Error paths: codex Q3/Q5 ----------


def test_missing_include_reports_render_failure(r: TestRunner) -> None:
    # A template that includes a partial that does not exist must fail
    # loudly with exit 1 (not silently render an empty include).
    with tempfile.TemporaryDirectory() as td:
        src = Path(td) / "demo.md.j2"
        src.write_text("{% include 'partials/__does_not_exist__.j2' %}\n")
        result = _run(td)
        r.test(
            "missing include exits 1",
            result.returncode == 1,
            f"exit={result.returncode}",
        )
        r.test(
            "missing include reports the failure in stdout",
            "TemplateNotFound" in result.stdout
            or "failed to render" in result.stdout,
            f"stdout={result.stdout!r}",
        )


def test_undefined_runtime_var_reports_render_failure(r: TestRunner) -> None:
    # StrictUndefined contract: a template referencing {{ runtime_var }}
    # with no caller vars must exit 1 — runtime-variable templates do not
    # belong in the build-time plugin tree.
    with tempfile.TemporaryDirectory() as td:
        src = Path(td) / "demo.md.j2"
        src.write_text("hello {{ some_runtime_var }}\n")
        result = _run(td)
        r.test(
            "undefined runtime var exits 1",
            result.returncode == 1,
            f"exit={result.returncode}",
        )
        r.test(
            "undefined runtime var reports the failure",
            "UndefinedError" in result.stdout
            or "failed to render" in result.stdout,
            f"stdout={result.stdout!r}",
        )


# ---------- Zero-variable build-time contract for plugin tree ----------


def test_plugin_templates_have_no_runtime_vars(r: TestRunner) -> None:
    # The plugin tree (`plugins/requirements-framework/`) is build-time
    # only — every .md.j2 under it MUST render without any caller vars.
    # Once any plugin .md.j2 introduces a runtime var, this test fails
    # and the offending file is forced into the runtime tree
    # (`hooks/lib/llm/prompts/`) instead.
    result = _run(str(PLUGIN_TREE), "--dry-run")
    r.test(
        "every plugin .md.j2 renders with zero caller vars",
        result.returncode == 0,
        f"exit={result.returncode} stdout={result.stdout!r}",
    )


def test_all_plugin_md_files_have_j2_source(r: TestRunner) -> None:
    # Step 16c invariant: every dispatched plugin .md has a .md.j2 source.
    # Turns the previously-manual shell check from the plan's acceptance
    # criterion into a permanent regression guard. Excludes reference
    # material under skills/*/references/, plugin docs (README, ATTRIBUTION),
    # and the 3 refactor-orchestration template files (skill-internal
    # scaffolding read via Read at runtime — not dispatched prompts).
    excluded_names = {
        "README.md",
        "ATTRIBUTION.md",
        "orchestrator-prompt-template.md",
        "plan-template.md",
        "retrospective-template.md",
    }
    missing: list[str] = []
    # Agents and commands: flat .md scan
    for sub in ("agents", "commands"):
        for md in (PLUGIN_TREE / sub).glob("*.md"):
            if md.name in excluded_names:
                continue
            if not Path(str(md) + ".j2").exists():
                missing.append(str(md.relative_to(PLUGIN_TREE)))
    # Skills: only SKILL.md at depth 2 (skip references/ and templates)
    for md in PLUGIN_TREE.glob("skills/*/SKILL.md"):
        if not Path(str(md) + ".j2").exists():
            missing.append(str(md.relative_to(PLUGIN_TREE)))
    r.test(
        "every dispatched plugin .md has a .md.j2 source",
        not missing,
        f"missing .md.j2 source for: {missing}",
    )


def main() -> int:
    print("Running render_prompts.py CLI tests...")
    r = TestRunner()

    test_render_default_writes_md_sibling(r)
    test_render_no_sources_is_ok(r)
    test_dry_run_writes_nothing(r)
    test_check_passes_when_md_matches_source(r)
    test_check_fails_when_md_is_missing(r)
    test_check_fails_when_md_is_drifted(r)
    test_missing_include_reports_render_failure(r)
    test_undefined_runtime_var_reports_render_failure(r)
    test_plugin_templates_have_no_runtime_vars(r)
    test_all_plugin_md_files_have_j2_source(r)

    return r.summary()


if __name__ == "__main__":
    sys.exit(main())
