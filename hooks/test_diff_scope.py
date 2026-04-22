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


# --- Tests: branch arg ------------------------------------------------------

def test_branch_arg_valid(r: TestRunner):
    with tempfile.TemporaryDirectory() as tmp:
        make_repo(tmp)
        _run(["git", "checkout", "-b", "feat/x"], cwd=tmp)
        write_and_stage(tmp, "c.py", "print('new')\n")
        _run(["git", "commit", "-m", "feat"], cwd=tmp)
        _run(["git", "checkout", "master"], cwd=tmp)
        os.chdir(tmp)
        scope = prepare_diff_scope("feat/x", scope_file=Path(tmp) / "scope.txt", diff_file=Path(tmp) / "review.diff")
        r.test("branch arg source correct", scope.source == "branch:feat/x",
               f"got source={scope.source}")
        r.test("branch arg files correct", "c.py" in scope.files,
               f"got files={scope.files}")


def test_branch_arg_not_found(r: TestRunner):
    with tempfile.TemporaryDirectory() as tmp:
        make_repo(tmp)
        os.chdir(tmp)
        try:
            prepare_diff_scope("nonexistent")
            r.test("branch not-found raises", False, "no exception")
        except DiffScopeError as e:
            r.test("branch not-found raises", "not found" in str(e).lower(),
                   f"wrong message: {e}")


def test_branch_arg_identical_to_base(r: TestRunner):
    with tempfile.TemporaryDirectory() as tmp:
        make_repo(tmp)
        os.chdir(tmp)
        scope = prepare_diff_scope("master", scope_file=Path(tmp) / "scope.txt", diff_file=Path(tmp) / "review.diff")
        r.test("identical branch returns empty scope", scope.files == [],
               f"expected empty, got {scope.files}")


# --- Tests: range arg --------------------------------------------------------

def test_range_arg_two_dot(r: TestRunner):
    with tempfile.TemporaryDirectory() as tmp:
        make_repo(tmp)
        a = _run(["git", "rev-parse", "HEAD"], cwd=tmp).stdout.strip()
        write_and_stage(tmp, "x.py", "x\n")
        _run(["git", "commit", "-m", "x"], cwd=tmp)
        b = _run(["git", "rev-parse", "HEAD"], cwd=tmp).stdout.strip()
        os.chdir(tmp)
        scope = prepare_diff_scope(f"{a}..{b}", scope_file=Path(tmp) / "scope.txt", diff_file=Path(tmp) / "review.diff")
        r.test("two-dot range resolves", scope.source.startswith("range:"),
               f"got source={scope.source}")
        r.test("two-dot range files", "x.py" in scope.files,
               f"got files={scope.files}")


def test_range_arg_three_dot(r: TestRunner):
    with tempfile.TemporaryDirectory() as tmp:
        make_repo(tmp)
        a = _run(["git", "rev-parse", "HEAD"], cwd=tmp).stdout.strip()
        write_and_stage(tmp, "y.py", "y\n")
        _run(["git", "commit", "-m", "y"], cwd=tmp)
        b = _run(["git", "rev-parse", "HEAD"], cwd=tmp).stdout.strip()
        os.chdir(tmp)
        scope = prepare_diff_scope(f"{a}...{b}", scope_file=Path(tmp) / "scope.txt", diff_file=Path(tmp) / "review.diff")
        r.test("three-dot range resolves", scope.source.startswith("range:"),
               f"got source={scope.source}")


def test_range_arg_malformed(r: TestRunner):
    with tempfile.TemporaryDirectory() as tmp:
        make_repo(tmp)
        os.chdir(tmp)
        try:
            prepare_diff_scope("bad..junk..ref")
            r.test("malformed range raises", False, "no exception")
        except DiffScopeError:
            r.test("malformed range raises", True)


# --- Tests: PR# arg ----------------------------------------------------------

def _install_fake_gh(tmp: str, stdout: str, exit_code: int) -> str:
    """Create a fake gh binary that prints `stdout` and exits `exit_code`.

    Returns the bin directory path to prepend to PATH.
    """
    bin_dir = Path(tmp) / "fakebin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    # Use a here-doc-esque approach so the fake gh prints exactly `stdout`.
    # We write the stdout to a sidecar file and have the gh script cat it,
    # which avoids shell-escaping headaches for diffs containing quotes.
    out_file = bin_dir / "stdout.txt"
    out_file.write_text(stdout)
    gh.write_text(
        "#!/bin/bash\n"
        f"cat {out_file}\n"
        f"exit {exit_code}\n"
    )
    gh.chmod(0o755)
    return str(bin_dir)


