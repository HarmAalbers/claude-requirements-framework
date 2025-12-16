# ADR-002: Use Claude Code's Native Session ID

## Status
Accepted

## Date
2024-12-16

## Context

The requirements framework generates session IDs to track which Claude Code session satisfied which requirements. Originally, we generated our own session IDs using:

```python
def get_session_id() -> str:
    """Generate session ID from parent process ID."""
    ppid = os.getppid()
    return hashlib.md5(str(ppid).encode()).hexdigest()[:8]
```

This approach had limitations:
1. **PPID instability**: Parent process IDs can change if Claude Code's process tree changes
2. **No cross-process correlation**: Our generated ID couldn't be correlated with Claude Code's internal session tracking
3. **Duplicate IDs possible**: Different sessions could theoretically get the same PPID

Claude Code now provides its own `session_id` in the hook's stdin input, which is stable and authoritative.

## Decision

Use Claude Code's native `session_id` from stdin when available, falling back to PPID-based generation for backward compatibility.

### Implementation

```python
# Read hook input from stdin EARLY (before session_id generation)
input_data = {}
try:
    stdin_content = sys.stdin.read()
    if stdin_content:
        input_data = json.loads(stdin_content)
except json.JSONDecodeError as e:
    # Log parsing errors to help debug hook issues
    # ... debug logging ...
    pass

# Use Claude Code's session_id if provided, fallback to ppid-based generation
session_id = input_data.get('session_id') or get_session_id()
```

### Key Changes
1. **Stdin reading moved earlier**: Now happens before any session ID usage
2. **Native session_id preferred**: Uses Claude Code's ID when available
3. **Debug logging added**: JSON parse errors are logged for troubleshooting
4. **Backward compatible**: Falls back to PPID-based ID if stdin doesn't provide one

## Consequences

### Positive
- Session IDs are stable and authoritative
- Better correlation with Claude Code's internal tracking
- More reliable session detection across hook invocations
- Debug logging helps troubleshoot hook issues

### Negative
- Slightly more complex stdin handling (reading earlier in the flow)
- Existing sessions with old-style IDs won't match (one-time migration)

### Neutral
- Fallback ensures backward compatibility with older Claude Code versions

## Related
- ADR-001: Remove Main/Master Branch Skip (related change in same commit)
