"""Shared utilities for hook implementation."""
import json
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from config import RequirementsConfig
from git_utils import get_current_branch, is_git_repo, resolve_project_root
from logger import configure_logger, get_logger, JsonLogger
from console import configure_console


def parse_hook_input(stdin_content: str) -> Tuple[Dict[str, Any], Optional[str]]:
    """
    Parse and validate basic hook input structure from stdin.

    This centralizes JSON parsing and basic type validation for hook inputs.
    Following fail-open semantics: returns empty dict on parse errors rather
    than raising exceptions.

    Args:
        stdin_content: Raw stdin content (may be empty or malformed)

    Returns:
        Tuple of (input_data, error):
        - input_data: Parsed dict with validated fields:
            - 'tool_name': str or None (validated as string type)
            - 'tool_input': dict (defaults to {} if missing/invalid)
            - '_empty_stdin': True if stdin was empty (for debugging)
            - '_tool_name_type_error': error message if tool_name had wrong type
            - '_tool_input_type_error': error message if tool_input had wrong type
            - All other fields preserved as-is
        - error: Error message string if parsing failed, None on success

    Example:
        input_data, error = parse_hook_input(sys.stdin.read())
        if error:
            logger.warning("Hook input parse error", error=error)
        tool_name = input_data.get('tool_name')  # str or None
    """
    if not stdin_content:
        return {'_empty_stdin': True}, None

    # Parse JSON
    try:
        input_data = json.loads(stdin_content)
    except json.JSONDecodeError as e:
        return {}, f"JSON parse error: {e}"

    # Ensure we got a dict
    if not isinstance(input_data, dict):
        return {}, f"Expected dict, got {type(input_data).__name__}"

    # Validate tool_name is a string (Issue #01 fix)
    tool_name = input_data.get('tool_name')
    if tool_name is not None and not isinstance(tool_name, str):
        # Log warning but normalize to None (fail-open)
        input_data['_tool_name_type_error'] = f"Expected str, got {type(tool_name).__name__}"
        input_data['tool_name'] = None

    # Validate tool_input is a dict (default to empty dict)
    tool_input = input_data.get('tool_input')
    if tool_input is not None and not isinstance(tool_input, dict):
        input_data['_tool_input_type_error'] = f"Expected dict, got {type(tool_input).__name__}"
        input_data['tool_input'] = {}
    elif tool_input is None:
        input_data['tool_input'] = {}

    return input_data, None


def early_hook_setup(
    session_id: str,
    hook_name: str,
    cwd: Optional[str] = None,
    skip_config: bool = False
) -> Tuple[Optional[str], Optional[str], Optional[RequirementsConfig], JsonLogger]:
    """
    Perform early hook setup: resolve paths, load config, create logger.

    This centralizes the common pattern across all hooks to ensure:
    - Config is loaded before any logging happens
    - Logger uses config-specified level from the start
    - Consistent error handling with fail-open semantics

    Args:
        session_id: Current session ID
        hook_name: Hook name for context (e.g., "Stop", "PreToolUse")
        cwd: Project directory hint (from stdin)
        skip_config: If True, skip config loading (for minimal hooks)

    Returns:
        Tuple of (project_dir, branch, config, logger)
        - project_dir: None if not found/not git
        - branch: None if not found/detached HEAD
        - config: None if skip_config=True or loading failed
        - logger: Always present, uses config if available
    """
    base_context = {"session": session_id, "hook": hook_name}

    # Resolve project directory
    project_dir = cwd or resolve_project_root(verbose=False)
    if not project_dir:
        # No project context - create basic logger
        return None, None, None, get_logger(base_context=base_context)

    base_context["project_dir"] = project_dir

    # Get branch
    branch = None
    if is_git_repo(project_dir):
        branch = get_current_branch(project_dir)
        if branch:
            base_context["branch"] = branch

    # Load config (if requested)
    config = None
    if not skip_config:
        try:
            # Check if project has requirements config
            config_file = Path(project_dir) / '.claude' / 'requirements.yaml'

            if config_file.exists():
                config = RequirementsConfig(project_dir)
        except Exception as e:
            # Config loading failed - fail open with basic logger
            logger = get_logger(base_context=base_context)
            logger.error("Config loading failed", error=str(e))
            return project_dir, branch, None, logger

    # Create logger with config (if available)
    logging_config = config.get_logging_config() if config else None
    console_config = config.get_console_config() if config else None
    configure_console(console_config)
    logger = configure_logger(logging_config, base_context=base_context)

    return project_dir, branch, config, logger
