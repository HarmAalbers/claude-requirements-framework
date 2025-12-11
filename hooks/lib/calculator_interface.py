#!/usr/bin/env python3
"""
Calculator Interface for Dynamic Requirements

Defines the abstract base class that all dynamic requirement calculators
must implement. This ensures a consistent contract and enables type checking.

Following the Dependency Inversion Principle (SOLID), this interface allows
high-level modules (the requirements framework) to depend on abstractions
rather than concrete implementations.
"""

from abc import ABC, abstractmethod
from typing import Optional


class RequirementCalculator(ABC):
    """
    Abstract base class for dynamic requirement calculators.

    All calculators must implement the calculate() method and follow the
    fail-open philosophy: NEVER raise exceptions, return None instead.

    Example:
        class BranchSizeCalculator(RequirementCalculator):
            def calculate(self, project_dir: str, branch: str, **kwargs) -> Optional[dict]:
                try:
                    # Perform calculation
                    return {'value': 450, 'summary': '...'}
                except Exception:
                    return None  # Fail open - never block on errors
    """

    @abstractmethod
    def calculate(self, project_dir: str, branch: str, **kwargs) -> Optional[dict]:
        """
        Calculate the current status of this requirement.

        Args:
            project_dir: Absolute path to the project root directory
            branch: Current git branch name
            **kwargs: Calculator-specific additional parameters (for future extensions)

        Returns:
            None if the check should be skipped (e.g., main branch, not applicable,
                 error occurred). This follows the fail-open principle.

            Dict with the following required keys:
                - 'value' (int|float): Numeric value for threshold comparison.
                                      This is what gets compared against warn/block thresholds.
                - 'summary' (str): Human-readable one-line summary of the result.
                                  Displayed in error messages and CLI output.

            Optional additional keys:
                - Any calculator-specific data (e.g., 'base_branch', 'committed', etc.)
                - These can be used in message templates via {key} syntax

        Note:
            MUST NEVER raise exceptions. All errors should be caught and return None
            to implement fail-open behavior. The requirements framework should never
            block legitimate work due to calculator errors.

        Example return values:
            # Normal case
            {'value': 450, 'summary': 'committed: 200+/50- | staged: 100+/0-'}

            # Skip check (main branch)
            None

            # Error occurred
            None  # Don't raise, just return None
        """
        pass
