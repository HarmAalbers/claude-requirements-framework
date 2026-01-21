"""
Messages Module for Requirements Framework.

Loads externalized messages from YAML files with cascade priority:
  local > project > global

Each requirement has its own message file (e.g., commit_plan.yaml).
Templates (_templates.yaml) provide defaults by requirement type.
Status templates (_status.yaml) control status briefing formats.

Design Decisions:
- One file per requirement (commit_plan.yaml, adr_reviewed.yaml, etc.)
- Strict mode by default (fail if message file missing)
- All 6 message fields mandatory per requirement
- Calculator classes provide their own dynamic messages
- Cascade loading follows same pattern as requirements config

Example directory structure:
    ~/.claude/messages/                    # Global defaults
        _templates.yaml                    # Type-based defaults
        _status.yaml                       # Status format templates
        commit_plan.yaml                   # Per-requirement messages
        adr_reviewed.yaml
        ...

    <project>/.claude/messages/            # Project-specific (version controlled)
        _templates.yaml                    # Override global templates
        my_custom_req.yaml                 # Project-specific requirements

    <project>/.claude/messages.local/      # Local overrides (gitignored)
        commit_plan.yaml                   # Personal tweaks
"""
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Dict, Any, List, Protocol, runtime_checkable
import re
import yaml


class MessageNotFoundError(Exception):
    """Raised when strict mode is enabled and a message file is missing."""

    def __init__(self, req_name: str, searched_paths: List[Path]):
        self.req_name = req_name
        self.searched_paths = searched_paths
        paths_str = "\n  ".join(str(p) for p in searched_paths)
        super().__init__(
            f"Message file not found for requirement '{req_name}'.\n"
            f"Searched in:\n  {paths_str}"
        )


class MessageValidationError(Exception):
    """Raised when a message file fails validation."""

    def __init__(self, file_path: Path, errors: List[str]):
        self.file_path = file_path
        self.errors = errors
        errors_str = "\n  - ".join(errors)
        super().__init__(
            f"Message file validation failed for '{file_path}':\n  - {errors_str}"
        )


@dataclass
class MessagePaths:
    """
    Cascade paths for message files.

    Attributes:
        global_dir: ~/.claude/messages/
        project_dir: <project>/.claude/messages/
        local_dir: <project>/.claude/messages.local/
    """
    global_dir: Path
    project_dir: Path
    local_dir: Path

    @classmethod
    def from_project(cls, project_dir: str) -> 'MessagePaths':
        """
        Create MessagePaths from a project directory.

        Args:
            project_dir: Project root directory path

        Returns:
            MessagePaths with resolved cascade directories
        """
        home = Path.home()
        project = Path(project_dir)

        return cls(
            global_dir=home / '.claude' / 'messages',
            project_dir=project / '.claude' / 'messages',
            local_dir=project / '.claude' / 'messages.local',
        )


@dataclass
class RequirementMessages:
    """
    All message variants for a single requirement.

    Attributes:
        blocking_message: Full message shown first time (markdown)
        short_message: Deduplicated message for parallel calls
        success_message: Shown when requirement is satisfied
        header: Short header for status displays
        action_label: Action label for quick start sections
        fallback_text: Plain text fallback command
    """
    blocking_message: str
    short_message: str
    success_message: str
    header: str
    action_label: str
    fallback_text: str

    def format(self, **kwargs) -> 'RequirementMessages':
        """
        Return new instance with {var} placeholders substituted.

        Safely handles missing placeholders by leaving them unchanged.

        Args:
            **kwargs: Variable substitutions (e.g., req_name='commit_plan')

        Returns:
            New RequirementMessages with placeholders replaced
        """
        def safe_format(template: str, **kw) -> str:
            """Format string, leaving unknown placeholders unchanged."""
            # Use a pattern that matches {word} but not {{word}}
            pattern = r'\{([a-zA-Z_][a-zA-Z0-9_]*)\}'

            def replacer(match):
                key = match.group(1)
                return str(kw.get(key, match.group(0)))

            return re.sub(pattern, replacer, template)

        return RequirementMessages(
            blocking_message=safe_format(self.blocking_message, **kwargs),
            short_message=safe_format(self.short_message, **kwargs),
            success_message=safe_format(self.success_message, **kwargs),
            header=safe_format(self.header, **kwargs),
            action_label=safe_format(self.action_label, **kwargs),
            fallback_text=safe_format(self.fallback_text, **kwargs),
        )

    def to_dict(self) -> Dict[str, str]:
        """Convert to dictionary for serialization."""
        return {
            'blocking_message': self.blocking_message,
            'short_message': self.short_message,
            'success_message': self.success_message,
            'header': self.header,
            'action_label': self.action_label,
            'fallback_text': self.fallback_text,
        }


