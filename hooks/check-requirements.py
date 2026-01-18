#!/usr/bin/env python3
"""
Requirements Framework - PreToolUse Hook

This hook checks requirements before Edit/Write/MultiEdit operations.
It's called by Claude Code before any file modification tool.

Input (stdin):
    JSON with tool invocation details:
    {
        "tool_name": "Edit",
        "tool_input": {...}
    }

Output (stdout):
    If requirements not satisfied:
    {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": "Message to user"
        }
    }

    If satisfied (or no config): Empty output, exit 0

Environment:
    CLAUDE_PROJECT_DIR: Project directory (defaults to cwd)
    CLAUDE_SKIP_REQUIREMENTS: Set to skip all checks

Design:
    - FAIL OPEN on any error (log but don't block)
    - Skip if no project config exists
    - Register session in registry when project context exists (for CLI discovery)
"""
import os
import sys
from pathlib import Path

# Add lib to path
lib_path = Path(__file__).parent / 'lib'
sys.path.insert(0, str(lib_path))

from requirements import BranchRequirements
from config import matches_trigger
from session import update_registry, normalize_session_id
from strategy_registry import STRATEGIES
from logger import get_logger
from hook_utils import early_hook_setup, parse_hook_input, extract_file_path
from console import emit_json
from progress import show_progress, clear_progress


def should_skip_plan_file(file_path: str) -> bool:
    """
    Check if a file path is a plan file that should skip requirements checks.

    Plan files need to be written before requirements can be satisfied,
    so we skip checks for them to avoid chicken-and-egg problems.

    Args:
        file_path: Path to check

    Returns:
        True if this is a plan file that should be skipped
    """
    try:
        # Normalize path (expand ~, resolve symlinks, make absolute)
        normalized = Path(file_path).expanduser().resolve()

        # Skip files in global plans directory (~/.claude/plans/)
        global_plans = Path.home() / '.claude' / 'plans'
        try:
            if normalized.is_relative_to(global_plans):
                return True
        except (ValueError, AttributeError):
            # Python < 3.9 doesn't have is_relative_to, use string matching
            pass

        # Skip files in project .claude/plans/ directories
        # Check if path contains .claude/plans/
        path_str = str(normalized)
        if '/.claude/plans/' in path_str or '\\.claude\\plans\\' in path_str:
            return True

        return False

    except Exception:
        # If anything fails, don't skip (fail safe)
        return False


def create_batched_denial(unsatisfied: list, session_id: str, project_dir: str, branch: str) -> dict:
    """
    Create batched denial message for all unsatisfied requirements.

    Uses directive-first format optimized for autonomous resolution.

    Args:
        unsatisfied: List of tuples (req_name, req_config)
        session_id: Current session ID
        project_dir: Project directory
        branch: Current branch

    Returns:
        Hook response dict with batched denial message
    """
    req_names = [r[0] for r in unsatisfied]

    # Group requirements by their auto_resolve_skill
    skill_groups: dict[str, list[str]] = {}
    no_skill_reqs: list[tuple[str, dict]] = []

    for req_name, req_config in unsatisfied:
        auto_skill = req_config.get('auto_resolve_skill', '')
        if auto_skill:
            if auto_skill not in skill_groups:
                skill_groups[auto_skill] = []
            skill_groups[auto_skill].append(req_name)
        else:
            no_skill_reqs.append((req_name, req_config))

    lines = []

    if len(unsatisfied) == 1:
        # Single requirement - use direct format
        req_name, req_config = unsatisfied[0]
        auto_skill = req_config.get('auto_resolve_skill', '')
        message = req_config.get('message', '')

        if message:
            # Use the configured message (which should be directive-first)
            lines.append(message.strip())
        else:
            # Fallback format
            lines.append(f"## Blocked: {req_name}")
            lines.append("")
            if auto_skill:
                lines.append(f"**Execute**: `/{auto_skill}`")
            else:
                lines.append(f"**Action**: `req satisfy {req_name} --session {session_id}`")
    else:
        # Multiple requirements - use tabular format
        lines.append("## Blocked: Multiple Requirements")
        lines.append("")

        # If all requirements can be resolved by the same skill, highlight that
        if len(skill_groups) == 1 and not no_skill_reqs:
            skill = list(skill_groups.keys())[0]
            reqs = skill_groups[skill]
            lines.append(f"**Execute**: `/{skill}`")
            lines.append("")
            lines.append(f"Satisfies: {', '.join(reqs)}")
        else:
            # Show table of requirements and their resolutions
            lines.append("| Requirement | Execute |")
            lines.append("|-------------|---------|")

            for skill, reqs in skill_groups.items():
                for req_name in reqs:
                    lines.append(f"| {req_name} | `/{skill}` |")

            for req_name, req_config in no_skill_reqs:
                lines.append(f"| {req_name} | `req satisfy {req_name}` |")

    # Add fallback command
    lines.append("")
    lines.append("---")
    req_list = ' '.join(req_names)
    lines.append(f"Fallback: `req satisfy {req_list} --session {session_id}`")

    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": "\n".join(lines)
        }
    }


