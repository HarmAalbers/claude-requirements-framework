#!/usr/bin/env python3
"""Once-per-session dedup marker for the lazy-dev compact reminder.

The compact lazy-dev reminder is injected at most once per session from
``handle-prompt-submit.py``. A tiny marker file under the framework state dir
records that it has fired, modeled on ``brainstorm.py``'s nudge marker.

Everything here is fail-open: an unresolvable/unreadable/unwritable marker must
never break prompt submission. ``shown`` then degrades to "not shown" (so the
reminder may fire again) and ``mark_shown`` silently no-ops.
"""

import re
from pathlib import Path

from state_storage import get_state_dir


def _safe_token(session_id: str) -> str:
    return re.sub(r'[^A-Za-z0-9_-]', '_', str(session_id))[:64]


def _marker_path(session_id, project_dir) -> Path:
    return get_state_dir(project_dir) / f".lazy-ladder-{_safe_token(session_id)}"


def shown(session_id, project_dir) -> bool:
    try:
        return _marker_path(session_id, project_dir).exists()
    except Exception:
        return False


def mark_shown(session_id, project_dir) -> None:
    try:
        p = _marker_path(session_id, project_dir)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.touch()
    except Exception:
        pass
