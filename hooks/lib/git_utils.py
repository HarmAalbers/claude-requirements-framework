#!/usr/bin/env python3
"""
Git operation helpers for requirements framework.

Provides safe, timeout-protected git operations for:
- Getting current branch name
- Listing all branches
- Checking if directory is a git repo
"""
import subprocess
import os
from typing import Optional


def run_git(cmd: str, cwd: Optional[str] = None) -> tuple[int, str, str]:
    """
    Run a git command safely with timeout.

    Args:
        cmd: Git command to run (e.g., "git status")
        cwd: Working directory (defaults to current)

    Returns:
        Tuple of (exit_code, stdout, stderr)
        - exit_code: 0 for success, non-zero for failure
        - stdout: Command output (stripped)
        - stderr: Error output (stripped)
    """
    if cwd is None:
        cwd = os.getcwd()

    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=3  # 3 second timeout
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, "", "timeout"
    except Exception as e:
        return -1, "", str(e)


def get_current_branch(project_dir: Optional[str] = None) -> Optional[str]:
    """
    Get the current git branch name.

    Args:
        project_dir: Project directory (defaults to cwd)

    Returns:
        Branch name (e.g., "feature/auth") or None if:
        - Not a git repo
        - Detached HEAD state
        - Git command failed
    """
    code, branch, _ = run_git("git symbolic-ref --short HEAD", project_dir)
    return branch if code == 0 and branch else None


def get_all_branches(project_dir: Optional[str] = None) -> list[str]:
    """
    Get all local branch names.

    Args:
        project_dir: Project directory (defaults to cwd)

    Returns:
        List of branch names (empty list if not a git repo)
    """
    code, output, _ = run_git(
        "git for-each-ref --format='%(refname:short)' refs/heads/",
        project_dir
    )
    if code != 0 or not output:
        return []

    # Strip quotes from each branch name
    return [b.strip("'") for b in output.split('\n') if b.strip()]


def is_git_repo(project_dir: Optional[str] = None) -> bool:
    """
    Check if directory is inside a git repository.

    Args:
        project_dir: Directory to check (defaults to cwd)

    Returns:
        True if inside a git repo, False otherwise
    """
    code, _, _ = run_git("git rev-parse --git-dir", project_dir)
    return code == 0


def get_git_root(project_dir: Optional[str] = None) -> Optional[str]:
    """
    Get the root directory of the git repository.

    Args:
        project_dir: Starting directory (defaults to cwd)

    Returns:
        Absolute path to git root, or None if not in a repo
    """
    code, root, _ = run_git("git rev-parse --show-toplevel", project_dir)
    return root if code == 0 and root else None


if __name__ == "__main__":
    # Quick test
    print(f"Is git repo: {is_git_repo()}")
    print(f"Current branch: {get_current_branch()}")
    print(f"Git root: {get_git_root()}")
    print(f"All branches: {get_all_branches()}")
