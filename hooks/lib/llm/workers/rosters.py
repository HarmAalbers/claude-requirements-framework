"""Worker rosters for fan-out review runs.

Step 18c. `review_workers()` is the `/deep-review`-parity roster used by `/v3-review`.
It is kept separate from `fanout._default_workers()` (the 3-worker 18b pilot) so the
coordinator stays roster-agnostic — callers pass the roster via `fanout_review(workers=...)`.

Laziness (arch-review #7): worker modules are imported INSIDE `review_workers()`, never at
module scope, so importing `rosters` doesn't pull in the worker→SDK dependency chain. The
`WorkerFn` type is imported one-way under `TYPE_CHECKING` only — at runtime the annotation is
a string (`from __future__ import annotations`), so importing `rosters` does not import
`fanout`. `fanout.py` must NOT import this module (that would create a cycle).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hooks.lib.llm.workers.fanout import WorkerFn


def review_workers() -> dict[str, WorkerFn]:
    """The `/v3-review` roster — `/deep-review`'s reviewers plus `solid-reviewer`.

    Seeded here with the 3 existing workers; Step 18c batches 1 and 2 grow this to 11.
    Imports are deferred so this is callable without eagerly importing the worker modules.
    """
    from hooks.lib.llm.workers import (
        appsec_auditor,
        backward_compatibility_checker,
        code_reviewer,
        comment_analyzer,
        compliance_auditor,
        silent_failure_hunter,
        solid_reviewer,
        tenant_isolation_auditor,
        test_analyzer,
        type_design_analyzer,
    )
    return {
        "code-reviewer": code_reviewer.review,
        "solid-reviewer": solid_reviewer.review,
        "appsec-auditor": appsec_auditor.review,
        "silent-failure-hunter": silent_failure_hunter.review,
        "test-analyzer": test_analyzer.review,
        "backward-compatibility-checker": backward_compatibility_checker.review,
        "type-design-analyzer": type_design_analyzer.review,
        "comment-analyzer": comment_analyzer.review,
        "tenant-isolation-auditor": tenant_isolation_auditor.review,
        "compliance-auditor": compliance_auditor.review,
    }


__all__ = ["review_workers"]
