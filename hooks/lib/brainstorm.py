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

from typing import Any

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
    its own configured skill. Mode-agnostic: artifact rules live in the skill, so
    the directive never mentions plan files, design documents, or git.
    """
    command = '/' + skill.split(':')[-1]
    return f"""\
## Brainstorm Before Planning

Before implementing (or writing an implementation plan), invoke the brainstorming skill to design the approach first.

**Action**: Invoke `{command}` now.

The skill starts with a triage step so the design ceremony matches the task's size, then asks clarifying questions, proposes approaches, and gets the design approved. Follow its artifact rules for what to capture where."""


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


# --- Generalized phase nudge -------------------------------------------------
# The brainstorm nudge above is the design phase's special case. These helpers
# generalize it across the whole workflow: any phase can nudge its configured
# skill, deduplicated per (session, phase) so the nudge re-fires each time the
# chain advances to a new phase (but stays quiet within a phase).


def phase_directive(phase: str, skill: str, phase_cfg: Any = None) -> str:
    """Render a concise 'next step' nudge for an arbitrary workflow *phase*.

    The design/brainstorm phase keeps its richer directive (``brainstorm_directive``);
    every other phase renders this generic form from its configured ``plugin:skill``
    name. The slash form drops the plugin prefix
    (``requirements-framework:writing-plans`` → ``/writing-plans``).

    ``phase_cfg`` (the resolved phase dict, optional) surfaces the typed-node
    metadata of the 7-node backbone: a ``team`` node notes it fans out a review
    team; a ``loop`` (e.g. Build's per-commit pre-commit) is surfaced as a
    recurring step; declared ``conditionals`` are listed as optional side-quests.
    Absent/malformed ``phase_cfg`` degrades to the plain base directive.
    """
    command = '/' + skill.split(':')[-1]
    cfg = phase_cfg if isinstance(phase_cfg, dict) else {}
    extra: list[str] = []
    if cfg.get('type') == 'team':
        extra.append(f"`{command}` runs a review team (agents fan out in parallel).")
    loop = cfg.get('loop')
    if isinstance(loop, dict) and loop.get('skill'):
        loop_cmd = '/' + str(loop['skill']).split(':')[-1]
        trigger = loop.get('on') or 'commit'
        extra.append(f"Loop: run `{loop_cmd}` before each {trigger}.")
    conditionals = cfg.get('conditionals')
    if isinstance(conditionals, (list, tuple)) and conditionals:
        listed = ', '.join(
            '`/' + str(c).split(':')[-1] + '`' for c in conditionals
        )
        extra.append(f"Available here (optional): {listed}.")
    extra_block = ("\n\n" + "\n".join(extra)) if extra else ""
    return f"""\
## Next Step: {phase}

You're in the **{phase}** phase of the workflow. Invoke `{command}` to proceed.{extra_block}

This is a nudge, not a block — you can proceed without it, but the workflow
expects `{command}` at this phase."""


def resolve_current_phase(config, reqs) -> tuple[str, str, Any]:
    """Session-aware current phase + skill + phase config for the proactive nudge.

    Returns ``(phase_name, skill, phase_cfg)`` for the first configured workflow
    phase whose gate requirement is UNSATISFIED *for this session*. ``phase_cfg``
    is the resolved phase dict (carrying ``type``/``loop``/``conditionals``) so
    the directive can surface the typed-node metadata; it is ``None`` for the
    ship/fallback cases. Unlike ``derive_phase`` (state-file based,
    any-session-satisfied — used by the session-less statusline), this honors
    per-session scope via ``reqs.is_satisfied`` so the nudge asks "does THIS
    session still need to do X?". Gateless phases are transparent (skipped).
    Returns ``(ship_phase, '', None)`` when every gate is satisfied. Fail-open:
    any error returns the design defaults so the nudge still fires.
    """
    try:
        workflow = config.get_workflow_phases()
        phases = workflow.get('phases') or []
        ship = workflow.get('ship_phase', 'ship')
    except Exception:
        return 'design', DEFAULT_BRAINSTORM_SKILL, None

    for p in phases:
        if not isinstance(p, dict):
            continue
        gate = p.get('gate')
        if not gate:
            continue  # gateless phase: transparent to derivation
        skill = p.get('skill') or ''
        try:
            req_config = config.get_requirement(gate)
            scope = (req_config or {}).get('scope', 'session')
            satisfied = reqs.is_satisfied(gate, scope)
        except Exception:
            satisfied = False
        if not satisfied:
            return (p.get('name') or 'design'), skill, p
    return ship, '', None


def _phase_marker_path(session_id: str, project_dir: str, phase: str):
    """Path to the once-per-(session, phase) nudge marker file."""
    token = _safe_session_token(session_id)
    ptoken = _safe_session_token(phase)
    return get_state_dir(project_dir) / f".phase-nudge-{token}-{ptoken}"


def phase_nudge_shown(session_id: str, project_dir: str, phase: str) -> bool:
    """Return True if the nudge for this (session, phase) already fired.

    Fail-open: if the marker can't be resolved/read, treat as "not shown" (so the
    nudge still fires) and never raise.
    """
    try:
        return _phase_marker_path(session_id, project_dir, phase).exists()
    except Exception:
        return False


def mark_phase_nudge_shown(session_id: str, project_dir: str, phase: str) -> None:
    """Record that the nudge for this (session, phase) fired.

    Fail-open: a marker that can't be written is silently ignored (the only cost
    is a possible duplicate nudge), never raised.
    """
    try:
        path = _phase_marker_path(session_id, project_dir, phase)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    except Exception:
        pass
