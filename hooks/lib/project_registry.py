#!/usr/bin/env python3
"""
Project Registry Module

Tracks all projects using the requirements framework across the machine.
Enables cross-project feature discovery and upgrade workflows.

Storage: ~/.claude/project_registry.json

Registry format:
{
    "version": "1.0",
    "updated_at": 1234567890,
    "projects": {
        "/path/to/project": {
            "discovered_at": 1234567890,
            "last_seen": 1234567890,
            "has_global_inherit": true,
            "configured_features": ["commit_plan", "adr_reviewed"]
        }
    }
}

Usage:
    from project_registry import ProjectRegistry

    registry = ProjectRegistry()

    # Scan for projects
    found = registry.scan_for_projects([Path.home()])

    # Register current project
    registry.register_project("/path/to/project", ["commit_plan"])

    # List all known projects
    projects = registry.list_projects()

    # Prune stale entries
    removed = registry.prune_stale()
"""
import fcntl
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from logger import get_logger

# Default registry location
DEFAULT_REGISTRY_PATH = Path.home() / ".claude" / "project_registry.json"

# Default paths to scan for projects
DEFAULT_SCAN_PATHS = [
    Path.home() / "Projects",
    Path.home() / "Work",
    Path.home() / "Code",
    Path.home() / "Developer",
    Path.home() / "dev",
    Path.home() / "Tools",
]

# Maximum scan depth to prevent scanning entire filesystem
MAX_SCAN_DEPTH = 4


