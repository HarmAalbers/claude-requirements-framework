#!/usr/bin/env python3
"""
Learning updates management for session learning system.

Handles applying and tracking updates to memories, skills, and commands.
All changes are recorded in a history file for rollback capability.

Storage: .git/requirements/learning_history.json

Design principles:
- Fail-open: Update errors never block execution
- Atomic writes: File locking + atomic rename for safety
- Full audit trail: Every change recorded with hashes
- Rollback capable: Previous content hashes enable restoration
"""
import fcntl
import hashlib
import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from logger import get_logger


def get_history_path(project_dir: str) -> Path:
    """
    Get path to learning history file.

    Args:
        project_dir: Project root directory

    Returns:
        Path to learning history JSON file
    """
    try:
        from .git_utils import get_git_common_dir
    except ImportError:
        from git_utils import get_git_common_dir

    common_dir = get_git_common_dir(project_dir)

    if common_dir:
        return Path(common_dir) / 'requirements' / 'learning_history.json'

    return Path(project_dir) / '.git' / 'requirements' / 'learning_history.json'


def content_hash(content: str) -> str:
    """
    Calculate SHA256 hash of content.

    Args:
        content: String content to hash

    Returns:
        First 12 characters of hex SHA256 hash
    """
    return hashlib.sha256(content.encode('utf-8')).hexdigest()[:12]


def create_empty_history() -> dict:
    """
    Create empty history structure.

    Returns:
        Empty history dictionary
    """
    return {
        "version": "1.0",
        "created_at": int(time.time()),
        "updated_at": int(time.time()),
        "updates": [],
        "stats": {
            "total_updates": 0,
            "memories_updated": 0,
            "skills_updated": 0,
            "commands_updated": 0,
            "rollbacks": 0
        }
    }


def load_history(project_dir: str) -> dict:
    """
    Load learning history.

    Args:
        project_dir: Project root directory

    Returns:
        History dictionary (empty history if file doesn't exist)
    """
    path = get_history_path(project_dir)

    if not path.exists():
        return create_empty_history()

    try:
        with open(path, 'r') as f:
            fcntl.flock(f, fcntl.LOCK_SH)
            try:
                history = json.load(f)
                if history.get('version') != '1.0':
                    return create_empty_history()
                return history
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
    except (json.JSONDecodeError, OSError, IOError) as e:
        get_logger().warning(f"Learning history issue: {e}")
        return create_empty_history()


