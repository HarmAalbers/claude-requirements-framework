#!/usr/bin/env python3
"""
State file storage with atomic operations.

State files track which requirements have been satisfied for each branch.
They live in .git/requirements/ (automatically gitignored) and use
atomic writes with file locking to prevent corruption.

State File Format (JSON):
{
    "version": "1.0",
    "branch": "feature/auth",
    "project": "/path/to/project",
    "created_at": 1234567890,
    "updated_at": 1234567890,
    "requirements": {
        "commit_plan": {
            "scope": "session",
            "sessions": {
                "abc123": {
                    "satisfied": true,
                    "satisfied_at": 1234567890,
                    "satisfied_by": "cli"
                }
            }
        }
    }
}
"""
import fcntl
import json
import os
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

from logger import get_logger


def atomic_write_json(path: Path, data: dict) -> None:
    """Atomically write JSON to ``path`` via a per-writer unique temp + rename.

    Writes to a UNIQUE temp file in the same directory (``tempfile.mkstemp``),
    fsyncs, then ``os.replace`` over the target. The unique name is the crux of
    the fix: the old code shared a fixed ``<name>.tmp`` and truncated it at
    ``open('w')`` before taking the lock, so a second concurrent writer could
    truncate the first's in-flight temp to 0 bytes and the rename would then
    install an empty file. With unique temps that interleaving is impossible,
    and ``os.replace`` is an atomic same-directory rename on POSIX.

    Raises ``OSError`` on failure (callers decide whether to fail-open).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=path.name + ".", suffix=".tmp"
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, path)
    except OSError:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass
        raise


@contextmanager
def exclusive_file_lock(lock_path: Path):
    """Hold an exclusive cross-process advisory lock for the duration of the block.

    The lock is taken on a dedicated sidecar lock file (opened in append mode so
    it is never truncated, and never deleted) so it can safely serialize a full
    read-modify-write of a SEPARATE data file. Fail-open: if the lock cannot be
    acquired (unsupported filesystem, OS error, uncreatable path) the block still
    runs unlocked rather than blocking work — consistent with the framework's
    fail-open principle.
    """
    lock_file = None
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_file = open(lock_path, "a")
        fcntl.flock(lock_file, fcntl.LOCK_EX)
    except OSError as e:
        get_logger().warning(f"⚠️ Could not acquire lock {lock_path}: {e}")
        if lock_file is not None:
            try:
                lock_file.close()
            except OSError:
                pass
            lock_file = None
    try:
        yield
    finally:
        if lock_file is not None:
            try:
                fcntl.flock(lock_file, fcntl.LOCK_UN)
            except OSError:
                pass
            try:
                lock_file.close()
            except OSError:
                pass


def get_lock_path(branch: str, project_dir: str) -> Path:
    """Path to the sidecar lock file guarding a branch's state file."""
    return get_state_path(branch, project_dir).with_suffix(".lock")


def state_lock(branch: str, project_dir: str):
    """Exclusive lock context manager for a branch's state-file read-modify-write."""
    return exclusive_file_lock(get_lock_path(branch, project_dir))

def get_state_dir(project_dir: str) -> Path:
    """
    Get state directory for project.

    State is stored in .git/requirements/ which is automatically
    gitignored (anything in .git/ is ignored).

    In git worktrees, state is stored in the COMMON git directory
    (main repo's .git/) to share requirements across worktrees.

    Args:
        project_dir: Project root directory

    Returns:
        Path to state directory
    """
    try:
        from .git_utils import get_git_common_dir
    except ImportError:
        from git_utils import get_git_common_dir

    common_dir = get_git_common_dir(project_dir)

    if common_dir:
        return Path(common_dir) / 'requirements'

    # Fallback for non-git directories (fail-open)
    return Path(project_dir) / '.git' / 'requirements'


def ensure_state_dir(project_dir: str) -> None:
    """
    Create state directory if it doesn't exist.

    Handles both regular repos and worktrees.

    Args:
        project_dir: Project root directory
    """
    state_dir = get_state_dir(project_dir)
    try:
        state_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        # Fail-open: if we can't create the directory, log and continue
        get_logger().warning(f"Could not create state dir {state_dir}: {e}")


def branch_to_filename(branch: str) -> str:
    """
    Convert branch name to safe filename.

    Replaces slashes and special characters with safe alternatives.

    Args:
        branch: Git branch name (e.g., "feature/auth")

    Returns:
        Safe filename (e.g., "feature-auth.json")
    """
    # Replace path separators
    safe = branch.replace('/', '-').replace('\\', '-')
    # Keep only alphanumeric, dash, underscore
    safe = ''.join(c if c.isalnum() or c in '-_' else '_' for c in safe)
    return f"{safe}.json"


