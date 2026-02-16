#!/usr/bin/env python3
"""
TaskCompleted Hook - quality gate for team review tasks.

When a team task is marked complete, this hook:
1. Records completion in session metrics for the learning system
2. Optionally validates that the task output is non-empty (configurable)

Input (stdin JSON):
{
    "hook_type": "TaskCompleted",
    "task_id": "1",
    "task_subject": "Code quality review",
    "team_name": "deep-review-abc123",
    "session_id": "abc12345"
}

Exit codes:
    0 = allow completion (default)
    2 = reject with feedback (empty/malformed output)

Configuration (in requirements.yaml):
    hooks:
      agent_teams:
        enabled: true
        validate_task_completion: false
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


def append_progress_log(project_dir: str, event: str, detail: str) -> None:
    """Append a line to team_progress.log (fail-open)."""
    try:
        from datetime import datetime
        from state_storage import get_state_dir
        log_dir = get_state_dir(project_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / 'team_progress.log'
        timestamp = datetime.now().strftime('%H:%M:%S')
        with open(log_path, 'a') as f:
            f.write(f"[{timestamp}] {event}  {detail}\n")
    except Exception:
        pass  # Fail-open


def main() -> int:
    """Hook entry point."""
    logger = get_logger(base_context={"hook": "TaskCompleted"})

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
        task_id = input_data.get('task_id', '')
        task_subject = input_data.get('task_subject', '')
        team_name = input_data.get('team_name', '')
        session_id = input_data.get('session_id', '')

        if not session_id:
            return 0  # Fail open on missing session

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
        if not agent_teams_config.get('enabled', True):
            return 0  # Agent teams explicitly disabled

        # Log the completion event
        logger.info(
            "Team task completed",
            task_id=task_id,
            task_subject=task_subject,
            team=team_name,
            session=session_id,
        )

        # Append to human-readable progress log
        task_label = f"#{task_id}" if task_id else "task"
        max_subject_len = 43
        subject_preview = (task_subject[:max_subject_len - 3] + "...") if len(task_subject) > max_subject_len else task_subject
        append_progress_log(project_dir, "DONE ", f"{task_label} completed: {subject_preview}  [{team_name}]")

        # Record in session metrics
        try:
            from session_metrics import SessionMetrics
            from git_utils import get_current_branch
            branch = get_current_branch(project_dir)
            if branch:
                metrics = SessionMetrics(session_id, project_dir, branch)
                metrics.record_agent_use(f"team:{team_name}:task_completed:{task_id}")
                metrics.save()
        except Exception as e:
            logger.error("Failed to record metrics", error=str(e))

        # Validate task output if enabled
        if agent_teams_config.get('validate_task_completion', False):
            if not task_subject or not task_subject.strip():
                feedback = (
                    f"Task {task_id} has an empty subject. "
                    f"Please provide a meaningful description of what was completed."
                )
                print(feedback)
                return 2  # Reject - output is empty/malformed

        return 0  # Allow completion

    except Exception as e:
        # FAIL OPEN - never block on errors
        logger.error("Unhandled error in TaskCompleted hook", error=str(e))
        return 0


if __name__ == '__main__':
    sys.exit(main())
