#!/usr/bin/env python3
"""
PreCompact Hook for Requirements Framework.

Triggered before context compaction (auto or manual).
Responsibilities:
1. Save requirement state and session metrics before compaction
2. Track compaction frequency in session metrics

Input (stdin JSON):
{
    "session_id": "abc123",
    "hook_event_name": "PreCompact",
    "source": "manual|auto",
    "cwd": "/path/to/project"
}

Output:
- Empty (metrics recording only)
"""
import json
import os
import sys
from pathlib import Path

# Add lib to path
lib_path = Path(__file__).parent / 'lib'
sys.path.insert(0, str(lib_path))

from session import normalize_session_id
from session_metrics import SessionMetrics
from hook_utils import early_hook_setup


def main() -> int:
    """Hook entry point."""
    input_data = {}
    try:
        stdin_content = sys.stdin.read()
        if stdin_content:
            input_data = json.loads(stdin_content)
    except json.JSONDecodeError:
        return 0  # Fail open

    raw_session = input_data.get('session_id')
    if not raw_session:
        return 0

    session_id = normalize_session_id(raw_session)
    source = input_data.get('source', 'unknown')

    # Early hook setup
    project_dir, branch, config, logger = early_hook_setup(
        session_id, "PreCompact", cwd=input_data.get('cwd')
    )

    try:
        if os.environ.get('CLAUDE_SKIP_REQUIREMENTS'):
            return 0

        if not project_dir or not branch or not config:
            return 0

        if not config.is_enabled():
            return 0

        # Record compaction event in session metrics
        metrics = SessionMetrics(session_id, project_dir, branch)
        metrics.record_tool_use(f'Compact:{source}', blocked=False)

        # Track compaction count
        try:
            compaction_count = metrics.data.get('compaction_count', 0) + 1
            metrics.data['compaction_count'] = compaction_count
            metrics.save()
            logger.info(
                "Pre-compaction state saved",
                source=source,
                compaction_count=compaction_count,
            )
        except Exception as e:
            logger.debug("Failed to save compaction metrics", error=str(e))

        return 0

    except Exception as e:
        logger.error("Unhandled error in PreCompact hook", error=str(e))
        return 0  # Fail open


if __name__ == '__main__':
    sys.exit(main())
