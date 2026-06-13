"""
Session-scoped pause marker for the requirements framework.

A pause marker temporarily suppresses BLOCKING gates (PreToolUse edit/bash gate
and the Stop verification gate) for ONE session, without touching nudges, status
injection, or strict-preflight. The marker is a presence-based file keyed by
session id, stored next to per-session metrics:

    <git-common-dir>/requirements/sessions/<session_id>.paused

DESIGN: fail-open everywhere. Any error reading/writing the marker is treated as
"not paused" and never raised — a pause bug must never block work nor crash a hook.
Auto-cleared by handle-session-end.py; manually cleared by `req resume`.
"""
import json
from pathlib import Path

try:
    from .session_metrics import get_sessions_dir, ensure_sessions_dir
except ImportError:
    from session_metrics import get_sessions_dir, ensure_sessions_dir


def marker_path(session_id: str, project_dir) -> Path:
    """Path to the pause marker for *session_id* (no existence guarantee)."""
    return get_sessions_dir(project_dir) / f"{session_id}.paused"


def is_paused(session_id: str, project_dir) -> bool:
    """True if a pause marker exists for this session. Fail-open -> False."""
    if not project_dir or not session_id:
        return False
    try:
        return marker_path(session_id, project_dir).exists()
    except Exception:
        return False


def set_paused(session_id: str, project_dir, reason: str = "") -> bool:
    """Create the pause marker. Returns True on success, False on failure."""
    if not project_dir or not session_id:
        return False
    try:
        ensure_sessions_dir(project_dir)
        payload = {"paused_at": _now_iso(), "reason": reason or "manual"}
        marker_path(session_id, project_dir).write_text(json.dumps(payload))
        return True
    except Exception:
        return False


def clear_paused(session_id: str, project_dir) -> bool:
    """Remove the pause marker if present. Idempotent. Fail-open -> False."""
    if not project_dir or not session_id:
        return False
    try:
        marker_path(session_id, project_dir).unlink(missing_ok=True)
        return True
    except Exception:
        return False


def paused_banner(session_id: str, project_dir) -> str:
    """A one-line visibility banner when paused, else empty string."""
    if is_paused(session_id, project_dir):
        return ("⏸ Framework paused for this session "
                "— run `/req-resume` to re-enable blocking gates.")
    return ""


def _now_iso() -> str:
    """UTC ISO timestamp. Fail-open -> empty string (marker presence is enough)."""
    try:
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()
    except Exception:
        return ""
