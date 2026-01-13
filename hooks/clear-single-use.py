#!/usr/bin/env python3
"""
PostToolUse hook for Bash - clears single_use requirements after successful completion.

When a Bash command that triggered a single_use requirement completes,
this hook clears that requirement so it must be satisfied again before
the next action.

Example workflow:
1. User runs /pre-pr-review:pre-commit → auto-satisfies pre_commit_review
2. User runs git commit → succeeds (requirement was satisfied)
3. This hook clears pre_commit_review (single_use scope)
4. Next git commit → blocked (must run review again)

Input (stdin):
    JSON with tool completion details:
    {
        "tool_name": "Bash",
        "tool_input": {"command": "git commit -m 'test'"},
        "session_id": "abc12345"
    }

Output:
    None (logging only)

Environment:
    CLAUDE_PROJECT_DIR: Project directory (defaults to cwd)
"""
import json
import sys
from pathlib import Path

# Add lib to path
lib_path = Path(__file__).parent / 'lib'
sys.path.insert(0, str(lib_path))

from requirements import BranchRequirements
from config import RequirementsConfig, matches_trigger
from git_utils import get_current_branch, is_git_repo, resolve_project_root
from session import normalize_session_id
from logger import get_logger


def main() -> int:
    """
    Hook entry point.

    Returns:
        Exit code (always 0 - don't block on clear errors)
    """
    try:
        # Read hook input
        input_data = {}
        try:
            stdin_content = sys.stdin.read()
            if stdin_content:
                input_data = json.loads(stdin_content)
        except json.JSONDecodeError as e:
            # Log the error for debugging
            _log_error(f"JSON decode error: {e}\nInput: {stdin_content[:200] if stdin_content else '(empty)'}")
            return 0

        tool_name = input_data.get('tool_name', '')
        logger = get_logger(base_context={"hook": "ClearSingleUse"})

        # Only process Bash tool completions
        if tool_name != 'Bash':
            return 0

        tool_input = input_data.get('tool_input', {})

        # Get project context
        project_dir = resolve_project_root(verbose=False)

        # Check if project has requirements config
        config_file = Path(project_dir) / '.claude' / 'requirements.yaml'

        if not config_file.exists():
            return 0  # No requirements config

        # Must be a git repo
        if not is_git_repo(project_dir):
            return 0

        # Get current branch
        branch = get_current_branch(project_dir)
        if not branch:
            return 0  # Detached HEAD

        # Get session ID from stdin (Claude Code always provides this)
        raw_session = input_data.get('session_id')
        if not raw_session:
            # This should NEVER happen - Claude Code always provides session_id
            logger.error("No session_id in hook input!", input_keys=list(input_data.keys()))
            return 0  # Fail open

        session_id = normalize_session_id(raw_session)

        # Load config
        config = RequirementsConfig(project_dir)

        # Initialize requirements manager
        reqs = BranchRequirements(branch, session_id, project_dir)

        # Check each requirement to see if this Bash command triggered it
        for req_name in config.get_all_requirements():
            if not config.is_requirement_enabled(req_name):
                continue

            # Only clear single_use scope requirements
            scope = config.get_scope(req_name)
            if scope != 'single_use':
                continue

            # Check if this command triggered the requirement
            triggers = config.get_triggers(req_name)
            if matches_trigger(tool_name, tool_input, triggers):
                # This command triggered the requirement - clear it
                if reqs.clear_single_use(req_name):
                    logger.info(
                        "Cleared single_use requirement",
                        requirement=req_name,
                    )

    except Exception as e:
        # Fail silently - don't block on clear errors
        import traceback
        _log_error(f"Error: {e}\nTraceback:\n{traceback.format_exc()}")

    return 0


def _log_error(message: str) -> None:
    """Log error for debugging via the central logger."""
    try:
        get_logger(base_context={"hook": "ClearSingleUse"}).error(message)
    except Exception:
        pass


if __name__ == '__main__':
    sys.exit(main())
