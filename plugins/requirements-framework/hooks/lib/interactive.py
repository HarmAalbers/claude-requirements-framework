"""
Interactive Prompt Module

Provides interactive prompts for CLI tools with InquirerPy fallback to stdlib.
Uses InquirerPy for rich terminal UI when available, gracefully falls back
to simple input()-based prompts when not installed.

This follows the framework's "zero dependencies" philosophy - the optional
InquirerPy dependency enhances the experience but isn't required.

Usage:
    from interactive import select, confirm, checkbox

    # Single selection
    choice = select("Pick one:", ["Option A", "Option B", "Option C"])

    # Yes/no confirmation
    ok = confirm("Continue?", default=True)

    # Multi-selection
    selected = checkbox("Select items:", ["A", "B", "C"], default=["A"])
"""
from typing import List, Optional


def has_inquirerpy() -> bool:
    """
    Check if InquirerPy is available.

    Returns:
        True if InquirerPy can be imported, False otherwise.
    """
    try:
        import InquirerPy  # noqa: F401
        return True
    except ImportError:
        return False


def _stdlib_select(message: str, choices: List[str], default: int = 0) -> str:
    """
    Stdlib fallback for single selection.

    Displays a numbered menu and accepts numeric input.

    Args:
        message: Prompt message to display
        choices: List of options to choose from
        default: Index of default choice (0-based)

    Returns:
        The selected choice string
    """
    print(f"\n{message}")
    for i, choice in enumerate(choices):
        marker = ">" if i == default else " "
        print(f"  {marker} {i + 1}. {choice}")

    while True:
        prompt = f"\nEnter number [1-{len(choices)}] (default: {default + 1}): "
        response = input(prompt).strip()

        if not response:
            return choices[default]

        try:
            idx = int(response) - 1
            if 0 <= idx < len(choices):
                return choices[idx]
        except ValueError:
            pass

        print(f"Please enter a number between 1 and {len(choices)}")


def _stdlib_confirm(message: str, default: bool = True) -> bool:
    """
    Stdlib fallback for yes/no confirmation.

    Args:
        message: Prompt message to display
        default: Default value if user presses Enter

    Returns:
        True for yes, False for no
    """
    default_str = "Y/n" if default else "y/N"
    response = input(f"{message} [{default_str}]: ").strip().lower()

    if not response:
        return default

    return response in ('y', 'yes')


def _stdlib_checkbox(message: str, choices: List[str],
                     default: Optional[List[str]] = None) -> List[str]:
    """
    Stdlib fallback for multi-selection.

    Accepts comma-separated numbers, 'all', or 'none'.

    Args:
        message: Prompt message to display
        choices: List of options to choose from
        default: List of pre-selected choices

    Returns:
        List of selected choice strings
    """
    if default is None:
        default = []

    selected = set(default)

    print(f"\n{message}")
    print("(Enter numbers separated by commas, or 'all'/'none')")

    for i, choice in enumerate(choices):
        marker = "[x]" if choice in selected else "[ ]"
        print(f"  {i + 1}. {marker} {choice}")

    response = input("\nSelect: ").strip().lower()

    if response == 'all':
        return choices.copy()
    if response == 'none':
        return []
    if not response:
        return list(selected)

    try:
        indices = [int(x.strip()) - 1 for x in response.split(',')]
        return [choices[i] for i in indices if 0 <= i < len(choices)]
    except (ValueError, IndexError):
        return list(selected)


def select(message: str, choices: List[str], default: int = 0) -> str:
    """
    Single selection from a list of choices.

    Uses InquirerPy if available, falls back to stdlib numbered menu.

    Args:
        message: Prompt message to display
        choices: List of options to choose from
        default: Index of default choice (0-based)

    Returns:
        The selected choice string
    """
    if has_inquirerpy():
        try:
            from InquirerPy import inquirer
            return inquirer.select(
                message=message,
                choices=choices,
                default=choices[default] if 0 <= default < len(choices) else None
            ).execute()
        except Exception:
            pass  # Fall back to stdlib on any error

    return _stdlib_select(message, choices, default)


def confirm(message: str, default: bool = True) -> bool:
    """
    Yes/no confirmation prompt.

    Uses InquirerPy if available, falls back to stdlib Y/n prompt.

    Args:
        message: Prompt message to display
        default: Default value if user presses Enter

    Returns:
        True for yes, False for no
    """
    if has_inquirerpy():
        try:
            from InquirerPy import inquirer
            return inquirer.confirm(message=message, default=default).execute()
        except Exception:
            pass  # Fall back to stdlib on any error

    return _stdlib_confirm(message, default)


def checkbox(message: str, choices: List[str],
             default: Optional[List[str]] = None) -> List[str]:
    """
    Multi-selection from a list of choices.

    Uses InquirerPy if available, falls back to stdlib comma-separated input.

    Args:
        message: Prompt message to display
        choices: List of options to choose from
        default: List of pre-selected choices

    Returns:
        List of selected choice strings
    """
    if default is None:
        default = []

    if has_inquirerpy():
        try:
            from InquirerPy import inquirer
            return inquirer.checkbox(
                message=message,
                choices=choices,
                default=default
            ).execute()
        except Exception:
            pass  # Fall back to stdlib on any error

    return _stdlib_checkbox(message, choices, default)
