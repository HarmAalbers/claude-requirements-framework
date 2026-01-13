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
from session import normalize_session_id
from logger import get_logger

# Default skill to requirement mapping (for backwards compatibility)
# Maps skill names to the requirement they satisfy
# Uses requirements-framework: namespace per ADR-006
DEFAULT_SKILL_MAPPINGS = {
    'requirements-framework:pre-commit': 'pre_commit_review',
    'requirements-framework:quality-check': 'pre_pr_review',
    'requirements-framework:codex-review': 'codex_reviewer',
}


def get_skill_requirement_mappings(config: RequirementsConfig) -> dict:
    """
    Build skill → requirement mapping from configuration.

    Scans all enabled requirements for 'satisfied_by_skill' field and builds
    a reverse mapping from skill name to requirement name.

    Args:
        config: Loaded RequirementsConfig instance

    Returns:
        Dict mapping skill names to requirement names
    """
    mappings = {}

    for req_name in config.get_all_requirements():
        if not config.is_requirement_enabled(req_name):
            continue

        skill_name = config.get_attribute(req_name, 'satisfied_by_skill')
        if skill_name and isinstance(skill_name, str):
            mappings[skill_name] = req_name

    return mappings


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
        logger = get_logger(base_context={"hook": "AutoSatisfySkills"})

        # Only process Skill tool completions
        if tool_name != 'Skill':
            return 0

        tool_input = input_data.get('tool_input', {})
        skill_name = tool_input.get('skill', '')

        if not skill_name:
            return 0

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

        # Build skill → requirement mappings from config + defaults
        # Config mappings take precedence over defaults
        skill_mappings = DEFAULT_SKILL_MAPPINGS.copy()
        skill_mappings.update(get_skill_requirement_mappings(config))

        # Check if this skill maps to a requirement
        if skill_name not in skill_mappings:
            return 0

        req_name = skill_mappings[skill_name]

        if not config.is_requirement_enabled(req_name):
            return 0  # Requirement not enabled

        scope = config.get_scope(req_name)

        # Satisfy the requirement
        reqs = BranchRequirements(branch, session_id, project_dir)
        reqs.satisfy(req_name, scope, method='skill', metadata={'skill': skill_name})

        # Output success message (visible to user)
        logger.info(
            "Auto-satisfied requirement from skill",
            requirement=req_name,
            skill=skill_name,
        )

    except Exception as e:
        # Fail silently - don't block on auto-satisfy errors
        import traceback
        _log_error(f"Error: {e}\nTraceback:\n{traceback.format_exc()}")

    return 0


def _log_error(message: str) -> None:
    """Log error for debugging via the central logger."""
    try:
        get_logger(base_context={"hook": "AutoSatisfySkills"}).error(message)
    except Exception:
        pass


if __name__ == '__main__':
    sys.exit(main())
