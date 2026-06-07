#!/usr/bin/env python3
"""Test suite for hooks/lib/llm/retrieval.py (Step 13).

Strategy (from the locked Step 13 plan):
    - Real QdrantClient(":memory:") so we exercise the actual upsert/query
      surface, but with zero network and zero Docker dependency.
    - Embedder is mocked to return deterministic 384-dim vectors; no
      sentence-transformers model load.
    - QDRANT_TEST_CLIENT=1 routes retrieval._get_client() to in-memory mode.

If qdrant-client is not installed (no [llm] extras), the suite gracefully
skips with exit code 0 and a single explanatory line — matches the project
pattern for optional-extras-gated tests.

Run with: python3 tests/test_retrieval.py
"""

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

# Gate on extras BEFORE importing retrieval (which itself defers, so the
# import would succeed but the first test would fail with a useless error).
try:
    from qdrant_client import QdrantClient  # noqa: F401
    from qdrant_client.models import Distance, VectorParams
except ImportError:
    print("SKIP: qdrant-client not installed. `pip install -e '.[llm]'` to enable.")
    sys.exit(0)

# Force retrieval._get_client() into in-memory mode for the whole suite.
os.environ["QDRANT_TEST_CLIENT"] = "1"

import hooks.lib.llm.embedder as embedder
import hooks.lib.llm.retrieval as retrieval


class TestRunner:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.failed_tests: list[tuple[str, str]] = []

    def test(self, name: str, condition: bool, msg: str = ""):
        if condition:
            self.passed += 1
            print(f"  ✓ {name}")
        else:
            self.failed += 1
            self.failed_tests.append((name, msg))
            print(f"  ✗ {name}: {msg}")

    def summary(self) -> int:
        total = self.passed + self.failed
        print(f"\n{self.passed}/{total} passed")
        if self.failed:
            print("\nFailures:")
            for name, msg in self.failed_tests:
                print(f"  - {name}: {msg}")
            return 1
        return 0


# ---------- fixtures ----------


class _FakeVector:
    def __init__(self, values: list[float]):
        self._values = values

    def tolist(self) -> list[float]:
        return list(self._values)


class _FakeModel:
    """Deterministic 384-dim vectors, semantically meaningful for tests.

    Strategy: encode text length into the first slot, sum-of-codepoints into
    the rest. Two identical strings produce identical vectors; "alpha" and
    "alphabet" produce similar (length-only-diff) vectors; "alpha" and
    "zulu" produce very different vectors. Good enough for top-k ordering.
    """

    def encode(self, text: str, normalize_embeddings: bool = False):  # noqa: D401
        n = len(text)
        s = sum(ord(c) for c in text) % 1000
        # Normalize-ish: keep values in a small range so cosine ordering is stable.
        return _FakeVector(
            [n / 100.0 + (s / 1000.0) * (i / embedder.EMBED_DIM)
             for i in range(embedder.EMBED_DIM)]
        )


def _setup() -> None:
    """Per-test reset: fresh in-memory client + fake embedder + fresh schema."""
    retrieval._reset_client_for_tests()
    embedder._model = _FakeModel()
    client = retrieval._get_client()
    # The in-memory mode requires us to create the collection ourselves —
    # bootstrap_qdrant.py is for the HTTP/Docker path, not :memory:.
    if client.collection_exists(retrieval.COLLECTION):
        client.delete_collection(retrieval.COLLECTION)
    client.create_collection(
        collection_name=retrieval.COLLECTION,
        vectors_config=VectorParams(
            size=embedder.EMBED_DIM, distance=Distance.COSINE
        ),
    )


def _teardown() -> None:
    embedder._model = None
    retrieval._reset_client_for_tests()


# ---------- tests ----------


def test_upsert_session_success(r: TestRunner) -> None:
    _setup()
    try:
        ok = retrieval.upsert_session(
            "sess_abc",
            "Refactored the auth middleware to remove session token storage.",
            {"project": "demo", "branch": "feat/auth"},
        )
        r.test("upsert_session returns True on success", ok is True)
    finally:
        _teardown()


