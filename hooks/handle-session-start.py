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
from git_utils import get_current_branch, is_git_repo, resolve_project_root
from requirements import BranchRequirements
from session import get_session_id, update_registry, cleanup_stale_sessions, normalize_session_id
from logger import get_logger


def format_full_status(reqs: BranchRequirements, config: RequirementsConfig,
                       session_id: str, branch: str) -> str:
    """
    Format detailed requirement status with instructions.

    Args:
        reqs: BranchRequirements manager
        config: RequirementsConfig instance
        session_id: Current session ID
        branch: Current git branch

    Returns:
        Formatted status string for context injection
    """
    lines = ["📋 **Requirements Framework Status**", ""]

    # List all enabled requirements with status
    has_requirements = False
    for req_name in config.get_all_requirements():
        if not config.is_requirement_enabled(req_name):
            continue

        has_requirements = True
        req_config = config.get_requirement(req_name)
        scope = req_config.get('scope', 'session')
        satisfied = reqs.is_satisfied(req_name, scope)
        status = "✅" if satisfied else "⬜"
        lines.append(f"  {status} **{req_name}** ({scope} scope)")

    if not has_requirements:
        lines.append("  No requirements configured")

    lines.append("")
    lines.append(f"**Branch**: `{branch}`")
    lines.append(f"**Session**: `{session_id}`")
    lines.append("")
    lines.append("💡 **Commands**:")
    lines.append("  • `req status` - View detailed status")
    lines.append("  • `req satisfy <name>` - Mark requirement satisfied")
    lines.append("  • `req clear <name>` - Clear a requirement")

    return "\n".join(lines)


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

    # Get session ID from input or generate (normalize to ensure consistent 8-char format)
    raw_session = input_data.get('session_id')
    session_id = normalize_session_id(raw_session) if raw_session else get_session_id()

    # Initialize logger (basic until we have config)
    logger = get_logger(base_context={"session": session_id, "hook": "SessionStart"})

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

        # Check if project has its own config
        project_config_yaml = Path(project_dir) / '.claude' / 'requirements.yaml'
        project_config_json = Path(project_dir) / '.claude' / 'requirements.json'
        has_project_config = project_config_yaml.exists() or project_config_json.exists()

        # Load config (may fall back to global)
        config = RequirementsConfig(project_dir)

        # Skip if framework disabled
        if not config.is_enabled():
            return 0

        # Suggest init if no project config (only on startup, not resume/compact)
        source = input_data.get('source', 'startup')
        if not has_project_config and source == 'startup':
            print("""💡 **No requirements config found for this project**

To set up the requirements framework, run:
  `req init`

Or create `.claude/requirements.yaml` manually.
See `req init --help` for options.
""")
            return 0

        # Update logger with config
        logger = get_logger(
            config.get_logging_config(),
            base_context={
                "session": session_id,
                "branch": branch,
                "project_dir": project_dir,
                "hook": "SessionStart"
            }
        )

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

        # 3. Inject context if configured (default: True)
        if config.get_hook_config('session_start', 'inject_context', True):
            reqs = BranchRequirements(branch, session_id, project_dir)
            status = format_full_status(reqs, config, session_id, branch)
            print(status)

        return 0

    except Exception as e:
        # FAIL OPEN - never block on errors
        logger.error("Unhandled error in SessionStart hook", error=str(e))
        return 0


if __name__ == '__main__':
    sys.exit(main())