@runtime_checkable
class CalculatorMessageProvider(Protocol):
    """
    Protocol for calculators that provide their own messages.

    Dynamic requirement calculators implement this to generate
    context-aware messages based on calculation results.
    """

    def get_blocking_message(self, result: dict, context: dict) -> str:
        """Generate blocking message from calculator result."""
        ...

    def get_short_message(self, result: dict) -> str:
        """Generate short/deduplicated message."""
        ...


# Default templates for each requirement type
DEFAULT_TEMPLATES: Dict[str, Dict[str, str]] = {
    'blocking': {
        'blocking_message': '''## Blocked: {req_name}

**Action**: `req satisfy {req_name} --session {session_id}`

---
Fallback: `req satisfy {req_name} --session {session_id}`''',
        'short_message': 'Requirement `{req_name}` not satisfied (waiting...)',
        'success_message': 'Requirement `{req_name}` satisfied',
        'header': '{req_name}',
        'action_label': '`req satisfy {req_name}`',
        'fallback_text': 'req satisfy {req_name}',
    },
    'guard': {
        'blocking_message': '''## Blocked: {req_name}

Guard condition not met.

---
Override: `req approve {req_name}`''',
        'short_message': 'Guard `{req_name}` blocked (waiting...)',
        'success_message': 'Guard `{req_name}` passed',
        'header': '{req_name}',
        'action_label': '`req approve {req_name}`',
        'fallback_text': 'req approve {req_name}',
    },
    'dynamic': {
        'blocking_message': '''## Blocked: {req_name}

Current value: {value} (threshold: {block_threshold})

---
Override: `req approve {req_name} --session {session_id}`''',
        'short_message': 'Requirement `{req_name}` not satisfied (value: {value})',
        'success_message': 'Requirement `{req_name}` satisfied',
        'header': '{req_name}',
        'action_label': '`req approve {req_name}`',
        'fallback_text': 'req approve {req_name}',
    },
}

# Default structural elements
DEFAULT_STRUCTURAL: Dict[str, str] = {
    'blocked_header': '## Blocked: {req_name}',
    'blocked_multiple_header': '## Blocked: Multiple Requirements',
    'execute_label': '**Execute**: `/{skill}`',
    'action_label': '**Action**: `{command}`',
    'fallback_label': 'Fallback: `{command}`',
    'table_header': '| Requirement | Execute |',
    'table_separator': '|-------------|---------|',
    'section_separator': '---',
    'cannot_complete_header': '## Cannot Complete: Unsatisfied Requirements',
}

# Default status templates
DEFAULT_STATUS_TEMPLATES: Dict[str, str] = {
    'compact': '''## Requirements: {satisfied_count}/{total_count} satisfied

{action_list}
**Fallback**: `req satisfy {unsatisfied_names} --session {session_id}`''',

    'standard': '''## Requirements Framework Active

**Branch**: `{branch}` @ `{project_dir}` | **Session**: `{session_id}`

{quick_start}

| Requirement | Status | Triggers | Resolve |
|-------------|--------|----------|---------|
{status_table}

{fallback}''',

    'rich': '''## Requirements Framework: Session Briefing

**Project**: `{project_dir}`
**Branch**: `{branch}` | **Session**: `{session_id}`

---

{quick_start}

### Requirement Definitions

{definitions}

---

### Scope Reference
| Scope | Behavior |
|-------|----------|
| session | Cleared when session ends |
| branch | Persists across sessions on same branch |
| single_use | Cleared after trigger command completes |
| permanent | Never auto-cleared |

---

### Current Status

| Requirement | Status |
|-------------|--------|
{status_table}

{workflow_guide}
{fallback}''',
}


