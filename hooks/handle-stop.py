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

from requirements import BranchRequirements
from session import normalize_session_id
from logger import get_logger
from hook_utils import early_hook_setup


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

    # Get session ID from stdin (Claude Code always provides this)
    raw_session = input_data.get('session_id')
    if not raw_session:
        # This should NEVER happen - Claude Code always provides session_id
        # If it does, fail open with visible warning
        logger = get_logger(base_context={"hook": "Stop"})
        logger.error("CRITICAL: No session_id in hook input!", input_keys=list(input_data.keys()))
        print(
            "⚠️ Requirements framework error: Missing session ID from Claude Code.\n"
            "   Stop hook verification disabled.\n"
            "   This may be a bug - please report with ~/.claude/logs/requirements.log",
            file=sys.stderr
        )
        return 0  # Fail open - allow stop to proceed

    session_id = normalize_session_id(raw_session)

    # Early hook setup: loads config, creates logger with correct level
    project_dir, branch, config, logger = early_hook_setup(
        session_id, "Stop", cwd=input_data.get('cwd')
    )

    try:
        # Skip if requirements explicitly disabled
        if os.environ.get('CLAUDE_SKIP_REQUIREMENTS'):
            return 0

        # Skip if no project context
        if not project_dir or not branch or not config:
            return 0

        # Skip if framework disabled
        if not config.is_enabled():
            return 0

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
            req_type = config.get_requirement_type(req_name)

            # Only check scopes that are configured for verification
            if scope not in verify_scopes:
                continue

            # Only check requirements that were triggered this session
            # (research-only sessions skip requirements they never triggered)
            if not reqs.is_triggered(req_name, scope):
                logger.debug("Skipping untriggered requirement", requirement=req_name, scope=scope)
                continue

            # Context-aware checking for guard requirements
            if req_type == 'guard':
                # For guard requirements, evaluate the actual condition
                # (e.g., "not on protected branch") rather than just checking
                # if it was manually satisfied
                context = {
                    'branch': branch,
                    'session_id': session_id,
                    'project_dir': project_dir,
                }
                if not reqs.is_guard_satisfied(req_name, config, context):
                    unsatisfied.append(req_name)
            else:
                # Regular satisfaction check for blocking/dynamic requirements
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
