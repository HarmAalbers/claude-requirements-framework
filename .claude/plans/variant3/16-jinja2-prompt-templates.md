# Step 16 — Jinja2 prompt templates (phase 1: engine + V3 prompts + render plumbing)

> **Rewritten 2026-05-23.** Original plan named `tool-validator` as a target;
> that worker doesn't exist. Real V3 prompts are `code-reviewer`,
> `review-aggregator`, `req-supervisor`.
>
> **Scope is phased**. This document covers Step 16 only. Sibling plans:
> - `16b-jinja2-plugin-agents.md` — the 25 plugin agents (future)
> - `16c-jinja2-plugin-commands-skills.md` — 11 commands + 21 skills (future)
>
> Step 16 establishes the **engine + render plumbing** that 16b/16c will
> consume. Without it, plugin migration has no build pipeline.

## Goal

Replace Python `str.format()`-style prompt rendering with Jinja2 for the
three V3 worker prompts. Stand up partials authored with **plugin reuse in
mind** (Step 16b/16c will pull from the same `partials/` library). Teach
`sync.sh deploy` to render `.md.j2` → `.md` before copying plugin files, so
Step 16b's first plugin migration has a working build pipeline waiting.

## Why now

Step 14's retrieval and Step 15's eval are in place; Step 18 supervisor
expansion and Step 20 (Sonnet pinning eval iteration) both benefit from
template-based prompts. Equally important: the framework has **60 prompt-like
files** (3 V3 workers + 25 plugin agents + 11 commands + 21 skills) with
substantial duplicated safety / convention / vocabulary text. Migrating in
three phases (16 → 16b → 16c) lets us dogfood partial design before
committing the larger plugin surfaces to whatever vocabulary turns out wrong.

## Scope decisions (locked 2026-05-23)

