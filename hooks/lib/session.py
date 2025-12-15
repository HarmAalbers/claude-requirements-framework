#!/usr/bin/env python3
"""
Session ID management for requirements framework.

A session represents a single Claude Code CLI session. Requirements with
'session' scope need to be satisfied once per session.

Strategy for obtaining session ID:
1. Check CLAUDE_SESSION_ID environment variable (if set by Claude Code)
2. Use parent process ID as stable identifier (same PID = same session)
3. Generate and cache in temp file as fallback
"""
import fcntl
import json
import os
import time
import uuid
from pathlib import Path


def get_session_id() -> str:
    """
    Get or generate a stable session ID.

    Returns the same ID for the duration of a Claude Code session,
    but different IDs for different sessions.

    Returns:
        str: 8-character hex session identifier
    """
    # Strategy 1: Check environment variable
    if 'CLAUDE_SESSION_ID' in os.environ:
        return os.environ['CLAUDE_SESSION_ID']

    # Strategy 2: Use parent process ID (stable for CLI session)
    # The parent PID is the Claude Code process, which stays constant
    # for all hook invocations within a single session
    ppid = os.getppid()
    session_file = Path(f"/tmp/claude-session-{ppid}.id")

    # Try to read existing session ID for this parent process
    if session_file.exists():
        try:
            session_id = session_file.read_text().strip()
            if session_id and len(session_id) == 8:
                return session_id
        except (OSError, IOError):
            pass  # Fall through to generate new

    # Strategy 3: Generate new session ID
    session_id = uuid.uuid4().hex[:8]

    # Best-effort cache (don't fail if we can't write)
    try:
        session_file.write_text(session_id)
    except (OSError, IOError):
        pass

    return session_id


def clear_session_cache() -> None:
    """
    Clear cached session ID files.

    Called during cleanup/prune operations to remove stale session files.
    """
    import glob

    for session_file in glob.glob("/tmp/claude-session-*.id"):
        try:
            Path(session_file).unlink()
        except (OSError, IOError):
            pass


def get_registry_path() -> Path:
    """
    Get path to session registry file.

    The registry tracks all active Claude Code sessions to enable
    session discovery and CLI auto-detection.

    Returns:
        Path to registry file (~/.claude/sessions.json)
    """
    return Path.home() / '.claude' / 'sessions.json'


def is_process_alive(pid: int) -> bool:
    """
    Check if a process ID exists.

    Uses os.kill(pid, 0) which doesn't send a signal but checks
    if the process exists.

    Args:
        pid: Process ID to check

    Returns:
        True if process exists, False otherwise
    """
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def update_registry(session_id: str, project_dir: str, branch: str) -> None:
    """
    Update session registry with current session info.

    Maintains a registry of active Claude Code sessions to enable
    CLI auto-detection and session discovery.

    Uses file locking for thread-safe concurrent updates and automatically
    cleans up stale entries for processes that no longer exist.

    Args:
        session_id: Current session ID (8-character hex)
        project_dir: Project root directory path
        branch: Current git branch name

    Note:
        This function is fail-open: errors are logged but don't raise exceptions,
        so registry failures never block hook execution.
    """
    registry_path = get_registry_path()

    # Ensure ~/.claude directory exists
    registry_path.parent.mkdir(parents=True, exist_ok=True)

    # Read existing registry (or create empty)
    registry = {"version": "1.0", "sessions": {}}

    if registry_path.exists():
        try:
            with open(registry_path, 'r') as f:
                fcntl.flock(f, fcntl.LOCK_SH)  # Shared lock for reading
                try:
                    registry = json.load(f)
                finally:
                    fcntl.flock(f, fcntl.LOCK_UN)
        except (json.JSONDecodeError, OSError, IOError):
            # Corrupted registry - start fresh
            registry = {"version": "1.0", "sessions": {}}

    # Clean up stale entries (dead processes) - check ppid (Claude session) not pid (hook)
    sessions = registry.get("sessions", {})
    stale_ids = []
    for sid, sess_data in sessions.items():
        if not is_process_alive(sess_data.get("ppid", 0)):
            stale_ids.append(sid)

    for sid in stale_ids:
        del sessions[sid]

    # Update or add current session
    now = int(time.time())
    if session_id not in sessions:
        sessions[session_id] = {
            "pid": os.getpid(),
            "ppid": os.getppid(),
            "project_dir": project_dir,
            "branch": branch,
            "started_at": now,
            "last_active": now
        }
    else:
        # Update existing session
        sessions[session_id].update({
            "project_dir": project_dir,
            "branch": branch,
            "last_active": now
        })

    registry["sessions"] = sessions

    # Write atomically using temp file + rename
    temp_path = registry_path.with_suffix('.tmp')

    try:
        with open(temp_path, 'w') as f:
            fcntl.flock(f, fcntl.LOCK_EX)  # Exclusive lock for writing
            try:
                json.dump(registry, f, indent=2)
                f.flush()
                os.fsync(f.fileno())  # Ensure written to disk
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

        # Atomic rename (POSIX guarantees atomicity)
        temp_path.rename(registry_path)
    except OSError:
        # Fail-open: clean up temp file but don't raise
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass


