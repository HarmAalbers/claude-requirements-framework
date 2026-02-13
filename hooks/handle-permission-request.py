#!/usr/bin/env python3
"""
PermissionRequest Hook for Requirements Framework.

Triggered when a permission dialog is about to be shown.
Responsibilities:
1. Auto-deny dangerous command patterns (rm -rf, force push, etc.)
2. Log permission patterns in session metrics

Input (stdin JSON):
{
    "session_id": "abc123",
    "hook_event_name": "PermissionRequest",
    "tool_name": "Bash",
    "tool_input": {"command": "rm -rf /"},
    "cwd": "/path/to/project"
}

Output:
- {"decision": "deny", "reason": "..."} to block dangerous commands
- Empty to allow the permission dialog to proceed normally
"""
import json
import os
import re
import sys
from pathlib import Path

# Add lib to path
lib_path = Path(__file__).parent / 'lib'
sys.path.insert(0, str(lib_path))

from session import normalize_session_id
from session_metrics import SessionMetrics
from hook_utils import early_hook_setup
from console import emit_json

# Dangerous command patterns that should be auto-denied
DANGEROUS_PATTERNS = [
    (re.compile(r'rm\s+(-[rfR]+\s+)?/(?!\btmp\b)'), 'Destructive rm on root directory'),
    (re.compile(r'git\s+push\s+.*--force(?!-with-lease)'), 'Force push without lease protection'),
    (re.compile(r'git\s+push\s+.*-f\b'), 'Force push (shorthand)'),
    (re.compile(r'git\s+reset\s+--hard\s+origin/(?:main|master)'), 'Hard reset to remote main'),
    (re.compile(r'git\s+clean\s+-[dfx]+'), 'Git clean (removes untracked files)'),
    (re.compile(r'DROP\s+(?:TABLE|DATABASE)', re.IGNORECASE), 'SQL DROP statement'),
    (re.compile(r'TRUNCATE\s+TABLE', re.IGNORECASE), 'SQL TRUNCATE statement'),
]


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
    tool_input = input_data.get('tool_input', {})

    # Early hook setup
    project_dir, branch, config, logger = early_hook_setup(
        session_id, "PermissionRequest", cwd=input_data.get('cwd')
    )

    try:
        if os.environ.get('CLAUDE_SKIP_REQUIREMENTS'):
            return 0

        if not project_dir or not branch or not config:
            return 0

        if not config.is_enabled():
            return 0

        # Check if permission safety is enabled (default: True)
        if not config.get_hook_config('permission_request', 'auto_deny_dangerous', True):
            return 0

        # Only check Bash commands for dangerous patterns
        if tool_name != 'Bash':
            return 0

        command = tool_input.get('command', '')
        if not command:
            return 0

        # Check against dangerous patterns
        for pattern, description in DANGEROUS_PATTERNS:
            if pattern.search(command):
                logger.warning(
                    "Auto-denied dangerous command",
                    command_preview=command[:100],
                    reason=description,
                )

                # Record in metrics
                try:
                    metrics = SessionMetrics(session_id, project_dir, branch)
                    metrics.record_tool_use('PermissionDenied', blocked=True)
                    metrics.save()
                except Exception:
                    pass

                response = {
                    "decision": "deny",
                    "reason": f"**Blocked by requirements framework**: {description}\n\n"
                              f"Command: `{command[:80]}{'...' if len(command) > 80 else ''}`\n\n"
                              "If you need to run this command, disable the safety check:\n"
                              "`req config set hooks.permission_request.auto_deny_dangerous false`"
                }
                emit_json(response)
                return 0

        return 0

    except Exception as e:
        logger.error("Unhandled error in PermissionRequest hook", error=str(e))
        return 0  # Fail open


if __name__ == '__main__':
    sys.exit(main())
