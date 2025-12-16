#!/usr/bin/env python3
"""
PostToolUse Hook for ExitPlanMode - shows requirements status proactively.

Fires immediately when Claude exits plan mode, BEFORE any Edit attempts.
This gives the user a chance to satisfy requirements upfront.

Input (stdin JSON):
{
    "tool_name": "ExitPlanMode",
    "tool_input": {...},
    "tool_result": {...},
    "session_id": "abc123",
    "cwd": "/path/to/project"
}

Output:
- Plain text status message (shown to Claude in context)
- Empty if all requirements satisfied
"""
import json
import os
import sys
from pathlib import Path

# Add lib to path
lib_path = Path(__file__).parent / 'lib'
sys.path.insert(0, str(lib_path))

from config import RequirementsConfig
from requirements import BranchRequirements
from git_utils import get_current_branch, is_git_repo, resolve_project_root
from session import get_session_id, update_registry
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

    # Get session ID from input or generate
    session_id = input_data.get('session_id') or get_session_id()

    # Initialize logger
    logger = get_logger(base_context={"session": session_id, "hook": "PlanExit"})

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

        # Update session registry
        try:
            update_registry(session_id, project_dir, branch)
        except Exception as e:
            logger.error("Failed to update registry", error=str(e))

        # Initialize requirements manager
        reqs = BranchRequirements(branch, session_id, project_dir)

        # Collect unsatisfied requirements
        unsatisfied = []
        for req_name in config.get_all_requirements():
            if not config.is_requirement_enabled(req_name):
                continue
            req_config = config.get_requirement(req_name)
            scope = req_config.get('scope', 'session')
            if not reqs.is_satisfied(req_name, scope):
                unsatisfied.append((req_name, req_config))

        if not unsatisfied:
            return 0  # All satisfied, nothing to show

        # Format proactive message
        req_names = [r[0] for r in unsatisfied]
        lines = [
            "📋 **Requirements Check** (Plan Mode Exited)",
            "",
            "Before proceeding with implementation, these requirements need to be satisfied:",
            ""
        ]

        for req_name, req_config in unsatisfied:
            scope = req_config.get('scope', 'session')
            message = req_config.get('message', '')
            lines.append(f"- **{req_name}** ({scope} scope)")
            if message:
                lines.append(f"  {message}")

        lines.append("")
        lines.append(f"**Session**: `{session_id}`")
        lines.append("")
        lines.append("💡 **Satisfy now** (run in terminal):")
        lines.append("```bash")
        lines.append(f"req satisfy {' '.join(req_names)} --session {session_id}")
        lines.append("```")

        # PostToolUse output goes to Claude's context
        print("\n".join(lines))

        logger.info("Plan exit - showed requirements", requirements=req_names)
        return 0

    except Exception as e:
        # FAIL OPEN - never block on errors
        logger.error("Unhandled error in PlanExit hook", error=str(e))
        return 0


if __name__ == '__main__':
    sys.exit(main())
