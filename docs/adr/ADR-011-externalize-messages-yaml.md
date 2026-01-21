# ADR-011: Externalize Messages to YAML Files

## Status
Approved (2026-01-21)

## Context

The requirements framework had ~180 hardcoded message strings scattered across Python files:
- Blocking messages in `check-requirements.py` and strategy classes
- Status briefing templates in `handle-session-start.py`
- CLI output in `requirements-cli.py`
- Structural elements (headers, labels, separators) in various hooks

This created several problems:
1. **Non-developers couldn't customize messages** without editing Python code
2. **A/B testing messages** required code changes and redeployment
3. **Consistency was hard to maintain** with strings duplicated across files
4. **Translation/localization** would require invasive code changes

## Decision

**Move all framework messages to external YAML files with cascade loading.**

### Architecture

#### Message File Organization
```
~/.claude/
  messages/                    # Global defaults
    _templates.yaml            # Shared templates by type
    _status.yaml               # Status format templates
    commit_plan.yaml           # Per-requirement messages
    adr_reviewed.yaml
    ...

<project>/.claude/
  messages/                    # Project-specific (version controlled)
    _templates.yaml
    custom_req.yaml

<project>/.claude/
  messages.local/              # Local overrides (gitignored)
    commit_plan.yaml
```

#### Message File Schema (`<requirement_name>.yaml`)
Each requirement has 6 required fields:
```yaml
version: "1.0"
blocking_message: |
  ## Blocked: {req_name}
  **Execute**: `/{satisfied_by_skill}`
short_message: "Requirement `{req_name}` not satisfied (waiting...)"
success_message: "Requirement `{req_name}` satisfied"
header: "Commit Plan"
action_label: "Run `/plan-review`"
fallback_text: "req satisfy {req_name}"
```

#### Cascade Loading Priority
Same as requirements config: **local > project > global**

The loader checks directories in this order and uses the first file found.

#### Core Module (`hooks/lib/messages.py`)
```python
class MessageLoader:
    """Load messages with cascade priority: local > project > global."""

    def get_messages(self, req_name: str, req_type: str) -> RequirementMessages:
        """Get messages for a requirement (cached)."""

    def get_status_template(self, mode: str) -> str:
        """Get status format template (compact/standard/rich)."""

    def get_structural(self, key: str, **kwargs) -> str:
        """Get structural element (headers, labels, separators)."""
```

#### Integration with Strategy Pattern
Strategies are singletons created at module load time, but MessageLoader needs project context. Solution: **pass MessageLoader via context dict**.

```python
# In check-requirements.py
context = {
    'project_dir': project_dir,
    'session_id': session_id,
    'message_loader': MessageLoader(project_dir, strict=False),
}

# In strategy classes
def _create_denial_response(self, req_name, config, context):
    message_loader = self._get_message_loader(context)
    if message_loader:
        messages = message_loader.get_messages(req_name, 'blocking')
        # Use externalized messages
```

### Validation

CLI command validates message files:
```bash
req messages validate           # Validate all message files
req messages validate --fix     # Generate missing files from templates
req messages list               # List all loaded message files with sources
```

### Calculator Messages Stay in Code

Dynamic requirement calculators provide their own messages because they need access to result data structures:

```python
class CalculatorMessageProvider(Protocol):
    def get_blocking_message(self, result: dict, context: dict) -> str: ...
    def get_short_message(self, result: dict) -> str: ...
```

## Consequences

### Positive
- Messages can be customized without touching Python code
- A/B testing possible through git branches
- Clear separation of concerns (code vs. content)
- Consistent message structure enforced by schema validation
- Future-proof for localization

### Negative
- Additional file I/O during requirement checking
- More files to manage in the message directories
- Breaking change: inline `message` config option removed

### Neutral
- Uses `strict=False` at runtime for backwards compatibility (missing files use templates)
- Validation available via CLI for strict checking
- Calculator messages remain in code (appropriate for dynamic content)

## Implementation Notes

1. **Fail-open design**: Uses `strict=False` at runtime so missing message files don't break hooks
2. **Safe string formatting**: Regex-based substitution leaves unknown `{placeholders}` unchanged
3. **Caching**: MessageLoader caches parsed YAML files to avoid repeated I/O
4. **Context injection**: MessageLoader passed via context dict to work with singleton strategies
5. **Template fallback**: If specific requirement file missing, uses type-based defaults from `_templates.yaml`

## Files Created/Modified

### New Files
- `hooks/lib/messages.py` - Core MessageLoader, RequirementMessages classes
- `hooks/lib/message_validator.py` - ValidationResult, MessageValidator classes
- `~/.claude/messages/_templates.yaml` - Type-based default templates
- `~/.claude/messages/_status.yaml` - Status briefing format templates
- `~/.claude/messages/*.yaml` - Individual requirement message files

### Modified Files
- `hooks/lib/base_strategy.py` - Added `_get_message_loader()` method
- `hooks/lib/blocking_strategy.py` - Use MessageLoader for denial responses
- `hooks/lib/guard_strategy.py` - Use MessageLoader for denial responses
- `hooks/check-requirements.py` - Inject MessageLoader into context
- `hooks/requirements-cli.py` - Added `req messages` command

## Example Usage

### Customizing a Message (Project-Level)
```bash
# Create project message directory
mkdir -p .claude/messages

# Override commit_plan messages for this project
cat > .claude/messages/commit_plan.yaml << 'EOF'
version: "1.0"
blocking_message: |
  ## Hold Up! Need a Plan First

  Before making changes, create a commit plan to ensure
  organized, reviewable commits.

  **Run**: `/plan-review`
short_message: "Plan required before editing"
success_message: "Plan approved - proceed with implementation"
header: "Commit Planning"
action_label: "Create plan with `/plan-review`"
fallback_text: "req satisfy commit_plan"
EOF
```

### Validating Messages
```bash
$ req messages validate
Validating message files...

Global: /Users/harm/.claude/messages
  _templates.yaml ............ OK
  _status.yaml ............... OK
  commit_plan.yaml ........... OK
  adr_reviewed.yaml .......... OK
  ...

9 files validated, 0 errors
```
