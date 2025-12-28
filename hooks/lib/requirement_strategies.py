#!/usr/bin/env python3
"""
Requirement Strategy Pattern

Implements the Strategy pattern for different requirement types, following
the Open/Closed Principle: the system is open for extension (new requirement
types) but closed for modification (existing code doesn't change).

This replaces if/elif type branching with polymorphic strategy dispatch.
"""

from abc import ABC, abstractmethod
from typing import Optional
import sys
import time

# Import from sibling modules
try:
    from requirements import BranchRequirements
    from config import RequirementsConfig
    from calculator_interface import RequirementCalculator
    from calculation_cache import CalculationCache
    from message_dedup_cache import MessageDedupCache
except ImportError:
    # For testing, allow imports to fail gracefully
    pass


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


class RequirementStrategy(ABC):
    """
    Abstract base class for requirement checking strategies.

    Each requirement type (blocking, dynamic, etc.) has its own strategy class
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


class DynamicRequirementStrategy(RequirementStrategy):
    """
    Strategy for dynamic (calculated) requirements.

    These requirements are automatically calculated on each file operation
    rather than being manually satisfied. Examples: branch_size_limit,
    test_coverage, complexity_check.

    Features:
    - Automatic calculation via calculator modules
    - Threshold-based evaluation (warn, block)
    - Approval mechanism with TTL
    - Calculation caching for performance
    """

    def __init__(self):
        """
        Initialize dynamic strategy with calculator cache.

        Note:
            Dedup cache initialization is handled by parent class.
            Cache initialization failures are logged but don't prevent strategy creation.
        """
        super().__init__()  # Initialize dedup cache from base class
        self.calculators = {}  # Cache loaded calculator instances
        self.cache = CalculationCache()  # Calculation result cache

    def check(self, req_name: str, config: RequirementsConfig,
              reqs: BranchRequirements, context: dict) -> Optional[dict]:
        """
        Check dynamic requirement with automatic calculation.

        Flow:
        1. Check if satisfied at branch level (via --branch flag) → allow
        2. Check if approved (TTL-based) → allow
        3. Get cached or calculate fresh result
        4. Evaluate thresholds (warn vs block)
        5. Return appropriate response

        Returns:
            None if passes or approved
            Dict with denial if blocked
        """
        # 1. Check if satisfied at branch level (via `req satisfy --branch`)
        # This uses is_satisfied with session scope, which now checks branch-level overrides first
        if reqs.is_satisfied(req_name, scope='session'):
            return None  # Satisfied at branch level, allow

        # 2. Check if approved (TTL-based short-circuit)
        if reqs.is_approved(req_name):
            return None  # Approved, allow

        # 3. Get or calculate result
        result = self._get_result(req_name, config, context)
        if result is None:
            return None  # Skip check (e.g., main branch, error)

        # 3. Evaluate thresholds
        return self._evaluate_thresholds(req_name, config, reqs, result, context)

    def _get_result(self, req_name: str, config: RequirementsConfig,
                   context: dict) -> Optional[dict]:
        """
        Get cached or fresh calculation result.

        Args:
            req_name: Requirement name
            config: Configuration
            context: Context dict

        Returns:
            Calculator result dict or None
        """
        project_dir = context['project_dir']
        branch = context['branch']

        # Check cache (60s TTL, separate from state)
        cache_key = f"{project_dir}:{branch}:{req_name}"
        cache_ttl = config.get_attribute(req_name, 'cache_ttl', 60)

        cached = self.cache.get(cache_key, cache_ttl)
        if cached:
            return cached

        # Load and run calculator
        calculator = self._load_calculator(req_name, config)
        if not calculator:
            return None  # Fail open

        try:
            result = calculator.calculate(project_dir, branch)
            if result:
                self.cache.set(cache_key, result)
            return result

        except Exception as e:
            log_error(f"Calculator failed for '{req_name}': {e}", exc_info=True)
            return None  # Fail open

    def _load_calculator(self, req_name: str,
                        config: RequirementsConfig) -> Optional[RequirementCalculator]:
        """
        Load and validate calculator instance.

        Implements lazy loading with instance caching.

        Args:
            req_name: Requirement name
            config: Configuration

        Returns:
            Calculator instance or None on error
        """
        # Return cached instance if available
        if req_name in self.calculators:
            return self.calculators[req_name]

        # Get calculator module name from config
        module_name = config.get_attribute(req_name, 'calculator')
        if not module_name:
            log_error(f"No calculator configured for '{req_name}'")
            return None

        try:
            # Import calculator module
            module = __import__(f'lib.{module_name}', fromlist=[module_name])

            # Get Calculator class
            if not hasattr(module, 'Calculator'):
                log_error(f"Calculator '{module_name}' missing Calculator class")
                return None

            # Instantiate calculator
            calculator = module.Calculator()

            # Validate implements interface
            if not isinstance(calculator, RequirementCalculator):
                log_error(f"Calculator '{module_name}' doesn't implement RequirementCalculator interface")
                return None

            # Cache for future use
            self.calculators[req_name] = calculator
            return calculator

        except ImportError as e:
            log_error(f"Failed to import calculator '{module_name}': {e}")
            return None
        except Exception as e:
            log_error(f"Failed to load calculator '{module_name}': {e}")
            return None

    def _evaluate_thresholds(self, req_name: str, config: RequirementsConfig,
                            reqs: BranchRequirements, result: dict,
                            context: dict) -> Optional[dict]:
        """
        Evaluate calculation result against thresholds.

        Args:
            req_name: Requirement name
            config: Configuration
            reqs: Requirements state
            result: Calculator result
            context: Context dict

        Returns:
            None if passes
            Dict with denial response if blocked
        """
        thresholds = config.get_attribute(req_name, 'thresholds', {})
        value = result.get('value', 0)

        # Check block threshold first (most severe)
        if value >= thresholds.get('block', float('inf')):
            # BLOCK - require manual approval via CLI
            # Note: We use "deny" not "ask" because "ask" gets overridden by
            # permissions.allow entries in settings.local.json
            message = self._format_block_message(req_name, config, result, context)

            # Deduplication check to prevent spam from parallel tool calls
            if self.dedup_cache:
                session_id = context['session_id']
                cache_key = f"{context['project_dir']}:{context['branch']}:{session_id}:{req_name}"

                if not self.dedup_cache.should_show_message(cache_key, message, ttl=5):
                    # Suppress verbose message - show minimal indicator instead
                    minimal_message = f"⏸️ Requirement `{req_name}` not satisfied (waiting...)"
                    return create_denial_response(minimal_message)

            # Show full message (first time or after TTL expiration)
            return create_denial_response(message)

        # Check warn threshold
        elif value >= thresholds.get('warn', float('inf')):
            # WARN - log but allow operation
            log_warning(f"{req_name}: {result.get('summary', value)}")
            return None

        # Under threshold - allow
        return None

    def _format_block_message(self, req_name: str, config: RequirementsConfig,
                              result: dict, context: dict) -> str:
        """
        Format blocking message with template variable substitution.

        Args:
            req_name: Requirement name
            config: Configuration
            result: Calculator result
            context: Context dict

        Returns:
            Formatted message string
        """
        template = config.get_attribute(req_name, 'blocking_message',
                                       'Requirement {req_name} not satisfied')

        # Prepare template variables
        thresholds = config.get_attribute(req_name, 'thresholds', {})
        template_vars = {
            'req_name': req_name,
            'total': result.get('value', 0),
            'value': result.get('value', 0),
            'summary': result.get('summary', ''),
            'base_branch': result.get('base_branch', ''),
            'warn_threshold': thresholds.get('warn', 0),
            'block_threshold': thresholds.get('block', 0),
        }

        # Add all result fields as potential template variables
        template_vars.update(result)

        # Replace template variables
        try:
            message = template.format(**template_vars)
        except KeyError as e:
            # Template has undefined variable - log and use as-is
            log_warning(f"Template for '{req_name}' references undefined variable: {e}")
            message = template

        # Add CLI approval instructions
        session_id = context['session_id']
        message += f"\n\n💡 **To approve and continue**:"
        message += f"\n```bash"
        message += f"\nreq satisfy {req_name} --session {session_id}"
        message += f"\n```"

        return message


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

        # Get guard type and dispatch to handler
        guard_type = config.get_attribute(req_name, 'guard_type', None)

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

        # Get protected branches list (default: master, main)
        protected_branches = config.get_attribute(
            req_name, 'protected_branches', ['master', 'main']
        )

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


# Strategy registry - maps requirement type to strategy instance
STRATEGIES = {
    'blocking': BlockingRequirementStrategy(),
    'dynamic': DynamicRequirementStrategy(),
    'guard': GuardRequirementStrategy(),
}
