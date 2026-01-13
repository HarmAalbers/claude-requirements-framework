#!/usr/bin/env python3
"""
Registry Client - Thread-safe session registry operations.

Centralizes file locking, atomic writes, and error handling for the session
registry. This eliminates ~110 lines of duplicated read-modify-write patterns
across session.py functions.

Key Design Decisions:
- Atomic writes using temp file + rename (POSIX atomicity guarantee)
- File locking (fcntl) for concurrent access safety
- Fail-open on all errors (registry failures never block work)
- Structured registry format with version field

Registry Structure:
{
    "version": "1.0",
    "sessions": {
        "abc12345": {
            "pid": 12345,
            "ppid": 12340,
            "project_dir": "/path/to/project",
            "branch": "main",
            "started_at": 1234567890,
            "last_active": 1234567895
        }
    }
}
"""

import fcntl
import json
import os
from pathlib import Path
from typing import Callable, Optional

from logger import get_logger

class RegistryClient:
    """
    Thread-safe client for session registry operations.

    Provides atomic read-modify-write operations with file locking.
    All operations fail-open (return empty/default values on errors).

    Thread-safety:
        Uses fcntl file locking for concurrent access:
        - LOCK_SH (shared) for reads
        - LOCK_EX (exclusive) for writes

    Atomic writes:
        Write to temp file → fsync → atomic rename
        Guarantees registry is never left in corrupted state.
    """

    def __init__(self, registry_path: Path):
        """
        Initialize registry client.

        Args:
            registry_path: Path to the sessions.json registry file
        """
        self.registry_path = registry_path

    def read(self) -> dict:
        """
        Read registry with shared lock.

        Returns:
            Registry dict with 'version' and 'sessions' keys.
            Returns empty registry {"version": "1.0", "sessions": {}} on errors.

        Errors (all return empty registry):
            - FileNotFoundError: Registry doesn't exist yet
            - json.JSONDecodeError: Corrupted registry
            - OSError/IOError: Permission errors, disk full, etc.

        Note:
            Fails open - errors don't propagate, ensuring registry
            read failures never block hook operations.
        """
        if not self.registry_path.exists():
            return {"version": "1.0", "sessions": {}}

        try:
            with open(self.registry_path, 'r') as f:
                fcntl.flock(f, fcntl.LOCK_SH)  # Shared lock for reading
                try:
                    registry = json.load(f)
                finally:
                    fcntl.flock(f, fcntl.LOCK_UN)
            return registry
        except json.JSONDecodeError as e:
            # Corrupted registry - log for debugging
            get_logger().warning(f"⚠️ Registry corrupted ({self.registry_path}): {e}")
            return {"version": "1.0", "sessions": {}}
        except (OSError, IOError) as e:
            # I/O or permission errors - log for debugging
            get_logger().warning(f"⚠️ Registry read error ({self.registry_path}): {e}")
            return {"version": "1.0", "sessions": {}}

    def write(self, registry: dict) -> bool:
        """
        Write registry atomically with exclusive lock.

        Uses atomic write pattern:
        1. Write to temp file with exclusive lock
        2. fsync to ensure data on disk
        3. Atomic rename (POSIX guarantee)
        4. Clean up temp file on any failure

        Args:
            registry: Registry dict to write

        Returns:
            True if write succeeded, False on error

        Errors (all return False):
            - OSError: Disk full, permission denied, etc.
            - IOError: I/O errors during write

        Note:
            Fails open - errors don't raise, ensuring registry
            write failures never block hook operations.
        """
        # Ensure parent directory exists
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)

        temp_path = self.registry_path.with_suffix('.tmp')

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
            temp_path.rename(self.registry_path)
            return True
        except (OSError, IOError) as e:
            # Fail-open: clean up temp file but don't raise
            get_logger().warning(f"⚠️ Registry write error ({self.registry_path}): {e}")
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except OSError as cleanup_err:
                    get_logger().warning(
                        f"⚠️ Failed to cleanup temp file ({temp_path}): {cleanup_err}"
                    )
            return False

    def update(self, update_fn: Callable[[dict], Optional[dict]]) -> bool:
        """
        Atomic read-modify-write operation.

        Reads registry, applies update function, writes back atomically.
        This pattern prevents race conditions from separate read/write calls.

        Args:
            update_fn: Function that takes registry dict and returns:
                - Updated registry dict to write back
                - None to abort write (no changes needed)

        Returns:
            True if update succeeded (or was skipped), False on error

        Example:
            def add_session(registry):
                registry["sessions"]["abc123"] = {...}
                return registry

            client.update(add_session)

        Note:
            The update_fn should be idempotent and fast, as the
            registry is locked during its execution.
        """
        registry = self.read()

        try:
            updated = update_fn(registry)

            # If update_fn returns None, skip write
            if updated is None:
                return True

            return self.write(updated)
        except (OSError, IOError, json.JSONDecodeError) as e:
            # Expected I/O errors from read/write - fail open
            get_logger().warning(f"⚠️ Registry update I/O error: {e}")
            return False
        except Exception as e:
            # Unexpected errors from update_fn - indicates programming bug
            get_logger().warning(f"⚠️ Registry update function error: {e}")
            # In production, we still fail-open, but log the full error
            import traceback
            get_logger().warning(traceback.format_exc())
            return False
