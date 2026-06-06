#!/usr/bin/env python3
"""
Dynamic requirement strategy.

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

import importlib
from typing import Optional

DEFAULT_CACHE_TTL_SECONDS = 60
DEDUP_MESSAGE_TTL_SECONDS = 5

# Import from sibling modules
try:
    from base_strategy import RequirementStrategy
    from requirements import BranchRequirements
    from config import RequirementsConfig
    from calculator_interface import RequirementCalculator
    from calculation_cache import CalculationCache
    from strategy_utils import log_error, log_warning, create_denial_response
except ImportError:
    # For testing, allow imports to fail gracefully
    pass


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

    def _get_session_id(self, context: dict) -> str:
        """
        Get session id with a safe default.

        Args:
            context: Context dict

        Returns:
            Session identifier string
        """
        return context.get("session_id", "unknown")

    def _get_context_value(self, context: dict, key: str, req_name: str) -> Optional[str]:
        """
        Get a required context value with fail-open behavior.

        Args:
            context: Context dict
            key: Required key to read
            req_name: Requirement name for logging

        Returns:
            Context value or None if missing
        """
        value = context.get(key)
        if not value:
            log_error(f"Missing required context '{key}' for dynamic requirement '{req_name}'")
            return None
        return value

    def _get_required_context(
        self,
        context: dict,
        req_name: str,
        *keys: str,
    ) -> Optional[dict]:
        """
        Get required context values with fail-open behavior.

        Args:
            context: Context dict
            req_name: Requirement name for logging
            keys: Required keys to read

        Returns:
            Dict of values or None if any missing
        """
        values = {}
        for key in keys:
            value = self._get_context_value(context, key, req_name)
            if not value:
                return None
            values[key] = value
        return values

    def _build_dedup_cache_key(self, context: dict, req_name: str, session_id: str) -> str:
        """
        Build a dedup cache key using available context values.

        Args:
            context: Context dict
            req_name: Requirement name
            session_id: Session identifier

        Returns:
            Cache key string
        """
        project_dir = context.get("project_dir", "")
        branch = context.get("branch", "")
        return f"{project_dir}:{branch}:{session_id}:{req_name}"

    def _create_block_response(self, req_name: str, message: str, context: dict) -> dict:
        """
        Create a deduplicated denial response for block conditions.

        Args:
            req_name: Requirement name
            message: Full denial message
            context: Context dict

        Returns:
            Hook response dict
        """
        if self.dedup_cache:
            session_id = self._get_session_id(context)
            cache_key = self._build_dedup_cache_key(context, req_name, session_id)

            if not self.dedup_cache.should_show_message(
                cache_key,
                message,
                ttl=DEDUP_MESSAGE_TTL_SECONDS,
            ):
                minimal_message = f"⏸️ Requirement `{req_name}` not satisfied (waiting...)"
                return create_denial_response(minimal_message)

        return create_denial_response(message)

    def check(
        self,
        req_name: str,
        config: RequirementsConfig,
        reqs: BranchRequirements,
        context: dict,
    ) -> Optional[dict]:
        """
        Check dynamic requirement with automatic calculation.

        Flow:
        1. Check if satisfied at branch level (via --branch flag) → allow
        2. Check if approved (TTL-based) → allow
        3. Load dynamic requirement config (fail open on invalid)
        4. Get cached or calculate fresh result
        5. Evaluate thresholds (warn vs block)
        6. Return appropriate response

        Returns:
            None if passes or approved
            Dict with denial if blocked
        """
        # 1. Check if satisfied at branch level (via `req satisfy --branch`)
        # This uses is_satisfied with session scope, which now checks branch-level overrides first
        if reqs.is_satisfied(req_name, scope="session"):
            return None  # Satisfied at branch level, allow

        # 2. Check if approved (TTL-based short-circuit)
        if reqs.is_approved(req_name):
            return None  # Approved, allow

        # 3. Load dynamic requirement config once
        req_config = self._get_dynamic_config(req_name, config)
        if not req_config:
            return None  # Fail open on missing/invalid config

        # 4. Get or calculate result
        result = self._get_result(req_name, config, req_config, context)
        if result is None:
            return None  # Skip check (e.g., main branch, error)

        # 5. Evaluate thresholds
        return self._evaluate_thresholds(req_name, config, req_config, reqs, result, context)

    def _get_dynamic_config(
        self,
        req_name: str,
        config: RequirementsConfig,
    ) -> Optional[dict]:
        """
        Load and validate dynamic requirement config once.

        Args:
            req_name: Requirement name
            config: Configuration

        Returns:
            Dynamic requirement config dict or None on error
        """
        try:
            req_config = config.get_dynamic_config(req_name)
            if not req_config:
                log_error(f"Dynamic requirement '{req_name}' not found")
                return None
            return req_config
        except ValueError as e:
            log_error(f"Invalid dynamic requirement config for '{req_name}': {e}")
            return None

    def _get_result(
        self,
        req_name: str,
        config: RequirementsConfig,
        req_config: dict,
        context: dict,
    ) -> Optional[dict]:
        """
        Get cached or fresh calculation result.

        Args:
            req_name: Requirement name
            config: Configuration
            req_config: Dynamic requirement config
            context: Context dict

        Returns:
            Calculator result dict or None
        """
        context_values = self._get_required_context(context, req_name, "project_dir", "branch")
        if not context_values:
            return None

        project_dir = context_values["project_dir"]
        branch = context_values["branch"]

        # Check cache (60s TTL, separate from state)
        cache_key = self._build_cache_key(project_dir, branch, req_name)
        cache_ttl = config.get_attribute(req_name, "cache_ttl", DEFAULT_CACHE_TTL_SECONDS)

        cached = self.cache.get(cache_key, cache_ttl)
        if cached is not None:
            return cached

        # Load and run calculator
        calculator = self._load_calculator(req_name, req_config)
        if not calculator:
            return None  # Fail open

        return self._run_calculator(calculator, project_dir, branch, cache_key, req_name)

    def _build_cache_key(self, project_dir: str, branch: str, req_name: str) -> str:
        """
        Build a cache key for calculation results.

        Args:
            project_dir: Project root path
            branch: Git branch name
            req_name: Requirement name

        Returns:
            Cache key string
        """
        return f"{project_dir}:{branch}:{req_name}"

    def _run_calculator(
        self,
        calculator: RequirementCalculator,
        project_dir: str,
        branch: str,
        cache_key: str,
        req_name: str,
    ) -> Optional[dict]:
        """
        Run calculator and cache the result.

        Args:
            calculator: Calculator instance
            project_dir: Project root path
            branch: Git branch name
            cache_key: Cache key for results
            req_name: Requirement name for logging

        Returns:
            Calculator result dict or None
        """
        try:
            result = calculator.calculate(project_dir, branch)
            if result is not None:
                self.cache.set(cache_key, result)
            return result

        except Exception as e:
            log_error(f"Calculator failed for '{req_name}': {e}", exc_info=True)
            return None  # Fail open

    def _load_calculator(
        self,
        req_name: str,
        req_config: dict,
    ) -> Optional[RequirementCalculator]:
        """
        Load and validate calculator instance.

        Implements lazy loading with instance caching.

        Args:
            req_name: Requirement name
            req_config: Dynamic requirement config

        Returns:
            Calculator instance or None on error
        """
        # Return cached instance if available
        if req_name in self.calculators:
            return self.calculators[req_name]

        # Type system now guarantees 'calculator' field exists
        module_name = req_config["calculator"]

        try:
            # Import calculator module
            module = importlib.import_module(f"lib.{module_name}")

            # Get Calculator class
            calculator_class = getattr(module, "Calculator", None)
            if not calculator_class:
                log_error(f"Calculator '{module_name}' missing Calculator class")
                return None

            # Instantiate calculator
            calculator = calculator_class()

            # Validate implements interface
            if not isinstance(calculator, RequirementCalculator):
                log_error(
                    f"Calculator '{module_name}' doesn't implement RequirementCalculator interface"
                )
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

    def _evaluate_thresholds(
        self,
        req_name: str,
        config: RequirementsConfig,
        req_config: dict,
        reqs: BranchRequirements,
        result: dict,
        context: dict,
    ) -> Optional[dict]:
        """
        Evaluate calculation result against thresholds.

        Args:
            req_name: Requirement name
            config: Configuration
            req_config: Dynamic requirement config
            reqs: Requirements state
            result: Calculator result
            context: Context dict

        Returns:
            None if passes
            Dict with denial response if blocked
        """
        # Type system now guarantees 'thresholds' field exists
        thresholds = req_config["thresholds"]

        value = result.get("value", 0)
        block_threshold = thresholds.get("block", float("inf"))
        warn_threshold = thresholds.get("warn", float("inf"))

        # Check block threshold first (most severe)
        if value >= block_threshold:
            # BLOCK - require manual approval via CLI
            # Note: We use "deny" not "ask" because "ask" gets overridden by
            # permissions.allow entries in settings.local.json
            message = self._format_block_message(req_name, config, thresholds, result, context)

            return self._create_block_response(req_name, message, context)

        # Check warn threshold
        if value >= warn_threshold:
            # WARN - log but allow operation
            log_warning(f"{req_name}: {result.get('summary', value)}")
            return None

        # Under threshold - allow
        return None

    def _build_template_vars(self, req_name: str, thresholds: dict, result: dict) -> dict:
        """
        Build template variables for blocking messages.

        Args:
            req_name: Requirement name
            thresholds: Thresholds for the requirement
            result: Calculator result

        Returns:
            Template variable mapping
        """
        value = result.get("value", 0)
        template_vars = {
            "req_name": req_name,
            "total": value,
            "value": value,
            "summary": result.get("summary", ""),
            "base_branch": result.get("base_branch", ""),
            "warn_threshold": thresholds.get("warn", 0),
            "block_threshold": thresholds.get("block", 0),
        }

        # Add all result fields as potential template variables
        template_vars.update(result)

        return template_vars

    def _format_message_template(self, req_name: str, template: str, template_vars: dict) -> str:
        """
        Format template variables into a message string.

        Args:
            req_name: Requirement name
            template: Message template
            template_vars: Template variable mapping

        Returns:
            Formatted message string
        """
        try:
            return template.format(**template_vars)
        except KeyError as e:
            # Template has undefined variable - log and use as-is
            log_warning(f"Template for '{req_name}' references undefined variable: {e}")
            return template

    def _approval_instructions(self, req_name: str, session_id: str) -> str:
        """
        Build CLI approval instructions.

        Args:
            req_name: Requirement name
            session_id: Session identifier

        Returns:
            Approval instructions string
        """
        return (
            "\n\n💡 **To approve and continue**:"
            "\n```bash"
            f"\nreq satisfy {req_name} --session {session_id}"
            "\n```"
        )

    def _format_block_message(
        self,
        req_name: str,
        config: RequirementsConfig,
        thresholds: dict,
        result: dict,
        context: dict,
    ) -> str:
        """
        Format blocking message with template variable substitution.

        Args:
            req_name: Requirement name
            config: Configuration
            thresholds: Thresholds for the requirement
            result: Calculator result
            context: Context dict

        Returns:
            Formatted message string
        """
        template = config.get_attribute(
            req_name,
            "blocking_message",
            "Requirement {req_name} not satisfied",
        )

        template_vars = self._build_template_vars(req_name, thresholds, result)
        message = self._format_message_template(req_name, template, template_vars)

        session_id = self._get_session_id(context)
        return message + self._approval_instructions(req_name, session_id)
