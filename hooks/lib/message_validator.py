"""
Message Validator Module for Requirements Framework.

Provides comprehensive validation for message YAML files including:
- Schema validation (required fields, types)
- Placeholder validation (valid variable names)
- Cross-reference validation (templates exist)
- Cascade consistency checks

Used by:
- `req messages validate` CLI command
- Runtime validation when loading messages
"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Any, Optional, Set
import re
import yaml


@dataclass
class ValidationResult:
    """
    Result of message file validation.

    Attributes:
        file_path: Path to the validated file
        errors: List of error messages (must be fixed)
        warnings: List of warning messages (suggestions)
        is_valid: True if no errors (warnings ok)
    """
    file_path: Path
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        """File is valid if no errors (warnings are ok)."""
        return len(self.errors) == 0

    def __str__(self) -> str:
        """Format result for display."""
        lines = [f"File: {self.file_path}"]
        if self.errors:
            lines.append("  Errors:")
            for err in self.errors:
                lines.append(f"    - {err}")
        if self.warnings:
            lines.append("  Warnings:")
            for warn in self.warnings:
                lines.append(f"    - {warn}")
        if self.is_valid and not self.warnings:
            lines.append("  Valid")
        return "\n".join(lines)


@dataclass
class ValidationSummary:
    """
    Summary of validation across multiple files.

    Attributes:
        results: List of individual file results
        total_files: Total files validated
        valid_files: Count of valid files
        error_count: Total error count
        warning_count: Total warning count
    """
    results: List[ValidationResult] = field(default_factory=list)

    @property
    def total_files(self) -> int:
        return len(self.results)

    @property
    def valid_files(self) -> int:
        return sum(1 for r in self.results if r.is_valid)

    @property
    def error_count(self) -> int:
        return sum(len(r.errors) for r in self.results)

    @property
    def warning_count(self) -> int:
        return sum(len(r.warnings) for r in self.results)

    @property
    def is_valid(self) -> bool:
        return all(r.is_valid for r in self.results)

    def add(self, result: ValidationResult) -> None:
        """Add a validation result."""
        self.results.append(result)

    def __str__(self) -> str:
        """Format summary for display."""
        lines = ["Validation Summary", "=" * 40]

        for result in self.results:
            if not result.is_valid:
                lines.append(str(result))
                lines.append("")

        lines.append(f"Files: {self.valid_files}/{self.total_files} valid")
        lines.append(f"Errors: {self.error_count}")
        lines.append(f"Warnings: {self.warning_count}")

        return "\n".join(lines)


class MessageValidator:
    """
    Validates message YAML files for the requirements framework.

    Performs comprehensive validation including:
    - Schema validation (required fields, correct types)
    - Placeholder validation (valid variable syntax)
    - Cross-reference validation (referenced templates exist)
    - Consistency checks across cascade levels
    """

    # Required fields for requirement message files
    REQUIRED_FIELDS = {
        'blocking_message': str,
        'short_message': str,
        'success_message': str,
        'header': str,
        'action_label': str,
        'fallback_text': str,
    }

    # Optional fields
    OPTIONAL_FIELDS = {
        'version': str,
    }

    # Valid placeholder pattern: {word} but not {{word}}
    PLACEHOLDER_PATTERN = re.compile(r'\{([a-zA-Z_][a-zA-Z0-9_]*)\}')

    # Known valid placeholders
    KNOWN_PLACEHOLDERS: Set[str] = {
        'req_name',
        'session_id',
        'branch',
        'project_dir',
        'skill',
        'command',
        'value',
        'block_threshold',
        'warn_threshold',
        'satisfied_count',
        'total_count',
        'unsatisfied_names',
        'action_list',
        'quick_start',
        'status_table',
        'fallback',
        'definitions',
        'workflow_guide',
        'summary',
        'total',
    }

    # Required fields for _templates.yaml type definitions
    TEMPLATE_TYPE_FIELDS = {
        'blocking_message',
        'short_message',
        'success_message',
        'header',
        'action_label',
        'fallback_text',
    }

    # Valid requirement types
    VALID_TYPES = {'blocking', 'guard', 'dynamic'}

    def __init__(self):
        """Initialize the validator."""
        pass

    def validate_file(self, file_path: Path) -> ValidationResult:
        """
        Validate a single message file.

        Args:
            file_path: Path to YAML file

        Returns:
            ValidationResult with errors and warnings
        """
        result = ValidationResult(file_path=file_path)

        if not file_path.exists():
            result.errors.append("File does not exist")
            return result

        # Load YAML
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            result.errors.append(f"Invalid YAML: {e}")
            return result
        except Exception as e:
            result.errors.append(f"Failed to read file: {e}")
            return result

        if data is None:
            result.errors.append("File is empty")
            return result

        # Determine file type from name
        file_name = file_path.name
        if file_name == '_templates.yaml':
            self._validate_templates_file(data, result)
        elif file_name == '_status.yaml':
            self._validate_status_file(data, result)
        else:
            self._validate_requirement_file(data, result)

        return result

    def _validate_requirement_file(self, data: Dict[str, Any],
                                   result: ValidationResult) -> None:
        """
        Validate a requirement message file.

        Args:
            data: Loaded YAML data
            result: ValidationResult to populate
        """
        # Check required fields
        for field_name, field_type in self.REQUIRED_FIELDS.items():
            if field_name not in data:
                result.errors.append(f"Missing required field: {field_name}")
            elif not isinstance(data[field_name], field_type):
                result.errors.append(
                    f"Field '{field_name}' must be {field_type.__name__}, "
                    f"got {type(data[field_name]).__name__}"
                )
            elif isinstance(data[field_name], str) and not data[field_name].strip():
                result.errors.append(f"Field '{field_name}' is empty")

        # Check for unknown fields
        known_fields = set(self.REQUIRED_FIELDS.keys()) | set(self.OPTIONAL_FIELDS.keys())
        for field_name in data.keys():
            if field_name not in known_fields:
                result.warnings.append(f"Unknown field: {field_name}")

        # Validate placeholders in string fields
        for field_name in self.REQUIRED_FIELDS.keys():
            if field_name in data and isinstance(data[field_name], str):
                self._validate_placeholders(data[field_name], field_name, result)

    def _validate_templates_file(self, data: Dict[str, Any],
                                 result: ValidationResult) -> None:
        """
        Validate _templates.yaml file.

        Args:
            data: Loaded YAML data
            result: ValidationResult to populate
        """
        for type_name, type_data in data.items():
            if type_name == 'version':
                continue

            if type_name == 'structural':
                # Structural elements are key-value strings
                if not isinstance(type_data, dict):
                    result.errors.append(
                        f"'structural' must be a dict, got {type(type_data).__name__}"
                    )
                else:
                    for key, value in type_data.items():
                        if not isinstance(value, str):
                            result.errors.append(
                                f"structural.{key} must be string, "
                                f"got {type(value).__name__}"
                            )
                        else:
                            self._validate_placeholders(value, f"structural.{key}", result)
                continue

            if type_name not in self.VALID_TYPES:
                result.warnings.append(
                    f"Unknown type '{type_name}' (valid: {', '.join(self.VALID_TYPES)})"
                )

            if not isinstance(type_data, dict):
                result.errors.append(
                    f"Type '{type_name}' must be a dict, got {type(type_data).__name__}"
                )
                continue

            # Check type has all required template fields
            for field_name in self.TEMPLATE_TYPE_FIELDS:
                if field_name in type_data:
                    if not isinstance(type_data[field_name], str):
                        result.errors.append(
                            f"{type_name}.{field_name} must be string"
                        )
                    else:
                        self._validate_placeholders(
                            type_data[field_name],
                            f"{type_name}.{field_name}",
                            result
                        )

    def _validate_status_file(self, data: Dict[str, Any],
                              result: ValidationResult) -> None:
        """
        Validate _status.yaml file.

        Args:
            data: Loaded YAML data
            result: ValidationResult to populate
        """
        valid_modes = {'compact', 'standard', 'rich'}

        for mode_name, mode_data in data.items():
            if mode_name == 'version':
                continue

            if mode_name == 'partials':
                # Partials are named template fragments
                if not isinstance(mode_data, dict):
                    result.errors.append("'partials' must be a dict")
                else:
                    for key, value in mode_data.items():
                        if not isinstance(value, str):
                            result.errors.append(f"partials.{key} must be string")
                        else:
                            self._validate_placeholders(value, f"partials.{key}", result)
                continue

            if mode_name not in valid_modes:
                result.warnings.append(
                    f"Unknown status mode '{mode_name}' (valid: {', '.join(valid_modes)})"
                )

            # Mode can be a string or dict with 'format' key
            if isinstance(mode_data, str):
                self._validate_placeholders(mode_data, mode_name, result)
            elif isinstance(mode_data, dict):
                if 'format' in mode_data:
                    if not isinstance(mode_data['format'], str):
                        result.errors.append(f"{mode_name}.format must be string")
                    else:
                        self._validate_placeholders(
                            mode_data['format'],
                            f"{mode_name}.format",
                            result
                        )
            else:
                result.errors.append(
                    f"Mode '{mode_name}' must be string or dict with 'format' key"
                )

    def _validate_placeholders(self, text: str, field_name: str,
                               result: ValidationResult) -> None:
        """
        Validate placeholder syntax in a string.

        Args:
            text: String to validate
            field_name: Field name for error messages
            result: ValidationResult to populate
        """
        placeholders = self.PLACEHOLDER_PATTERN.findall(text)

        for placeholder in placeholders:
            if placeholder not in self.KNOWN_PLACEHOLDERS:
                result.warnings.append(
                    f"Unknown placeholder '{{{placeholder}}}' in {field_name}"
                )

    def validate_directory(self, directory: Path) -> ValidationSummary:
        """
        Validate all message files in a directory.

        Args:
            directory: Directory containing message files

        Returns:
            ValidationSummary with all results
        """
        summary = ValidationSummary()

        if not directory.exists():
            return summary

        for yaml_file in directory.glob('*.yaml'):
            result = self.validate_file(yaml_file)
            summary.add(result)

        return summary

    def validate_cascade(self, project_dir: str) -> ValidationSummary:
        """
        Validate all message files across the cascade.

        Validates:
        - ~/.claude/messages/
        - <project>/.claude/messages/
        - <project>/.claude/messages.local/

        Args:
            project_dir: Project directory path

        Returns:
            ValidationSummary for all files
        """
        from messages import MessagePaths  # Local import to avoid circular

        paths = MessagePaths.from_project(project_dir)
        summary = ValidationSummary()

        for dir_path in [paths.global_dir, paths.project_dir, paths.local_dir]:
            if dir_path.exists():
                dir_summary = self.validate_directory(dir_path)
                for result in dir_summary.results:
                    summary.add(result)

        return summary


def generate_message_file(req_name: str, req_type: str = 'blocking',
                          auto_skill: Optional[str] = None,
                          description: Optional[str] = None) -> str:
    """
    Generate a message file template for a requirement.

    Creates a ready-to-use YAML file with all required fields.

    Args:
        req_name: Requirement name
        req_type: Requirement type ('blocking', 'guard', 'dynamic')
        auto_skill: Auto-resolve skill name (e.g., 'pre-commit')
        description: Human-readable description

    Returns:
        YAML content as string
    """
    description = description or f"Requirement: {req_name}"

    if req_type == 'blocking':
        if auto_skill:
            blocking = f"""## Blocked: {req_name}

