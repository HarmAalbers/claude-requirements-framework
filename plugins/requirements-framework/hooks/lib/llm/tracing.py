"""Usage-time OpenTelemetry helpers for the V3 review pipeline.

Step 18b. Distinct from `observability.py`, which is *setup-time*:
`init_observability()` runs once per process, is idempotent, and owns the
TracerProvider + atexit flush. This module is *usage-time*: `review_session`
is entered once per worker call, must be fail-open, and holds no module state.
Keeping the two apart avoids mixing a once-only singleton with a per-call
context manager (ADR-017 §2, arch-review #5).

`review_session` is the boundary that groups the N workers + 1 aggregator of a
single fan-out run into one filterable Langfuse session. The fan-out
coordinator (`workers/fanout.py`) owns it — individual workers never enter it.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager


@contextmanager
def review_session(session_id: str, worker: str) -> Iterator[None]:
    """Bind enclosed `query()` calls to one Langfuse session + per-worker tag.

    Sets the OpenInference span attributes `session_id` and `tags`
    (`worker:<worker>`, `feature:review`) for everything that runs inside the
    `with` block. The Step 11 boundary instrumentation then stamps those onto
    the AGENT span it emits, so the whole fan-out shows up as one session.

    Fail-open: if `openinference` isn't installed, this is a no-op context
    manager — workers still run, they're just ungrouped in the trace UI. The
    import is deferred (not module-level) so importing this module never
    requires the optional `[llm]` extras.
    """
    try:
        from openinference.instrumentation import using_attributes
    except ImportError:
        yield
        return
    with using_attributes(
        session_id=session_id,
        tags=[f"worker:{worker}", "feature:review"],
    ):
        yield


__all__ = ["review_session"]
