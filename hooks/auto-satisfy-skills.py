#!/usr/bin/env python3
"""
PostToolUse hook for Skill tool - auto-satisfies requirements when skills complete.

This hook runs after a Skill tool completes and checks if the skill
maps to a requirement that should be auto-satisfied. This enables
a seamless workflow where running /pre-pr-review:pre-commit automatically
satisfies the pre_commit_review requirement.

Input (stdin):
    JSON with tool completion details:
    {
        "tool_name": "Skill",
        "tool_input": {"skill": "pre-pr-review:pre-commit"},
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
from config import RequirementsConfig
from git_utils import get_current_branch, is_git_repo, resolve_project_root
from session import get_session_id

# Skill to requirement mapping
# Maps skill names to the requirement they satisfy
SKILL_REQUIREMENTS = {
    'pre-pr-review:pre-commit': 'pre_commit_review',
    'pre-pr-review:quality-check': 'pre_pr_review',
}


def main() -> int:
    """
    Hook entry point.

    Returns:
        Exit code (always 0 - don't block on auto-satisfy errors)
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

        # Only process Skill tool completions
        if tool_name != 'Skill':
            return 0

        tool_input = input_data.get('tool_input', {})
        skill_name = tool_input.get('skill', '')

        # Check if this skill maps to a requirement
        if skill_name not in SKILL_REQUIREMENTS:
            return 0

        req_name = SKILL_REQUIREMENTS[skill_name]

        # Get project context
        project_dir = resolve_project_root(verbose=False)

        # Check if project has requirements config
        config_file = Path(project_dir) / '.claude' / 'requirements.yaml'
        config_file_json = Path(project_dir) / '.claude' / 'requirements.json'

        if not config_file.exists() and not config_file_json.exists():
            return 0  # No requirements config

        # Must be a git repo
        if not is_git_repo(project_dir):
            return 0

        # Get current branch
        branch = get_current_branch(project_dir)
        if not branch:
            return 0  # Detached HEAD

        # Get session ID
        session_id = input_data.get('session_id') or get_session_id()

        # Load config to check if requirement is enabled and get scope
        config = RequirementsConfig(project_dir)

        if not config.is_requirement_enabled(req_name):
            return 0  # Requirement not enabled

        scope = config.get_scope(req_name)

        # Satisfy the requirement
        reqs = BranchRequirements(branch, session_id, project_dir)
        reqs.satisfy(req_name, scope, method='skill', metadata={'skill': skill_name})

        # Output success message (visible to user)
        print(f"✅ Auto-satisfied '{req_name}' from skill '{skill_name}'", file=sys.stderr)

    except Exception as e:
        # Fail silently - don't block on auto-satisfy errors
        import traceback
        _log_error(f"Error: {e}\nTraceback:\n{traceback.format_exc()}")

    return 0


def _log_error(message: str) -> None:
    """Log error to file for debugging."""
    try:
        import time
        error_log = Path.home() / '.claude' / 'auto-satisfy-errors.log'
        with open(error_log, 'a') as f:
            f.write(f"\n--- {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
            f.write(f"{message}\n")
    except Exception:
        pass  # Last resort: fail silently


if __name__ == '__main__':
    sys.exit(main())
