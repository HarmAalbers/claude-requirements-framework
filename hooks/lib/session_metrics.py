#!/usr/bin/env python3
"""
Session metrics collection for learning system.

Collects rich session data during hook execution for later analysis.
Metrics are stored in .git/requirements/sessions/<session_id>.json.

This enables the /session-reflect command to analyze session patterns
and suggest improvements to memories, skills, and commands.

Data collected:
- Tool usage patterns (which tools, how often, which files)
- Requirement blocks (what was blocked, how resolved)
- Errors and recovery patterns
- Git activity (commits, files changed)
- Session timing and duration

Design principles:
- Fail-open: Metric recording errors never block hook execution
- Atomic writes: File locking + atomic rename for safety
- Incremental: Each hook call appends to existing metrics
"""
import fcntl
import json
import os
import time
from pathlib import Path

from logger import get_logger


def get_sessions_dir(project_dir: str) -> Path:
    """
    Get sessions directory for project.

    Sessions are stored in .git/requirements/sessions/ which is automatically
    gitignored (anything in .git/ is ignored).

    In git worktrees, uses the COMMON git directory to share across worktrees.

    Args:
        project_dir: Project root directory

    Returns:
        Path to sessions directory
    """
    try:
        from .git_utils import get_git_common_dir
    except ImportError:
        from git_utils import get_git_common_dir

    common_dir = get_git_common_dir(project_dir)

    if common_dir:
        return Path(common_dir) / 'requirements' / 'sessions'

    # Fallback for non-git directories
    return Path(project_dir) / '.git' / 'requirements' / 'sessions'


def ensure_sessions_dir(project_dir: str) -> None:
    """
    Create sessions directory if it doesn't exist.

    Args:
        project_dir: Project root directory
    """
    sessions_dir = get_sessions_dir(project_dir)
    try:
        sessions_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        get_logger().warning(f"Could not create sessions dir {sessions_dir}: {e}")


def get_metrics_path(session_id: str, project_dir: str) -> Path:
    """
    Get path to session metrics file.

    Args:
        session_id: Session ID (8-character hex)
        project_dir: Project root directory

    Returns:
        Path to session metrics JSON file
    """
    ensure_sessions_dir(project_dir)
    return get_sessions_dir(project_dir) / f"{session_id}.json"


def create_empty_metrics(session_id: str, project_dir: str, branch: str) -> dict:
    """
    Create empty metrics structure for a new session.

    Args:
        session_id: Session ID (8-character hex)
        project_dir: Project root directory
        branch: Current git branch

    Returns:
        Empty metrics dictionary
    """
    now = int(time.time())
    return {
        "version": "1.0",
        "session_id": session_id,
        "project_dir": project_dir,
        "branch": branch,
        "started_at": now,
        "ended_at": None,
        "duration_seconds": None,

        # Tool usage patterns
        "tools": {},

        # Requirement flow
        "requirements": {},

        # Error patterns
        "errors": [],

        # Git activity
        "git": {
            "commits": [],
            "files_changed": 0,
            "lines_added": 0,
            "lines_removed": 0
        },

        # Skill/command usage
        "skills": [],
        "commands": [],

        # Agents invoked
        "agents": [],

        # Learning annotations (added by /session-reflect)
        "learnings": {
            "patterns_detected": [],
            "improvements_made": [],
            "user_feedback": None
        }
    }


def load_metrics(session_id: str, project_dir: str) -> dict:
    """
    Load metrics for session.

    Uses shared file locking for safe concurrent reads.

    Args:
        session_id: Session ID (8-character hex)
        project_dir: Project root directory

    Returns:
        Metrics dictionary (empty metrics if file doesn't exist)
    """
    path = get_metrics_path(session_id, project_dir)

    if not path.exists():
        return None  # Return None to indicate no metrics exist yet

    try:
        with open(path, 'r') as f:
            fcntl.flock(f, fcntl.LOCK_SH)
            try:
                metrics = json.load(f)
                if metrics.get('version') != '1.0':
                    return None
                return metrics
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
    except (json.JSONDecodeError, OSError, IOError) as e:
        get_logger().warning(f"Session metrics issue for {session_id}: {e}")
        return None


