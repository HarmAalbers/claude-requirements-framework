# Step 14 — LlamaIndex memory blocks

## Goal

Compose LlamaIndex's three memory primitives — `StaticMemoryBlock`, `FactExtractionMemoryBlock`, `VectorMemoryBlock` — over the Qdrant collection from Step 13. Wire the SessionStart hook to fetch top-K similar sessions and write `retrieval.json`.

## Why now

Qdrant has data (Step 13). Now we read from it. This step closes the retrieval loop.

## Files touched

- `hooks/lib/llm/memory.py` (populated)
- `hooks/handle-session-start.py` — extend to write `retrieval.json`
- `tests/test_memory.py` (new)

## Validated APIs (from [LlamaIndex memory docs](https://github.com/run-llama/llama_index/blob/main/docs/examples/memory/memory.ipynb))

> "There are three predefined memory blocks: `StaticMemoryBlock`, `FactExtractionMemoryBlock`, and `VectorMemoryBlock`. `StaticMemoryBlock` stores fixed information, while `FactExtractionMemoryBlock` uses an LLM to extract and summarize facts from chat history. `VectorMemoryBlock` stores and retrieves batches of chat messages using a vector database and embedding model."

```python
from llama_index.core.memory import Memory

memory = Memory.from_defaults(
    session_id="my_session",
    token_limit=30000,
    chat_history_token_ratio=0.02,
    token_flush_size=500,
    memory_blocks=blocks,
    insert_method="user",
)
```

## Implementation

```python
# hooks/lib/llm/memory.py
"""Composed memory: static + fact-extraction + vector."""
from llama_index.core.memory import (
    Memory,
    StaticMemoryBlock,
    FactExtractionMemoryBlock,
    VectorMemoryBlock,
)
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.vector_stores.qdrant import QdrantVectorStore
from llama_index.llms.anthropic import Anthropic
from qdrant_client import QdrantClient

def _project_facts() -> str:
    from pathlib import Path
    claude_md = Path("CLAUDE.md")
    return claude_md.read_text()[:1500] if claude_md.exists() else ""

def build_memory(session_id: str) -> Memory:
    qclient = QdrantClient(host="localhost", port=6333)
    vstore = QdrantVectorStore(client=qclient, collection_name="sessions")
    blocks = [
        StaticMemoryBlock(
            name="project_facts",
            static_content=_project_facts(),
            priority=10,
        ),
        FactExtractionMemoryBlock(
            name="extracted_facts",
            llm=Anthropic(model="claude-haiku-4-5"),
            max_facts=30,
            priority=5,
        ),
        VectorMemoryBlock(
            name="vector_recall",
            vector_store=vstore,
            embed_model=OpenAIEmbedding(model="text-embedding-3-small"),
            retrieval_context_window=5,
            priority=3,
        ),
    ]
    return Memory.from_defaults(
        session_id=session_id,
        token_limit=20000,
        chat_history_token_ratio=0.5,
        memory_blocks=blocks,
        insert_method="user",
    )

def write_retrieval_json(branch: str, query: str) -> None:
    """Lightweight: bypass LlamaIndex; query Qdrant directly for SessionStart."""
    import json
    from pathlib import Path
    from hooks.lib.llm.retrieval import query_sessions
    hits = query_sessions(query, top_k=3)
    Path(f".git/requirements/retrieval-{branch}.json").write_text(
        json.dumps({"hits": hits}, indent=2)
    )
```

### Hook wiring
```python
# hooks/handle-session-start.py — add (guarded)
from hooks.lib.config import load_config
cfg = load_config()
if cfg.get("hooks", {}).get("retrieval", {}).get("enabled", False):
    from hooks.lib.llm.memory import write_retrieval_json
    # We don't have user input yet at SessionStart — use branch name + recent commits as the query
    query = f"{branch} " + _recent_commit_subjects(limit=3)
    try:
        write_retrieval_json(branch, query)
    except Exception as exc:
        # fail-open: log + continue
        print(f"retrieval skipped: {exc}", file=sys.stderr)
```

## Example

After 50 stored sessions in Qdrant, starting a new session on a branch about "review middleware":

```bash
$ cat .git/requirements/retrieval-feat-mw.json
{
  "hits": [
    {"id": "session_1842", "score": 0.91,
     "summary": "Reviewed auth middleware; found 3 silent-failure issues..."},
    {"id": "session_1611", "score": 0.83,
     "summary": "Refactored ASGI middleware ordering after deep-review..."}
  ]
}
```

Statusline (from Step 03) now appends `[✓ similar #1842]`.

## Acceptance

- [ ] `build_memory()` returns a `Memory` instance without error
- [ ] After 5 stored sessions, `write_retrieval_json` produces a non-empty hits list for a related query
- [ ] An unrelated query returns hits below score 0.5 — verify ranking sanity
- [ ] If Qdrant is empty, the file is written with empty hits and the session continues
- [ ] Hook total runtime stays under 1.5s (set `OPENAI_API_KEY` env, embedding call ~500ms)

## Rollback

Set `retrieval.enabled: false`. The retrieval JSON is silently ignored by downstream consumers.

## Effort

1 day

## Depends on

Step 13 (data must be persisting before we read).

## Honest scope notes

- The SessionStart query is heuristic (branch name + recent commits) because we don't yet have the user's first prompt. UserPromptSubmit hook could improve this by re-running retrieval with the actual prompt — added in a future iteration.
- `FactExtractionMemoryBlock` costs Claude tokens. Capped at 30 facts to keep cost predictable.
