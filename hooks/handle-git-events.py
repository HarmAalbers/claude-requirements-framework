#!/usr/bin/env python3
"""
PostToolUse hook for Bash - tracks git events for WIP tracking.

Monitors Bash tool completions for git commit, git push, and gh pr create
commands. Updates WipTracker git metrics accordingly.

Input (stdin):
    JSON with tool completion details:
    {
        "tool_name": "Bash",
        "tool_input": {"command": "git commit -m 'feat: add auth'"},
        "tool_result": {"stdout": "...", "stderr": "..."},
        "session_id": "abc12345"
    }

Output:
    None (logging only)

Environment:
    CLAUDE_PROJECT_DIR: Project directory (defaults to cwd)
"""
import json
import re
import sys
from pathlib import Path

# Add lib to path
lib_path = Path(__file__).parent / 'lib'
sys.path.insert(0, str(lib_path))

from git_utils import get_current_branch, is_git_repo, resolve_project_root, run_git
from hook_utils import extract_command
from logger import get_logger


def _is_wip_enabled(project_dir: str) -> bool:
    """Check if WIP tracking is enabled for this project."""
    try:
        from config import RequirementsConfig
        config = RequirementsConfig(project_dir)
        return config.get_hook_config('wip_tracking', 'enabled', False)
    except Exception:
        return False


def _get_exclude_branches(project_dir: str) -> list[str]:
    """Get list of branches to exclude from WIP tracking."""
    try:
        from config import RequirementsConfig
        config = RequirementsConfig(project_dir)
        return config.get_hook_config(
            'wip_tracking', 'exclude_branches',
            ['main', 'master', 'develop']
        )
    except Exception:
        return ['main', 'master', 'develop']


def _handle_git_commit(tracker, project_dir: str, branch: str, logger) -> None:
    """Handle git commit: update commit count, hash, and diff stats."""
    # Get latest commit hash
    exit_code, commit_hash, _ = run_git("git rev-parse HEAD", cwd=project_dir)
    if exit_code != 0:
        return

    # Get diff stats for the latest commit
    exit_code, stat_output, _ = run_git(
        "git diff --stat HEAD~1 HEAD", cwd=project_dir
    )
    files_changed = 0
    lines_added = 0
    lines_removed = 0
    if exit_code == 0 and stat_output:
        # Parse summary line: " 3 files changed, 10 insertions(+), 2 deletions(-)"
        for line in stat_output.splitlines():
            m = re.search(
                r'(\d+) files? changed'
                r'(?:, (\d+) insertions?\(\+\))?'
                r'(?:, (\d+) deletions?\(-\))?',
                line
            )
            if m:
                files_changed = int(m.group(1))
                lines_added = int(m.group(2) or 0)
                lines_removed = int(m.group(3) or 0)
                break

    # Get current commit count
    entry = tracker.get_entry(project_dir, branch)
    current_count = 0
    if entry:
        current_count = entry.get("git_metrics", {}).get("commit_count", 0)

    tracker.update_git_metrics(
        project_dir, branch,
        commit_count=current_count + 1,
        last_commit_hash=commit_hash,
        files_changed=files_changed,
        lines_added=lines_added,
        lines_removed=lines_removed,
    )
    logger.info("Tracked git commit", commit_hash=commit_hash[:8])


def _handle_git_push(tracker, project_dir: str, branch: str, logger) -> None:
    """Handle git push: mark branch as pushed."""
    tracker.update_git_metrics(project_dir, branch, pushed=True)
    logger.info("Tracked git push")


def _handle_pr_create(tracker, project_dir: str, branch: str,
                      tool_result: dict, logger) -> None:
    """Handle gh pr create: extract PR URL from output."""
    stdout = tool_result.get("stdout", "")
    # gh pr create outputs the PR URL on the last line
    pr_url = None
    for line in stdout.splitlines():
        line = line.strip()
        if re.match(r'https://github\.com/.+/pull/\d+', line):
            pr_url = line
            break

    if pr_url:
        tracker.update_git_metrics(project_dir, branch, pr_url=pr_url)
        logger.info("Tracked PR creation", pr_url=pr_url)


def main() -> int:
    """Hook entry point."""
    try:
        # Read hook input
        input_data = {}
        try:
            stdin_content = sys.stdin.read()
            if stdin_content:
                input_data = json.loads(stdin_content)
        except json.JSONDecodeError:
            return 0

        tool_name = input_data.get('tool_name', '')

        # Only process Bash tool completions
        if tool_name != 'Bash':
            return 0

        tool_input = input_data.get('tool_input', {})
        command = extract_command(tool_input)
        if not command:
            return 0

        # Get project context
        project_dir = resolve_project_root(verbose=False)

        # Check if WIP tracking is enabled
        if not _is_wip_enabled(project_dir):
            return 0

        # Must be a git repo
        if not is_git_repo(project_dir):
            return 0

        branch = get_current_branch(project_dir)
        if not branch:
            return 0

        # Skip excluded branches
        exclude = _get_exclude_branches(project_dir)
        if branch in exclude:
            return 0

        logger = get_logger(base_context={"hook": "GitEvents"})

        # Lazy import to avoid loading WipTracker when not needed
        from wip_tracker import WipTracker
        tracker = WipTracker()

        # Match command patterns
        if re.match(r'git\s+commit\b', command):
            _handle_git_commit(tracker, project_dir, branch, logger)
        elif re.match(r'git\s+push\b', command):
            _handle_git_push(tracker, project_dir, branch, logger)
        elif re.match(r'gh\s+pr\s+create\b', command):
            tool_result = input_data.get('tool_result', {})
            _handle_pr_create(tracker, project_dir, branch, tool_result, logger)

    except Exception:
        # Fail silently - never block on tracking errors
        pass

    return 0


if __name__ == '__main__':
    sys.exit(main())
