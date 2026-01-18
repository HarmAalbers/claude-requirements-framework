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

from requirements import BranchRequirements
from session import update_registry, normalize_session_id
from logger import get_logger
from hook_utils import early_hook_setup
from console import emit_text


def main() -> int:
    """Hook entry point."""
    # Parse stdin input
    input_data = {}
    try:
        stdin_content = sys.stdin.read()
        if stdin_content:
            input_data = json.loads(stdin_content)
    except json.JSONDecodeError as e:
        # Log parse error but fail open
        logger = get_logger(base_context={"hook": "PlanExit"})
        logger.error(
            "Failed to parse hook input JSON",
            error=str(e),
            stdin_preview=stdin_content[:200] if stdin_content else "empty"
        )

    # Only run this hook for ExitPlanMode tool
    tool_name = input_data.get('tool_name')
    if tool_name != 'ExitPlanMode':
        return 0  # Silent skip for other tools

    # Get session ID from stdin (Claude Code always provides this)
    raw_session = input_data.get('session_id')
    if not raw_session:
        # This should NEVER happen - Claude Code always provides session_id
        # If it does, fail open with a logged warning
        logger = get_logger(base_context={"hook": "PlanExit"})
        logger.error("No session_id in hook input!", input_keys=list(input_data.keys()))
        return 0  # Fail open

    session_id = normalize_session_id(raw_session)

    # Early hook setup: loads config, creates logger with correct level
    project_dir, branch, config, logger = early_hook_setup(
        session_id, "PlanExit", cwd=input_data.get('cwd')
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
            req_type = config.get_requirement_type(req_name)

            # Context-aware checking for guard requirements
            if req_type == 'guard':
                context = {
                    'branch': branch,
                    'session_id': session_id,
                    'project_dir': project_dir,
                }
                if not reqs.is_guard_satisfied(req_name, config, context):
                    unsatisfied.append((req_name, req_config))
            else:
                if not reqs.is_satisfied(req_name, scope):
                    unsatisfied.append((req_name, req_config))

        if not unsatisfied:
            return 0  # All satisfied, nothing to show

        # Format directive message
        req_names = [r[0] for r in unsatisfied]

        # Check if all unsatisfied requirements can be resolved by plan-review
        all_plan_review = all(
            req_config.get('auto_resolve_skill', '') == 'requirements-framework:plan-review'
            for _, req_config in unsatisfied
        )

        lines = ["## Plan Validation Required", ""]

        if all_plan_review:
            # Simple directive when plan-review resolves all
            lines.append("**Execute**: `/requirements-framework:plan-review`")
            lines.append("")
            lines.append(f"Satisfies: {', '.join(req_names)}")
        else:
            # Show table for mixed requirements
            lines.append("| Requirement | Execute |")
            lines.append("|-------------|---------|")

            for req_name, req_config in unsatisfied:
                auto_skill = req_config.get('auto_resolve_skill', '')
                if auto_skill:
                    lines.append(f"| {req_name} | `/{auto_skill}` |")
                else:
                    lines.append(f"| {req_name} | `req satisfy {req_name}` |")

        lines.append("")
        lines.append("---")
        lines.append(f"Fallback: `req satisfy {' '.join(req_names)} --session {session_id}`")

        # PostToolUse output goes to Claude's context
        emit_text("\n".join(lines))

        logger.info("Plan exit - showed requirements", requirements=req_names)
        return 0

    except Exception as e:
        # FAIL OPEN - never block on errors
        logger.error("Unhandled error in PlanExit hook", error=str(e))
        return 0


if __name__ == '__main__':
    sys.exit(main())
