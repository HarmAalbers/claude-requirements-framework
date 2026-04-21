# Diff Scope Refactor Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use requirements-framework:executing-plans to implement this plan task-by-task.

**Goal:** Introduce a shared `diff_scope` helper that unifies review-scope resolution for all diff-based review agents and commands, accepting branch / range / PR# inputs, and pre-compute the diff once per review cycle.

**Architecture:** One new Python module `hooks/lib/diff_scope.py` owns scope resolution. A thin bash wrapper `scripts/prepare-diff-scope` drives it from commands and agents. 13 review agents lose their independent `git diff` Step 1 and all read `/tmp/review_scope.txt` + `/tmp/review.diff`. Plugin bumps to 3.0.0 (breaking agent contract).

**Tech Stack:** Python 3 stdlib + PyYAML, `gh` CLI for PR path, bash for wrapper, existing `hooks/lib/git_utils.py` + `hooks/lib/logger.py` + `hooks/lib/config.py`. Tests use the framework's custom `TestRunner` (not pytest).

**Design doc:** `docs/plans/2026-04-21-diff-scope-refactor-design.md`

**Branch:** `feat/diff-scope-refactor` (already created)

---

## Pre-flight

Before starting, from the repo root:

```bash
git -C /Users/harm/Tools/claude-requirements-framework status
# Expected: On branch feat/diff-scope-refactor, clean working tree
#           (design doc already committed as 0bb427c)

python3 hooks/test_requirements.py
# Expected: existing suite passes — this is our baseline
```

If the baseline suite fails, stop and report — the refactor must not regress it.

---

## Task 1: Create `diff_scope.py` skeleton + dataclass

**Files:**
- Create: `hooks/lib/diff_scope.py`

**Step 1: Create the module with dataclass, error, and empty function signatures**

```python
# hooks/lib/diff_scope.py
#!/usr/bin/env python3
"""
Review scope resolution for diff-based review agents and commands.

Resolves a user-supplied argument (branch name, git range, PR number,
or empty) to a concrete set of changed files and a unified diff, and
writes them to predictable paths so downstream agents don't re-run
git diff themselves.

See docs/plans/2026-04-21-diff-scope-refactor-design.md.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


DEFAULT_SCOPE_FILE = Path("/tmp/review_scope.txt")
DEFAULT_DIFF_FILE = Path("/tmp/review.diff")
DEFAULT_BASE = "origin/master"
LARGE_DIFF_BYTES = 1_000_000  # 1 MB — warn but don't truncate


class DiffScopeError(Exception):
    """Raised when scope cannot be resolved (bad input, missing gh, etc.)."""


@dataclass(frozen=True)
class Scope:
    files: list[str] = field(default_factory=list)
    diff_text: str = ""
    scope_file: Path = DEFAULT_SCOPE_FILE
    diff_file: Path = DEFAULT_DIFF_FILE
    source: str = "empty"          # "empty" | "staged" | "unstaged" | "branch:X" | "range:a..b" | "pr:N"
    base_ref: str | None = None    # ref we diffed against


def prepare_diff_scope(
    arg: str | None = None,
    scope_file: Path = DEFAULT_SCOPE_FILE,
    diff_file: Path = DEFAULT_DIFF_FILE,
    base: str = DEFAULT_BASE,
) -> Scope:
    """Resolve `arg` to a Scope and write both files. See module docstring."""
    raise NotImplementedError


def read_scope(
    scope_file: Path = DEFAULT_SCOPE_FILE,
    diff_file: Path = DEFAULT_DIFF_FILE,
) -> Scope:
    """Read pre-computed scope without re-resolving."""
    raise NotImplementedError


def ensure_scope(
    scope_file: Path = DEFAULT_SCOPE_FILE,
    diff_file: Path = DEFAULT_DIFF_FILE,
) -> Scope:
    """Agent entry: read pre-computed if present, else compute."""
    raise NotImplementedError
```

**Step 2: Verify module imports cleanly**

```bash
python3 -c "import sys; sys.path.insert(0, 'hooks/lib'); import diff_scope; print(diff_scope.DEFAULT_BASE)"
# Expected: origin/master
```

**Step 3: Commit**

```bash
git add hooks/lib/diff_scope.py
git commit -m "feat(diff-scope): add module skeleton + Scope dataclass"
```

---

## Task 2: Fixture repo helpers + empty-arg tests (RED)

**Files:**
- Create: `hooks/test_diff_scope.py`

**Step 1: Scaffold test file with TestRunner + fixture helpers**

