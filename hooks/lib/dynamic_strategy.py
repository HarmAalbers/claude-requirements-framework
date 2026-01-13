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

from typing import Optional

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

        # Get calculator module name from config using type-safe accessor
        try:
            req_config = config.get_dynamic_config(req_name)
            if not req_config:
                log_error(f"Dynamic requirement '{req_name}' not found")
                return None
            # Type system now guarantees 'calculator' field exists
            module_name = req_config['calculator']
        except ValueError as e:
            log_error(f"Invalid dynamic requirement config for '{req_name}': {e}")
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
        # Get thresholds using type-safe accessor
        try:
            req_config = config.get_dynamic_config(req_name)
            if not req_config:
                log_error(f"Dynamic requirement '{req_name}' not found")
                return None
            # Type system now guarantees 'thresholds' field exists
            thresholds = req_config['thresholds']
        except ValueError as e:
            log_error(f"Invalid dynamic requirement config for '{req_name}': {e}")
            return None

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
