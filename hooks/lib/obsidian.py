"""Obsidian CLI integration for session logging.

Provides ObsidianClient (CLI wrapper) and ObsidianSessionLogger
(session lifecycle orchestrator) for logging Claude Code sessions
to Obsidian notes.

Requires Obsidian desktop app to be running with CLI enabled.
All operations are fail-open — errors are logged but never block execution.
"""

import subprocess
import shutil
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
        args = ["create", f'name="{name}"', f"path={path}/"]
        if content:
            args.append(f'content="{content}"')
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
        result = self._run("append", f'file="{file}"', f'content="{content}"')
        return result is not None

    def prepend(self, file, content):
        """Prepend content to an existing note.

        Args:
            file: Note name (wikilink style, without .md)
            content: Text to prepend

        Returns:
            True on success, False on failure.
        """
        result = self._run("prepend", f'file="{file}"', f'content="{content}"')
        return result is not None

    def read(self, file):
        """Read note content.

        Args:
            file: Note name (wikilink style, without .md)

        Returns:
            Note content as string, or None on failure.
        """
        result = self._run("read", f'file="{file}"')
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
                "properties:set", f'file="{file}"', f"{key}={value}"
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
            cmd.append(f'vault="{self.vault}"')

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
