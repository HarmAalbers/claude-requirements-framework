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
import shutil
import subprocess
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


def _parse_diff_files(diff_text: str) -> list[str]:
    """Extract changed file paths from a unified diff (+++ b/... lines)."""
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
            capture_output=True,
            text=True,
            timeout=10,
        )
    except subprocess.TimeoutExpired:
        raise DiffScopeError(f"gh pr diff {num} timed out")

    if result.returncode != 0:
        combined = (result.stdout + "\n" + result.stderr).lower()
        if "could not resolve" in combined or "not found" in combined:
            raise DiffScopeError(f"PR #{num} not found or access denied")
        raise DiffScopeError(
            f"gh pr diff {num} failed: {result.stderr.strip() or result.stdout.strip()}"
        )

    diff_text = result.stdout
    files = _parse_diff_files(diff_text)
    return files, diff_text, f"pr:{num}", None


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
        files, diff_text, source, base_ref = _resolve_pr(arg)
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
    files = (
        [line for line in scope_file.read_text().splitlines() if line]
        if scope_file.exists()
        else []
    )
    diff_text = diff_file.read_text() if diff_file.exists() else ""
    return Scope(
        files=files,
        diff_text=diff_text,
        scope_file=scope_file,
        diff_file=diff_file,
        source="precomputed",
        base_ref=None,
    )


def ensure_scope(
    scope_file: Path = DEFAULT_SCOPE_FILE,
    diff_file: Path = DEFAULT_DIFF_FILE,
) -> Scope:
    """Agent entry: read pre-computed scope if present, else compute."""
    if scope_file.exists() and diff_file.exists() and scope_file.stat().st_size > 0:
        return read_scope(scope_file, diff_file)
    return prepare_diff_scope(None, scope_file=scope_file, diff_file=diff_file)


def base_from_config(project_dir: str | None = None) -> str:
    """Read hooks.diff_scope.base from the config cascade.

    Falls back to DEFAULT_BASE on any error. Config failures must never
    break scope resolution.
    """
    try:
        # Lazy imports: config stack may be unavailable in minimal environments.
        from config import RequirementsConfig  # noqa: WPS433
        from git_utils import resolve_project_root  # noqa: WPS433

        root = project_dir or resolve_project_root(verbose=False)
        cfg = RequirementsConfig(root)
        value = cfg.get_hook_config("diff_scope", "base", DEFAULT_BASE)
        return value if isinstance(value, str) and value else DEFAULT_BASE
    except Exception:
        return DEFAULT_BASE