| Question | Decision |
| --- | --- |
| Migration scope (this step) | **3 V3 worker prompts** (`code-reviewer`, `review-aggregator`, `req-supervisor`) → `.md.j2`. Plugin agents/commands/skills migrate in 16b/16c. |
| Template richness | **Plumbing + partials.** Convert like-for-like (same vars, same rendered output), add `partials/safety.j2` + `partials/project_conventions.j2`. **No `{% if retrieved %}` slot** — workers don't read `retrieval.json` yet. |
| Loader API | **Replace.** `load_prompt(name, **vars)` renders internally. Workers stop calling `.format()`. Matches `[[feedback-no-backwards-compat]]`. |
| Undefined strategy | **`StrictUndefined`** — missing vars raise `UndefinedError`. Optional sections use `{% if var is defined and var %}`. |
| File extension | `.md.j2` for sources. **Rendered `.md` siblings committed** (marketplace distribution constraint — `/plugin install` reads `.md` directly). |
| Render pipeline | New `scripts/render_prompts.py` renders all `.md.j2` in a tree to `.md` siblings. **`sync.sh deploy` invokes it** before copying plugin files. (Same script will run as a pre-commit hook in Step 16b.) |
| Custom Jinja2 filters | `repr` — needed because `code-reviewer.txt:11` uses Python's `{scope!r}`. Resist adding more filters reflexively. |
| Langfuse mirror | Update `scripts/sync_prompts.py` (from Step 12) to glob `*.md.j2`. Templates stored as opaque Jinja2 text per the [Langfuse FAQ-blessed external-templating pattern](https://langfuse.com/faq/all/using-external-templating-libraries). |
| Marketplace distribution | **Rendered `.md` siblings committed alongside `.md.j2` source.** `.claude-plugin/marketplace.json:source` points at `./plugins/requirements-framework` — users get whatever's in git. |
| Branching | Stack on `refactor/step-08-llm-package-scaffold`. Continues the 13/14/15 pattern. |

## Research grounding (referenced from Step 15→16 handoff)

- [Langfuse FAQ: external templating libraries](https://langfuse.com/faq/all/using-external-templating-libraries) — official maintainer-blessed pattern. Store `.md.j2` as opaque text in Langfuse, render client-side.
- [Discussion #4315](https://github.com/orgs/langfuse/discussions/4315) — Langfuse's caching rationale for refusing native Jinja2 server-side rendering. Confirms our approach aligns with maintainer intent.
- [Issue #1912 — CLOSED 2024-05-14](https://github.com/langfuse/langfuse/issues/1912) — Jinja2 formatting bug. Only affected `get_langchain_prompt()`; we use raw `prompt.prompt`. Not a concern for us.
- [Towards AI (Dec 2025): Prompt Management Using Jinja](https://medium.com/@arunabh223/prompt-management-using-jinja-aab5d634d9e2) — community walkthrough validating the same approach in production.

## Files touched (Step 16 only — see 16b/16c for plugin file lists)

| File | Action |
| --- | --- |
| `hooks/lib/llm/templates.py` | populated — Jinja2 Environment + `render(text, **vars)` + `repr` filter |
| `tests/test_templates.py` | **new** — env + render + StrictUndefined + partials + repr filter |
| `hooks/lib/llm/prompts.py` | rewrite — `load_prompt(name, **vars)` fetches raw text + renders; glob switches to `*.md.j2` |
| `hooks/lib/llm/prompts/code-reviewer.md.j2` | **new** (was `.txt`) |
| `hooks/lib/llm/prompts/review-aggregator.md.j2` | **new** (was `.txt`) |
| `hooks/lib/llm/prompts/req-supervisor.md.j2` | **new** (was `.txt`) |
| `hooks/lib/llm/prompts/{code-reviewer,review-aggregator,req-supervisor}.txt` | **deleted** |
| `hooks/lib/llm/prompts/partials/safety.j2` | **new** — review safety rules (designed for plugin agent reuse in 16b) |
| `hooks/lib/llm/prompts/partials/project_conventions.j2` | **new** — pulls CLAUDE.md head if present |
| `hooks/lib/llm/workers/code_reviewer.py` | edit — pass vars to `load_prompt`, drop `.format()` |
| `hooks/lib/llm/workers/aggregator.py` | edit — same |
| `hooks/lib/llm/supervisor.py` | edit — same |
| `tests/test_code_reviewer_worker.py`, `tests/test_aggregator.py`, `tests/test_supervisor.py` | edit — new signature |
| `scripts/render_prompts.py` | **new** — recursive Jinja2 renderer for `.md.j2` → `.md` siblings; invokable as script or imported by sync.sh / pre-commit |
| `sync.sh` | edit — invoke `render_prompts.py` before copying plugin files. No-op when no `.md.j2` files exist (Step 16 has zero plugin `.md.j2` files; the render call is plumbing for Step 16b's first user) |
| `scripts/sync_prompts.py` | edit (from Step 12) — glob `*.md.j2`; docstring note on Langfuse Playground limitation |
| `hooks/lib/llm/_spikes/v3_jinja2_smoke.py` | **new** — loud-fail end-to-end (no LLM calls) |
| `pyproject.toml` | **no change** — `jinja2>=3.0` already in `[llm]` extras |
| `plugins/requirements-framework/.claude-plugin/plugin.json` | bump 4.3.0 → 4.4.0 |
| `CHANGELOG.md` | append v4.4.0 entry |

## Patch breakdown (8 patches)

1. **`step-16-plan-rewrite`** — this document.
2. **`step-16-templates-module`** — Jinja2 environment + `render()` + tests.
3. **`step-16-partials`** — author the 2 partials. Designed for plugin agent reuse (no V3-specific assumptions).
4. **`step-16-convert-v3-and-rewire`** — convert 3 prompts + replace `load_prompt` signature + update 3 workers + adjust worker tests. Single atomic patch (tightly coupled).
5. **`step-16-render-script-and-sync`** — new `scripts/render_prompts.py` + `sync.sh deploy` hook. Render is a no-op for Step 16 (no plugin `.md.j2` exist yet); plumbing for 16b.
6. **`step-16-langfuse-mirror`** — update `scripts/sync_prompts.py` for `.md.j2` extension.
7. **`step-16-smoke`** — `_spikes/v3_jinja2_smoke.py` loud-fail end-to-end.
8. **`step-16-housekeeping`** — plugin 4.3.0 → 4.4.0, CHANGELOG v4.4.0, memory status (explicit pointer to Step 16b/16c).

## Validated APIs

```python
# templates.py
from jinja2 import Environment, FileSystemLoader, StrictUndefined

_ENV = Environment(
    loader=FileSystemLoader(Path(__file__).parent / "prompts"),
    autoescape=False,
    keep_trailing_newline=True,
    undefined=StrictUndefined,
)
_ENV.filters["repr"] = repr

def render(text: str, **vars: Any) -> str:
    return _ENV.from_string(text).render(**vars)
```

```python
# prompts.py (rewritten)
def load_prompt(name: str, **vars: Any) -> str:
    client = _get_langfuse_client()
    raw = None
    if client is not None:
        try:
            raw = client.get_prompt(name, label="production").prompt
        except Exception:
            pass
    if raw is None:
        raw = (_FILE_ROOT / f"{name}.md.j2").read_text()
    from hooks.lib.llm.templates import render
    return render(raw, **vars)
```

```python
# worker migration example
# before:
prompt = load_prompt("code-reviewer").format(diff=diff, scope=scope)
# after:
prompt = load_prompt("code-reviewer", diff=diff, scope=scope)
```

## Acceptance

- [ ] `tests/test_templates.py` passes (env + render + StrictUndefined + partials)
- [ ] Existing tests pass with new `.md.j2` extension + new loader signature
- [ ] `python3 hooks/lib/llm/_spikes/v3_jinja2_smoke.py` passes (no LLM calls)
- [ ] `scripts/render_prompts.py --dry-run` runs cleanly (no plugin `.md.j2` files yet, so dry-run output is empty)
- [ ] `sync.sh deploy` invokes the render script before copying — verified by adding a `set -x` line temporarily during smoke verification
- [ ] StrictUndefined raises on missing var (acceptance test in smoke spike)
- [ ] All three workers (code_reviewer, aggregator, supervisor) compile + run

## Rollback

Each patch atomic via `stg pop`. Most-reversible single change: keep `.md.j2`
files but flip `Environment(undefined=)` from `StrictUndefined` to default
to silence missing-var errors without touching prompt bodies.

## Effort

~1 day for Step 16 (this session). Step 16b is the larger surface; expect
2-3 days when authored.

## Depends on

- Step 12 (PromptLoader two-tier pattern — extended, not replaced)
- Step 14 NOT required as a blocker (no retrieval slot yet)

## Honest scope notes

- **Render plumbing has no consumer in Step 16.** Patch 5's `sync.sh` render
  hook is dead-code-eligible until Step 16b's first plugin `.md.j2` lands.
  We're landing it now so Step 16b is purely content migration, not
  infrastructure + content. The dead-code window is one session at most.
- **Partials are designed for plugin reuse.** `partials/safety.j2` covers
  review safety rules in language general enough that the 25 plugin review
  agents (Step 16b) can include it. If we authored partials narrowly for V3
  workers only, we'd have to rewrite them when 16b lands.
- **Langfuse Playground compatibility loss is documented and accepted.** The
  moment we add a `{% if %}` to a stored template, the Playground can't
  auto-render. Trade-off accepted; we'll keep simple-substitution prompts
  mustache-compatible where the Playground UX still matters (if any).
- **`StrictUndefined` is opinionated.** Optional sections become
  `{% if x is defined and x %}` — verbose. Revisit if it produces too many
  false positives during prompt iteration.
- **`get_langchain_prompt()` collision edge case.** If a future patch wires
  LangChain into the prompt loader, the Issue #1912 fix heuristic
  distinguishes Langfuse vars from Jinja2 by alphanumeric-only check —
  simple Jinja2 vars like `{{ scope }}` would collide. Our `prompt.prompt`
  path doesn't hit this, but the next person reaching for
  `get_langchain_prompt` needs to know.
- **Custom filter maintenance tax.** Adding `repr` for one prompt is fine;
  every additional filter is one more thing the next author has to learn.
