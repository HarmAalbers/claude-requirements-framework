"""Obsidian CLI integration for session logging.

Provides ObsidianClient (CLI wrapper) and ObsidianSessionLogger
(session lifecycle orchestrator) for logging Claude Code sessions
to Obsidian notes.

Requires Obsidian desktop app to be running with CLI enabled.
All operations are fail-open — errors are logged but never block execution.
"""

import subprocess
import shutil
from datetime import datetime
from pathlib import Path
from logger import get_logger


class ObsidianClient:
    """Thin wrapper around the `obsidian` CLI binary.

    All methods return bool or None on failure — never raise.
    Requires Obsidian to be running for commands to work.
    """

    def __init__(self, vault=None, timeout=5):
        self.vault = vault
        self.timeout = timeout
        self._available = None  # Lazy cache

    def is_available(self):
        """Check if obsidian CLI is in PATH."""
        if self._available is None:
            self._available = shutil.which("obsidian") is not None
        return self._available

    def create_note(self, name, path, content=""):
        """Create a new note in the vault.

        Args:
            name: Note title (without .md extension)
            path: Folder path within the vault (e.g. "Claude/Sessions/")
            content: Initial markdown content

        Returns:
            True on success, False on failure.
        """
        args = ["create", f'name={name}', f"path={path}/"]
        if content:
            args.append(f'content={content}')
        result = self._run(*args)
        return result is not None

    def append(self, file, content):
        """Append content to an existing note.

        Args:
            file: Note name (wikilink style, without .md)
            content: Text to append

        Returns:
            True on success, False on failure.
        """
        result = self._run("append", f'file={file}', f'content={content}')
        return result is not None

    def prepend(self, file, content):
        """Prepend content to an existing note.

        Args:
            file: Note name (wikilink style, without .md)
            content: Text to prepend

        Returns:
            True on success, False on failure.
        """
        result = self._run("prepend", f'file={file}', f'content={content}')
        return result is not None

    def read(self, file):
        """Read note content.

        Args:
            file: Note name (wikilink style, without .md)

        Returns:
            Note content as string, or None on failure.
        """
        result = self._run("read", f'file={file}')
        if result is not None:
            return result.stdout.strip()
        return None

    def set_properties(self, file, **props):
        """Set YAML frontmatter properties on a note.

        Args:
            file: Note name (wikilink style, without .md)
            **props: Key-value pairs to set as properties

        Returns:
            True if all properties set successfully, False otherwise.
        """
        logger = get_logger()
        success = True
        for key, value in props.items():
            result = self._run(
                "properties:set", f'file={file}', f"{key}={value}"
            )
            if result is None:
                logger.debug(
                    "Failed to set property",
                    file=file, key=key, value=str(value),
                )
                success = False
        return success

    def _run(self, *args):
        """Execute an obsidian CLI command with fail-open error handling.

        Args:
            *args: Command arguments (e.g. "create", 'name="Title"')

        Returns:
            subprocess.CompletedProcess on success, None on any failure.
        """
        if not self.is_available():
            return None

        logger = get_logger()
        cmd = ["obsidian"]
        cmd.extend(args)

        if self.vault:
            cmd.append(f'vault={self.vault}')

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
            if result.returncode != 0:
                logger.debug(
                    "Obsidian CLI command failed",
                    args=str(args),
                    returncode=result.returncode,
                    stderr=result.stderr[:200] if result.stderr else "",
                )
                return None
            return result
        except FileNotFoundError:
            logger.debug("Obsidian CLI not found in PATH")
            self._available = False
            return None
        except subprocess.TimeoutExpired:
            logger.debug(
                "Obsidian CLI timed out",
                args=str(args),
                timeout=self.timeout,
            )
            return None
        except Exception as e:
            logger.debug(
                "Obsidian CLI unexpected error",
                args=str(args),
                error=str(e),
            )
            return None


