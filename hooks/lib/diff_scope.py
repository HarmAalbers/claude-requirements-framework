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

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

# Import run_git from the same lib directory
sys.path.insert(0, str(Path(__file__).parent))
from git_utils import run_git  # noqa: E402
from logger import get_logger  # noqa: E402


DEFAULT_SCOPE_FILE = Path("/tmp/review_scope.txt")
DEFAULT_DIFF_FILE = Path("/tmp/review.diff")
DEFAULT_BASE = "origin/master"
LARGE_DIFF_BYTES = 1_000_000  # 1 MB — warn but don't truncate

_RANGE_RE = re.compile(r"^[^.\s]+\.{2,3}[^.\s]+$")


_log = get_logger()


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


def _is_git_repo(cwd: str | None = None) -> bool:
    code, _, _ = run_git("git rev-parse --git-dir", cwd=cwd)
    return code == 0


def _write_scope_files(
    files: list[str],
    diff_text: str,
    scope_file: Path,
    diff_file: Path,
) -> None:
    scope_file.write_text("\n".join(files) + ("\n" if files else ""))
    diff_file.write_text(diff_text)
    if len(diff_text) > LARGE_DIFF_BYTES:
        _log.warning(
            f"review diff exceeds {LARGE_DIFF_BYTES} bytes ({len(diff_text)} bytes)"
        )


def _resolve_empty(base: str) -> tuple[list[str], str, str, str | None]:
    """Return (files, diff_text, source, base_ref) for empty arg."""
    # Staged
    code, staged_names, _ = run_git("git diff --cached --name-only --diff-filter=ACMRD")
    if code == 0 and staged_names:
        files = [line for line in staged_names.splitlines() if line]
        _, diff_text, _ = run_git("git diff --cached")
        return files, diff_text, "staged", None

    # Unstaged (modified tracked files + untracked files)
    _, un_names, _ = run_git("git diff --name-only --diff-filter=ACMRD")
    _, untracked, _ = run_git("git ls-files --others --exclude-standard")
    un_files = [line for line in un_names.splitlines() if line]
    untracked_files = [line for line in untracked.splitlines() if line]
    # Preserve order: modified first, then untracked, deduped.
    seen: set[str] = set()
    files: list[str] = []
    for name in un_files + untracked_files:
        if name not in seen:
            seen.add(name)
            files.append(name)
    if files:
        _, diff_text, _ = run_git("git diff")
        return files, diff_text, "unstaged", None

    # Branch vs base
    code, branch, _ = run_git("git symbolic-ref --short HEAD")
    if code != 0 or not branch:
        # Detached HEAD — fall back to SHA
        _, sha, _ = run_git("git rev-parse HEAD")
        branch = sha

    verify_code, _, _ = run_git(f"git rev-parse --verify {base}")
    if verify_code != 0:
        raise DiffScopeError(f"base ref not found: {base}")

    code, names, _ = run_git(f"git diff --name-only {base}...HEAD")
    files = [line for line in names.splitlines() if line] if code == 0 else []
    _, diff_text, _ = run_git(f"git diff {base}...HEAD")
    return files, diff_text, f"branch:{branch}", base


def _classify_arg(arg: str) -> str:
    """Return 'range', 'pr', or 'branch' based on shape."""
    if _RANGE_RE.match(arg):
        return "range"
    if arg.lstrip("#").isdigit():
        return "pr"
    return "branch"


def _resolve_branch(branch: str, base: str) -> tuple[list[str], str, str, str | None]:
    code, _, _ = run_git(f"git rev-parse --verify {branch}")
    if code != 0:
        raise DiffScopeError(f"branch '{branch}' not found")
    # Validate base ref too (consistent with _resolve_empty)
    verify_code, _, _ = run_git(f"git rev-parse --verify {base}")
    if verify_code != 0:
        raise DiffScopeError(f"base ref not found: {base}")
    code, names, _ = run_git(f"git diff --name-only {base}...{branch}")
    files = [line for line in names.splitlines() if line] if code == 0 else []
    _, diff_text, _ = run_git(f"git diff {base}...{branch}")
    return files, diff_text, f"branch:{branch}", base


def _resolve_range(rng: str) -> tuple[list[str], str, str, str | None]:
    code, names, err = run_git(f"git diff --name-only {rng}")
    if code != 0:
        raise DiffScopeError(f"invalid range '{rng}': {err}")
    files = [line for line in names.splitlines() if line]
    _, diff_text, _ = run_git(f"git diff {rng}")
    return files, diff_text, f"range:{rng}", None


def prepare_diff_scope(
    arg: str | None = None,
    scope_file: Path = DEFAULT_SCOPE_FILE,
    diff_file: Path = DEFAULT_DIFF_FILE,
    base: str = DEFAULT_BASE,
) -> Scope:
    """Resolve `arg` to a Scope and write both files. See module docstring."""
    if not _is_git_repo():
        raise DiffScopeError("not a git repository")

    if not arg:
        files, diff_text, source, base_ref = _resolve_empty(base)
        _write_scope_files(files, diff_text, scope_file, diff_file)
        return Scope(
            files=files,
            diff_text=diff_text,
            scope_file=scope_file,
            diff_file=diff_file,
            source=source,
            base_ref=base_ref,
        )

    # Non-empty arg: classify and dispatch
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
    return Scope(
        files=files,
        diff_text=diff_text,
        scope_file=scope_file,
        diff_file=diff_file,
        source=source,
        base_ref=base_ref,
    )


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
