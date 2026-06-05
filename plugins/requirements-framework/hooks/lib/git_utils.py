#!/usr/bin/env python3
"""
Git operation helpers for requirements framework.

Provides safe, timeout-protected git operations for:
- Getting current branch name
- Listing all branches
- Checking if directory is a git repo
"""
import os
import subprocess
from typing import Optional

from logger import get_logger

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


def get_git_common_dir(project_dir: Optional[str] = None) -> Optional[str]:
    """
    Get the common git directory (shared across worktrees).

    In a regular repo, returns the .git directory.
    In a worktree, returns the main repo's .git directory.

    This ensures state is shared across all worktrees of the same repo.

    Args:
        project_dir: Starting directory (defaults to cwd)

    Returns:
        Absolute path to common git directory, or None if not in a repo
    """
    code, common_dir, _ = run_git("git rev-parse --git-common-dir", project_dir)
    if code != 0 or not common_dir:
        return None

    # Handle relative path (git returns ".git" in main repos)
    if not common_dir.startswith('/'):
        base = project_dir if project_dir else os.getcwd()
        common_dir = os.path.abspath(os.path.join(base, common_dir))

    return common_dir


def resolve_project_root(start_dir: Optional[str] = None, verbose: bool = True) -> str:
    """
    Resolve the project root directory for requirements framework.

    This ensures the framework works correctly even when Claude Code
    cd's into a subdirectory of the project.

    Priority:
    1. CLAUDE_PROJECT_DIR environment variable (if set)
    2. Git repository root (if in a git repo)
    3. Current working directory (fallback)

    Args:
        start_dir: Starting directory (defaults to cwd)
        verbose: If True, log when resolving to different directory

    Returns:
        Absolute path to project root directory
    """
    # Priority 1: Explicit CLAUDE_PROJECT_DIR
    if 'CLAUDE_PROJECT_DIR' in os.environ:
        return os.environ['CLAUDE_PROJECT_DIR']

    # Priority 2: Git root
    cwd = start_dir or os.getcwd()
    git_root = get_git_root(cwd)

    if git_root:
        # Log if we resolved to a different directory than cwd
        if verbose and os.path.realpath(git_root) != os.path.realpath(cwd):
            get_logger().info(f"📂 Resolved project root: {git_root} (from {cwd})")
        return git_root

    # Priority 3: Fallback to cwd (not in git repo)
    if verbose:
        get_logger().warning(f"⚠️ Not in git repo, using cwd: {cwd}")
    return cwd


if __name__ == "__main__":
    # Quick test
    print(f"Is git repo: {is_git_repo()}")
    print(f"Current branch: {get_current_branch()}")
    print(f"Git root: {get_git_root()}")
    print(f"All branches: {get_all_branches()}")