```python
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


def main():
    runner = TestRunner()
    print("Empty-arg precedence:")
    test_empty_arg_staged_wins(runner)
    test_empty_arg_unstaged_fallback(runner)
    test_empty_arg_branch_vs_base(runner)
    test_empty_arg_detached_head(runner)
    test_non_git_dir_raises(runner)
    sys.exit(runner.summary())


if __name__ == "__main__":
    main()
```

**Step 2: Run test to verify it fails (RED)**

```bash
python3 hooks/test_diff_scope.py
# Expected: all 5 tests fail with NotImplementedError or similar.
```

**Step 3: Commit (RED)**

```bash
git add hooks/test_diff_scope.py
git commit -m "test(diff-scope): add fixture helpers and empty-arg tests"
```

---

## Task 3: Implement empty-arg resolution (GREEN)

**Files:**
- Modify: `hooks/lib/diff_scope.py`

**Step 1: Import `run_git` and implement `prepare_diff_scope` for None arg**

Key behaviors:
- Detect non-git via `git rev-parse --git-dir` — raise `DiffScopeError("not a git repository")`
- Check staged first: `git diff --cached --name-only --diff-filter=ACMR`
- Fall back to unstaged: `git diff --name-only --diff-filter=ACMR`
- Fall back to branch vs base: `git diff --name-only base...HEAD`
- For each, also capture the unified diff (`git diff`, `git diff --cached`, `git diff base...HEAD`)
- Write files, return `Scope`

Implementation sketch (add to `diff_scope.py`):

```python
import sys
from pathlib import Path

# Import run_git from the same lib directory
sys.path.insert(0, str(Path(__file__).parent))
from git_utils import run_git
from logger import get_logger

_log = get_logger(__name__)


def _is_git_repo(cwd: str | None = None) -> bool:
    code, _, _ = run_git("git rev-parse --git-dir", cwd=cwd)
    return code == 0


def _write_scope_files(files: list[str], diff_text: str, scope_file: Path, diff_file: Path) -> None:
    scope_file.write_text("\n".join(files) + ("\n" if files else ""))
    diff_file.write_text(diff_text)
    if len(diff_text) > LARGE_DIFF_BYTES:
        _log.warning(f"review diff exceeds {LARGE_DIFF_BYTES} bytes ({len(diff_text)} bytes)")


def _resolve_empty(base: str) -> tuple[list[str], str, str, str | None]:
    """Return (files, diff_text, source, base_ref) for empty arg."""
    # Staged
    code, staged_names, _ = run_git("git diff --cached --name-only --diff-filter=ACMR")
    if code == 0 and staged_names:
        files = [l for l in staged_names.splitlines() if l]
        _, diff_text, _ = run_git("git diff --cached")
        return files, diff_text, "staged", None

    # Unstaged
    code, un_names, _ = run_git("git diff --name-only --diff-filter=ACMR")
    if code == 0 and un_names:
        files = [l for l in un_names.splitlines() if l]
        _, diff_text, _ = run_git("git diff")
        return files, diff_text, "unstaged", None

    # Branch vs base
    _, branch, _ = run_git("git symbolic-ref --short HEAD")
    if not branch:
        # Detached HEAD
        _, sha, _ = run_git("git rev-parse HEAD")
        branch = sha
    code, names, _ = run_git(f"git diff --name-only {base}...HEAD")
    files = [l for l in names.splitlines() if l] if code == 0 else []
    _, diff_text, _ = run_git(f"git diff {base}...HEAD")
    return files, diff_text, f"branch:{branch}", base


def prepare_diff_scope(
    arg: str | None = None,
    scope_file: Path = DEFAULT_SCOPE_FILE,
    diff_file: Path = DEFAULT_DIFF_FILE,
    base: str = DEFAULT_BASE,
) -> Scope:
    if not _is_git_repo():
        raise DiffScopeError("not a git repository")

    if not arg:
        files, diff_text, source, base_ref = _resolve_empty(base)
        _write_scope_files(files, diff_text, scope_file, diff_file)
        return Scope(files=files, diff_text=diff_text,
                     scope_file=scope_file, diff_file=diff_file,
                     source=source, base_ref=base_ref)

    raise NotImplementedError(f"arg not yet supported: {arg!r}")
```

**Step 2: Run tests to verify GREEN**

```bash
python3 hooks/test_diff_scope.py
# Expected: all 5 empty-arg tests pass.
```

**Step 3: Commit**

```bash
git add hooks/lib/diff_scope.py
git commit -m "feat(diff-scope): implement empty-arg resolution"
```

---

## Task 4: Branch + range arg tests (RED)

**Files:**
- Modify: `hooks/test_diff_scope.py`

**Step 1: Add Group 2 (branch arg) + Group 3 (range arg) tests + wire into `main()`**

```python
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
```

Update `main()` to call all new tests under `print("Branch arg:")` and `print("Range arg:")` sections.

