#!/usr/bin/env python3
"""
Shared utility functions for requirement strategies.

This module provides common utilities used across all strategy implementations:
- Error and warning logging
- Standard hook response formatting

These utilities are separated to avoid code duplication and maintain consistency
across different strategy types.
"""

from logger import get_logger

def log_error(message: str, exc_info: bool = False) -> None:
    """
    Log error message to the central logger.

    Args:
        message: Error message
        exc_info: Whether to include traceback
    """
    logger = get_logger()
    if exc_info:
        import traceback
        logger.error(f"⚠️ {message}", traceback=traceback.format_exc())
    else:
        logger.error(f"⚠️ {message}")


def log_warning(message: str) -> None:
    """Log warning message to the central logger."""
    get_logger().warning(f"⚠️ {message}")


def create_denial_response(message: str) -> dict:
    """
    Create standard denial response for PreToolUse hook.

    Args:
        message: The message to show to the user

    Returns:
        Hook response dict with denial decision

    Note:
        Always uses "deny" rather than "ask" because "ask" can be overridden
        by permissions.allow entries in settings.local.json, which would bypass
        requirement enforcement.
    """
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": message
        }
    }
