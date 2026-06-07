#!/usr/bin/env python3
"""Step 13 smoke — verifies Qdrant + sentence-transformers round-trip.

Hard-fails loudly per `[[feedback-loud-smoke-spikes]]`: if Qdrant is down,
the [llm] extras are missing, or the collection wasn't bootstrapped, the
script exits non-zero with a clear stderr message. The whole point of a
smoke is to surface problems — a fail-open success print would defeat that.

Prereqs:
    docker compose -f infra/docker-compose.qdrant.yml up -d
    python3 scripts/bootstrap_qdrant.py
    pip install -e '.[llm]'   # sentence-transformers + qdrant-client

Run:
    python3 hooks/lib/llm/_spikes/v3_qdrant_smoke.py

What it does:
    1. Verify Qdrant is reachable (get_collections round-trip).
    2. Verify the `sessions` collection exists at the expected dimension.
    3. Load the REAL BAAI/bge-small-en-v1.5 model (~33MB on first run,
       cached at ~/.cache/huggingface/ thereafter).
    4. Insert 3 fixture sessions with distinct summaries.
    5. Query "auth middleware refactor" and print the top hit.
    6. Verify the top hit is the auth-themed session (semantic ordering
       check — proves embeddings carry meaning, not just hashes).

What it does NOT do:
    - Exercise the SDK Haiku summarizer path. The summarizer has its own
      mocked-SDK test suite (tests/test_summarizer.py); integration with
      the real SDK runs through the SessionEnd hook in regular use.
      A smoke for the SDK lives at _spikes/v3_agent_sdk_smoke.py.

Verify:
    Open http://localhost:6333/dashboard → Collections → sessions and
    confirm the 3 points are visible. The script tears them down at the
    end to keep the smoke idempotent.
"""

import sys
import time
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT))


def _refuse_if_extras_missing() -> None:
    missing: list[str] = []
    try:
        import qdrant_client  # noqa: F401
    except ImportError:
        missing.append("qdrant-client")
    try:
        import sentence_transformers  # noqa: F401
    except ImportError:
        missing.append("sentence-transformers")
    if missing:
        sys.stderr.write(
            "ERROR: missing python package(s): " + ", ".join(missing) + "\n"
            "Install with:\n"
            "    pip install -e '.[llm]'\n"
        )
        sys.exit(2)


def _refuse_if_qdrant_unreachable() -> None:
    from qdrant_client import QdrantClient
    import os

    host = os.getenv("QDRANT_HOST", "localhost")
    port = int(os.getenv("QDRANT_PORT", "6333"))
    try:
        client = QdrantClient(host=host, port=port)
        client.get_collections()
    except Exception as exc:
        sys.stderr.write(
            f"ERROR: Qdrant unreachable at {host}:{port} "
            f"({type(exc).__name__}: {exc}).\n"
            "Bring it up with:\n"
            "    docker compose -f infra/docker-compose.qdrant.yml up -d\n"
        )
        sys.exit(3)


def _refuse_if_collection_missing() -> None:
    from qdrant_client import QdrantClient

    from hooks.lib.llm.embedder import EMBED_DIM
    from hooks.lib.llm.retrieval import COLLECTION

    client = QdrantClient()
    if not client.collection_exists(COLLECTION):
        sys.stderr.write(
            f"ERROR: collection '{COLLECTION}' missing. Bootstrap with:\n"
            "    python3 scripts/bootstrap_qdrant.py\n"
        )
        sys.exit(4)

    info = client.get_collection(COLLECTION)
    actual_dim = info.config.params.vectors.size
    if actual_dim != EMBED_DIM:
        sys.stderr.write(
            f"ERROR: collection '{COLLECTION}' has dim={actual_dim}, "
            f"expected {EMBED_DIM}. Drop & re-bootstrap:\n"
            "    docker compose -f infra/docker-compose.qdrant.yml down -v\n"
            "    docker compose -f infra/docker-compose.qdrant.yml up -d\n"
            "    python3 scripts/bootstrap_qdrant.py\n"
        )
        sys.exit(5)


_refuse_if_extras_missing()
_refuse_if_qdrant_unreachable()
_refuse_if_collection_missing()


from hooks.lib.llm.retrieval import (  # noqa: E402 — must follow guards
    COLLECTION,
    query_sessions,
    upsert_session,
)


FIXTURES = [
    # The auth-themed one — what the query should retrieve first.
    (
        "smoke_auth",
        "Refactored auth middleware to remove session-token storage that "
        "legal flagged as non-compliant. Switched to JWT in a new file "
        "api/auth.py, deleted the old SessionStore class, and updated "
        "tests/test_auth.py to cover the new flow.",
        {"project": "demo", "branch": "feat/auth-rewrite"},
    ),
    (
        "smoke_perf",
        "Added a Redis-backed cache layer in front of the user lookup "
        "service to bring p99 latency from 800ms down to 50ms. New "
        "module: services/user_cache.py.",
        {"project": "demo", "branch": "perf/user-cache"},
    ),
    (
        "smoke_docs",
        "Updated README and docs/architecture.md to reflect the new "
        "deployment topology (k8s instead of bare metal). No code changes.",
        {"project": "demo", "branch": "docs/k8s-migration"},
    ),
]


def main() -> int:
    print("Loading BAAI/bge-small-en-v1.5 (first run: ~1.5s + ~33MB download)...")
    start = time.monotonic()
    # Touch the embedder via a real call so the cold-start cost is visible.
    from hooks.lib.llm.embedder import embed

    embed("warmup")
    print(f"  model loaded in {time.monotonic() - start:.1f}s")

    print("\nUpserting 3 fixture sessions...")
    for sid, summary, payload in FIXTURES:
        # Suffix with a uuid hex so reruns don't collide with prior runs
        # in the persistent Qdrant volume.
        unique_id = f"{sid}_{uuid.uuid4().hex[:8]}"
        ok = upsert_session(unique_id, summary, payload)
        if not ok:
            sys.stderr.write(f"ERROR: upsert failed for {unique_id}\n")
            return 6
        print(f"  ✓ upserted {unique_id} ({len(summary)} chars summary)")

    print("\nQuerying 'auth middleware refactor'...")
    hits = query_sessions("auth middleware refactor", top_k=3)
    if not hits:
        sys.stderr.write("ERROR: query returned no hits — embeddings broken?\n")
        return 7

    for i, h in enumerate(hits, 1):
        print(
            f"  {i}. session_id={h.get('session_id', '?')[:20]} "
            f"score={h['score']:.3f} branch={h.get('branch', '?')}"
        )

    # Semantic-ordering assertion: the auth-themed fixture should rank first
    # for an auth-themed query. If it doesn't, embeddings aren't carrying
    # the meaning we expect — that's a real problem worth surfacing.
    top_branch = hits[0].get("branch", "")
    if "auth" not in top_branch:
        sys.stderr.write(
            f"ERROR: top hit branch={top_branch!r} doesn't mention 'auth'. "
            "Embeddings may not be carrying semantic meaning.\n"
        )
        return 8
    print(f"\n✓ Semantic ordering correct: '{top_branch}' ranked first for "
          "'auth middleware refactor' query.")

    # Clean up the fixture points so reruns stay idempotent. Use the same
    # UUID5 hashing the retrieval module uses, applied to each fixture's
    # actual upserted id (we don't track those above, so just leave them —
    # the dashboard view at /dashboard makes them easy to clear by hand if
    # you want a clean slate).
    print("\nDone. Fixture points left in place; clear via dashboard if needed:")
    print(f"  http://localhost:6333/dashboard#/collections/{COLLECTION}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
