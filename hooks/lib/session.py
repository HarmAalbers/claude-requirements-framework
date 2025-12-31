#!/usr/bin/env python3
"""
Session ID management for requirements framework.

A session represents a single Claude Code CLI session. Requirements with
'session' scope need to be satisfied once per session.

Session ID detection:
- Hooks: Read session_id from stdin JSON (always provided by Claude Code)
- CLI: Look up session in registry by PPID and project directory
- Registry is maintained by hooks at ~/.claude/sessions.json
"""
import json
import os
import time
import uuid
from pathlib import Path


class SessionNotFoundError(RuntimeError):
    """Raised when no matching Claude Code session is found in the registry."""
    pass


def normalize_session_id(session_id: str) -> str:
    """
    Normalize session ID to 8-character hex format.

    Ensures consistent session ID format across all code paths (env var,
    PPID-based, and generated). This fixes the bug where CLAUDE_SESSION_ID
    provides full UUIDs but PPID fallback generates 8-char IDs, causing
    state mismatch.

    Handles:
    - Full UUIDs with dashes: "cad0ac4d-3933-45ad-9a1c-14aec05bb940" → "cad0ac4d"
    - Full UUIDs without dashes: "cad0ac4d393345ad9a1c14aec05bb940" → "cad0ac4d"
    - Already 8-char IDs: "08345d22" → "08345d22" (idempotent)
    - Short IDs: "abc" → "abc" (unchanged)
    - Invalid/empty input: "" → generates new 8-char ID

    Args:
        session_id: Session identifier in any format

    Returns:
        8-character hex session ID

    Example:
        >>> normalize_session_id("cad0ac4d-3933-45ad-9a1c-14aec05bb940")
        'cad0ac4d'
        >>> normalize_session_id("08345d22")
        '08345d22'
    """
    if not session_id or not isinstance(session_id, str):
        # Generate new ID for invalid input
        return uuid.uuid4().hex[:8]

    # Remove dashes (UUIDs like cad0ac4d-3933-45ad-9a1c-14aec05bb940)
    clean = session_id.replace('-', '')

    # Take first 8 hex chars
    # If already 8 or less, return as-is (idempotent)
    # If longer (full UUID), take first 8
    if len(clean) <= 8:
        return clean
    else:
        return clean[:8]