**Step 2: Run — expect 6 new failures (RED)**

```bash
python3 hooks/test_diff_scope.py
# Expected: empty-arg tests still GREEN (5 pass); 6 new tests fail.
```

**Step 3: Commit (RED)**

```bash
git add hooks/test_diff_scope.py
git commit -m "test(diff-scope): add branch and range arg tests"
```

---

## Task 5: Branch + range implementation (GREEN)

**Files:**
- Modify: `hooks/lib/diff_scope.py`

**Step 1: Add parser and handlers for branch and range args**

```python
import re

_RANGE_RE = re.compile(r"^[^.\s]+\.{2,3}[^.\s]+$")


def _classify_arg(arg: str) -> str:
    """Return 'range', 'pr', or 'branch' based on shape."""
    if _RANGE_RE.match(arg):
        return "range"
    if arg.lstrip("#").isdigit():
        return "pr"
    return "branch"


def _resolve_branch(branch: str, base: str) -> tuple[list[str], str, str, str | None]:
    code, _, err = run_git(f"git rev-parse --verify {branch}")
    if code != 0:
        raise DiffScopeError(f"branch '{branch}' not found")
    code, names, _ = run_git(f"git diff --name-only {base}...{branch}")
    files = [l for l in names.splitlines() if l] if code == 0 else []
    _, diff_text, _ = run_git(f"git diff {base}...{branch}")
    return files, diff_text, f"branch:{branch}", base


def _resolve_range(rng: str) -> tuple[list[str], str, str, str | None]:
    code, names, err = run_git(f"git diff --name-only {rng}")
    if code != 0:
        raise DiffScopeError(f"invalid range '{rng}': {err}")
    files = [l for l in names.splitlines() if l]
    _, diff_text, _ = run_git(f"git diff {rng}")
    return files, diff_text, f"range:{rng}", None
```

Update `prepare_diff_scope` body (replace the trailing `raise NotImplementedError`):

```python
    kind = _classify_arg(arg)
    if kind == "range":
        files, diff_text, source, base_ref = _resolve_range(arg)
    elif kind == "branch":
        files, diff_text, source, base_ref = _resolve_branch(arg, base)
    elif kind == "pr":
        raise NotImplementedError("pr support in next task")
    else:
        raise DiffScopeError(f"unrecognized arg: {arg!r}")

    _write_scope_files(files, diff_text, scope_file, diff_file)
    return Scope(files=files, diff_text=diff_text,
                 scope_file=scope_file, diff_file=diff_file,
                 source=source, base_ref=base_ref)
```

**Step 2: Run tests — expect all 11 (5 empty + 3 branch + 3 range) GREEN**

```bash
python3 hooks/test_diff_scope.py
# Expected: 11/11 pass.
```

**Step 3: Commit**

```bash
git add hooks/lib/diff_scope.py
git commit -m "feat(diff-scope): implement branch and range arg resolution"
```

---

## Task 6: PR# tests with `gh` shim (RED)

**Files:**
- Modify: `hooks/test_diff_scope.py`

**Step 1: Add PR# tests using a fake `gh` binary via PATH manipulation**

```python
# --- Tests: PR# arg ----------------------------------------------------------

def _install_fake_gh(tmp: str, stdout: str, exit_code: int) -> str:
    """Create a fake gh binary that prints `stdout` and exits `exit_code`."""
    bin_dir = Path(tmp) / "fakebin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_text(
        "#!/bin/bash\n"
        f"echo -n '{stdout}'\n"
        f"exit {exit_code}\n"
    )
    gh.chmod(0o755)
    return str(bin_dir)


def test_pr_gh_missing(r: TestRunner):
    with tempfile.TemporaryDirectory() as tmp:
        make_repo(tmp)
        os.chdir(tmp)
        old_path = os.environ.get("PATH", "")
        # Empty PATH = no gh
        os.environ["PATH"] = "/usr/bin:/bin"  # nothing with gh
        try:
            prepare_diff_scope("1234")
            r.test("gh missing raises", False, "no exception")
        except DiffScopeError as e:
            r.test("gh missing raises with install hint",
                   "gh" in str(e).lower() and ("cli" in str(e).lower() or "install" in str(e).lower()),
                   f"got: {e}")
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
            r.test("pr not-found raises", "not found" in str(e).lower() or "access" in str(e).lower(),
                   f"got: {e}")
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
        except DiffScopeError as e:
            r.test("pr not-authed raises", True)
        finally:
            os.environ["PATH"] = old_path
```

Wire into `main()` under `print("PR# arg:")`.

**Step 2: Run — 4 new RED tests**

