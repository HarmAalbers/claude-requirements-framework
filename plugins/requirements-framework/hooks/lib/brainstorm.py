#!/usr/bin/env python3
"""Shared brainstorm-nudge helpers for the design/brainstorm phase.

The framework nudges Claude to invoke the brainstorming skill before it starts
implementing, so structured design exploration (questions, approaches,
trade-offs) happens first. Two hooks emit this nudge:

* ``handle-plan-enter.py`` — fires on the ``EnterPlanMode`` tool, so it only
  reaches users who actually transition into plan mode mid-session.
* ``handle-prompt-submit.py`` — fires on ``UserPromptSubmit`` every turn in
  every mode, so it ALSO reaches users who live in ``acceptEdits``/auto mode and
  never enter plan mode.

Because both can fire in one session, the nudge is deduplicated once-per-session
via a tiny marker file under the framework state dir. Everything here is
fail-open: a missing/malformed config or an unreadable/unwritable marker must
never break prompt submission or plan-mode entry.
"""
from __future__ import annotations

try:
    from .state_storage import get_state_dir
except ImportError:  # direct import when lib/ is on sys.path
    from state_storage import get_state_dir

# Fail-open defaults: the historical hardcoded gate/skill. Used whenever the
# configured workflow can't be resolved, so a missing/malformed `workflow:`
# section never breaks the nudge.
DEFAULT_BRAINSTORM_GATE = 'design_approved'
DEFAULT_BRAINSTORM_SKILL = 'requirements-framework:brainstorming'


def brainstorm_directive(skill: str) -> str:
    """Render the brainstorm directive for *skill* (a ``plugin:skill`` name).

    The slash form drops the plugin prefix: ``requirements-framework:brainstorming``
    → ``/brainstorming``. Skill-agnostic so a custom brainstorm phase dispatches
    its own configured skill.
    """
    command = '/' + skill.split(':')[-1]
    return f"""\
## Brainstorm Before Planning

Before writing your implementation plan, invoke the brainstorming skill to design the approach first.

**Action**: Invoke `{command}` now.

The brainstorm will help you explore the problem, ask clarifying questions, propose approaches, and validate the design — all inside plan mode.

**Important**: Write the design output directly into the plan file. Do NOT create a separate design document or attempt git commits during brainstorming."""


def resolve_brainstorm_phase(config) -> tuple[str, str]:
    """Return ``(gate, skill)`` for the configured brainstorm-on-enter phase.

    Picks the phase flagged ``brainstorm_on_enter: true`` from the project's
    ``workflow:`` config; if none is flagged, the first phase. Fail-open: returns
    the historical ``design_approved`` / brainstorming pair on any error so a
    missing/malformed workflow never breaks the nudge.
    """
    gate = DEFAULT_BRAINSTORM_GATE
    skill = DEFAULT_BRAINSTORM_SKILL
    try:
        phases = config.get_workflow_phases().get('phases') or []
        chosen = next(
            (p for p in phases
             if isinstance(p, dict) and p.get('brainstorm_on_enter') is True),
            None,
        )
        if chosen is None and phases and isinstance(phases[0], dict):
            chosen = phases[0]
        if isinstance(chosen, dict):
            if isinstance(chosen.get('gate'), str) and chosen['gate']:
                gate = chosen['gate']
            if isinstance(chosen.get('skill'), str) and chosen['skill']:
                skill = chosen['skill']
    except Exception:
        # Fail-open: keep the historical gate/skill on any resolution failure.
        pass
    return gate, skill


def _safe_session_token(session_id: str) -> str:
    """Sanitize a session id into a filename-safe token (no path separators)."""
    return ''.join(c if c.isalnum() or c in '-_' else '_' for c in str(session_id))


def _nudge_marker_path(session_id: str, project_dir: str):
    """Path to the once-per-session brainstorm-nudge marker file."""
    return get_state_dir(project_dir) / f".brainstorm-nudge-{_safe_session_token(session_id)}"


def nudge_already_shown(session_id: str, project_dir: str) -> bool:
    """Return True if the brainstorm nudge already fired this session.

    Fail-open: if the marker can't be resolved/read, treat as "not shown" (so the
    nudge still fires) and never raise.
    """
    try:
        return _nudge_marker_path(session_id, project_dir).exists()
    except Exception:
        return False


def mark_nudge_shown(session_id: str, project_dir: str) -> None:
    """Record that the brainstorm nudge fired this session.

    Fail-open: a marker that can't be written is silently ignored (the only cost
    is a possible duplicate nudge), never raised.
    """
    try:
        path = _nudge_marker_path(session_id, project_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    except Exception:
        pass
