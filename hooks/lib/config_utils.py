#!/usr/bin/env python3
"""
Configuration utilities for requirements framework.

This module contains standalone helper functions used by config.py and other
modules. These utilities handle:
- Trigger matching for tool invocations
- Config file I/O (YAML/JSON with fallbacks)
- Dictionary merging for config cascades
"""
import json
import os
import re
import sys
import tempfile
from pathlib import Path


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
                pattern = trigger['command_pattern']
                try:
                    if re.search(pattern, command, re.IGNORECASE):
                        return True
                except re.error:
                    # Invalid regex - log and skip
                    print(f"⚠️ Invalid regex pattern: {pattern}", file=sys.stderr)
                    continue
            elif 'command_pattern' not in trigger:
                # Tool matches, no command pattern required
                return True

    return False


def load_yaml_or_json(path: Path) -> dict:
    """
    Load config file, preferring YAML if available.

    Falls back to JSON parsing if PyYAML is not installed.

    Args:
        path: Path to config file

    Returns:
        Parsed config dictionary (empty dict on error)
    """
    if not path.exists():
        return {}

    content = path.read_text()

    # Try YAML first
    try:
        import yaml
        return yaml.safe_load(content) or {}
    except ImportError:
        pass  # PyYAML not available, try JSON
    except Exception as e:
        print(f"⚠️ YAML parse error in {path}: {e}", file=sys.stderr)
        return {}

    # Try JSON
    try:
        return json.loads(content)
    except json.JSONDecodeError as e:
        # Check if it looks like YAML (has colons but no proper JSON structure)
        if ':' in content and not content.strip().startswith('{'):
            print(
                f"⚠️ Config {path} appears to be YAML but PyYAML is not installed. "
                "Install with: pip install pyyaml",
                file=sys.stderr
            )
        else:
            print(f"⚠️ JSON parse error in {path}: {e}", file=sys.stderr)
        return {}
    except Exception as e:
        print(f"⚠️ Could not load {path}: {e}", file=sys.stderr)
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

    Tries to write YAML if PyYAML is available, otherwise falls back to JSON.
    The local config file is gitignored and overrides project/global config.

    Args:
        project_dir: Project directory
        config_data: Configuration data to write

    Returns:
        Path to the file that was written (relative to cwd if possible)

    Raises:
        OSError: If write fails
    """
    # Ensure .claude directory exists
    claude_dir = Path(project_dir) / '.claude'
    claude_dir.mkdir(parents=True, exist_ok=True)

    # Try to write as YAML first (preferred format)
    local_file = claude_dir / 'requirements.local.yaml'
    try:
        import yaml
        with open(local_file, 'w') as f:
            yaml.safe_dump(
                config_data,
                f,
                default_flow_style=False,
                sort_keys=False,
                allow_unicode=True
            )
        # Return relative path if possible
        try:
            return str(local_file.relative_to(Path.cwd()))
        except ValueError:
            return str(local_file)
    except ImportError:
        # PyYAML not available - fallback to JSON
        pass

    # Fallback to JSON
    local_file_json = claude_dir / 'requirements.local.json'
    with open(local_file_json, 'w') as f:
        json.dump(config_data, f, indent=2)

    # Return relative path if possible
    try:
        return str(local_file_json.relative_to(Path.cwd()))
    except ValueError:
        return str(local_file_json)


def write_project_config(project_dir: str, config_data: dict) -> str:
    """
    Write configuration to project file.

    Writes to .claude/requirements.yaml (version-controlled). Unlike local config,
    only supports YAML (no JSON fallback) to maintain consistency with `req init`.

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

    # Project config requires YAML (no JSON fallback)
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
    except Exception:
        # Cleanup temp file on error
        if os.path.exists(temp_path):
            os.unlink(temp_path)
        raise

    # Return relative path if possible
    try:
        return str(project_file.relative_to(Path.cwd()))
    except ValueError:
        return str(project_file)
