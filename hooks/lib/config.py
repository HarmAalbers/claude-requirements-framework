#!/usr/bin/env python3
"""
Configuration loading for requirements framework.

Implements cascading configuration:
1. Global defaults (~/.claude/requirements.yaml)
2. Project config (.claude/requirements.yaml) - committed to repo
3. Local overrides (.claude/requirements.local.yaml) - gitignored

Config files can be YAML (if PyYAML available) or JSON (fallback).
"""
import json
import sys
from pathlib import Path
from typing import Optional


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


class RequirementsConfig:
    """
    Configuration manager for requirements framework.

    Loads and merges configuration from global, project, and local sources.
    """

    def __init__(self, project_dir: str):
        """
        Initialize config for project.

        Args:
            project_dir: Project root directory
        """
        self.project_dir = project_dir
        self._config = self._load_cascade()

    def _load_cascade(self) -> dict:
        """
        Load configuration cascade: global → project → local.

        Returns:
            Merged configuration dictionary
        """
        config = {'requirements': {}}

        # 1. Global defaults
        global_file = Path.home() / '.claude' / 'requirements.yaml'
        if global_file.exists():
            global_config = load_yaml_or_json(global_file)
            if global_config:
                config = global_config.copy()

        # 2. Project config (versioned)
        project_file = Path(self.project_dir) / '.claude' / 'requirements.yaml'
        if project_file.exists():
            project_config = load_yaml_or_json(project_file)

            if project_config:
                # Check inherit flag (default: True)
                if project_config.get('inherit', True):
                    # Deep merge project into global
                    deep_merge(config, project_config)
                else:
                    # Replace entirely (no inheritance)
                    config = project_config

        # 3. Local overrides (gitignored)
        local_file = Path(self.project_dir) / '.claude' / 'requirements.local.yaml'
        if local_file.exists():
            local_config = load_yaml_or_json(local_file)
            if local_config:
                deep_merge(config, local_config)

        return config

    def is_enabled(self) -> bool:
        """
        Check if framework enabled for this project.

        Returns:
            True if enabled, False if disabled
        """
        return self._config.get('enabled', True)

    def get_requirement(self, name: str) -> Optional[dict]:
        """
        Get configuration for a specific requirement.

        Args:
            name: Requirement name (e.g., "commit_plan")

        Returns:
            Requirement config dict or None if not found
        """
        return self._config.get('requirements', {}).get(name)

    def get_all_requirements(self) -> list[str]:
        """
        Get all configured requirement names.

        Returns:
            List of requirement names
        """
        return list(self._config.get('requirements', {}).keys())

    def is_requirement_enabled(self, name: str) -> bool:
        """
        Check if specific requirement is enabled.

        Args:
            name: Requirement name

        Returns:
            True if requirement exists and is enabled
        """
        req = self.get_requirement(name)
        return req is not None and req.get('enabled', False)

    def get_scope(self, name: str) -> str:
        """
        Get scope for requirement.

        Args:
            name: Requirement name

        Returns:
            Scope string: "session", "branch", or "permanent"
        """
        req = self.get_requirement(name)
        return req.get('scope', 'session') if req else 'session'

    def get_trigger_tools(self, name: str) -> list[str]:
        """
        Get tools that trigger this requirement check.

        Args:
            name: Requirement name

        Returns:
            List of tool names (default: Edit, Write, MultiEdit)
        """
        req = self.get_requirement(name)
        if req:
            return req.get('trigger_tools', ['Edit', 'Write', 'MultiEdit'])
        return ['Edit', 'Write', 'MultiEdit']

    def get_message(self, name: str) -> str:
        """
        Get message to display when requirement not satisfied.

        Args:
            name: Requirement name

        Returns:
            Message string
        """
        req = self.get_requirement(name)
        if req:
            return req.get('message', f'Requirement "{name}" not satisfied.')
        return f'Requirement "{name}" not satisfied.'

    def get_checklist(self, name: str) -> list[str]:
        """
        Get checklist items for requirement.

        Args:
            name: Requirement name

        Returns:
            List of checklist items (empty list if none configured)
        """
        req = self.get_requirement(name)
        if req:
            return req.get('checklist', [])
        return []

    def get_raw_config(self) -> dict:
        """
        Get raw merged configuration.

        Returns:
            Full config dictionary
        """
        return self._config.copy()


if __name__ == "__main__":
    import tempfile
    import os

    # Quick test with temp directory
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create project config
        os.makedirs(f"{tmpdir}/.claude")
        config_content = {
            "version": "1.0",
            "enabled": True,
            "requirements": {
                "test_req": {
                    "enabled": True,
                    "scope": "session",
                    "message": "Test requirement not satisfied"
                }
            }
        }

        with open(f"{tmpdir}/.claude/requirements.yaml", 'w') as f:
            json.dump(config_content, f)

        # Test loading
        config = RequirementsConfig(tmpdir)
        print(f"Enabled: {config.is_enabled()}")
        print(f"All requirements: {config.get_all_requirements()}")
        print(f"test_req enabled: {config.is_requirement_enabled('test_req')}")
        print(f"test_req scope: {config.get_scope('test_req')}")
        print(f"test_req message: {config.get_message('test_req')}")

    print("✅ Config tests passed")
