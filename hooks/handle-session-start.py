#!/usr/bin/env python3
"""
SessionStart Hook for Requirements Framework.

Triggered when a Claude Code session starts or resumes.
Responsibilities:
1. Clean up stale sessions from registry
2. Update registry with current session
3. Inject requirement status into context (if configured)

Input (stdin JSON):
{
    "session_id": "abc123",
    "hook_event_name": "SessionStart",
    "source": "startup|resume|clear|compact",
    "cwd": "/path/to/project"
}

Output:
- Plain text status (injected into Claude's context)
- Or empty if inject_context is disabled
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
from session import update_registry, cleanup_stale_sessions, normalize_session_id, get_active_sessions
from logger import get_logger
from hook_utils import early_hook_setup
from console import emit_text


def format_full_status(reqs: BranchRequirements, config: RequirementsConfig,
                       session_id: str, branch: str) -> str:
    """
    Format detailed requirement status with rules for autonomous operation.

    Args:
        reqs: BranchRequirements manager
        config: RequirementsConfig instance
        session_id: Current session ID
        branch: Current git branch

    Returns:
        Formatted status string for context injection
    """
    lines = []

    # Add custom header if configured (project-specific context)
    custom_header = config.get_hook_config('session_start', 'custom_header')
    if custom_header:
        lines.append(custom_header.strip())
        lines.append("")

    # Rules preamble for autonomous operation
    lines.append("## Requirements Framework: Active Rules")
    lines.append("")
    lines.append("**Mode**: Autonomous Resolution Enabled")
    lines.append("")
    lines.append("When a requirement blocks an operation, run the specified skill automatically.")
    lines.append("")

    # Build tabular requirement status
    lines.append("| Requirement | Status | Auto-Resolve |")
    lines.append("|-------------|--------|--------------|")

    has_requirements = False
    unsatisfied_reqs = []

    for req_name in config.get_all_requirements():
        if not config.is_requirement_enabled(req_name):
            continue

        has_requirements = True
        req_config = config.get_requirement(req_name)
        scope = req_config.get('scope', 'session')
        req_type = config.get_requirement_type(req_name)

        # Context-aware checking for guard requirements
        if req_type == 'guard':
            context = {
                'branch': branch,
                'session_id': session_id,
                'project_dir': reqs.project_dir,
            }
            satisfied = reqs.is_guard_satisfied(req_name, config, context)
        else:
            satisfied = reqs.is_satisfied(req_name, scope)

        status = "✅" if satisfied else "⬜"

        # Get auto-resolve skill or provide default action
        auto_resolve = req_config.get('auto_resolve_skill', '')
        if auto_resolve:
            resolve_action = f"`/{auto_resolve}`"
        elif req_type == 'guard':
            # Guards have condition-specific actions
            guard_config = config.get_guard_config(req_name)
            if guard_config and guard_config.get('guard_type') == 'protected_branch':
                resolve_action = "Create feature branch"
            elif guard_config and guard_config.get('guard_type') == 'single_session':
                resolve_action = "Close other session"
            else:
                resolve_action = f"`req approve {req_name}`"
        elif req_type == 'dynamic':
            resolve_action = f"`req approve {req_name}`"
        else:
            resolve_action = f"`req satisfy {req_name}`"

        lines.append(f"| {req_name} | {status} | {resolve_action} |")

        if not satisfied:
            unsatisfied_reqs.append(req_name)

    if not has_requirements:
        lines.append("| (none configured) | - | - |")

    lines.append("")
    lines.append(f"**Context**: `{branch}` @ `{reqs.project_dir}`")
    lines.append(f"**Session**: `{session_id}`")

    # Provide batch satisfy command if there are unsatisfied requirements
    if unsatisfied_reqs:
        lines.append("")
        lines.append(f"**Fallback**: `req satisfy {' '.join(unsatisfied_reqs)} --session {session_id}`")

    return "\n".join(lines)


def check_other_sessions_warning(config: RequirementsConfig, project_dir: str,
                                  session_id: str, logger) -> str | None:
    """
    Check if other sessions are active on this project and generate warning.

    Only generates a warning if a single_session guard is configured.
    This is informational only - does not block.

    Args:
        config: RequirementsConfig instance
        project_dir: Current project directory
        session_id: Current session ID
        logger: Logger instance

    Returns:
        Warning message string if other sessions exist, None otherwise
    """
    # Check if any single_session guard is configured
    has_single_session_guard = False
    for req_name in config.get_all_requirements():
        if not config.is_requirement_enabled(req_name):
            continue
        req_type = config.get_requirement_type(req_name)
        if req_type != 'guard':
            continue
        try:
            guard_config = config.get_guard_config(req_name)
            if guard_config and guard_config.get('guard_type') == 'single_session':
                has_single_session_guard = True
                break
        except (ValueError, KeyError):
            continue

    if not has_single_session_guard:
        return None

    # Check for other active sessions on this project
    try:
        active = get_active_sessions(project_dir=project_dir)
        other_sessions = [s for s in active if s.get('id') != session_id]

        if not other_sessions:
            return None

        # Generate warning message
        import time
        lines = ["⚠️  **Other Claude Code sessions detected on this project**", ""]

        for sess in other_sessions:
            sess_id = sess.get('id', 'unknown')
            branch = sess.get('branch', 'unknown')
            last_active = sess.get('last_active', 0)

            if last_active:
                elapsed = int(time.time()) - last_active
                if elapsed < 60:
                    time_str = f"{elapsed}s ago"
                elif elapsed < 3600:
                    time_str = f"{elapsed // 60}m ago"
                else:
                    time_str = f"{elapsed // 3600}h ago"
            else:
                time_str = "unknown"

            lines.append(f"  • `{sess_id}` on `{branch}` (active {time_str})")

        lines.append("")
        lines.append("**Note**: Edits may be blocked to prevent conflicts.")
        lines.append("Use `req approve single_session_per_project` to override if needed.")

        return "\n".join(lines)

    except Exception as e:
        logger.warning("Failed to check other sessions", error=str(e))
        return None


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
        logger = get_logger(base_context={"hook": "SessionStart"})
        logger.error(
            "Failed to parse hook input JSON",
            error=str(e),
            stdin_preview=stdin_content[:200] if stdin_content else "empty"
        )

    # Get session ID from stdin (Claude Code always provides this)
    raw_session = input_data.get('session_id')
    if not raw_session:
        # This should NEVER happen - Claude Code always provides session_id
        # If it does, fail open with a logged warning
        logger = get_logger(base_context={"hook": "SessionStart"})
        logger.error("No session_id in hook input!", input_keys=list(input_data.keys()))
        return 0  # Fail open

    session_id = normalize_session_id(raw_session)

    # Early hook setup: loads config, creates logger with correct level
    project_dir, branch, config, logger = early_hook_setup(
        session_id, "SessionStart", cwd=input_data.get('cwd')
    )

    try:
        # Skip if requirements explicitly disabled
        if os.environ.get('CLAUDE_SKIP_REQUIREMENTS'):
            return 0

        # Skip if no project context
        if not project_dir or not branch:
            return 0

        # Check if project has its own config
        project_config_yaml = Path(project_dir) / '.claude' / 'requirements.yaml'
        has_project_config = project_config_yaml.exists()

        # Suggest init if no project config (only on startup, not resume/compact)
        source = input_data.get('source', 'startup')
        if not has_project_config and source == 'startup':
            emit_text("""💡 **No requirements config found for this project**

