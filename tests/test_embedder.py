#!/usr/bin/env python3
"""Test suite for hooks/lib/llm/embedder.py (Step 13).

Follows the framework's TestRunner convention (see tests/test_schemas.py).
Run with: python3 tests/test_embedder.py

The real `sentence-transformers` model is NEVER loaded in unit tests:
    - 33MB download in CI is wasteful
    - 1.5s import cost dominates test runtime
    - The smoke spike (_spikes/v3_qdrant_smoke.py) covers the real-model path

Instead we monkey-patch `embedder._model` with a fake `.encode()` callable
that returns a deterministic 384-element numpy-like list.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import hooks.lib.llm.embedder as embedder


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


class _FakeVector:
    """Mimics numpy.ndarray's .tolist() so embedder.embed() works unchanged."""

    def __init__(self, values: list[float]):
        self._values = values

    def tolist(self) -> list[float]:
        return list(self._values)


class _FakeModel:
    """Stand-in for SentenceTransformer; records calls + returns fixed vector."""

    def __init__(self, dim: int = embedder.EMBED_DIM):
        self.dim = dim
        self.encode_calls: list[tuple[str, bool]] = []

    def encode(self, text: str, normalize_embeddings: bool = False):  # noqa: D401
        self.encode_calls.append((text, normalize_embeddings))
        # Deterministic vector — value depends on text hash so different inputs
        # don't accidentally compare equal.
        seed = sum(ord(c) for c in text) % 100 / 100.0
        return _FakeVector([seed + (i / self.dim) for i in range(self.dim)])


def _install_fake_model(fake: _FakeModel) -> None:
    """Swap the singleton so _get_model() returns the fake instead of loading."""
    embedder._model = fake


def _reset_model() -> None:
    embedder._model = None


# ---------- tests ----------


def test_embed_returns_correct_dim(r: TestRunner) -> None:
    _install_fake_model(_FakeModel())
    try:
        vec = embedder.embed("hello world")
        r.test("embed() returns list[float]", isinstance(vec, list))
        r.test(
            f"embed() returns {embedder.EMBED_DIM}-dim vector",
            len(vec) == embedder.EMBED_DIM,
            f"got len={len(vec)}",
        )
        r.test(
            "embed() values are floats",
            all(isinstance(v, float) for v in vec),
        )
    finally:
        _reset_model()


def test_embed_passes_normalize_true(r: TestRunner) -> None:
    fake = _FakeModel()
    _install_fake_model(fake)
    try:
        embedder.embed("anything")
        r.test(
            "embed() calls encode with normalize_embeddings=True",
            bool(fake.encode_calls) and fake.encode_calls[0][1] is True,
            f"calls={fake.encode_calls}",
        )
    finally:
        _reset_model()


def test_get_model_caches_singleton(r: TestRunner) -> None:
    _reset_model()
    fake = _FakeModel()
    _install_fake_model(fake)
    try:
        m1 = embedder.get_model()
        m2 = embedder.get_model()
        r.test(
            "get_model() returns same instance on repeat calls",
            m1 is m2 is fake,
        )
    finally:
        _reset_model()


def test_embed_deterministic_for_same_input(r: TestRunner) -> None:
    _install_fake_model(_FakeModel())
    try:
        v1 = embedder.embed("identical")
        v2 = embedder.embed("identical")
        r.test("embed() deterministic for same input", v1 == v2)
    finally:
        _reset_model()


def test_embed_differs_for_different_input(r: TestRunner) -> None:
    _install_fake_model(_FakeModel())
    try:
        v1 = embedder.embed("alpha")
        v2 = embedder.embed("bravo")
        r.test("embed() differs for different input", v1 != v2)
    finally:
        _reset_model()


def test_module_constants_match_qdrant_bootstrap(r: TestRunner) -> None:
    # The bootstrap script hard-codes EMBED_DIM=384 — keep them in sync.
    r.test("EMBED_DIM == 384 (must match scripts/bootstrap_qdrant.py)",
           embedder.EMBED_DIM == 384)
    r.test("MODEL_NAME == BAAI/bge-small-en-v1.5",
           embedder.MODEL_NAME == "BAAI/bge-small-en-v1.5")


def main() -> int:
    print("Running embedder tests...")
    r = TestRunner()
    test_embed_returns_correct_dim(r)
    test_embed_passes_normalize_true(r)
    test_get_model_caches_singleton(r)
    test_embed_deterministic_for_same_input(r)
    test_embed_differs_for_different_input(r)
    test_module_constants_match_qdrant_bootstrap(r)
    return r.summary()


if __name__ == "__main__":
    sys.exit(main())
