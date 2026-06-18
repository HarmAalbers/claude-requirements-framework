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
from hook_utils import early_hook_setup, collect_unsatisfied
from console import emit_hook_context
from brainstorm import (
    brainstorm_directive,
    resolve_brainstorm_phase,
    nudge_already_shown,
    mark_nudge_shown,
)

# Keywords that suggest the user is about to edit/commit/deploy
EDIT_KEYWORDS = {
    'edit', 'write', 'modify', 'change', 'update', 'fix', 'add', 'remove',
    'delete', 'refactor', 'implement', 'create', 'build',
}
COMMIT_KEYWORDS = {
    'commit', 'push', 'deploy', 'release', 'merge', 'pr ', 'pull request',
    'git add', 'git commit', 'git push', 'gh pr',
}

# Min length (chars) for a keyword-less prompt to count as a real request.
MIN_SUBSTANTIVE_LEN = 40
# First words that mark a prompt as a bare question / status ask (read-only).
QUESTION_STARTERS = {
    'what', 'why', 'how', 'who', 'where', 'when', 'which',
    'is', 'are', 'does', 'can', 'could', 'should', 'explain',
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


def _is_pure_question(prompt: str) -> bool:
    """True if *prompt* opens like a bare question / status ask.

    Looks only at the first word (lowercased, leading punctuation stripped) — a
    cheap proxy for "the user is asking, not requesting work."
    """
    first = prompt.strip().lower().split(None, 1)[0] if prompt.strip() else ''
    first = first.strip('"\'`([{*#-')
    return first in QUESTION_STARTERS


def _prompt_is_substantive(prompt: str) -> bool:
    """Whether *prompt* warrants a proactive brainstorm nudge.

    An explicit edit/commit/feature keyword (``_prompt_needs_context``) is the
    strongest substantive signal and always qualifies — even for a terse prompt
    like "let's implement the auth flow". Without such a keyword we fall back to
    a simple heuristic: a prompt is trivial (and skipped) if it is short
    (< ``MIN_SUBSTANTIVE_LEN`` chars) or opens as a bare question/status ask.
    """
    text = prompt.strip()
    if not text:
        return False
    if _prompt_needs_context(prompt):
        return True
    if len(text) < MIN_SUBSTANTIVE_LEN:
        return False
    if _is_pure_question(prompt):
        return False
    return True


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

        # Session pause: surface a visible banner every turn so a paused session
        # is never silently off. Blocking gates are suppressed elsewhere; nudges
        # and status (this hook) keep firing. Fail-open: any error -> no banner.
        try:
            from pause import paused_banner
            _pb = paused_banner(session_id, project_dir)
            if _pb:
                emit_hook_context("UserPromptSubmit", _pb)
        except Exception as e:
            logger.debug("pause banner skipped (fail-open)", error=str(e))

        # Track prompt in session metrics
        try:
            metrics = SessionMetrics(session_id, project_dir, branch)
            metrics.record_tool_use('UserPrompt', blocked=False)
            metrics.save()
        except Exception as e:
            logger.debug("Failed to record prompt metric", error=str(e))

        reqs = BranchRequirements(branch, session_id, project_dir)

        # Lazy-dev compact reminder (once per session). Fires on a substantive
        # prompt when lazy_dev is enabled; own try/except + fail-open so it never
        # breaks prompt submission and never early-returns (the brainstorm nudge
        # and status injection below must still run).
        try:
            if (prompt and config.get_hook_config('lazy_dev', 'enabled')
                    and _prompt_is_substantive(prompt)):
                from ruleset_marker import shown as _ladder_shown, mark_shown as _mark_ladder
                if not _ladder_shown(session_id, project_dir):
                    from lazy_dev.rules import COMPACT_REMINDER
                    emit_hook_context('UserPromptSubmit', COMPACT_REMINDER)
                    _mark_ladder(session_id, project_dir)
        except Exception:
            pass

        # PROACTIVE brainstorm nudge (mode-independent). UserPromptSubmit fires
        # every turn in every mode, so this reaches auto-accept users who never
        # enter plan mode (where handle-plan-enter would otherwise nudge). Fires
        # at most once per session via the shared dedup marker, and only at the
        # brainstorm/design phase (gate unsatisfied) for a substantive prompt.
        if (
            prompt
            and config.get_hook_config('prompt_submit', 'brainstorm_nudge', True)
            and _prompt_is_substantive(prompt)
            and not nudge_already_shown(session_id, project_dir)
        ):
            gate, skill = resolve_brainstorm_phase(config)
            req_config = config.get_requirement(gate)
            scope = (req_config or {}).get('scope', 'session')
            if not reqs.is_satisfied(gate, scope):
                emit_hook_context("UserPromptSubmit", brainstorm_directive(skill))
                mark_nudge_shown(session_id, project_dir)
                logger.debug(
                    "Injected brainstorm nudge", gate=gate, skill=skill
                )
                return 0

        # Only inject context when prompt relates to editing/committing
        if not prompt or not _prompt_needs_context(prompt):
            return 0

        # Build compact status (guard-aware: a passing guard is not "unsatisfied")
        unsatisfied = collect_unsatisfied(reqs, config, branch, session_id, project_dir)

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
