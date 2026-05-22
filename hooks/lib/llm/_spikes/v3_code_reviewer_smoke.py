#!/usr/bin/env python3
"""Step 10 smoke spike — code-reviewer worker + aggregator end-to-end.

Promotes the v3_spike.py pattern into a check against the **package**
(`hooks.lib.llm.workers`) rather than ad-hoc inline functions. Validates:

  1. `review(diff, scope)` returns a typed ReviewReport
  2. `aggregate([report])` accepts a length-1 input (degenerate case)
     and still produces a unified report
  3. The budget recorder (Step 17a) picks up both calls — verify with
     `req budget tail -n 5` after running this script

Run:  python3 hooks/lib/llm/_spikes/v3_code_reviewer_smoke.py

Cost: ~$0.15–$0.30 in Sonnet usage. Under Max auth, no API key required.

Not part of the test suite. Re-run when:
  - claude-agent-sdk version changes
  - ReviewReport schema changes
  - Either worker's prompt body changes
"""
import asyncio
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from hooks.lib.llm.workers import aggregate, review


BUGGY_DIFF = """\
--- a/api/export.py
+++ b/api/export.py
@@ -1,5 +1,15 @@
+import os
 import sqlite3

 def get_user(db_path, username):
-    return db.execute("SELECT * FROM users WHERE name=?", (username,)).fetchone()
+    db = sqlite3.connect(db_path)
+    return db.execute("SELECT * FROM users WHERE name='" + username + "'").fetchone()
+
+
+def export_users(filter_query):
+    # Build a mysqldump command and run it
+    cmd = f"mysqldump --where=\\"{filter_query}\\" users > /tmp/export.csv"
+    os.system(cmd)
+    return "/tmp/export.csv"
"""


async def main():
    print("=" * 64)
    print("Step 10 smoke — code-reviewer worker + aggregator")
    print("=" * 64)
    print()

    # Phase 1 — single worker
    print("PHASE 1: code-reviewer worker")
    print("-" * 64)
    t0 = time.time()
    report = await review(diff=BUGGY_DIFF, scope="HEAD")
    elapsed1 = time.time() - t0
    print(f"  agent:    {report.agent}")
    print(f"  scope:    {report.scope}")
    print(f"  findings: {len(report.findings)}")
    print(f"  elapsed:  {elapsed1:.2f}s")
    print(f"  summary:  {report.summary}")
    print()
    for f in report.findings:
        print(f"  [{f.severity}] {f.file}:{f.line} ({f.category}, "
              f"conf={f.confidence:.2f})")
        print(f"    {f.title}")
    print()

    # Phase 2 — aggregator with length-1 input (degenerate)
    print("PHASE 2: aggregator (length-1 input — degenerate case)")
    print("-" * 64)
    t1 = time.time()
    unified = await aggregate([report])
    elapsed2 = time.time() - t1
    print(f"  agent:    {unified.agent}")
    print(f"  findings: {len(unified.findings)} "
          f"(was {len(report.findings)} pre-aggregation)")
    print(f"  elapsed:  {elapsed2:.2f}s")
    print(f"  summary:  {unified.summary}")
    print()

    total = elapsed1 + elapsed2
    print("=" * 64)
    print("SMOKE SUMMARY")
    print("=" * 64)
    print(f"  Worker:     {elapsed1:6.2f}s   → ReviewReport "
          f"({len(report.findings)} findings)")
    print(f"  Aggregator: {elapsed2:6.2f}s   → ReviewReport "
          f"({len(unified.findings)} findings, with narrative)")
    print(f"  Total:      {total:6.2f}s")
    print()
    print("Next: `req budget tail -n 5` should show two recent entries "
          "labeled code-reviewer / review-aggregator.")


if __name__ == "__main__":
    asyncio.run(main())
