"""SessionStart retrieval pipeline over the Step 13 sessions collection.

Public surface:
    write_retrieval_json(branch, query, top_k=3, timeout_s=1.5, out_dir=None)
        -> dict
        Embed `query`, fetch top-K hits via retrieval.query_sessions, write
        `.git/requirements/retrieval-<sanitized-branch>.json`, return the
        dict that was written. Fail-open: returns {"hits": []} (plus an
        "error" key) on any failure (Qdrant down, model missing, timeout).
    render_retrieval(hits, max_hits=3, min_score=0.5) -> str
        Format hits as a compact markdown block suitable for prepending to
        the SessionStart briefing. Returns "" when no hits pass min_score —
        callers can safely prepend without checking emptiness.

Design notes:

1. **Pure helpers stay infra-free.** `_branch_to_filename` and
   `render_retrieval` have no dependencies; importing this module costs
   nothing. The retrieval import is deferred inside `write_retrieval_json`
   so qdrant-client isn't required to use the renderer.

2. **Hard timeout via SIGALRM.** SessionStart fires on every CLI launch;
   a hung Qdrant cannot block the user. SIGALRM is POSIX-only (darwin/linux,
   which is where Claude Code runs). Windows would need a thread-based
   timer — out of scope today.

3. **Fail-open mirrors Step 13.** Every failure path writes a JSON file with
   empty hits and the error message. Consumers (SessionStart hook) can
   distinguish "no similar sessions" from "retrieval broken" by checking
   the "error" key, but the absence of hits alone never blocks anything.

4. **Filename sanitization.** Branch names commonly contain '/' (illegal in
   filenames on most systems). `_branch_to_filename` collapses any run of
   non-`[A-Za-z0-9._-]` chars to a single '-' and falls back to 'unknown'
   if the branch sanitizes to empty.
"""

from __future__ import annotations

import json
import re
import signal
import subprocess
from contextlib import contextmanager
from pathlib import Path
from typing import Any

_BRANCH_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _branch_to_filename(branch: str) -> str:
    """Sanitize a git branch name for safe filesystem use.

    Collapses any run of non-`[A-Za-z0-9._-]` chars to a single '-' and
    strips leading/trailing dashes. Falls back to 'unknown' if the result
    is empty (e.g. branch = "" or "///").
    """
    return _BRANCH_FILENAME_RE.sub("-", branch).strip("-") or "unknown"


def _recent_commit_subjects(limit: int = 3) -> str:
    """Space-joined recent commit subjects. Returns "" on any failure.

    Used at SessionStart to build a semantic query: branch names alone are
    often non-semantic ("refactor/step-14-foo") while commit subjects on
    this project are descriptive.
    """
    try:
        out = subprocess.check_output(
            ["git", "log", f"-{limit}", "--format=%s"],
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=2,
        )
        return " ".join(out.strip().splitlines())
    except Exception:
        return ""


@contextmanager
def _hard_timeout(seconds: float):
    """SIGALRM-based hard timeout. Main-thread, POSIX-only.

    Resets the previous handler + itimer on exit so nested or sequential
    calls don't leak state. If `seconds <= 0`, the context is a no-op
    (signal.setitimer rejects non-positive intervals).
    """
    if seconds <= 0:
        yield
        return

    def _raise(signum, frame):  # noqa: ARG001 (signal handler signature)
        raise TimeoutError(f"retrieval exceeded {seconds}s")

    old = signal.signal(signal.SIGALRM, _raise)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old)


def write_retrieval_json(
    branch: str,
    query: str,
    top_k: int = 3,
    timeout_s: float = 1.5,
    out_dir: Path | None = None,
) -> dict[str, Any]:
    """Run a retrieval query and persist results next to other branch state.

    Args:
        branch: Current git branch (used to derive the filename).
        query: Semantic query to embed (typically branch + recent commits).
        top_k: Max number of hits to request from Qdrant.
        timeout_s: Hard timeout; on expiry, hits=[] and error is recorded.
        out_dir: Output directory. Defaults to `.git/requirements/`.

    Returns:
        The dict that was written: always contains `query` and `hits`
        keys; contains `error` if anything went wrong.
    """
    out_dir = out_dir or Path(".git/requirements")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"retrieval-{_branch_to_filename(branch)}.json"

    payload: dict[str, Any] = {"query": query, "hits": []}
    try:
        with _hard_timeout(timeout_s):
            # Imported inside the function: query_sessions can be monkey-patched
            # via `retrieval.query_sessions = ...` in tests, and a top-of-file
            # `from ... import query_sessions` would snapshot the original.
            from hooks.lib.llm import retrieval

            payload["hits"] = retrieval.query_sessions(query, top_k=top_k)
    except Exception as exc:
        payload["error"] = f"{type(exc).__name__}: {exc}"

    out_path.write_text(json.dumps(payload, indent=2))
    return payload


def render_retrieval(
    hits: list[dict[str, Any]],
    max_hits: int = 3,
    min_score: float = 0.5,
) -> str:
    """Format retrieval hits as a compact markdown block.

    Returns "" when no hits pass `min_score` so SessionStart can prepend
    unconditionally (`block + briefing` is safe when block is empty).

    Per hit: short session_id (8 chars), score (2 decimals), branch, and
    the first line of the summary truncated to 160 chars.
    """
    kept = [h for h in hits if h.get("score", 0.0) >= min_score][:max_hits]
    if not kept:
        return ""

    lines = ["### Similar prior sessions"]
    for h in kept:
        sid = str(h.get("session_id", "?"))[:8]
        score = float(h.get("score", 0.0))
        branch = h.get("branch", "?")
        summary = (h.get("summary") or "").strip().split("\n")[0][:160]
        lines.append(f"- `{sid}` ({score:.2f}) on `{branch}` — {summary}")
    return "\n".join(lines) + "\n"
