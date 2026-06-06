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
prints the phase name to stdout. Exits 0 even on errors (fail-open).
"""

from __future__ import annotations

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


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(DEFAULT_PHASE)
        return 0
    print(derive_phase(Path(argv[1])))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