def get_active_sessions(project_dir: str = None, branch: str = None) -> list[dict]:
    """
    Get list of active Claude Code sessions.

    Reads the registry and filters for sessions with processes that still exist.
    Optionally filters by project directory and/or branch name.

    Args:
        project_dir: Optional project directory filter
        branch: Optional branch name filter

    Returns:
        List of session dictionaries with keys:
        - id: Session ID
        - pid: Process ID
        - ppid: Parent process ID
        - project_dir: Project directory
        - branch: Branch name
        - started_at: Session start timestamp
        - last_active: Last activity timestamp
    """
    registry_path = get_registry_path()

    if not registry_path.exists():
        return []

    try:
        with open(registry_path, 'r') as f:
            fcntl.flock(f, fcntl.LOCK_SH)  # Shared lock for reading
            try:
                registry = json.load(f)
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
    except (json.JSONDecodeError, OSError, IOError):
        return []

    sessions = registry.get("sessions", {})
    result = []

    for session_id, sess_data in sessions.items():
        # Filter out dead processes - check ppid (Claude session) not pid (hook subprocess)
        # The hook is a short-lived subprocess, but ppid is the actual Claude session
        if not is_process_alive(sess_data.get("ppid", 0)):
            continue

        # Apply filters
        if project_dir and sess_data.get("project_dir") != project_dir:
            continue
        if branch and sess_data.get("branch") != branch:
            continue

        # Add to result with id field
        sess_copy = sess_data.copy()
        sess_copy["id"] = session_id
        result.append(sess_copy)

    return result


def cleanup_stale_sessions() -> int:
    """
    Remove registry entries for dead processes.

    Reads the registry, validates each PID, and removes entries for
    processes that no longer exist.

    Returns:
        Number of stale entries removed
    """
    registry_path = get_registry_path()

    if not registry_path.exists():
        return 0

    # Read registry
    try:
        with open(registry_path, 'r') as f:
            fcntl.flock(f, fcntl.LOCK_SH)
            try:
                registry = json.load(f)
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
    except (json.JSONDecodeError, OSError, IOError):
        return 0

    # Find stale entries - check ppid (Claude session) not pid (hook subprocess)
    sessions = registry.get("sessions", {})
    stale_ids = []
    for session_id, sess_data in sessions.items():
        if not is_process_alive(sess_data.get("ppid", 0)):
            stale_ids.append(session_id)

    if not stale_ids:
        return 0

    # Remove stale entries
    for session_id in stale_ids:
        del sessions[session_id]

    registry["sessions"] = sessions

    # Write back atomically
    temp_path = registry_path.with_suffix('.tmp')

    try:
        with open(temp_path, 'w') as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                json.dump(registry, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

        temp_path.rename(registry_path)
    except OSError:
        # Fail-open
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass
        return 0

    return len(stale_ids)


def remove_session_from_registry(session_id: str) -> bool:
    """
    Remove a specific session from the registry.

    Used by SessionEnd hook to clean up when a session ends.

    Args:
        session_id: Session ID to remove (8-character hex)

    Returns:
        True if session was found and removed, False otherwise
    """
    registry_path = get_registry_path()

    if not registry_path.exists():
        return False

    # Read registry
    try:
        with open(registry_path, 'r') as f:
            fcntl.flock(f, fcntl.LOCK_SH)
            try:
                registry = json.load(f)
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
    except (json.JSONDecodeError, OSError, IOError):
        return False

    sessions = registry.get("sessions", {})

    # Check if session exists
    if session_id not in sessions:
        return False

    # Remove the session
    del sessions[session_id]
    registry["sessions"] = sessions

    # Write back atomically
    temp_path = registry_path.with_suffix('.tmp')

    try:
        with open(temp_path, 'w') as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                json.dump(registry, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

        temp_path.rename(registry_path)
        return True
    except OSError:
        # Fail-open
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass
        return False


if __name__ == "__main__":
    # Quick test
    print(f"Session ID: {get_session_id()}")
    print(f"Session ID (again): {get_session_id()}")  # Should be same
