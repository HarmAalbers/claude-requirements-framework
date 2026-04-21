#!/usr/bin/env python3
"""
Test Suite for diff_scope module.

Tests follow the framework's TestRunner convention (see test_branch_size_calculator.py).
Uses real git repos in tempdirs — no subprocess mocking except for `gh` CLI.

Run with: python3 hooks/test_diff_scope.py
"""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# Add lib directory to path
lib_path = Path(__file__).parent / "lib"
sys.path.insert(0, str(lib_path))

from diff_scope import (
    DEFAULT_BASE,
    DEFAULT_DIFF_FILE,
    DEFAULT_SCOPE_FILE,
    DiffScopeError,
    Scope,
    ensure_scope,
    prepare_diff_scope,
    read_scope,
)


class TestRunner:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.failed_tests = []

    def test(self, name: str, condition: bool, msg: str = ""):
        if condition:
            print(f"  ✅ {name}")
            self.passed += 1
        else:
            print(f"  ❌ {name}: {msg}")
            self.failed += 1
            self.failed_tests.append((name, msg))

    def summary(self):
        total = self.passed + self.failed
        print(f"\n{'=' * 60}")
        print(f"Results: {self.passed}/{total} passed")
        if self.failed_tests:
            print("\nFailed:")
            for name, msg in self.failed_tests:
                print(f"  • {name}: {msg}")
        return 0 if self.failed == 0 else 1


# --- Fixture helpers ---------------------------------------------------------

def _run(cmd: list[str], cwd: str, check: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if check and result.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)} failed: {result.stderr}")
    return result


def make_repo(tmpdir: str) -> None:
    """Init a git repo with one initial commit on `master`."""
    _run(["git", "init", "-b", "master"], cwd=tmpdir)
    _run(["git", "config", "user.email", "test@test.com"], cwd=tmpdir)
    _run(["git", "config", "user.name", "Test"], cwd=tmpdir)
    Path(tmpdir, "README.md").write_text("base\n")
    _run(["git", "add", "."], cwd=tmpdir)
    _run(["git", "commit", "-m", "initial"], cwd=tmpdir)
    # Create origin/master ref locally so tests can diff against it
    _run(["git", "update-ref", "refs/remotes/origin/master", "HEAD"], cwd=tmpdir)


def write_and_stage(tmpdir: str, path: str, content: str) -> None:
    Path(tmpdir, path).write_text(content)
    _run(["git", "add", path], cwd=tmpdir)


def write_unstaged(tmpdir: str, path: str, content: str) -> None:
    Path(tmpdir, path).write_text(content)


# --- Tests: empty-arg precedence ---------------------------------------------

def test_empty_arg_staged_wins(r: TestRunner):
    with tempfile.TemporaryDirectory() as tmp:
        make_repo(tmp)
        write_and_stage(tmp, "a.py", "print('staged')\n")
        write_unstaged(tmp, "b.py", "print('unstaged')\n")
        os.chdir(tmp)
        scope = prepare_diff_scope(None, scope_file=Path(tmp) / "scope.txt", diff_file=Path(tmp) / "review.diff")
        r.test("empty arg prefers staged", scope.source == "staged",
               f"expected source=staged, got {scope.source}")
        r.test("empty arg staged files correct", scope.files == ["a.py"],
               f"expected ['a.py'], got {scope.files}")


def test_empty_arg_unstaged_fallback(r: TestRunner):
    with tempfile.TemporaryDirectory() as tmp:
        make_repo(tmp)
        write_unstaged(tmp, "b.py", "print('unstaged')\n")
        os.chdir(tmp)
        scope = prepare_diff_scope(None, scope_file=Path(tmp) / "scope.txt", diff_file=Path(tmp) / "review.diff")
        r.test("empty arg uses unstaged when no staged", scope.source == "unstaged",
               f"got source={scope.source}")


