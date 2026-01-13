#!/usr/bin/env python3
"""
Blocking requirement strategy.

Strategy for blocking (manually satisfied) requirements.

These requirements must be manually satisfied via the CLI using
'req satisfy <name>' before file modifications are allowed.

Examples: commit_plan, adr_reviewed, github_ticket
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


class BlockingRequirementStrategy(RequirementStrategy):
    """
    Strategy for blocking (manually satisfied) requirements.

    These requirements must be manually satisfied via the CLI using
    'req satisfy <name>' before file modifications are allowed.

    Examples: commit_plan, adr_reviewed, github_ticket
    """

    def check(self, req_name: str, config: RequirementsConfig,
              reqs: BranchRequirements, context: dict) -> Optional[dict]:
        """
        Check if blocking requirement is satisfied.

        Returns:
            None if satisfied
            Dict with denial message if not satisfied
        """
        scope = config.get_scope(req_name)

        if not reqs.is_satisfied(req_name, scope):
            # Not satisfied - create denial response
            return self._create_denial_response(req_name, config, context)

        return None  # Satisfied, allow

    def _create_denial_response(self, req_name: str, config: RequirementsConfig,
                                context: dict) -> dict:
        """
        Create denial response with formatted message.

        Args:
            req_name: Requirement name
            config: Configuration
            context: Context dict

        Returns:
            Hook response dict
        """
        # Get requirement config using type-safe accessor
        # For blocking requirements, use get_blocking_config() for type safety
        # Falls back to get_requirement() if type-specific accessor fails
        try:
            req_config = config.get_blocking_config(req_name)
            if not req_config:
                # Requirement not found - use generic accessor as fallback
                req_config = config.get_requirement(req_name)
        except ValueError:
            # Not a blocking type - use generic accessor as fallback
            req_config = config.get_requirement(req_name)

        message = req_config.get('message', f'Requirement "{req_name}" not satisfied.')

        # Add checklist if present
        checklist = req_config.get('checklist', [])
        if checklist:
            message += "\n\n**Checklist**:"
            for i, item in enumerate(checklist, 1):
                message += f"\n⬜ {i}. {item}"

        # Add session context
        session_id = context['session_id']
        message += f"\n\n**Current session**: `{session_id}`"

        # Add helper hint
        message += f"\n\n💡 **To satisfy from terminal**:"
        message += f"\n```bash"
        message += f"\nreq satisfy {req_name} --session {session_id}"
        message += f"\n```"

        # Deduplication check to prevent spam from parallel tool calls
        if self.dedup_cache:
            cache_key = f"{context['project_dir']}:{context['branch']}:{session_id}:{req_name}"

            if not self.dedup_cache.should_show_message(cache_key, message, ttl=5):
                # Suppress verbose message - show minimal indicator instead
                minimal_message = f"⏸️ Requirement `{req_name}` not satisfied (waiting...)"
                return create_denial_response(minimal_message)

        # Show full message (first time or after TTL expiration)
        return create_denial_response(message)
