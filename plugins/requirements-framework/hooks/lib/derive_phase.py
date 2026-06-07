"""Derive the workflow phase from a requirement state file.

Reads a JSON state file path, returns one of the phase names in the configured
workflow order. Used by the statusline (which has no session context) and by
the /req conductor.

Phase order is top-to-bottom; the first phase whose gate requirement is
unsatisfied wins. If every gate is satisfied (or no phase has a gate), the
phase is `ship`.

The phase order comes from the per-project `workflow:` config section (via
`RequirementsConfig.get_workflow_phases`) when callable; otherwise it falls back
to the module-level constants below, which reproduce the zero-config order
exactly. The config lookup is lazy and fully fail-open: the statusline must
never refuse to run.

CLI usage:
    python3 derive_phase.py <state-file-path>
        prints the phase name to stdout.
    python3 derive_phase.py <state-file-path> --with-skill
        prints "<phase>\t<resolver_skill>" (tab-separated); the skill is the
        configured ``skill`` for that phase (empty when the phase has none,
        e.g. ship).
    python3 derive_phase.py <state-file-path> --with-skill --phase <name>
        resolves the resolver skill for an explicitly named phase instead of
        deriving — used by ``/req <phase>`` to dispatch a gateless phase.
Exits 0 even on errors (fail-open).
"""

import json
import sys
from pathlib import Path
from typing import Any, Optional

# Order matters: first unsatisfied wins. These constants are the fail-open
# fallback used when config cannot be resolved; they are kept byte-for-byte in
# sync with config.RequirementsConfig.WORKFLOW_DEFAULTS.
# plan-write satisfies plan_written; plan-validate is gated on solid_reviewed
# (which arch-review flips alongside commit_plan, adr_reviewed, tdd_planned).
PHASE_GATES: list[tuple[str, str]] = [
    ("design", "design_approved"),
    ("plan-write", "plan_written"),
    ("plan-validate", "solid_reviewed"),
    ("implement", "verification_evidence"),
    ("review", "pre_pr_review"),
]
SHIP_PHASE = "ship"
DEFAULT_PHASE = "design"


def _is_satisfied(req_state: object) -> bool:
    """True if the requirement is satisfied at branch or any session level.

    Treats ANY session-level satisfaction as "this phase has been completed,"
    because the caller has no session context. Defensive against schema drift —
    any non-dict input returns False rather than raising.
    """
    if not isinstance(req_state, dict):
        return False
    if req_state.get("satisfied") is True:
        return True
    sessions = req_state.get("sessions")
    if not isinstance(sessions, dict):
        return False
    return any(
        isinstance(sess, dict) and sess.get("satisfied")
        for sess in sessions.values()
    )


def _phase_name_and_gate(entry: object) -> tuple[Optional[str], Optional[str]]:
    """Extract ``(name, gate)`` from a phase descriptor.

    Accepts both shapes used in this codebase: a ``(name, gate)`` tuple/list
    (the PHASE_GATES fallback) and a ``{name, gate, ...}`` mapping (what
    ``get_workflow_phases`` returns). ``gate`` is normalized to ``None`` when
    absent/empty so a gateless phase is transparent to derivation. Defensive
    against schema drift — never raises.
    """
    if isinstance(entry, dict):
        name = entry.get("name")
        gate = entry.get("gate")
    elif isinstance(entry, (tuple, list)) and len(entry) >= 2:
        name, gate = entry[0], entry[1]
    else:
        return None, None
    name = name if isinstance(name, str) and name else None
    gate = gate if isinstance(gate, str) and gate else None
    return name, gate


def _resolve_workflow(
    state_file: Path,
) -> Optional[tuple[list[Any], str, str]]:
    """Best-effort config-driven phase order for the project at *state_file*.

    Returns ``(phases, default_phase, ship_phase)`` from the project's
    ``workflow:`` config, or ``None`` on ANY failure so the caller falls back to
    the module constants. Lazily imports RequirementsConfig (kept off the import
    hot path) and swallows every exception — the statusline depends on this
    never raising.
    """
    try:
        # state_file is <repo>/.git/requirements/<branch>.json, so parents[2]
        # is the repository root that RequirementsConfig expects.
        project_dir = state_file.parents[2]
    except IndexError:
        return None
    try:
        lib_dir = str(Path(__file__).resolve().parent)
        if lib_dir not in sys.path:
            sys.path.insert(0, lib_dir)
        from config import RequirementsConfig

        workflow = RequirementsConfig(str(project_dir)).get_workflow_phases()
        phases = workflow["phases"]
        if not isinstance(phases, list) or not phases:
            return None
        return phases, workflow["default_phase"], workflow["ship_phase"]
    except Exception:
        # Fail-open: import error, missing/malformed config, anything — the
        # caller falls back to the module constants.
        return None