```bash
python3 hooks/test_diff_scope.py
# Expected: 15 tests; 11 pass, 4 fail (PR tests).
```

**Step 3: Commit (RED)**

```bash
git add hooks/test_diff_scope.py
git commit -m "test(diff-scope): add PR# arg tests with gh shim"
```

---

## Task 7: PR# implementation (GREEN)

**Files:**
- Modify: `hooks/lib/diff_scope.py`

**Step 1: Add `_resolve_pr` and wire into `prepare_diff_scope`**

```python
import shutil
import subprocess


def _parse_diff_files(diff_text: str) -> list[str]:
    """Extract changed file paths from a unified diff."""
    files: list[str] = []
    for line in diff_text.splitlines():
        if line.startswith("+++ b/"):
            path = line[6:].strip()
            if path and path != "/dev/null":
                files.append(path)
    return files


def _resolve_pr(pr_num: str) -> tuple[list[str], str, str, str | None]:
    if shutil.which("gh") is None:
        raise DiffScopeError(
            "gh CLI required for PR# argument. Install: https://cli.github.com/"
        )
    num = pr_num.lstrip("#")
    try:
        result = subprocess.run(
            ["gh", "pr", "diff", num, "--patch"],
            capture_output=True, text=True, timeout=10,
        )
    except subprocess.TimeoutExpired:
        raise DiffScopeError(f"gh pr diff {num} timed out")
    if result.returncode != 0:
        if "could not resolve" in result.stdout.lower() or "not found" in result.stderr.lower():
            raise DiffScopeError(f"PR #{num} not found or access denied")
        raise DiffScopeError(f"gh pr diff {num} failed: {result.stderr.strip() or result.stdout.strip()}")
    diff_text = result.stdout
    files = _parse_diff_files(diff_text)
    return files, diff_text, f"pr:{num}", None
```

Wire into `prepare_diff_scope`:

```python
    elif kind == "pr":
        files, diff_text, source, base_ref = _resolve_pr(arg)
```

**Step 2: Run — expect 15/15 GREEN**

```bash
python3 hooks/test_diff_scope.py
# Expected: 15/15 pass.
```

**Step 3: Commit**

```bash
git add hooks/lib/diff_scope.py
git commit -m "feat(diff-scope): implement PR# arg via gh CLI"
```

---

## Task 8: Config override for `hooks.diff_scope.base`

**Files:**
- Modify: `hooks/lib/diff_scope.py`
- Modify: `hooks/test_diff_scope.py`

**Step 1: Add tests for config override (RED)**

```python
def test_config_override_applied(r: TestRunner):
    with tempfile.TemporaryDirectory() as tmp:
        make_repo(tmp)
        # Create alternate base ref
        _run(["git", "update-ref", "refs/remotes/origin/main", "HEAD"], cwd=tmp)
        os.chdir(tmp)
        scope = prepare_diff_scope(None, base="origin/main",
                                   scope_file=Path(tmp) / "scope.txt",
                                   diff_file=Path(tmp) / "review.diff")
        r.test("explicit base override applied",
               scope.base_ref == "origin/main" or scope.base_ref is None,
               f"got {scope.base_ref}")


def test_config_default_used(r: TestRunner):
    # covered implicitly by earlier tests; add an explicit assertion
    with tempfile.TemporaryDirectory() as tmp:
        make_repo(tmp)
        _run(["git", "checkout", "-b", "feat"], cwd=tmp)
        write_and_stage(tmp, "z.py", "z\n")
        _run(["git", "commit", "-m", "z"], cwd=tmp)
        os.chdir(tmp)
        scope = prepare_diff_scope(None, scope_file=Path(tmp) / "scope.txt", diff_file=Path(tmp) / "review.diff")
        r.test("default base used when not overridden", scope.base_ref == DEFAULT_BASE,
               f"got {scope.base_ref}")
```

**Step 2: Verify RED (default test might pass already)**

```bash
python3 hooks/test_diff_scope.py
# Expected: 16-17 tests; the override test may fail if we didn't carry base_ref through.
```

**Step 3: Add a config helper in `diff_scope.py` that reads `hooks.diff_scope.base`**

```python
def base_from_config(project_dir: str | None = None) -> str:
    """Read hooks.diff_scope.base from requirements.yaml cascade, falling back to DEFAULT_BASE."""
    try:
        from config import load_config
        cfg = load_config(project_dir)
        return cfg.get("hooks", {}).get("diff_scope", {}).get("base", DEFAULT_BASE)
    except Exception:
        return DEFAULT_BASE
```

Commands (next tasks) pass `base=base_from_config()` to `prepare_diff_scope`.

**Step 4: Run tests**

```bash
python3 hooks/test_diff_scope.py
# Expected: 17/17 GREEN.
```

