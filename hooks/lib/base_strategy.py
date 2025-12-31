#!/usr/bin/env python3
"""
Base strategy class for requirement checking.

Implements the Strategy pattern for different requirement types, following
the Open/Closed Principle: the system is open for extension (new requirement
types) but closed for modification (existing code doesn't change).

This module provides the abstract base class that all concrete strategies
must implement.
"""

from abc import ABC, abstractmethod
from typing import Optional

# Import from sibling modules
try:
    from requirements import BranchRequirements
    from config import RequirementsConfig
    from message_dedup_cache import MessageDedupCache
    from strategy_utils import log_error
except ImportError:
    # For testing, allow imports to fail gracefully
    pass


class RequirementStrategy(ABC):
    """
    Abstract base class for requirement checking strategies.

    Each requirement type (blocking, dynamic, guard) has its own strategy class
    that implements the check() method.
    """

    def __init__(self):
        """
        Initialize strategy with message deduplication cache.

        Note:
            Cache initialization failures are logged but don't prevent strategy creation.
            If cache fails, all messages will be shown (fail-open behavior).
        """
        self._init_dedup_cache()

    def _init_dedup_cache(self) -> None:
        """
        Initialize message deduplication cache with fail-open error handling.

        This method is shared by all strategy subclasses to avoid code duplication.
        """
        try:
            self.dedup_cache = MessageDedupCache()
        except Exception as e:
            log_error(f"Failed to initialize message dedup cache: {e}", exc_info=True)
            # Create a dummy cache that always shows messages (fail-open)
            self.dedup_cache = None

    @abstractmethod
    def check(self, req_name: str, config: RequirementsConfig,
              reqs: BranchRequirements, context: dict) -> Optional[dict]:
        """
        Check if requirement is satisfied.

        Args:
            req_name: Requirement name
            config: Requirements configuration
            reqs: Branch requirements state manager
            context: Context dict with project_dir, branch, session_id, tool_name

        Returns:
            None if satisfied (allow operation)
            Dict with hookSpecificOutput if blocked/denied

        Raises:
            Never - all strategies must fail-open on errors
        """
        pass
