#!/usr/bin/env python3
"""Step 18 smoke — verifies the supervisor routes each of the 7 phases.

Runs `supervisor.route(phase, unsatisfied)` for each workflow phase and
prints the (target, rationale) pair. The point is NOT to assert specific
targets — small models may diverge from the expected mapping — but to
prove the round-trip works end-to-end on real SDK + Max auth + budget
ledger + Langfuse instrumentation, and that the LLM produces valid
HandoffResult JSON within the SDK's internal retry cap.

Prereqs:
    pip install -e '.[llm]'
    # Optional (for tracing):
    export LANGFUSE_PUBLIC_KEY=pk-...
    export LANGFUSE_SECRET_KEY=sk-...
    export LANGFUSE_HOST=http://localhost:3000

Run:
    python3 hooks/lib/llm/_spikes/v3_supervisor_smoke.py

Then verify cost telemetry:
    req budget tail -n 7      # 7 ledger entries labeled 'req-supervisor'

Open http://localhost:3000 -> Traces tab -> see 7 supervisor spans.
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT))

from hooks.lib.llm.supervisor import route


SCENARIOS = [
    ("design",          []),
    ("plan-write",      ["plan_written"]),
    ("plan-validate",   ["adr_reviewed", "tdd_planned"]),
    ("implement",       ["plan_written"]),
    ("review",          ["pre_pr_review", "codex_reviewer"]),
    ("refactor",        []),
    ("ship",            []),
]


async def main() -> int:
    print("Phase".ljust(16), "Target".ljust(22), "Rationale")
    print("-" * 80)
    start = time.monotonic()
    for phase, unsatisfied in SCENARIOS:
        try:
            result = await route(phase=phase, unsatisfied=unsatisfied)
            print(phase.ljust(16), result.target.ljust(22), result.rationale)
        except Exception as exc:  # noqa: BLE001 — spike is informational
            print(phase.ljust(16), "FAILED".ljust(22), repr(exc))
    elapsed = time.monotonic() - start
    print("-" * 80)
    print(f"Total elapsed: {elapsed:.1f}s for {len(SCENARIOS)} routes")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
