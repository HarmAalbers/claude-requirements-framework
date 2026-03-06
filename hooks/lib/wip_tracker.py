#!/usr/bin/env python3
"""
WIP Projects Tracker - Cross-project work-in-progress tracking.

Tracks branch lifecycle from plan creation through merge across all projects.
Uses RegistryClient for atomic file operations on ~/.claude/wip_projects.json.

Storage Format:
{
    "version": "1.0",
    "entries": {
        "/path/to/project::feature/auth": {
            "project_dir": "/path/to/project",
            "branch": "feature/auth",
            "status": "wip",
            "summary": "...",
            ...
        }
    }
}
"""

import time
from pathlib import Path
from typing import Any, Optional

from git_utils import run_git
from logger import get_logger
from registry_client import RegistryClient

# Default storage location
WIP_FILE = Path.home() / ".claude" / "wip_projects.json"

# Valid statuses
VALID_STATUSES = {"wip", "done", "paused", "todo"}


def _empty_registry() -> dict:
    """Return empty WIP registry structure."""
    return {"version": "1.0", "entries": {}}


def _new_entry(project_dir: str, branch: str) -> dict:
    """Create a new WIP entry with defaults."""
    now = time.time()
    return {
        "project_dir": project_dir,
        "branch": branch,
        "status": "wip",
        "summary": "",
        "github_issue": "",
        "plan_path": "",
        "session_id": "",
        "session_history": [],
        "created_at": now,
        "updated_at": now,
        "git_metrics": {
            "commit_count": 0,
            "files_changed": 0,
            "lines_added": 0,
            "lines_removed": 0,
            "last_commit_hash": None,
            "pushed": False,
            "pr_url": None,
        },
        "total_time_seconds": 0,
    }


