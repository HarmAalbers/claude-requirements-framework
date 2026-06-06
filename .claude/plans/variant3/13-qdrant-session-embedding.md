# Step 13 — Qdrant local + session embedding (write + minimal query)

> **Rewritten 2026-05-23** for the ADR-016 substrate. The original Step 13 (OpenAI
> `text-embedding-3-small` + `instructor.from_anthropic`) is non-viable under
> Max-only auth and was marked "SUPERSEDED IN PART." This document replaces it.
>
> **Landed 2026-05-23** as 8 stacked stg patches on
> `refactor/step-08-llm-package-scaffold`:
> `step-13-{plan-rewrite, infra, embedder, retrieval, summarizer,
>   session-end-write, smoke, housekeeping}`. Plugin bumped to 4.1.0.
> Verification: live smoke against Qdrant v1.15.0 + real
> `BAAI/bge-small-en-v1.5` model ranked the auth-themed fixture first
> (score 0.696) for an auth-themed query, ahead of docs (0.591) and
> perf (0.566).

## Goal

Stand up a local Qdrant instance and a local embedding pipeline. On `SessionEnd`,
summarize the session via the Claude Agent SDK (Haiku), embed the summary with
`sentence-transformers`, and upsert a point to the `sessions` collection. Also
expose a thin `query_sessions(query, top_k)` so the round-trip is provably
working — but **do not** wire SessionStart retrieval injection (that's Step 14).

## Why now

After Step 18 (supervisor) landed, the obvious next missing ingredient is *real
context*. The supervisor currently only sees `derive_phase` output; it cannot
reason about past sessions because none are recorded. Step 13 fills the write
side. Step 14 (LlamaIndex Memory blocks) reads it back in a structured way.

## Scope decisions (locked 2026-05-23)

| Question | Decision |
| --- | --- |
| Round-trip scope | **Write + minimal query API** — `upsert_session` + `query_sessions`. No SessionStart injection. |
| Summarization | **Haiku via `hooks.lib.llm.claude.query`** so budget tracker sees the spend. |
| Branching | **Stack on `refactor/step-08-llm-package-scaffold`** as stg patches (continues the pattern). |
| Model load lifecycle | **Lazy on first `embed()` call, process-singleton**. Hooks are short-lived; pay the 1.5s cold start in SessionEnd, not in every hook spawn. |
| Test strategy | **In-memory `QdrantClient(":memory:")` + mocked embedder**. Real `sentence-transformers` only in the smoke spike. |
| Default flag | **`hooks.qdrant.enabled = false`**. Dogfood locally first, flip default later. |

## Files touched

| File | Action |
| --- | --- |
| `infra/docker-compose.qdrant.yml` | **new** — separate compose file (don't touch the Langfuse-pinned `infra/docker-compose.yml`) |
| `scripts/bootstrap_qdrant.py` | **new** — idempotent collection creation |
| `hooks/lib/llm/embedder.py` | **new** — `embed(text) -> list[float]` with singleton model load |
| `hooks/lib/llm/retrieval.py` | populated — `upsert_session`, `query_sessions`, fail-open |
| `hooks/lib/llm/summarizer.py` | **new** — `summarize_session(transcript_tail) -> str` via SDK Haiku |
| `hooks/handle-session-end.py` | append block "5. Qdrant session embedding" guarded by feature flag |
| `hooks/lib/llm/_spikes/v3_qdrant_smoke.py` | **new** — hard-fail smoke per `feedback-loud-smoke-spikes` |
| `tests/test_embedder.py`, `tests/test_retrieval.py`, `tests/test_summarizer.py` | **new** — using the project's `TestRunner` pattern |
| `examples/global-requirements.yaml` | append `hooks.qdrant` block (commented-out template) |
| `pyproject.toml` | **no change** — `qdrant-client>=1.12` and `sentence-transformers>=3.0` are already in `[llm]` extras |
| `plugins/requirements-framework/.claude-plugin/plugin.json` | bump 4.0.0 → 4.1.0 (minor: new feature) |

## Validated APIs

### Qdrant (in-memory and HTTP modes share the same surface)

```python
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

# Production: HTTP to local Docker
client = QdrantClient(host="localhost", port=6333)

# Tests: in-memory, zero deps
client = QdrantClient(":memory:")

client.create_collection(
    collection_name="sessions",
    vectors_config=VectorParams(size=384, distance=Distance.COSINE),
)

client.upsert(
    collection_name="sessions",
    points=[PointStruct(id="session_abc", vector=vec_384,
                        payload={"project": "...", "summary": "...", "branch": "...", "ended": "..."})],
)

hits = client.query_points(collection_name="sessions", query=vec_384, limit=3).points
```

### sentence-transformers (BAAI/bge-small-en-v1.5, 384-dim)

```python
from sentence_transformers import SentenceTransformer
_model = None
def _get_model():
    global _model
    if _model is None:
        _model = SentenceTransformer("BAAI/bge-small-en-v1.5")
    return _model

def embed(text: str) -> list[float]:
    return _get_model().encode(text, normalize_embeddings=True).tolist()
```

`normalize_embeddings=True` matters: combined with `Distance.COSINE` it makes
similarity scores live in `[0, 1]` instead of arbitrary cosine units.

### Claude Agent SDK Haiku summarization

```python
from hooks.lib.llm.claude import query, ClaudeAgentOptions
from pydantic import BaseModel

class Summary(BaseModel):
    text: str  # <= 300 chars

async def summarize_session(transcript_tail: str) -> str:
    opts = ClaudeAgentOptions(
        model="claude-haiku-4-5",
        output_format={"type": "json_schema", "schema": Summary.model_json_schema()},
        allowed_tools=[],  # pure text-in, JSON-out
    )
    async for msg in query(prompt=f"Summarize this Claude Code session in <=300 chars, focus on what was changed and why:\n\n{transcript_tail}", options=opts):
        if hasattr(msg, "subtype") and msg.subtype == "success":
            return Summary.model_validate_json(msg.result).text
    return ""  # fail-open: empty summary still allows the embed
```

## Implementation sketches

### `infra/docker-compose.qdrant.yml`

```yaml
# Local Qdrant for Step 13 session retrieval (V3).
# Kept separate from infra/docker-compose.yml because that file is a vendored
# Langfuse upstream pin marked "Do NOT edit by hand."
services:
  qdrant:
    image: qdrant/qdrant:v1.12.0
    container_name: qdrant
    ports:
      - "127.0.0.1:6333:6333"   # REST + dashboard
      - "127.0.0.1:6334:6334"   # gRPC
    volumes:
      - qdrant-data:/qdrant/storage
    restart: unless-stopped

volumes:
  qdrant-data:
```

### `scripts/bootstrap_qdrant.py`

```python
#!/usr/bin/env python3
"""Idempotent Qdrant collection bootstrap for Step 13."""
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

EMBED_DIM = 384  # BAAI/bge-small-en-v1.5

def main() -> int:
    c = QdrantClient(host="localhost", port=6333)
    for name in ("sessions",):
        if c.collection_exists(name):
            print(f"exists: {name}")
            continue
        c.create_collection(name, vectors_config=VectorParams(size=EMBED_DIM, distance=Distance.COSINE))
        print(f"created: {name} (dim={EMBED_DIM}, cosine)")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
```

### `hooks/lib/llm/retrieval.py`

```python
"""Qdrant-backed session store. Step 13 — write + minimal query."""
from __future__ import annotations
import os
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct
from hooks.lib.llm.embedder import embed

_client: QdrantClient | None = None

def _get_client() -> QdrantClient:
    global _client
    if _client is None:
        _client = QdrantClient(
            host=os.getenv("QDRANT_HOST", "localhost"),
            port=int(os.getenv("QDRANT_PORT", "6333")),
        )
    return _client

def upsert_session(session_id: str, summary: str, payload: dict) -> bool:
    """Embed `summary` and upsert one point. Returns True on success, False on any failure (fail-open)."""
    try:
        vec = embed(summary)
        _get_client().upsert(
            collection_name="sessions",
            points=[PointStruct(id=session_id, vector=vec,
                                payload={**payload, "summary": summary})],
        )
        return True
    except Exception:
        return False  # caller logs at debug; SessionEnd hook must not break

def query_sessions(query: str, top_k: int = 3) -> list[dict]:
    """Return list of {id, score, ...payload}. Empty list on any failure."""
    try:
        vec = embed(query)
        hits = _get_client().query_points(collection_name="sessions", query=vec, limit=top_k).points
        return [{"id": h.id, "score": h.score, **(h.payload or {})} for h in hits]
    except Exception:
        return []
```

### `hooks/handle-session-end.py` — block 5

```python
# 5. Qdrant session embedding (Step 13)
try:
    qdrant_enabled = config and config.get_hook_config('qdrant', 'enabled', False)
    if qdrant_enabled:
        transcript_path = input_data.get('transcript_path')
        if transcript_path and Path(transcript_path).is_file():
            import asyncio
            from hooks.lib.llm.summarizer import summarize_session
            from hooks.lib.llm.retrieval import upsert_session

            tail = Path(transcript_path).read_text()[-15000:]
            summary = asyncio.run(summarize_session(tail))
            if summary:
                ok = upsert_session(
                    session_id=session_id,
                    summary=summary,
                    payload={"project": str(project_dir), "branch": branch,
                             "ended_at": int(time.time()), "reason": reason},
                )
                logger.debug("Qdrant session upsert", ok=ok)
except Exception as e:
    logger.debug("Qdrant session embedding failed (fail-open)", error=str(e))
```

### `examples/global-requirements.yaml` addition

```yaml
hooks:
  qdrant:
    enabled: false              # Step 13 — flip to true after `bootstrap_qdrant.py`
    # host: "localhost"         # override via env QDRANT_HOST
    # port: 6333                # override via env QDRANT_PORT
    # collection: "sessions"    # fixed for now
```

## Acceptance

- [ ] `docker compose -f infra/docker-compose.qdrant.yml up -d` succeeds on Apple Silicon (image is `linux/arm64`-compatible)
- [ ] `python3 scripts/bootstrap_qdrant.py` creates the `sessions` collection on a fresh volume; rerunning prints `exists: sessions` (idempotent)
- [ ] `tests/test_embedder.py` passes with mocked `SentenceTransformer` (no model download in CI)
- [ ] `tests/test_retrieval.py` passes against `QdrantClient(":memory:")` with deterministic 384-dim fake vectors
- [ ] `tests/test_summarizer.py` passes with mocked `claude.query` (no real SDK call)
- [ ] Ending a Claude Code session with `hooks.qdrant.enabled: true` writes a point to `sessions` collection (visible at `http://localhost:6333/dashboard`)
- [ ] If Qdrant is down OR `[llm]` extras missing, SessionEnd logs at debug and does NOT block (fail-open verified by killing the container mid-session)
- [ ] The smoke spike `_spikes/v3_qdrant_smoke.py` hard-fails (non-zero exit, loud stderr) when Qdrant unreachable or extras missing (per `feedback-loud-smoke-spikes`)
- [ ] Full test suite (`python3 hooks/test_requirements.py` + `python3 tests/test_*.py`) stays green
- [ ] Plugin bumped to 4.1.0
- [ ] `refactor-current-status` memory updated

## Rollback

```bash
docker compose -f infra/docker-compose.qdrant.yml down -v   # nukes data volume
# In .claude/requirements.yaml:
hooks:
  qdrant:
    enabled: false
```

The retrieval module never imports `sentence-transformers` at module-import
time, only inside `_get_model()`. So setting the flag to false also avoids any
model load.

## Rejected alternatives

- **Embed at SessionEnd, store on disk, async-flush to Qdrant later.** Too clever
  for v0. SessionEnd already runs after the user has moved on; a synchronous
  1.5s + Haiku call is fine.
- **Use Qdrant's `local mode` (file-backed) instead of HTTP/Docker.** Tempting
  for single-user, but blocks any future multi-process access (e.g. a future
  CLI tool that reads recent sessions while a session is ending).
- **Embed raw transcript tail (no LLM summary).** Considered, rejected: raw
  tool-call noise produces noisy embeddings, weakening retrieval quality. Cost
  delta is ~$0.001/session for the Haiku call.
- **Use `BAAI/bge-m3` (1024-dim, multilingual).** Overkill for English-only
  software-engineering sessions. `bge-small-en-v1.5` is 33MB vs ~2GB and benches
  competitively on STS tasks. Easy to swap later by changing `EMBED_DIM` + recreating the collection.

## Effort

~1 day end-to-end across 7 stg patches:

1. `step-13-infra` — compose file + bootstrap script
2. `step-13-embedder` — embedder module + tests
3. `step-13-retrieval` — retrieval module + tests
4. `step-13-summarizer` — summarizer module + tests
5. `step-13-session-end-write` — SessionEnd hook block 5
6. `step-13-smoke` — `_spikes/v3_qdrant_smoke.py`
7. `step-13-housekeeping` — plugin bump, status memory update, examples yaml

## Depends on

- Step 08 (LLM package scaffold) ✅
- Step 11 (observability) ✅ — Haiku summarization calls go through `claude.query` and will be traced
- Step 12 (prompt loader) ✅ — optional; the summarization prompt is short enough to inline for now
- Step 17a (budget tracker) ✅ — Haiku summarization spend goes into the monthly ledger

## Unblocks

- Step 14 (LlamaIndex Memory blocks) — the read side. Composes Static + FactExtraction + Vector blocks against the `sessions` collection.
- Step 18 (deferred Markdown `/req` replacement) — once retrieval lands, the supervisor gets reasoning context that `derive_phase` cannot produce, at which point replacing the Markdown table with `await supervisor.route()` becomes worth doing.

## Honest scope notes

- The Qdrant dashboard at `http://localhost:6333/dashboard` is a great smoke surface — open it during the first dogfood session.
- Cold-start cost (measured during the 2026-05-23 live smoke on a fresh cache): **~25 seconds** for the very first run including the 33MB model download from HF Hub. Subsequent runs hit `~/.cache/huggingface/` and complete in ~1.5s. Plan an extra ~25s for the first hook-triggered embed after deployment to a fresh machine; thereafter the cost is negligible.
- **Version-pin follow-up**: `qdrant-client>=1.12` resolves to a 1.18+ wheel today, while the compose image pin is `qdrant/qdrant:v1.15.0`. That's still a 3-minor-version gap and the client emits a warning on every call. The smoke works regardless, but a future patch should bump the server image to align (target: same minor or +/- 1). Tracked because pinning carelessly to `:latest` would re-introduce reproducibility issues.
- The `summarize_session` call adds one Haiku invocation per session end. Cost: ~$0.001 per session (300 chars in + 100 chars out). Budget tracker captures it automatically via the `claude.query` wrapper.
- No PII masking. Per project memory `[[project-no-pii-masking]]`: self-hosted, single-user, out of scope.
- The `payload` dict is intentionally small (project, branch, ended_at, reason, summary). Step 14 will add structured fields (satisfied requirements, commit shas) once the read side knows what it wants to filter on.
