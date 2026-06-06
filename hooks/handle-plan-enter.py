#!/usr/bin/env python3
"""
PostToolUse Hook for EnterPlanMode - auto-invoke brainstorming skill.

Fires when Claude enters plan mode, injecting a directive to invoke the
brainstorming skill before writing the implementation plan. This ensures
structured design exploration (questions, approaches, trade-offs) happens
before planning begins.

Input (stdin JSON):
{
    "tool_name": "EnterPlanMode",
    "tool_input": {...},
    "tool_result": {...},
    "session_id": "abc123",
    "cwd": "/path/to/project"
}

Output:
- Structured JSON with hookSpecificOutput.additionalContext (shown to Claude in context)
- Empty if brainstorming not needed
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
from console import emit_hook_context
from brainstorm import (
    brainstorm_directive,
    resolve_brainstorm_phase,
    nudge_already_shown,
    mark_nudge_shown,
)


def main() -> int:
    """Hook entry point."""
    # Parse stdin input
    input_data = {}
    stdin_content = ""
    try:
        stdin_content = sys.stdin.read()
        if stdin_content:
            input_data = json.loads(stdin_content)
    except json.JSONDecodeError as e:
        logger = get_logger(base_context={"hook": "PlanEnter"})
        logger.error(
            "Failed to parse hook input JSON",
            error=str(e),
            stdin_preview=stdin_content[:200] if stdin_content else "empty"
        )

    # Only run this hook for EnterPlanMode tool
    tool_name = input_data.get('tool_name')
    if tool_name != 'EnterPlanMode':
        return 0  # Silent skip for other tools

    # Get session ID from stdin
    raw_session = input_data.get('session_id')
    if not raw_session:
        logger = get_logger(base_context={"hook": "PlanEnter"})
        logger.error("No session_id in hook input!", input_keys=list(input_data.keys()))
        return 0  # Fail open

    session_id = normalize_session_id(raw_session)

    # Early hook setup: loads config, creates logger with correct level
    project_dir, branch, config, logger = early_hook_setup(
        session_id, "PlanEnter", cwd=input_data.get('cwd')
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

        # Check config: brainstorm_on_enter (default: True)
        if not config.get_hook_config('plan_enter', 'brainstorm_on_enter', True):
            logger.info("Brainstorm on enter disabled by config")
            return 0

        # Resolve the brainstorm phase (gate + skill) from the configured
        # workflow. Fail-open to design_approved / brainstorming.
        gate, skill = resolve_brainstorm_phase(config)

        # Check if the brainstorm gate exists AND is already satisfied.
        req_config = config.get_requirement(gate)
        if req_config and config.is_requirement_enabled(gate):
            reqs = BranchRequirements(branch, session_id, project_dir)
            scope = req_config.get('scope', 'session')
            if reqs.is_satisfied(gate, scope):
                logger.info(
                    "Brainstorm gate already satisfied, skipping directive",
                    gate=gate,
                )
                return 0

        # Once-per-session dedup shared with the UserPromptSubmit nudge so the
        # user never sees two brainstorm directives in one session.
        if nudge_already_shown(session_id, project_dir):
            logger.info("Brainstorm nudge already shown this session, skipping")
            return 0

        # Emit brainstorm directive
        emit_hook_context("PostToolUse", brainstorm_directive(skill))
        mark_nudge_shown(session_id, project_dir)
        logger.info(
            "Plan enter - injected brainstorm directive", gate=gate, skill=skill
        )
        return 0

    except Exception as e:
        # FAIL OPEN - never block on errors
        logger.error("Unhandled error in PlanEnter hook", error=str(e))
        return 0


if __name__ == '__main__':
    sys.exit(main())
