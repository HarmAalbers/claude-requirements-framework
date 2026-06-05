#!/usr/bin/env python3
"""
Blocking requirement strategy.

Strategy for blocking (manually satisfied) requirements.

These requirements must be manually satisfied via the CLI using
'req satisfy <name>' before file modifications are allowed.

Examples: commit_plan, adr_reviewed, github_ticket
"""

from typing import Optional, TYPE_CHECKING

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

if TYPE_CHECKING:
    from messages import MessageLoader


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

        Uses MessageLoader if available, otherwise falls back to inline config messages.

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

        # Get auto_resolve_skill for message substitution
        auto_resolve_skill = req_config.get('auto_resolve_skill', '') if req_config else ''

        # Try to use externalized messages from MessageLoader
        message_loader = self._get_message_loader(context)
        if message_loader:
            try:
                messages = message_loader.get_messages(req_name, 'blocking')
                formatted = messages.format(
                    req_name=req_name,
                    session_id=session_id,
                    branch=context.get('branch', ''),
                    project_dir=context.get('project_dir', ''),
                    auto_resolve_skill=auto_resolve_skill,
                )
                message = formatted.blocking_message
                short_msg = formatted.short_message
            except Exception:
                # Fall back to inline config messages if loader fails
                message = None
                short_msg = None
        else:
            message = None
            short_msg = None

        # Fall back to inline config message if no externalized message
        if not message and req_config:
            message = req_config.get('message', '')
            if message:
                message = message.replace('{auto_resolve_skill}', auto_resolve_skill)
                message = message.replace('{session_id}', session_id)

        if not message:
            # Generate directive-first fallback message
            auto_skill = req_config.get('auto_resolve_skill', '') if req_config else ''
            lines = [f"## Blocked: {req_name}", ""]

            if auto_skill:
                lines.append(f"**Execute**: `/{auto_skill}`")
            else:
                lines.append(f"**Action**: `req satisfy {req_name} --session {session_id}`")
            message = "\n".join(lines)

        # Fall back to inline config short message
        if not short_msg:
            default_short = f"Requirement `{req_name}` not satisfied (waiting...)"
            short_msg = req_config.get('short_message', default_short) if req_config else default_short

        # Deduplication check to prevent spam from parallel tool calls
        if self.dedup_cache:
            cache_key = f"{context['project_dir']}:{context['branch']}:{session_id}:{req_name}"

            if not self.dedup_cache.should_show_message(cache_key, message, ttl=5):
                # Suppress verbose message - show short message instead
                return create_denial_response(short_msg)

        # Show full message (first time or after TTL expiration)
        return create_denial_response(message)
