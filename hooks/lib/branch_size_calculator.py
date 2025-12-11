#!/usr/bin/env python3
"""
Branch Size Calculator

Calculates the total number of line changes (insertions + deletions) on a
branch compared to its base branch. Supports stacked PRs.

Security: Uses subprocess with list arguments to prevent command injection.
"""

import subprocess
import re
from typing import Optional
from calculator_interface import RequirementCalculator


class BranchSizeCalculator(RequirementCalculator):
    """
    Calculates branch size (line changes) for dynamic requirement checking.

    Features:
    - Three-way calculation: committed + staged + unstaged changes
    - Stacked PR support: detects parent feature branch via merge-base
    - Fail-open: returns None on any error (never blocks legitimate work)
    - Security: No command injection (uses subprocess with list args)
    """

    def calculate(self, project_dir: str, branch: str, **kwargs) -> Optional[dict]:
        """
        Calculate total line changes on current branch.

        Args:
            project_dir: Project root directory
            branch: Current git branch name

        Returns:
            None if check should be skipped (main branch, errors, etc.)
            Dict with:
                - 'value': Total line changes (int)
                - 'summary': Human-readable summary (str)
                - 'committed': {ins, del} dict
                - 'staged': {ins, del} dict
                - 'unstaged': {ins, del} dict
                - 'base_branch': Base branch name (str)
        """
        try:
            # Skip protected branches
            if branch in ('main', 'master'):
                return None

            # Skip detached HEAD (branch name is a commit hash)
            # Commit hashes are 40 hex characters
            if len(branch) == 40 and all(c in '0123456789abcdef' for c in branch):
                return None

            # Find base branch (with stacked PR support)
            base_branch = self._find_base_branch(branch, project_dir)
            if not base_branch:
                return None  # No base found, skip check

            # Calculate changes (committed + staged + unstaged)
            committed = self._diff_shortstat(project_dir, f'{base_branch}...HEAD')
            staged = self._diff_shortstat(project_dir, '--cached')
            unstaged = self._diff_shortstat(project_dir, None)

            total = (committed['ins'] + committed['del'] +
                    staged['ins'] + staged['del'] +
                    unstaged['ins'] + unstaged['del'])

            summary = self._format_summary(committed, staged, unstaged)

            return {
                'value': total,  # Required for threshold comparison
                'summary': summary,  # Required for display
                'committed': committed,
                'staged': staged,
                'unstaged': unstaged,
                'base_branch': base_branch
            }

        except Exception:
            # FAIL OPEN - never block on calculator errors
            return None

    def _find_base_branch(self, branch: str, project_dir: str) -> Optional[str]:
        """
        Find base branch (stacked PR aware).

        Tries in order:
        1. Parent feature branch (for stacked PRs)
        2. origin/main
        3. origin/master

        Args:
            branch: Current branch name
            project_dir: Project directory

        Returns:
            Base branch name or None if not found
        """
        # Try parent branch via merge-base (stacked PR support)
        parent = self._find_parent_branch(branch, project_dir)
        if parent:
            return parent

        # Try origin/main
        if self._branch_exists(project_dir, 'origin/main'):
            return 'origin/main'

        # Try origin/master
        if self._branch_exists(project_dir, 'origin/master'):
            return 'origin/master'

        # Try local main
        if self._branch_exists(project_dir, 'main'):
            return 'main'

        # Try local master
        if self._branch_exists(project_dir, 'master'):
            return 'master'

        return None

    def _find_parent_branch(self, branch: str, project_dir: str) -> Optional[str]:
        """
        Find parent feature branch for stacked PRs.

        Uses merge-base to find the closest feature/* or fix/* branch.

        Args:
            branch: Current branch name
            project_dir: Project directory

        Returns:
            Parent branch name or None if not a stacked PR
        """
        try:
            # Get all local branches
            result = self._run_git(['branch'], project_dir)
            if result[0] != 0:
                return None

            branches = [b.strip().lstrip('* ') for b in result[1].split('\n') if b.strip()]

            # Find feature/fix branches (excluding current branch)
            candidate_branches = [
                b for b in branches
                if (b.startswith('feature/') or b.startswith('fix/'))
                and b != branch
            ]

            if not candidate_branches:
                return None

            # Find the closest parent via merge-base
            # The parent is the branch with the most recent common ancestor
            best_parent = None
            best_commit_count = float('inf')

            for candidate in candidate_branches:
                # Get merge-base
                result = self._run_git(['merge-base', branch, candidate], project_dir)
                if result[0] != 0:
                    continue

                merge_base = result[1]

                # Count commits from merge-base to current branch
                result = self._run_git(['rev-list', '--count', f'{merge_base}..{branch}'],
                                      project_dir)
                if result[0] != 0:
                    continue

                commit_count = int(result[1])

                # Closest parent has fewest commits
                if commit_count < best_commit_count:
                    best_commit_count = commit_count
                    best_parent = candidate

            return best_parent

        except Exception:
            return None

    def _diff_shortstat(self, project_dir: str, ref: Optional[str]) -> dict:
        """
        Run git diff --shortstat and parse.

        For unstaged changes (ref=None), this includes:
        - Changes to tracked files (git diff)
        - Untracked files (counted via git ls-files)

        Args:
            project_dir: Project directory
            ref: Git ref to diff against (or None for working tree)

        Returns:
            Dict with 'ins' and 'del' keys (insertion and deletion counts)
        """
        try:
            args = ['diff', '--shortstat']
            if ref:
                args.append(ref)

            result = self._run_git(args, project_dir)
            if result[0] != 0:
                return {'ins': 0, 'del': 0}

            changes = self._parse_shortstat(result[1])

            # For unstaged changes, also count untracked files
            if ref is None:
                untracked = self._count_untracked_lines(project_dir)
                changes['ins'] += untracked

            return changes

        except Exception:
            return {'ins': 0, 'del': 0}

    def _count_untracked_lines(self, project_dir: str) -> int:
        """
        Count lines in untracked files.

        Args:
            project_dir: Project directory

        Returns:
            Number of lines in untracked files
        """
        try:
            # Get list of untracked files
            result = self._run_git(['ls-files', '--others', '--exclude-standard'],
                                  project_dir)
            if result[0] != 0:
                return 0

            untracked_files = [f.strip() for f in result[1].split('\n') if f.strip()]

            total_lines = 0
            for file_path in untracked_files:
                full_path = f"{project_dir}/{file_path}"
                try:
                    with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                        total_lines += sum(1 for _ in f)
                except Exception:
                    pass  # Skip files that can't be read

            return total_lines

        except Exception:
            return 0

    def _parse_shortstat(self, output: str) -> dict:
        """
        Parse 'git diff --shortstat' output.

        Example outputs:
        - " 5 files changed, 120 insertions(+)"
        - " 2 files changed, 50 deletions(-)"
        - " 10 files changed, 200 insertions(+), 150 deletions(-)"

        Args:
            output: Output from git diff --shortstat

        Returns:
            Dict with 'ins' and 'del' keys
        """
        ins_match = re.search(r'(\d+) insertion', output)
        del_match = re.search(r'(\d+) deletion', output)

        return {
            'ins': int(ins_match.group(1)) if ins_match else 0,
            'del': int(del_match.group(1)) if del_match else 0
        }

    def _run_git(self, args: list[str], project_dir: str,
                timeout: int = 3) -> tuple[int, str, str]:
        """
        Run git command SAFELY (no shell injection).

        CRITICAL SECURITY: Uses list args, not f-strings, to prevent command injection.

        Args:
            args: Git command arguments as list (e.g., ['diff', '--shortstat'])
            project_dir: Working directory
            timeout: Timeout in seconds

        Returns:
            Tuple of (returncode, stdout, stderr)
        """
        try:
            result = subprocess.run(
                ['git'] + args,  # List, NOT f-string
                capture_output=True,
                text=True,
                cwd=project_dir,
                timeout=timeout,
                shell=False  # CRITICAL: no shell = no injection
            )
            return result.returncode, result.stdout.strip(), result.stderr.strip()
        except subprocess.TimeoutExpired:
            return -1, '', 'timeout'
        except Exception:
            return -1, '', 'error'

    def _branch_exists(self, project_dir: str, branch: str) -> bool:
        """
        Check if branch exists.

        Args:
            project_dir: Project directory
            branch: Branch name to check

        Returns:
            True if branch exists
        """
        result = self._run_git(['rev-parse', '--verify', branch], project_dir)
        return result[0] == 0

    def _format_summary(self, committed: dict, staged: dict, unstaged: dict) -> str:
        """
        Format one-line summary of changes.

        Args:
            committed: {ins, del} dict for committed changes
            staged: {ins, del} dict for staged changes
            unstaged: {ins, del} dict for unstaged changes

        Returns:
            Human-readable summary string

        Example:
            "committed: 200+/50- | staged: 100+/0- | unstaged: 10+/5-"
        """
        parts = []

        if committed['ins'] or committed['del']:
            parts.append(f"committed: {committed['ins']}+/{committed['del']}-")

        if staged['ins'] or staged['del']:
            parts.append(f"staged: {staged['ins']}+/{staged['del']}-")

        if unstaged['ins'] or unstaged['del']:
            parts.append(f"unstaged: {unstaged['ins']}+/{unstaged['del']}-")

        return ' | '.join(parts) if parts else 'no changes'


# Singleton instance for import
Calculator = BranchSizeCalculator