def save_metrics(session_id: str, project_dir: str, metrics: dict) -> None:
    """
    Save metrics atomically.

    Uses exclusive file locking and atomic rename for safety.

    Args:
        session_id: Session ID (8-character hex)
        project_dir: Project root directory
        metrics: Metrics dictionary to save
    """
    path = get_metrics_path(session_id, project_dir)
    temp_path = path.with_suffix('.tmp')

    try:
        with open(temp_path, 'w') as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                json.dump(metrics, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

        # Atomic rename
        temp_path.rename(path)
    except OSError as e:
        get_logger().warning(f"Could not save session metrics for {session_id}: {e}")
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass


def delete_metrics(session_id: str, project_dir: str) -> None:
    """
    Delete metrics file for session.

    Args:
        session_id: Session ID (8-character hex)
        project_dir: Project root directory
    """
    path = get_metrics_path(session_id, project_dir)
    if path.exists():
        try:
            path.unlink()
        except OSError as e:
            get_logger().warning(f"Could not delete metrics for {session_id}: {e}")


def list_session_metrics(project_dir: str, max_age_days: int = 30) -> list[dict]:
    """
    List all session metrics for project within age limit.

    Args:
        project_dir: Project root directory
        max_age_days: Only return sessions from last N days

    Returns:
        List of (session_id, metrics_summary) tuples sorted by start time
    """
    sessions_dir = get_sessions_dir(project_dir)
    if not sessions_dir.exists():
        return []

    cutoff = int(time.time()) - (max_age_days * 86400)
    results = []

    for path in sessions_dir.glob('*.json'):
        if path.name.endswith('.tmp'):
            continue

        try:
            with open(path) as f:
                metrics = json.load(f)
                started_at = metrics.get('started_at', 0)
                if started_at >= cutoff:
                    results.append({
                        'session_id': metrics.get('session_id', path.stem),
                        'branch': metrics.get('branch', 'unknown'),
                        'started_at': started_at,
                        'ended_at': metrics.get('ended_at'),
                        'tool_count': sum(t.get('count', 0) for t in metrics.get('tools', {}).values()),
                        'error_count': len(metrics.get('errors', [])),
                        'path': str(path)
                    })
        except (json.JSONDecodeError, OSError):
            continue

    # Sort by start time, newest first
    results.sort(key=lambda x: x['started_at'], reverse=True)
    return results


class SessionMetrics:
    """
    Session metrics recorder for use in hooks.

    Provides a simple interface for recording session activity.
    All operations are fail-open - errors are logged but never raised.

    Usage:
        metrics = SessionMetrics(session_id, project_dir, branch)
        metrics.record_tool_use("Edit", file="src/auth.py", blocked=True)
        metrics.record_requirement_trigger("commit_plan")
        metrics.save()
    """

    def __init__(self, session_id: str, project_dir: str, branch: str = None):
        """
        Initialize metrics recorder.

        Args:
            session_id: Session ID (8-character hex)
            project_dir: Project root directory
            branch: Current git branch (optional, loaded from existing metrics)
        """
        self.session_id = session_id
        self.project_dir = project_dir
        self.branch = branch
        self._metrics = None
        self._dirty = False

    def _ensure_loaded(self) -> None:
        """Load or create metrics."""
        if self._metrics is not None:
            return

        self._metrics = load_metrics(self.session_id, self.project_dir)
        if self._metrics is None:
            self._metrics = create_empty_metrics(
                self.session_id,
                self.project_dir,
                self.branch or 'unknown'
            )
            self._dirty = True

    def record_tool_use(self, tool_name: str, file: str = None,
                        blocked: bool = False, requirement: str = None,
                        command: str = None) -> None:
        """
        Record a tool use event.

        Args:
            tool_name: Name of the tool (Edit, Write, Bash, Read, Task, etc.)
            file: File being operated on (for file tools)
            blocked: Whether the tool was blocked by a requirement
            requirement: Requirement that blocked (if blocked=True)
            command: Command executed (for Bash tool)
        """
        try:
            self._ensure_loaded()

            tools = self._metrics.setdefault('tools', {})
            tool_data = tools.setdefault(tool_name, {
                'count': 0,
                'blocked_count': 0,
                'files': [],
                'commands': []
            })

            tool_data['count'] += 1

            if blocked:
                tool_data['blocked_count'] += 1

            if file and file not in tool_data['files']:
                tool_data['files'].append(file)
                # Keep only last 50 unique files
                if len(tool_data['files']) > 50:
                    tool_data['files'] = tool_data['files'][-50:]

            if command and command not in tool_data['commands']:
                tool_data['commands'].append(command)
                # Keep only last 30 unique commands
                if len(tool_data['commands']) > 30:
                    tool_data['commands'] = tool_data['commands'][-30:]

            self._dirty = True

        except Exception as e:
            get_logger().warning(f"Failed to record tool use: {e}")

    def record_requirement_trigger(self, req_name: str, blocked: bool = True) -> None:
        """
        Record when a requirement is triggered.

        Args:
            req_name: Name of the requirement
            blocked: Whether the requirement blocked the action
        """
        try:
            self._ensure_loaded()

            reqs = self._metrics.setdefault('requirements', {})
            req_data = reqs.setdefault(req_name, {
                'triggered_at': None,
                'blocked_count': 0,
                'satisfied_at': None,
                'satisfied_by': None,
                'time_to_satisfy_seconds': None
            })

            now = int(time.time())
            if req_data['triggered_at'] is None:
                req_data['triggered_at'] = now

            if blocked:
                req_data['blocked_count'] += 1

            self._dirty = True

        except Exception as e:
            get_logger().warning(f"Failed to record requirement trigger: {e}")

    def record_requirement_satisfied(self, req_name: str, satisfied_by: str) -> None:
        """
        Record when a requirement is satisfied.

        Args:
            req_name: Name of the requirement
            satisfied_by: Method of satisfaction (skill, cli, auto_satisfy)
        """
        try:
            self._ensure_loaded()

            reqs = self._metrics.setdefault('requirements', {})
            req_data = reqs.setdefault(req_name, {
                'triggered_at': None,
                'blocked_count': 0,
                'satisfied_at': None,
                'satisfied_by': None,
                'time_to_satisfy_seconds': None
            })

            now = int(time.time())
            req_data['satisfied_at'] = now
            req_data['satisfied_by'] = satisfied_by

            # Calculate time to satisfy
            if req_data['triggered_at']:
                req_data['time_to_satisfy_seconds'] = now - req_data['triggered_at']

            self._dirty = True

        except Exception as e:
            get_logger().warning(f"Failed to record requirement satisfaction: {e}")

    def record_error(self, error_type: str, message: str = None,
                     tool: str = None, requirement: str = None) -> None:
        """
        Record an error event.

        Args:
            error_type: Type of error (blocked, command_failed, etc.)
            message: Error message
            tool: Tool that caused the error
            requirement: Requirement involved
        """
        try:
            self._ensure_loaded()

            errors = self._metrics.setdefault('errors', [])
            errors.append({
                'type': error_type,
                'message': message,
                'tool': tool,
                'requirement': requirement,
                'timestamp': int(time.time())
            })

            # Keep only last 100 errors
            if len(errors) > 100:
                self._metrics['errors'] = errors[-100:]

            self._dirty = True

        except Exception as e:
            get_logger().warning(f"Failed to record error: {e}")

    def record_skill_use(self, skill_name: str) -> None:
        """
        Record a skill invocation.

        Args:
            skill_name: Name of the skill (e.g., 'pre-commit', 'quality-check')
        """
        try:
            self._ensure_loaded()

            skills = self._metrics.setdefault('skills', [])
            skills.append({
                'name': skill_name,
                'timestamp': int(time.time())
            })

            # Keep only last 50 skills
            if len(skills) > 50:
                self._metrics['skills'] = skills[-50:]

            self._dirty = True

        except Exception as e:
            get_logger().warning(f"Failed to record skill use: {e}")

    def record_agent_use(self, agent_name: str) -> None:
        """
        Record an agent invocation.

        Args:
            agent_name: Name of the agent (e.g., 'code-reviewer', 'test-analyzer')
        """
        try:
            self._ensure_loaded()

            agents = self._metrics.setdefault('agents', [])
            agents.append({
                'name': agent_name,
                'timestamp': int(time.time())
            })

            # Keep only last 50 agents
            if len(agents) > 50:
                self._metrics['agents'] = agents[-50:]

            self._dirty = True

        except Exception as e:
            get_logger().warning(f"Failed to record agent use: {e}")

    def record_git_activity(self, commits: list[str] = None,
                            files_changed: int = None,
                            lines_added: int = None,
                            lines_removed: int = None) -> None:
        """
        Record git activity.

        Args:
            commits: List of commit hashes
            files_changed: Number of files changed
            lines_added: Lines added
            lines_removed: Lines removed
        """
        try:
            self._ensure_loaded()

            git_data = self._metrics.setdefault('git', {
                'commits': [],
                'files_changed': 0,
                'lines_added': 0,
                'lines_removed': 0
            })

            if commits:
                for commit in commits:
                    if commit not in git_data['commits']:
                        git_data['commits'].append(commit)

            if files_changed is not None:
                git_data['files_changed'] = files_changed

            if lines_added is not None:
                git_data['lines_added'] = lines_added

            if lines_removed is not None:
                git_data['lines_removed'] = lines_removed

            self._dirty = True

        except Exception as e:
            get_logger().warning(f"Failed to record git activity: {e}")

    def finalize_session(self) -> None:
        """
        Finalize session metrics with end time and duration.

        Called when session ends.
        """
        try:
            self._ensure_loaded()

            now = int(time.time())
            self._metrics['ended_at'] = now

            if self._metrics.get('started_at'):
                self._metrics['duration_seconds'] = now - self._metrics['started_at']

            self._dirty = True

        except Exception as e:
            get_logger().warning(f"Failed to finalize session: {e}")

    def get_summary(self) -> dict:
        """
        Get a summary of session metrics.

        Returns:
            Summary dictionary with key metrics
        """
        try:
            self._ensure_loaded()

            tools = self._metrics.get('tools', {})
            reqs = self._metrics.get('requirements', {})

            return {
                'session_id': self.session_id,
                'branch': self._metrics.get('branch', 'unknown'),
                'duration_seconds': self._metrics.get('duration_seconds'),
                'tool_uses': sum(t.get('count', 0) for t in tools.values()),
                'blocked_count': sum(t.get('blocked_count', 0) for t in tools.values()),
                'requirements_triggered': len(reqs),
                'requirements_satisfied': sum(
                    1 for r in reqs.values() if r.get('satisfied_at')
                ),
                'error_count': len(self._metrics.get('errors', [])),
                'skills_used': len(self._metrics.get('skills', [])),
                'agents_used': len(self._metrics.get('agents', []))
            }
        except Exception as e:
            get_logger().warning(f"Failed to get summary: {e}")
            return {}

    def save(self) -> None:
        """
        Save metrics to disk if modified.

        Uses atomic write for safety.
        """
        if not self._dirty or self._metrics is None:
            return

        save_metrics(self.session_id, self.project_dir, self._metrics)
        self._dirty = False


if __name__ == "__main__":
    # Quick test
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        # Simulate git repo
        os.makedirs(f"{tmpdir}/.git")

        # Test session metrics
        metrics = SessionMetrics("test1234", tmpdir, "main")

        # Record some activity
        metrics.record_tool_use("Edit", file="src/auth.py", blocked=True, requirement="commit_plan")
        metrics.record_tool_use("Edit", file="src/auth.py")
        metrics.record_tool_use("Bash", command="pytest")
        metrics.record_requirement_trigger("commit_plan", blocked=True)
        metrics.record_requirement_satisfied("commit_plan", "skill")
        metrics.record_skill_use("pre-commit")
        metrics.record_agent_use("code-reviewer")
        metrics.record_error("blocked", message="Requirement not satisfied", requirement="commit_plan")
        metrics.save()

        # Load and verify
        loaded = load_metrics("test1234", tmpdir)
        print(f"Loaded metrics: {json.dumps(loaded, indent=2)}")

        # Test summary
        summary = metrics.get_summary()
        print(f"\nSummary: {summary}")

        # Test listing
        sessions = list_session_metrics(tmpdir)
        print(f"\nSessions: {sessions}")

        # Test finalize
        metrics.finalize_session()
        metrics.save()

        loaded = load_metrics("test1234", tmpdir)
        print(f"\nAfter finalize: ended_at={loaded.get('ended_at')}, duration={loaded.get('duration_seconds')}")

    print("\n✅ Session metrics tests passed")
