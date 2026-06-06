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
    sys.stderr.write(f"[WARNING] guard_strategy import failed: {e}\n")

if TYPE_CHECKING:
    from messages import MessageLoader


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
            from strategy_utils import log_warning
            log_warning(f"Invalid guard requirement config for '{req_name}': {e}")
            return None

        if guard_type == 'protected_branch':
            return self._check_protected_branch(req_name, config, context)
        elif guard_type == 'single_session':
            return self._check_single_session(req_name, config, context)

        # Unknown guard type - fail open but log warning
        from strategy_utils import log_warning
        log_warning(f"Guard requirement '{req_name}' has unknown guard_type '{guard_type}' - skipped")
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
            from strategy_utils import log_warning
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

        Uses MessageLoader if available, otherwise falls back to inline config messages.

        Args:
            req_name: Requirement name
            config: Configuration
            branch: Current branch name
            context: Context dict

        Returns:
            Hook response dict with denial
        """
        session_id = context.get('session_id', 'unknown')

        # Get auto_resolve_skill for message substitution
        auto_resolve_skill = config.get_attribute(req_name, 'auto_resolve_skill', '')

        # Try to use externalized messages from MessageLoader
        message = None
        short_msg = None
        message_loader = self._get_message_loader(context)

        if message_loader:
            try:
                messages = message_loader.get_messages(req_name, 'guard')
                formatted = messages.format(
                    req_name=req_name,
                    session_id=session_id,
                    branch=branch,
                    project_dir=context.get('project_dir', ''),
                    auto_resolve_skill=auto_resolve_skill,
                )
                message = formatted.blocking_message
                short_msg = formatted.short_message
            except Exception:
                # Fall back to inline config messages if loader fails
                pass

        # Fall back to inline config message
        if not message:
            custom_message = config.get_attribute(req_name, 'message', None)

            if custom_message:
                # Use configured message as-is (directive-first format)
                # Substitute placeholders if present
                message = custom_message.replace('{branch}', branch)
                message = message.replace('{auto_resolve_skill}', auto_resolve_skill)
                message = message.replace('{session_id}', session_id)
            else:
                # Directive-first fallback
                lines = [
                    f"## Blocked: {req_name}",
                    "",
                    f"Cannot edit files on protected branch `{branch}`.",
                    "",
                    "**Actions**:",
                    "1. Create feature branch: `git checkout -b feature/your-feature-name`",
                    f"2. Emergency override: `req approve {req_name}`",
                ]
                message = "\n".join(lines)

        if not short_msg:
            short_msg = f"Guard `{req_name}` blocked (waiting...)"

        # Deduplication check to prevent spam from parallel tool calls
        if self.dedup_cache:
            cache_key = f"{context.get('project_dir', '')}:{branch}:{session_id}:{req_name}"

            if not self.dedup_cache.should_show_message(cache_key, message, ttl=5):
                return create_denial_response(short_msg)

        return create_denial_response(message)

    def _check_single_session(self, req_name: str, config: RequirementsConfig,
                              context: dict) -> Optional[dict]:
        """
        Check if another session is active on this project.

        Args:
            req_name: Requirement name
            config: Configuration
            context: Context with session_id and project_dir

        Returns:
            None if no other sessions are active
            Denial response if another session is active on the same project
        """
        try:
            from session import get_active_sessions
        except ImportError as e:
            # Fail open if session module unavailable, but log the error
            from strategy_utils import log_warning
            log_warning(f"single_session guard disabled - session module import failed: {e}")
            return None

        project_dir = context.get('project_dir')
        current_session = context.get('session_id')

        if not project_dir:
            return None  # No project context - fail open

        # Get active sessions for this project
        # get_active_sessions already filters out stale sessions via is_process_alive()
        active = get_active_sessions(project_dir=project_dir)

        # Exclude current session from the list
        other_sessions = [s for s in active if s.get('id') != current_session]

        if not other_sessions:
            return None  # No conflict - allow

        # Another session is active - create denial
        return self._create_single_session_denial(req_name, config, other_sessions, context)

    def _create_single_session_denial(self, req_name: str, config: RequirementsConfig,
                                      other_sessions: list, context: dict) -> dict:
        """
        Create denial response for single session violation.

        Uses MessageLoader if available, otherwise falls back to inline config messages.
        Note: Single session guard generates dynamic session info, so the externalized
        message serves as a fallback template.

        Args:
            req_name: Requirement name
            config: Configuration
            other_sessions: List of other active sessions on the same project
            context: Context dict

        Returns:
            Hook response dict with denial
        """
        session_id = context.get('session_id', 'unknown')
        project_dir = context.get('project_dir', 'unknown')

        # Get auto_resolve_skill for message substitution
        auto_resolve_skill = config.get_attribute(req_name, 'auto_resolve_skill', '')

        # Try to get short message from loader
        short_msg = None
        message_loader = self._get_message_loader(context)
        if message_loader:
            try:
                messages = message_loader.get_messages(req_name, 'guard')
                formatted = messages.format(
                    req_name=req_name,
                    session_id=session_id,
                    project_dir=project_dir,
                    auto_resolve_skill=auto_resolve_skill,
                )
                short_msg = formatted.short_message
            except Exception:
                pass

        if not short_msg:
            short_msg = f"Guard `{req_name}` blocked (waiting...)"

        # Get custom message (should be directive-first format)
        custom_message = config.get_attribute(req_name, 'message', None)

        if custom_message:
            # Use configured message - substitute placeholders
            message = custom_message.replace('{auto_resolve_skill}', auto_resolve_skill)
            message = message.replace('{session_id}', session_id)
            message = message.replace('{project_dir}', project_dir)
        else:
            # Directive-first fallback with session info
            import time

            lines = [
                f"## Blocked: {req_name}",
                "",
                "Another Claude Code session is active on this project.",
                "",
                "**Active sessions**:",
            ]

            for sess in other_sessions:
                sess_id = sess.get('id', 'unknown')
                branch = sess.get('branch', 'unknown')
                last_active = sess.get('last_active', 0)

                if last_active:
                    elapsed = int(time.time()) - last_active
                    if elapsed < 60:
                        time_str = f"{elapsed}s ago"
                    elif elapsed < 3600:
                        time_str = f"{elapsed // 60}m ago"
                    else:
                        time_str = f"{elapsed // 3600}h ago"
                else:
                    time_str = "unknown"

                lines.append(f"- `{sess_id}` on `{branch}` ({time_str})")

            lines.extend([
                "",
                "**Actions**:",
                "1. Close the other session",
                "2. Wait for completion",
                f"3. Override: `req approve {req_name}`",
            ])
            message = "\n".join(lines)

        # Deduplication check to prevent spam from parallel tool calls
        if self.dedup_cache:
            cache_key = f"{project_dir}:{session_id}:{req_name}:single_session"

            if not self.dedup_cache.should_show_message(cache_key, message, ttl=5):
                return create_denial_response(short_msg)

        return create_denial_response(message)