class ObsidianSessionLogger:
    """Manages the session note lifecycle in Obsidian.

    Creates per-session detail notes with YAML frontmatter and a
    session index/ledger note. Updates notes throughout the session
    lifecycle (start → periodic → end).

    All operations are fail-open — errors never block execution.
    """

    def __init__(self, config):
        """Initialize from RequirementsConfig.

        Args:
            config: RequirementsConfig instance for reading hook config.
        """
        self.enabled = config.get_hook_config('obsidian', 'enabled', False)
        self.client = ObsidianClient(
            vault=config.get_hook_config('obsidian', 'vault', None),
            timeout=config.get_hook_config('obsidian', 'timeout', 5),
        )
        self.folder = config.get_hook_config(
            'obsidian', 'session_folder', 'Claude/Sessions'
        )
        self.index_note = config.get_hook_config(
            'obsidian', 'index_note', 'Claude/Sessions Log'
        )

    def _note_name(self, session_id, project_dir):
        """Generate note name for a session.

        Format: 'YYYY-MM-DD <project> <session_id>'

        Args:
            session_id: Short session ID (e.g. 'abc12345')
            project_dir: Full project path

        Returns:
            Note name string.
        """
        date_str = datetime.now().strftime("%Y-%m-%d")
        project_name = Path(project_dir).name
        return f"{date_str} {project_name} {session_id}"

    def on_session_start(self, session_id, project_dir, branch):
        """Create session detail note and add ledger row.

        Args:
            session_id: Short session ID
            project_dir: Full project path
            branch: Git branch name
        """
        if not self.enabled:
            return

        logger = get_logger()
        note_name = self._note_name(session_id, project_dir)
        project_name = Path(project_dir).name
        now = datetime.now()
        time_str = now.strftime("%H:%M")

        # Build initial note content
        content = (
            f"# Session {session_id}\\n\\n"
            f"**Project**: [[{project_name}]]\\n"
            f"**Branch**: `{branch}`\\n"
            f"**Started**: {now.strftime('%Y-%m-%d %H:%M')}\\n\\n"
            f"## Timeline\\n\\n"
            f"- \U0001f7e2 **{time_str}** \u2014 Session started\\n\\n"
            f"## Git Activity\\n\\n"
            f"_No commits yet_\\n\\n"
            f"## Requirements\\n\\n"
            f"_No requirements satisfied yet_\\n\\n"
            f"## Skills & Agents\\n\\n"
            f"_None used yet_"
        )

        # Create the detail note
        created = self.client.create_note(note_name, self.folder, content)
        if not created:
            logger.debug("Failed to create session note", note=note_name)
            return

        # Set YAML frontmatter properties
        self.client.set_properties(
            note_name,
            type="claude-session",
            session_id=session_id,
            project=project_name,
            project_path=project_dir,
            branch=branch,
            status="active",
            started=now.strftime("%Y-%m-%dT%H:%M:%S"),
            commits=0,
            files_changed=0,
            lines_added=0,
            lines_removed=0,
            tools_used=0,
            requirements_satisfied=0,
        )

        # Ensure index note exists and add ledger row
        self._ensure_index_note()
        ledger_row = self._build_ledger_row(
            date=now.strftime("%Y-%m-%d"),
            project=project_name,
            branch=branch,
            duration="-",
            commits="0",
            files="0",
            status="\u23f3",
            link=note_name,
        )
        self.client.prepend(self.index_note, ledger_row)

        logger.debug("Obsidian session note created", note=note_name)

    def on_update(self, session_id, project_dir, event_type, detail):
        """Append a timeline entry to the session detail note.

        Args:
            session_id: Short session ID
            project_dir: Full project path
            event_type: 'commit' or 'requirement'
            detail: Human-readable description of the event
        """
        if not self.enabled:
            return

        note_name = self._note_name(session_id, project_dir)
        time_str = datetime.now().strftime("%H:%M")

        if event_type == "commit":
            icon = "\U0001f4dd"
        elif event_type == "requirement":
            icon = "\u2705"
        else:
            icon = "\u2022"

        entry = f"- {icon} **{time_str}** \u2014 {detail}\\n"
        self.client.append(note_name, entry)

    def on_session_end(self, session_id, project_dir, metrics_summary):
        """Finalize session note with complete metrics.

        Args:
            session_id: Short session ID
            project_dir: Full project path
            metrics_summary: Dict from SessionMetrics.get_summary()
        """
        if not self.enabled:
            return

        logger = get_logger()
        note_name = self._note_name(session_id, project_dir)
        now = datetime.now()

        # Calculate duration
        duration_seconds = metrics_summary.get('duration_seconds') or 0
        duration_minutes = max(1, duration_seconds // 60)

        # Update frontmatter properties
        self.client.set_properties(
            note_name,
            status="complete",
            ended=now.strftime("%Y-%m-%dT%H:%M:%S"),
            duration_minutes=duration_minutes,
            tools_used=metrics_summary.get('tool_uses', 0),
            requirements_satisfied=metrics_summary.get('requirements_satisfied', 0),
        )

        # Append final timeline entry
        time_str = now.strftime("%H:%M")
        self.client.append(
            note_name,
            f"- \U0001f534 **{time_str}** \u2014 Session ended ({duration_minutes}m)\\n"
        )

        logger.debug("Obsidian session note finalized", note=note_name)

    def _ensure_index_note(self):
        """Create the index/ledger note if it doesn't exist."""
        content = self.client.read(self.index_note)
        if content is None:
            header = (
                "# Claude Sessions Log\\n\\n"
                "| Date | Project | Branch | Duration | Commits | Files | Status | Link |\\n"
                "|------|---------|--------|----------|---------|-------|--------|------|"
            )
            # Extract folder and name from index_note path
            parts = self.index_note.rsplit("/", 1)
            if len(parts) == 2:
                folder, name = parts
            else:
                folder, name = "", parts[0]
            self.client.create_note(name, folder, header)

    def _build_ledger_row(self, date, project, branch, duration,
                          commits, files, status, link):
        """Build a markdown table row for the ledger.

        Returns:
            Single table row string.
        """
        # Truncate branch for readability
        short_branch = branch[:20] + "..." if len(branch) > 23 else branch
        return (
            f"| {date} | {project} | {short_branch} | "
            f"{duration} | {commits} | {files} | "
            f"{status} | [[{link}]] |\\n"
        )
