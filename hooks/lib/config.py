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
    from pathlib import Path

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
    import json
    local_file_json = claude_dir / 'requirements.local.json'
    with open(local_file_json, 'w') as f:
        json.dump(config_data, f, indent=2)

    # Return relative path if possible
    try:
        return str(local_file_json.relative_to(Path.cwd()))
    except ValueError:
        return str(local_file_json)


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
        self.validation_errors: list[str] = []
        self._config = self._load_cascade()

    REQUIREMENT_SCHEMA = {
        'enabled': {'type': bool},
        'scope': {'type': str, 'allowed': {'session', 'branch', 'permanent'}},
        'trigger_tools': {'type': list, 'element_type': str},
        'checklist': {'type': list, 'element_type': str},
        'message': {'type': str},
        'type': {'type': str, 'allowed': {'blocking', 'dynamic'}},
    }

    def _load_cascade(self) -> dict:
        """
        Load configuration cascade: global → project → local.

        Also validates dynamic requirements to catch configuration errors early.

        Returns:
            Merged and validated configuration dictionary
        """
        config = {
            'requirements': {},
            'logging': {
                'level': 'error',
                'destinations': ['file'],
            },
        }

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

        # 4. Validate dynamic requirements (fail-safe: remove invalid ones)
        requirements = config.get('requirements', {})
        invalid_requirements = []

        for req_name in list(requirements.keys()):
            try:
                self._validate_requirement_config(req_name, requirements[req_name])
            except ValueError as e:
                print(f"⚠️ Config validation error: {e}", file=sys.stderr)
                self.validation_errors.append(str(e))
                invalid_requirements.append(req_name)

        # Remove invalid requirements (fail-safe approach)
        for req_name in invalid_requirements:
            del config['requirements'][req_name]
            print(f"⚠️ Disabled invalid requirement: {req_name}", file=sys.stderr)

        return config

    def get_validation_errors(self) -> list[str]:
        """Return any validation errors encountered while loading config."""
        return list(self.validation_errors)

    def _validate_requirement_schema(self, req_name: str, req_config: dict) -> None:
        """Validate common requirement fields against schema."""
        for field, rules in self.REQUIREMENT_SCHEMA.items():
            if field not in req_config:
                continue

            value = req_config[field]
            expected_type = rules['type']

            if expected_type is list:
                if not isinstance(value, list):
                    raise ValueError(
                        f"Requirement '{req_name}' field '{field}' must be a list of strings"
                    )

                element_type = rules.get('element_type')
                if element_type:
                    invalid_items = [item for item in value if not isinstance(item, element_type)]
                    if invalid_items:
                        raise ValueError(
                            f"Requirement '{req_name}' field '{field}' must contain only strings"
                        )
            else:
                if not isinstance(value, expected_type):
                    raise ValueError(
                        f"Requirement '{req_name}' field '{field}' must be {expected_type.__name__}"
                    )

            if 'allowed' in rules and value not in rules['allowed']:
                allowed_values = ', '.join(sorted(rules['allowed']))
                raise ValueError(
                    f"Requirement '{req_name}' field '{field}' must be one of: {allowed_values}"
                )

    def _validate_requirement_config(self, req_name: str, req_config: dict) -> None:
        """
        Validate requirement configuration.

        Args:
            req_name: Requirement name
            req_config: Requirement configuration dict

        Raises:
            ValueError: If configuration is invalid
        """
        req_type = req_config.get('type', 'blocking')

        # Validate common fields present on all requirements
        self._validate_requirement_schema(req_name, req_config)

        if req_type == 'dynamic':
            # Validate dynamic requirement fields
            self._validate_dynamic_fields(req_name, req_config)
        elif req_type == 'blocking':
            # Blocking requirements are simple - just check enabled is bool
            enabled = req_config.get('enabled')
            if enabled is not None and not isinstance(enabled, bool):
                raise ValueError(
                    f"Requirement '{req_name}' enabled must be boolean, got {type(enabled).__name__}"
                )
        else:
            raise ValueError(
                f"Requirement '{req_name}' has unknown type '{req_type}'. "
                f"Valid types: 'blocking', 'dynamic'"
            )

    def _validate_dynamic_fields(self, req_name: str, req_config: dict) -> None:
        """
        Validate dynamic requirement specific fields.

        Args:
            req_name: Requirement name
            req_config: Requirement configuration dict

        Raises:
            ValueError: If dynamic configuration is invalid
        """
        # Required: calculator
        if not req_config.get('calculator'):
            raise ValueError(
                f"Dynamic requirement '{req_name}' missing required 'calculator' field"
            )

        # Required: thresholds.block
        thresholds = req_config.get('thresholds', {})
        if 'block' not in thresholds:
            raise ValueError(
                f"Dynamic requirement '{req_name}' missing required 'thresholds.block' field"
            )

        # Validate thresholds are positive numbers
        for key, value in thresholds.items():
            if not isinstance(value, (int, float)) or value < 0:
                raise ValueError(
                    f"Dynamic requirement '{req_name}' threshold '{key}' "
                    f"must be a positive number, got: {value} ({type(value).__name__})"
                )

        # Validate calculator module exists (try import)
        calculator = req_config['calculator']
        try:
            __import__(f'lib.{calculator}')
        except ImportError:
            raise ValueError(
                f"Dynamic requirement '{req_name}' calculator module '{calculator}' not found. "
                f"Expected file: ~/.claude/hooks/lib/{calculator}.py"
            )

    def is_enabled(self) -> bool:
        """
        Check if framework enabled for this project.

        Returns:
            True if enabled, False if disabled
        """
        return self._config.get('enabled', True)

    def write_local_override(self, enabled: Optional[bool] = None,
                            requirement_overrides: Optional[dict] = None) -> str:
        """
        Write local configuration override to .claude/requirements.local.yaml.

        This creates or updates a gitignored local config file that overrides
        project and global settings. Use this for personal preferences that
        shouldn't affect the team.

        Args:
            enabled: Framework enabled state (None = don't change)
            requirement_overrides: Dict of requirement names to their enabled state
                                  e.g., {'commit_plan': False, 'github_ticket': True}

        Returns:
            Path to file that was written (relative to cwd if possible)

        Raises:
            OSError: If write fails

        Example:
            # Disable framework for this project
            config.write_local_override(enabled=False)

            # Disable specific requirement
            config.write_local_override(
                requirement_overrides={'commit_plan': False}
            )

            # Enable framework but disable specific requirement
            config.write_local_override(
                enabled=True,
                requirement_overrides={'commit_plan': False}
            )
        """
        from pathlib import Path

        local_file = Path(self.project_dir) / '.claude' / 'requirements.local.yaml'
        local_file_json = Path(self.project_dir) / '.claude' / 'requirements.local.json'

        # Load existing local config if it exists
        existing_config = {}
        if local_file.exists():
            existing_config = load_yaml_or_json(local_file)
        elif local_file_json.exists():
            existing_config = load_yaml_or_json(local_file_json)

        # Update framework enabled state
        if enabled is not None:
            existing_config['enabled'] = enabled

        # Update requirement-level overrides
        if requirement_overrides:
            if 'requirements' not in existing_config:
                existing_config['requirements'] = {}

            for req_name, req_enabled in requirement_overrides.items():
                if req_name not in existing_config['requirements']:
                    existing_config['requirements'][req_name] = {}
                existing_config['requirements'][req_name]['enabled'] = req_enabled

        # Ensure version field exists
        if 'version' not in existing_config:
            existing_config['version'] = '1.0'

        # Write to file using the write_local_config helper
        file_path = write_local_config(self.project_dir, existing_config)

        return file_path

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

    def get_logging_config(self) -> dict:
        """
        Get logging configuration.

        Returns:
            Logging config dictionary
        """
        return self._config.get('logging', {})

    def get_attribute(self, req_name: str, attr: str, default=None):
        """
        Get any attribute from requirement config with default fallback.

        Generic accessor prevents method explosion (ISP compliance).
        New requirement attributes don't require new methods.

        Args:
            req_name: Requirement name
            attr: Attribute name to retrieve
            default: Default value if attribute not found

        Returns:
            Attribute value or default
        """
        req = self.get_requirement(req_name)
        if req is None:
            return default
        return req.get(attr, default)

    def get_requirement_type(self, req_name: str) -> str:
        """
        Get requirement type.

        Args:
            req_name: Requirement name

        Returns:
            'blocking' (manually satisfied) or 'dynamic' (calculated)
            Default: 'blocking' for backwards compatibility
        """
        return self.get_attribute(req_name, 'type', 'blocking')

    def validate_dynamic_requirement(self, req_name: str) -> None:
        """
        Validate dynamic requirement configuration.

        Checks that required fields are present and valid for dynamic requirements.
        Invalid requirements are logged and can be removed from config.

        Args:
            req_name: Requirement name to validate

        Raises:
            ValueError: If configuration is invalid
        """
        req = self.get_requirement(req_name)
        if not req or req.get('type') != 'dynamic':
            return  # Not dynamic, skip validation

        # Required: calculator
        if not req.get('calculator'):
            raise ValueError(
                f"Dynamic requirement '{req_name}' missing required 'calculator' field"
            )

        # Required: thresholds.block
        thresholds = req.get('thresholds', {})
        if 'block' not in thresholds:
            raise ValueError(
                f"Dynamic requirement '{req_name}' missing required 'thresholds.block' field"
            )

        # Validate thresholds are positive numbers
        for key, value in thresholds.items():
            if not isinstance(value, (int, float)) or value < 0:
                raise ValueError(
                    f"Dynamic requirement '{req_name}' threshold '{key}' "
                    f"must be a positive number, got: {value} ({type(value).__name__})"
                )

        # Validate calculator module exists (try import)
        calculator = req['calculator']
        try:
            __import__(f'lib.{calculator}')
        except ImportError:
            raise ValueError(
                f"Dynamic requirement '{req_name}' calculator module '{calculator}' not found. "
                f"Expected file: ~/.claude/hooks/lib/{calculator}.py"
            )


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
