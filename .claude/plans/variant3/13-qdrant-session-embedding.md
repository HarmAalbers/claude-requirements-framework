# Step 13 — Qdrant local + session embedding/persistence

## Goal

Stand up a local Qdrant instance. On SessionEnd, summarize the session, embed the summary, and upsert to Qdrant. No retrieval yet (Step 14 wires it).

## Why now

Need persistence before retrieval. This step is "write only" — sessions accumulate; future steps query against them.

## Files touched

- `infra/docker-compose.yml` — add `qdrant` service
- `hooks/lib/llm/retrieval.py` (populated)
- `hooks/handle-session-end.py` — append the upsert call (guarded by feature flag)
- `scripts/bootstrap_qdrant.py` (new — creates collections)
- `requirements.yaml` — add `hooks.qdrant.enabled` flag (default false)

## Validated APIs (from [Qdrant client docs](https://python-client.qdrant.tech/))

```python
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

client = QdrantClient(host="localhost", port=6333)

# Create collection (once)
client.create_collection(
    collection_name="sessions",
    vectors_config=VectorParams(size=1536, distance=Distance.COSINE),
)

# Upsert
client.upsert(
    collection_name="sessions",
    points=[PointStruct(id="session_abc123", vector=embedding,
                        payload={"project": "...", "summary": "..."})],
)
```

## Implementation

### Compose addition
```yaml
# infra/docker-compose.yml (add)
  qdrant:
    image: qdrant/qdrant:v1.12.0
    ports: ["6333:6333", "6334:6334"]
    volumes:
      - qdrant-data:/qdrant/storage

volumes:
  qdrant-data:
```

### Bootstrap
```python
# scripts/bootstrap_qdrant.py
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

c = QdrantClient(host="localhost", port=6333)
for name, dim in [("sessions", 1536), ("findings", 1536)]:
    if not c.collection_exists(name):
        c.create_collection(name, vectors_config=VectorParams(size=dim, distance=Distance.COSINE))
        print(f"created collection: {name}")
```

### Retrieval module
```python
# hooks/lib/llm/retrieval.py
"""Qdrant-backed session/findings store."""
import os
import uuid
from typing import Sequence
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct

_client = QdrantClient(host=os.getenv("QDRANT_HOST", "localhost"),
                       port=int(os.getenv("QDRANT_PORT", "6333")))

def embed(text: str) -> list[float]:
    """Use OpenAI embeddings; could swap for local bge-m3."""
    import openai
    return openai.embeddings.create(
        model="text-embedding-3-small", input=text
    ).data[0].embedding

def upsert_session(session_id: str, summary: str, payload: dict) -> None:
    vec = embed(summary)
    _client.upsert(
        collection_name="sessions",
        points=[PointStruct(id=session_id, vector=vec,
                            payload={**payload, "summary": summary})],
    )

def query_sessions(query: str, top_k: int = 3) -> list[dict]:
    vec = embed(query)
    hits = _client.query_points(collection_name="sessions", query=vec, limit=top_k).points
    return [{"id": h.id, "score": h.score, **h.payload} for h in hits]
```

### Hook integration
```python
# hooks/handle-session-end.py — add (guarded)
from hooks.lib.config import load_config
cfg = load_config()
if cfg.get("hooks", {}).get("qdrant", {}).get("enabled", False):
    from hooks.lib.llm.retrieval import upsert_session
    summary = summarize_transcript(transcript_path)  # implement; see below
    upsert_session(session_id, summary,
                   payload={"project": project, "branch": branch,
                            "ended": iso_now(), "reason": reason})
```

`summarize_transcript` is a quick Claude call:
```python
def summarize_transcript(path: str) -> str:
    import anthropic, instructor
    from pydantic import BaseModel
    client = instructor.from_anthropic(anthropic.Anthropic())
    class Summary(BaseModel):
        text: str
    raw = Path(path).read_text()
    return client.create(
        model="claude-haiku-4-5", max_tokens=400, response_model=Summary,
        messages=[{"role": "user",
                   "content": f"Summarize this session in <300 chars:\n{raw[-15000:]}"}]
    ).text
```

## Acceptance

- [ ] `docker compose up qdrant` succeeds on Apple Silicon
- [ ] `python scripts/bootstrap_qdrant.py` creates two collections
- [ ] Ending a session writes a point to `sessions` collection (visible at `http://localhost:6333/dashboard`)
- [ ] If Qdrant is down, the hook logs a warning and does not block session end
- [ ] No retrieval is wired yet — that's Step 14

## Rollback

`docker compose stop qdrant && docker compose rm -f qdrant`. Set `qdrant.enabled: false` in config.

## Effort

1 day

## Depends on

Step 08 (deps), Step 11 (observability — not strictly required but trace the summarize call).

## Honest scope notes

- Embedding via OpenAI requires `OPENAI_API_KEY`. For fully offline operation, swap in `llama-index-embeddings-huggingface` with `bge-m3` (also 1024-dim — adjust `VectorParams.size`).
- The Qdrant dashboard at `http://localhost:6333/dashboard` is a great smoke-test surface.
