#!/usr/bin/env python3
"""Step 18b smoke spike — multi-worker review fan-out end-to-end.

Runs the real 3-worker fan-out (`fanout_review`) against a real diff resolved
by `prepare-diff-scope` — the same scope resolver `/deep-review` uses — so this
is a dress rehearsal for the eventual command wiring. Validates:

  1. `prepare-diff-scope` resolves a diff to /tmp/review.diff
  2. `fanout_review(diff, scope)` runs 3 workers in parallel + the aggregator
  3. One `session_id` groups the whole run (printed for Langfuse lookup)
  4. The budget recorder (Step 17a) picks up all 4 calls — per-agent cost is
     read back from the ledger delta

Run:  python3 hooks/lib/llm/_spikes/v3_fanout_smoke.py [scope]
      scope is passed verbatim to prepare-diff-scope (empty | branch | a..b | PR#).

Cost: ~$2–$6 in Sonnet usage on a full branch diff. Under Max auth, no API key.

Loud-fail on missing prereqs (per the loud-smoke-spikes rule): a missing
scope script, an empty diff, or an SDK failure aborts with a non-zero exit —
this script does NOT fail open like the library code it exercises.

Not part of the test suite. Re-run when claude-agent-sdk, the ReviewReport
schema, the fan-out coordinator, or any worker prompt changes.
"""

import asyncio
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from hooks.lib.llm import budget
from hooks.lib.llm.workers.fanout import fanout_review

_SCOPE_SCRIPT = (REPO_ROOT / "plugins" / "requirements-framework"
                 / "scripts" / "prepare-diff-scope")
_DIFF_PATH = Path("/tmp/review.diff")


def _die(msg: str) -> None:
    """Hard-fail: print to stderr and exit non-zero. No fail-open."""
    print(f"\n✗ SMOKE ABORTED: {msg}", file=sys.stderr)
    raise SystemExit(1)


def _resolve_diff(scope_arg: str) -> tuple[str, str]:
    """Run prepare-diff-scope; return (diff_text, scope_label). Loud-fail."""
    if not _SCOPE_SCRIPT.exists():
        _die(f"scope resolver not found: {_SCOPE_SCRIPT}")
    proc = subprocess.run(
        ["bash", str(_SCOPE_SCRIPT), scope_arg],
        capture_output=True, text=True, cwd=str(REPO_ROOT),
    )
    if proc.returncode != 0:
        _die(f"prepare-diff-scope exited {proc.returncode}: "
             f"{proc.stderr.strip() or proc.stdout.strip()}")
    scope_label = proc.stdout.strip()
    if not _DIFF_PATH.exists():
        _die(f"{_DIFF_PATH} was not created by prepare-diff-scope")
    diff_text = _DIFF_PATH.read_text()
    if not diff_text.strip():
        _die("resolved diff is empty — nothing to review")
    return diff_text, scope_label


def _ledger_count(now: datetime) -> int:
    return sum(1 for _ in budget.load_month(now.year, now.month))


def _new_run_cost(now: datetime, before_count: int) -> dict:
    records = list(budget.load_month(now.year, now.month))[before_count:]
    return budget.summarize(records)


async def main() -> None:
    scope_arg = sys.argv[1] if len(sys.argv) > 1 else ""

    print("=" * 64)
    print("Step 18b smoke — multi-worker review fan-out")
    print("=" * 64)

    diff_text, scope_label = _resolve_diff(scope_arg)
    print(f"  {scope_label}")
    print(f"  diff bytes: {len(diff_text)}")
    print()

    now = datetime.now(timezone.utc)
    before = _ledger_count(now)

    t0 = time.time()
    result = await fanout_review(diff_text, scope=scope_label or "smoke")
    elapsed = time.time() - t0

    report = result.report
    print("-" * 64)
    print(f"  session_id:     {result.session_id}")
    print(f"  survivors:      {result.survivor_count} worker(s) aggregated")
    print(f"  unified agent:  {report.agent}")
    print(f"  findings:       {len(report.findings)}")
    print(f"  elapsed:        {elapsed:.2f}s")
    print(f"  summary:        {report.summary}")
    print()
    for f in report.findings:
        print(f"  [{f.severity}] {f.file}:{f.line} ({f.category}, "
              f"conf={f.confidence:.2f})")
        print(f"    {f.title}")
    print()

    cost = _new_run_cost(now, before)
    print("=" * 64)
    print("COST (this run, from budget ledger delta)")
    print("=" * 64)
    print(f"  total:  ${cost['mtd_usd']:.4f} over {cost['call_count']} call(s)")
    for agent, usd in cost["top_agents"]:
        print(f"    {agent:20s} ${usd:.4f}")
    print()
    print(f"Langfuse: filter session_id={result.session_id} to see the "
          f"{result.survivor_count} worker(s) + aggregator as one session.")


if __name__ == "__main__":
    asyncio.run(main())
