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
from session_metrics import SessionMetrics
from logger import get_logger
from hook_utils import early_hook_setup
from console import emit_json, emit_text


def _should_prompt_session_review(config, session_id: str, project_dir: str,
                                   branch: str, logger) -> bool:
    """
    Check if we should prompt for session review.

    Conditions:
    - Session learning is enabled in config
    - prompt_on_stop is enabled (default: True)
    - Session had meaningful activity (>5 tool uses)

    Args:
        config: RequirementsConfig instance
        session_id: Current session ID
        project_dir: Project directory
        branch: Current branch
        logger: Logger instance

    Returns:
        True if should prompt, False otherwise
    """
    try:
        # Check config for session_learning settings
        learning_config = config.get_hook_config('session_learning', 'enabled', False)
        if not learning_config:
            return False

        prompt_on_stop = config.get_hook_config('session_learning', 'prompt_on_stop', True)
        if not prompt_on_stop:
            return False

        # Check session metrics for meaningful activity
        metrics = SessionMetrics(session_id, project_dir, branch)
        summary = metrics.get_summary()

        tool_uses = summary.get('tool_uses', 0)
        min_tool_uses = config.get_hook_config('session_learning', 'min_tool_uses', 5)

        if tool_uses < min_tool_uses:
            logger.debug(
                "Session too short for review prompt",
                tool_uses=tool_uses,
                min_required=min_tool_uses
            )
            return False

        return True

    except Exception as e:
        logger.warning(f"Failed to check session review conditions: {e}")
        return False


def _emit_session_review_prompt(session_id: str, project_dir: str,
                                branch: str, logger) -> None:
    """
    Emit a prompt suggesting session review.

    Args:
        session_id: Current session ID
        project_dir: Project directory
        branch: Current branch
        logger: Logger instance
    """
    try:
        # Get session summary for the prompt
        metrics = SessionMetrics(session_id, project_dir, branch)
        summary = metrics.get_summary()

        tool_uses = summary.get('tool_uses', 0)
        blocked_count = summary.get('blocked_count', 0)
        skills_used = summary.get('skills_used', 0)

        # Build prompt message
        lines = [
            "",
            "---",
            "",
            "**Session Learning Available**",
            "",
            f"This session had {tool_uses} tool uses"
            + (f" ({blocked_count} blocked)" if blocked_count > 0 else "")
            + (f", {skills_used} skills" if skills_used > 0 else "") + ".",
            "",
            "Run `/session-reflect` to analyze patterns and improve future sessions.",
            "Run `/session-reflect quick` for a quick summary.",
            ""
        ]

        emit_text("\n".join(lines))
        logger.info("Emitted session review prompt", tool_uses=tool_uses)

    except Exception as e:
        logger.warning(f"Failed to emit session review prompt: {e}")


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
        logger = get_logger(base_context={"hook": "Stop"})
        logger.error(
            "Failed to parse hook input JSON",
            error=str(e),
            stdin_preview=stdin_content[:200] if stdin_content else "empty"
        )

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

            # Build resolution-guided message
            lines = ["## Cannot Complete: Unsatisfied Requirements", ""]

            # Group by auto_resolve_skill
            skill_groups: dict[str, list[str]] = {}
            no_skill_reqs: list[str] = []

            for req_name in unsatisfied:
                req_config = config.get_requirement(req_name)
                auto_skill = req_config.get('auto_resolve_skill', '') if req_config else ''
                if auto_skill:
                    if auto_skill not in skill_groups:
                        skill_groups[auto_skill] = []
                    skill_groups[auto_skill].append(req_name)
                else:
                    no_skill_reqs.append(req_name)

            # Show tabular resolution guide
            lines.append("| Requirement | Execute |")
            lines.append("|-------------|---------|")

            for skill, reqs in skill_groups.items():
                for req_name in reqs:
                    lines.append(f"| {req_name} | `/{skill}` |")

            for req_name in no_skill_reqs:
                lines.append(f"| {req_name} | `req satisfy {req_name}` |")

            lines.append("")
            lines.append("Run the resolution skills above to satisfy requirements.")
            lines.append("")
            lines.append("---")
            lines.append(f"Fallback: `req satisfy {' '.join(unsatisfied)} --session {session_id}`")

            response = {
                "decision": "block",
                "reason": "\n".join(lines)
            }
            emit_json(response)
        else:
            logger.debug("All requirements satisfied - allowing stop")

            # Check if we should prompt for session review
            if _should_prompt_session_review(config, session_id, project_dir, branch, logger):
                _emit_session_review_prompt(session_id, project_dir, branch, logger)

        return 0

    except Exception as e:
        # FAIL OPEN - never block on errors
        logger.error("Unhandled error in Stop hook", error=str(e))
        return 0


if __name__ == '__main__':
    sys.exit(main())
