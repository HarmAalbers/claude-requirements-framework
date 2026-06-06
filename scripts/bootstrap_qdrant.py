#!/usr/bin/env python3
"""Idempotent Qdrant collection bootstrap for Step 13.

Creates the `sessions` collection at the embedding dimension used by
`BAAI/bge-small-en-v1.5` (384) with cosine distance. Safe to rerun: if the
collection already exists, prints `exists:` and returns 0.

Why a separate bootstrap script (instead of lazy-creating on first upsert):
    - Failure mode separation: `docker compose up` succeeds before the
      schema exists. Without an explicit bootstrap, the first session that
      ends after bringing Qdrant up would silently no-op (upsert against
      a missing collection raises; retrieval.py is fail-open).
    - Visibility: the user sees `created: sessions (dim=384, cosine)` once,
      which is much louder than discovering a missing collection via a
      log line in `~/.claude/requirements.log` weeks later.

Usage:
    docker compose -f infra/docker-compose.qdrant.yml up -d
    python3 scripts/bootstrap_qdrant.py

Env overrides (optional):
    QDRANT_HOST  (default: localhost)
    QDRANT_PORT  (default: 6333)
"""

from __future__ import annotations

import os
import sys

EMBED_DIM = 384  # BAAI/bge-small-en-v1.5; must match hooks/lib/llm/embedder.py
COLLECTIONS = ("sessions",)  # add new collections here (Step 14+ may add "findings")


def main() -> int:
    try:
        from qdrant_client import QdrantClient
        from qdrant_client.models import Distance, VectorParams
    except ImportError:
        sys.stderr.write(
            "ERROR: qdrant-client not installed. Run:\n"
            "    pip install -e '.[llm]'\n"
        )
        return 2

    host = os.getenv("QDRANT_HOST", "localhost")
    port = int(os.getenv("QDRANT_PORT", "6333"))

    try:
        client = QdrantClient(host=host, port=port)
        # Force a real round-trip so we fail loudly on a closed port instead
        # of waiting until the first create_collection call.
        client.get_collections()
    except Exception as exc:
        sys.stderr.write(
            f"ERROR: cannot reach Qdrant at {host}:{port} ({type(exc).__name__}: {exc}).\n"
            "Bring it up with:\n"
            "    docker compose -f infra/docker-compose.qdrant.yml up -d\n"
        )
        return 1

    for name in COLLECTIONS:
        if client.collection_exists(name):
            print(f"exists: {name}")
            continue
        client.create_collection(
            collection_name=name,
            vectors_config=VectorParams(size=EMBED_DIM, distance=Distance.COSINE),
        )
        print(f"created: {name} (dim={EMBED_DIM}, cosine)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