class ProjectRegistry:
    """
    Registry for tracking projects using the requirements framework.

    Stores project information in a JSON file at ~/.claude/project_registry.json.
    Uses atomic writes with file locking for safe concurrent access.
    """

    def __init__(self, registry_path: Optional[Path] = None):
        """
        Initialize registry client.

        Args:
            registry_path: Path to registry file. Defaults to ~/.claude/project_registry.json
        """
        self.registry_path = registry_path or DEFAULT_REGISTRY_PATH

    def read(self) -> Dict[str, Any]:
        """
        Read registry with shared lock.

        Returns:
            Registry dict with 'version', 'updated_at', and 'projects' keys.
            Returns empty registry on errors.

        Note:
            Fails open - errors don't propagate.
        """
        if not self.registry_path.exists():
            return {"version": "1.0", "updated_at": 0, "projects": {}}

        try:
            with open(self.registry_path, 'r') as f:
                fcntl.flock(f, fcntl.LOCK_SH)  # Shared lock for reading
                try:
                    registry = json.load(f)
                finally:
                    fcntl.flock(f, fcntl.LOCK_UN)
            return registry
        except json.JSONDecodeError as e:
            get_logger().warning(f"Registry corrupted ({self.registry_path}): {e}")
            return {"version": "1.0", "updated_at": 0, "projects": {}}
        except (OSError, IOError) as e:
            get_logger().warning(f"Registry read error ({self.registry_path}): {e}")
            return {"version": "1.0", "updated_at": 0, "projects": {}}

    def write(self, registry: Dict[str, Any]) -> bool:
        """
        Write registry atomically with exclusive lock.

        Uses atomic write pattern:
        1. Write to temp file with exclusive lock
        2. fsync to ensure data on disk
        3. Atomic rename (POSIX guarantee)

        Args:
            registry: Registry dict to write

        Returns:
            True if write succeeded, False on error

        Note:
            Fails open - errors don't raise.
        """
        # Ensure parent directory exists
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)

        # Update timestamp
        registry["updated_at"] = int(time.time())

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
            get_logger().warning(f"Registry write error ({self.registry_path}): {e}")
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except OSError:
                    pass
            return False

    def scan_for_projects(
        self,
        root_paths: Optional[List[Path]] = None,
        max_depth: int = MAX_SCAN_DEPTH
    ) -> List[str]:
        """
        Scan directories for projects with .claude/requirements.yaml files.

        Args:
            root_paths: Directories to scan. Uses defaults if not specified.
            max_depth: Maximum directory depth to scan.

        Returns:
            List of absolute paths to discovered projects.
        """
        if root_paths is None:
            root_paths = [p for p in DEFAULT_SCAN_PATHS if p.exists()]

        discovered: Set[str] = set()

        for root in root_paths:
            if not root.exists():
                continue
            self._scan_directory(root, discovered, 0, max_depth)

        return sorted(discovered)

    def _scan_directory(
        self,
        directory: Path,
        discovered: Set[str],
        current_depth: int,
        max_depth: int
    ) -> None:
        """
        Recursively scan a directory for requirements configs.

        Args:
            directory: Directory to scan
            discovered: Set to add discovered projects to
            current_depth: Current recursion depth
            max_depth: Maximum recursion depth
        """
        if current_depth > max_depth:
            return

        try:
            # Check for requirements config in this directory
            config_path = directory / ".claude" / "requirements.yaml"
            if config_path.exists():
                discovered.add(str(directory.resolve()))
                # Don't recurse into discovered projects
                return

            # Skip common non-project directories
            skip_dirs = {
                '.git', 'node_modules', 'venv', '.venv', '__pycache__',
                'build', 'dist', '.next', '.cache', 'vendor', 'target'
            }

            # Recurse into subdirectories
            for item in directory.iterdir():
                if item.is_dir() and item.name not in skip_dirs and not item.name.startswith('.'):
                    self._scan_directory(item, discovered, current_depth + 1, max_depth)

        except PermissionError:
            # Skip directories we can't read
            pass
        except OSError as e:
            get_logger().debug(f"Error scanning {directory}: {e}")

    def register_project(
        self,
        project_path: str,
        configured_features: Optional[List[str]] = None,
        has_global_inherit: bool = False
    ) -> bool:
        """
        Register or update a project in the registry.

        Args:
            project_path: Absolute path to project directory
            configured_features: List of enabled feature names
            has_global_inherit: Whether project inherits from global config

        Returns:
            True if registration succeeded
        """
        registry = self.read()
        now = int(time.time())

        project_path = str(Path(project_path).resolve())

        if project_path in registry["projects"]:
            # Update existing entry
            registry["projects"][project_path].update({
                "last_seen": now,
                "configured_features": configured_features or [],
                "has_global_inherit": has_global_inherit,
            })
        else:
            # New entry
            registry["projects"][project_path] = {
                "discovered_at": now,
                "last_seen": now,
                "configured_features": configured_features or [],
                "has_global_inherit": has_global_inherit,
            }

        return self.write(registry)

    def list_projects(self) -> List[Dict[str, Any]]:
        """
        Get all known projects with their metadata.

        Returns:
            List of project info dicts with 'path' key added.
        """
        registry = self.read()
        projects = []

        for path, info in registry.get("projects", {}).items():
            project = info.copy()
            project["path"] = path
            projects.append(project)

        # Sort by last_seen (most recent first)
        projects.sort(key=lambda p: p.get("last_seen", 0), reverse=True)
        return projects

    def get_project(self, project_path: str) -> Optional[Dict[str, Any]]:
        """
        Get info for a specific project.

        Args:
            project_path: Path to project

        Returns:
            Project info dict or None if not found
        """
        registry = self.read()
        project_path = str(Path(project_path).resolve())
        info = registry.get("projects", {}).get(project_path)
        if info:
            info = info.copy()
            info["path"] = project_path
        return info

    def prune_stale(self) -> int:
        """
        Remove projects where the config file no longer exists.

        Returns:
            Number of entries removed.
        """
        registry = self.read()
        projects = registry.get("projects", {})

        to_remove = []
        for path in projects:
            config_path = Path(path) / ".claude" / "requirements.yaml"
            if not config_path.exists():
                to_remove.append(path)

        for path in to_remove:
            del registry["projects"][path]

        if to_remove:
            self.write(registry)

        return len(to_remove)

    def update_and_scan(self, scan_paths: Optional[List[Path]] = None) -> Dict[str, Any]:
        """
        Scan for projects and update registry, returning summary.

        Args:
            scan_paths: Paths to scan (uses defaults if None)

        Returns:
            Dict with 'new', 'updated', 'removed' counts
        """
        registry = self.read()
        existing_paths = set(registry.get("projects", {}).keys())

        # Scan for projects
        discovered = set(self.scan_for_projects(scan_paths))

        # Categorize
        new_projects = discovered - existing_paths
        still_valid = discovered & existing_paths
        removed = existing_paths - discovered

        # Register new projects
        from feature_catalog import detect_configured_features
        from config import RequirementsConfig

        for path in new_projects:
            try:
                config_obj = RequirementsConfig(project_dir=path)
                raw_config = config_obj.get_raw_config()
                features = detect_configured_features(raw_config)
                enabled = [f for f, e in features.items() if e]
                has_inherit = raw_config.get("inherit", False)
                self.register_project(path, enabled, has_inherit)
            except Exception as e:
                get_logger().debug(f"Error loading config for {path}: {e}")
                self.register_project(path, [], False)

        # Re-read registry after registrations to get updated state
        registry = self.read()

        # Update timestamps for still-valid projects
        now = int(time.time())
        for path in still_valid:
            if path in registry["projects"]:
                registry["projects"][path]["last_seen"] = now

        # Remove stale entries
        for path in removed:
            if path in registry["projects"]:
                del registry["projects"][path]

        # Only write if we have timestamp updates or removals
        if still_valid or removed:
            self.write(registry)

        return {
            "new": len(new_projects),
            "updated": len(still_valid),
            "removed": len(removed),
            "total": len(discovered),
        }
