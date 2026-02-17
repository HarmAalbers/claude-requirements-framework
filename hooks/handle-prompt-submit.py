#!/usr/bin/env python3
"""
UserPromptSubmit Hook for Requirements Framework.

Triggered when the user submits a prompt, BEFORE Claude processes it.
Responsibilities:
1. Inject compact requirement status when prompt relates to editing/committing
2. Track prompt count in session metrics

Input (stdin JSON):
{
    "session_id": "abc123",
    "hook_event_name": "UserPromptSubmit",
    "prompt": "The user's full prompt text",
    "cwd": "/path/to/project"
}

Output:
- Structured JSON with hookSpecificOutput.additionalContext (injected into Claude's context)
- Empty if no context needed
"""
import json
import os
import sys
from pathlib import Path

# Add lib to path
lib_path = Path(__file__).parent / 'lib'
sys.path.insert(0, str(lib_path))

from requirements import BranchRequirements
from session import normalize_session_id
from session_metrics import SessionMetrics
from hook_utils import early_hook_setup
from console import emit_hook_context

# Keywords that suggest the user is about to edit/commit/deploy
EDIT_KEYWORDS = {
    'edit', 'write', 'modify', 'change', 'update', 'fix', 'add', 'remove',
    'delete', 'refactor', 'implement', 'create', 'build',
}
COMMIT_KEYWORDS = {
    'commit', 'push', 'deploy', 'release', 'merge', 'pr ', 'pull request',
    'git add', 'git commit', 'git push', 'gh pr',
}


def _prompt_needs_context(prompt: str) -> bool:
    """Check if a prompt relates to editing or committing."""
    prompt_lower = prompt.lower()
    # Check commit keywords (higher priority)
    for keyword in COMMIT_KEYWORDS:
        if keyword in prompt_lower:
            return True
    # Check edit keywords
    words = set(prompt_lower.split())
    return bool(words & EDIT_KEYWORDS)


def main() -> int:
    """Hook entry point."""
    input_data = {}
    try:
        stdin_content = sys.stdin.read()
        if stdin_content:
            input_data = json.loads(stdin_content)
    except json.JSONDecodeError:
        return 0  # Fail open

    # Get session ID
    raw_session = input_data.get('session_id')
    if not raw_session:
        return 0  # Fail open

    session_id = normalize_session_id(raw_session)
    prompt = input_data.get('prompt', '')

    # Early hook setup
    project_dir, branch, config, logger = early_hook_setup(
        session_id, "UserPromptSubmit", cwd=input_data.get('cwd')
    )

    try:
        if os.environ.get('CLAUDE_SKIP_REQUIREMENTS'):
            return 0

        if not project_dir or not branch or not config:
            return 0

        if not config.is_enabled():
            return 0

        # Track prompt in session metrics
        try:
            metrics = SessionMetrics(session_id, project_dir, branch)
            metrics.record_tool_use('UserPrompt', blocked=False)
            metrics.save()
        except Exception as e:
            logger.debug("Failed to record prompt metric", error=str(e))

        # Only inject context when prompt relates to editing/committing
        if not prompt or not _prompt_needs_context(prompt):
            return 0

        # Build compact status
        reqs = BranchRequirements(branch, session_id, project_dir)
        unsatisfied = []
        for req_name in config.get_all_requirements():
            if not config.is_requirement_enabled(req_name):
                continue
            scope = config.get_scope(req_name)
            if not reqs.is_satisfied(req_name, scope):
                unsatisfied.append(req_name)

        if not unsatisfied:
            return 0  # All satisfied, no context needed

        # Inject compact reminder
        context = f"**Requirements reminder**: {len(unsatisfied)} unsatisfied: {', '.join(unsatisfied)}"
        emit_hook_context("UserPromptSubmit", context)
        logger.debug("Injected prompt context", unsatisfied_count=len(unsatisfied))

        return 0

    except Exception as e:
        logger.error("Unhandled error in UserPromptSubmit hook", error=str(e))
        return 0  # Fail open


if __name__ == '__main__':
    sys.exit(main())
