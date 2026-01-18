# Strategy Pattern Architecture

> How the framework uses strategy pattern for extensible requirement types

## Overview

The requirements framework uses the Strategy pattern to handle different requirement types (blocking, dynamic, guard) through a pluggable architecture.

## Core Design

**Location**: `hooks/lib/strategy_registry.py`

```python
# Central registry maps type → strategy instance
STRATEGIES = {
    'blocking': BlockingRequirementStrategy(),
    'dynamic': DynamicRequirementStrategy(),
    'guard': GuardRequirementStrategy(),
}

def get_strategy(req_type: str) -> RequirementStrategy:
    return STRATEGIES.get(req_type)
```

## Base Strategy: `base_strategy.py`

```python
class RequirementStrategy(ABC):
    @abstractmethod
    def check(self, req_name: str, config: RequirementsConfig,
              reqs: BranchRequirements, context: dict) -> Optional[dict]:
        """
        Check if requirement is satisfied.
        Returns: None (allow) or dict (denial response)
        """
        pass
```

## Strategy Implementations

### 1. BlockingRequirementStrategy (`blocking_strategy.py`)

**Use**: Must be manually satisfied via CLI or skill
**Returns**: Denial if not satisfied

```python
def check(self, req_name, config, reqs, context):
    scope = config.get_scope(req_name)
    if not reqs.is_satisfied(req_name, scope):
        return self._create_denial_response(req_name, config, context)
    return None
```

**Example**:
```yaml
pre_commit_review:
  type: blocking
  scope: single_use
```

### 2. DynamicRequirementStrategy (`dynamic_strategy.py`)

**Use**: Calculated/evaluated dynamically (e.g., branch size limits)
**Returns**: Denial if calculation fails condition

```python
def check(self, req_name, config, reqs, context):
    calculator = get_calculator(config, req_name)
    result = calculator.calculate()
    if not passes_threshold(result, config):
        return self._create_denial_response(...)
    return None
```

**Example**:
```yaml
branch_size_limit:
  type: dynamic
  calculator: branch_size
  max_lines: 500
```

### 3. GuardRequirementStrategy (`guard_strategy.py`)

**Use**: Conditional gates (e.g., protected branches, file patterns)
**Returns**: Denial if guard condition violated

**Types**:
- `protected_branch`: Block changes on protected branches
- `file_pattern`: Require approval for certain files
- `single_session`: Ensure one session per branch

**Example**:
```yaml
main_branch_protection:
  type: guard
  guard_type: protected_branch
  branches: ['main', 'master']
```

## Dispatch Flow in check-requirements.py

```python
# 1. Load config and requirements
config = RequirementsConfig.load()
reqs = BranchRequirements(session_id)

# 2. Iterate requirements
for req_name in config.get_all_requirements():
    req_type = config.get_type(req_name)
    
    # 3. Get strategy for type
    strategy = STRATEGIES.get(req_type)
    
    # 4. Check requirement
    response = strategy.check(req_name, config, reqs, context)
    
    # 5. Collect denials
    if response:
        denials.append(response)

# 6. Return aggregated denials or allow
if denials:
    emit_json(batch_denials(denials))
    sys.exit(1)
else:
    sys.exit(0)
```

## Adding New Strategy Types

1. **Create strategy file**: `hooks/lib/my_strategy.py`

```python
from hooks.lib.base_strategy import RequirementStrategy

class MyRequirementStrategy(RequirementStrategy):
    def check(self, req_name, config, reqs, context):
        # Custom logic
        if not my_condition():
            return self._create_denial_response(...)
        return None
```

2. **Register in registry**: `hooks/lib/strategy_registry.py`

```python
STRATEGIES = {
    'blocking': BlockingRequirementStrategy(),
    'dynamic': DynamicRequirementStrategy(),
    'guard': GuardRequirementStrategy(),
    'my_type': MyRequirementStrategy(),  # Add here
}
```

3. **Use in config**:

```yaml
my_requirement:
  type: my_type  # Uses MyRequirementStrategy
```

## Strategy Utilities: `strategy_utils.py`

Shared utilities for all strategies:
- `create_denial_response()` - Standard denial format
- `format_message()` - Message templating
- `check_ttl_expiration()` - TTL validation

## Related Files

- `hooks/lib/strategy_registry.py` - Central registry
- `hooks/lib/base_strategy.py` - Abstract base class
- `hooks/lib/blocking_strategy.py` - Blocking implementation
- `hooks/lib/dynamic_strategy.py` - Dynamic implementation
- `hooks/lib/guard_strategy.py` - Guard implementation
- `hooks/lib/strategy_utils.py` - Shared utilities
- `hooks/check-requirements.py:354` - Strategy dispatch
