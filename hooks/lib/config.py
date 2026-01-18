#!/usr/bin/env python3
"""
Configuration loading for requirements framework.

Implements cascading configuration:
1. Global defaults (~/.claude/requirements.yaml)
2. Project config (.claude/requirements.yaml) - committed to repo
3. Local overrides (.claude/requirements.local.yaml) - git ignored

Config files are YAML (PyYAML required).
"""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import (
    Any,
    Callable,
    Literal,
    Mapping,
    MutableMapping,
    Optional,
    Protocol,
    TypedDict,
    Union,
    cast,
)

# Import utilities from config_utils (the canonical location)
from config_utils import (
    deep_merge,
    load_yaml,
    matches_trigger,
    write_local_config,
    write_project_config,
)
from console import configure_console
from logger import configure_logger, get_logger
from progress import configure_progress

# Re-export for backwards compatibility - external code can still import from config
__all__ = [
    "RequirementsConfig",
    "RequirementConfigAccess",
    "HookConfigAccess",
    "ConfigStateAccess",
    "ConfigOverridesWriter",
    "ConfigIO",
    "ConfigUtilsIO",
    "matches_trigger",
    "load_yaml",
    "deep_merge",
    "write_local_config",
    "write_project_config",
]


RequirementScope = Literal["session", "branch", "permanent", "single_use"]
RequirementType = Literal["blocking", "dynamic", "guard"]


class TriggerToolConfig(TypedDict, total=False):
    tool: str
    command_pattern: str


TriggerSpec = Union[str, TriggerToolConfig]


# Type-safe requirement configuration classes
# These provide explicit contracts for each requirement type with proper LSP compliance


class RequirementConfigBase(TypedDict, total=False):
    """Base configuration fields shared by all requirement types."""

    enabled: bool
    scope: RequirementScope
    trigger_tools: list[TriggerSpec]
    checklist: list[str]
    message: str
    short_message: str  # Brief message for deduplication scenarios
    satisfied_by_skill: str
    auto_resolve_skill: str  # Skill command for autonomous resolution


class BlockingRequirementConfig(RequirementConfigBase, total=False):
    """Configuration for blocking (manually satisfied) requirements.

    Inherits all base fields with no additional required fields.
    """

    type: Literal["blocking"]


class DynamicRequirementConfig(RequirementConfigBase):
    """Configuration for dynamic (calculated) requirements.

    Inherits base fields and adds REQUIRED calculator and thresholds fields.
    """

    type: Literal["dynamic"]
    calculator: str  # REQUIRED
    thresholds: dict[str, float]  # REQUIRED


class GuardRequirementConfig(RequirementConfigBase):
    """Configuration for guard (condition-based) requirements.

    Inherits base fields and adds REQUIRED guard_type field.
    """

    type: Literal["guard"]
    guard_type: str  # REQUIRED
    protected_branches: list[str]  # Optional


# Union for polymorphic access
RequirementConfig = Union[
    BlockingRequirementConfig,
    DynamicRequirementConfig,
    GuardRequirementConfig,
]


# Legacy TypedDict - DEPRECATED
# Use typed configs above for type-safe access to requirement-specific fields
class RequirementConfigDict(TypedDict, total=False):
    enabled: bool
    scope: RequirementScope
    trigger_tools: list[TriggerSpec]
    checklist: list[str]
    message: str
    short_message: str  # Brief message for deduplication scenarios
    type: RequirementType
    satisfied_by_skill: str
    auto_resolve_skill: str  # Skill command for autonomous resolution
    calculator: str
    thresholds: dict[str, float]
    guard_type: str
    protected_branches: list[str]


class LoggingConfigDict(TypedDict, total=False):
    level: str
    destinations: list[str]
    file: str


class ConsoleConfigDict(TypedDict, total=False):
    level: str
    destinations: list[str]
    file: str


class DebugConfigDict(TypedDict, total=False):
    """Debug configuration for progress and timing.

    These settings can also be controlled via environment variables:
    - SHOW_PROGRESS=1/0: Enable/disable progress indicators
    - NO_COLOR=1: Disable all progress (respects https://no-color.org/)
    - FORCE_COLOR=1: Force progress even in non-TTY

    Config settings take precedence over environment variables.
    """
    show_progress: bool  # Show progress indicators (default: auto-detect TTY)
    timing_threshold: float  # Min duration (seconds) before showing progress (default: 0.3)


class HookConfigDict(TypedDict, total=False):
    inject_context: bool
    verify_requirements: bool
    verify_scopes: list[RequirementScope]
    clear_session_state: bool
    custom_header: str  # Custom header text for session start


HooksConfigDict = dict[str, HookConfigDict]


class RequirementsConfigData(TypedDict, total=False):
    version: str
    enabled: bool
    inherit: bool
    requirements: dict[str, RequirementConfigDict]
    logging: LoggingConfigDict
    console: ConsoleConfigDict
    hooks: HooksConfigDict
    debug: DebugConfigDict


RequirementOverrideValue = Union[bool, RequirementConfigDict, Mapping[str, Any]]
RequirementOverrides = Mapping[str, RequirementOverrideValue]
ConfigWriter = Callable[[str, RequirementsConfigData], str]
RequirementFieldValidator = Callable[[str, Any], None]
RequirementTypeValidator = Callable[[str, Mapping[str, Any]], None]