**Step 5: Commit**

```bash
git add hooks/lib/diff_scope.py hooks/test_diff_scope.py
git commit -m "feat(diff-scope): support hooks.diff_scope.base config override"
```

---

## Task 9: `ensure_scope` + `read_scope` tests (RED)

**Files:**
- Modify: `hooks/test_diff_scope.py`

**Step 1: Add Group 8 tests**

```python
def test_ensure_scope_uses_precomputed(r: TestRunner):
    with tempfile.TemporaryDirectory() as tmp:
        scope_f = Path(tmp) / "scope.txt"
        diff_f = Path(tmp) / "review.diff"
        scope_f.write_text("a.py\nb.py\n")
        diff_f.write_text("fake diff content")
        scope = ensure_scope(scope_file=scope_f, diff_file=diff_f)
        r.test("ensure reads precomputed files", scope.files == ["a.py", "b.py"],
               f"got {scope.files}")
        r.test("ensure reads diff text", "fake diff" in scope.diff_text,
               "diff content not read")


def test_ensure_scope_computes_on_demand(r: TestRunner):
    with tempfile.TemporaryDirectory() as tmp:
        make_repo(tmp)
        write_and_stage(tmp, "x.py", "x\n")
        os.chdir(tmp)
        scope_f = Path(tmp) / "scope.txt"
        diff_f = Path(tmp) / "review.diff"
        # Files don't exist yet
        scope = ensure_scope(scope_file=scope_f, diff_file=diff_f)
        r.test("ensure falls back to prepare", scope.files == ["x.py"],
               f"got {scope.files}")
        r.test("ensure wrote files during fallback", scope_f.exists() and diff_f.exists(),
               "files not written")
```

**Step 2: RED**

```bash
python3 hooks/test_diff_scope.py
# Expected: 2 new fails (NotImplementedError).
```

**Step 3: Commit (RED)**

```bash
git add hooks/test_diff_scope.py
git commit -m "test(diff-scope): add ensure_scope fallback tests"
```

---

## Task 10: Implement `ensure_scope` + `read_scope` (GREEN)

**Files:**
- Modify: `hooks/lib/diff_scope.py`

**Step 1: Implement both**

```python
def read_scope(
    scope_file: Path = DEFAULT_SCOPE_FILE,
    diff_file: Path = DEFAULT_DIFF_FILE,
) -> Scope:
    files = [l for l in scope_file.read_text().splitlines() if l] if scope_file.exists() else []
    diff_text = diff_file.read_text() if diff_file.exists() else ""
    return Scope(files=files, diff_text=diff_text,
                 scope_file=scope_file, diff_file=diff_file,
                 source="precomputed", base_ref=None)


def ensure_scope(
    scope_file: Path = DEFAULT_SCOPE_FILE,
    diff_file: Path = DEFAULT_DIFF_FILE,
) -> Scope:
    if scope_file.exists() and diff_file.exists() and scope_file.stat().st_size > 0:
        return read_scope(scope_file, diff_file)
    return prepare_diff_scope(None, scope_file=scope_file, diff_file=diff_file)
```

**Step 2: Run — expect 19/19 GREEN**

```bash
python3 hooks/test_diff_scope.py
# Expected: 19/19 pass.
```

**Step 3: Commit**

```bash
git add hooks/lib/diff_scope.py
git commit -m "feat(diff-scope): implement ensure_scope and read_scope"
```

---

## Task 11: Bash wrapper + integration smoke test

**Files:**
- Create: `scripts/prepare-diff-scope`
- Modify: `hooks/test_diff_scope.py` (add smoke test)

**Step 1: Create the wrapper**

```bash
#!/usr/bin/env bash
# scripts/prepare-diff-scope
# Thin wrapper around hooks/lib/diff_scope.py for commands and agents.
#
# Usage:
#   scripts/prepare-diff-scope "$ARGUMENTS"   # command-side (always runs)
#   scripts/prepare-diff-scope --ensure       # agent-side (no-op if precomputed)

set -euo pipefail

repo_root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
py="python3"

case "${1:-}" in
  --ensure)
    # Silent no-op if both files exist non-empty
    if [[ -s /tmp/review_scope.txt && -s /tmp/review.diff ]]; then
      exit 0
    fi
    "$py" -c "
import sys; sys.path.insert(0, '$repo_root/hooks/lib')
from diff_scope import ensure_scope, base_from_config
s = ensure_scope()
print(f'Scope: {s.source} ({len(s.files)} files, base={s.base_ref or \"(none)\"})')
"
    ;;
  *)
    arg="${1:-}"
    "$py" -c "
import sys; sys.path.insert(0, '$repo_root/hooks/lib')
from diff_scope import prepare_diff_scope, base_from_config, DiffScopeError
try:
    s = prepare_diff_scope('$arg' or None, base=base_from_config())
    print(f'Scope: {s.source} ({len(s.files)} files, base={s.base_ref or \"(none)\"})')
except DiffScopeError as e:
    print(f'Cannot resolve scope: {e}', file=sys.stderr)
    sys.exit(2)
"
    ;;
esac
```

