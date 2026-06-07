"""Entry point for the `/v3-review` command — SDK fan-out review.

Launch constraint (observed, mechanism not fully diagnosed): run this
INTERACTIVELY in a terminal. The fan-out spawns N `claude-agent-sdk`
subprocesses (the bundled Max CLI), and their control-protocol handshake needs
an interactive stdio context. Launching `/v3-review` as a DETACHED / BACKGROUND
process with redirected stdio (e.g. via an automation tool) fails with
`Control request timeout: initialize` + cancelled session hooks. A foreground
shell run works (incl. via the `!` prefix inside a Claude Code session).

Step 18c. Two layers (arch-review #1):

    run_review(diff, scope, files, workers) -> str
        The testable core: tool-gate → fan-out → render. Pure enough to unit-test
        with mock workers + a mocked gate. Never raises for an all-workers-fail or
        aggregator failure — it returns a human-readable markdown report in every
        case so the command always has something to show.

    main()
        The thin shell: resolve scope via `prepare-diff-scope` (loud-fail), read the
        prepared `/tmp/review.diff` + `/tmp/review_scope.txt`, call `run_review`, and
        print the markdown plus a session-id + cost footer. Uses plain `asyncio.run`
        — a manual loop-close/task-cancel (the original aclose-race mitigation) made
        teardown WORSE under live instrumentation (OTel "Failed to detach context"
        flood + "Event loop is closed" __del__ errors); letting asyncio.run drain the
        generators in their own contexts is clean. Accepts the single documented
        `aclose()` warning (ADR-017) over the flood.

`run_tool_gate`, `fanout_review`, and `render_review_markdown` are imported at module
level so tests can `patch.object(review_cli, ...)` them.
"""

import asyncio
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent


def _load_dotenv() -> None:
    """Load `infra/.env` (then repo `.env`) so `/v3-review` picks up LANGFUSE_*
    without the caller exporting them. Shell env wins (`override=False`).

    Soft dependency on python-dotenv: if it's absent we fall through to shell
    env only, and the run's footer will report observability disabled.
    """
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    for candidate in (REPO_ROOT / "infra" / ".env", REPO_ROOT / ".env"):
        if candidate.is_file():
            load_dotenv(candidate, override=False)


# Load creds + initialize observability BEFORE importing the SDK wrapper chain.
# The OpenInference instrumentor patches `claude_agent_sdk.query` at instrument
# time; `claude.py` captures its reference at import time. If we init after that
# import, review runs untraced (claude.py docstring: import order matters).
_load_dotenv()
from hooks.lib.llm.observability import init_observability  # noqa: E402
init_observability()

from hooks.lib.llm import budget  # noqa: E402
from hooks.lib.llm import observability  # noqa: E402
from hooks.lib.llm.render import render_review_markdown  # noqa: E402
from hooks.lib.llm.tool_gate import run_tool_gate  # noqa: E402
from hooks.lib.llm.workers.fanout import fanout_review  # noqa: E402
from hooks.lib.llm.workers.rosters import review_workers  # noqa: E402
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
            f"{exc}\n\n"
            "Likely causes:\n"
            "- **Oversized diff** — the workers couldn't process it. Try a narrower "
            "scope (e.g. a commit range like `abc123~1..HEAD`).\n"
            "- **Wrong launch context** — `Control request timeout: initialize` / "
            "cancelled hooks mean the SDK subprocess couldn't start. Run "
            "`/v3-review` INTERACTIVELY in a terminal; launching it as a "
            "detached/background process with redirected stdio can break the "
            "SDK's control handshake.\n\n"
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
    # A successful diff resolution that produced no scope file is anomalous —
    # treat it as loud, not as "no files to lint" (self-review #8: otherwise a
    # missing scope file silently degrades the tool-gate to a no-op).
    if not _SCOPE_PATH.exists():
        print("v3-review: prepare-diff-scope produced a diff but no scope file "
              f"({_SCOPE_PATH}) — refusing to run the gate blind", file=sys.stderr)
        raise SystemExit(1)
    scope_files = [ln.strip() for ln in _SCOPE_PATH.read_text().splitlines()
                   if ln.strip()]
    return diff, scope_files, proc.stdout.strip()


def main() -> None:
    scope_arg = sys.argv[1] if len(sys.argv) > 1 else ""
    diff, files, scope_label = _resolve_scope(scope_arg)

    now = datetime.now(timezone.utc)
    before = sum(1 for _ in budget.load_month(now.year, now.month))

    # Plain asyncio.run: lets Python drain the worker generators in their own
    # contexts, which the OpenInference instrumentor cleans up correctly. A
    # manual loop-close + task-cancel here instead produced an OTel
    # "Failed to detach context" flood + "Event loop is closed" __del__ errors.
    markdown = asyncio.run(
        run_review(diff, scope_label or "v3-review", files, review_workers()))
    print(markdown)

    new = list(budget.load_month(now.year, now.month))[before:]
    cost = budget.summarize(new)
    print(f"\ncost: ${cost['mtd_usd']:.4f} over {cost['call_count']} call(s)")

    # Be honest about observability: a printed session_id only corresponds to a
    # real Langfuse trace when instrumentation actually initialized (creds present
    # AND extras installed). Report the true state, not just env presence.
    if observability._instrumented and cost["call_count"] > 0:
        print("Langfuse: traces exported — filter by the session_id above")
    elif observability._instrumented:
        print("Langfuse: instrumented, but no LLM calls were made this run "
              "(nothing to trace — e.g. the tool gate aborted first)")
    else:
        print("Langfuse: disabled — session_id is local-only, no trace was sent "
              "(set LANGFUSE_* in infra/.env or the shell)")


if __name__ == "__main__":
    main()


__all__ = ["run_review", "main"]
