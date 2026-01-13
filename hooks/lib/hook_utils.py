"""Shared utilities for hook implementation."""
from pathlib import Path
from typing import Optional, Tuple

from config import RequirementsConfig
from git_utils import get_current_branch, is_git_repo, resolve_project_root
from logger import get_logger, JsonLogger


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
    logger = get_logger(logging_config, base_context=base_context)

    return project_dir, branch, config, logger