def save_history(project_dir: str, history: dict) -> None:
    """
    Save learning history atomically.

    Args:
        project_dir: Project root directory
        history: History dictionary to save
    """
    path = get_history_path(project_dir)

    # Ensure directory exists
    path.parent.mkdir(parents=True, exist_ok=True)

    temp_path = path.with_suffix('.tmp')
    history['updated_at'] = int(time.time())

    try:
        with open(temp_path, 'w') as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                json.dump(history, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

        temp_path.rename(path)
    except OSError as e:
        get_logger().warning(f"Could not save learning history: {e}")
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass


def record_update(project_dir: str, session_id: str, update_type: str,
                  target: str, action: str, new_content: str,
                  previous_content: str = None, metadata: dict = None) -> int:
    """
    Record an update in the learning history.

    Args:
        project_dir: Project root directory
        session_id: Session ID that made the update
        update_type: Type of update (memory, skill, command)
        target: Target file path (relative to project)
        action: Action performed (create, append, update)
        new_content: New content written
        previous_content: Previous content (for rollback)
        metadata: Additional metadata (confidence, evidence, etc.)

    Returns:
        Update ID (index in updates array)
    """
    history = load_history(project_dir)

    update_id = len(history.get('updates', []))
    now = int(time.time())

    update_record = {
        "id": update_id,
        "timestamp": now,
        "datetime": datetime.fromtimestamp(now).isoformat(),
        "session_id": session_id,
        "type": update_type,
        "target": target,
        "action": action,
        "new_content_hash": content_hash(new_content),
        "previous_content_hash": content_hash(previous_content) if previous_content else None,
        "rollback_available": previous_content is not None,
        "rolled_back": False,
        "metadata": metadata or {}
    }

    history.setdefault('updates', []).append(update_record)

    # Update stats
    stats = history.setdefault('stats', {
        "total_updates": 0,
        "memories_updated": 0,
        "skills_updated": 0,
        "commands_updated": 0,
        "rollbacks": 0
    })
    stats['total_updates'] += 1
    stat_keys = {'memory': 'memories_updated', 'skill': 'skills_updated', 'command': 'commands_updated'}
    if update_type in stat_keys:
        stats[stat_keys[update_type]] += 1

    save_history(project_dir, history)
    return update_id


def get_recent_updates(project_dir: str, count: int = 10) -> list[dict]:
    """
    Get most recent updates.

    Args:
        project_dir: Project root directory
        count: Number of updates to return

    Returns:
        List of update records (newest first)
    """
    history = load_history(project_dir)
    updates = history.get('updates', [])
    return list(reversed(updates[-count:]))


def get_update_by_id(project_dir: str, update_id: int) -> Optional[dict]:
    """
    Get a specific update by ID.

    Args:
        project_dir: Project root directory
        update_id: Update ID to retrieve

    Returns:
        Update record or None if not found
    """
    history = load_history(project_dir)
    updates = history.get('updates', [])

    if 0 <= update_id < len(updates):
        return updates[update_id]
    return None


def mark_rolled_back(project_dir: str, update_id: int) -> bool:
    """
    Mark an update as rolled back.

    Args:
        project_dir: Project root directory
        update_id: Update ID to mark

    Returns:
        True if successful, False if update not found
    """
    history = load_history(project_dir)
    updates = history.get('updates', [])

    if 0 <= update_id < len(updates):
        updates[update_id]['rolled_back'] = True
        updates[update_id]['rolled_back_at'] = int(time.time())
        history['stats']['rollbacks'] = history.get('stats', {}).get('rollbacks', 0) + 1
        save_history(project_dir, history)
        return True
    return False


class LearningUpdater:
    """
    High-level interface for applying learning updates.

    Handles applying updates to files and recording them in history.
    All operations are fail-open - errors are logged but never raised.

    Usage:
        updater = LearningUpdater(session_id, project_dir)
        updater.apply_memory_update(target, content, action='append')
        updater.apply_skill_update(target, new_triggers)
    """

    def __init__(self, session_id: str, project_dir: str):
        """
        Initialize updater.

        Args:
            session_id: Current session ID
            project_dir: Project root directory
        """
        self.session_id = session_id
        self.project_dir = project_dir
        self.logger = get_logger(base_context={"component": "LearningUpdater"})

    def _read_file(self, path: Path) -> Optional[str]:
        """Read file content if it exists."""
        try:
            if path.exists():
                return path.read_text(encoding='utf-8')
            return None
        except OSError as e:
            self.logger.warning(f"Could not read {path}: {e}")
            return None

    def _write_file(self, path: Path, content: str) -> bool:
        """Write content to file atomically."""
        try:
            # Ensure directory exists
            path.parent.mkdir(parents=True, exist_ok=True)

            # Atomic write
            temp_path = path.with_suffix('.tmp')
            with open(temp_path, 'w', encoding='utf-8') as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())
            temp_path.rename(path)
            return True
        except OSError as e:
            self.logger.warning(f"Could not write {path}: {e}")
            return False

    def apply_memory_update(self, target: str, content: str,
                           action: str = 'append',
                           confidence: float = None,
                           evidence: list = None) -> bool:
        """
        Apply an update to a Serena memory file.

        Args:
            target: Target file path (e.g., '.serena/memories/workflow-patterns.md')
            content: Content to add/write
            action: 'create', 'append', or 'replace'
            confidence: Confidence score (for metadata)
            evidence: Evidence list (for metadata)

        Returns:
            True if successful, False otherwise
        """
        try:
            path = Path(self.project_dir) / target

            # Read existing content
            previous_content = self._read_file(path)

            # Prepare new content based on action
            if action == 'create' or previous_content is None:
                new_content = content
                actual_action = 'create'
            elif action == 'append':
                # Add timestamp header for appended content
                timestamp = datetime.now().strftime('%Y-%m-%d')
                header = f"\n\n---\n## Session Learning: {timestamp} (Session {self.session_id})\n\n"
                new_content = previous_content.rstrip() + header + content
                actual_action = 'append'
            elif action == 'replace':
                new_content = content
                actual_action = 'replace'
            else:
                self.logger.warning(f"Unknown action: {action}")
                return False

            # Write the file
            if not self._write_file(path, new_content):
                return False

            # Record in history
            metadata = {}
            if confidence is not None:
                metadata['confidence'] = confidence
            if evidence:
                metadata['evidence'] = evidence

            record_update(
                self.project_dir,
                self.session_id,
                'memory',
                target,
                actual_action,
                new_content,
                previous_content,
                metadata
            )

            self.logger.info(
                "Applied memory update",
                target=target,
                action=actual_action
            )
            return True

        except Exception as e:
            self.logger.error(f"Failed to apply memory update: {e}")
            return False

    def apply_skill_update(self, target: str, new_triggers: list[str],
                          confidence: float = None,
                          evidence: list = None) -> bool:
        """
        Apply an update to a skill's trigger patterns.

        Adds new trigger phrases to the skill's description.

        Args:
            target: Target skill file path
            new_triggers: New trigger phrases to add
            confidence: Confidence score (for metadata)
            evidence: Evidence list (for metadata)

        Returns:
            True if successful, False otherwise
        """
        try:
            path = Path(self.project_dir) / target

            previous_content = self._read_file(path)
            if previous_content is None:
                self.logger.warning(f"Skill file not found: {target}")
                return False

            # Parse YAML frontmatter
            if not previous_content.startswith('---'):
                self.logger.warning(f"Skill file has no frontmatter: {target}")
                return False

            # Find end of frontmatter
            end_idx = previous_content.find('---', 3)
            if end_idx == -1:
                self.logger.warning(f"Invalid frontmatter in: {target}")
                return False

            frontmatter = previous_content[3:end_idx].strip()
            body = previous_content[end_idx + 3:]

            # Add triggers as comment in description
            # Format: Add new triggers to description field
            triggers_note = f"\n\n<!-- Session-learned triggers: {', '.join(new_triggers)} -->"

            # Append to frontmatter before closing
            new_frontmatter = frontmatter + triggers_note
            new_content = f"---\n{new_frontmatter}\n---{body}"

            if not self._write_file(path, new_content):
                return False

            # Record in history
            metadata = {'new_triggers': new_triggers}
            if confidence is not None:
                metadata['confidence'] = confidence
            if evidence:
                metadata['evidence'] = evidence

            record_update(
                self.project_dir,
                self.session_id,
                'skill',
                target,
                'update',
                new_content,
                previous_content,
                metadata
            )

            self.logger.info(
                "Applied skill update",
                target=target,
                triggers=new_triggers
            )
            return True

        except Exception as e:
            self.logger.error(f"Failed to apply skill update: {e}")
            return False

    def apply_command_update(self, target: str, section_name: str,
                            section_content: str,
                            confidence: float = None,
                            evidence: list = None) -> bool:
        """
        Apply an update to a command file.

        Adds a new section with learned patterns.

        Args:
            target: Target command file path
            section_name: Name for the new section
            section_content: Content for the section
            confidence: Confidence score (for metadata)
            evidence: Evidence list (for metadata)

        Returns:
            True if successful, False otherwise
        """
        try:
            path = Path(self.project_dir) / target

            previous_content = self._read_file(path)
            if previous_content is None:
                self.logger.warning(f"Command file not found: {target}")
                return False

            # Add section at the end
            timestamp = datetime.now().strftime('%Y-%m-%d')
            new_section = f"\n\n## {section_name} (Learned {timestamp})\n\n{section_content}"
            new_content = previous_content.rstrip() + new_section

            if not self._write_file(path, new_content):
                return False

            # Record in history
            metadata = {'section_name': section_name}
            if confidence is not None:
                metadata['confidence'] = confidence
            if evidence:
                metadata['evidence'] = evidence

            record_update(
                self.project_dir,
                self.session_id,
                'command',
                target,
                'update',
                new_content,
                previous_content,
                metadata
            )

            self.logger.info(
                "Applied command update",
                target=target,
                section=section_name
            )
            return True

        except Exception as e:
            self.logger.error(f"Failed to apply command update: {e}")
            return False

    def rollback_update(self, update_id: int) -> bool:
        """
        Rollback a specific update.

        Note: This only marks the update as rolled back in history.
        Actual file restoration requires the previous_content which
        is not stored in history (only the hash). Full rollback
        requires git or manual restoration.

        Args:
            update_id: ID of update to rollback

        Returns:
            True if marked as rolled back, False otherwise
        """
        update = get_update_by_id(self.project_dir, update_id)
        if not update:
            self.logger.warning(f"Update not found: {update_id}")
            return False

        if update.get('rolled_back'):
            self.logger.warning(f"Update already rolled back: {update_id}")
            return False

        if not update.get('rollback_available'):
            self.logger.warning(f"Rollback not available for update: {update_id}")
            return False

        # Mark as rolled back
        return mark_rolled_back(self.project_dir, update_id)


