# Step 14 — SessionStart retrieval pipeline (thin read-side over Step 13)

> **Rewritten 2026-05-23** for the ADR-016 substrate. The original Step 14
> (`LlamaIndex Memory blocks` with `OpenAIEmbedding` + direct `Anthropic`) is
> non-viable under Max-only auth and was marked superseded. This document
> replaces it with a minimal read-side that composes over Step 13's
> `query_sessions` API and defers the LlamaIndex `Memory` composition until a
> downstream consumer (worker / supervisor) actually needs a `Memory` object.
>
> Filename kept (`14-llamaindex-memory-blocks.md`) for historical numbering;
> the LlamaIndex composition is scope-deferred, not abandoned.

## Goal

On `SessionStart`, derive a heuristic semantic query from the branch context,
embed it locally, query the Step 13 `sessions` collection, and inject a compact
"Similar prior sessions" block into the existing SessionStart briefing so the
user sees relevant prior work immediately.

## Why now

Step 13 wired the **write side**: every `SessionEnd` summarizes + embeds + upserts
a point. The Qdrant collection has data but nothing reads it back. Step 14
closes the loop: SessionStart pulls top-K matches and surfaces them as
context. Without a consumer, the Step 13 write pipeline is dead weight.

## Scope decisions (locked 2026-05-23)

| Question | Decision |
| --- | --- |
| Scope shape | **Thin SessionStart read-pipeline** — populate `memory.py` with `write_retrieval_json` + `render_retrieval`. Skip LlamaIndex `Memory` composition entirely (no `Memory.from_defaults`, no `FactExtractionMemoryBlock`, no `ClaudeAgentSDKLLM` adapter). |
| First consumer | **SessionStart context injection.** `handle-session-start.py` reads the file it just wrote and prepends a compact "Similar prior sessions" block (≤3 hits, score ≥0.5) to the briefing it already emits. No statusline change in this step. |
| Query construction | **Branch name + last 3 commit subjects** via `git log -3 --format=%s`. Falls back gracefully on empty repo / fresh branch. |
| Latency budget | **Accept cold start, hard timeout 1.5s.** First call pays the ~1–2s sentence-transformers model load (Step 13 reality). Wrap retrieval in a 1.5s timeout — on timeout, write empty hits and continue. Matches Step 13's fail-open posture. |
| Default flag | **`hooks.retrieval.enabled = false`.** Dogfood locally first; flip default in a follow-up once we've validated UX. |
| Branching | **Stack on `refactor/step-08-llm-package-scaffold`** as stg patches (continues the 13-patch pattern). |

## Files touched

| File | Action |
| --- | --- |
| `hooks/lib/llm/memory.py` | populated — `write_retrieval_json`, `render_retrieval`, `_branch_to_filename`, `_recent_commit_subjects` |
| `tests/test_memory.py` | **new** — ~10 tests using the `TestRunner` pattern + `QDRANT_TEST_CLIENT=1` |
| `hooks/handle-session-start.py` | append guarded block that writes retrieval JSON + injects rendered block |
| `hooks/lib/llm/_spikes/v3_retrieval_pipeline_smoke.py` | **new** — hard-fail smoke per `feedback-loud-smoke-spikes` |
| `examples/global-requirements.yaml` | append `hooks.retrieval` block (commented-out template) |
| `plugins/requirements-framework/.claude-plugin/plugin.json` | bump 4.1.0 → 4.2.0 (minor: new SessionStart capability) |
| `CHANGELOG.md` | append v4.2.0 entry |

## Validated APIs (already shipped in Step 13)

```python
from hooks.lib.llm.retrieval import query_sessions

hits = query_sessions(query="auth middleware review", top_k=3)
# -> [{"id": "<uuid>", "score": 0.696, "session_id": "abc12345",
#      "summary": "...", "project": "...", "branch": "...",
#      "ended_at": "2026-05-23T14:00:00Z"}, ...]
```

Step 14 wraps this and adds: JSON persistence, timeout enforcement, markdown
rendering, and the SessionStart hook integration.

## Implementation

### `hooks/lib/llm/memory.py`