def get_session_id() -> str:
    """
    Get session ID from registry by matching PPID and project directory.

    IMPORTANT: This should ONLY be used by CLI commands, NOT by hooks!
    Hooks should always read session_id from stdin JSON.

    This function uses the session registry (maintained by hooks) to find
    the active Claude Code session for the current process and project.
    If no matching session is found, raises RuntimeError with helpful message.

    Returns:
        str: 8-character hex session identifier

    Raises:
        SessionNotFoundError: If no matching session found in registry
    """
    from git_utils import resolve_project_root

    ppid = os.getppid()
    registry_path = get_registry_path()

    # Check if registry exists
    if not registry_path.exists():
        raise SessionNotFoundError(
            f"❌ No active Claude Code session found!\n\n"
            f"💡 Session registry not found at: {registry_path}\n"
            f"💡 Are you running this from within a Claude Code session?\n\n"
            f"If you're running from a shell, make sure it was spawned by Claude Code."
        )

    # Load registry
    try:
        with open(registry_path) as f:
            registry = json.load(f)
    except json.JSONDecodeError as e:
        raise SessionNotFoundError(
            f"❌ Failed to read session registry!\n\n"
            f"💡 Registry path: {registry_path}\n"
            f"💡 JSON parse error: {e}\n\n"
            f"Try restarting Claude Code to rebuild the registry."
        ) from e
    except OSError as e:
        raise SessionNotFoundError(
            f"❌ Failed to read session registry!\n\n"
            f"💡 Registry path: {registry_path}\n"
            f"💡 File error: {e}\n\n"
            f"Try restarting Claude Code to rebuild the registry."
        ) from e

    sessions = registry.get("sessions", {})
    if not sessions:
        raise SessionNotFoundError(
            f"❌ No active Claude Code sessions in registry!\n\n"
            f"💡 Registry exists but contains no sessions\n"
            f"💡 Try running a command in Claude Code first to populate the registry"
        )

    # Get current project directory
    try:
        project_dir = resolve_project_root(verbose=False)
    except (OSError, RuntimeError):
        # Not in a git repo or permission denied - match by PPID only
        project_dir = None

    # Find session matching BOTH ppid AND project (if we have a project)
    for session_id, sess_data in sessions.items():
        ppid_match = sess_data.get("ppid") == ppid

        if project_dir:
            project_match = sess_data.get("project_dir") == project_dir
            if ppid_match and project_match:
                return normalize_session_id(session_id)
        else:
            # No project dir - match by PPID only
            if ppid_match:
                return normalize_session_id(session_id)

    # No match found - show helpful error
    session_list = "\n".join(
        f"  • {sid}: {sd.get('project_dir', 'unknown')} (PPID {sd.get('ppid', '?')})"
        for sid, sd in sessions.items()
    )

    raise SessionNotFoundError(
        f"❌ No Claude Code session found for this shell!\n\n"
        f"💡 Current PPID: {ppid}\n"
        f"💡 Current Project: {project_dir or '(not in git repo)'}\n\n"
        f"Active sessions:\n{session_list}\n\n"
        f"💡 Use --session flag to specify session explicitly, or\n"
        f"💡 Run this command from a shell within Claude Code"
    )


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
    from registry_client import RegistryClient

    registry_path = get_registry_path()
    client = RegistryClient(registry_path)

    def update_session(registry):
        """Update or add session with inline stale cleanup and ID normalization migration."""
        sessions = registry.get("sessions", {})

        # Clean up stale entries (dead processes) - check ppid (Claude session) not pid (hook)
        stale_ids = []
        for sid, sess_data in sessions.items():
            if not is_process_alive(sess_data.get("ppid", 0)):
                stale_ids.append(sid)

        for sid in stale_ids:
            del sessions[sid]

        # MIGRATION: Check for duplicate entries with same PPID but different session IDs
        # This handles the case where a session existed before session ID normalization
        # Example: "cad0ac4d-3933-..." (old) and "cad0ac4d" (new) both exist for same PPID
        current_ppid = os.getppid()
        duplicate_ids = []
        for sid, sess_data in sessions.items():
            if sid != session_id and sess_data.get("ppid") == current_ppid:
                # Found an existing entry for this session with a different ID
                # Check if it's a non-normalized version of the current session_id
                normalized = normalize_session_id(sid)
                if normalized == session_id:
                    # This is the same session, just with old UUID format
                    duplicate_ids.append(sid)

        # Remove duplicate entries (old UUID format entries for same PPID)
        for sid in duplicate_ids:
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
        return registry

    # Use atomic update
    client.update(update_session)


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
    from registry_client import RegistryClient

    registry_path = get_registry_path()
    client = RegistryClient(registry_path)

    registry = client.read()
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
    from registry_client import RegistryClient

    registry_path = get_registry_path()
    client = RegistryClient(registry_path)

    stale_count = 0

    def cleanup_stale(registry):
        """Find and remove stale sessions."""
        nonlocal stale_count

        sessions = registry.get("sessions", {})
        stale_ids = []

        # Find stale entries - check ppid (Claude session) not pid (hook subprocess)
        for session_id, sess_data in sessions.items():
            if not is_process_alive(sess_data.get("ppid", 0)):
                stale_ids.append(session_id)

        if not stale_ids:
            return None  # No changes needed

        # Remove stale entries
        for session_id in stale_ids:
            del sessions[session_id]

        registry["sessions"] = sessions
        stale_count = len(stale_ids)
        return registry

    # Use atomic update
    client.update(cleanup_stale)
    return stale_count


def remove_session_from_registry(session_id: str) -> bool:
    """
    Remove a specific session from the registry.

    Used by SessionEnd hook to clean up when a session ends.

    Args:
        session_id: Session ID to remove (8-character hex)

    Returns:
        True if session was found and removed, False otherwise
    """
    from registry_client import RegistryClient

    registry_path = get_registry_path()
    client = RegistryClient(registry_path)

    was_found = False

    def remove_session(registry):
        """Remove session if it exists."""
        nonlocal was_found

        sessions = registry.get("sessions", {})

        if session_id not in sessions:
            # Session not found - signal no write needed
            was_found = False
            return None

        # Remove the session
        del sessions[session_id]
        registry["sessions"] = sessions
        was_found = True
        return registry

    # Use atomic update
    client.update(remove_session)
    return was_found


if __name__ == "__main__":
    # Quick test
    print(f"Session ID: {get_session_id()}")
    print(f"Session ID (again): {get_session_id()}")  # Should be same