class RequirementConfigAccess(Protocol):
    def get_requirement(self, name: str) -> Optional[RequirementConfigDict]:
        ...

    def get_all_requirements(self) -> list[str]:
        ...

    def is_requirement_enabled(self, name: str) -> bool:
        ...

    def get_scope(self, name: str) -> RequirementScope:
        ...

    def get_trigger_tools(self, name: str) -> list[str]:
        ...

    def get_triggers(self, name: str) -> list[TriggerSpec]:
        ...

    def get_message(self, name: str) -> str:
        ...

    def get_checklist(self, name: str) -> list[str]:
        ...

    def get_attribute(self, req_name: str, attr: str, default: Any = None) -> Any:
        ...

    def get_blocking_config(self, req_name: str) -> Optional[BlockingRequirementConfig]:
        ...

    def get_dynamic_config(self, req_name: str) -> Optional[DynamicRequirementConfig]:
        ...

    def get_guard_config(self, req_name: str) -> Optional[GuardRequirementConfig]:
        ...

    def get_requirement_type(self, req_name: str) -> RequirementType:
        ...

    def validate_dynamic_requirement(self, req_name: str) -> None:
        ...


class HookConfigAccess(Protocol):
    def get_hook_config(self, hook_name: str, key: str, default: Any = None) -> Any:
        ...


class ConfigStateAccess(Protocol):
    def is_enabled(self) -> bool:
        ...

    def get_validation_errors(self) -> list[str]:
        ...

    def get_raw_config(self) -> RequirementsConfigData:
        ...

    def get_logging_config(self) -> LoggingConfigDict:
        ...

    def get_console_config(self) -> ConsoleConfigDict:
        ...


class ConfigOverridesWriter(Protocol):
    def write_local_override(
        self,
        enabled: Optional[bool] = None,
        requirement_overrides: Optional[RequirementOverrides] = None,
        logging_config: Optional[LoggingConfigDict] = None,
    ) -> str:
        ...

    def write_project_override(
        self,
        enabled: Optional[bool] = None,
        requirement_overrides: Optional[RequirementOverrides] = None,
        preserve_inherit: bool = True,
        logging_config: Optional[LoggingConfigDict] = None,
    ) -> str:
        ...


class ConfigIO(Protocol):
    load_yaml: Callable[[Path], RequirementsConfigData]
    deep_merge: Callable[
        [MutableMapping[str, Any], Mapping[str, Any]], MutableMapping[str, Any]
    ]
    write_local_config: ConfigWriter
    write_project_config: ConfigWriter


@dataclass(frozen=True)
class ConfigUtilsIO:
    load_yaml: Callable[[Path], RequirementsConfigData] = load_yaml
    deep_merge: Callable[
        [MutableMapping[str, Any], Mapping[str, Any]], MutableMapping[str, Any]
    ] = deep_merge
    write_local_config: ConfigWriter = write_local_config
    write_project_config: ConfigWriter = write_project_config


@dataclass(frozen=True)
class RequirementConfigView(RequirementConfigAccess):
    _config: "RequirementsConfig"

    def get_requirement(self, name: str) -> Optional[RequirementConfigDict]:
        return self._config.get_requirement(name)

    def get_all_requirements(self) -> list[str]:
        return self._config.get_all_requirements()

    def is_requirement_enabled(self, name: str) -> bool:
        return self._config.is_requirement_enabled(name)

    def get_scope(self, name: str) -> RequirementScope:
        return self._config.get_scope(name)

    def get_trigger_tools(self, name: str) -> list[str]:
        return self._config.get_trigger_tools(name)

    def get_triggers(self, name: str) -> list[TriggerSpec]:
        return self._config.get_triggers(name)

    def get_message(self, name: str) -> str:
        return self._config.get_message(name)

    def get_checklist(self, name: str) -> list[str]:
        return self._config.get_checklist(name)

    def get_attribute(self, req_name: str, attr: str, default: Any = None) -> Any:
        return self._config.get_attribute(req_name, attr, default)

    def get_blocking_config(self, req_name: str) -> Optional[BlockingRequirementConfig]:
        return self._config.get_blocking_config(req_name)

    def get_dynamic_config(self, req_name: str) -> Optional[DynamicRequirementConfig]:
        return self._config.get_dynamic_config(req_name)

    def get_guard_config(self, req_name: str) -> Optional[GuardRequirementConfig]:
        return self._config.get_guard_config(req_name)

    def get_requirement_type(self, req_name: str) -> RequirementType:
        return self._config.get_requirement_type(req_name)

    def validate_dynamic_requirement(self, req_name: str) -> None:
        self._config.validate_dynamic_requirement(req_name)


@dataclass(frozen=True)
class HookConfigView(HookConfigAccess):
    _config: "RequirementsConfig"

    def get_hook_config(self, hook_name: str, key: str, default: Any = None) -> Any:
        return self._config.get_hook_config(hook_name, key, default)


@dataclass(frozen=True)
class ConfigStateView(ConfigStateAccess):
    _config: "RequirementsConfig"

    def is_enabled(self) -> bool:
        return self._config.is_enabled()

    def get_validation_errors(self) -> list[str]:
        return self._config.get_validation_errors()

    def get_raw_config(self) -> RequirementsConfigData:
        return self._config.get_raw_config()

    def get_logging_config(self) -> LoggingConfigDict:
        return self._config.get_logging_config()

    def get_console_config(self) -> ConsoleConfigDict:
        return self._config.get_console_config()


@dataclass(frozen=True)
class ConfigOverridesView(ConfigOverridesWriter):
    _config: "RequirementsConfig"

    def write_local_override(
        self,
        enabled: Optional[bool] = None,
        requirement_overrides: Optional[RequirementOverrides] = None,
        logging_config: Optional[LoggingConfigDict] = None,
    ) -> str:
        return self._config.write_local_override(
            enabled=enabled,
            requirement_overrides=requirement_overrides,
            logging_config=logging_config,
        )

    def write_project_override(
        self,
        enabled: Optional[bool] = None,
        requirement_overrides: Optional[RequirementOverrides] = None,
        preserve_inherit: bool = True,
        logging_config: Optional[LoggingConfigDict] = None,
    ) -> str:
        return self._config.write_project_override(
            enabled=enabled,
            requirement_overrides=requirement_overrides,
            preserve_inherit=preserve_inherit,
            logging_config=logging_config,
        )


