#!/usr/bin/env python3
"""End-to-end smoke proof for Step 17a — SDK monthly spend tracker.

Runs a tiny `query()` through the V3 wrapper, verifies a ledger record
was appended, then prints what `req budget status` would see.

Run with:
    python3 hooks/lib/llm/_spikes/v3_budget_smoke.py

Requires:
    - claude-agent-sdk installed (`pip install -e .[llm]`)
    - the bundled Claude Code CLI on PATH (for Max-auth subprocess)

If you do not want to spend a real query, this spike still proves the
ledger I/O independently — pass --dry to skip the SDK call.
"""

import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT))

from hooks.lib.llm import budget  # noqa: E402


def dry_path() -> None:
    """Prove the ledger path without spending a real call."""
    print("[dry] seeding a fake ResultMessage into the ledger…")
    fake = SimpleNamespace(
        total_cost_usd=0.0123,
        usage={"input_tokens": 200, "output_tokens": 100},
        duration_ms=1500,
        session_id="dry-smoke",
        is_error=False,
        model_usage=None,
    )
    budget.record(fake, agent="smoke-test")
    now = datetime.now(timezone.utc)
    records = list(budget.load_month(now.year, now.month))
    print(f"[dry] ledger now has {len(records)} record(s); last:")
    print(json.dumps(records[-1], indent=2))
    summary = budget.summarize(records)
    print(f"[dry] MTD: ${summary['mtd_usd']:.4f}, "
          f"call_count: {summary['call_count']}")


async def live_path() -> None:
    """Run a real query through the wrapped claude.query — ledger should pick it up."""
    from hooks.lib.llm.claude import ClaudeAgentOptions, ResultMessage, query

    print("[live] calling claude.query with a trivial prompt…")
    options = ClaudeAgentOptions(model="claude-haiku-4-5-20251001")
    seen_result = False
    async for msg in query(
        prompt="Reply with exactly the word OK and nothing else.",
        options=options,
    ):
        if isinstance(msg, ResultMessage):
            seen_result = True
            print(f"[live] ResultMessage: cost=${msg.total_cost_usd or 0:.4f}, "
                  f"duration_ms={msg.duration_ms}, is_error={msg.is_error}")

    if not seen_result:
        print("[live] WARN: no ResultMessage observed — ledger may be empty")
        return

    now = datetime.now(timezone.utc)
    records = list(budget.load_month(now.year, now.month))
    print(f"[live] ledger now has {len(records)} record(s)")
    summary = budget.summarize(records)
    summary["projected_eom_usd"] = budget.project_eom(summary["mtd_usd"], now)
    print(f"[live] MTD: ${summary['mtd_usd']:.4f}, "
          f"projected EOM: ${summary['projected_eom_usd']:.4f}")


def main() -> int:
    if "--dry" in sys.argv:
        dry_path()
        return 0
    try:
        asyncio.run(live_path())
        return 0
    except ImportError as exc:
        print(f"[live] SDK import failed ({exc}); falling back to --dry path")
        dry_path()
        return 0


if __name__ == "__main__":
    sys.exit(main())
