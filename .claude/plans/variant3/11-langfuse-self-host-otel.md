# Step 11 — Self-host Langfuse + OpenInference instrumentation

## Goal

Stand up a local Langfuse instance and wire the OpenInference Claude Agent SDK instrumentor. Every Claude call from V3 code is traced. No behavior change for users.

## Why now

We have one Instructor-wrapped agent (Step 10). Instrumenting it gives us our first end-to-end trace. Better to validate the trace path on one agent before scaling out.

## Files touched

- `infra/docker-compose.yml` (new) — Langfuse + Postgres
- `infra/.env.example` (new) — Langfuse keys placeholders
- `hooks/lib/llm/observability.py` (populated)
- `hooks/lib/llm/__init__.py` — call `_init_observability()` on import (guarded)
- `README.md` — add "Local observability" section

## Validated APIs (from [Langfuse Claude Agent SDK docs](https://github.com/langfuse/langfuse-docs/blob/main/content/integrations/frameworks/claude-agent-sdk.mdx))

```python
%pip install langfuse claude-agent-sdk openinference-instrumentation-claude-agent-sdk -q
```

```python
from openinference.instrumentation.claude_agent_sdk import ClaudeAgentSDKInstrumentor
ClaudeAgentSDKInstrumentor().instrument()
```

The instrumentor automatically captures spans for `PreToolUse`, `PostToolUse`, `PostToolUseFailure` events from Claude Agent SDK ([Phoenix integration page](https://arize.com/docs/phoenix/integrations/python/claude-agent-sdk)).

The `@observe()` decorator (from `langfuse.decorators`) wraps arbitrary functions — useful when calling Claude through Instructor (which uses the Anthropic SDK, not the Agent SDK directly). For full coverage we also install `openinference-instrumentation-anthropic`.

## Implementation

### Docker compose
```yaml
# infra/docker-compose.yml
services:
  langfuse-db:
    image: postgres:16
    environment:
      POSTGRES_USER: langfuse
      POSTGRES_PASSWORD: langfuse
      POSTGRES_DB: langfuse
    volumes:
      - langfuse-db-data:/var/lib/postgresql/data

  langfuse:
    image: langfuse/langfuse:3
    depends_on: [langfuse-db]
    environment:
      DATABASE_URL: postgresql://langfuse:langfuse@langfuse-db:5432/langfuse
      NEXTAUTH_SECRET: change-me-locally
      SALT: change-me-locally
      NEXTAUTH_URL: http://localhost:3000
      TELEMETRY_ENABLED: "false"
    ports: ["3000:3000"]

volumes:
  langfuse-db-data:
```

### Python wiring
```python
# hooks/lib/llm/observability.py
import os
from openinference.instrumentation.claude_agent_sdk import ClaudeAgentSDKInstrumentor
from openinference.instrumentation.anthropic import AnthropicInstrumentor

_initialized = False

def init_observability() -> None:
    global _initialized
    if _initialized:
        return
    if not os.getenv("LANGFUSE_PUBLIC_KEY"):
        return  # silently skip if not configured
    ClaudeAgentSDKInstrumentor().instrument()
    AnthropicInstrumentor().instrument()   # also captures Instructor calls
    _initialized = True
```

```python
# hooks/lib/llm/__init__.py
from .observability import init_observability
init_observability()  # idempotent; no-op if not configured
```

## Example: verifying a trace

After `docker compose up -d` and setting `LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY` env vars:

```python
from hooks.lib.llm.workers.code_reviewer import review
report = review("@@ -1,3 +1,3 @@\n-print('hi')\n+os.system(input())\n")
# Open http://localhost:3000 → traces tab → see the call with prompt + response
```

## Acceptance

- [ ] `docker compose up -d` from `infra/` starts Langfuse on localhost:3000
- [ ] Logging in to Langfuse UI succeeds (set up a local user once)
- [ ] After running the Step 10 wrapper, a trace appears in Langfuse with model, tokens, cost
- [ ] If `LANGFUSE_PUBLIC_KEY` is unset, `init_observability` returns silently — no errors
- [ ] No existing tests fail

## Rollback

```bash
docker compose -f infra/docker-compose.yml down -v
git revert <commit>
```

## Effort

1 day

## Depends on

Step 10 (the first traced call).

## Honest scope notes

- Langfuse uses a Postgres backend. Keep the data volume — it accumulates traces over weeks.
- Run `docker compose pull` periodically to receive Langfuse updates.
- For team use later: switch from local Langfuse to Langfuse Cloud or a shared instance — same Python code.