def test_empty_arg_branch_vs_base(r: TestRunner):
    with tempfile.TemporaryDirectory() as tmp:
        make_repo(tmp)
        _run(["git", "checkout", "-b", "feat/x"], cwd=tmp)
        write_and_stage(tmp, "c.py", "print('on branch')\n")
        _run(["git", "commit", "-m", "feat"], cwd=tmp)
        os.chdir(tmp)
        scope = prepare_diff_scope(None, scope_file=Path(tmp) / "scope.txt", diff_file=Path(tmp) / "review.diff")
        r.test("empty arg falls back to branch vs base", scope.source.startswith("branch:"),
               f"got source={scope.source}")


def test_empty_arg_detached_head(r: TestRunner):
    with tempfile.TemporaryDirectory() as tmp:
        make_repo(tmp)
        write_and_stage(tmp, "c.py", "content\n")
        _run(["git", "commit", "-m", "second"], cwd=tmp)
        sha = _run(["git", "rev-parse", "HEAD"], cwd=tmp).stdout.strip()
        _run(["git", "checkout", sha], cwd=tmp)
        os.chdir(tmp)
        scope = prepare_diff_scope(None, scope_file=Path(tmp) / "scope.txt", diff_file=Path(tmp) / "review.diff")
        r.test("detached HEAD resolves to branch-like diff", scope.files != [],
               "detached HEAD should still produce a scope")


def test_non_git_dir_raises(r: TestRunner):
    with tempfile.TemporaryDirectory() as tmp:
        os.chdir(tmp)
        try:
            prepare_diff_scope(None, scope_file=Path(tmp) / "scope.txt", diff_file=Path(tmp) / "review.diff")
            r.test("non-git raises DiffScopeError", False, "no exception raised")
        except DiffScopeError as e:
            r.test("non-git raises DiffScopeError", "not a git repository" in str(e).lower(),
                   f"wrong message: {e}")


def test_empty_arg_staged_deletion_included(r: TestRunner):
    with tempfile.TemporaryDirectory() as tmp:
        make_repo(tmp)
        # add and commit a file that will later be deleted
        write_and_stage(tmp, "gone.py", "content\n")
        _run(["git", "commit", "-m", "add gone.py"], cwd=tmp)
        # Stage its deletion
        _run(["git", "rm", "gone.py"], cwd=tmp)
        os.chdir(tmp)
        scope = prepare_diff_scope(None, scope_file=Path(tmp) / "scope.txt", diff_file=Path(tmp) / "review.diff")
        r.test("staged deletion included in scope", "gone.py" in scope.files,
               f"expected gone.py in files, got {scope.files}")
        r.test("staged deletion keeps source=staged", scope.source == "staged",
               f"got source={scope.source}")


def test_empty_arg_missing_base_raises(r: TestRunner):
    with tempfile.TemporaryDirectory() as tmp:
        # make_repo creates origin/master; delete it so base is missing
        make_repo(tmp)
        _run(["git", "update-ref", "-d", "refs/remotes/origin/master"], cwd=tmp)
        _run(["git", "checkout", "-b", "feat/x"], cwd=tmp)
        write_and_stage(tmp, "c.py", "content\n")
        _run(["git", "commit", "-m", "feat"], cwd=tmp)
        os.chdir(tmp)
        try:
            prepare_diff_scope(None, scope_file=Path(tmp) / "scope.txt", diff_file=Path(tmp) / "review.diff")
            r.test("missing base ref raises", False, "no exception")
        except DiffScopeError as e:
            r.test("missing base ref raises with message",
                   "base ref" in str(e).lower() or "not found" in str(e).lower(),
                   f"got: {e}")


def main():
    runner = TestRunner()
    print("Empty-arg precedence:")
    test_empty_arg_staged_wins(runner)
    test_empty_arg_unstaged_fallback(runner)
    test_empty_arg_branch_vs_base(runner)
    test_empty_arg_detached_head(runner)
    test_non_git_dir_raises(runner)
    test_empty_arg_staged_deletion_included(runner)
    test_empty_arg_missing_base_raises(runner)
    sys.exit(runner.summary())


if __name__ == "__main__":
    main()
