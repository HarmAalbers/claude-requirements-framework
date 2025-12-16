#!/usr/bin/env python3
"""
Stop Hook for Requirements Framework.

Triggered when Claude Code finishes responding and is about to stop.
Verifies all requirements were satisfied before allowing Claude to stop.

CRITICAL: Handles stop_hook_active flag to prevent infinite loops!

Input (stdin JSON):
{
    "session_id": "abc123",
    "hook_event_name": "Stop",
    "stop_hook_active": false,  // CRITICAL: true if already continued once
    "cwd": "/path/to/project"
}

Output (to block stop):
{
    "decision": "block",
    "reason": "Requirements not satisfied: commit_plan. Please satisfy before finishing."
}

Output (to allow stop):
- Empty (no output)
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
from session import get_session_id
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

    # CRITICAL: Prevent infinite loops
    # If stop_hook_active is True, Claude already continued once due to this hook
    # We MUST NOT block again or we'll loop forever
    if input_data.get('stop_hook_active', False):
        return 0

    # Get session ID from input or generate
    session_id = input_data.get('session_id') or get_session_id()

    # Initialize logger (basic until we have config)
    logger = get_logger(base_context={"session": session_id, "hook": "Stop"})

    try:
        # Skip if requirements explicitly disabled
        if os.environ.get('CLAUDE_SKIP_REQUIREMENTS'):
            return 0

        # Resolve project directory
        project_dir = input_data.get('cwd') or resolve_project_root(verbose=False)
        if not project_dir:
            return 0

        # Skip if not a git repo
        if not is_git_repo(project_dir):
            return 0

        # Get current branch
        branch = get_current_branch(project_dir)
        if not branch:
            return 0

        # Load config
        config = RequirementsConfig(project_dir)

        # Skip if framework disabled
        if not config.is_enabled():
            return 0

        # Update logger with config
        logger = get_logger(
            config.get_logging_config(),
            base_context={
                "session": session_id,
                "branch": branch,
                "project_dir": project_dir,
                "hook": "Stop"
            }
        )

        # Check if stop verification is enabled (default: True)
        if not config.get_hook_config('stop', 'verify_requirements', True):
            logger.debug("Stop verification disabled by config")
            return 0

        # Get which scopes to verify (default: session only)
        verify_scopes = config.get_hook_config('stop', 'verify_scopes', ['session'])

        # Check all enabled requirements
        reqs = BranchRequirements(branch, session_id, project_dir)
        unsatisfied = []

        for req_name in config.get_all_requirements():
            if not config.is_requirement_enabled(req_name):
                continue

            req_config = config.get_requirement(req_name)
            scope = req_config.get('scope', 'session')

            # Only check scopes that are configured for verification
            if scope not in verify_scopes:
                continue

            if not reqs.is_satisfied(req_name, scope):
                unsatisfied.append(req_name)

        if unsatisfied:
            logger.info("Blocking stop - requirements unsatisfied", requirements=unsatisfied)

            # Format helpful message
            req_list = ', '.join(unsatisfied)
            response = {
                "decision": "block",
                "reason": (
                    f"⚠️ **Requirements not satisfied**: {req_list}\n\n"
                    "Please satisfy these requirements before finishing, or use "
                    "`req satisfy <name>` to mark them complete."
                )
            }
            print(json.dumps(response))
        else:
            logger.debug("All requirements satisfied - allowing stop")

        return 0

    except Exception as e:
        # FAIL OPEN - never block on errors
        logger.error("Unhandled error in Stop hook", error=str(e))
        return 0


if __name__ == '__main__':
    sys.exit(main())
