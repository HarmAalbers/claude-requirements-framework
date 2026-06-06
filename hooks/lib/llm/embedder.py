"""Local text embedding via `sentence-transformers` (Step 13).

Public surface:
    EMBED_DIM            — int, must match Qdrant collection vector size
    MODEL_NAME           — str, the HuggingFace model id
    embed(text) -> list[float]
                          — returns a normalized 384-dim vector. ImportError
                            propagates if the [llm] extra isn't installed
                            (callers in retrieval.py wrap in try/except for
                            fail-open behavior).
    get_model()          — exposes the singleton, mainly so tests can swap
                            it via monkeypatching the module attribute
                            `_model`.

Design notes:

1. **Lazy singleton.** The `SentenceTransformer` constructor downloads ~33MB
   on first invocation (cached at `~/.cache/huggingface/` thereafter) and
   takes ~1.5s to deserialize. Loading at module import would pay that cost
   on every short-lived hook spawn — which the framework spawns a lot.
   Loading on first `embed()` call moves the cost to SessionEnd, where the
   user has already moved on.

2. **`normalize_embeddings=True`.** Combined with Qdrant's `Distance.COSINE`,
   this makes returned similarity scores live in [0, 1] instead of arbitrary
   cosine units. Downstream UIs and threshold tuning become predictable.

3. **Import inside `_get_model()`, not at module top.** Without this, any
   `from hooks.lib.llm import embedder` would fail when the [llm] extra
   isn't installed, breaking the whole `hooks.lib.llm` package. With the
   import deferred, the ImportError surfaces only when something actually
   tries to embed — and `retrieval.py` is fail-open against that.

4. **No async.** sentence-transformers is CPU/MPS-bound, not I/O-bound.
   Wrapping in asyncio.to_thread would only matter if a hot path were to
   embed in parallel with other work — not relevant for SessionEnd's
   one-call-per-session pattern. Add it later if Step 14 needs it.
"""

from __future__ import annotations

from typing import Any

EMBED_DIM = 384
MODEL_NAME = "BAAI/bge-small-en-v1.5"

_model: Any | None = None  # SentenceTransformer | None; typed Any to avoid the import


def _get_model() -> Any:
    """Return the process-singleton SentenceTransformer, loading on first call."""
    global _model
    if _model is None:
        # Deferred import: see design note 3.
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer(MODEL_NAME)
    return _model


def get_model() -> Any:
    """Public accessor for the singleton — tests use this to verify caching."""
    return _get_model()


def embed(text: str) -> list[float]:
    """Embed `text` into a normalized 384-dim float vector.

    Raises ImportError if the [llm] extra isn't installed. Callers that need
    fail-open behavior (e.g. retrieval.upsert_session) should wrap in
    try/except.
    """
    vec = _get_model().encode(text, normalize_embeddings=True)
    # `.encode` returns numpy.ndarray; Qdrant accepts list[float]. .tolist()
    # is the canonical conversion.
    return vec.tolist()