class WipTracker:
    """
    Cross-project WIP tracking with atomic file operations.

    Uses RegistryClient for thread-safe, atomic read-modify-write.
    All operations fail-open (errors don't block work).
    """

    def __init__(self, wip_path: Optional[Path] = None):
        """
        Initialize WIP tracker.

        Args:
            wip_path: Path to wip_projects.json (default: ~/.claude/wip_projects.json)
        """
        self._path = wip_path or WIP_FILE
        self._client = RegistryClient(self._path)

    def _make_key(self, project_dir: str, branch: str) -> str:
        """Create composite key from project directory and branch."""
        return f"{project_dir}::{branch}"

    def get_entry(self, project_dir: str, branch: str) -> Optional[dict]:
        """
        Get a single WIP entry.

        Returns:
            Entry dict or None if not found.
        """
        registry = self._client.read()
        entries = registry.get("entries", {})
        return entries.get(self._make_key(project_dir, branch))

    def upsert_entry(self, project_dir: str, branch: str, updates: dict) -> bool:
        """
        Create or update a WIP entry atomically.

        Args:
            project_dir: Project directory path
            branch: Branch name
            updates: Fields to set/update on the entry

        Returns:
            True if successful, False on error.
        """
        key = self._make_key(project_dir, branch)

        def _update(registry: dict) -> dict:
            if "entries" not in registry:
                registry["entries"] = {}
            if key not in registry["entries"]:
                registry["entries"][key] = _new_entry(project_dir, branch)
            entry = registry["entries"][key]
            entry.update(updates)
            entry["updated_at"] = time.time()
            return registry

        return self._client.update(_update)

    def add_session(self, project_dir: str, branch: str, session_id: str) -> bool:
        """
        Register a session against a WIP entry.

        Creates entry if it doesn't exist. Adds session_id to history
        and sets it as the current session.

        Returns:
            True if successful, False on error.
        """
        key = self._make_key(project_dir, branch)

        def _update(registry: dict) -> dict:
            if "entries" not in registry:
                registry["entries"] = {}
            if key not in registry["entries"]:
                registry["entries"][key] = _new_entry(project_dir, branch)
            entry = registry["entries"][key]
            entry["session_id"] = session_id
            if session_id not in entry.get("session_history", []):
                entry.setdefault("session_history", []).append(session_id)
            entry["updated_at"] = time.time()
            return registry

        return self._client.update(_update)

    def set_status(self, project_dir: str, branch: str, status: str) -> bool:
        """
        Update status of a WIP entry.

        Args:
            status: One of 'wip', 'done', 'paused', 'todo'

        Returns:
            True if successful, False on error or invalid status.
        """
        if status not in VALID_STATUSES:
            return False
        return self.upsert_entry(project_dir, branch, {"status": status})

    def update_git_metrics(self, project_dir: str, branch: str, **kwargs: Any) -> bool:
        """
        Update git metrics on a WIP entry.

        Args:
            **kwargs: Metric fields to update (commit_count, files_changed, etc.)

        Returns:
            True if successful, False on error.
        """
        key = self._make_key(project_dir, branch)

        def _update(registry: dict) -> Optional[dict]:
            entries = registry.get("entries", {})
            if key not in entries:
                return None  # No entry to update
            metrics = entries[key].setdefault("git_metrics", {})
            for field, value in kwargs.items():
                metrics[field] = value
            entries[key]["updated_at"] = time.time()
            return registry

        return self._client.update(_update)

    def record_commit(self, project_dir: str, branch: str,
                      commit_hash: str, files_changed: int = 0,
                      lines_added: int = 0, lines_removed: int = 0) -> bool:
        """
        Atomically increment commit count and update git metrics.

        Args:
            commit_hash: Latest commit hash
            files_changed: Number of files changed
            lines_added: Lines added
            lines_removed: Lines removed

        Returns:
            True if successful, False on error.
        """
        key = self._make_key(project_dir, branch)

        def _update(registry: dict) -> Optional[dict]:
            entries = registry.get("entries", {})
            if key not in entries:
                return None
            metrics = entries[key].setdefault("git_metrics", {})
            metrics["commit_count"] = metrics.get("commit_count", 0) + 1
            metrics["last_commit_hash"] = commit_hash
            metrics["files_changed"] = files_changed
            metrics["lines_added"] = lines_added
            metrics["lines_removed"] = lines_removed
            entries[key]["updated_at"] = time.time()
            return registry

        return self._client.update(_update)

    def increment_time(self, project_dir: str, branch: str, seconds: float) -> bool:
        """
        Add elapsed time to a WIP entry.

        Args:
            seconds: Time to add in seconds

        Returns:
            True if successful, False on error.
        """
        key = self._make_key(project_dir, branch)

        def _update(registry: dict) -> Optional[dict]:
            entries = registry.get("entries", {})
            if key not in entries:
                return None
            entries[key]["total_time_seconds"] = (
                entries[key].get("total_time_seconds", 0) + seconds
            )
            entries[key]["updated_at"] = time.time()
            return registry

        return self._client.update(_update)

    def check_merged_branches(self, project_dir: str) -> list[str]:
        """
        Detect branches merged into main and auto-mark as done.

        Returns:
            List of branch names that were marked done.
        """
        logger = get_logger(base_context={"component": "WipTracker"})
        marked = []

        # Get merged branches from git
        exit_code, stdout, _ = run_git("git branch --merged main", cwd=project_dir)
        if exit_code != 0:
            # Try 'master' as fallback
            exit_code, stdout, _ = run_git(
                "git branch --merged master", cwd=project_dir
            )
        if exit_code != 0:
            return []

        merged = set()
        for line in stdout.splitlines():
            branch = line.strip().removeprefix("* ")
            if branch and branch not in ("main", "master", "develop"):
                merged.add(branch)

        if not merged:
            return []

        # Atomically mark merged WIP entries as done
        def _update(registry: dict) -> Optional[dict]:
            entries = registry.get("entries", {})
            changed = False
            for key, entry in entries.items():
                if (
                    entry.get("project_dir") == project_dir
                    and entry.get("branch") in merged
                    and entry.get("status") != "done"
                ):
                    entry["status"] = "done"
                    entry["updated_at"] = time.time()
                    marked.append(entry["branch"])
                    changed = True
                    logger.info("Auto-marked merged branch as done", branch=entry["branch"])
            return registry if changed else None

        self._client.update(_update)
        return marked

    def list_entries(
        self,
        status: Optional[str] = None,
        project: Optional[str] = None,
    ) -> list[dict]:
        """
        List WIP entries with optional filtering.

        Args:
            status: Filter by status (wip, done, paused, todo)
            project: Filter by project directory path

        Returns:
            List of matching entry dicts.
        """
        registry = self._client.read()
        entries = registry.get("entries", {})

        results = []
        for entry in entries.values():
            if status and entry.get("status") != status:
                continue
            if project and entry.get("project_dir") != project:
                continue
            results.append(entry)

        # Sort by updated_at descending (most recent first)
        results.sort(key=lambda e: e.get("updated_at", 0), reverse=True)
        return results

    def clean_done(self) -> int:
        """
        Remove all entries with status 'done'.

        Returns:
            Count of removed entries.
        """
        registry = self._client.read()
        count = sum(
            1 for e in registry.get("entries", {}).values()
            if e.get("status") == "done"
        )

        if count == 0:
            return 0

        def _update(reg: dict) -> Optional[dict]:
            entries = reg.get("entries", {})
            to_remove = [
                key for key, entry in entries.items()
                if entry.get("status") == "done"
            ]
            if not to_remove:
                return None
            for key in to_remove:
                del entries[key]
            return reg

        self._client.update(_update)
        return count
