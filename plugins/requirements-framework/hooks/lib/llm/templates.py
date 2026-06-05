"""Jinja2 prompt template engine for V3 (Step 16).

Public surface:
    render(text, **vars) -> str
        Render a raw template string with vars. Uses the module-level
        Environment so partials authored under `prompts/partials/` can be
        `{% include %}`'d. Raises UndefinedError on missing variables
        (StrictUndefined contract — see design note 2).

    _ENV  (module-private but introspectable)
        The configured Jinja2 Environment. Tests assert its shape;
        application code should not touch it directly.

Design notes:

1. **FileSystemLoader anchored at `hooks/lib/llm/prompts/`.** Templates can
   `{% include 'partials/safety.j2' %}` against that root. Application code
   that uses `render(text, **vars)` passes the text inline, not by name —
   name lookup is the loader's job (see `prompts.py`). The loader still
   matters for resolving `{% include %}` directives at render time.

2. **`StrictUndefined`.** Missing variables raise `UndefinedError` at render
   time, including inside `{% if %}` blocks. Optional sections must use
   `{% if x is defined and x %}`. This is verbose but catches typos and
   schema drift fast — chosen by Step 16 scope decision over the silent
   default-empty behavior.

3. **`autoescape=False`.** Prompts are text content sent to LLMs, not HTML
   rendered in a browser. Auto-escaping `<`, `>`, `&` would corrupt diffs
   and code snippets in template variables.

4. **`keep_trailing_newline=True`.** LLM prompt parsers sometimes treat a
   trailing newline as significant whitespace. Default Jinja2 strips it;
   we preserve.

5. **Custom `repr` filter.** Python's `{scope!r}` (used in
   `code-reviewer.txt` prior to migration) has no direct Jinja2 equivalent.
   Adding `repr` lets the migrated `.md.j2` write `{{ scope | repr }}` and
   render the same single-quoted output. Resist adding more filters
   reflexively; every filter is one more thing the next author must learn.

6. **No `lstrip_blocks` / `trim_blocks`.** Default whitespace handling.
   Could revisit if prompts grow visually noisy from block-tag whitespace,
   but defaults are explicit and predictable.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined

_PROMPTS_ROOT = Path(__file__).parent / "prompts"

_ENV = Environment(
    loader=FileSystemLoader(_PROMPTS_ROOT),
    autoescape=False,
    keep_trailing_newline=True,
    undefined=StrictUndefined,
)
_ENV.filters["repr"] = repr


def render(text: str, **vars: Any) -> str:
    """Render `text` as a Jinja2 template with `vars`.

    Raises:
        UndefinedError: when a referenced variable is not in `vars`.
        TemplateSyntaxError: when the template body is malformed.
        TemplateNotFound: when a `{% include %}` target doesn't exist
            under `_PROMPTS_ROOT`.
    """
    return _ENV.from_string(text).render(**vars)


__all__ = ["render"]
