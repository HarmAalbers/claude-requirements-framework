#!/usr/bin/env python3
"""
Configuration utilities for requirements framework.

This module contains standalone helper functions used by config.py and other
modules. These utilities handle:
- Trigger matching for tool invocations
- Config file I/O (YAML)
- Dictionary merging for config cascades
"""
import os
import re
import tempfile
from pathlib import Path

from logger import get_logger


def matches_trigger(tool_name: str, tool_input: dict, triggers: list) -> bool:
    """
    Check if a tool invocation matches any configured trigger.

    Supports two trigger formats:
    1. Simple string: 'Edit' - matches tool name exactly
    2. Complex object: {tool: 'Bash', command_pattern: 'git\\s+commit'} - matches tool + command regex

    Args:
        tool_name: Name of the tool being invoked (e.g., 'Edit', 'Bash')
        tool_input: Tool input parameters (for Bash, includes 'command')
        triggers: List of triggers from config (strings or dicts)

    Returns:
        True if tool matches any trigger, False otherwise

    Examples:
        # Simple trigger
        matches_trigger('Edit', {}, ['Edit', 'Write'])  # True

        # Complex trigger with command pattern
        matches_trigger('Bash', {'command': 'git commit -m "test"'},
                        [{'tool': 'Bash', 'command_pattern': 'git\\s+commit'}])  # True
    """
    for trigger in triggers:
        if isinstance(trigger, str):
            # Simple tool name match (backwards compatible)
            if tool_name == trigger:
                return True
        elif isinstance(trigger, dict):
            # Complex match with optional command pattern
            trigger_tool = trigger.get('tool', '')
            if trigger_tool != tool_name:
                continue

            # Check command pattern for Bash tool
            if 'command_pattern' in trigger and tool_name == 'Bash':
                command = tool_input.get('command', '')
                # Type safety: ensure command is a string (fail-open)
                if not isinstance(command, str):
                    get_logger().warning(
                        "Invalid command type in tool_input",
                        expected="str",
                        got=type(command).__name__
                    )
                    continue
                pattern = trigger['command_pattern']
                try:
                    if re.search(pattern, command, re.IGNORECASE):
                        return True
                except re.error:
                    # Invalid regex - log and skip
                    get_logger().warning(f"⚠️ Invalid regex pattern: {pattern}")
                    continue
            elif 'command_pattern' not in trigger:
                # Tool matches, no command pattern required
                return True

    return False


def load_yaml(path: Path) -> dict:
    """
    Load config file as YAML.

    Args:
        path: Path to config file

    Returns:
        Parsed config dictionary (empty dict on error)
    """
    if not path.exists():
        return {}

    try:
        import yaml
    except ImportError:
        get_logger().error(
            "⚠️ PyYAML is required to load config files. Install with: pip install pyyaml"
        )
        return {}

    try:
        content = path.read_text()
    except Exception as e:
        get_logger().warning(
            "Could not read config file",
            path=str(path),
            error=str(e),
            error_type=type(e).__name__,
        )
        return {}

    try:
        return yaml.safe_load(content) or {}
    except yaml.YAMLError as e:
        # YAML-specific errors have line/column info
        problem_mark = getattr(e, 'problem_mark', None)
        get_logger().warning(
            "YAML parse error in config file",
            path=str(path),
            error=str(e),
            line=problem_mark.line if problem_mark else None,
            column=problem_mark.column if problem_mark else None,
        )
        return {}
    except Exception as e:
        get_logger().warning(
            "Unexpected error parsing config file",
            path=str(path),
            error=str(e),
            error_type=type(e).__name__,
        )
        return {}


def deep_merge(base: dict, override: dict) -> dict:
    """
    Deep merge override into base dictionary.

    Recursively merges nested dictionaries. Non-dict values are replaced.

    Args:
        base: Base dictionary (modified in place)
        override: Dictionary with values to merge

    Returns:
        Merged dictionary (same as base)
    """
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            deep_merge(base[key], value)
        else:
            base[key] = value
    return base


def write_local_config(project_dir: str, config_data: dict) -> str:
    """
    Write configuration to local override file.

    Writes YAML only. The local config file is gitignored and overrides
    project/global config.

    Args:
        project_dir: Project directory
        config_data: Configuration data to write

    Returns:
        Path to the file that was written (relative to cwd if possible)

    Raises:
        OSError: If write fails
        ImportError: If PyYAML not available (required for local config)
    """
    # Ensure .claude directory exists
    claude_dir = Path(project_dir) / '.claude'
    claude_dir.mkdir(parents=True, exist_ok=True)

    local_file = claude_dir / 'requirements.local.yaml'

    try:
        import yaml
    except ImportError:
        raise ImportError(
            "PyYAML is required for local config. "
            "Install with: pip install pyyaml"
        )

    try:
        with open(local_file, 'w') as f:
            yaml.safe_dump(
                config_data,
                f,
                default_flow_style=False,
                sort_keys=False,
                allow_unicode=True
            )
    except OSError as e:
        from logger import get_logger
        get_logger().error(
            "Failed to write local config",
            path=str(local_file),
            error=e.strerror,
            errno=e.errno,
        )
        raise
    except Exception:
        from logger import get_logger
        get_logger().error(
            "Unexpected error writing local config",
            path=str(local_file),
            exc_info=True,
        )
        raise

    # Return relative path if possible
    try:
        return str(local_file.relative_to(Path.cwd()))
    except ValueError:
        return str(local_file)


