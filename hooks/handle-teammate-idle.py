#!/usr/bin/env python3
"""
TeammateIdle Hook - progress tracking for team reviews.

When a teammate goes idle during a team review, this hook:
1. Logs the event to session metrics (team activity tracking)
2. Optionally sends feedback to keep the teammate working (configurable)

Input (stdin JSON):
{
    "hook_type": "TeammateIdle",
    "teammate_name": "code-reviewer",
    "team_name": "deep-review-abc123",
    "session_id": "abc12345"
}

Exit codes:
    0 = allow idle (default)
    2 = send feedback to keep teammate working

Configuration (in requirements.yaml):
    hooks:
      agent_teams:
        enabled: true
        keep_working_on_idle: false
"""
import json
import sys
from pathlib import Path

# Add lib to path
lib_path = Path(__file__).parent / 'lib'
sys.path.insert(0, str(lib_path))

from logger import get_logger
from config import RequirementsConfig
from git_utils import resolve_project_root


def main() -> int:
    """Hook entry point."""
    logger = get_logger(base_context={"hook": "TeammateIdle"})

    try:
        # Parse stdin input
        stdin_content = sys.stdin.read()
        if not stdin_content:
            return 0  # Fail open on empty input

        try:
            input_data = json.loads(stdin_content)
        except json.JSONDecodeError as e:
            logger.error("Failed to parse hook input JSON", error=str(e))
            return 0  # Fail open

        if not isinstance(input_data, dict):
            return 0  # Fail open

        # Extract fields
        teammate_name = input_data.get('teammate_name', '')
        team_name = input_data.get('team_name', '')
        session_id = input_data.get('session_id', '')

        if not teammate_name or not session_id:
            return 0  # Fail open on missing required fields

        # Resolve project and load config
        hook_cwd = input_data.get('cwd')
        project_dir = resolve_project_root(start_dir=hook_cwd, verbose=False)
        if not project_dir:
            return 0  # No project context

        config_file = Path(project_dir) / '.claude' / 'requirements.yaml'
        if not config_file.exists():
            return 0  # No config

        config = RequirementsConfig(project_dir)

        # Check agent_teams config
        agent_teams_config = config.get_raw_config().get('hooks', {}).get('agent_teams', {})
        if not agent_teams_config.get('enabled', False):
            return 0  # Agent teams disabled

        # Log the idle event
        logger.info(
            "Teammate went idle",
            teammate=teammate_name,
            team=team_name,
            session=session_id,
        )

        # Record in session metrics if available
        try:
            from session_metrics import SessionMetrics
            from git_utils import get_current_branch
            branch = get_current_branch(project_dir)
            if branch:
                metrics = SessionMetrics(session_id, project_dir, branch)
                metrics.record_agent_use(f"team:{teammate_name}:idle")
                metrics.save()
        except Exception as e:
            logger.error("Failed to record metrics", error=str(e))

        # Check if we should re-engage idle teammates
        if agent_teams_config.get('keep_working_on_idle', False):
            feedback = (
                f"Teammate '{teammate_name}' is idle. "
                f"Please check if your assigned task is complete. "
                f"If not, continue working on it."
            )
            print(feedback)
            return 2  # Exit code 2 = send feedback

        return 0  # Allow idle

    except Exception as e:
        # FAIL OPEN - never block on errors
        logger.error("Unhandled error in TeammateIdle hook", error=str(e))
        return 0


if __name__ == '__main__':
    sys.exit(main())
