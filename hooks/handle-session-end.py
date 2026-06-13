#!/usr/bin/env python3
"""
SessionEnd Hook for Requirements Framework.

Triggered when a Claude Code session ends.
Responsibilities:
1. Remove session from registry
2. Optionally clear session-scoped requirement state (if configured)
3. Log session end for debugging

Input (stdin JSON):
{
    "session_id": "abc123",
    "hook_event_name": "SessionEnd",
    "reason": "clear|logout|prompt_input_exit|other",
    "cwd": "/path/to/project"
}

Output:
- None (cleanup only, cannot block session end)
"""
import json
import os
import sys
from pathlib import Path

# Add lib to path
lib_path = Path(__file__).parent / 'lib'
sys.path.insert(0, str(lib_path))

from requirements import BranchRequirements
from session import remove_session_from_registry, normalize_session_id, get_registry_path
from logger import get_logger
from hook_utils import early_hook_setup


def main() -> int:
    """Hook entry point."""
    # Parse stdin input
    input_data = {}
    try:
        stdin_content = sys.stdin.read()
        if stdin_content:
            input_data = json.loads(stdin_content)
    except json.JSONDecodeError:
        pass

    # Get session ID from stdin (Claude Code always provides this)
    raw_session = input_data.get('session_id')
    if not raw_session:
        # This should NEVER happen - Claude Code always provides session_id
        # If it does, fail open with a logged warning
        logger = get_logger(base_context={"hook": "SessionEnd"})
        logger.error("No session_id in hook input!", input_keys=list(input_data.keys()))
        return 0  # Fail open

    session_id = normalize_session_id(raw_session)
    reason = input_data.get('reason', 'unknown')

    # Early hook setup: loads config, creates logger with correct level
    project_dir, branch, config, logger = early_hook_setup(
        session_id, "SessionEnd", cwd=input_data.get('cwd')
    )

    try:
        # Skip if requirements explicitly disabled
        if os.environ.get('CLAUDE_SKIP_REQUIREMENTS'):
            return 0

        # Still try to remove from registry even without project context
        if not project_dir:
            remove_session_from_registry(session_id)
            return 0

        logger.info("Session ending", reason=reason)

        # Clear any session pause marker (auto-resume on session end).
        # Fail-open: cleanup must never crash session end.
        try:
            from pause import clear_paused
            clear_paused(session_id, project_dir)
        except Exception:
            pass

        # 0. Read session start time before registry removal (for WIP time tracking)
        session_started_at = None
        try:
            from registry_client import RegistryClient
            reg_client = RegistryClient(get_registry_path())
            reg_data = reg_client.read()
            session_entry = reg_data.get("sessions", {}).get(session_id, {})
            session_started_at = session_entry.get("started_at")
        except Exception:
            pass

        # 1. Remove session from registry
        removed = remove_session_from_registry(session_id)
        if removed:
            logger.debug("Session removed from registry")
        else:
            logger.debug("Session was not in registry")

        # 2. Optionally clear session-scoped state (default: False - preserve state)
        if config and branch and config.get_hook_config('session_end', 'clear_session_state', False):
            reqs = BranchRequirements(branch, session_id, project_dir)

            for req_name in config.get_all_requirements():
                req_config = config.get_requirement(req_name)
                if req_config and req_config.get('scope') == 'session':
                    try:
                        reqs.clear(req_name)
                        logger.debug("Cleared session requirement", requirement=req_name)
                    except Exception as e:
                        logger.error("Failed to clear requirement", requirement=req_name, error=str(e))

        # 3. WIP tracking: accumulate session time
        try:
            wip_enabled = config and config.get_hook_config('wip_tracking', 'enabled', False)
            exclude_branches = (
                config.get_hook_config('wip_tracking', 'exclude_branches',
                                       ['main', 'master', 'develop'])
                if config else ['main', 'master', 'develop']
            )

            if wip_enabled and branch and branch not in exclude_branches:
                import time
                from wip_tracker import WipTracker

                if session_started_at:
                    elapsed = time.time() - session_started_at
                    if elapsed > 0:
                        tracker = WipTracker()
                        tracker.increment_time(project_dir, branch, elapsed)
                        logger.debug("WIP time tracked", elapsed_seconds=int(elapsed))
        except Exception as e:
            logger.debug("WIP time tracking failed (fail-open)", error=str(e))

        # 3.5. Finalize session metrics.
        # finalize_session() sets ended_at + duration_seconds in memory and
        # marks the instance dirty; save() is required to persist to disk.
        # Without BOTH calls, .git/requirements/sessions/<id>.json ends with
        # ended_at=null — the regression this block protects against.
        # Only finalize if a metrics file already exists — don't fabricate
        # synthetic files for sessions that never recorded any metrics
        # (non-framework sessions, disabled session_learning, non-git dirs).
        # Log failures at warning level so the exact class of bug being fixed
        # cannot silently reappear.
        try:
            from session_metrics import SessionMetrics, get_metrics_path
            if get_metrics_path(session_id, project_dir).exists():
                metrics = SessionMetrics(session_id, project_dir, branch)
                metrics.finalize_session()
                metrics.save()
                logger.debug("Session metrics finalized")
        except Exception as e:
            logger.warning("Session metrics finalization failed (fail-open)",
                           error=str(e), session_id=session_id)

        # 4. Obsidian session logging: finalize session note
        try:
            obsidian_enabled = config and config.get_hook_config('obsidian', 'enabled', False)
            if obsidian_enabled:
                from obsidian import ObsidianSessionLogger
                from session_metrics import SessionMetrics

                obs_logger = ObsidianSessionLogger(config)
                metrics = SessionMetrics(session_id, project_dir, branch)
                summary = metrics.get_summary()
                obs_logger.finalize_in_background(session_id, project_dir, summary)
                logger.debug("Obsidian finalization spawned in background")
        except Exception as e:
            logger.debug("Obsidian finalization failed (fail-open)", error=str(e))

        # 5. Qdrant session embedding (Step 13).
        #
        # Fail-open: every nested call already returns "" / False on error,
        # AND the outer try here catches anything they miss (e.g. extras
        # missing → ImportError). The framework rule is that SessionEnd
        # cannot raise; this block honors that at three layers.
        #
        # Why an inner sys.path mutation: this hook is invoked as a fresh
        # subprocess by Claude Code, with no guarantee that `pip install
        # -e '.[llm]'` has been run in the active python. Adding REPO_ROOT
        # here lets the package import resolve when extras ARE installed,
        # and ImportError fail-opens cleanly when they aren't.
        try:
            qdrant_enabled = config and config.get_hook_config('qdrant', 'enabled', False)
            if qdrant_enabled:
                transcript_path = input_data.get('transcript_path')
                if transcript_path and Path(transcript_path).is_file():
                    import asyncio
                    import time as _time
                    repo_root = Path(__file__).resolve().parent.parent
                    if str(repo_root) not in sys.path:
                        sys.path.insert(0, str(repo_root))
                    from hooks.lib.llm.retrieval import upsert_session
                    from hooks.lib.llm.summarizer import summarize_session

                    tail = Path(transcript_path).read_text()[-15000:]
                    session_summary = asyncio.run(summarize_session(tail))
                    if session_summary:
                        ok = upsert_session(
                            session_id=session_id,
                            summary=session_summary,
                            payload={
                                "project": str(project_dir),
                                "branch": branch or "",
                                "ended_at": int(_time.time()),
                                "reason": reason,
                            },
                        )
                        logger.debug("Qdrant session upsert",
                                     ok=ok, summary_chars=len(session_summary))
                    else:
                        logger.debug("Qdrant: empty summary, skipping upsert")
                else:
                    logger.debug("Qdrant: no transcript_path, skipping",
                                 path=transcript_path)
        except Exception as e:
            logger.debug("Qdrant session embedding failed (fail-open)",
                         error=str(e))

        return 0

    except Exception as e:
        # FAIL OPEN - never block on errors
        logger.error("Unhandled error in SessionEnd hook", error=str(e))
        return 0


if __name__ == '__main__':
    sys.exit(main())