def summarize_triggers(trigger_tools: list) -> str:
    """
    Convert trigger_tools config to human-readable summary.

    Supports two trigger formats:
    1. Simple string: 'Edit' - tool name
    2. Complex object: {tool: 'Bash', command_pattern: 'git\\s+commit'} - extracts pattern

    Args:
        trigger_tools: List of triggers from config (strings or dicts)

    Returns:
        Human-readable summary string

    Examples:
        ["Edit", "Write"] → "Edit, Write"
        [{"tool": "Bash", "command_pattern": "git\\s+commit"}] → "git commit"
        ["Edit", {"tool": "Bash", "command_pattern": "git\\s+(commit|merge)"}] → "Edit, git commit/merge"
    """
    if not trigger_tools:
        return "Edit, Write, MultiEdit"

    summaries = []
    for trigger in trigger_tools:
        if isinstance(trigger, str):
            summaries.append(trigger)
        elif isinstance(trigger, dict):
            tool = trigger.get('tool', '')
            pattern = trigger.get('command_pattern', '')

            if pattern and tool == 'Bash':
                # Extract human-readable command from regex pattern
                # Common patterns: git\s+commit → git commit
                #                  git\s+(commit|merge) → git commit/merge
                #                  gh\s+pr\s+create → gh pr create
                human_cmd = pattern
                # Replace regex whitespace with space
                human_cmd = human_cmd.replace('\\s+', ' ').replace('\\s', ' ')
                # Handle alternation groups: (commit|merge) → commit/merge
                human_cmd = re.sub(r'\(([^)]+)\)', lambda m: m.group(1).replace('|', '/'), human_cmd)
                # Remove remaining regex artifacts
                human_cmd = human_cmd.replace('\\', '').replace('^', '').replace('$', '')
                summaries.append(human_cmd)
            else:
                summaries.append(tool)

    return ", ".join(summaries) if summaries else "Edit, Write, MultiEdit"


def get_requirement_description(req_config: dict) -> str:
    """
    Get description from config, falling back to first sentence of message.

    Provides a concise description of what a requirement does, useful for
    context injection where space is limited.

    Args:
        req_config: Requirement configuration dictionary

    Returns:
        Description string (never empty)

    Examples:
        {'description': 'Ensures ADRs are reviewed'} → "Ensures ADRs are reviewed"
        {'message': 'Run /plan-review. Creates commit strategy.'} → "Run /plan-review."
        {} → "No description available."
    """
    # Prefer explicit description field
    if desc := req_config.get('description'):
        if isinstance(desc, str) and desc.strip():
            return desc.strip()

    # Fall back to first sentence of message
    if msg := req_config.get('message'):
        if isinstance(msg, str) and msg.strip():
            # Skip markdown headers (##, **) at start
            lines = msg.strip().split('\n')
            for line in lines:
                line = line.strip()
                # Skip empty lines and markdown headers
                if not line or line.startswith('#'):
                    continue
                # Handle bold markdown at start: **Execute**: `/plan-review` → extract content
                if line.startswith('**'):
                    # Try to extract useful content from bold line
                    # Match pattern like **Label**: content or **Label** content
                    bold_match = re.match(r'\*\*[^*]+\*\*:?\s*(.+)', line)
                    if bold_match:
                        content = bold_match.group(1).strip()
                        if content:
                            return content[:100] + ('...' if len(content) > 100 else '')
                    continue  # Skip pure bold headers without content
                # Found content line - extract first sentence
                # Look for period followed by space or end
                match = re.match(r'^([^.!?]+[.!?])', line)
                if match:
                    return match.group(1).strip()
                # No sentence ending found, return whole line (truncated)
                return line[:100] + ('...' if len(line) > 100 else '')

    return "No description available."


def write_project_config(project_dir: str, config_data: dict) -> str:
    """
    Write configuration to project file.

    Writes to .claude/requirements.yaml (version-controlled) in YAML format.

    Args:
        project_dir: Project directory
        config_data: Configuration data to write

    Returns:
        Path to the file that was written (relative to cwd if possible)

    Raises:
        OSError: If write fails
        ImportError: If PyYAML not available (required for project config)
    """
    # Ensure .claude directory exists
    claude_dir = Path(project_dir) / '.claude'
    claude_dir.mkdir(parents=True, exist_ok=True)

    # Project config requires YAML
    project_file = claude_dir / 'requirements.yaml'

    try:
        import yaml
    except ImportError:
        raise ImportError(
            "PyYAML is required for project config. "
            "Install with: pip install pyyaml"
        )

    # Use atomic write pattern (temp file + rename) to prevent corruption
    temp_fd, temp_path = tempfile.mkstemp(
        dir=claude_dir,
        prefix='.requirements.yaml.',
        suffix='.tmp',
        text=True
    )

    try:
        with os.fdopen(temp_fd, 'w') as f:
            yaml.safe_dump(
                config_data,
                f,
                default_flow_style=False,
                sort_keys=False,
                allow_unicode=True
            )
        # Atomic rename (POSIX compliant)
        os.replace(temp_path, project_file)
    except OSError as e:
        # Cleanup temp file on error
        if os.path.exists(temp_path):
            os.unlink(temp_path)
        from logger import get_logger
        get_logger().error(
            "Failed to write project config",
            path=str(project_file),
            temp_path=temp_path,
            error=e.strerror if hasattr(e, 'strerror') else str(e),
            errno=e.errno if hasattr(e, 'errno') else None,
        )
        raise
    except Exception:
        # Cleanup temp file on error
        if os.path.exists(temp_path):
            os.unlink(temp_path)
        from logger import get_logger
        get_logger().error(
            "Unexpected error writing project config",
            path=str(project_file),
            temp_path=temp_path,
            exc_info=True,
        )
        raise

    # Return relative path if possible
    try:
        return str(project_file.relative_to(Path.cwd()))
    except ValueError:
        return str(project_file)
