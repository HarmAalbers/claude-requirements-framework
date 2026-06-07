---
name: langfuse-observability
description: Work on this project's V3 review tracing (observability.py, OpenInference, OTLP). Use when auditing or extending the existing instrumentation — it is already set up; do not bootstrap a new integration.
---

# Langfuse Observability

Instrumentation guidance for this project's V3 review stack.

## This Project's Instrumentation Architecture

Tracing is **already set up** — do not bootstrap a new integration. The chain:

```
plugins/requirements-framework/scripts/v3-review   (bash wrapper)
  → hooks/lib/llm/review_cli.py
      _load_dotenv()            # pulls LANGFUSE_* from infra/.env
      init_observability()      # arms OpenInference instrumentor BEFORE SDK import
      → query() calls auto-traced as `claude_agent_sdk.query` spans
  → OTLP HTTP/protobuf → http://localhost:3000/api/public/otel/v1/traces
```

Key facts (violating these breaks tracing silently):

- **Import order is load-bearing**: `init_observability()` must run before `claude_agent_sdk` is imported. `hooks/lib/llm/claude.py` is a thin wrapper that guarantees this structurally — import `query` from there, never from the SDK directly.
- **Env contract**: `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST` (read in `observability.py`). All three unset → logged once at INFO, tracing skipped, work continues (fail-open). `LANGFUSE_DEBUG=1` enables init-failure tracebacks.
- **Idempotent late init**: `_instrumented` / `_disabled_logged` are separate flags so dotenv can load after first import and a later explicit `init_observability()` still works.
- **Tracer provider is passed explicitly** to `instrument()` — don't refactor to rely on the OTel global.
- **`_DetachNoiseFilter`**: fan-out under `asyncio.gather()` makes OpenInference log benign "Failed to detach context" errors; the filter suppresses those while keeping genuine context errors. Don't remove it, don't broaden it.
- **Dual copies**: `hooks/lib/llm/observability.py` and `plugins/requirements-framework/hooks/lib/llm/observability.py` are identical copies — edit both.
- **Scope honesty**: only the Claude Agent SDK is instrumented (no Anthropic-SDK child spans for internal retries). Known limitation, revisit if an API-key path appears.
- **Never launch `/v3-review` via the Bash tool** to "test tracing" — hand the command to the user (`!`). For a quick end-to-end check use the smoke spike: `hooks/lib/llm/_spikes/v3_langfuse_smoke.py` (hard-fails on missing prereqs, prints the trace URL).
- **Tests**: `tests/test_observability.py` covers env handling, ImportError swallowing, idempotency, atexit flush. Extend it when touching `observability.py`.

## Workflow (auditing or extending the instrumentation)

### 1. Verify Baseline Requirements

Every trace should have these fundamentals:

| Requirement               | Check                                                                                    | Why                                                    |
| ------------------------- | ---------------------------------------------------------------------------------------- | ------------------------------------------------------ |
| Model name                | Is the LLM model captured?                                                               | Enables model comparison and filtering                 |
| Token usage               | Are input/output tokens tracked?                                                         | Enables automatic cost calculation                     |
| Good trace names          | Are names descriptive? (`chat-response`, not `trace-1`)                                  | Makes traces findable and filterable                   |
| Span hierarchy            | Are multi-step operations nested properly?                                               | Shows which step is slow or failing                    |
| Correct observation types | Are generations marked as generations?                                                   | Enables model-specific analytics                       |
| Trace input/output        | Does the trace capture meaningful input/output? Is input explicitly set to show only relevant data (e.g., user message), not all function args? | Makes traces readable in the UI |

(No PII-masking requirement here: self-hosted, single-user — masking is explicitly out of scope for this project.)

The OpenInference instrumentor handles model name, tokens, and observation types automatically — prefer extending it over adding manual spans.

Docs: https://langfuse.com/docs/tracing

### 2. Explore Traces First

Once baseline instrumentation is working, encourage the user to explore their traces in the Langfuse UI before adding more context:

"Your traces are now appearing in Langfuse. Take a look at a few of them—see what data is being captured, what's useful, and what's missing. This will help us decide what additional context to add."

This helps the user:

- Understand what they're already getting
- Form opinions about what's missing
- Ask better questions about what they need

### 3. Discover Additional Context Needs

Determine what additional instrumentation would be valuable. **Infer from code when possible, only ask when unclear.**

Plausible additions **for this project** (single-user CLI — no `user_id`, tenants, or end-user feedback):

| Addition            | Why                                                              | Docs                                                |
| ------------------- | ---------------------------------------------------------------- | --------------------------------------------------- |
| `session_id`        | Group all worker spans of one `/v3-review` run together          | https://langfuse.com/docs/tracing-features/sessions |
| `agent` tag         | Per-review-agent analytics (code-reviewer, solid-reviewer, ...)  | https://langfuse.com/docs/tracing-features/tags     |
| `branch` metadata   | Correlate traces with the git branch under review                | https://langfuse.com/docs/tracing-features/tags     |
| Eval scores         | Already implemented — `finding_match`, `agent_goal_accuracy` via `eval.py` | https://langfuse.com/docs/scores/overview           |

These are NOT baseline requirements—only add what's relevant, and keep any addition fail-open.

### 4. Guide to UI

After adding context, point users to relevant UI features:

- Traces view: See individual requests
- Sessions view: See grouped conversations (if session_id added)
- Dashboard: Build filtered views using tags
- Scores: Filter by quality metrics

## Common Mistakes

| Mistake                                        | Problem                                             | Fix                                                                               |
| ---------------------------------------------- | --------------------------------------------------- | --------------------------------------------------------------------------------- |
| No `flush()` in scripts                        | Traces never sent                                   | Call `langfuse.flush()` before exit                                               |
| Flat traces                                    | Can't see which step failed                         | Use nested spans for distinct steps                                               |
| Generic trace names                            | Hard to filter                                      | Use descriptive names: `chat-response`, `doc-summary`                             |
| Not explicitly setting input with `@observe`   | All function args become trace input (including API keys, configs) | Python: use `langfuse.update_current_span(input=...)`. Set only the relevant input |
| Manual instrumentation when integration exists | More code, less context                             | Extend the OpenInference instrumentor path instead                                |
| Env vars loaded after `init_observability()`   | Instrumentation arms with missing credentials → silently untraced | `_load_dotenv()` runs first in `review_cli.py`; preserve that order in any new entry point |
| Importing `claude_agent_sdk` directly          | Monkey-patch not yet armed → calls untraced         | Import `query` via `hooks/lib/llm/claude.py` (structural import-order guarantee)  |
| Editing only one copy of `observability.py`    | Repo and plugin behavior diverge silently           | Edit both `hooks/lib/llm/` and `plugins/requirements-framework/hooks/lib/llm/`    |
