"""Two-tier prompt loader: Langfuse first, file fallback.

Step 12. Reads prompts from Langfuse Prompt Management when LANGFUSE_*
env vars are set and the SDK can construct a client; otherwise falls
back to bundled `.txt` files in the sibling `prompts/` directory.

Design notes:

    No `lru_cache` (deliberate deviation from the original Step 12 plan):
    process-lifetime caching would defeat Langfuse's own ~60s TTL
    refresh, breaking the rollback story (label switch in the Langfuse
    UI takes effect within the TTL). Langfuse's client already caches
    `get_prompt` results internally; our wrapper stays thin.

    Lazy singleton client: the Langfuse client is constructed at most
    once per process — on the first `load_prompt` call that finds the
    LANGFUSE_* env vars set. If keys are not yet present (e.g. dotenv
    hasn't run), the client stays unattempted so a later call can still
    succeed. Once an attempt has been made (success OR ImportError OR
    constructor exception), the result sticks until process exit.

Public API: `load_prompt(name, label="production") -> str`.

Filesystem layout:
    hooks/lib/llm/prompts.py         (this module)
    hooks/lib/llm/prompts/           (bundled .txt files, no __init__.py)
        code-reviewer.txt
        review-aggregator.txt
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

_FILE_ROOT = Path(__file__).parent / "prompts"

_client: Any | None = None
_client_attempted: bool = False


def _get_langfuse_client() -> Any | None:
    """Return a Langfuse client singleton, or None if unavailable.

    Resolution order, short-circuiting on the first miss:
      1. LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY must be set.
         If not, return None *without* marking the attempt — a later
         call (after dotenv runs) can still succeed.
      2. `from langfuse import Langfuse` must succeed.
      3. `Langfuse()` constructor must not raise.

    Steps 2 and 3 are one-shot: once attempted, the result is cached
    for the rest of the process. Steps 1 is re-checked every call.
    """
    global _client, _client_attempted
    if _client_attempted:
        return _client
    if not (os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY")):
        return None
    try:
        from langfuse import Langfuse
        _client = Langfuse()
    except ImportError:
        _client = None
    except Exception:  # noqa: BLE001 — fail-open: any constructor failure disables.
        _client = None
    _client_attempted = True
    return _client


def load_prompt(name: str, label: str = "production") -> str:
    """Return the raw prompt text for `name`.

    Tries Langfuse first when the client resolves; falls back to
    `prompts/<name>.txt` on any failure (Langfuse not configured,
    network error, name not in the registry).

    Raises:
        FileNotFoundError: if Langfuse is unavailable AND no bundled
            `.txt` file exists for `name`.
    """
    client = _get_langfuse_client()
    if client is not None:
        try:
            return client.get_prompt(name, label=label).prompt
        except Exception:  # noqa: BLE001 — any Langfuse failure falls through.
            pass
    return (_FILE_ROOT / f"{name}.txt").read_text()


__all__ = ["load_prompt"]