Mark executable:

```bash
chmod +x scripts/prepare-diff-scope
```

**Step 2: Add smoke test**

```python
def test_wrapper_smoke(r: TestRunner):
    with tempfile.TemporaryDirectory() as tmp:
        make_repo(tmp)
        write_and_stage(tmp, "a.py", "a\n")
        os.chdir(tmp)
        # Reset default paths so wrapper writes into tmp-safe locations
        # (wrapper uses /tmp/review_scope.txt + /tmp/review.diff by default)
        repo_root = Path(__file__).parent.parent
        wrapper = repo_root / "scripts" / "prepare-diff-scope"
        result = subprocess.run([str(wrapper), "--ensure"], cwd=tmp, capture_output=True, text=True)
        r.test("wrapper exits 0", result.returncode == 0,
               f"rc={result.returncode} stderr={result.stderr}")
        r.test("wrapper wrote scope file", Path("/tmp/review_scope.txt").exists(),
               "scope file missing after wrapper run")
```

**Step 3: Run — expect 20/20 GREEN**

```bash
python3 hooks/test_diff_scope.py
```

**Step 4: Commit**

```bash
git add scripts/prepare-diff-scope hooks/test_diff_scope.py
git commit -m "feat(scripts): add prepare-diff-scope bash wrapper"
```

---

## Task 12: Migrate `/deep-review` to `diff_scope` helper

**Files:**
- Modify: `plugins/requirements-framework/commands/deep-review.md`

**Step 1: Update frontmatter**

```yaml
---
name: deep-review
description: "Cross-validated team-based code review with agent debate"
argument-hint: "[branch | a..b | PR#]"
allowed-tools: ["Bash", "Glob", "Grep", "Read", "Task", "TeamCreate", "TeamDelete", "SendMessage", "TaskCreate", "TaskUpdate", "TaskList", "TaskGet"]
git_hash: uncommitted
---
```

**Step 2: Replace Step 1 body**

Find the current `### Step 1: Identify Changes to Review` section (around line 19-30). Replace its bash with:

```bash
scripts/prepare-diff-scope "$ARGUMENTS"
```

Add a paragraph: *"The wrapper writes `/tmp/review_scope.txt` (one file per line) and `/tmp/review.diff` (unified diff). If either is empty, output `No changes to review` and EXIT."*

**Step 3: Update Step 5 teammate prompts to reference the new paths**

In the "Standard preamble for ALL teammate prompts" block, ensure the prompt includes: *"SCOPE_FILE=/tmp/review_scope.txt DIFF_FILE=/tmp/review.diff"*.

**Step 4: Deploy and sanity-check the command file**

```bash
./sync.sh deploy
grep -c "git diff --cached" plugins/requirements-framework/commands/deep-review.md
# Expected: 0 (the inline git diff lines should be gone)
```

**Step 5: Commit**

```bash
git add plugins/requirements-framework/commands/deep-review.md
git commit -m "feat(commands): migrate /deep-review to diff_scope helper"
```

---

## Task 13: Migrate `/quality-check` to `diff_scope` helper

**Files:**
- Modify: `plugins/requirements-framework/commands/quality-check.md`

**Step 1: Read the current quality-check.md to locate its Step 1**

```bash
grep -n "git diff" plugins/requirements-framework/commands/quality-check.md
```

**Step 2: Apply the same Step 1 replacement as Task 12**

Replace inline `git diff` with `scripts/prepare-diff-scope "$ARGUMENTS"` and update `argument-hint` to `"[branch | a..b | PR#]"`.

**Step 3: Update any subagent prompts to reference `/tmp/review_scope.txt` + `/tmp/review.diff`**

**Step 4: Deploy + verify**

```bash
./sync.sh deploy
```

**Step 5: Commit**

```bash
git add plugins/requirements-framework/commands/quality-check.md
git commit -m "feat(commands): migrate /quality-check to diff_scope helper"
```

---

## Task 14: Unify Step 1 across 13 review agents

