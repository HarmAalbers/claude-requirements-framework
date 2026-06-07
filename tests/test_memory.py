#!/usr/bin/env python3
"""Test suite for hooks/lib/llm/memory.py (Step 14).

Strategy (from the locked Step 14 plan):
    - Pure helpers (_branch_to_filename, render_retrieval) exercised directly
      with no infra dependency.
    - write_retrieval_json exercised against an in-memory Qdrant (Step 13
      pattern: QDRANT_TEST_CLIENT=1 + monkey-patched _FakeModel embedder).
    - Timeout path exercised by monkey-patching query_sessions to sleep past
      the budget.

If qdrant-client is not installed (no [llm] extras), only the pure-helper
tests run; the round-trip / timeout tests skip gracefully.

Run with: python3 tests/test_memory.py
"""

import json
import os
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

# Optional-extras gate: pure helpers always run; round-trip tests require qdrant.
try:
    from qdrant_client import QdrantClient  # noqa: F401
    from qdrant_client.models import Distance, VectorParams

    _HAS_QDRANT = True
except ImportError:
    _HAS_QDRANT = False

if _HAS_QDRANT:
    os.environ["QDRANT_TEST_CLIENT"] = "1"
    import hooks.lib.llm.embedder as embedder
    import hooks.lib.llm.retrieval as retrieval

import hooks.lib.llm.memory as memory  # always importable (no infra at import)


class TestRunner:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.skipped = 0
        self.failed_tests: list[tuple[str, str]] = []

    def test(self, name: str, condition: bool, msg: str = ""):
        if condition:
            self.passed += 1
            print(f"  ✓ {name}")
        else:
            self.failed += 1
            self.failed_tests.append((name, msg))
            print(f"  ✗ {name}: {msg}")

    def skip(self, name: str, reason: str):
        self.skipped += 1
        print(f"  - {name} (skipped: {reason})")

    def summary(self) -> int:
        total = self.passed + self.failed
        print(f"\n{self.passed}/{total} passed ({self.skipped} skipped)")
        if self.failed:
            print("\nFailures:")
            for name, msg in self.failed_tests:
                print(f"  - {name}: {msg}")
            return 1
        return 0


# ---------- fixtures (Qdrant-gated) ----------

if _HAS_QDRANT:

    class _FakeVector:
        def __init__(self, values: list[float]):
            self._values = values

        def tolist(self) -> list[float]:
            return list(self._values)

    class _FakeModel:
        """Deterministic 384-dim embedder (mirrors test_retrieval.py)."""

        def encode(self, text: str, normalize_embeddings: bool = False):
            n = len(text)
            s = sum(ord(c) for c in text) % 1000
            return _FakeVector(
                [n / 100.0 + (s / 1000.0) * (i / embedder.EMBED_DIM)
                 for i in range(embedder.EMBED_DIM)]
            )

    def _setup() -> None:
        retrieval._reset_client_for_tests()
        embedder._model = _FakeModel()
        client = retrieval._get_client()
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


# ---------- pure-helper tests (no infra) ----------


def test_branch_to_filename_sanitizes_slashes(r: TestRunner) -> None:
    r.test(
        "slashes in branch name become dashes",
        memory._branch_to_filename("refactor/step-14") == "refactor-step-14",
    )


def test_branch_to_filename_collapses_runs(r: TestRunner) -> None:
    r.test(
        "consecutive non-safe chars collapse to a single dash",
        memory._branch_to_filename("foo///bar") == "foo-bar",
    )


def test_branch_to_filename_strips_trailing_dashes(r: TestRunner) -> None:
    r.test(
        "trailing junk stripped",
        memory._branch_to_filename("foo///") == "foo",
    )


def test_branch_to_filename_handles_empty(r: TestRunner) -> None:
    r.test(
        "empty branch falls back to 'unknown'",
        memory._branch_to_filename("") == "unknown",
    )
    r.test(
        "all-junk branch falls back to 'unknown'",
        memory._branch_to_filename("///") == "unknown",
    )


def test_render_retrieval_empty_returns_empty_string(r: TestRunner) -> None:
    r.test(
        "no hits → empty string (so the SessionStart prepend is a no-op)",
        memory.render_retrieval([]) == "",
    )


def test_render_retrieval_filters_by_min_score(r: TestRunner) -> None:
    hits = [
        {"session_id": "lowscore", "score": 0.30, "branch": "x", "summary": "noise"},
        {"session_id": "goodone1", "score": 0.66, "branch": "y", "summary": "signal"},
    ]
    out = memory.render_retrieval(hits, min_score=0.5)
    r.test("low-score hit dropped", "lowscore" not in out)
    r.test("high-score hit kept", "goodone1" in out)


def test_render_retrieval_all_below_threshold_returns_empty(r: TestRunner) -> None:
    hits = [{"session_id": "x", "score": 0.10, "branch": "b", "summary": "s"}]
    r.test(
        "all below min_score → empty string (no header)",
        memory.render_retrieval(hits, min_score=0.5) == "",
    )


def test_render_retrieval_truncates_to_max_hits(r: TestRunner) -> None:
    hits = [
        {"session_id": f"sess{i}", "score": 0.9, "branch": "b", "summary": "s"}
        for i in range(5)
    ]
    out = memory.render_retrieval(hits, max_hits=3)
    r.test("max_hits=3 keeps 3 bullets", out.count("- `") == 3)