def test_pr_gh_missing(r: TestRunner):
    with tempfile.TemporaryDirectory() as tmp:
        make_repo(tmp)
        os.chdir(tmp)
        old_path = os.environ.get("PATH", "")
        # PATH without any gh
        os.environ["PATH"] = "/usr/bin:/bin"
        try:
            prepare_diff_scope("1234")
            r.test("gh missing raises", False, "no exception")
        except DiffScopeError as e:
            msg = str(e).lower()
            r.test("gh missing raises with install hint",
                   "gh" in msg and ("cli" in msg or "install" in msg),
                   f"got: {e}")
        except NotImplementedError as e:
            # Expected during RED phase before Task 7
            r.test("gh missing raises with install hint", False,
                   f"RED: got NotImplementedError: {e}")
        finally:
            os.environ["PATH"] = old_path


def test_pr_gh_succeeds(r: TestRunner):
    with tempfile.TemporaryDirectory() as tmp:
        make_repo(tmp)
        fake_diff = "diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -0,0 +1 @@\n+hello\n"
        fake_bin = _install_fake_gh(tmp, fake_diff, 0)
        os.chdir(tmp)
        old_path = os.environ.get("PATH", "")
        os.environ["PATH"] = f"{fake_bin}:{old_path}"
        try:
            scope = prepare_diff_scope("1234", scope_file=Path(tmp) / "scope.txt", diff_file=Path(tmp) / "review.diff")
            r.test("pr arg source correct", scope.source == "pr:1234",
                   f"got {scope.source}")
            r.test("pr arg parsed a.py from diff", "a.py" in scope.files,
                   f"got {scope.files}")
        except NotImplementedError as e:
            r.test("pr arg source correct", False, f"RED: got NotImplementedError: {e}")
            r.test("pr arg parsed a.py from diff", False, f"RED: got NotImplementedError: {e}")
        finally:
            os.environ["PATH"] = old_path


def test_pr_gh_not_found(r: TestRunner):
    with tempfile.TemporaryDirectory() as tmp:
        make_repo(tmp)
        fake_bin = _install_fake_gh(tmp, "GraphQL: Could not resolve to a PullRequest", 1)
        os.chdir(tmp)
        old_path = os.environ.get("PATH", "")
        os.environ["PATH"] = f"{fake_bin}:{old_path}"
        try:
            prepare_diff_scope("9999")
            r.test("pr not-found raises", False, "no exception")
        except DiffScopeError as e:
            msg = str(e).lower()
            r.test("pr not-found raises", "not found" in msg or "access" in msg,
                   f"got: {e}")
        except NotImplementedError as e:
            r.test("pr not-found raises", False, f"RED: got NotImplementedError: {e}")
        finally:
            os.environ["PATH"] = old_path


def test_pr_gh_not_authed(r: TestRunner):
    with tempfile.TemporaryDirectory() as tmp:
        make_repo(tmp)
        fake_bin = _install_fake_gh(tmp, "auth status failed", 4)
        os.chdir(tmp)
        old_path = os.environ.get("PATH", "")
        os.environ["PATH"] = f"{fake_bin}:{old_path}"
        try:
            prepare_diff_scope("1234")
            r.test("pr not-authed raises", False, "no exception")
        except DiffScopeError:
            r.test("pr not-authed raises", True)
        except NotImplementedError as e:
            r.test("pr not-authed raises", False, f"RED: got NotImplementedError: {e}")
        finally:
            os.environ["PATH"] = old_path


# --- Tests: config override --------------------------------------------------

def test_config_override_applied(r: TestRunner):
    """Explicit base= parameter threads through to Scope.base_ref."""
    with tempfile.TemporaryDirectory() as tmp:
        make_repo(tmp)
        _run(["git", "update-ref", "refs/remotes/origin/main", "HEAD"], cwd=tmp)
        _run(["git", "checkout", "-b", "feat/x"], cwd=tmp)
        write_and_stage(tmp, "z.py", "z\n")
        _run(["git", "commit", "-m", "z"], cwd=tmp)
        os.chdir(tmp)
        scope = prepare_diff_scope(
            None,
            base="origin/main",
            scope_file=Path(tmp) / "scope.txt",
            diff_file=Path(tmp) / "review.diff",
        )
        r.test("explicit base override threaded through",
               scope.base_ref == "origin/main",
               f"got {scope.base_ref}")