def output_prompt(req_name: str, config: dict, session_id: str, project_dir: str, branch: str) -> None:
    """
    Output 'deny' decision to block until requirement is satisfied.

    DEPRECATED: Use create_batched_denial() for batched blocking.
    Kept for backwards compatibility.

    We use 'deny' instead of 'ask' because 'ask' gets overridden by
    permissions.allow entries in settings.local.json.

    Args:
        req_name: Requirement name
        config: Requirement configuration
        session_id: Current session ID
        project_dir: Project directory
        branch: Current branch
    """
    # Use the new batched function with a single requirement
    response = create_batched_denial([(req_name, config)], session_id, project_dir, branch)
    emit_json(response)


def main() -> int:
    """
    Hook entry point.

    Returns:
        Exit code (always 0 - fail open)
    """
    # Read and parse hook input from stdin (centralized parsing)
    stdin_content = sys.stdin.read()
    input_data, parse_error = parse_hook_input(stdin_content)

    # Log any parsing or validation issues (consolidated logger)
    if parse_error or '_tool_name_type_error' in input_data or '_tool_input_type_error' in input_data:
        early_logger = get_logger(base_context={"hook": "PreToolUse"})
        if parse_error:
            early_logger.error(
                "Hook input parse error",
                error=parse_error,
                stdin_preview=stdin_content[:500] if stdin_content else "empty",
            )
        if '_tool_name_type_error' in input_data:
            early_logger.warning(
                "Invalid tool_name type in hook input",
                type_error=input_data['_tool_name_type_error'],
            )
        if '_tool_input_type_error' in input_data:
            early_logger.warning(
                "Invalid tool_input type in hook input",
                type_error=input_data['_tool_input_type_error'],
            )

    # Get session_id from stdin (Claude Code always provides this)
    raw_session = input_data.get('session_id')
    if not raw_session:
        # This should NEVER happen - Claude Code always provides session_id
        # If it does, fail open with visible warning
        early_logger = get_logger(base_context={"hook": "PreToolUse"})
        early_logger.error(
            "CRITICAL: No session_id in hook input - requirements checking disabled",
            input_keys=list(input_data.keys()),
            stdin_was_empty=input_data.get('_empty_stdin', False),
        )
        return 0  # Fail open - don't block work

    session_id = normalize_session_id(raw_session)

    # Early hook setup: loads config, creates logger with correct level
    project_dir, branch, config, logger = early_hook_setup(
        session_id, "PreToolUse", cwd=input_data.get('cwd')
    )

    try:
        # Check skip flag
        if os.environ.get('CLAUDE_SKIP_REQUIREMENTS'):
            logger.info("Skipping requirements (env override)", reason='CLAUDE_SKIP_REQUIREMENTS')
            return 0

        # tool_name is validated as str or None by parse_hook_input()
        # tool_input is validated as dict by parse_hook_input()
        tool_name = input_data.get('tool_name') or ''
        tool_input = input_data.get('tool_input', {})

        logger = logger.bind(tool=tool_name)

        # Quick skip for tools that never trigger requirements
        # (Read, Glob, Grep, etc. - read-only tools)
        POTENTIALLY_TRIGGERING_TOOLS = {
            'Edit', 'Write', 'MultiEdit', 'Bash',
            'EnterPlanMode', 'ExitPlanMode'  # Plan mode transitions
        }
        if tool_name not in POTENTIALLY_TRIGGERING_TOOLS:
            return 0

        # Skip plan files - plan mode needs to write plans before requirements can be satisfied
        file_path = extract_file_path(tool_input, logger)
        if file_path and should_skip_plan_file(file_path):
            logger.info("Skipping plan file", file_path=file_path)
            return 0

        # Skip if no project context or config
        if not project_dir or not branch or not config:
            logger.info("Skipping requirements (no project context)")
            return 0

        # Update session registry early (before other checks)
        # This allows CLI to discover sessions on any branch
        try:
            update_registry(session_id, project_dir, branch)
        except Exception as e:
            logger.error("Registry update failed (early)", error=str(e))

        logger.info("Loaded requirements configuration")

        # Check if enabled for this project
        if not config.is_enabled():
            logger.info("Requirements disabled via config")
            return 0

        # Initialize requirements manager
        reqs = BranchRequirements(branch, session_id, project_dir)

        # Collect all unsatisfied requirements (batch blocking)
        unsatisfied = []

        # Check all enabled requirements using strategy pattern
        for req_name in config.get_all_requirements():
            if not config.is_requirement_enabled(req_name):
                continue

            # Check if this tool triggers this requirement using full pattern matching
            triggers = config.get_triggers(req_name)
            if not matches_trigger(tool_name, tool_input, triggers):
                continue

            # Mark requirement as triggered for Stop hook verification
            # (do this before checking satisfaction - triggered != satisfied)
            scope = config.get_scope(req_name)
            reqs.mark_triggered(req_name, scope)

            # Get strategy for requirement type (blocking, dynamic, etc.)
            req_type = config.get_requirement_type(req_name)
            strategy = STRATEGIES.get(req_type)

            if not strategy:
                # Unknown type - log error and fail open
                logger.error(
                    "Unknown requirement type",
                    requirement=req_name,
                    req_type=req_type,
                )
                continue

            # Execute strategy to check requirement
            context = {
                'project_dir': project_dir,
                'branch': branch,
                'session_id': session_id,
                'tool_name': tool_name,
            }

            logger.debug(
                "Checking requirement",
                requirement=req_name,
                req_type=req_type,
            )

            # Show progress for dynamic requirements (can involve slow calculations)
            if req_type == 'dynamic':
                show_progress("Checking requirements", req_name)

            try:
                response = strategy.check(req_name, config, reqs, context)
                if response:
                    # Strategy returned a block/deny response - collect it
                    req_config = config.get_requirement(req_name)
                    # For guard requirements, capture the strategy's response message
                    # since it contains condition-specific details
                    if req_type == 'guard' and 'hookSpecificOutput' in response:
                        guard_message = response['hookSpecificOutput'].get('permissionDecisionReason', '')
                        if guard_message:
                            req_config = dict(req_config)  # Make copy to avoid mutation
                            req_config['message'] = guard_message
                    unsatisfied.append((req_name, req_config))
                    logger.debug(
                        "Requirement unsatisfied",
                        requirement=req_name,
                        req_type=req_type,
                    )
            except Exception as e:
                # Fail open on strategy errors
                logger.error(
                    "Strategy error",
                    requirement=req_name,
                    req_type=req_type,
                    error=str(e),
                )
                continue  # Try next requirement

        # Clear any progress indicator
        clear_progress()

        # If any requirements unsatisfied, create batched denial
        if unsatisfied:
            logger.info(
                "Requirements blocked (batched)",
                requirements=[r[0] for r in unsatisfied],
                count=len(unsatisfied),
            )
            response = create_batched_denial(unsatisfied, session_id, project_dir, branch)
            emit_json(response)
            return 0

        # All requirements satisfied or passed
        return 0

    except Exception as e:
        # FAIL OPEN with visible warning
        logger.error("Unhandled requirements error", error=str(e))
        return 0


if __name__ == '__main__':
    sys.exit(main())
