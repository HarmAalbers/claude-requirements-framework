#!/usr/bin/env python3
"""V3 dogfood spike — shadow run against the current branch.

Reads `git diff <base>..<head>` (default: 7c090b4..HEAD), runs the real
V3 chain (Step 18 supervisor → Step 10 code-reviewer worker), captures
structured JSON output, ensures Langfuse spans flow.

Why this exists:
    Steps 08-18 built the V3 substrate (workers, schemas, observability,
    prompts, retrieval, memory, eval, budget, supervisor) but never
    exercised it end-to-end against a real branch diff under real
    interactive conditions. This spike closes the Layer-4 gap minimally:
    one V3 chain run on this branch, side-by-side with today's
    `/deep-review` baseline.

REQUIRED env (loud-fail per `feedback-loud-smoke-spikes` memory):
    LANGFUSE_PUBLIC_KEY      Local Langfuse public key (see UI → Settings)
    LANGFUSE_SECRET_KEY      Local Langfuse secret key
    LANGFUSE_HOST            http://localhost:3000 (or remote)

REQUIRED service:
    Langfuse must be running and healthy at LANGFUSE_HOST. Start locally:
        cd infra && docker compose up -d

Usage:
    # One-time per shell:
    export LANGFUSE_PUBLIC_KEY=pk-...
    export LANGFUSE_SECRET_KEY=sk-...
    export LANGFUSE_HOST=http://localhost:3000

    # Run the dogfood:
    python3 hooks/lib/llm/_spikes/v3_dogfood_spike.py

    # Test env + health only (skip SDK calls, $0 cost):
    python3 hooks/lib/llm/_spikes/v3_dogfood_spike.py --dry-run

    # Custom diff range:
    python3 hooks/lib/llm/_spikes/v3_dogfood_spike.py --base <sha> --head HEAD

Output:
    docs/v3-dogfood/2026-05-24-step-16c-v3-output.json — structured run
    artifact with supervisor HandoffResult, worker ReviewReport, timing,
    and Langfuse session identifiers. Open Langfuse UI to see auto-
    instrumented spans (supervisor + worker, each a top-level trace).

See: .claude/plans/variant3/V3-dogfood-step-16c-shadow.md
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT))


REQUIRED_ENV = ["LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_HOST"]


def validate_env() -> None:
    """Hard-fail if any LANGFUSE_* env var is missing."""
    missing = [v for v in REQUIRED_ENV if not os.environ.get(v)]
    if missing:
        print(f"✗ Missing required env vars: {', '.join(missing)}", file=sys.stderr)
        print("", file=sys.stderr)
        print("Set them before running:", file=sys.stderr)
        for v in missing:
            print(f"  export {v}=...", file=sys.stderr)
        print("", file=sys.stderr)
        print("Find local Langfuse keys at http://localhost:3000 → Settings", file=sys.stderr)
        sys.exit(1)


def probe_langfuse_health() -> None:
    """Hard-fail if Langfuse health endpoint is unreachable or unhealthy."""
    host = os.environ["LANGFUSE_HOST"].rstrip("/")
    url = f"{host}/api/public/health"
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            body = resp.read().decode()
            if resp.status != 200 or '"OK"' not in body:
                raise RuntimeError(f"status={resp.status} body={body!r}")
    except (urllib.error.URLError, RuntimeError) as e:
        print(f"✗ Langfuse health probe failed at {url}: {e}", file=sys.stderr)
        print("", file=sys.stderr)
        print("Start Langfuse locally:", file=sys.stderr)
        print("  cd infra && docker compose up -d", file=sys.stderr)
        sys.exit(1)


def read_diff(base: str, head: str) -> str:
    """Capture `git diff base..head` from the repo."""
    result = subprocess.run(
        ["git", "diff", f"{base}..{head}"],
        capture_output=True, text=True, cwd=str(REPO_ROOT), check=True,
    )
    return result.stdout


async def run_v3_chain(diff: str, scope: str, dry_run: bool):
    """Run supervisor → code-reviewer worker. Aggregator skipped (single worker).

    Returns (handoff, report, sup_elapsed, work_elapsed, sup_error, work_error)
    so the caller can write a partial artifact even when one phase fails — the
    dogfood goal is to learn what the V3 chain does on real input, including
    failures.
    """
    # observability auto-inits at import (idempotent); explicit call also
    # supported for late init after dotenv-loading. We call it explicitly
    # so the Pyright "unused import" diagnostic doesn't fire on the side-
    # effect import.
    from hooks.lib.llm import observability
    from hooks.lib.llm.supervisor import route
    from hooks.lib.llm.workers.code_reviewer import review
    observability.init_observability()

    if dry_run:
        print("DRY RUN — skipping SDK calls (env + health passed)")
        return None, None, 0.0, 0.0, None, None

    # Phase 1: supervisor
    handoff = None
    sup_elapsed = 0.0
    sup_error: str | None = None
    print()
    print("Phase 1: supervisor.route(phase='review', unsatisfied=['pre_pr_review', 'codex_reviewer'])")
    t0 = time.monotonic()
    try:
        handoff = await route(phase="review", unsatisfied=["pre_pr_review", "codex_reviewer"])
        sup_elapsed = time.monotonic() - t0
        rationale_preview = (handoff.rationale[:120] + "...") if len(handoff.rationale) > 120 else handoff.rationale
        print(f"  → target={handoff.target}")
        print(f"  → rationale={rationale_preview}")
        print(f"  → elapsed={sup_elapsed:.1f}s")
    except Exception as e:  # noqa: BLE001 — dogfood wants to record the failure
        sup_elapsed = time.monotonic() - t0
        sup_error = f"{type(e).__name__}: {e}"
        print(f"  ✗ supervisor failed: {sup_error}")
        print(f"  → elapsed={sup_elapsed:.1f}s (before failure)")

    # Phase 2: code-reviewer worker
    report = None
    work_elapsed = 0.0
    work_error: str | None = None
    print()
    print(f"Phase 2: code_reviewer.review(diff=<{len(diff)} chars>, scope='{scope}')")
    t1 = time.monotonic()
    try:
        report = await review(diff=diff, scope=scope)
        work_elapsed = time.monotonic() - t1
        print(f"  → findings={len(report.findings)}")
        print(f"  → elapsed={work_elapsed:.1f}s")
    except Exception as e:  # noqa: BLE001 — dogfood wants to record the failure
        work_elapsed = time.monotonic() - t1
        work_error = f"{type(e).__name__}: {e}"
        print(f"  ✗ code-reviewer failed: {work_error}")
        print(f"  → elapsed={work_elapsed:.1f}s (before failure)")
        if "max_turns" in str(e):
            print(f"  → hint: diff may be too large for max_turns=5; try --base <closer-sha> to narrow scope")

    return handoff, report, sup_elapsed, work_elapsed, sup_error, work_error


def write_output(
    handoff, report, sup_elapsed, work_elapsed,
    sup_error, work_error,
    diff_lines: int, base: str, head: str,
    session_id: str, dry_run: bool, out_name: str,
) -> Path:
    """Write structured JSON artifact for the comparison report.

    Always writes — even if supervisor or worker failed — so the dogfood
    captures real-world behavior including failure modes.
    """
    out_dir = REPO_ROOT / "docs" / "v3-dogfood"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / out_name

    payload = {
        "session_id": session_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "branch": "refactor/step-08-llm-package-scaffold",
        "diff_range": f"{base}..{head}",
        "diff_lines": diff_lines,
        "dry_run": dry_run,
        "supervisor": {
            "status": "ok" if handoff else ("error" if sup_error else "skipped"),
            "elapsed_sec": sup_elapsed,
            "target": handoff.target if handoff else None,
            "rationale": handoff.rationale if handoff else None,
            "error": sup_error,
        },
        "code_reviewer": {
            "status": "ok" if report else ("error" if work_error else "skipped"),
            "elapsed_sec": work_elapsed,
            "report": report.model_dump() if report else None,
            "error": work_error,
        },
        "aggregator": {
            "skipped_reason": "single worker; aggregator is moot for N=1 reports",
        },
        "langfuse": {
            "host": os.environ.get("LANGFUSE_HOST"),
            "session_id": session_id,
            "view_url": f"{os.environ.get('LANGFUSE_HOST', '').rstrip('/')}/sessions/{session_id}",
            "note": "Open Langfuse UI to see auto-instrumented spans (supervisor + worker, each a top-level trace).",
        },
    }
    with out_path.open("w") as f:
        json.dump(payload, f, indent=2, default=str)
        f.write("\n")
    return out_path


def print_budget_tail() -> None:
    """Print last few budget ledger entries to surface dogfood cost."""
    try:
        result = subprocess.run(
            [sys.executable, str(REPO_ROOT / "hooks" / "requirements-cli.py"), "budget", "tail", "-n", "5"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            print(result.stdout)
        else:
            print(f"(budget tail unavailable: rc={result.returncode})")
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        print(f"(budget tail skipped: {e})")


def main() -> int:
    p = argparse.ArgumentParser(description="V3 dogfood spike — shadow run against current branch")
    p.add_argument("--base", default="7c090b4",
                   help="git diff base (default: Step 16b housekeeping commit)")
    p.add_argument("--head", default="HEAD",
                   help="git diff head (default: HEAD)")
    p.add_argument("--dry-run", action="store_true",
                   help="Skip SDK calls (test env + health only, $0 cost)")
    p.add_argument("--out-name", default="2026-05-24-step-16c-v3-output.json",
                   help="Output filename under docs/v3-dogfood/")
    args = p.parse_args()

    print("=" * 72)
    print("V3 dogfood spike — shadow run against the current branch")
    print("=" * 72)

    # Loud-fail prereq gates
    validate_env()
    print(f"✓ env vars set: {', '.join(REQUIRED_ENV)}")
    probe_langfuse_health()
    print(f"✓ Langfuse healthy at {os.environ['LANGFUSE_HOST']}")

    # Capture diff
    diff = read_diff(args.base, args.head)
    diff_lines = diff.count("\n")
    if not diff.strip():
        print(f"✗ git diff {args.base}..{args.head} is empty — nothing to review", file=sys.stderr)
        sys.exit(1)
    print(f"✓ git diff {args.base}..{args.head}: {diff_lines} lines, {len(diff)} chars")

    # Langfuse session marker (visible in UI for grouping spans from this run)
    session_id = f"v3-dogfood-step-16c-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}"
    os.environ["LANGFUSE_SESSION_ID"] = session_id
    print(f"✓ Langfuse session_id: {session_id}")

    scope = f"{args.base}..{args.head}"
    handoff, report, sup_elapsed, work_elapsed, sup_error, work_error = asyncio.run(
        run_v3_chain(diff, scope, args.dry_run)
    )

    # Write artifact (always — captures failures too)
    out_path = write_output(
        handoff, report, sup_elapsed, work_elapsed,
        sup_error, work_error,
        diff_lines, args.base, args.head, session_id, args.dry_run,
        args.out_name,
    )
    print()
    print(f"✓ Output: {out_path.relative_to(REPO_ROOT)}")
    print()

    # Surface Langfuse UI link prominently
    langfuse_url = f"{os.environ['LANGFUSE_HOST'].rstrip('/')}/sessions/{session_id}"
    print("Langfuse traces:")
    print(f"  {langfuse_url}")
    print(f"  (or filter by metadata.session_id={session_id})")
    print()

    # Budget delta
    if not args.dry_run:
        print("Budget ledger (last 5 entries):")
        print_budget_tail()

    # Summary
    if not args.dry_run and report:
        total = sup_elapsed + work_elapsed
        print(f"Summary: supervisor {sup_elapsed:.1f}s + worker {work_elapsed:.1f}s = {total:.1f}s")
        print(f"Findings: {len(report.findings)} total")
        if report.findings:
            print("Top 5 findings (by order in report):")
            for f in report.findings[:5]:
                print(f"  [{f.severity}] {f.file}:{f.line} — {f.title}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
