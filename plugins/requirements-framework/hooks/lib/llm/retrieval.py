"""Qdrant-backed session store (Step 13 — write + minimal query).

Public surface:
    COLLECTION                — str, the only collection Step 13 writes to
    upsert_session(session_id, summary, payload) -> bool
                              — embed + upsert; True on success, False on
                                any failure (fail-open for SessionEnd hook).
    query_sessions(query, top_k=3) -> list[dict]
                              — embed query + return hits with payload merged.
                                Empty list on any failure.

Design notes:

1. **Fail-open everywhere.** This module is called from the SessionEnd hook,
   which itself is fail-open at the framework level. Surfacing exceptions
   would risk breaking session teardown. Both public functions catch broadly
   and return a sentinel value the caller can check. Errors are NOT logged
   from here — the caller (SessionEnd) decides the log level.

2. **Singleton QdrantClient.** Reuses the HTTP connection pool. The client
   is also lazily constructed so importing this module doesn't try to
   connect at import time (matters for non-Qdrant test runs).

3. **No collection auto-creation.** `scripts/bootstrap_qdrant.py` owns
   schema creation. If the collection is missing, upsert will raise and we
   return False — that's the signal to run the bootstrap. We deliberately
   don't paper over a missing schema with implicit creation because that
   would mask config drift (wrong dim, wrong distance metric).

4. **Embedder import deferred.** Same reason as in `embedder.py` itself:
   defer the sentence-transformers cost until something actually calls
   `upsert_session` or `query_sessions`. Importing `retrieval` should be
   free.

5. **Test mode via QDRANT_TEST_CLIENT.** When the env var is set to "1",
   `_get_client()` returns a `QdrantClient(":memory:")` singleton instead of
   the HTTP client. This is the seam tests use to exercise the real Qdrant
   surface without Docker. Production code never sets this var.
"""

import os
import uuid
from typing import Any

COLLECTION = "sessions"

# Stable namespace for deriving deterministic UUIDs from framework session_ids.
# Qdrant point IDs must be UUIDs or unsigned ints; framework session_ids are
# 8-char hex strings (e.g. "eca06a48"), so we hash via uuid5(NAMESPACE_OID,
# session_id). Same session_id → same UUID, so re-upserts overwrite cleanly.
_SESSION_UUID_NAMESPACE = uuid.NAMESPACE_OID


def _session_point_id(session_id: str) -> str:
    """Deterministic UUID5 derived from `session_id` — used as Qdrant point id."""
    return str(uuid.uuid5(_SESSION_UUID_NAMESPACE, session_id))

_client: Any | None = None  # QdrantClient | None


def _get_client() -> Any:
    """Return the process-singleton QdrantClient, lazily constructed.

    Honors QDRANT_TEST_CLIENT=1 by switching to in-memory mode. Honors
    QDRANT_HOST / QDRANT_PORT for the HTTP client.
    """
    global _client
    if _client is None:
        from qdrant_client import QdrantClient

        if os.getenv("QDRANT_TEST_CLIENT") == "1":
            _client = QdrantClient(":memory:")
        else:
            _client = QdrantClient(
                host=os.getenv("QDRANT_HOST", "localhost"),
                port=int(os.getenv("QDRANT_PORT", "6333")),
            )
    return _client


def _reset_client_for_tests() -> None:
    """Test-only: drop the singleton so the next call rebuilds it.

    Public-ish (leading underscore is a convention, not enforcement) because
    test_retrieval.py needs it to swap between `:memory:` clients without
    leaking state across tests.
    """
    global _client
    _client = None


def upsert_session(session_id: str, summary: str, payload: dict) -> bool:
    """Embed `summary` and upsert one point to the sessions collection.

    Args:
        session_id: Stable id for the point (overwrites prior session_id reuse).
        summary: Text to embed AND store in the payload under "summary".
        payload: Extra metadata (project, branch, ended_at, etc.).

    Returns:
        True if the upsert reached Qdrant, False on any failure
        (missing extras, missing collection, network error, …).
    """
    try:
        from qdrant_client.models import PointStruct

        from hooks.lib.llm.embedder import embed

        vec = embed(summary)
        _get_client().upsert(
            collection_name=COLLECTION,
            points=[
                PointStruct(
                    id=_session_point_id(session_id),
                    vector=vec,
                    # session_id kept in payload so the human-readable id
                    # survives the UUID hash; consumers should prefer
                    # payload["session_id"] over the Qdrant-side id.
                    payload={**payload, "summary": summary, "session_id": session_id},
                )
            ],
        )
        return True
    except Exception:
        return False


def query_sessions(query: str, top_k: int = 3) -> list[dict]:
    """Return top-k semantically similar session payloads for `query`.

    Each result dict contains: id, score, plus every key from the stored
    payload (project, branch, ended_at, summary, …). Empty list on any
    failure — caller cannot distinguish "no results" from "Qdrant down" from
    "extras missing" by inspecting the return alone.
    """
    try:
        from hooks.lib.llm.embedder import embed

        vec = embed(query)
        hits = _get_client().query_points(
            collection_name=COLLECTION, query=vec, limit=top_k
        ).points
        return [
            {"id": h.id, "score": h.score, **(h.payload or {})}
            for h in hits
        ]
    except Exception:
        return []
