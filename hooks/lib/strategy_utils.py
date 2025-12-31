#!/usr/bin/env python3
"""
Shared utility functions for requirement strategies.

This module provides common utilities used across all strategy implementations:
- Error and warning logging
- Standard hook response formatting

These utilities are separated to avoid code duplication and maintain consistency
across different strategy types.
"""

import sys
import time


def log_error(message: str, exc_info: bool = False) -> None:
    """
    Log error message to stderr and error log file.

    Args:
        message: Error message
        exc_info: Whether to include traceback
    """
    print(f"⚠️ {message}", file=sys.stderr)

    if exc_info:
        import traceback
        from pathlib import Path

        try:
            log_file = Path.home() / '.claude' / 'requirements-errors.log'
            with open(log_file, 'a') as f:
                f.write(f"\n{'='*60}\n")
                f.write(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Error: {message}\n")
                f.write(traceback.format_exc())
        except Exception:
            pass  # Silent fail for logging


def log_warning(message: str) -> None:
    """Log warning message."""
    print(f"⚠️ {message}", file=sys.stderr)


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