@dataclass(frozen=True)
class RequirementFieldRule:
    expected_type: type
    allowed: Optional[set[str]] = None
    element_type: Optional[type] = None


@dataclass(frozen=True)
class ConfigPaths:
    project_root: Path
    claude_dirname: str
    project_config_filename: str
    local_override_filenames: tuple[str, ...]

    def global_config_path(self) -> Path:
        return Path.home() / self.claude_dirname / self.project_config_filename

    def project_config_dir(self) -> Path:
        return self.project_root / self.claude_dirname

    def project_config_path(self) -> Path:
        return self.project_config_dir() / self.project_config_filename

    def local_override_paths(self) -> list[Path]:
        claude_dir = self.project_config_dir()
        return [claude_dir / filename for filename in self.local_override_filenames]


@dataclass(frozen=True)
class ValidationIssue:
    requirement: str
    error: ValueError


class RequirementValidator:
    def __init__(
        self,
        schema: Mapping[str, RequirementFieldRule],
        field_validators: Optional[Mapping[str, RequirementFieldValidator]] = None,
        type_validators: Optional[Mapping[str, RequirementTypeValidator]] = None,
    ) -> None:
        self._schema = dict(schema)
        self._field_validators: dict[str, RequirementFieldValidator] = {}
        self._type_validators: dict[str, RequirementTypeValidator] = {}

        # Register built-in validators; callers can extend/override via registries.
        self.register_field_validator("trigger_tools", self._validate_trigger_tools)
        self.register_type_validator("dynamic", self._validate_dynamic_fields)
        self.register_type_validator("blocking", self._validate_blocking_fields)
        self.register_type_validator("guard", self._validate_guard_fields)

        if field_validators:
            for field, validator in field_validators.items():
                self.register_field_validator(field, validator)
        if type_validators:
            for req_type, validator in type_validators.items():
                self.register_type_validator(req_type, validator)

    def register_field_validator(
        self, field: str, validator: RequirementFieldValidator
    ) -> None:
        self._field_validators[field] = validator

    def register_type_validator(
        self, req_type: str, validator: RequirementTypeValidator
    ) -> None:
        self._type_validators[req_type] = validator

    def validate_requirements(
        self, requirements: MutableMapping[str, RequirementConfigDict]
    ) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        for req_name in list(requirements.keys()):
            try:
                self.validate_requirement(req_name, requirements[req_name])
            except ValueError as error:
                issues.append(ValidationIssue(req_name, error))
        return issues

    def validate_requirement(self, req_name: str, req_config: Mapping[str, Any]) -> None:
        req_type = req_config.get("type", "blocking")

        # Validate common fields present on all requirements
        self._validate_requirement_schema(req_name, req_config)

        # Validate satisfied_by_skill if present (applies to all types)
        self._validate_satisfied_by_skill(req_name, req_config)

        # Validate auto_resolve_skill if present (applies to all types)
        self._validate_auto_resolve_skill(req_name, req_config)

        self._validate_requirement_type(req_name, req_config, req_type)

    def _validate_requirement_type(
        self, req_name: str, req_config: Mapping[str, Any], req_type: str
    ) -> None:
        validator = self._type_validators.get(req_type)
        if validator is None:
            allowed_values = ", ".join(
                f"'{value}'" for value in sorted(self._type_validators.keys())
            )
            raise ValueError(
                f"Requirement '{req_name}' has unknown type '{req_type}'. "
                f"Valid types: {allowed_values}"
            )
        validator(req_name, req_config)

    def validate_dynamic_requirement(
        self, req_name: str, req_config: Mapping[str, Any]
    ) -> None:
        if req_config.get("type") != "dynamic":
            return
        self._validate_requirement_type(req_name, req_config, "dynamic")

    def _validate_requirement_schema(
        self, req_name: str, req_config: Mapping[str, Any]
    ) -> None:
        """Validate common requirement fields against schema."""
        for field, rules in self._schema.items():
            if field not in req_config:
                continue

            value = req_config[field]
            expected_type = rules.expected_type

            if expected_type is list:
                if not isinstance(value, list):
                    raise ValueError(f"Requirement '{req_name}' field '{field}' must be a list")

                element_type = rules.element_type
                if element_type:
                    invalid_items = [
                        item for item in value if not isinstance(item, element_type)
                    ]
                    if invalid_items:
                        raise ValueError(
                            f"Requirement '{req_name}' field '{field}' must contain only strings"
                        )
            else:
                if not isinstance(value, expected_type):
                    raise ValueError(
                        f"Requirement '{req_name}' field '{field}' must be {expected_type.__name__}"
                    )

            field_validator = self._field_validators.get(field)
            if field_validator is not None:
                field_validator(req_name, value)

            if rules.allowed is not None and value not in rules.allowed:
                allowed_values = ", ".join(sorted(rules.allowed))
                raise ValueError(
                    f"Requirement '{req_name}' field '{field}' must be one of: {allowed_values}"
                )

    def _validate_trigger_tools(
        self, req_name: str, triggers: list[TriggerSpec]
    ) -> None:
        """
        Validate trigger_tools configuration.

        Allows two formats:
        1. Simple string: 'Edit' - tool name
        2. Complex object: {tool: 'Bash', command_pattern: 'regex'}

        Args:
            req_name: Requirement name (for error messages)
            triggers: List of triggers to validate

        Raises:
            ValueError: If any trigger is invalid
        """
        for i, trigger in enumerate(triggers):
            self._validate_trigger_tool(req_name, i, trigger)

    def _validate_trigger_tool(
        self, req_name: str, index: int, trigger: TriggerSpec
    ) -> None:
        if isinstance(trigger, str):
            # Simple tool name - valid
            return
        if not isinstance(trigger, dict):
            raise ValueError(
                f"Requirement '{req_name}' trigger_tools[{index}]: "
                f"must be string or dict, got {type(trigger).__name__}"
            )

        # Complex trigger - validate structure
        if "tool" not in trigger:
            raise ValueError(
                f"Requirement '{req_name}' trigger_tools[{index}]: "
                f"dict trigger must have 'tool' field"
            )
        if not isinstance(trigger["tool"], str):
            raise ValueError(
                f"Requirement '{req_name}' trigger_tools[{index}]: 'tool' must be a string"
            )
        # Validate command_pattern is valid regex if present
        if "command_pattern" in trigger:
            pattern = trigger["command_pattern"]
            if not isinstance(pattern, str):
                raise ValueError(
                    f"Requirement '{req_name}' trigger_tools[{index}]: "
                    f"'command_pattern' must be a string"
                )
            try:
                re.compile(pattern)
            except re.error as e:
                raise ValueError(
                    f"Requirement '{req_name}' trigger_tools[{index}]: "
                    f"invalid regex pattern '{pattern}': {e}"
                )

    def _validate_satisfied_by_skill(
        self, req_name: str, req_config: Mapping[str, Any]
    ) -> None:
        """Validate satisfied_by_skill if present."""
        if "satisfied_by_skill" not in req_config:
            return

        skill_name = req_config["satisfied_by_skill"]
        if not isinstance(skill_name, str):
            raise ValueError(
                f"Requirement '{req_name}' field 'satisfied_by_skill' must be a string"
            )
        if not skill_name.strip():
            raise ValueError(f"Requirement '{req_name}' field 'satisfied_by_skill' cannot be empty")

    def _validate_auto_resolve_skill(
        self, req_name: str, req_config: Mapping[str, Any]
    ) -> None:
        """Validate auto_resolve_skill if present."""
        if "auto_resolve_skill" not in req_config:
            return

        skill_name = req_config["auto_resolve_skill"]
        if not isinstance(skill_name, str):
            raise ValueError(
                f"Requirement '{req_name}' field 'auto_resolve_skill' must be a string"
            )
        if not skill_name.strip():
            raise ValueError(f"Requirement '{req_name}' field 'auto_resolve_skill' cannot be empty")

    def _validate_blocking_fields(
        self, req_name: str, req_config: Mapping[str, Any]
    ) -> None:
        """Validate blocking requirement specific fields."""
        enabled = req_config.get("enabled")
        if enabled is not None and not isinstance(enabled, bool):
            raise ValueError(
                f"Requirement '{req_name}' enabled must be boolean, got {type(enabled).__name__}"
            )

    def _validate_guard_fields(self, req_name: str, req_config: Mapping[str, Any]) -> None:
        """Validate guard requirement specific fields."""
        guard_type = req_config.get("guard_type")
        if not guard_type:
            raise ValueError(f"Guard requirement '{req_name}' must have 'guard_type' field")
        protected = req_config.get("protected_branches")
        if protected is not None and not isinstance(protected, list):
            raise ValueError(f"Requirement '{req_name}' protected_branches must be a list")

    def _validate_dynamic_fields(
        self, req_name: str, req_config: Mapping[str, Any]
    ) -> None:
        """
        Validate dynamic requirement specific fields.

        Args:
            req_name: Requirement name
            req_config: Requirement configuration dict

        Raises:
            ValueError: If dynamic configuration is invalid
        """
        # Required: calculator
        if not req_config.get("calculator"):
            raise ValueError(
                f"Dynamic requirement '{req_name}' missing required 'calculator' field"
            )

        # Required: thresholds.block
        thresholds = req_config.get("thresholds", {})
        if "block" not in thresholds:
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
        calculator = req_config["calculator"]
        try:
            __import__(calculator)
        except ImportError:
            raise ValueError(
                f"Dynamic requirement '{req_name}' calculator module '{calculator}' not found. "
                f"Expected file: ~/.claude/hooks/lib/{calculator}.py"
            )


