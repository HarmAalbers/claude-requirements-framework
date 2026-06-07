---
name: langfuse-prompt-migration
description: Work with this project's Langfuse prompt registry — add/edit prompts via the file-first sync workflow. Migration of existing prompts is DONE; the generic migration flow below applies only to newly discovered hardcoded prompts.
---

# Prompt Registry (this project) & Migration

## Project Convention — read this first

**The migration already happened.** All review prompts live as Jinja2 templates in `hooks/lib/llm/prompts/*.md.j2` (plus `partials/`), mirrored to Langfuse by `scripts/sync_prompts_to_langfuse.py`, and loaded at runtime by `hooks/lib/llm/prompts.py`.

This project **deliberately chose Option B** from the decision tree below: prompts are stored in Langfuse as **opaque raw Jinja2 text** (type `text`, label `production`) and compiled **client-side** via `templates.render()` — NOT converted to Langfuse's `{{var}}` mustache syntax. The generic guidance below that says "you MUST convert to `{{var}}`" does **not** apply here. Known trade-off, accepted: no Playground preview / in-UI experiments without SDK-side compile.

Two more load-bearing facts:

- **`keep_trailing_newline` is active and load-bearing** in the Jinja2 renderer (`from_string()` path) — removing it would silently strip trailing newlines from all rendered templates.
- **Files are the source of truth.** Never create or edit prompts in the Langfuse UI — the next sync overwrites them.

### Adding or editing a prompt

1. Create/edit `hooks/lib/llm/prompts/<name>.md.j2` (shared fragments go in `partials/`).
2. Preview the sync: `python3 scripts/sync_prompts_to_langfuse.py --dry-run`
3. Push: `python3 scripts/sync_prompts_to_langfuse.py` — identical content is skipped via a **client-side compare** (Langfuse does NOT dedup server-side; verified 2026-06-07, it mints identical new versions). Changed/missing content creates a new version and moves the `production` label; `--label` for a different label.
4. Drift gate: `python3 scripts/sync_prompts_to_langfuse.py --check` exits 1 if any local file differs from the registry. A stale registry silently serves old prompts at runtime (the loader prefers Langfuse over bundled files), so check after editing templates.
5. Runtime pickup: `load_prompt(name, label="production", **vars)` tries Langfuse first (~60s client cache, no local LRU — deliberate, preserves the rollback story), falls back to the bundled file. `label` is a **reserved kwarg**, not a template variable.
6. Remember the dual-copy rule for the loader code itself: `hooks/lib/llm/prompts.py` and `plugins/requirements-framework/hooks/lib/llm/prompts.py` are identical copies.

### Rollback

Move the `production` label to an older version in Langfuse (UI or API) — the ~60s cache means it takes effect within a minute, no deploy needed. For a durable rollback, also revert the `.md.j2` file and re-sync.

### Credentials

Source `infra/.env` (the sync script and loader read `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` / `LANGFUSE_HOST`). Check existence only — never print secret values.

---

## Generic Migration Flow (only for newly discovered hardcoded prompts)

```
1. Scan codebase for prompts
2. Analyze templating compatibility
3. Propose structure (names, subprompts, variables)
4. User approves
5. Create prompts in Langfuse
6. Refactor code to use get_prompt()
7. Link prompts to traces (if tracing enabled)
8. Verify application works
```

## Step 1: Find Prompts and Build an Inventory

Before writing ANY code, make a complete list of every prompt you found. For each one, note:

- Name: descriptive, lowercase, hyphenated (e.g. chat-assistant, email-classifier)
- Source file: where the prompt text lives
- Code file to refactor: the Python/JS file that USES the prompt (for asset files like .txt/.yaml/.md, this is the file that reads/loads the asset — NOT the asset file itself)
- Type: chat (used as a message in a chat API) or text (used as a plain string)
- Variables: values interpolated into the prompt, converted to {{var}} syntax:
f-string {var} → {{var}}
.format(var=...) → {{var}}
${var} → {{var}}
String concatenation + var + → {{var}}
YAML {var} → {{var}}
- Prompt content: the actual text to upload, with variables converted to {{var}} syntax

Search for these patterns:

| Framework | Look for |
|-----------|----------|
| OpenAI | `messages=[{"role": "system", "content": "..."}]` |
| Anthropic | `system="..."` |
| LangChain | `ChatPromptTemplate`, `SystemMessage` |
| Vercel AI | `system: "..."`, `prompt: "..."` |
| Raw | Multi-line strings near LLM calls |

## Step 2: Check Templating Compatibility

**CRITICAL:** Langfuse only supports simple `{{variable}}` substitution natively. No conditionals, loops, or filters. **This project bypasses native substitution entirely (Option B, see Project Convention above)** — for new prompts in *this* repo, write Jinja2 and let the sync script + client-side renderer handle it; skip the conversion table below.

| Template Feature | Langfuse Native | Action |
|------------------|-----------------|--------|
| `{{variable}}` | ✅ | Direct migration |
| `{var}` / `${var}` | ⚠️ | Convert to `{{var}}` |
| `{% if %}` / `{% for %}` | ❌ | Move logic to code |
| `{{ var \| filter }}` | ❌ | Apply filter in code |

