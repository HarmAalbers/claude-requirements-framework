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
except ImportError as e:
    # For testing, allow imports to fail gracefully but log warning
    import sys
    sys.stderr.write(f"[WARNING] blocking_strategy import failed: {e}\n")


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
        Create denial response with directive-first message format.

        Args:
            req_name: Requirement name
            config: Configuration
            context: Context dict

        Returns:
            Hook response dict
        """
        # Get requirement config using type-safe accessor
        try:
            req_config = config.get_blocking_config(req_name)
            if not req_config:
                req_config = config.get_requirement(req_name)
        except ValueError:
            req_config = config.get_requirement(req_name)

        session_id = context.get('session_id', 'unknown')

        # Use configured message if present (should be directive-first format)
        message = req_config.get('message', '')

        if not message:
            # Generate directive-first fallback message
            auto_skill = req_config.get('auto_resolve_skill', '')
            lines = [f"## Blocked: {req_name}", ""]

            if auto_skill:
                lines.append(f"**Execute**: `/{auto_skill}`")
            else:
                lines.append(f"**Action**: `req satisfy {req_name} --session {session_id}`")

            lines.append("")
            lines.append("---")
            lines.append(f"Fallback: `req satisfy {req_name} --session {session_id}`")
            message = "\n".join(lines)

        # Deduplication check to prevent spam from parallel tool calls
        if self.dedup_cache:
            cache_key = f"{context['project_dir']}:{context['branch']}:{session_id}:{req_name}"

            if not self.dedup_cache.should_show_message(cache_key, message, ttl=5):
                # Suppress verbose message - show configurable short message instead
                default_short = f"⏸️ Requirement `{req_name}` not satisfied (waiting...)"
                short_msg = req_config.get('short_message', default_short)
                return create_denial_response(short_msg)

        # Show full message (first time or after TTL expiration)
        return create_denial_response(message)
