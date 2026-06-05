#!/usr/bin/env python3
"""
PostToolUseFailure Hook for Requirements Framework.

Triggered when a tool call fails (throws error or returns failure).
Responsibilities:
1. Track failure patterns in session metrics
2. Provide requirement-aware error guidance
3. Suggest running review skills after repeated failures

Input (stdin JSON):
{
    "session_id": "abc123",
    "hook_event_name": "PostToolUseFailure",
    "tool_name": "Edit",
    "tool_input": {"file_path": "/path/to/file"},
    "error": "Error message string",
    "is_interrupt": false,
    "cwd": "/path/to/project"
}

Output:
- Structured JSON with hookSpecificOutput.additionalContext (guidance)
- Empty if no guidance needed
"""
import json
import os
import sys
from pathlib import Path

# Add lib to path
lib_path = Path(__file__).parent / 'lib'
sys.path.insert(0, str(lib_path))

from session import normalize_session_id
from session_metrics import SessionMetrics
from hook_utils import early_hook_setup
from console import emit_hook_context

# Failure threshold before suggesting review
FAILURE_THRESHOLD = 3


def main() -> int:
    """Hook entry point."""
    input_data = {}
    try:
        stdin_content = sys.stdin.read()
        if stdin_content:
            input_data = json.loads(stdin_content)
    except json.JSONDecodeError:
        return 0  # Fail open

    raw_session = input_data.get('session_id')
    if not raw_session:
        return 0

    session_id = normalize_session_id(raw_session)
    tool_name = input_data.get('tool_name', '')
    error_msg = input_data.get('error', '')
    is_interrupt = input_data.get('is_interrupt', False)

    # Early hook setup
    project_dir, branch, config, logger = early_hook_setup(
        session_id, "PostToolUseFailure", cwd=input_data.get('cwd')
    )

    try:
        if os.environ.get('CLAUDE_SKIP_REQUIREMENTS'):
            return 0

        if not project_dir or not branch or not config:
            return 0

        if not config.is_enabled():
            return 0

        # Don't process interrupts
        if is_interrupt:
            return 0

        # Record failure in session metrics
        metrics = SessionMetrics(session_id, project_dir, branch)
        metrics.record_tool_use(tool_name, blocked=False, file=None)

        # Track failure count for this tool type
        summary = metrics.get_summary()
        # Use a simple counter based on existing metrics
        failure_key = f'failures_{tool_name}'
        failures = summary.get(failure_key, 0) + 1

        # Store updated failure count
        try:
            metrics.data.setdefault('failure_counts', {})[tool_name] = failures
            metrics.save()
        except Exception as e:
            logger.debug("Failed to save failure count", error=str(e))

        logger.info(
            "Tool failure recorded",
            tool=tool_name,
            error_preview=error_msg[:100] if error_msg else "",
            failure_count=failures,
        )

        # After repeated Edit/Write failures, suggest running pre-commit review
        if tool_name in ('Edit', 'Write', 'MultiEdit') and failures >= FAILURE_THRESHOLD:
            context = (
                f"**Repeated {tool_name} failures detected** ({failures} failures). "
                "Consider running `/pre-commit` to identify underlying issues before continuing."
            )
            emit_hook_context("PostToolUseFailure", context)

        return 0

    except Exception as e:
        logger.error("Unhandled error in PostToolUseFailure hook", error=str(e))
        return 0  # Fail open


if __name__ == '__main__':
    sys.exit(main())