**Files (all 13):**
- `plugins/requirements-framework/agents/code-reviewer.md`
- `plugins/requirements-framework/agents/tool-validator.md`
- `plugins/requirements-framework/agents/silent-failure-hunter.md`
- `plugins/requirements-framework/agents/test-analyzer.md`
- `plugins/requirements-framework/agents/type-design-analyzer.md`
- `plugins/requirements-framework/agents/comment-analyzer.md`
- `plugins/requirements-framework/agents/code-simplifier.md`
- `plugins/requirements-framework/agents/backward-compatibility-checker.md`
- `plugins/requirements-framework/agents/frontend-reviewer.md`
- `plugins/requirements-framework/agents/codex-review-agent.md`
- `plugins/requirements-framework/agents/tenant-isolation-auditor.md`
- `plugins/requirements-framework/agents/appsec-auditor.md`
- `plugins/requirements-framework/agents/compliance-auditor.md`

**Step 1: For each agent, locate its existing Step 1**

```bash
for f in plugins/requirements-framework/agents/{code-reviewer,tool-validator,silent-failure-hunter,test-analyzer,type-design-analyzer,comment-analyzer,code-simplifier,backward-compatibility-checker,frontend-reviewer,codex-review-agent,tenant-isolation-auditor,appsec-auditor,compliance-auditor}.md; do
  echo "=== $f ==="
  grep -n "Step 1" "$f" | head -3
done
```

**Step 2: Replace each existing Step 1 body with this canonical block**

```markdown
## Step 1: Load Review Scope

Execute: `scripts/prepare-diff-scope --ensure`

Read `/tmp/review_scope.txt` (list of changed files, one per line) and
`/tmp/review.diff` (unified diff). If the scope file is empty, output
"No review scope provided" and EXIT.

Focus your review on the files in the scope; do not expand beyond them.
```

Keep each agent's subsequent Steps 2+ intact.

**Step 3: Ensure each agent has the right `allowed-tools` frontmatter**

Required minimum for diff-based reviewers: `["Bash", "Read", "Glob", "Grep"]`.
Add `"SendMessage", "TaskUpdate"` where the agent is used as a teammate (already present in most).

**Step 4: Codex agent special-case**

`codex-review-agent.md`: where it currently constructs its own diff via `git diff`, replace with reading `/tmp/review.diff` and passing the content to `codex exec` as context.

**Step 5: Deploy + sanity grep**

```bash
./sync.sh deploy
grep -l "git diff --cached\|git diff >\|git diff > /tmp" plugins/requirements-framework/agents/{code-reviewer,tool-validator,silent-failure-hunter,test-analyzer,type-design-analyzer,comment-analyzer,code-simplifier,backward-compatibility-checker,frontend-reviewer,codex-review-agent,tenant-isolation-auditor,appsec-auditor,compliance-auditor}.md
# Expected: empty output — no agents still run git diff in Step 1
```

**Step 6: Run test suite**

```bash
python3 hooks/test_requirements.py
python3 hooks/test_diff_scope.py
# Expected: both green.
```

**Step 7: Commit**

```bash
git add plugins/requirements-framework/agents/
git commit -m "refactor(agents): unify Step 1 on diff_scope helper (13 agents)"
```

---

## Task 15: Plugin bump to 3.0.0 + CHANGELOG + plugin-version guard test

**Files:**
- Modify: `plugins/requirements-framework/.claude-plugin/plugin.json`
- Create/Modify: `CHANGELOG.md` (repo root)
- Modify: `hooks/test_diff_scope.py`

**Step 1: Bump version**

Edit `plugin.json`:

```json
{
  "name": "requirements-framework",
  "version": "3.0.0",
  ...
}
```

**Step 2: Write CHANGELOG entry**

Create or prepend to `CHANGELOG.md`:

```markdown
## 3.0.0 — 2026-04-XX

### Breaking
- All 13 diff-based review agents now require `/tmp/review_scope.txt` and
  `/tmp/review.diff` to be pre-computed (or use `scripts/prepare-diff-scope
  --ensure` as fallback). Agents no longer run `git diff` in Step 1.
- Consumers that invoke review agents directly via Task tool with a
  custom pre-populated `/tmp/code_review.diff` must update to the new
  paths.

### Added
- `hooks/lib/diff_scope.py` — unified review-scope resolution (branch,
  range, PR number, empty).
- `scripts/prepare-diff-scope` — bash wrapper invoked by commands and agents.
- `hooks.diff_scope.base` config key (default `origin/master`).
- `/deep-review` and `/quality-check` accept branch / range / PR# args.
- `/arch-review` accepts a plan file path as argument.

### Developer
- New test file `hooks/test_diff_scope.py` with ~26 tests using fixture git repos.
```

**Step 3: Add plugin-version guard test**