def test_query_sessions_returns_inserted(r: TestRunner) -> None:
    _setup()
    try:
        retrieval.upsert_session(
            "sess_one",
            "Refactored auth middleware",
            {"project": "demo", "branch": "feat/auth"},
        )
        retrieval.upsert_session(
            "sess_two",
            "Added unit tests for the rate limiter",
            {"project": "demo", "branch": "feat/limits"},
        )

        hits = retrieval.query_sessions("auth middleware refactor", top_k=2)
        r.test("query returns 2 hits", len(hits) == 2)
        # Consumers should read payload["session_id"]; the top-level "id"
        # is the Qdrant-side UUID derived from the session_id.
        ids = {h["session_id"] for h in hits}
        r.test("query returns inserted session_ids", ids == {"sess_one", "sess_two"})
        # And the top-level id should be a valid UUID (Qdrant invariant).
        uuid_format = all(
            len(h["id"]) == 36 and h["id"].count("-") == 4 for h in hits
        )
        r.test("top-level id is UUID-formatted", uuid_format)
        r.test(
            "hits carry payload through (project)",
            all(h.get("project") == "demo" for h in hits),
        )
        r.test(
            "hits carry summary through",
            all("summary" in h for h in hits),
        )
        r.test(
            "hits carry score",
            all(isinstance(h["score"], (int, float)) for h in hits),
        )
    finally:
        _teardown()


def test_query_top_k_limits_results(r: TestRunner) -> None:
    _setup()
    try:
        for i in range(5):
            retrieval.upsert_session(
                f"sess_{i}",
                f"work item number {i}",
                {"project": "demo", "branch": "main"},
            )
        hits = retrieval.query_sessions("anything", top_k=3)
        r.test("top_k=3 returns at most 3 hits", len(hits) <= 3)
    finally:
        _teardown()


def test_upsert_session_overwrites_same_id(r: TestRunner) -> None:
    _setup()
    try:
        retrieval.upsert_session(
            "sess_dup", "first summary", {"project": "demo", "branch": "x"}
        )
        retrieval.upsert_session(
            "sess_dup", "second summary", {"project": "demo", "branch": "y"}
        )
        hits = retrieval.query_sessions("anything", top_k=10)
        r.test(
            "single row after re-upsert (Qdrant upsert overwrites by id)",
            len(hits) == 1,
        )
        r.test(
            "overwritten payload reflects second call",
            hits[0]["summary"] == "second summary",
        )
        r.test(
            "overwritten payload reflects second call's branch",
            hits[0]["branch"] == "y",
        )
    finally:
        _teardown()


def test_upsert_fail_open_when_collection_missing(r: TestRunner) -> None:
    # Fresh client with NO collection created — verifies our fail-open guard.
    retrieval._reset_client_for_tests()
    embedder._model = _FakeModel()
    client = retrieval._get_client()
    if client.collection_exists(retrieval.COLLECTION):
        client.delete_collection(retrieval.COLLECTION)
    try:
        ok = retrieval.upsert_session(
            "sess_no_coll", "irrelevant", {"project": "x", "branch": "y"}
        )
        r.test(
            "upsert returns False when collection doesn't exist (no exception)",
            ok is False,
        )
    finally:
        _teardown()


def test_query_returns_empty_when_collection_missing(r: TestRunner) -> None:
    retrieval._reset_client_for_tests()
    embedder._model = _FakeModel()
    client = retrieval._get_client()
    if client.collection_exists(retrieval.COLLECTION):
        client.delete_collection(retrieval.COLLECTION)
    try:
        hits = retrieval.query_sessions("anything", top_k=3)
        r.test(
            "query returns [] when collection doesn't exist (no exception)",
            hits == [],
        )
    finally:
        _teardown()


def test_get_client_singleton(r: TestRunner) -> None:
    retrieval._reset_client_for_tests()
    try:
        c1 = retrieval._get_client()
        c2 = retrieval._get_client()
        r.test("_get_client() returns same instance on repeat calls", c1 is c2)
    finally:
        _teardown()


def main() -> int:
    print("Running retrieval tests...")
    r = TestRunner()
    test_upsert_session_success(r)
    test_query_sessions_returns_inserted(r)
    test_query_top_k_limits_results(r)
    test_upsert_session_overwrites_same_id(r)
    test_upsert_fail_open_when_collection_missing(r)
    test_query_returns_empty_when_collection_missing(r)
    test_get_client_singleton(r)
    return r.summary()


if __name__ == "__main__":
    sys.exit(main())
