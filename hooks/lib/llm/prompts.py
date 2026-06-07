"""Two-tier prompt loader: Langfuse first, file fallback, Jinja2 rendered.

Step 12 (loader) + Step 16 (Jinja2 rendering). Reads prompts from Langfuse
Prompt Management when LANGFUSE_* env vars are set and the SDK can construct
a client; otherwise falls back to bundled `.md.j2` files in the sibling
`prompts/` directory. Either way, the raw text is rendered through
`hooks.lib.llm.templates.render()` with the caller-supplied vars before
being returned.

Design notes:

    No `lru_cache` (deliberate deviation from the original Step 12 plan):
    process-lifetime caching would defeat Langfuse's own ~60s TTL refresh,
    breaking the rollback story. Langfuse's client already caches
    `get_prompt` results internally; our wrapper stays thin.

    Lazy singleton client: constructed at most once per process — on the
    first `load_prompt` call that finds the LANGFUSE_* env vars set. If
    keys are not yet present (e.g. dotenv hasn't run), the client stays
    unattempted so a later call can still succeed.

    `label` is a reserved kwarg, NOT a template variable. Callers wanting
    to override the Langfuse version label pass `label="staging"`;
    everything else in **vars goes to the Jinja2 renderer.

    File extension is `.md.j2` (was `.txt` pre-Step-16). Bundled files are
    the fallback when Langfuse is unreachable; they are also the source of
    truth for `scripts/sync_prompts.py`'s mirror to the Langfuse registry.

Public API: `load_prompt(name, *, label="production", **vars) -> str`.

Filesystem layout:
    hooks/lib/llm/prompts.py         (this module)
    hooks/lib/llm/prompts/           (bundled templates, no __init__.py)
        code-reviewer.md.j2
        review-aggregator.md.j2
        req-supervisor.md.j2
        partials/
            safety.j2
            project_conventions.j2
"""

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
    for the rest of the process. Step 1 is re-checked every call.
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


def _fetch_raw(name: str, label: str) -> str:
    """Fetch the raw template text for `name`. Langfuse first, file fallback.

    Raises:
        FileNotFoundError: if Langfuse is unavailable AND no bundled
            `.md.j2` file exists for `name`.
    """
    client = _get_langfuse_client()
    if client is not None:
        try:
            return client.get_prompt(name, label=label).prompt
        except Exception:  # noqa: BLE001 — any Langfuse failure falls through.
            pass
    return (_FILE_ROOT / f"{name}.md.j2").read_text()


def load_prompt(name: str, *, label: str = "production", **vars: Any) -> str:
    """Fetch a prompt by `name` and Jinja2-render it with `vars`.

    Args:
        name: Prompt name. Resolves to `prompts/<name>.md.j2` when the file
            fallback fires; in Langfuse it's the prompt identifier.
        label: Langfuse version label. RESERVED kwarg — not a template
            variable. Defaults to "production".
        **vars: Passed to `templates.render()` as Jinja2 variables.

    Raises:
        FileNotFoundError: Langfuse unavailable and no bundled file.
        jinja2.UndefinedError: a template variable was referenced but not
            supplied (StrictUndefined contract from Step 16).
    """
    raw = _fetch_raw(name, label)
    # Import locally so test suites can monkey-patch `templates.render` if
    # they want to bypass Jinja2 (e.g., to test the fetch tier in isolation).
    from hooks.lib.llm.templates import render
    return render(raw, **vars)


__all__ = ["load_prompt"]
