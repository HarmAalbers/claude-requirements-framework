"""Derive the workflow phase from a requirement state file.

Pure function: reads a JSON state file path, returns one of the
phase names defined in the workflow-index skill. Used by the
statusline (which has no session context) and by the /req conductor.

Phase order is top-to-bottom; the first unsatisfied gate wins.
If everything is satisfied, the phase is `ship`.

CLI usage:
    python3 derive_phase.py <state-file-path>
prints the phase name to stdout. Exits 0 even on errors (fail-open).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Order matters: first unsatisfied wins.
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


def derive_phase(state_file: Path) -> str:
    """Return the current phase name for the project at this state file."""
    if not state_file.is_file():
        return DEFAULT_PHASE
    try:
        data = json.loads(state_file.read_text())
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return DEFAULT_PHASE
    if not isinstance(data, dict):
        return DEFAULT_PHASE
    reqs = data.get("requirements")
    if not isinstance(reqs, dict):
        return DEFAULT_PHASE
    for phase_name, req_name in PHASE_GATES:
        if not _is_satisfied(reqs.get(req_name)):
            return phase_name
    return SHIP_PHASE


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(DEFAULT_PHASE)
        return 0
    print(derive_phase(Path(argv[1])))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
