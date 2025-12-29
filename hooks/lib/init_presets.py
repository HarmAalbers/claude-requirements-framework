"""
Init Presets Module

Provides preset configuration profiles for the `req init` command.
Each preset defines a set of requirements with sensible defaults.

Presets:
- strict: Full enforcement with commit_plan + protected_branch
- relaxed: Light touch with commit_plan only (default for project without global)
- minimal: Framework enabled, no requirements (configure later)
- advanced: All features - showcases every requirement type (recommended for global)
- inherit: Use global defaults (recommended for project with global config)

Usage:
    from init_presets import get_preset, generate_config, config_to_yaml

    # Get raw preset
    preset = get_preset('relaxed')

    # Generate full config with version/enabled
    config = generate_config('relaxed', context='project')

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

    'advanced': {
        'requirements': {
            'commit_plan': {
                'enabled': True,
                'type': 'blocking',
                'scope': 'session',
                'trigger_tools': ['Edit', 'Write', 'MultiEdit'],
                'message': '''📋 **Commit Plan Required**

Before making code changes, create a brief plan documenting your approach.

**To proceed**: Run `req satisfy commit_plan` after creating a plan
''',
                'checklist': [
                    'Identified the changes needed',
                    'Determined atomic commit boundaries',
                    'Planned commit sequence',
                    'Considered rollback strategy',
                    'Created plan file',
                ],
            },

            'adr_reviewed': {
                'enabled': True,
                'type': 'blocking',
                'scope': 'session',
                'trigger_tools': ['Edit', 'Write', 'MultiEdit'],
                'message': '''📚 **ADR Review Checkpoint**

Have you reviewed relevant Architecture Decision Records?

**To satisfy**: `req satisfy adr_reviewed` after reviewing ADRs
''',
                'checklist': [
                    'Found relevant ADRs',
                    'Reviewed decision context',
                    'Confirmed approach aligns with ADRs',
                ],
            },

            'protected_branch': {
                'enabled': True,
                'type': 'guard',
                'guard_type': 'protected_branch',
                'protected_branches': ['master', 'main'],
                'trigger_tools': ['Edit', 'Write', 'MultiEdit'],
                'message': '''🚫 **Cannot edit files on protected branch**

Create a feature branch: `git checkout -b feature/name`

**For emergency**: `req approve protected_branch`
''',
            },

            'branch_size_limit': {
                'enabled': True,
                'type': 'dynamic',
                'calculator': 'branch_size_calculator',
                'scope': 'session',
                'trigger_tools': ['Edit', 'Write', 'MultiEdit'],
                'cache_ttl': 60,
                'approval_ttl': 3600,
                'thresholds': {
                    'warn': 250,
                    'block': 400,
                },
                'blocking_message': '''🛑 **Branch size limit: {total} changes**

{summary}

Consider splitting into smaller PRs for easier review.

**To override**: `req approve branch_size_limit`
''',
            },

            'pre_commit_review': {
                'enabled': True,
                'type': 'blocking',
                'scope': 'single_use',
                'trigger_tools': [
                    {'tool': 'Bash', 'command_pattern': 'git\\s+(commit|cherry-pick|revert|merge)'},
                ],
                'message': '''📝 **Code review before commit**

Run `/pre-pr-review:pre-commit` to review changes.

**After review**: Proceed with commit.
''',
                'checklist': [
                    'Code follows conventions',
                    'Error handling adequate',
                    'No obvious bugs',
                ],
            },

            'pre_pr_review': {
                'enabled': True,
                'type': 'blocking',
                'scope': 'single_use',
                'trigger_tools': [
                    {'tool': 'Bash', 'command_pattern': 'gh\\s+pr\\s+create'},
                ],
                'message': '''🔍 **Quality check before PR**

Run `/pre-pr-review:quality-check` for comprehensive review.

**After review**: Create PR.
''',
                'checklist': [
                    'Code reviewed for bugs',
                    'Error handling complete',
                    'Style guide followed',
                    'Tests adequate',
                ],
            },

            'codex_reviewer': {
                'enabled': False,  # Optional (requires Codex CLI)
                'type': 'blocking',
                'scope': 'single_use',
                'trigger_tools': [
                    {'tool': 'Bash', 'command_pattern': 'gh\\s+pr\\s+create'},
                ],
                'message': '''🤖 **Codex AI Review Required**

Run `/requirements-framework:codex-review` for AI-powered code review.

**After review**: Create PR.
''',
                'checklist': [
                    'Codex CLI installed (npm install -g @openai/codex)',
                    'Logged in (codex login)',
                    'AI review completed',
                    'Critical findings addressed',
                ],
            },

            'github_ticket': {
                'enabled': False,
                'type': 'blocking',
                'scope': 'branch',
                'trigger_tools': ['Edit', 'Write', 'MultiEdit'],
                'message': '''🎫 **No GitHub issue linked**

**To satisfy**: `req satisfy github_ticket --metadata '{"ticket":"#1234"}'`

(Disabled by default - enable if using issue tracking)
''',
            },
        },
        'hooks': {
            'stop': {'verify_requirements': True},
        },
    },

    'inherit': {
        'inherit': True,
        'requirements': {},
    },
}


def get_preset(name: str) -> Dict[str, Any]:
    """
    Get a preset configuration by name.

    Args:
        name: Preset name ('strict', 'relaxed', 'minimal', 'advanced', 'inherit')

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
                    customizations: Optional[Dict[str, Any]] = None,
                    context: str = 'project') -> Dict[str, Any]:
    """
    Generate a full configuration from a preset with optional customizations.

    Adds version and enabled fields, then merges any customizations.
    Context-aware behavior adjusts defaults based on whether this is
    global, project, or local config.

    Args:
        preset_name: Preset name ('strict', 'relaxed', 'minimal', 'advanced', 'inherit')
        customizations: Optional dict to merge on top of preset
        context: Config context - 'global', 'project', or 'local'

    Returns:
        Complete configuration dict ready to write

    Raises:
        ValueError: If preset_name or context is invalid
    """
    # Validate preset name
    valid_presets = list(PRESETS.keys())
    if preset_name not in valid_presets:
        raise ValueError(
            f"Invalid preset '{preset_name}'. "
            f"Valid presets: {', '.join(valid_presets)}"
        )

    # Validate context
    valid_contexts = ['global', 'project', 'local']
    if context not in valid_contexts:
        raise ValueError(
            f"Invalid context '{context}'. "
            f"Valid contexts: {', '.join(valid_contexts)}"
        )

    config = get_preset(preset_name)

    # Add standard fields
    config['version'] = '1.0'
    config['enabled'] = True

    # Add inherit flag for project context (unless preset already defines it)
    if context == 'project' and 'inherit' not in config:
        # The 'inherit' preset already has inherit: True
        # Standalone presets like 'strict'/'relaxed' should not inherit
        if preset_name == 'inherit':
            config['inherit'] = True
        elif preset_name in ['minimal']:
            # Minimal can inherit for project context
            config['inherit'] = True

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
