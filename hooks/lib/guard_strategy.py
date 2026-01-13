#!/usr/bin/env python3
"""
Guard requirement strategy.

Strategy for guard requirements - boolean conditions that must be met.

Guards are different from blocking/dynamic requirements:
- They check a boolean condition (e.g., "not on protected branch")
- If the condition fails → block the operation
- Can be approved (session-scoped) for emergencies via `req approve`
- Approvals expire when the session ends

Examples: protected_branch (prevents edits on main/master)
"""

from typing import Optional

# Import from sibling modules
try:
    from base_strategy import RequirementStrategy
    from requirements import BranchRequirements
    from config import RequirementsConfig
    from strategy_utils import create_denial_response
except ImportError:
    # For testing, allow imports to fail gracefully
    pass


class GuardRequirementStrategy(RequirementStrategy):
    """
    Strategy for guard requirements - boolean conditions that must be met.

    Guards are different from blocking/dynamic requirements:
    - They check a boolean condition (e.g., "not on protected branch")
    - If the condition fails → block the operation
    - Can be approved (session-scoped) for emergencies via `req approve`
    - Approvals expire when the session ends

    Examples: protected_branch (prevents edits on main/master)
    """

    def check(self, req_name: str, config: RequirementsConfig,
              reqs: BranchRequirements, context: dict) -> Optional[dict]:
        """
        Check if guard condition is satisfied.

        Returns:
            None if condition passes or approved
            Dict with denial message if condition fails
        """
        # Check if already approved for this session (emergency override)
        if reqs.is_satisfied(req_name, scope='session'):
            return None  # Approved, allow

        # Get guard type using type-safe accessor
        try:
            req_config = config.get_guard_config(req_name)
            if not req_config:
                # Requirement not found - fail open
                return None
            # Type system now guarantees 'guard_type' field exists
            guard_type = req_config['guard_type']
        except ValueError as e:
            # Invalid config - fail open with warning
            from lib.logger import log_warning
            log_warning(f"Invalid guard requirement config for '{req_name}': {e}")
            return None

        if guard_type == 'protected_branch':
            return self._check_protected_branch(req_name, config, context)

        # Unknown guard type - fail open
        return None

    def _check_protected_branch(self, req_name: str, config: RequirementsConfig,
                                context: dict) -> Optional[dict]:
        """
        Check if current branch is protected.

        Args:
            req_name: Requirement name
            config: Configuration
            context: Context with branch info

        Returns:
            None if not on protected branch
            Denial response if on protected branch
        """
        branch = context.get('branch')
        if not branch:
            return None  # No branch info - fail open

        # Get protected branches list using type-safe accessor
        try:
            req_config = config.get_guard_config(req_name)
            if not req_config:
                return None  # Requirement not found - fail open
            # 'protected_branches' is optional, so use .get() with default
            protected_branches = req_config.get('protected_branches', ['master', 'main'])
        except ValueError as e:
            # Invalid config - fail open with warning
            from lib.logger import log_warning
            log_warning(f"Invalid guard requirement config for '{req_name}': {e}")
            return None

        if branch in protected_branches:
            # On protected branch - create denial response
            return self._create_denial_response(req_name, config, branch, context)

        return None  # Not on protected branch - allow

    def _create_denial_response(self, req_name: str, config: RequirementsConfig,
                                branch: str, context: dict) -> dict:
        """
        Create denial response for protected branch violation.

        Args:
            req_name: Requirement name
            config: Configuration
            branch: Current branch name
            context: Context dict

        Returns:
            Hook response dict with denial
        """
        # Get custom message or use default
        custom_message = config.get_attribute(req_name, 'message', None)

        if custom_message:
            message = custom_message
        else:
            message = f"🚫 **Cannot edit files on protected branch '{branch}'**\n\n"
            message += "Direct edits on protected branches are not allowed.\n\n"
            message += "**Options:**\n"
            message += "1. Create a feature branch first:\n"
            message += f"   `git checkout -b feature/your-feature-name`\n\n"
            message += "2. Override for emergency hotfix (current session only):\n"
            message += f"   `req approve {req_name}`"

        # Add session context
        session_id = context.get('session_id', 'unknown')
        message += f"\n\n**Current session**: `{session_id}`"
        message += f"\n**Branch**: `{branch}`"

        # Deduplication check to prevent spam from parallel tool calls
        if self.dedup_cache:
            cache_key = f"{context.get('project_dir', '')}:{branch}:{session_id}:{req_name}"

            if not self.dedup_cache.should_show_message(cache_key, message, ttl=5):
                # Suppress verbose message - show minimal indicator instead
                minimal_message = f"⏸️ Guard requirement `{req_name}` not satisfied (waiting...)"
                return create_denial_response(minimal_message)

        # Show full message (first time or after TTL expiration)
        return create_denial_response(message)
