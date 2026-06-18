#!/usr/bin/env python3
"""
SubagentStart Hook for Requirements Framework.

Triggered when a subagent (Task tool) is spawned.
Injects requirement context into review subagents so they are aware
of the current requirement state and can focus their review accordingly.

Input (stdin JSON):
{
    "session_id": "abc123",
    "hook_event_name": "SubagentStart",
    "agent_name": "code-reviewer",
    "agent_type": "requirements-framework:code-reviewer",
    "cwd": "/path/to/project"
}

Output:
- Structured JSON with hookSpecificOutput.additionalContext
- Empty if agent is not a review agent
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

# Review agent types that benefit from requirement context injection
REVIEW_AGENTS = {
    'requirements-framework:code-reviewer',
    'requirements-framework:silent-failure-hunter',
    'requirements-framework:tool-validator',
    'requirements-framework:test-analyzer',
    'requirements-framework:type-design-analyzer',
    'requirements-framework:comment-analyzer',
    'requirements-framework:code-simplifier',
    'requirements-framework:backward-compatibility-checker',
    'requirements-framework:adr-guardian',
    'requirements-framework:codex-review-agent',
    'requirements-framework:solid-reviewer',
    'requirements-framework:commit-planner',
    'requirements-framework:frontend-reviewer',
    'requirements-framework:refactor-advisor',
}

# Agents that write/edit code and therefore benefit from the lazy-dev ladder
# (injected only when hooks.lazy_dev.enabled).
CODE_TOUCHING_AGENTS = {
    'requirements-framework:refactor-executor',
}


def _ladder_for_subagent(config) -> str:
    """The lazy-dev ladder for a subagent, or '' when disabled/unavailable."""
    try:
        if not config.get_hook_config('lazy_dev', 'enabled'):
            return ""
        from lazy_dev.rules import get_ruleset
        return get_ruleset()
    except Exception:
        return ""


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
    agent_type = input_data.get('agent_type', '')

    # Early hook setup
    project_dir, branch, config, logger = early_hook_setup(
        session_id, "SubagentStart", cwd=input_data.get('cwd')
    )

    try:
        if os.environ.get('CLAUDE_SKIP_REQUIREMENTS'):
            return 0

        if not project_dir or not branch or not config:
            return 0

        if not config.is_enabled():
            return 0

        # Track subagent spawn in session metrics
        try:
            metrics = SessionMetrics(session_id, project_dir, branch)
            metrics.record_tool_use(f'SubagentStart:{agent_type}', blocked=False)
            metrics.save()
        except Exception as e:
            logger.debug("Failed to record subagent metric", error=str(e))

        # Only inject context into review agents OR code-touching agents
        if agent_type not in REVIEW_AGENTS and agent_type not in CODE_TOUCHING_AGENTS:
            return 0

        sections = []

        # Review agents keep their requirement context (guard-aware: a passing
        # guard is not reported as unsatisfied).
        if agent_type in REVIEW_AGENTS:
            reqs = BranchRequirements(branch, session_id, project_dir)
            unsatisfied = collect_unsatisfied(reqs, config, branch, session_id, project_dir)

            lines = [
                "## Requirements Framework Context",
                "",
                f"**Branch**: `{branch}` | **Project**: `{project_dir}`",
            ]

            if unsatisfied:
                lines.append(f"**Unsatisfied requirements**: {', '.join(unsatisfied)}")
                lines.append("")
                lines.append("Focus your review on issues that relate to these requirements.")
            else:
                lines.append("**All requirements satisfied.**")

            sections.append("\n".join(lines))

        # Lazy-dev ladder: appended for review agents AND given to code-touching
        # agents (flag-gated + fail-open in the helper).
        ladder = _ladder_for_subagent(config)
        if ladder:
            sections.append(ladder)

        if not sections:
            # Code-touching agent with lazy_dev disabled → nothing to inject.
            return 0

        emit_hook_context("SubagentStart", "\n\n".join(sections))
        logger.debug("Injected context into subagent", agent_type=agent_type)

        return 0

    except Exception as e:
        logger.error("Unhandled error in SubagentStart hook", error=str(e))
        return 0  # Fail open


if __name__ == '__main__':
    sys.exit(main())