def derive_phase(
    state_file: Path,
    phases: Optional[list[Any]] = None,
    default_phase: Optional[str] = None,
    ship_phase: Optional[str] = None,
) -> str:
    """Return the current phase name for the project at this state file.

    With ``phases is None`` (the default), the phase order is resolved from the
    project's ``workflow:`` config; on any failure it falls back to the module
    constants PHASE_GATES / DEFAULT_PHASE / SHIP_PHASE. Callers (e.g. build-2
    dispatch wiring) may pass an explicit ``phases`` list plus
    ``default_phase``/``ship_phase`` to skip the config lookup entirely.

    Never raises — the statusline depends on this being fail-open.
    """
    if phases is None:
        resolved = _resolve_workflow(state_file)
        if resolved is not None:
            r_phases, r_default, r_ship = resolved
            phases = r_phases
            if default_phase is None:
                default_phase = r_default
            if ship_phase is None:
                ship_phase = r_ship

    if phases is None:
        phases = PHASE_GATES
    if default_phase is None:
        default_phase = DEFAULT_PHASE
    if ship_phase is None:
        ship_phase = SHIP_PHASE

    if not state_file.is_file():
        return default_phase
    try:
        data = json.loads(state_file.read_text())
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return default_phase
    if not isinstance(data, dict):
        return default_phase
    reqs = data.get("requirements")
    if not isinstance(reqs, dict):
        return default_phase
    for entry in phases:
        phase_name, gate = _phase_name_and_gate(entry)
        if phase_name is None or gate is None:
            # Unusable entry or gateless phase: transparent to derivation.
            continue
        if not _is_satisfied(reqs.get(gate)):
            return phase_name
    return ship_phase


def _phase_skill(entry: object) -> str:
    """Resolver skill for a phase descriptor; empty string when none/unusable.

    Accepts a ``{name, gate, skill, ...}`` mapping (what ``get_workflow_phases``
    returns). The ``(name, gate)`` tuple fallback (PHASE_GATES) carries no skill,
    so it transparently yields the empty string. Never raises.
    """
    if isinstance(entry, dict):
        skill = entry.get("skill")
        if isinstance(skill, str) and skill:
            return skill
    return ""


def _workflow_for(state_file: Path) -> tuple[list[Any], str, str]:
    """Resolve ``(phases, default_phase, ship_phase)`` for *state_file*.

    Fail-open: returns the module constants (PHASE_GATES / DEFAULT_PHASE /
    SHIP_PHASE) on any failure. The constant fallback list carries no skills,
    so ``--with-skill`` degrades to an empty skill rather than crashing.
    """
    try:
        resolved = _resolve_workflow(state_file)
    except Exception:
        resolved = None
    if resolved is not None:
        return resolved
    return PHASE_GATES, DEFAULT_PHASE, SHIP_PHASE


def _skill_for_phase(phases: list[Any], phase_name: str) -> str:
    """Configured resolver skill for *phase_name* within *phases* (empty if none)."""
    for entry in phases:
        name, _ = _phase_name_and_gate(entry)
        if name == phase_name:
            return _phase_skill(entry)
    return ""


def derive_phase_and_skill(state_file: Path) -> tuple[str, str]:
    """Return ``(derived_phase, resolver_skill)`` for the project at *state_file*.

    The skill is the configured ``skill`` for the derived phase — empty when the
    phase has no skill (e.g. ship) or when config can't be resolved (the constant
    fallback list carries no skills). Phase and skill are read from the SAME
    resolved phase list, so they never disagree. Never raises.
    """
    phases, default_phase, ship_phase = _workflow_for(state_file)
    phase = derive_phase(state_file, phases, default_phase, ship_phase)
    return phase, _skill_for_phase(phases, phase)


def resolve_named_phase_skill(state_file: Path, phase_name: str) -> str:
    """Configured resolver skill for an explicitly named phase (empty if none).

    Used by ``/req <phase>`` to dispatch a gateless DISPATCH-ONLY phase (a phase
    with a skill but no gate) that derivation never surfaces. Fail-open: returns
    the empty string on any failure.
    """
    try:
        phases, _, _ = _workflow_for(state_file)
        return _skill_for_phase(phases, phase_name)
    except Exception:
        return ""


def main(argv: list[str]) -> int:
    args = argv[1:]
    with_skill = "--with-skill" in args
    phase_override: Optional[str] = None
    positional: list[str] = []
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--with-skill":
            pass
        elif arg == "--phase":
            i += 1
            if i < len(args):
                phase_override = args[i]
        elif arg.startswith("--phase="):
            phase_override = arg.split("=", 1)[1]
        else:
            positional.append(arg)
        i += 1

    if not positional:
        # No state-file path: fail-open to the default phase.
        print(f"{DEFAULT_PHASE}\t" if with_skill else DEFAULT_PHASE)
        return 0

    state_file = Path(positional[0])

    if not with_skill:
        # Unchanged legacy behaviour — phase name only.
        print(derive_phase(state_file))
        return 0

    try:
        if phase_override:
            phase = phase_override
            skill = resolve_named_phase_skill(state_file, phase_override)
        else:
            phase, skill = derive_phase_and_skill(state_file)
    except Exception:
        # Last-resort fail-open: emit the phase with an empty skill rather than
        # crash — the conductor must always get a parseable tab-separated line.
        phase = phase_override or DEFAULT_PHASE
        skill = ""
    print(f"{phase}\t{skill}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