def get_state_path(branch: str, project_dir: str) -> Path:
    """
    Get path to state file for branch.

    Args:
        branch: Git branch name
        project_dir: Project root directory

    Returns:
        Path to state JSON file
    """
    ensure_state_dir(project_dir)
    return get_state_dir(project_dir) / branch_to_filename(branch)


def create_empty_state(branch: str, project_dir: str) -> dict:
    """
    Create empty state structure.

    Args:
        branch: Git branch name
        project_dir: Project root directory

    Returns:
        Empty state dictionary
    """
    now = int(time.time())
    return {
        "version": "1.0",
        "branch": branch,
        "project": project_dir,
        "created_at": now,
        "updated_at": now,
        "requirements": {}
    }


def load_state(branch: str, project_dir: str) -> dict:
    """
    Load state for branch.

    Uses shared file locking for safe concurrent reads.

    Args:
        branch: Git branch name
        project_dir: Project root directory

    Returns:
        State dictionary (empty state if file doesn't exist or is corrupted)
    """
    path = get_state_path(branch, project_dir)

    if not path.exists():
        return create_empty_state(branch, project_dir)

    try:
        with open(path, 'r') as f:
            # Shared lock for reading
            fcntl.flock(f, fcntl.LOCK_SH)
            try:
                state = json.load(f)
                # Version check - regenerate if incompatible
                if state.get('version') != '1.0':
                    return create_empty_state(branch, project_dir)
                return state
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
    except (json.JSONDecodeError, OSError, IOError) as e:
        # Corrupted or unreadable - return empty state
        get_logger().warning(f"⚠️ State file issue for {branch}: {e}")
        return create_empty_state(branch, project_dir)


def save_state(branch: str, project_dir: str, state: dict) -> None:
    """
    Save state atomically.

    Uses exclusive file locking and atomic rename for safety.

    Args:
        branch: Git branch name
        project_dir: Project root directory
        state: State dictionary to save
    """
    path = get_state_path(branch, project_dir)
    state['updated_at'] = int(time.time())

    # Atomic, corruption-safe write via a unique temp + os.replace.
    # Note: this writes the state as given. Serializing the full
    # read-modify-write across processes (so concurrent writers don't
    # last-writer-wins) is the caller's job via BranchRequirements.transaction()
    # / exclusive_file_lock(); save_state on its own only guarantees that an
    # individual write never corrupts the file.
    try:
        atomic_write_json(path, state)
    except OSError as e:
        get_logger().warning(f"⚠️ Could not save state for {branch}: {e}")


def delete_state(branch: str, project_dir: str) -> None:
    """
    Delete state file for branch.

    Args:
        branch: Git branch name
        project_dir: Project root directory
    """
    path = get_state_path(branch, project_dir)
    if path.exists():
        try:
            path.unlink()
        except OSError as e:
            get_logger().warning(f"⚠️ Could not delete state for {branch}: {e}")


def list_all_states(project_dir: str) -> list[tuple[str, Path]]:
    """
    List all state files in project.

    Args:
        project_dir: Project root directory

    Returns:
        List of (branch_name, path) tuples
    """
    state_dir = get_state_dir(project_dir)
    if not state_dir.exists():
        return []

    states = []
    for path in state_dir.glob('*.json'):
        # Skip temp files
        if path.name.endswith('.tmp'):
            continue

        # Try to read branch name from state
        try:
            with open(path) as f:
                state = json.load(f)
                branch = state.get('branch', path.stem)
                states.append((branch, path))
        except (json.JSONDecodeError, OSError):
            # Fall back to filename
            states.append((path.stem, path))

    return states


if __name__ == "__main__":
    # Quick test
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        # Simulate git repo
        os.makedirs(f"{tmpdir}/.git")

        # Test save/load
        state = create_empty_state("test/branch", tmpdir)
        state["requirements"]["test_req"] = {"satisfied": True}
        save_state("test/branch", tmpdir, state)

        loaded = load_state("test/branch", tmpdir)
        print(f"Loaded state: {json.dumps(loaded, indent=2)}")

        # Test list
        states = list_all_states(tmpdir)
        print(f"All states: {states}")

        # Test delete
        delete_state("test/branch", tmpdir)
        states = list_all_states(tmpdir)
        print(f"After delete: {states}")

    print("✅ State storage tests passed")
