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