def test_render_retrieval_one_line_summary(r: TestRunner) -> None:
    multi = "first line\nsecond line\nthird line"
    hits = [{"session_id": "x" * 16, "score": 0.9, "branch": "b", "summary": multi}]
    out = memory.render_retrieval(hits)
    r.test("only first line of summary appears", "second line" not in out)
    r.test("first line included", "first line" in out)
    r.test(
        "session_id truncated to 8 chars in render",
        "xxxxxxxx" in out and "xxxxxxxxx" not in out,
    )


def test_render_retrieval_truncates_long_summary(r: TestRunner) -> None:
    long = "x" * 500
    hits = [{"session_id": "s", "score": 0.9, "branch": "b", "summary": long}]
    out = memory.render_retrieval(hits)
    r.test("summary truncated below 200 chars", all(len(line) < 220 for line in out.splitlines()))


def test_render_retrieval_includes_header(r: TestRunner) -> None:
    hits = [{"session_id": "s", "score": 0.9, "branch": "b", "summary": "x"}]
    r.test(
        "markdown header present",
        memory.render_retrieval(hits).startswith("### Similar prior sessions"),
    )


def test_recent_commit_subjects_string_or_empty(r: TestRunner) -> None:
    out = memory._recent_commit_subjects(limit=2)
    r.test("returns a string", isinstance(out, str))


# ---------- write_retrieval_json round-trip (Qdrant-gated) ----------


def test_write_retrieval_json_writes_file_with_empty_hits_on_no_collection(
    r: TestRunner,
) -> None:
    if not _HAS_QDRANT:
        return r.skip("write_retrieval_json no-collection fail-open", "qdrant-client not installed")
    retrieval._reset_client_for_tests()
    embedder._model = _FakeModel()
    client = retrieval._get_client()
    if client.collection_exists(retrieval.COLLECTION):
        client.delete_collection(retrieval.COLLECTION)
    try:
        with tempfile.TemporaryDirectory() as td:
            out = memory.write_retrieval_json(
                "feat/foo", "anything", out_dir=Path(td)
            )
            r.test("returns dict with empty hits", out.get("hits") == [])
            written = Path(td) / "retrieval-feat-foo.json"
            r.test("JSON file written", written.exists())
            data = json.loads(written.read_text())
            r.test("file content matches return value", data.get("hits") == [])
    finally:
        _teardown()


def test_write_retrieval_json_round_trip(r: TestRunner) -> None:
    if not _HAS_QDRANT:
        return r.skip("write_retrieval_json round-trip", "qdrant-client not installed")
    _setup()
    try:
        retrieval.upsert_session(
            "sess_alpha",
            "Refactored auth middleware to drop token storage",
            {"project": "demo", "branch": "feat/auth"},
        )
        retrieval.upsert_session(
            "sess_beta",
            "Wrote tests for rate limiter",
            {"project": "demo", "branch": "feat/limits"},
        )
        with tempfile.TemporaryDirectory() as td:
            out = memory.write_retrieval_json(
                "refactor/step-14", "auth middleware refactor",
                top_k=2, out_dir=Path(td),
            )
            r.test("hits returned", len(out.get("hits", [])) == 2)
            r.test("query echoed in payload", out.get("query") == "auth middleware refactor")
            written = Path(td) / "retrieval-refactor-step-14.json"
            r.test("filename sanitized (slashes → dashes)", written.exists())
            data = json.loads(written.read_text())
            r.test("file content has hits", len(data["hits"]) == 2)
    finally:
        _teardown()


def test_write_retrieval_json_timeout_returns_empty(r: TestRunner) -> None:
    if not _HAS_QDRANT:
        return r.skip("write_retrieval_json timeout", "qdrant-client not installed")
    _setup()
    try:
        original = retrieval.query_sessions

        def slow_query(query, top_k=3):
            time.sleep(2.0)
            return original(query, top_k=top_k)

        retrieval.query_sessions = slow_query  # type: ignore[assignment]
        try:
            with tempfile.TemporaryDirectory() as td:
                start = time.time()
                out = memory.write_retrieval_json(
                    "feat/slow", "anything", timeout_s=0.5, out_dir=Path(td)
                )
                elapsed = time.time() - start
                r.test("timeout enforced (elapsed < 1.5s)", elapsed < 1.5)
                r.test("hits empty on timeout", out.get("hits") == [])
                r.test("error recorded in payload", "error" in out)
        finally:
            retrieval.query_sessions = original  # type: ignore[assignment]
    finally:
        _teardown()


def main() -> int:
    print("Running memory tests...")
    if not _HAS_QDRANT:
        print("(qdrant-client not installed — round-trip tests will skip)")
    r = TestRunner()

    test_branch_to_filename_sanitizes_slashes(r)
    test_branch_to_filename_collapses_runs(r)
    test_branch_to_filename_strips_trailing_dashes(r)
    test_branch_to_filename_handles_empty(r)
    test_render_retrieval_empty_returns_empty_string(r)
    test_render_retrieval_filters_by_min_score(r)
    test_render_retrieval_all_below_threshold_returns_empty(r)
    test_render_retrieval_truncates_to_max_hits(r)
    test_render_retrieval_one_line_summary(r)
    test_render_retrieval_truncates_long_summary(r)
    test_render_retrieval_includes_header(r)
    test_recent_commit_subjects_string_or_empty(r)

    test_write_retrieval_json_writes_file_with_empty_hits_on_no_collection(r)
    test_write_retrieval_json_round_trip(r)
    test_write_retrieval_json_timeout_returns_empty(r)

    return r.summary()


if __name__ == "__main__":
    sys.exit(main())
