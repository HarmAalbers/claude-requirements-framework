"""Multi-worker review fan-out coordinator.

Step 18b. Productionizes the pattern proven in `_spikes/v3_spike.py`: run N
pure-transform review workers in parallel over one diff, bind the whole run
into a single Langfuse session, and compose the survivors through the
aggregator agent. See ADR-017 for the coordination design.

Responsibilities that live HERE (and nowhere else):
    - Generate one `session_id` per fan-out run.
    - Enter `tracing.review_session` around every worker call AND the
      aggregator call, so they group into one filterable session.
    - Proceed with survivors on partial failure (log + drop a worker that
      raises); raise only if EVERY worker fails.

Workers themselves are I/O-free and session-unaware — `_base.run_worker`
must never enter a session (ADR-017 §2).
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from hooks.lib.llm.schemas import ReviewReport
from hooks.lib.llm.tracing import review_session
from hooks.lib.llm.workers.aggregator import aggregate

logger = logging.getLogger(__name__)

WorkerFn = Callable[[str, str], Awaitable[ReviewReport]]


@dataclass(frozen=True)
class FanoutResult:
    """Result of one fan-out run.

    `session_id` and `survivor_count` are coordinator-level metadata that the
    smoke (Langfuse URL) and Step 17b (cost attribution) need programmatically.
    They are deliberately NOT on `ReviewReport`, which is the per-worker
    structured-output schema contract (ADR-017 §5).
    """

    report: ReviewReport
    session_id: str
    survivor_count: int


def _default_workers() -> dict[str, WorkerFn]:
    """The 3-worker pilot set. Imports deferred so `import fanout` doesn't pull
    in the worker deps and so test injection of `workers=` avoids them entirely
    (arch-review #3)."""
    from hooks.lib.llm.workers import (
        appsec_auditor,
        code_reviewer,
        solid_reviewer,
    )
    return {
        "code-reviewer": code_reviewer.review,
        "solid-reviewer": solid_reviewer.review,
        "appsec-auditor": appsec_auditor.review,
    }


async def fanout_review(
    diff: str,
    scope: str = "unstaged",
    workers: dict[str, WorkerFn] | None = None,
) -> FanoutResult:
    """Run all `workers` in parallel over `diff`, aggregate survivors.

    Args:
        diff: unified diff to review.
        scope: scope label passed through to each worker (e.g. a branch range).
        workers: name -> async review fn. Defaults to the 3-worker pilot set.

    Returns:
        FanoutResult(report, session_id, survivor_count).

    Raises:
        RuntimeError: if EVERY worker fails (no survivors to aggregate).
    """
    workers = workers if workers is not None else _default_workers()
    session_id = str(uuid.uuid4())

    async def _bound(name: str, fn: WorkerFn) -> ReviewReport:
        with review_session(session_id, name):
            return await fn(diff, scope)

    names = list(workers)
    results = await asyncio.gather(
        *(_bound(name, workers[name]) for name in names),
        return_exceptions=True,
    )

    reports: list[ReviewReport] = []
    for name, result in zip(names, results):
        if isinstance(result, ReviewReport):
            reports.append(result)
        else:
            logger.warning("worker %s failed: %s", name, result)

    if not reports:
        raise RuntimeError("fanout_review: all workers failed")

    with review_session(session_id, "aggregator"):
        unified = await aggregate(reports)
    return FanoutResult(unified, session_id, len(reports))


__all__ = ["FanoutResult", "fanout_review"]
