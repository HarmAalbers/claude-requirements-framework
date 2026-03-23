"""Obsidian CLI integration for session logging.

Provides ObsidianClient (CLI wrapper) and ObsidianSessionLogger
(session lifecycle orchestrator) for logging Claude Code sessions
to Obsidian notes.

Requires Obsidian desktop app to be running with CLI enabled.
All operations are fail-open — errors are logged but never block execution.

Requires Dataview plugin for auto-updating session ledger (default).
Legacy markdown table format available via ledger_format: "table".
"""

import json
import os
import subprocess
import shutil
import sys
import textwrap
from datetime import datetime
from pathlib import Path
from logger import get_logger


# Dataview query for the auto-updating session ledger.
# Renders a live table from session note frontmatter — no manual writes needed.
DATAVIEW_LEDGER_QUERY = (
    "# Claude Sessions Log\\n\\n"
    "```dataview\\n"
    "TABLE WITHOUT ID\\n"
    "  file.link as \\\"Session\\\",\\n"
    "  dateformat(started, \\\"yyyy-MM-dd HH:mm\\\") as \\\"Started\\\",\\n"
    "  project as \\\"Project\\\",\\n"
    "  branch as \\\"Branch\\\",\\n"
    "  duration_minutes + \\\"m\\\" as \\\"Duration\\\",\\n"
    "  commits as \\\"Commits\\\",\\n"
    "  files_changed as \\\"Files\\\",\\n"
    "  choice(status = \\\"complete\\\", \\\"\\u2705\\\", \\\"\\u23f3\\\") as \\\"Status\\\"\\n"
    "FROM #claude-session\\n"
    "WHERE type = \\\"claude-session\\\"\\n"
    "SORT started DESC\\n"
    "LIMIT 50\\n"
    "```"
)


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

        Tries batch setting via eval first (single CLI call), falling
        back to individual property:set calls if eval fails.

        Args:
            file: Note name (wikilink style, without .md)
            **props: Key-value pairs to set as properties

        Returns:
            True if all properties set successfully, False otherwise.
        """
        if self.set_properties_batch(file, **props):
            return True
        # Fall back to individual calls
        return self._set_properties_individual(file, **props)

    def set_properties_batch(self, file, **props):
        """Set multiple YAML frontmatter properties in one CLI call via eval.

        Uses Obsidian's JS API (app.fileManager.processFrontMatter) to set
        all properties atomically in a single subprocess invocation.

        Args:
            file: Note name (wikilink style, without .md)
            **props: Key-value pairs to set as properties

        Returns:
            True on success, False on failure.
        """
        if not props:
            return True

        js_assignments = []
        for key, value in props.items():
            js_assignments.append(f'fm["{_escape_js(key)}"] = {json.dumps(value)};')

        basename = _escape_js(file)
        js_code = (
            f'const files = app.vault.getMarkdownFiles()'
            f'.filter(f => f.basename === "{basename}");'
            f'if (files.length > 0) {{'
            f'await app.fileManager.processFrontMatter(files[0], (fm) => {{'
            f'{"".join(js_assignments)}'
            f'}});'
            f'}}'
        )
        result = self._run("eval", f'code={js_code}')
        return result is not None

    def _set_properties_individual(self, file, **props):
        """Set properties one at a time via property:set CLI calls.

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
            # Obsidian CLI sometimes returns exit code 0 with error on stdout
            if result.stdout and result.stdout.strip().startswith("Error:"):
                logger.debug(
                    "Obsidian CLI returned error on stdout",
                    args=str(args),
                    stdout=result.stdout.strip()[:200],
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


def _escape_js(s):
    """Escape a string for safe interpolation into JavaScript code.

    Handles quotes, backslashes, and newlines.

    Args:
        s: String to escape

    Returns:
        Escaped string safe for JS string literals.
    """
    s = str(s)
    s = s.replace("\\", "\\\\")
    s = s.replace('"', '\\"')
    s = s.replace("'", "\\'")
    s = s.replace("\n", "\\n")
    s = s.replace("\r", "\\r")
    return s


class ObsidianSessionLogger:
    """Manages the session note lifecycle in Obsidian.

    Creates per-session detail notes with YAML frontmatter and a
    session index/ledger note. Updates notes throughout the session
    lifecycle (start → periodic → end).

    Supports two ledger formats:
    - "dataview" (default): Auto-updating Dataview TABLE query
    - "table": Legacy manually-maintained markdown table

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
        self.ledger_format = config.get_hook_config(
            'obsidian', 'ledger_format', 'dataview'
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
        """Create session detail note and update ledger.

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

        # Set YAML frontmatter properties (including enriched metadata)
        self.client.set_properties(
            note_name,
            type="claude-session",
            tags=["claude-session", f"project/{project_name}"],
            aliases=[session_id],
            cssclasses=["claude-session"],
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

        # Ensure index note exists
        self._ensure_index_note()

        # In legacy table mode, prepend a ledger row
        if self.ledger_format == "table":
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

    def finalize_in_background(self, session_id, project_dir, metrics_summary):
        """Spawn a detached background process to finalize the session note.

        Collects all data needed for finalization, serializes it as JSON,
        and spawns a subprocess that performs the Obsidian CLI calls after
        this hook returns. This avoids the SessionEnd hook being killed
        by Claude Code's exit grace period.

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

        # Build the payload with everything the background process needs
        payload = {
            'note_name': note_name,
            'vault': self.client.vault,
            'timeout': self.client.timeout,
            'status': 'complete',
            'ended': now.strftime("%Y-%m-%dT%H:%M:%S"),
            'duration_minutes': duration_minutes,
            'tools_used': metrics_summary.get('tool_uses', 0),
            'requirements_satisfied': metrics_summary.get('requirements_satisfied', 0),
            'time_str': now.strftime("%H:%M"),
        }

        # Inline script that imports ObsidianClient and does the finalization
        lib_dir = str(Path(__file__).parent)
        script = textwrap.dedent(f"""\
            import json, sys
            sys.path.insert(0, {lib_dir!r})
            from obsidian import ObsidianClient

            data = json.loads(sys.stdin.read())
            client = ObsidianClient(vault=data.get('vault'), timeout=data.get('timeout', 5))

            client.set_properties(
                data['note_name'],
                status=data['status'],
                ended=data['ended'],
                duration_minutes=data['duration_minutes'],
                tools_used=data['tools_used'],
                requirements_satisfied=data['requirements_satisfied'],
            )

            entry = "- \\U0001f534 **" + data['time_str'] + "** \\u2014 Session ended (" + str(data['duration_minutes']) + "m)\\\\n"
            client.append(data['note_name'], entry)
        """)

        try:
            devnull = open(os.devnull, 'w')
            proc = subprocess.Popen(
                [sys.executable, '-c', script],
                stdin=subprocess.PIPE,
                stdout=devnull,
                stderr=devnull,
                start_new_session=True,
            )
            proc.stdin.write(json.dumps(payload).encode())
            proc.stdin.close()
            # Do NOT wait — fire and forget
            logger.debug(
                "Obsidian finalization spawned in background",
                note=note_name, pid=proc.pid,
            )
        except Exception as e:
            logger.debug(
                "Failed to spawn Obsidian background finalization (fail-open)",
                error=str(e),
            )

    def _ensure_index_note(self):
        """Create or migrate the index/ledger note.

        In Dataview mode: creates a note with a Dataview TABLE query that
        auto-renders session data from frontmatter. If an existing legacy
        table note is found, it is migrated (backed up as "(legacy)").

        In table mode: creates a note with a markdown table header.
        """
        logger = get_logger()
        # Extract folder and name from index_note path
        parts = self.index_note.rsplit("/", 1)
        if len(parts) == 2:
            folder, name = parts
        else:
            folder, name = "", parts[0]

        content = self.client.read(self.index_note)

        if self.ledger_format == "dataview":
            if content is None:
                # No note exists — create with Dataview query
                created = self.client.create_note(
                    name, folder, DATAVIEW_LEDGER_QUERY
                )
                if not created:
                    logger.debug(
                        "Failed to create Dataview index note",
                        note=self.index_note,
                    )
            elif "| Date |" in content and "dataview" not in content:
                # Legacy table note detected — migrate
                self._migrate_legacy_index(folder, name, content)
            # else: Dataview note already exists, nothing to do
        else:
            # Legacy table mode
            if content is None:
                header = (
                    "# Claude Sessions Log\\n\\n"
                    "| Date | Project | Branch | Duration | Commits "
                    "| Files | Status | Link |\\n"
                    "|------|---------|--------|----------|---------|"
                    "-------|--------|------|"
                )
                created = self.client.create_note(name, folder, header)
                if not created:
                    logger.debug(
                        "Failed to create index note",
                        note=self.index_note,
                    )

    def _migrate_legacy_index(self, folder, name, old_content):
        """Migrate a legacy markdown table index note to Dataview format.

        Backs up the old note as "{name} (legacy)" and creates a new
        Dataview-powered index note in its place.

        Args:
            folder: Folder path within the vault
            name: Note name (without extension)
            old_content: Content of the existing legacy note
        """
        logger = get_logger()

        # Back up old note
        legacy_name = f"{name} (legacy)"
        escaped_content = old_content.replace("\\", "\\\\").replace("\n", "\\n")
        backed_up = self.client.create_note(legacy_name, folder, escaped_content)
        if not backed_up:
            logger.debug(
                "Failed to back up legacy index note, skipping migration",
                note=self.index_note,
            )
            return

        # Overwrite the index note with Dataview content using the
        # CLI's 'overwrite' flag
        args = [
            "create",
            f'name={name}',
            f"path={folder}/",
            f'content={DATAVIEW_LEDGER_QUERY}',
            "overwrite",
        ]
        result = self.client._run(*args)
        if result is not None:
            logger.debug(
                "Migrated legacy index note to Dataview format",
                note=self.index_note,
                backup=legacy_name,
            )
        else:
            logger.debug(
                "Failed to overwrite index note with Dataview content",
                note=self.index_note,
            )

    def _build_ledger_row(self, date, project, branch, duration,
                          commits, files, status, link):
        """Build a markdown table row for the legacy ledger.

        Only used when ledger_format is "table".

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
