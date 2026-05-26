"""Entry point for the `/v3-review` command — SDK fan-out review.

Step 18c. Two layers (arch-review #1):

    run_review(diff, scope, files, workers) -> str
        The testable core: tool-gate → fan-out → render. Pure enough to unit-test
        with mock workers + a mocked gate. Never raises for an all-workers-fail or
        aggregator failure — it returns a human-readable markdown report in every
        case so the command always has something to show.

    main()
        The thin shell: resolve scope via `prepare-diff-scope` (loud-fail), read the
        prepared `/tmp/review.diff` + `/tmp/review_scope.txt`, call `run_review`, and
        print the markdown plus a session-id + cost footer. The async run is wrapped
        in try/finally that drains pending tasks to tame the `aclose()` teardown race
        at N≈10 (arch-review #4).

`run_tool_gate`, `fanout_review`, and `render_review_markdown` are imported at module
level so tests can `patch.object(review_cli, ...)` them.
"""

from __future__ import annotations

import asyncio
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from hooks.lib.llm import budget
from hooks.lib.llm.render import render_review_markdown
from hooks.lib.llm.tool_gate import run_tool_gate
from hooks.lib.llm.workers.fanout import fanout_review
from hooks.lib.llm.workers.rosters import review_workers

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_SCOPE_SCRIPT = (REPO_ROOT / "plugins" / "requirements-framework"
                 / "scripts" / "prepare-diff-scope")
_DIFF_PATH = Path("/tmp/review.diff")
_SCOPE_PATH = Path("/tmp/review_scope.txt")


async def run_review(diff: str, scope: str, files: list[str], workers) -> str:
    """Tool-gate → fan-out → render. Returns ADR-013 markdown in every case.

    Never raises on review failure: a tool-gate block, an all-workers-fail, and a
    successful review all map to a markdown string with a verdict line.
    """
    gate_errors = run_tool_gate(files)
    if gate_errors:
        lines = [
            "# V3 Review — ABORTED at the tool gate",
            "",
            "Deterministic linters failed; no LLM spend was incurred. Fix these first:",
            "",
        ]
        lines += [f"- {e}" for e in gate_errors[:50]]
        lines += ["", "**Verdict**: FIX TOOL ERRORS FIRST"]
        return "\n".join(lines)

    try:
        result = await fanout_review(diff, scope, workers=workers)
    except RuntimeError as exc:
        return (
            "# V3 Review — FAILED\n\n"
            f"All review workers failed: {exc}\n\n"
            "This usually means the diff is too large for the workers to process. "
            "Try a narrower scope (e.g. a commit range like `abc123~1..HEAD`).\n\n"
            "**Verdict**: FIX ISSUES FIRST"
        )

    md = render_review_markdown(
        result.report,
        worker_errors=result.worker_errors,
        aggregator_error=result.aggregator_error,
    )
    # Total workers = survivors + failed workers. aggregator_error is NOT a
    # worker and must not inflate the ratio (self-review #3).
    total_workers = result.survivor_count + len(result.worker_errors)
    return (
        f"{md}\n\n---\n"
        f"session_id: {result.session_id}  ·  "
        f"survivors: {result.survivor_count}/{total_workers}"
    )


def _run_async(coro):
    """Run `coro` and drain any lingering tasks before closing the loop.

    The fan-out leaves worker async-generators mid-stream on the exception path;
    abandoning them at loop teardown triggers `aclose(): asynchronous generator is
    already running` (ADR-017). Cancelling + gathering pending tasks first keeps
    teardown quiet at N≈10.
    """
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        pending = asyncio.all_tasks(loop)
        for task in pending:
            task.cancel()
        if pending:
            loop.run_until_complete(
                asyncio.gather(*pending, return_exceptions=True))
        loop.close()


def _resolve_scope(scope_arg: str) -> tuple[str, list[str], str]:
    """Run prepare-diff-scope; return (diff, python_files, scope_label). Loud-fail."""
    if not _SCOPE_SCRIPT.exists():
        print(f"v3-review: scope resolver not found: {_SCOPE_SCRIPT}",
              file=sys.stderr)
        raise SystemExit(1)
    proc = subprocess.run(
        ["bash", str(_SCOPE_SCRIPT), scope_arg],
        capture_output=True, text=True, cwd=str(REPO_ROOT))
    if proc.returncode != 0:
        print(f"v3-review: prepare-diff-scope failed: "
              f"{proc.stderr.strip() or proc.stdout.strip()}", file=sys.stderr)
        raise SystemExit(1)
    if not _DIFF_PATH.exists() or not _DIFF_PATH.read_text().strip():
        print("v3-review: no changes to review", file=sys.stderr)
        raise SystemExit(1)
    diff = _DIFF_PATH.read_text()
    scope_files = ([ln.strip() for ln in _SCOPE_PATH.read_text().splitlines()
                    if ln.strip()] if _SCOPE_PATH.exists() else [])
    return diff, scope_files, proc.stdout.strip()


def main() -> None:
    scope_arg = sys.argv[1] if len(sys.argv) > 1 else ""
    diff, files, scope_label = _resolve_scope(scope_arg)

    now = datetime.now(timezone.utc)
    before = sum(1 for _ in budget.load_month(now.year, now.month))

    markdown = _run_async(
        run_review(diff, scope_label or "v3-review", files, review_workers()))
    print(markdown)

    new = list(budget.load_month(now.year, now.month))[before:]
    cost = budget.summarize(new)
    print(f"\ncost: ${cost['mtd_usd']:.4f} over {cost['call_count']} call(s)")


if __name__ == "__main__":
    main()


__all__ = ["run_review", "main"]