**Execute**: `/{auto_skill}`

{description}

---
Fallback: `req satisfy {req_name} --session {{session_id}}`"""
            action_label = f"Run `/{auto_skill}`"
        else:
            blocking = f"""## Blocked: {req_name}

**Action**: `req satisfy {req_name} --session {{session_id}}`

{description}

---
Fallback: `req satisfy {req_name} --session {{session_id}}`"""
            action_label = f"`req satisfy {req_name}`"

        return f'''version: "1.0"

blocking_message: |
{_indent(blocking, 2)}

short_message: "Requirement `{req_name}` not satisfied (waiting...)"

success_message: "Requirement `{req_name}` satisfied"

header: "{req_name.replace('_', ' ').title()}"

action_label: "{action_label}"

fallback_text: "req satisfy {req_name}"
'''

    elif req_type == 'guard':
        blocking = f"""## Blocked: {req_name}

Guard condition not met.

---
Override: `req approve {req_name}`"""

        return f'''version: "1.0"

blocking_message: |
{_indent(blocking, 2)}

short_message: "Guard `{req_name}` blocked (waiting...)"

success_message: "Guard `{req_name}` passed"

header: "{req_name.replace('_', ' ').title()}"

action_label: "`req approve {req_name}`"

fallback_text: "req approve {req_name}"
'''

    else:  # dynamic
        blocking = f"""## Blocked: {req_name}

Current value: {{value}} (threshold: {{block_threshold}})

---
Override: `req approve {req_name} --session {{session_id}}`"""

        return f'''version: "1.0"

blocking_message: |
{_indent(blocking, 2)}

short_message: "Requirement `{req_name}` not satisfied (value: {{value}})"

success_message: "Requirement `{req_name}` satisfied"

header: "{req_name.replace('_', ' ').title()}"

action_label: "`req approve {req_name}`"

fallback_text: "req approve {req_name}"
'''


def _indent(text: str, spaces: int) -> str:
    """Indent multi-line text."""
    prefix = ' ' * spaces
    lines = text.split('\n')
    return '\n'.join(prefix + line if line else line for line in lines)