**CRITICAL — Variable syntax:** Langfuse uses DOUBLE curly braces for variables: `{{var}}`. When uploading prompt content, you MUST convert every single-brace `{var}` from the original code to double-brace `{{var}}`. Never upload `{var}` — it must be `{{var}}`.

### Decision Tree

```
Contains {% if %}, {% for %}, or filters?
├─ No → Direct migration
└─ Yes → Choose:
    ├─ Option A: Move logic to code, pass pre-computed values
    └─ Option B (THIS PROJECT'S CHOICE): Store raw template, compile client-side with Jinja2
        └─ ⚠️ Loses: Playground preview, UI experiments — accepted trade-off here
```

### Simplifying Complex Templates

**Conditionals** → Pre-compute in code:
```python
# Instead of {% if user.is_premium %}...{% endif %} in prompt
# Use {{tier_message}} and compute value in code before compile()
```

**Loops** → Pre-format in code:
```python
# Instead of {% for tool in tools %}...{% endfor %} in prompt
# Use {{tools_list}} and format the list in code before compile()
```

For external templating details, fetch: https://langfuse.com/faq/all/using-external-templating-libraries

## Step 3: Propose Structure

### Naming Conventions

| Rule | Example | Bad |
|------|---------|-----|
| Lowercase, hyphenated | `chat-assistant` | `ChatAssistant_v2` |
| Feature-based | `document-summarizer` | `prompt1` |
| Hierarchical for related | `support/triage` | `supportTriage` |
| Prefix subprompts with `_` | `_base-personality` | `shared-personality` |

### Identify Subprompts

Extract when:
- Same text in 2+ prompts
- Represents distinct component (personality, safety rules, format)
- Would need to change together

### Variable Extraction

| Make Variable | Keep Hardcoded |
|---------------|----------------|
| User-specific (`{{user_name}}`) | Output format instructions |
| Dynamic content (`{{context}}`) | Safety guardrails |
| Per-request (`{{query}}`) | Persona/personality |
| Environment-specific (`{{company_name}}`) | Static examples |

## Step 4: Present Plan to User

Format:
```
Found N prompts across M files:

src/chat.py:
  - System prompt (47 lines) → 'chat-assistant'

src/support/triage.py:
  - Triage prompt (34 lines) → 'support/triage'
    ⚠️ Contains {% if %} - will simplify

Subprompts to extract:
  - '_base-personality' - used by: chat-assistant, support/triage

Variables to add:
  - {{user_name}} - hardcoded in 2 prompts

Proceed?
```

## Step 5: Create Prompts in Langfuse

**In this repo**: drop the template into `hooks/lib/llm/prompts/<name>.md.j2` and run the sync script (see Project Convention) — don't call `create_prompt()` ad hoc. The generic API, for reference:

Use `langfuse.create_prompt()` with:
- `name`: Your chosen name
- `prompt`: Template text (or message array for chat type)
- `type`: `"text"` or `"chat"`
- `labels`: `["production"]` (they're already live)
- `config`: Optional model settings

**Labeling strategy:**
- `production` → All migrated prompts
- `staging` → Add later for testing
- `latest` → Auto-applied by Langfuse

For full API: fetch https://langfuse.com/docs/prompts/get-started

## Step 6: Refactor Code

**In this repo**: replace hardcoded prompts with the existing loader — `load_prompt("name", **vars)` from `hooks/lib/llm/prompts.py` (handles Langfuse fetch, file fallback, and Jinja2 render). The generic SDK pattern, for reference:

```python
prompt = langfuse.get_prompt("name", label="production")
messages = prompt.compile(var1=value1, var2=value2)
```

**Key points:**
- Always use `label="production"` (not `latest`) for stability
- Call `.compile()` to substitute variables
- For chat prompts, result is message array ready for API

For SDK examples (Python/JS/TS): fetch https://langfuse.com/docs/prompts/get-started

## Step 7: Link Prompts to Traces

If codebase uses Langfuse tracing, link prompts so you can see which version produced each response.

### Detect Existing Tracing

Look for:
- `@observe()` decorators
- `langfuse.trace()` calls
- `from langfuse.openai import openai` (instrumented client)

### Link Methods

| Setup | How to Link |
|-------|-------------|
| `@observe()` decorator | `langfuse_context.update_current_observation(prompt=prompt)` |
| Manual tracing | `trace.generation(prompt=prompt, ...)` |
| OpenAI integration | `openai.chat.completions.create(..., langfuse_prompt=prompt)` |

### Verify in UI

1. Go to **Traces** → select a trace
2. Click on **Generation**
3. Check **Prompt** field shows name and version

For tracing details: fetch https://langfuse.com/docs/prompts/get-started#link-with-langfuse-tracing

## Step 8: Verify Migration

### Checklist

- [ ] All prompts created with `production` label
- [ ] Code fetches with `label="production"`
- [ ] Variables compile without errors
- [ ] Subprompts resolve correctly
- [ ] Application behavior unchanged
- [ ] Generations show linked prompt in UI (if tracing)

### Common Issues

| Issue | Solution |
|-------|----------|
| `PromptNotFoundError` | Check name spelling |
| Variables not replaced | Use `{{var}}` not `{var}`, call `.compile()` |
| Subprompt not resolved | Must exist with same label |
| Old prompt cached | Restart app |

## Out of Scope

- Prompt engineering (writing better prompts)
- Evaluation setup
- A/B testing workflow
- Non-LLM string templates
