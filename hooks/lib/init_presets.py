"""
Init Presets Module

Provides preset configuration profiles for the `req init` command.
Each preset defines a set of requirements with sensible defaults.

Presets:
- strict: Full enforcement with commit_plan + protected_branch
- relaxed: Light touch with commit_plan only (default)
- minimal: Framework enabled, no requirements (configure later)

Usage:
    from init_presets import get_preset, generate_config, config_to_yaml

    # Get raw preset
    preset = get_preset('relaxed')

    # Generate full config with version/enabled
    config = generate_config('relaxed')

    # Convert to YAML string
    yaml_str = config_to_yaml(config)
"""
import copy
from typing import Dict, Any, Optional


# Preset definitions
PRESETS: Dict[str, Dict[str, Any]] = {
    'strict': {
        'requirements': {
            'commit_plan': {
                'enabled': True,
                'type': 'blocking',
                'scope': 'session',
                'trigger_tools': ['Edit', 'Write', 'MultiEdit'],
                'message': '''📋 **No commit plan found for this session**

Before making code changes, you should plan your commits.

**Required**: Create a commit plan that describes:
- What changes you'll make
- How you'll split them into atomic commits
- What order to make the changes

**Why this matters**:
- Ensures commits are atomic and reviewable
- Prevents "fix comments" commits
- Follows project conventions

**To proceed**: Run `req satisfy commit_plan` after creating a plan
''',
                'checklist': [
                    'Identified the changes needed for this feature/fix',
                    'Determined atomic commit boundaries (each commit is reviewable)',
                    'Planned commit sequence and dependencies',
                    'Considered what can be safely rolled back',
                    'Created plan file documenting the approach',
                ],
            },
            'protected_branch': {
                'enabled': True,
                'type': 'guard',
                'guard_type': 'protected_branch',
                'protected_branches': ['master', 'main'],
                'trigger_tools': ['Edit', 'Write', 'MultiEdit'],
                'message': '''🚫 **Cannot edit files on protected branch**

Direct edits on protected branches are not allowed.
Please create a feature branch first:

```bash
git checkout -b feature/your-feature-name
```

**For emergency hotfixes** (current session only):
```bash
req approve protected_branch
```
''',
            },
        },
        'hooks': {
            'stop': {'verify_requirements': True},
        },
    },

    'relaxed': {
        'requirements': {
            'commit_plan': {
                'enabled': True,
                'type': 'blocking',
                'scope': 'session',
                'trigger_tools': ['Edit', 'Write', 'MultiEdit'],
                'message': '''📋 **No commit plan found for this session**

Before making code changes, please create a brief plan describing:
- What you're implementing
- Key files to modify
- Approach and considerations

**To proceed**: Run `req satisfy commit_plan` after creating a plan
''',
                'checklist': [
                    'Plan created documenting approach',
                    'Atomic commits identified',
                ],
            },
        },
    },

    'minimal': {
        'requirements': {},
    },
}


def get_preset(name: str) -> Dict[str, Any]:
    """
    Get a preset configuration by name.

    Args:
        name: Preset name ('strict', 'relaxed', 'minimal')

    Returns:
        Deep copy of the preset configuration.
        Returns 'minimal' preset if name is unknown.
    """
    preset = PRESETS.get(name, PRESETS['minimal'])
    return copy.deepcopy(preset)


def deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """
    Recursively merge two dictionaries.

    Override values take precedence. Nested dicts are merged recursively.

    Args:
        base: Base dictionary
        override: Override dictionary

    Returns:
        Merged dictionary (base is modified in place and returned)
    """
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            deep_merge(base[key], value)
        else:
            base[key] = copy.deepcopy(value)
    return base


def generate_config(preset_name: str,
                    customizations: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Generate a full configuration from a preset with optional customizations.

    Adds version and enabled fields, then merges any customizations.

    Args:
        preset_name: Preset name ('strict', 'relaxed', 'minimal')
        customizations: Optional dict to merge on top of preset

    Returns:
        Complete configuration dict ready to write
    """
    config = get_preset(preset_name)

    # Add standard fields
    config['version'] = '1.0'
    config['enabled'] = True

    # Merge customizations if provided
    if customizations:
        deep_merge(config, customizations)

    return config


def config_to_yaml(config: Dict[str, Any]) -> str:
    """
    Convert configuration dict to YAML string.

    Uses PyYAML if available, falls back to manual formatting.

    Args:
        config: Configuration dictionary

    Returns:
        YAML-formatted string
    """
    try:
        import yaml
        return yaml.safe_dump(config, default_flow_style=False, sort_keys=False)
    except ImportError:
        return _manual_yaml_format(config)


def _needs_quoting(value: str) -> bool:
    """
    Check if a string value needs quoting in YAML.

    Args:
        value: String value to check

    Returns:
        True if the value should be quoted
    """
    if not value:
        return True

    # YAML special indicators that need quoting
    special_chars = (':', '#', '{', '}', '[', ']', ',', '&', '*', '?', '|', '>', "'", '"', '%', '@', '`')
    yaml_booleans = ('yes', 'no', 'true', 'false', 'on', 'off', 'null', '~')

    # Quote if contains special chars
    if any(c in value for c in special_chars):
        return True

    # Quote if looks like a YAML boolean/null
    if value.lower() in yaml_booleans:
        return True

    # Quote if starts with special YAML indicators
    if value[0] in ('-', '!', '&', '*', '?', '|', '>', "'", '"', '%', '@', '`', ' '):
        return True

    # Quote if looks like a number
    try:
        float(value)
        return True
    except ValueError:
        pass

    return False


def _manual_yaml_format(config: Dict[str, Any], indent: int = 0) -> str:
    """
    Simple YAML-like formatting without PyYAML dependency.

    Args:
        config: Configuration dictionary
        indent: Current indentation level

    Returns:
        YAML-formatted string
    """
    lines = []
    prefix = '  ' * indent

    for key, value in config.items():
        if isinstance(value, dict):
            lines.append(f"{prefix}{key}:")
            lines.append(_manual_yaml_format(value, indent + 1))
        elif isinstance(value, list):
            lines.append(f"{prefix}{key}:")
            for item in value:
                if isinstance(item, str):
                    # Quote strings that might need it
                    if '\n' in item or ':' in item or '#' in item:
                        lines.append(f'{prefix}  - "{item}"')
                    else:
                        lines.append(f"{prefix}  - {item}")
                else:
                    lines.append(f"{prefix}  - {item}")
        elif isinstance(value, bool):
            lines.append(f"{prefix}{key}: {str(value).lower()}")
        elif isinstance(value, str) and '\n' in value:
            # Multi-line string - use literal block scalar
            lines.append(f"{prefix}{key}: |")
            for line in value.rstrip('\n').split('\n'):
                lines.append(f"{prefix}  {line}")
        elif isinstance(value, str):
            # Simple string - quote if needed for YAML safety
            if _needs_quoting(value):
                # Escape any double quotes in the value
                escaped = value.replace('"', '\\"')
                lines.append(f'{prefix}{key}: "{escaped}"')
            else:
                lines.append(f"{prefix}{key}: {value}")
        elif value is None:
            lines.append(f"{prefix}{key}: null")
        else:
            lines.append(f"{prefix}{key}: {value}")

    return '\n'.join(lines)