def test_config_default_used(r: TestRunner):
    """When no base is passed, DEFAULT_BASE is used."""
    with tempfile.TemporaryDirectory() as tmp:
        make_repo(tmp)
        _run(["git", "checkout", "-b", "feat/x"], cwd=tmp)
        write_and_stage(tmp, "z.py", "z\n")
        _run(["git", "commit", "-m", "z"], cwd=tmp)
        os.chdir(tmp)
        scope = prepare_diff_scope(
            None,
            scope_file=Path(tmp) / "scope.txt",
            diff_file=Path(tmp) / "review.diff",
        )
        r.test("default base used when not overridden",
               scope.base_ref == DEFAULT_BASE,
               f"got {scope.base_ref}")


# --- Tests: ensure_scope fallback --------------------------------------------

def test_ensure_scope_uses_precomputed(r: TestRunner):
    """ensure_scope reads pre-existing files without re-running git diff."""
    with tempfile.TemporaryDirectory() as tmp:
        scope_f = Path(tmp) / "scope.txt"
        diff_f = Path(tmp) / "review.diff"
        scope_f.write_text("a.py\nb.py\n")
        diff_f.write_text("fake diff content\n")
        try:
            scope = ensure_scope(scope_file=scope_f, diff_file=diff_f)
            r.test("ensure reads precomputed files",
                   scope.files == ["a.py", "b.py"],
                   f"got {scope.files}")
            r.test("ensure reads diff text",
                   "fake diff" in scope.diff_text,
                   "diff content not read")
        except NotImplementedError as e:
            r.test("ensure reads precomputed files", False,
                   f"RED: got NotImplementedError: {e}")
            r.test("ensure reads diff text", False,
                   f"RED: got NotImplementedError: {e}")


def test_ensure_scope_computes_on_demand(r: TestRunner):
    """ensure_scope falls back to prepare_diff_scope(None) when files absent."""
    with tempfile.TemporaryDirectory() as tmp:
        make_repo(tmp)
        write_and_stage(tmp, "x.py", "x\n")
        os.chdir(tmp)
        scope_f = Path(tmp) / "scope.txt"
        diff_f = Path(tmp) / "review.diff"
        # Files don't exist yet
        try:
            scope = ensure_scope(scope_file=scope_f, diff_file=diff_f)
            r.test("ensure falls back to prepare when files absent",
                   scope.files == ["x.py"],
                   f"got {scope.files}")
            r.test("ensure wrote files during fallback",
                   scope_f.exists() and diff_f.exists(),
                   "files not written")
        except NotImplementedError as e:
            r.test("ensure falls back to prepare when files absent", False,
                   f"RED: got NotImplementedError: {e}")
            r.test("ensure wrote files during fallback", False,
                   f"RED: got NotImplementedError: {e}")


# --- Tests: wrapper script integration ---------------------------------------

def test_wrapper_smoke(r: TestRunner):
    """plugins/requirements-framework/scripts/prepare-diff-scope --ensure writes expected files."""
    with tempfile.TemporaryDirectory() as tmp:
        make_repo(tmp)
        write_and_stage(tmp, "smoke.py", "smoke\n")
        # Wrapper writes to /tmp/review_scope.txt + /tmp/review.diff by default.
        # Clear them first so we actually exercise the fallback path.
        for default in ("/tmp/review_scope.txt", "/tmp/review.diff"):
            try:
                Path(default).unlink()
            except FileNotFoundError:
                pass
        os.chdir(tmp)
        repo_root = Path(__file__).parent.parent
        wrapper = repo_root / "plugins" / "requirements-framework" / "scripts" / "prepare-diff-scope"
        result = subprocess.run(
            [str(wrapper), "--ensure"],
            cwd=tmp,
            capture_output=True,
            text=True,
        )
        r.test("wrapper exits 0",
               result.returncode == 0,
               f"rc={result.returncode} stderr={result.stderr}")
        r.test("wrapper wrote /tmp/review_scope.txt",
               Path("/tmp/review_scope.txt").exists(),
               "scope file missing after wrapper run")


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

    print("\nBranch arg:")
    test_branch_arg_valid(runner)
    test_branch_arg_not_found(runner)
    test_branch_arg_identical_to_base(runner)

    print("\nRange arg:")
    test_range_arg_two_dot(runner)
    test_range_arg_three_dot(runner)
    test_range_arg_malformed(runner)

    print("\nPR# arg:")
    test_pr_gh_missing(runner)
    test_pr_gh_succeeds(runner)
    test_pr_gh_not_found(runner)
    test_pr_gh_not_authed(runner)

    print("\nConfig override:")
    test_config_override_applied(runner)
    test_config_default_used(runner)

    print("\nEnsure scope fallback:")
    test_ensure_scope_uses_precomputed(runner)
    test_ensure_scope_computes_on_demand(runner)

    print("\nWrapper integration:")
    test_wrapper_smoke(runner)
    sys.exit(runner.summary())


if __name__ == "__main__":
    main()
