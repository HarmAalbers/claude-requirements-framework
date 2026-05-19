"""Count unsatisfied (but triggered) requirements for the statusline.

Pure function. A requirement counts as unsatisfied when it has been
*triggered* at the branch or any session level but is not yet satisfied
at either branch or any session level.

CLI usage:
    python3 count_unsatisfied.py <state-file-path>
prints an integer to stdout. Exits 0 even on errors (fail-open).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _is_triggered(req_state: object) -> bool:
    if not isinstance(req_state, dict):
        return False
    if req_state.get("triggered"):
        return True
    sessions = req_state.get("sessions")
    if not isinstance(sessions, dict):
        return False
    return any(
        isinstance(sess, dict) and sess.get("triggered")
        for sess in sessions.values()
    )


def _is_satisfied(req_state: object) -> bool:
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


def count_unsatisfied(state_file: Path) -> int:
    if not state_file.is_file():
        return 0
    try:
        data = json.loads(state_file.read_text())
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return 0
    if not isinstance(data, dict):
        return 0
    reqs = data.get("requirements")
    if not isinstance(reqs, dict):
        return 0
    return sum(
        1
        for req_state in reqs.values()
        if _is_triggered(req_state) and not _is_satisfied(req_state)
    )


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(0)
        return 0
    print(count_unsatisfied(Path(argv[1])))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
