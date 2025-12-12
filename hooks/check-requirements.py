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
    - Skip main/master branches
    - Skip if no project config exists
"""
import json
import os
import sys
from pathlib import Path

# Add lib to path
lib_path = Path(__file__).parent / 'lib'
sys.path.insert(0, str(lib_path))

from requirements import BranchRequirements
from config import RequirementsConfig
from git_utils import get_current_branch, is_git_repo
from session import get_session_id, update_registry, get_active_sessions
from requirement_strategies import STRATEGIES
from logger import get_logger


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


def output_prompt(req_name: str, config: dict, session_id: str, project_dir: str, branch: str) -> None:
    """
    Output 'deny' decision to block until requirement is satisfied.

    We use 'deny' instead of 'ask' because 'ask' gets overridden by
    permissions.allow entries in settings.local.json.

    Args:
        req_name: Requirement name
        config: Requirement configuration
        session_id: Current session ID
        project_dir: Project directory
        branch: Current branch
    """
    message = config.get('message', f'Requirement "{req_name}" not satisfied.')

    # Add checklist if present
    checklist = config.get('checklist', [])
    if checklist:
        message += "\n\n**Checklist**:"
        for i, item in enumerate(checklist, 1):
            message += f"\n⬜ {i}. {item}"

    # Add session context
    message += f"\n\n**Current session**: `{session_id}`"

    active_sessions = get_active_sessions(project_dir=project_dir, branch=branch)
    if len(active_sessions) > 1:
        message += "\n\n**Other active sessions**:"
        for sess in active_sessions:
            if sess['id'] != session_id:
                message += f"\n  • `{sess['id']}` [PID {sess['pid']}]"

    # Add helper hint with session context
    message += f"\n\n💡 **To satisfy from terminal**:"
    message += f"\n```bash"
    message += f"\nreq satisfy {req_name} --session {session_id}"
    message += f"\n```"
    message += f"\n\n💡 **Tip**: If you have multiple unsatisfied requirements, you can satisfy them all at once:"
    message += f"\n```bash"
    message += f"\nreq satisfy commit_plan --session {session_id} && req satisfy adr_reviewed --session {session_id}"
    message += f"\n```"

    response = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": message
        }
    }
    print(json.dumps(response))


def main() -> int:
    """
    Hook entry point.

    Returns:
        Exit code (always 0 - fail open)
    """
    session_id = get_session_id()
    logger = get_logger(base_context={"session": session_id})

    try:
        # Check skip flag
        if os.environ.get('CLAUDE_SKIP_REQUIREMENTS'):
            logger.info("Skipping requirements (env override)", reason='CLAUDE_SKIP_REQUIREMENTS')
            return 0

        # Read hook input from stdin
        input_data = {}
        try:
            stdin_content = sys.stdin.read()
            if stdin_content:
                input_data = json.loads(stdin_content)
        except json.JSONDecodeError:
            pass

        tool_name = input_data.get('tool_name', '')

        logger = logger.bind(tool=tool_name)

        # Only check on write operations
        if tool_name not in ['Edit', 'Write', 'MultiEdit']:
            return 0

        # Skip plan files - plan mode needs to write plans before requirements can be satisfied
        tool_input = input_data.get('tool_input', {})
        if tool_input:
            file_path = tool_input.get('file_path', '')
            if file_path and should_skip_plan_file(file_path):
                logger.info("Skipping plan file", file_path=file_path)
                return 0

        # Get project directory
        project_dir = os.environ.get('CLAUDE_PROJECT_DIR', os.getcwd())
        logger = logger.bind(project_dir=project_dir)

        # Check if project has requirements config
        config_file = Path(project_dir) / '.claude' / 'requirements.yaml'
        config_file_json = Path(project_dir) / '.claude' / 'requirements.json'

        if not config_file.exists() and not config_file_json.exists():
            # No config = no requirements for this project
            logger.info("Skipping requirements (no config)", project_dir=project_dir)
            return 0

        # Skip if not git repo
        if not is_git_repo(project_dir):
            logger.info("Skipping requirements (not a git repo)", project_dir=project_dir)
            return 0

        # Get current branch
        branch = get_current_branch(project_dir)
        logger = logger.bind(branch=branch)
        if not branch:
            logger.info("Skipping requirements (detached HEAD)")
            return 0  # Detached HEAD

        # Skip main/master
        if branch in ['main', 'master']:
            logger.info("Skipping requirements (protected branch)")
            return 0

        # Load configuration
        config = RequirementsConfig(project_dir)

        # Reconfigure logger with project settings
        logger = get_logger(
            config.get_logging_config(),
            base_context={
                "session": session_id,
                "tool": tool_name,
                "branch": branch,
                "project_dir": project_dir,
            },
        )
        logger.info("Loaded requirements configuration")

        # Check if enabled for this project
        if not config.is_enabled():
            logger.info("Requirements disabled via config")
            return 0

        # Update session registry FIRST (before checking requirements)
        # This allows CLI to find the session for bootstrapping new sessions
        # fail-open: errors don't block
        try:
            update_registry(session_id, project_dir, branch)
        except Exception as e:
            logger.error("Registry update failed", error=str(e))

        # Initialize requirements manager
        reqs = BranchRequirements(branch, session_id, project_dir)

        # Check all enabled requirements using strategy pattern
        for req_name in config.get_all_requirements():
            if not config.is_requirement_enabled(req_name):
                continue

            # Check if this tool triggers this requirement
            trigger_tools = config.get_trigger_tools(req_name)
            if tool_name not in trigger_tools:
                continue

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

            try:
                response = strategy.check(req_name, config, reqs, context)
                if response:
                    # Strategy returned a block/deny response
                    logger.info(
                        "Requirement blocked",
                        requirement=req_name,
                        req_type=req_type,
                    )
                    print(json.dumps(response))
                    return 0
            except Exception as e:
                # Fail open on strategy errors
                logger.error(
                    "Strategy error",
                    requirement=req_name,
                    req_type=req_type,
                    error=str(e),
                )
                continue  # Try next requirement

        # All requirements satisfied or passed
        return 0

    except Exception as e:
        # FAIL OPEN with visible warning
        error_msg = f"Requirements check error: {e}"
        print(f"⚠️ {error_msg}", file=sys.stderr)
        logger.error("Unhandled requirements error", error=str(e))
        return 0


if __name__ == '__main__':
    sys.exit(main())
