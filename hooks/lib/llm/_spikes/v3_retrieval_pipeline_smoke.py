#!/usr/bin/env python3
"""Step 14 smoke — verifies SessionStart retrieval pipeline end-to-end.

Hard-fails loudly per `[[feedback-loud-smoke-spikes]]`: missing extras, Qdrant
down, missing collection, or semantically-wrong top hit → non-zero exit with
a clear stderr message. Fail-open is for production hooks; smokes must shout.

Prereqs (one-time):
    docker compose -f infra/docker-compose.qdrant.yml up -d
    python3 scripts/bootstrap_qdrant.py
    pip install -e '.[llm]'

Run:
    python3 hooks/lib/llm/_spikes/v3_retrieval_pipeline_smoke.py

What it does:
    1. All Step 13 prerequisite guards (extras, Qdrant, collection).
    2. Seeds 5 themed fixture sessions in Qdrant.
    3. Calls `write_retrieval_json` with a query designed to match one fixture
       (auth-themed) — same path SessionStart uses.
    4. Asserts the JSON file exists, contains hits, top hit is semantically
       correct (branch contains 'auth').
    5. Calls `render_retrieval` on the hits and prints the rendered markdown
       block so the user can eyeball what SessionStart would inject.

What it does NOT do:
    - Drive the actual SessionStart hook subprocess (covered by the
      synthetic `echo ... | python3 hooks/handle-session-start.py` smoke).
    - Test the timeout path — the test suite covers that deterministically.
"""

import json
import sys
import tempfile
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
    import os

    from qdrant_client import QdrantClient

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
            f"ERROR: collection '{COLLECTION}' dim={actual_dim}, expected {EMBED_DIM}\n"
        )
        sys.exit(5)


_refuse_if_extras_missing()
_refuse_if_qdrant_unreachable()
_refuse_if_collection_missing()


from hooks.lib.llm.memory import (  # noqa: E402
    render_retrieval,
    write_retrieval_json,
)
from hooks.lib.llm.retrieval import upsert_session  # noqa: E402


FIXTURES = [
    (
        "smk14_auth",
        "Refactored auth middleware to drop session-token storage; switched "
        "to JWT in a new api/auth.py and updated tests/test_auth.py.",
        {"project": "demo", "branch": "feat/auth-rewrite"},
    ),
    (
        "smk14_perf",
        "Added Redis cache in front of user lookup service; p99 dropped from "
        "800ms to 50ms. New module services/user_cache.py.",
        {"project": "demo", "branch": "perf/user-cache"},
    ),
    (
        "smk14_docs",
        "Updated README and docs/architecture.md to reflect the new k8s "
        "deployment topology. No code changes.",
        {"project": "demo", "branch": "docs/k8s-migration"},
    ),
    (
        "smk14_dbmig",
        "Wrote alembic migration to add NOT NULL column to users table; "
        "rolled out behind a feature flag with two-phase deploy.",
        {"project": "demo", "branch": "feat/users-not-null"},
    ),
    (
        "smk14_obs",
        "Wired OpenInference instrumentation into the claude-agent-sdk "
        "boundary; spans now flow into the self-hosted Langfuse v3.175.",
        {"project": "demo", "branch": "obs/langfuse-otel"},
    ),
]


def main() -> int:
    print("Loading embedder (cold start ~1.5s if HF cache empty)...")
    start = time.monotonic()
    from hooks.lib.llm.embedder import embed

    embed("warmup")
    print(f"  model warm in {time.monotonic() - start:.1f}s")

    print("\nSeeding 5 themed fixture sessions...")
    for sid, summary, payload in FIXTURES:
        unique = f"{sid}_{uuid.uuid4().hex[:8]}"
        ok = upsert_session(unique, summary, payload)
        if not ok:
            sys.stderr.write(f"ERROR: upsert failed for {unique}\n")
            return 6
        print(f"  ✓ {unique}")

    print("\nCalling write_retrieval_json('refactor/step-14-foo', "
          "'auth middleware JWT rewrite')...")
    with tempfile.TemporaryDirectory() as td:
        payload = write_retrieval_json(
            "refactor/step-14-foo",
            "auth middleware JWT rewrite",
            top_k=3,
            timeout_s=5.0,  # generous: real model, real Qdrant
            out_dir=Path(td),
        )
        written = Path(td) / "retrieval-refactor-step-14-foo.json"
        if not written.exists():
            sys.stderr.write("ERROR: retrieval JSON not written\n")
            return 7
        if "error" in payload:
            sys.stderr.write(f"ERROR: retrieval payload reports error: {payload['error']}\n")
            return 8
        hits = payload.get("hits", [])
        if not hits:
            sys.stderr.write("ERROR: hits empty — embeddings broken?\n")
            return 9

        print(f"  ✓ wrote {written.name} ({written.stat().st_size} bytes)")
        print("\nTop hits:")
        for i, h in enumerate(hits, 1):
            print(f"  {i}. score={h['score']:.3f} branch={h.get('branch')} "
                  f"sid={str(h.get('session_id', '?'))[:16]}")

        top_branch = hits[0].get("branch", "")
        if "auth" not in top_branch:
            sys.stderr.write(
                f"ERROR: top hit branch={top_branch!r} should mention 'auth' "
                f"for an auth-themed query. Embeddings may be regressing.\n"
            )
            return 10
        print(f"\n✓ Top hit is '{top_branch}' — semantic ordering correct.\n")

        print("─" * 60)
        print("Rendered block (what SessionStart would inject):")
        print("─" * 60)
        block = render_retrieval(hits, max_hits=3, min_score=0.5)
        if not block:
            sys.stderr.write("ERROR: render_retrieval returned empty string — "
                             "min_score=0.5 filtered everything?\n")
            return 11
        print(block, end="")
        print("─" * 60)

        print("\nJSON payload on disk:")
        print(json.dumps(json.loads(written.read_text()), indent=2)[:800] + "\n...")

    print("\n✓ Step 14 smoke complete — pipeline ready for SessionStart wiring.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
