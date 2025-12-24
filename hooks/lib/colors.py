#!/usr/bin/env python3
"""
Terminal color utilities for requirements framework CLI.

Provides ANSI color codes and semantic helper functions for consistent
colored output across the CLI. Respects NO_COLOR, FORCE_COLOR, and TTY detection.

Usage:
    from colors import success, error, warning, info, header, hint, dim, bold

    print(success("✅ Operation completed"))
    print(error("❌ Something went wrong"))
    print(warning("⚠️  Heads up"))
    print(info("ℹ️  Note"))
    print(header("📋 Section Title"))
    print(hint("💡 Tip"))
    print(dim("secondary info"))
    print(bold("important"))

Environment Variables:
    NO_COLOR=1      Disable all colors (https://no-color.org/)
    FORCE_COLOR=1   Force colors even in non-TTY
    TERM=dumb       Disable colors for dumb terminals
"""
import os
import sys


class Colors:
    """ANSI escape code constants."""

    RESET = '\033[0m'
    BOLD = '\033[1m'
    DIM = '\033[2m'

    # Standard colors
    RED = '\033[31m'
    GREEN = '\033[32m'
    YELLOW = '\033[33m'
    BLUE = '\033[34m'
    CYAN = '\033[36m'
    GRAY = '\033[90m'

    # Bright colors
    BRIGHT_RED = '\033[91m'
    BRIGHT_GREEN = '\033[92m'
    BRIGHT_YELLOW = '\033[93m'
    BRIGHT_BLUE = '\033[94m'
    BRIGHT_CYAN = '\033[96m'


def _supports_color() -> bool:
    """
    Check if terminal supports colors.

    Checks in order:
    1. NO_COLOR env var - disables colors (https://no-color.org/)
    2. FORCE_COLOR env var - forces colors on
    3. stdout.isatty() - must be a TTY
    4. TERM != 'dumb' - dumb terminals don't support colors

    Returns:
        True if colors should be enabled
    """
    # Respect NO_COLOR standard (https://no-color.org/)
    if os.environ.get('NO_COLOR'):
        return False

    # Check FORCE_COLOR override
    if os.environ.get('FORCE_COLOR'):
        return True

    # Check if stdout is a TTY
    if not hasattr(sys.stdout, 'isatty') or not sys.stdout.isatty():
        return False

    # Check TERM
    term = os.environ.get('TERM', '')
    if term == 'dumb':
        return False

    return True


# Cache the result (can be reset for testing by setting to None)
_color_enabled = None


def colors_enabled() -> bool:
    """
    Check if colors are enabled (cached).

    Returns:
        True if colors should be applied
    """
    global _color_enabled
    if _color_enabled is None:
        _color_enabled = _supports_color()
    return _color_enabled


def _wrap(text: str, color: str) -> str:
    """
    Wrap text with color codes if colors are enabled.

    Args:
        text: The text to colorize
        color: ANSI color code(s) to apply

    Returns:
        Colored text if colors enabled, otherwise original text
    """
    if not colors_enabled():
        return text
    return f"{color}{text}{Colors.RESET}"


# Semantic color functions

def success(text: str) -> str:
    """Green text for success messages (✅)."""
    return _wrap(text, Colors.BRIGHT_GREEN)


def error(text: str) -> str:
    """Red text for error messages (❌)."""
    return _wrap(text, Colors.BRIGHT_RED)


def warning(text: str) -> str:
    """Yellow text for warning messages (⚠️)."""
    return _wrap(text, Colors.BRIGHT_YELLOW)


def info(text: str) -> str:
    """Cyan text for info messages (ℹ️)."""
    return _wrap(text, Colors.BRIGHT_CYAN)


def header(text: str) -> str:
    """Bold blue text for headers (📋📌📊)."""
    return _wrap(text, f"{Colors.BOLD}{Colors.BLUE}")


def hint(text: str) -> str:
    """Cyan text for hints/tips (💡)."""
    return _wrap(text, Colors.CYAN)


def dim(text: str) -> str:
    """Gray text for secondary information."""
    return _wrap(text, Colors.GRAY)


def bold(text: str) -> str:
    """Bold text for emphasis."""
    return _wrap(text, Colors.BOLD)
