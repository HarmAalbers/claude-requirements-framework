# Step 16 — Jinja2 prompt templates

## Goal

Move prompts from plain text to Jinja2 templates so retrieval, examples, and project conventions can be slotted in at render time. Refactor the two highest-volume prompts (`code-reviewer`, `tool-validator`) first.

## Why now

We have retrieval (Steps 13–14) but no way to inject the retrieved context into prompts cleanly. Templates make slotting trivial.

## Files touched

- `hooks/lib/llm/prompts/code-reviewer.md.j2` (new — renamed from .txt)
- `hooks/lib/llm/prompts/tool-validator.md.j2` (new)
- `hooks/lib/llm/prompts/partials/safety.j2` (new)
- `hooks/lib/llm/prompts/partials/project_conventions.j2` (new)
- `hooks/lib/llm/templates.py` (populated — Jinja2 environment)
- `hooks/lib/llm/prompts.py` — update `load_prompt` to render

## Validated APIs

Jinja2 (well-known; no validation needed beyond install):

```python
from jinja2 import Environment, FileSystemLoader

env = Environment(loader=FileSystemLoader("hooks/lib/llm/prompts"),
                  autoescape=False, keep_trailing_newline=True)
tmpl = env.get_template("code-reviewer.md.j2")
rendered = tmpl.render(scope=..., retrieved=...)
```

## Implementation

### Templates module
```python
# hooks/lib/llm/templates.py
from jinja2 import Environment, FileSystemLoader, StrictUndefined
from pathlib import Path

_ENV = Environment(
    loader=FileSystemLoader(Path(__file__).parent / "prompts"),
    autoescape=False,
    keep_trailing_newline=True,
    undefined=StrictUndefined,  # fail loudly on missing vars
)

def render(name: str, **vars) -> str:
    return _ENV.get_template(f"{name}.md.j2").render(**vars)
```

### Example template
```jinja
{# hooks/lib/llm/prompts/code-reviewer.md.j2 #}
You are reviewing {{ scope.description }}.

{% include 'partials/safety.j2' %}
{% include 'partials/project_conventions.j2' %}

{% if retrieved %}
## Similar prior findings in this area
{% for hit in retrieved[:3] %}
- {{ hit.summary | truncate(180) }}
{% endfor %}
{% endif %}

{% if examples %}
## Past examples
{% for ex in examples[:2] %}
<example>
Input: {{ ex.input }}
Output: {{ ex.output | tojson }}
</example>
{% endfor %}
{% endif %}

Respond ONLY with a JSON object matching the ReviewReport schema.
Token budget: {{ budget }} input tokens remaining.

---DIFF---
{{ diff }}
```

```jinja
{# partials/safety.j2 #}
- Never report findings about test fixtures or generated code.
- If you cannot verify a line number, set confidence below 0.5.
- Findings without a concrete file path are invalid.
```

```jinja
{# partials/project_conventions.j2 #}
{% if project_conventions %}
## Project conventions
{{ project_conventions }}
{% endif %}
```

### Update PromptLoader
```python
# hooks/lib/llm/prompts.py (modified)
from hooks.lib.llm.templates import render

def load_and_render(name: str, **vars) -> str:
    # If Langfuse has the template (Jinja-typed), use it; else local file
    if _langfuse:
        try:
            p = _langfuse.get_prompt(name, label="production")
            from jinja2 import Template
            return Template(p.prompt).render(**vars)
        except Exception:
            pass
    return render(name, **vars)
```

## Example

```python
from hooks.lib.llm.templates import render

prompt = render(
    "code-reviewer",
    scope={"description": "HEAD..origin/main"},
    retrieved=[{"summary": "Past finding: empty except in auth.py"}],
    examples=[],
    budget=4000,
    project_conventions="No bare excepts. All logs include error IDs.",
    diff="<unified diff text>",
)
```

## Acceptance

- [ ] Template renders for the standard input fixture without raising `UndefinedError`
- [ ] Adding a new partial does not break existing templates
- [ ] `code-reviewer.md.j2` renders to <5000 tokens with typical inputs
- [ ] When `retrieved` is empty, the "Similar prior findings" section is omitted entirely
- [ ] Worker (`code_reviewer.py`) calls `load_and_render(...)` instead of plain `load_prompt(...)`

## Rollback

Switch `load_and_render` to ignore Jinja and always read raw text. Delete templates.

## Effort

1 day

## Depends on

Step 12 (PromptLoader). Step 14 helps but isn't strictly required (retrieval can be empty).

## Honest scope notes

- `StrictUndefined` is opinionated — it forces every template variable to be provided. This catches drift early.
- For Langfuse-hosted Jinja prompts: Langfuse's text-prompt type uses `{{ var }}` substitution but NOT full Jinja2. To get full Jinja2 from Langfuse, store the source and render locally as shown.