```python
"""SessionStart read-pipeline over the Step 13 sessions collection.

Public surface:
    write_retrieval_json(branch, query, top_k=3, timeout_s=1.5) -> dict
        Embed query, fetch top-K hits, write .git/requirements/retrieval-<branch>.json,
        return the dict that was written. Fail-open: returns {"hits": []} on any
        failure (Qdrant down, model missing, timeout, etc.).
    render_retrieval(hits, max_hits=3, min_score=0.5) -> str
        Format hits as a compact markdown block suitable for SessionStart
        injection. Returns empty string if no hits pass the min_score filter.
"""

from __future__ import annotations

import json
import re
import signal
import subprocess
from contextlib import contextmanager
from pathlib import Path
from typing import Any

_BRANCH_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _branch_to_filename(branch: str) -> str:
    """Sanitize branch name for safe filesystem use (slashes → dashes)."""
    return _BRANCH_FILENAME_RE.sub("-", branch).strip("-") or "unknown"


def _recent_commit_subjects(limit: int = 3) -> str:
    """Return space-joined recent commit subjects, empty string on failure."""
    try:
        out = subprocess.check_output(
            ["git", "log", f"-{limit}", "--format=%s"],
            stderr=subprocess.DEVNULL, text=True, timeout=2,
        )
        return " ".join(out.strip().splitlines())
    except Exception:
        return ""


@contextmanager
def _hard_timeout(seconds: float):
    """SIGALRM-based hard timeout. Only works on the main thread of POSIX."""
    def _raise(signum, frame):
        raise TimeoutError(f"exceeded {seconds}s")
    old = signal.signal(signal.SIGALRM, _raise)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old)


def write_retrieval_json(
    branch: str, query: str, top_k: int = 3, timeout_s: float = 1.5,
    out_dir: Path | None = None,
) -> dict:
    out_dir = out_dir or Path(".git/requirements")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"retrieval-{_branch_to_filename(branch)}.json"

    payload: dict[str, Any] = {"query": query, "hits": []}
    try:
        with _hard_timeout(timeout_s):
            from hooks.lib.llm.retrieval import query_sessions
            payload["hits"] = query_sessions(query, top_k=top_k)
    except Exception as exc:
        payload["error"] = str(exc)

    out_path.write_text(json.dumps(payload, indent=2))
    return payload


def render_retrieval(hits: list[dict], max_hits: int = 3, min_score: float = 0.5) -> str:
    kept = [h for h in hits if h.get("score", 0.0) >= min_score][:max_hits]
    if not kept:
        return ""
    lines = ["### Similar prior sessions"]
    for h in kept:
        sid = h.get("session_id", "?")[:8]
        score = h.get("score", 0.0)
        branch = h.get("branch", "?")
        summary = (h.get("summary") or "").strip().split("\n")[0][:160]
        lines.append(f"- `{sid}` ({score:.2f}) on `{branch}` — {summary}")
    return "\n".join(lines) + "\n"
```

### Hook wiring (`hooks/handle-session-start.py`)

```python
# inside the existing SessionStart handler, AFTER briefing is composed:
retr_cfg = config.get_hook_config("retrieval", {}) if config else {}
if retr_cfg.get("enabled", False):
    try:
        from hooks.lib.llm.memory import (
            write_retrieval_json, render_retrieval, _recent_commit_subjects,
        )
        query = f"{branch} {_recent_commit_subjects(3)}".strip()
        payload = write_retrieval_json(branch, query)
        block = render_retrieval(payload.get("hits", []))
        if block:
            briefing = block + "\n" + briefing  # prepend
    except Exception:
        pass  # fail-open
```

## Example

After 50 stored sessions in Qdrant, starting a fresh session on
`refactor/step-14-llamaindex-memory-blocks`:

```bash
$ cat .git/requirements/retrieval-refactor-step-14-llamaindex-memory-blocks.json
{
  "query": "refactor/step-14-llamaindex-memory-blocks feat(step-13): qdrant ...",
  "hits": [
    {"session_id": "abc12345", "score": 0.78, "branch": "refactor/step-13-...",
     "summary": "Stood up Qdrant locally, wired SessionEnd embed pipeline...", ...},
    ...
  ]
}
```

Injected at the top of the SessionStart briefing:

```
### Similar prior sessions
- `abc12345` (0.78) on `refactor/step-13-...` — Stood up Qdrant locally, wired SessionEnd embed pipeline...
- `def67890` (0.62) on `refactor/step-08-...` — Scaffolded the hooks.lib.llm package...
```

## Acceptance

- [ ] `write_retrieval_json` produces a file even when Qdrant is unreachable (empty hits, no exception)
- [ ] `render_retrieval` drops hits with `score < 0.5` and returns empty string if none remain
- [ ] Filename sanitizer handles `refactor/step-14-foo` → `refactor-step-14-foo`
- [ ] SessionStart hook adds < 1.5s when `hooks.retrieval.enabled: true`, < 5ms when disabled
- [ ] After 5 themed sessions, smoke spike's related query returns top hit with score ≥ 0.5 and matches semantically
- [ ] 1325/1325 existing tests still pass; ~10 new tests added under `tests/test_memory.py`

## Rollback

Set `hooks.retrieval.enabled: false`. The hook returns immediately without
touching Qdrant. Existing `retrieval-*.json` files are inert without a consumer.

## Effort

Half a day — most of the surface (`query_sessions`, embedder, fail-open
posture, in-memory Qdrant test mode) already shipped in Step 13.

## Depends on

Step 13 (write pipeline + `query_sessions` API).

## Honest scope notes

- **LlamaIndex `Memory` is deferred, not deleted.** When Step 18's supervisor or
  a future worker actually needs a chat-formatted `Memory` object (rather than a
  rendered string), we'll add `build_memory()` with a `ClaudeAgentSDKLLM`
  adapter and a `LocalSentenceTransformerEmbedding` adapter. Today, neither
  consumer exists.
- **SessionStart query is heuristic.** Branch names are often non-semantic
  (`refactor/step-14-...`); commit subjects carry most of the signal. A future
  iteration can wire `UserPromptSubmit` to re-run retrieval against the actual
  user prompt for sharper hits — left out of scope here to keep Step 14 atomic.
- **Statusline tag deferred.** The original plan referenced
  `[✓ similar #abcd]` in the statusline — that requires touching the Step 03
  statusline pipeline and arguably adds noise. Defer until SessionStart
  injection has been dogfooded.
- **SIGALRM timeout is POSIX-only.** Fine for darwin/linux. If we ever target
  Windows, swap to a thread-based timer. Hooks already assume POSIX in
  several places.