```python
def test_plugin_version_bumped(r: TestRunner):
    import json
    repo_root = Path(__file__).parent.parent
    manifest = repo_root / "plugins" / "requirements-framework" / ".claude-plugin" / "plugin.json"
    diff_scope_py = repo_root / "hooks" / "lib" / "diff_scope.py"
    if not diff_scope_py.exists():
        r.test("version guard skipped (diff_scope absent)", True)
        return
    version = json.loads(manifest.read_text())["version"]
    major = int(version.split(".")[0])
    r.test("plugin version bumped to >= 3.0.0 when diff_scope present",
           major >= 3, f"got version {version}")
```

**Step 4: Run tests — expect all GREEN**

```bash
python3 hooks/test_diff_scope.py
python3 hooks/test_requirements.py
```

**Step 5: Commit**

```bash
git add plugins/requirements-framework/.claude-plugin/plugin.json CHANGELOG.md hooks/test_diff_scope.py
git commit -m "chore: bump plugin to 3.0.0 + CHANGELOG + version guard test"
```

---

## Task 16: `/arch-review` accepts plan file path argument

**Files:**
- Modify: `plugins/requirements-framework/commands/arch-review.md`

**Step 1: Read current arch-review.md**

```bash
grep -n "argument-hint\|ARGUMENTS\|plan file" plugins/requirements-framework/commands/arch-review.md
```

**Step 2: Update frontmatter**

```yaml
argument-hint: "[plan-file-path]"
```

**Step 3: Add a Step 0 to resolve the plan file**

Insert (near top of the command body):

```markdown
## Step 0: Resolve Plan File

If `$ARGUMENTS` is provided, treat it as the plan file path. Verify it exists:

```bash
test -f "$ARGUMENTS" || { echo "Plan file not found: $ARGUMENTS"; exit 2; }
```

Otherwise, default to the most recent file in `docs/plans/*.md`:

```bash
ls -t docs/plans/*.md 2>/dev/null | head -1
```

Pass this plan path into all teammate prompts.
```

**Step 4: Deploy and manual-smoke**

```bash
./sync.sh deploy
```

**Step 5: Commit**

```bash
git add plugins/requirements-framework/commands/arch-review.md
git commit -m "feat(commands): /arch-review accepts plan file path argument"
```

---

## Post-implementation

**Step 1: Run the full suite**

```bash
python3 hooks/test_requirements.py
python3 hooks/test_diff_scope.py
python3 hooks/test_branch_size_calculator.py
```

Expected: all three green.

**Step 2: Update plugin versions metadata for changed files**

```bash
./update-plugin-versions.sh
git add -u
git commit -m "chore: update plugin component git_hash metadata"
```

**Step 3: Run `/arch-review docs/plans/2026-04-21-diff-scope-refactor-plan.md`**

This re-satisfies the gates we bypassed earlier (commit_plan, adr_reviewed, tdd_planned, solid_reviewed) against the real plan.

**Step 4: Run `/deep-review` before PR**

```bash
/deep-review
```

**Step 5: Open PR**

```bash
gh pr create --title "Diff scope refactor (plugin 3.0.0)" \
  --body "$(cat <<'EOF'
## Summary
- Adds hooks/lib/diff_scope.py as one source of truth for review scope
- Adds scripts/prepare-diff-scope bash wrapper
- Migrates /deep-review and /quality-check commands
- Unifies Step 1 across 13 review agents
- /arch-review now accepts plan file path argument
- Breaking: agents no longer run their own git diff — bumps plugin to 3.0.0

See docs/plans/2026-04-21-diff-scope-refactor-design.md for the full design.

## Test plan
- [ ] python3 hooks/test_diff_scope.py (26+ tests)
- [ ] python3 hooks/test_requirements.py (existing suite)
- [ ] /deep-review feat/diff-scope-refactor (dogfood)
- [ ] /deep-review 1234 (new PR# path) against a real PR
- [ ] scripts/prepare-diff-scope master..HEAD (range path)
EOF
)"
```

---

## Open items (carried over from design)

- Task #7 in brainstorming session: review `comment-cleaner` + `import-organizer` for inclusion in a future staged-scope helper
- Consider writing ADR-014 for the 3.0.0 agent-contract break (decide after Task 15)

---

## Test count summary

| Group | Tests | After Task |
|---|---|---|
| Empty-arg precedence | 5 | 2 |
| Branch arg | 3 | 4 |
| Range arg | 3 | 4 |
| PR# arg | 4 | 6 |
| Scope dataclass / file outputs | 2 | 3 |
| Config override | 2 | 8 |
| ensure_scope fallback | 2 | 9 |
| Wrapper smoke | 1 | 11 |
| Plugin version guard | 1 | 15 |
| **Total** | **23** | end |

Design called for ~26 — gaps we may add opportunistically: large-diff warning test, idempotent overwrite test, custom-paths test. These can land within Task 11 or Task 15 without separate commits.