To set up the requirements framework, run:
  `req init`

Or create `.claude/requirements.yaml` manually.
See `req init --help` for options.
""")
            return 0

        # Skip if config wasn't loaded (shouldn't happen given checks above)
        if not config:
            return 0

        # Skip if framework disabled
        if not config.is_enabled():
            return 0

        logger.info("Session starting", source=source)

        # 1. Clean stale sessions
        stale_count = cleanup_stale_sessions()
        if stale_count > 0:
            logger.info("Cleaned stale sessions", count=stale_count)

        # 2. Update registry with current session
        try:
            update_registry(session_id, project_dir, branch)
        except Exception as e:
            logger.error("Failed to update registry", error=str(e))

        # 2b. Check for other sessions and warn if single_session guard is enabled
        other_sessions_warning = check_other_sessions_warning(
            config, project_dir, session_id, logger
        )
        if other_sessions_warning:
            emit_text(other_sessions_warning)
            emit_text("")  # Add blank line before status

        # 3. Inject context if configured (default: True)
        if config.get_hook_config('session_start', 'inject_context', True):
            reqs = BranchRequirements(branch, session_id, project_dir)
            status = format_full_status(reqs, config, session_id, branch)
            emit_text(status)

        return 0

    except Exception as e:
        # FAIL OPEN - never block on errors
        logger.error("Unhandled error in SessionStart hook", error=str(e))
        return 0


if __name__ == '__main__':
    sys.exit(main())
