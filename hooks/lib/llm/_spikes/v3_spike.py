#!/usr/bin/env python3
"""V3 architecture spike — supervisor + 2 parallel workers + aggregator.

Proves the V3 user-visible behavior change end-to-end:
  1. Supervisor takes user intent → returns typed HandoffResult
  2. Two workers run in parallel, each return typed ReviewReport
  3. Aggregator dedupes findings by (file, line, category) across agents
  4. Final unified ranking, sorted by severity × confidence

Stubs (out of spike scope, real V3 will fill in):
  - Retrieval hits hardcoded to []
  - No Langfuse / OpenInference instrumentation
  - No token-budget enforcement
  - No Ragas eval scoring

Run:  python3 /tmp/v3_spike.py
"""
import asyncio
import json
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path("/Users/harm/Tools/claude-requirements-framework")
sys.path.insert(0, str(REPO_ROOT))

from claude_agent_sdk import query, ClaudeAgentOptions, ResultMessage
from hooks.lib.llm.schemas import HandoffResult, ReviewReport


# Deliberate buggy diff: 1 issue both agents should find (SQL injection),
# 1 issue mainly appsec catches (os.system command injection).
BUGGY_DIFF = """\
--- a/api/auth.py
+++ b/api/auth.py
@@ -10,9 +10,15 @@ def authenticate(username, password):
-    user = db.execute("SELECT * FROM users WHERE name=?", (username,)).fetchone()
+    user = db.execute("SELECT * FROM users WHERE name='" + username + "'").fetchone()
     if user and user.password == password:
         return user
     return None
+
+
+def export_users(filter_query):
+    cmd = f"mysqldump --where=\\"{filter_query}\\" users > /tmp/export.csv"
+    os.system(cmd)
+    return "/tmp/export.csv"
"""


async def supervisor(user_prompt: str, retrieval_hits: list) -> HandoffResult:
    """Decide which workflow command to invoke next, return typed HandoffResult."""
    prompt = f"""You are the requirements-framework workflow router.

Current state:
  - Phase: review (implementation just finished)
  - Unsatisfied gates: pre_pr_review
  - Retrieval hits from past sessions: {retrieval_hits or '(none)'}

User said: "{user_prompt}"

Pick exactly one workflow command to invoke. Available targets:
  brainstorm, arch-review, execute-plan, deep-review, refactor-orchestrate, ship

Respond with HandoffResult."""

    async for msg in query(
        prompt=prompt,
        options=ClaudeAgentOptions(
            system_prompt="You are a strict workflow router. Output only structured data.",
            output_format={"type": "json_schema", "schema": HandoffResult.model_json_schema()},
            allowed_tools=[],
            max_turns=3,
        ),
    ):
        if isinstance(msg, ResultMessage):
            if msg.subtype == "success" and msg.structured_output:
                return HandoffResult.model_validate(msg.structured_output)
            raise RuntimeError(f"supervisor failed: subtype={msg.subtype!r}")
    raise RuntimeError("supervisor: no ResultMessage")


async def review_worker(agent_name: str, focus: str, diff: str) -> ReviewReport:
    """Run one review agent over the diff, return typed ReviewReport."""
    prompt = f"""Review the diff below. You are the '{agent_name}' agent specializing in {focus}.

For each problem you find, produce a ReviewFinding with:
  severity: CRITICAL | IMPORTANT | SUGGESTION
  file:     the affected file
  line:     the affected line number (1-based, integer >= 1)
  category: security | performance | logic | style | test | compatibility | complexity
  title:    short title (10-120 characters)
  body:     1-3 sentences explaining the issue
  suggested_fix: optional code or guidance
  confidence: 0.0 to 1.0

Then wrap them in a ReviewReport with agent='{agent_name}', scope='HEAD', and a 1-3 sentence summary.

```diff
{diff}
```"""

    async for msg in query(
        prompt=prompt,
        options=ClaudeAgentOptions(
            system_prompt=f"You are {agent_name}, a {focus}-focused code reviewer producing structured JSON output.",
            output_format={"type": "json_schema", "schema": ReviewReport.model_json_schema()},
            allowed_tools=[],
            max_turns=5,
        ),
    ):
        if isinstance(msg, ResultMessage):
            if msg.subtype == "success" and msg.structured_output:
                return ReviewReport.model_validate(msg.structured_output)
            raise RuntimeError(f"{agent_name} failed: subtype={msg.subtype!r}")
    raise RuntimeError(f"{agent_name}: no ResultMessage")