class RequirementsConfig:
    """
    Configuration manager for requirements framework.

    Loads and merges configuration from global, project, and local sources.
    Use segregated views (requirements, hooks, state, overrides) when you only
    need a narrow slice of behavior.
    """

    REQUIREMENT_SCHEMA: dict[str, RequirementFieldRule] = {
        "enabled": RequirementFieldRule(bool),
        "scope": RequirementFieldRule(
            str, allowed={"session", "branch", "permanent", "single_use"}
        ),
        "trigger_tools": RequirementFieldRule(list),  # Validated separately
        "checklist": RequirementFieldRule(list, element_type=str),
        "message": RequirementFieldRule(str),
        "type": RequirementFieldRule(str, allowed={"blocking", "dynamic", "guard"}),
        "satisfied_by_skill": RequirementFieldRule(str),
        "auto_resolve_skill": RequirementFieldRule(str),  # Skill for autonomous resolution
    }
    DEFAULT_TRIGGER_TOOLS: tuple[str, ...] = ("Edit", "Write", "MultiEdit")
    DEFAULT_VERSION: str = "1.0"
    CLAUDE_DIRNAME: str = ".claude"
    PROJECT_CONFIG_FILENAME: str = "requirements.yaml"
    LOCAL_OVERRIDE_FILENAMES: tuple[str, ...] = ("requirements.local.yaml",)
    HOOK_DEFAULTS: HooksConfigDict = {
        "session_start": {
            "inject_context": True,
            "injection_mode": "auto",  # auto | compact | standard | rich
        },
        "stop": {
            "verify_requirements": True,
            "verify_scopes": ["session"],
        },
        "session_end": {
            "clear_session_state": False,
        },
    }

    def __init__(
        self,
        project_dir: str,
        requirement_schema: Optional[Mapping[str, RequirementFieldRule]] = None,
        field_validators: Optional[Mapping[str, RequirementFieldValidator]] = None,
        type_validators: Optional[Mapping[str, RequirementTypeValidator]] = None,
        *,
        config_io: Optional[ConfigIO] = None,
    ):
        """
        Initialize config for project.

        Args:
            project_dir: Project root directory
            requirement_schema: Optional schema override for requirement fields
            field_validators: Optional field-specific validators keyed by field name
            type_validators: Optional requirement-type validators keyed by type name
            config_io: Optional config I/O provider for load/merge/write operations
        """
        self.project_dir: str = project_dir
        self._project_root: Path = Path(project_dir)
        self._io: ConfigIO = config_io or ConfigUtilsIO()
        self._paths = ConfigPaths(
            project_root=self._project_root,
            claude_dirname=self.CLAUDE_DIRNAME,
            project_config_filename=self.PROJECT_CONFIG_FILENAME,
            local_override_filenames=self.LOCAL_OVERRIDE_FILENAMES,
        )
        self._validator = RequirementValidator(
            requirement_schema or self.REQUIREMENT_SCHEMA,
            field_validators=field_validators,
            type_validators=type_validators,
        )
        self.validation_errors: list[str] = []
        self._config: RequirementsConfigData = self._load_cascade()
        configure_console(self._config.get("console"))
        configure_logger(self._config.get("logging"))
        self._configure_progress()
        self._requirements_view = RequirementConfigView(self)
        self._hooks_view = HookConfigView(self)
        self._state_view = ConfigStateView(self)
        self._overrides_view = ConfigOverridesView(self)

    def _configure_progress(self) -> None:
        """Configure progress module from debug config."""
        debug_config = self._config.get("debug", {})
        if debug_config:
            configure_progress(
                show_progress=debug_config.get("show_progress"),
                timing_threshold=debug_config.get("timing_threshold"),
            )

    @property
    def requirements(self) -> RequirementConfigAccess:
        return self._requirements_view

    @property
    def hooks(self) -> HookConfigAccess:
        return self._hooks_view

    @property
    def state(self) -> ConfigStateAccess:
        return self._state_view

    @property
    def overrides(self) -> ConfigOverridesWriter:
        return self._overrides_view

    def _base_config(self) -> RequirementsConfigData:
        """Return a fresh default config skeleton."""
        return {
            "requirements": {},
            "logging": {
                "level": "error",
                "destinations": ["file"],
            },
            "console": {
                "level": "error",
                "destinations": [],
            },
        }

    def _load_config(self, path: Path) -> RequirementsConfigData:
        """Load configuration from an existing path."""
        return cast(RequirementsConfigData, self._io.load_yaml(path) or {})

    def _load_config_if_exists(self, path: Path) -> RequirementsConfigData:
        """Load configuration from path if it exists."""
        if not path.exists():
            return cast(RequirementsConfigData, {})
        return self._load_config(path)

    def _load_first_existing_config(self, paths: list[Path]) -> RequirementsConfigData:
        """Load the first existing config file from a list of paths."""
        for path in paths:
            if path.exists():
                return self._load_config(path)
        return cast(RequirementsConfigData, {})

    def _default_trigger_tools(self) -> list[str]:
        """Return a new list of default trigger tools."""
        return list(self.DEFAULT_TRIGGER_TOOLS)

    def _get_trigger_config(self, name: str) -> list[TriggerSpec]:
        """Return trigger config for a requirement with defaults."""
        triggers = self.get_attribute(
            name, "trigger_tools", self._default_trigger_tools()
        )
        return cast(list[TriggerSpec], triggers)

    def _extract_trigger_tool_names(self, triggers: list[TriggerSpec]) -> list[str]:
        """Extract tool names from trigger definitions for legacy callers."""
        tool_names = []
        for trigger in triggers:
            if isinstance(trigger, str):
                tool_names.append(trigger)
            elif isinstance(trigger, dict):
                tool_names.append(trigger.get("tool", ""))
        return tool_names

    def _ensure_version(self, config: MutableMapping[str, Any]) -> None:
        """Ensure the config has a version field."""
        if "version" not in config:
            config["version"] = self.DEFAULT_VERSION

    def _apply_requirement_overrides(
        self,
        config: MutableMapping[str, Any],
        requirement_overrides: Optional[RequirementOverrides],
    ) -> None:
        """Apply requirement-level overrides to a config dict."""
        if not requirement_overrides:
            return

        requirements = cast(
            MutableMapping[str, RequirementConfigDict],
            config.setdefault("requirements", {}),
        )
        for req_name, req_update in requirement_overrides.items():
            req_config = requirements.setdefault(req_name, {})

            # Handle both boolean (simple enable/disable) and dict (full config) values
            if isinstance(req_update, bool):
                req_config["enabled"] = req_update
            elif isinstance(req_update, dict):
                # Merge dict updates (preserves existing fields not in update)
                req_config.update(req_update)
            else:
                req_config["enabled"] = req_update

    def _apply_override_updates(
        self,
        config: MutableMapping[str, Any],
        enabled: Optional[bool],
        requirement_overrides: Optional[RequirementOverrides],
        logging_config: Optional[LoggingConfigDict] = None,
    ) -> None:
        """Apply common override updates for enabled, requirements, and logging."""
        if enabled is not None:
            config["enabled"] = enabled

        self._apply_requirement_overrides(config, requirement_overrides)

        if logging_config is not None:
            # Validate logging_config structure before merging
            if not isinstance(logging_config, dict):
                raise ValueError(f"logging_config must be a dict, got {type(logging_config).__name__}")

            # Merge with existing logging config (if any)
            existing_logging = config.get("logging", {})
            if isinstance(existing_logging, dict):
                existing_logging.update(logging_config)
                config["logging"] = existing_logging
            else:
                # Log replacement of malformed config
                get_logger().warning(
                    "Replacing malformed logging config",
                    was_type=type(existing_logging).__name__,
                    expected_type="dict",
                )
                config["logging"] = logging_config

        self._ensure_version(config)

    def _write_override_config(
        self,
        config: RequirementsConfigData,
        enabled: Optional[bool],
        requirement_overrides: Optional[RequirementOverrides],
        writer: ConfigWriter,
        logging_config: Optional[LoggingConfigDict] = None,
    ) -> str:
        """Apply overrides and persist config with the provided writer."""
        self._apply_override_updates(config, enabled, requirement_overrides, logging_config)
        return writer(self.project_dir, config)

    def _record_validation_error(self, error: ValueError) -> None:
        """Track and emit a validation error."""
        message = str(error)
        get_logger().warning(f"⚠️ Config validation error: {message}")
        self.validation_errors.append(message)

    def _merge_project_config(
        self, config: RequirementsConfigData, project_config: RequirementsConfigData
    ) -> RequirementsConfigData:
        """Merge project config into base config with inherit handling."""
        if project_config.get("inherit", True):
            self._io.deep_merge(config, project_config)
            return config
        return project_config

    def _apply_local_overrides(
        self, config: MutableMapping[str, Any], local_config: RequirementsConfigData
    ) -> None:
        """Apply local overrides onto the current config."""
        if local_config:
            self._io.deep_merge(config, local_config)

    def _validate_and_prune_requirements(self, config: MutableMapping[str, Any]) -> None:
        """Validate requirements and remove invalid entries."""
        requirements = cast(
            MutableMapping[str, RequirementConfigDict],
            config.get("requirements", {}),
        )
        issues = self._validator.validate_requirements(requirements)
        for issue in issues:
            self._record_validation_error(issue.error)
            del requirements[issue.requirement]
            get_logger().warning(f"⚠️ Disabled invalid requirement: {issue.requirement}")

    def _load_cascade(self) -> RequirementsConfigData:
        """
        Load configuration cascade: global → project → local.

        Also validates requirements to catch configuration errors early.

        Returns:
            Merged and validated configuration dictionary
        """
        config = self._base_config()

        # 1. Global defaults
        global_config = self._load_config_if_exists(self._paths.global_config_path())
        if global_config:
            config = cast(RequirementsConfigData, global_config.copy())

        # 2. Project config (versioned)
        project_config = self._load_config_if_exists(self._paths.project_config_path())
        if project_config:
            config = self._merge_project_config(config, project_config)

        # 3. Local overrides (gitignored)
        local_config = self._load_first_existing_config(self._paths.local_override_paths())
        self._apply_local_overrides(config, local_config)

        # 4. Validate requirements (fail-safe: remove invalid ones)
        self._validate_and_prune_requirements(config)

        return config

    def get_validation_errors(self) -> list[str]:
        """Return any validation errors encountered while loading config."""
        return list(self.validation_errors)

    def is_enabled(self) -> bool:
        """
        Check if framework enabled for this project.

        Returns:
            True if enabled, False if disabled
        """
        return self._config.get("enabled", True)

    def write_local_override(
        self,
        enabled: Optional[bool] = None,
        requirement_overrides: Optional[RequirementOverrides] = None,
        logging_config: Optional[LoggingConfigDict] = None,
    ) -> str:
        """
        Write local configuration override to .claude/requirements.local.yaml.

        This creates or updates a gitignored local config file that overrides
        project and global settings. Use this for personal preferences that
        shouldn't affect the team.

        Args:
            enabled: Framework enabled state (None = don't change)
            requirement_overrides: Dict of requirement names to their enabled state
                                  e.g., {'commit_plan': False, 'github_ticket': True}
            logging_config: Logging configuration dict with optional keys: level, destinations, file
                           e.g., {'level': 'debug', 'destinations': ['file', 'stdout']}

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

            # Set debug logging
            config.write_local_override(
                logging_config={'level': 'debug', 'destinations': ['file']}
            )
        """
        # Load existing local config if it exists
        existing_config = self._load_first_existing_config(self._paths.local_override_paths())

        return self._write_override_config(
            existing_config,
            enabled,
            requirement_overrides,
            self._io.write_local_config,
            logging_config,
        )

    def write_project_override(
        self,
        enabled: Optional[bool] = None,
        requirement_overrides: Optional[RequirementOverrides] = None,
        preserve_inherit: bool = True,
        logging_config: Optional[LoggingConfigDict] = None,
    ) -> str:
        """
        Write project configuration to .claude/requirements.yaml.

        This modifies the version-controlled project config. Changes affect
        all team members. Use write_local_override() for personal preferences.

        Args:
            enabled: Framework enabled state (None = don't change)
            requirement_overrides: Dict of requirement names to their config
                                  e.g., {'commit_plan': {'enabled': False}}
                                  or {'adr_reviewed': {'adr_path': '/docs/adr'}}
            preserve_inherit: Keep existing 'inherit' flag (default: True)
            logging_config: Logging configuration dict with optional keys: level, destinations, file
                           e.g., {'level': 'info', 'destinations': ['file']}

        Returns:
            Path to file that was written (relative to cwd if possible)

        Raises:
            OSError: If write fails
            ImportError: If PyYAML not available

        Example:
            # Enable framework in project config
            config.write_project_override(enabled=True)

            # Add requirement field to project config
            config.write_project_override(
                requirement_overrides={'adr_reviewed': {'adr_path': '/docs/adr'}}
            )

            # Set info logging for project
            config.write_project_override(
                logging_config={'level': 'info', 'destinations': ['file']}
            )
        """
        project_file = self._paths.project_config_path()

        # Load existing project config (NOT cascade - only project file)
        existing_config = self._load_config_if_exists(project_file)

        # Handle inherit flag (KEY DIFFERENCE from local config)
        if preserve_inherit:
            # Add inherit: true if not present (default for project configs)
            if "inherit" not in existing_config:
                existing_config["inherit"] = True
            # Otherwise keep existing value

        return self._write_override_config(
            existing_config,
            enabled,
            requirement_overrides,
            self._io.write_project_config,
            logging_config,
        )

    def _requirements_map(self) -> dict[str, RequirementConfigDict]:
        return cast(
            dict[str, RequirementConfigDict], self._config.get("requirements", {})
        )

    def _get_typed_requirement(
        self, req_name: str, expected_type: RequirementType
    ) -> Optional[RequirementConfigDict]:
        req = self.get_requirement(req_name)
        if req is None:
            return None

        req_type = req.get("type", "blocking")
        if req_type != expected_type:
            raise ValueError(
                f"Requirement '{req_name}' is type '{req_type}', expected '{expected_type}'"
            )
        return req

    def _require_field(
        self, req_name: str, req_config: Mapping[str, Any], field: str, label: str
    ) -> Any:
        value = req_config.get(field)
        if not value:
            raise ValueError(
                f"{label} requirement '{req_name}' missing required field '{field}'"
            )
        return value

    def get_requirement(self, name: str) -> Optional[RequirementConfigDict]:
        """
        Get configuration for a specific requirement.

        Args:
            name: Requirement name (e.g., "commit_plan")

        Returns:
            Requirement config dict or None if not found
        """
        return self._requirements_map().get(name)

    def get_all_requirements(self) -> list[str]:
        """
        Get all configured requirement names.

        Returns:
            List of requirement names
        """
        return list(self._requirements_map().keys())

    def is_requirement_enabled(self, name: str) -> bool:
        """
        Check if specific requirement is enabled.

        Args:
            name: Requirement name

        Returns:
            True if requirement exists and is enabled
        """
        req = self.get_requirement(name)
        return req is not None and req.get("enabled", False)

    def get_scope(self, name: str) -> RequirementScope:
        """
        Get scope for requirement.

        Args:
            name: Requirement name

        Returns:
            Scope string: "session", "branch", "permanent", or "single_use"
        """
        return cast(RequirementScope, self.get_attribute(name, "scope", "session"))

    def get_trigger_tools(self, name: str) -> list[str]:
        """
        Get tools that trigger this requirement check.

        DEPRECATED: Use get_triggers() for full trigger matching support.

        Args:
            name: Requirement name

        Returns:
            List of tool names (default: Edit, Write, MultiEdit)
        """
        triggers = self._get_trigger_config(name)
        return self._extract_trigger_tool_names(triggers)

    def get_triggers(self, name: str) -> list[TriggerSpec]:
        """
        Get full trigger configuration for a requirement.

        Returns raw trigger_tools config that may include:
        - Simple strings: ['Edit', 'Write']
        - Complex objects: [{'tool': 'Bash', 'command_pattern': 'git\\s+commit'}]

        Use with matches_trigger() for proper matching:
            triggers = config.get_triggers('pre_commit_review')
            if matches_trigger(tool_name, tool_input, triggers):
                # Requirement applies

        Args:
            name: Requirement name

        Returns:
            List of triggers (strings or dicts). Default: ['Edit', 'Write', 'MultiEdit']
        """
        return self._get_trigger_config(name)

    def get_message(self, name: str) -> str:
        """
        Get message to display when requirement not satisfied.

        Args:
            name: Requirement name

        Returns:
            Message string
        """
        default_message = f'Requirement "{name}" not satisfied.'
        return self.get_attribute(name, "message", default_message)

    def get_checklist(self, name: str) -> list[str]:
        """
        Get checklist items for requirement.

        Args:
            name: Requirement name

        Returns:
            List of checklist items (empty list if none configured)
        """
        return cast(list[str], self.get_attribute(name, "checklist", []))

    def get_raw_config(self) -> RequirementsConfigData:
        """
        Get raw merged configuration.

        Returns:
            Full config dictionary
        """
        return cast(RequirementsConfigData, self._config.copy())

    def get_logging_config(self) -> LoggingConfigDict:
        """
        Get logging configuration.

        Returns:
            Logging config dictionary
        """
        return cast(LoggingConfigDict, self._config.get("logging", {}))

    def get_console_config(self) -> ConsoleConfigDict:
        """
        Get console output configuration.

        Returns:
            Console config dictionary
        """
        return cast(ConsoleConfigDict, self._config.get("console", {}))

    def get_debug_config(self) -> DebugConfigDict:
        """
        Get debug/progress configuration.

        Returns:
            Debug config dictionary with optional keys:
            - show_progress: bool (default: auto-detect TTY)
            - timing_threshold: float (default: 0.3)

        Example config:
            debug:
              show_progress: true
              timing_threshold: 0.5
        """
        return cast(DebugConfigDict, self._config.get("debug", {}))

    def get_hook_config(self, hook_name: str, key: str, default: Any = None) -> Any:
        """
        Get configuration for a specific hook.

        Accesses the 'hooks' section of config with sensible defaults:
        - session_start.inject_context: True (show status at start)
        - stop.verify_requirements: True (check before stopping)
        - stop.verify_scopes: ['session'] (only session-scoped)
        - session_end.clear_session_state: False (preserve state)

        Args:
            hook_name: Hook name ('session_start', 'stop', 'session_end')
            key: Configuration key within the hook config
            default: Default value if not configured (overrides built-in defaults)

        Returns:
            Configuration value or default

        Example:
            # Check if stop verification is enabled (default: True)
            if config.get_hook_config('stop', 'verify_requirements', True):
                # Check requirements before stopping
                pass
        """
        # Get hooks config section
        hooks_config = cast(HooksConfigDict, self._config.get("hooks", {}))
        hook_specific = hooks_config.get(hook_name, {})

        # Priority: explicit config > provided default > built-in default
        if key in hook_specific:
            return hook_specific[key]

        if default is not None:
            return default

        # Fall back to built-in default
        default_value = self.HOOK_DEFAULTS.get(hook_name, {}).get(key)
        if isinstance(default_value, list):
            return list(default_value)
        if isinstance(default_value, dict):
            return default_value.copy()
        return default_value

    def get_attribute(self, req_name: str, attr: str, default: Any = None) -> Any:
        """
        Get any attribute from requirement config with default fallback.

        Generic accessor prevents method explosion (ISP compliance).
        New requirement attributes don't require new methods.

        DEPRECATED for type-specific fields (calculator, guard_type, thresholds):
        - Use get_dynamic_config() for 'calculator' and 'thresholds' fields
        - Use get_guard_config() for 'guard_type' field
        - Use get_blocking_config() for blocking requirements

        Type-safe accessors provide compile-time guarantees and fail-fast validation.
        Continue using this method for common fields (enabled, scope, message, etc.).

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

    def get_blocking_config(self, req_name: str) -> Optional[BlockingRequirementConfig]:
        """
        Get type-safe blocking requirement configuration.

        Returns blocking config with guaranteed base fields only.
        No type-specific required fields for blocking requirements.

        Args:
            req_name: Requirement name

        Returns:
            BlockingRequirementConfig if found and valid, None otherwise

        Raises:
            ValueError: If requirement exists but is not blocking type
        """
        req = self._get_typed_requirement(req_name, "blocking")
        if req is None:
            return None

        # Blocking requirements don't have required type-specific fields
        return cast(BlockingRequirementConfig, req)

    def get_dynamic_config(self, req_name: str) -> Optional[DynamicRequirementConfig]:
        """
        Get type-safe dynamic requirement configuration.

        Returns dynamic config with guaranteed 'calculator' and 'thresholds' fields.

        Args:
            req_name: Requirement name

        Returns:
            DynamicRequirementConfig with guaranteed required fields, None if not found

        Raises:
            ValueError: If requirement exists but is not dynamic type or missing required fields
        """
        req = self._get_typed_requirement(req_name, "dynamic")
        if req is None:
            return None

        # Validate required fields for dynamic requirements
        self._require_field(req_name, req, "calculator", "Dynamic")
        self._require_field(req_name, req, "thresholds", "Dynamic")

        # Type checker now knows these fields exist
        return cast(DynamicRequirementConfig, req)

    def get_guard_config(self, req_name: str) -> Optional[GuardRequirementConfig]:
        """
        Get type-safe guard requirement configuration.

        Returns guard config with guaranteed 'guard_type' field.

        Args:
            req_name: Requirement name

        Returns:
            GuardRequirementConfig with guaranteed guard_type field, None if not found

        Raises:
            ValueError: If requirement exists but is not guard type or missing required field
        """
        req = self._get_typed_requirement(req_name, "guard")
        if req is None:
            return None

        # Validate required field for guard requirements
        self._require_field(req_name, req, "guard_type", "Guard")

        # Type checker now knows this field exists
        return cast(GuardRequirementConfig, req)

    def get_requirement_type(self, req_name: str) -> RequirementType:
        """
        Get requirement type.

        Args:
            req_name: Requirement name

        Returns:
            'blocking' (manually satisfied), 'dynamic' (calculated), or 'guard'
            Default: 'blocking' for backwards compatibility
        """
        return cast(RequirementType, self.get_attribute(req_name, "type", "blocking"))

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
        if not req or req.get("type") != "dynamic":
            return  # Not dynamic, skip validation
        self._validator.validate_dynamic_requirement(req_name, req)


if __name__ == "__main__":
    import tempfile
    import os

    try:
        import yaml
    except ImportError as e:
        raise ImportError("PyYAML is required for config tests.") from e

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
                    "message": "Test requirement not satisfied",
                }
            },
        }

        with open(f"{tmpdir}/.claude/requirements.yaml", "w") as f:
            yaml.safe_dump(config_content, f, default_flow_style=False, sort_keys=False)

        # Test loading
        config = RequirementsConfig(tmpdir)
        print(f"Enabled: {config.is_enabled()}")
        print(f"All requirements: {config.get_all_requirements()}")
        print(f"test_req enabled: {config.is_requirement_enabled('test_req')}")
        print(f"test_req scope: {config.get_scope('test_req')}")
        print(f"test_req message: {config.get_message('test_req')}")

    print("✅ Config tests passed")