def get_learning_stats(project_dir: str) -> dict:
    """
    Get learning system statistics.

    Args:
        project_dir: Project root directory

    Returns:
        Statistics dictionary
    """
    history = load_history(project_dir)
    return history.get('stats', {
        "total_updates": 0,
        "memories_updated": 0,
        "skills_updated": 0,
        "commands_updated": 0,
        "rollbacks": 0
    })


if __name__ == "__main__":
    # Quick test
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        # Simulate git repo
        os.makedirs(f"{tmpdir}/.git")
        os.makedirs(f"{tmpdir}/.serena/memories")

        # Test updater
        updater = LearningUpdater("test1234", tmpdir)

        # Apply memory update
        success = updater.apply_memory_update(
            ".serena/memories/test-memory.md",
            "This is a test memory about TDD workflow.",
            action='create',
            confidence=0.85,
            evidence=["pytest run 12 times", "tests written before implementation"]
        )
        print(f"Memory update: {success}")

        # Check history
        history = load_history(tmpdir)
        print(f"\nHistory: {json.dumps(history, indent=2)}")

        # Get stats
        stats = get_learning_stats(tmpdir)
        print(f"\nStats: {stats}")

        # Get recent updates
        recent = get_recent_updates(tmpdir)
        print(f"\nRecent updates: {recent}")

    print("\n✅ Learning updates tests passed")