class MessageLoader:
    """
    Load messages with cascade priority: local > project > global.

    The loader searches for message files in this order:
    1. <project>/.claude/messages.local/<req_name>.yaml (personal tweaks)
    2. <project>/.claude/messages/<req_name>.yaml (project-specific)
    3. ~/.claude/messages/<req_name>.yaml (global defaults)

    Templates (_templates.yaml) provide defaults by requirement type.
    If no file is found and strict=True, raises MessageNotFoundError.
    If strict=False, uses built-in default templates.

    Attributes:
        paths: MessagePaths for cascade directories
        strict: Whether to fail on missing files
        _cache: Cache for loaded messages
        _templates: Cache for loaded templates
        _status_templates: Cache for status format templates
        _structural: Cache for structural elements
    """

    # Required fields in requirement message files
    REQUIRED_FIELDS = [
        'blocking_message',
        'short_message',
        'success_message',
        'header',
        'action_label',
        'fallback_text',
    ]

    def __init__(self, project_dir: str, strict: bool = True):
        """
        Initialize the message loader.

        Args:
            project_dir: Project directory path
            strict: If True, fail when message file is missing.
                    If False, use default templates.
        """
        self.paths = MessagePaths.from_project(project_dir)
        self.strict = strict
        self._cache: Dict[str, RequirementMessages] = {}
        self._templates: Optional[Dict[str, Dict[str, str]]] = None
        self._status_templates: Optional[Dict[str, str]] = None
        self._structural: Optional[Dict[str, str]] = None

    def _load_yaml(self, file_path: Path) -> Optional[Dict[str, Any]]:
        """
        Load YAML file safely.

        Args:
            file_path: Path to YAML file

        Returns:
            Parsed YAML content or None if file doesn't exist
        """
        if not file_path.exists():
            return None
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        except Exception:
            return None

    def _find_message_file(self, req_name: str) -> Optional[Path]:
        """
        Find message file for a requirement using cascade priority.

        Args:
            req_name: Requirement name

        Returns:
            Path to message file or None if not found
        """
        filename = f"{req_name}.yaml"

        # Cascade order: local > project > global
        search_paths = [
            self.paths.local_dir / filename,
            self.paths.project_dir / filename,
            self.paths.global_dir / filename,
        ]

        for path in search_paths:
            if path.exists():
                return path

        return None

    def _get_searched_paths(self, req_name: str) -> List[Path]:
        """Get list of paths that would be searched for a requirement."""
        filename = f"{req_name}.yaml"
        return [
            self.paths.local_dir / filename,
            self.paths.project_dir / filename,
            self.paths.global_dir / filename,
        ]

    def _load_templates(self) -> Dict[str, Dict[str, str]]:
        """
        Load templates from _templates.yaml with cascade.

        Returns:
            Merged templates dict
        """
        if self._templates is not None:
            return self._templates

        # Start with defaults
        templates = {k: dict(v) for k, v in DEFAULT_TEMPLATES.items()}

        # Load and merge in cascade order (reverse: global first)
        for dir_path in [self.paths.global_dir, self.paths.project_dir, self.paths.local_dir]:
            file_path = dir_path / '_templates.yaml'
            data = self._load_yaml(file_path)
            if data:
                for type_name, type_templates in data.items():
                    if type_name == 'version':
                        continue
                    if type_name not in templates:
                        templates[type_name] = {}
                    templates[type_name].update(type_templates)

        self._templates = templates
        return templates

    def _load_structural(self) -> Dict[str, str]:
        """
        Load structural elements from _templates.yaml with cascade.

        Returns:
            Merged structural elements dict
        """
        if self._structural is not None:
            return self._structural

        # Start with defaults
        structural = dict(DEFAULT_STRUCTURAL)

        # Load and merge in cascade order
        for dir_path in [self.paths.global_dir, self.paths.project_dir, self.paths.local_dir]:
            file_path = dir_path / '_templates.yaml'
            data = self._load_yaml(file_path)
            if data and 'structural' in data:
                structural.update(data['structural'])

        self._structural = structural
        return structural

    def _load_status_templates(self) -> Dict[str, str]:
        """
        Load status templates from _status.yaml with cascade.

        Returns:
            Merged status templates dict
        """
        if self._status_templates is not None:
            return self._status_templates

        # Start with defaults
        status = dict(DEFAULT_STATUS_TEMPLATES)

        # Load and merge in cascade order
        for dir_path in [self.paths.global_dir, self.paths.project_dir, self.paths.local_dir]:
            file_path = dir_path / '_status.yaml'
            data = self._load_yaml(file_path)
            if data:
                for key, value in data.items():
                    if key == 'version' or key == 'partials':
                        continue
                    # Handle nested format structure
                    if isinstance(value, dict) and 'format' in value:
                        status[key] = value['format']
                    elif isinstance(value, str):
                        status[key] = value

        self._status_templates = status
        return status

    def get_messages(self, req_name: str, req_type: str = 'blocking') -> RequirementMessages:
        """
        Get messages for a requirement (cached).

        Args:
            req_name: Requirement name (e.g., 'commit_plan')
            req_type: Requirement type ('blocking', 'guard', 'dynamic')

        Returns:
            RequirementMessages with all message variants

        Raises:
            MessageNotFoundError: If strict=True and no message file found
        """
        cache_key = f"{req_name}:{req_type}"

        if cache_key in self._cache:
            return self._cache[cache_key]

        # Try to find message file
        file_path = self._find_message_file(req_name)

        if file_path:
            data = self._load_yaml(file_path)
            if data:
                messages = self._messages_from_dict(data, req_name, req_type)
                self._cache[cache_key] = messages
                return messages

        # No file found
        if self.strict:
            raise MessageNotFoundError(req_name, self._get_searched_paths(req_name))

        # Use template defaults
        templates = self._load_templates()
        type_defaults = templates.get(req_type, templates.get('blocking', {}))

        messages = RequirementMessages(
            blocking_message=type_defaults.get('blocking_message', ''),
            short_message=type_defaults.get('short_message', ''),
            success_message=type_defaults.get('success_message', ''),
            header=type_defaults.get('header', req_name),
            action_label=type_defaults.get('action_label', ''),
            fallback_text=type_defaults.get('fallback_text', ''),
        )

        self._cache[cache_key] = messages
        return messages

    def _messages_from_dict(self, data: Dict[str, Any], req_name: str,
                           req_type: str) -> RequirementMessages:
        """
        Create RequirementMessages from loaded YAML data.

        Falls back to templates for missing fields.

        Args:
            data: Loaded YAML data
            req_name: Requirement name
            req_type: Requirement type

        Returns:
            RequirementMessages instance
        """
        templates = self._load_templates()
        type_defaults = templates.get(req_type, templates.get('blocking', {}))

        return RequirementMessages(
            blocking_message=data.get('blocking_message',
                                      type_defaults.get('blocking_message', '')),
            short_message=data.get('short_message',
                                   type_defaults.get('short_message', '')),
            success_message=data.get('success_message',
                                     type_defaults.get('success_message', '')),
            header=data.get('header', type_defaults.get('header', req_name)),
            action_label=data.get('action_label',
                                  type_defaults.get('action_label', '')),
            fallback_text=data.get('fallback_text',
                                   type_defaults.get('fallback_text', '')),
        )

    def get_status_template(self, mode: str) -> str:
        """
        Get status format template.

        Args:
            mode: Format mode ('compact', 'standard', 'rich')

        Returns:
            Status template string
        """
        templates = self._load_status_templates()
        return templates.get(mode, templates.get('standard', ''))

    def get_structural(self, key: str, **kwargs) -> str:
        """
        Get structural element (headers, labels, separators).

        Args:
            key: Structural element key (e.g., 'blocked_header')
            **kwargs: Variable substitutions

        Returns:
            Formatted structural element
        """
        structural = self._load_structural()
        template = structural.get(key, '')

        if kwargs:
            # Safe format with placeholders
            pattern = r'\{([a-zA-Z_][a-zA-Z0-9_]*)\}'

            def replacer(match):
                k = match.group(1)
                return str(kwargs.get(k, match.group(0)))

            return re.sub(pattern, replacer, template)

        return template

    def validate_all(self, requirements: List[str]) -> List[str]:
        """
        Validate all message files for given requirements.

        Checks:
        - File exists (in strict mode)
        - All required fields present
        - Fields are non-empty strings

        Args:
            requirements: List of requirement names to validate

        Returns:
            List of validation error messages (empty if all valid)
        """
        errors = []

        for req_name in requirements:
            file_path = self._find_message_file(req_name)

            if not file_path:
                if self.strict:
                    errors.append(
                        f"{req_name}: Message file not found in "
                        f"{[str(p) for p in self._get_searched_paths(req_name)]}"
                    )
                continue

            data = self._load_yaml(file_path)
            if not data:
                errors.append(f"{req_name}: Failed to load {file_path}")
                continue

            # Check required fields
            for field in self.REQUIRED_FIELDS:
                if field not in data:
                    errors.append(f"{req_name}: Missing required field '{field}'")
                elif not isinstance(data[field], str):
                    errors.append(f"{req_name}: Field '{field}' must be a string")
                elif not data[field].strip():
                    errors.append(f"{req_name}: Field '{field}' is empty")

        return errors

    def clear_cache(self) -> None:
        """Clear all cached data."""
        self._cache.clear()
        self._templates = None
        self._status_templates = None
        self._structural = None

    def get_message_file_path(self, req_name: str) -> Optional[Path]:
        """
        Get the resolved path for a requirement's message file.

        Useful for debugging and showing which file is being used.

        Args:
            req_name: Requirement name

        Returns:
            Path to the message file being used, or None if not found
        """
        return self._find_message_file(req_name)