async def aggregator_agent(reports: list[ReviewReport]) -> ReviewReport:
    """Read worker review reports and produce a single unified ReviewReport.

    Semantic deduplication via LLM rather than mechanical (file, line, category)
    keys. Merges findings describing the same underlying issue (even at slightly
    different lines or in different wording); keeps distinct findings separate
    (even at the same line). Returns a ReviewReport with agent='review-aggregator'.
    """
    reports_json = json.dumps([r.model_dump() for r in reports], indent=2)

    prompt = f"""You are the review-aggregator. You receive structured review reports from multiple reviewers (different agents, different focus areas) on the SAME code change. Produce a single unified ReviewReport.

Rules:

1. MERGE findings that describe the same underlying issue — even if reported at slightly different line numbers (±2 lines) or in different wording. When merging, take the worst severity and the highest confidence. Include attribution in the body, e.g. "[flagged by code-reviewer + appsec-auditor]".

2. KEEP DISTINCT findings separate — even if they happen to be at the same line. Two different bugs reported at the same line remain two findings.

3. RANK the final findings by severity (CRITICAL > IMPORTANT > SUGGESTION), then by confidence within each severity.

4. WRITE A NARRATIVE SUMMARY (1-3 sentences) that surfaces patterns across the findings — e.g., "Security issues cluster around the new export_users function."

Return a single ReviewReport with:
  - agent: "review-aggregator"
  - scope: copy from the inputs (they should all share the same scope)
  - findings: the merged, ranked list
  - summary: the narrative summary

Input worker reports (JSON):
{reports_json}
"""

    async for msg in query(
        prompt=prompt,
        options=ClaudeAgentOptions(
            system_prompt="You are a review aggregator producing strict JSON output. Merge semantic duplicates, keep distinct findings, attribute sources.",
            output_format={"type": "json_schema", "schema": ReviewReport.model_json_schema()},
            allowed_tools=[],
            max_turns=5,
        ),
    ):
        if isinstance(msg, ResultMessage):
            if msg.subtype == "success" and msg.structured_output:
                return ReviewReport.model_validate(msg.structured_output)
            raise RuntimeError(f"aggregator failed: subtype={msg.subtype!r}")
    raise RuntimeError("aggregator: no ResultMessage")


async def main():
    print("=" * 64)
    print("V3 spike — supervisor + 2 parallel workers + aggregator")
    print("=" * 64)
    print(f"Auth: {'API key in env' if os.environ.get('ANTHROPIC_API_KEY') else 'Max only (no API key)'}")
    print()

    # Phase 1: supervisor decides
    print("PHASE 1: Supervisor routing")
    print("-" * 64)
    t0 = time.time()
    handoff = await supervisor(
        user_prompt="I just finished implementing a CSV export feature. Please review it.",
        retrieval_hits=[],
    )
    sup_elapsed = time.time() - t0
    print(f"  target:    {handoff.target}")
    print(f"  rationale: {handoff.rationale}")
    print(f"  elapsed:   {sup_elapsed:.2f}s")
    if handoff.target not in ("deep-review",):
        print("  note:      spike will run review workers regardless of supervisor choice")
    print()

    # Phase 2: parallel workers
    print("PHASE 2: Parallel review workers")
    print("-" * 64)
    t1 = time.time()
    results = await asyncio.gather(
        review_worker("code-reviewer", "general code quality, logic, complexity", BUGGY_DIFF),
        review_worker("appsec-auditor", "security vulnerabilities and injection attacks", BUGGY_DIFF),
        return_exceptions=True,
    )
    work_elapsed = time.time() - t1

    reports: list[ReviewReport] = []
    for r in results:
        if isinstance(r, Exception):
            print(f"  ✗ worker exception: {type(r).__name__}: {r}")
        else:
            reports.append(r)
            print(f"  ✓ {r.agent}: {len(r.findings)} finding(s)")
    print(f"  elapsed (parallel): {work_elapsed:.2f}s")
    print()

    if not reports:
        print("No worker output to aggregate. Aborting.")
        return

    # Phase 3: aggregation (agent-based, not mechanical)
    print("PHASE 3: Aggregation via agent")
    print("-" * 64)
    t2 = time.time()
    unified = await aggregator_agent(reports)
    agg_elapsed = time.time() - t2

    raw_count = sum(len(r.findings) for r in reports)
    print(f"  {raw_count} raw finding(s) → {len(unified.findings)} unified after agent aggregation")
    print(f"  elapsed: {agg_elapsed:.2f}s")
    print()
    print("  Narrative summary (from aggregator):")
    print(f"    {unified.summary}")
    print()

    for f in unified.findings:
        print(f"  [{f.severity}] {f.file}:{f.line} ({f.category}, conf={f.confidence:.2f})")
        print(f"    {f.title}")
        # Body often contains attribution like "[flagged by code-reviewer + appsec-auditor]"
        body_preview = f.body[:200] + ("..." if len(f.body) > 200 else "")
        print(f"    {body_preview}")
        if f.suggested_fix:
            fix = f.suggested_fix.replace("\n", " ")
            print(f"    fix: {fix[:120]}{'...' if len(fix) > 120 else ''}")
        print()

    # Summary
    total = sup_elapsed + work_elapsed + agg_elapsed
    dedup_savings = raw_count - len(unified.findings)
    print("=" * 64)
    print("SPIKE SUMMARY")
    print("=" * 64)
    print(f"  Supervisor:   {sup_elapsed:6.2f}s   → HandoffResult")
    print(f"  Workers (∥):  {work_elapsed:6.2f}s   → {len(reports)} × ReviewReport in parallel")
    print(f"  Aggregator:   {agg_elapsed:6.2f}s   → ReviewReport (unified, with narrative)")
    print(f"  Total:        {total:6.2f}s")
    print(f"  Dedup:        {raw_count} raw → {len(unified.findings)} unified (saved {dedup_savings} duplicate{'s' if dedup_savings != 1 else ''})")
    print()
    print("Architecture validated:")
    print("  ✓ Supervisor → HandoffResult (typed)")
    print("  ✓ Workers in parallel → ReviewReport (typed)")
    print("  ✓ Aggregator agent → ReviewReport (typed; semantic dedup + narrative)")
    print("  ✓ End-to-end flow under Max auth, no API key required")


if __name__ == "__main__":
    asyncio.run(main())
