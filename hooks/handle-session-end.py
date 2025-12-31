#!/usr/bin/env python3
"""
SessionEnd Hook for Requirements Framework.

Triggered when a Claude Code session ends.
Responsibilities:
1. Remove session from registry
2. Optionally clear session-scoped requirement state (if configured)
3. Log session end for debugging

Input (stdin JSON):
{
    "session_id": "abc123",
    "hook_event_name": "SessionEnd",
    "reason": "clear|logout|prompt_input_exit|other",
    "cwd": "/path/to/project"
}

Output:
- None (cleanup only, cannot block session end)
"""
import json
import os
import sys
from pathlib import Path

# Add lib to path
lib_path = Path(__file__).parent / 'lib'
sys.path.insert(0, str(lib_path))

from config import RequirementsConfig
from git_utils import get_current_branch, is_git_repo, resolve_project_root
from requirements import BranchRequirements
from session import get_session_id, remove_session_from_registry, normalize_session_id
from logger import get_logger


def main() -> int:
    """Hook entry point."""
    # Parse stdin input
    input_data = {}
    try:
        stdin_content = sys.stdin.read()
        if stdin_content:
            input_data = json.loads(stdin_content)
    except json.JSONDecodeError:
        pass

    # Get session ID from stdin (Claude Code always provides this)
    raw_session = input_data.get('session_id')
    if not raw_session:
        # This should NEVER happen - Claude Code always provides session_id
        # If it does, fail open with a logged warning
        logger = get_logger(base_context={"hook": "SessionEnd"})
        logger.error("No session_id in hook input!", input_keys=list(input_data.keys()))
        return 0  # Fail open

    session_id = normalize_session_id(raw_session)
    reason = input_data.get('reason', 'unknown')

    # Initialize logger (basic until we have config)
    logger = get_logger(base_context={"session": session_id, "hook": "SessionEnd"})

    try:
        # Skip if requirements explicitly disabled
        if os.environ.get('CLAUDE_SKIP_REQUIREMENTS'):
            return 0

        # Resolve project directory
        project_dir = input_data.get('cwd') or resolve_project_root(verbose=False)
        if not project_dir:
            # Still try to remove from registry even without project context
            remove_session_from_registry(session_id)
            return 0

        # Get branch (may not exist if not in git repo)
        branch = None
        if is_git_repo(project_dir):
            branch = get_current_branch(project_dir)

        # Load config (if available)
        config = None
        try:
            config = RequirementsConfig(project_dir)
        except Exception:
            pass

        # Update logger with config if available
        if config:
            logger = get_logger(
                config.get_logging_config(),
                base_context={
                    "session": session_id,
                    "branch": branch or "unknown",
                    "project_dir": project_dir,
                    "hook": "SessionEnd"
                }
            )

        logger.info("Session ending", reason=reason)

        # 1. Remove session from registry
        removed = remove_session_from_registry(session_id)
        if removed:
            logger.debug("Session removed from registry")
        else:
            logger.debug("Session was not in registry")

        # 2. Optionally clear session-scoped state (default: False - preserve state)
        if config and branch and config.get_hook_config('session_end', 'clear_session_state', False):
            reqs = BranchRequirements(branch, session_id, project_dir)

            for req_name in config.get_all_requirements():
                req_config = config.get_requirement(req_name)
                if req_config and req_config.get('scope') == 'session':
                    try:
                        reqs.clear(req_name)
                        logger.debug("Cleared session requirement", requirement=req_name)
                    except Exception as e:
                        logger.error("Failed to clear requirement", requirement=req_name, error=str(e))

        return 0

    except Exception as e:
        # FAIL OPEN - never block on errors
        logger.error("Unhandled error in SessionEnd hook", error=str(e))
        return 0


if __name__ == '__main__':
    sys.exit(main())
