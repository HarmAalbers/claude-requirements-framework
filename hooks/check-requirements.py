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
    - Register session in registry on every invocation (for CLI discovery)
"""
import json
import os
import sys
from pathlib import Path

# Add lib to path
lib_path = Path(__file__).parent / 'lib'
sys.path.insert(0, str(lib_path))

from requirements import BranchRequirements
from config import RequirementsConfig, matches_trigger
from git_utils import get_current_branch, is_git_repo, resolve_project_root
from session import get_session_id, update_registry, get_active_sessions, normalize_session_id
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


def create_batched_denial(unsatisfied: list, session_id: str, project_dir: str, branch: str) -> dict:
    """
    Create batched denial message for all unsatisfied requirements.

    Args:
        unsatisfied: List of tuples (req_name, req_config)
        session_id: Current session ID
        project_dir: Project directory
        branch: Current branch

    Returns:
        Hook response dict with batched denial message
    """
    req_names = [r[0] for r in unsatisfied]

    lines = ["**Unsatisfied Requirements**", ""]
    lines.append("The following requirements must be satisfied before making changes:")
    lines.append("")

    for req_name, req_config in unsatisfied:
        scope = req_config.get('scope', 'session')
        message = req_config.get('message', f'"{req_name}" not satisfied.')
        lines.append(f"- **{req_name}** ({scope} scope)")
        lines.append(f"  {message}")

        # Add checklist if present
        checklist = req_config.get('checklist', [])
        if checklist:
            lines.append("  **Checklist**:")
            for i, item in enumerate(checklist, 1):
                lines.append(f"  ⬜ {i}. {item}")
        lines.append("")

    # Add session context
    lines.append(f"**Current session**: `{session_id}`")

    active_sessions = get_active_sessions(project_dir=project_dir, branch=branch)
    if len(active_sessions) > 1:
        lines.append("")
        lines.append("**Other active sessions**:")
        for sess in active_sessions:
            if sess['id'] != session_id:
                lines.append(f"  • `{sess['id']}` [PID {sess['pid']}]")

    lines.append("")

    # Single command to satisfy all
    req_list = ' '.join(req_names)
    lines.append("💡 **To satisfy all requirements at once**:")
    lines.append("```bash")
    lines.append(f"req satisfy {req_list} --session {session_id}")
    lines.append("```")

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
    print(json.dumps(response))


def main() -> int:
    """
    Hook entry point.

    Returns:
        Exit code (always 0 - fail open)
    """
    # Read hook input from stdin
    input_data = {}
    try:
        stdin_content = sys.stdin.read()
        if stdin_content:
            input_data = json.loads(stdin_content)
    except json.JSONDecodeError as e:
        # Log parsing errors to help debug hook issues
        debug_log = Path.home() / '.claude' / 'hook-debug.log'
        try:
            import time
            with open(debug_log, 'a') as f:
                f.write(f"\n--- {time.strftime('%Y-%m-%d %H:%M:%S')} JSON PARSE ERROR ---\n")
                f.write(f"error: {e}\n")
                f.write(f"stdin: {stdin_content[:500] if stdin_content else 'empty'}\n")
        except (OSError, IOError):
            # Debug logging failed (permission denied, disk full, etc.) - acceptable to skip
            pass

    # Get session_id from stdin (Claude Code always provides this)
    raw_session = input_data.get('session_id')
    if not raw_session:
        # This should NEVER happen - Claude Code always provides session_id
        # If it does, fail open with visible warning
        logger = get_logger()
        logger.error("CRITICAL: No session_id in hook input!", input_keys=list(input_data.keys()))
        print(
            "⚠️ Requirements framework error: Missing session ID from Claude Code.\n"
            "   Requirements checking is disabled for this operation.\n"
            "   This may be a bug - please report with ~/.claude/logs/requirements.log",
            file=sys.stderr
        )
        return 0  # Fail open - don't block work

    session_id = normalize_session_id(raw_session)
    logger = get_logger(base_context={"session": session_id})

    try:
        # Check skip flag
        if os.environ.get('CLAUDE_SKIP_REQUIREMENTS'):
            logger.info("Skipping requirements (env override)", reason='CLAUDE_SKIP_REQUIREMENTS')
            return 0

        tool_name = input_data.get('tool_name', '')
        tool_input = input_data.get('tool_input', {})

        logger = logger.bind(tool=tool_name)

        # Quick skip for tools that never trigger requirements
        # (Read, Glob, Grep, etc. - read-only tools)
        POTENTIALLY_TRIGGERING_TOOLS = {'Edit', 'Write', 'MultiEdit', 'Bash'}
        if tool_name not in POTENTIALLY_TRIGGERING_TOOLS:
            return 0

        # Skip plan files - plan mode needs to write plans before requirements can be satisfied
        file_path = tool_input.get('file_path', '')
        if file_path and should_skip_plan_file(file_path):
            logger.info("Skipping plan file", file_path=file_path)
            return 0

        # Get project directory (resolves to git root from subdirectories)
        project_dir = resolve_project_root(verbose=False)
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

        # Update session registry early (before other checks)
        # This allows CLI to discover sessions on any branch
        try:
            update_registry(session_id, project_dir, branch)
        except Exception as e:
            logger.error("Registry update failed (early)", error=str(e))

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

        # If any requirements unsatisfied, create batched denial
        if unsatisfied:
            logger.info(
                "Requirements blocked (batched)",
                requirements=[r[0] for r in unsatisfied],
                count=len(unsatisfied),
            )
            response = create_batched_denial(unsatisfied, session_id, project_dir, branch)
            print(json.dumps(response))
            return 0

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
