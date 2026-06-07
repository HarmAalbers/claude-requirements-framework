# Langfuse CLI Reference

Documentation: https://langfuse.com/docs/api-and-data-platform/features/cli

## Project Context

Target instance: **self-hosted at `http://localhost:3000`** (docker stack in `infra/`). If calls fail to connect, check `docker compose -f infra/docker-compose.yml ps` first.

## Install

```bash
# Run directly (recommended)
npx langfuse-cli api <resource> <action>
bunx langfuse-cli api <resource> <action>

# Or install globally
npm i -g langfuse-cli
langfuse api <resource> <action>
```

## Discovery

```bash
# List all resources and auth info
langfuse api __schema

# List actions for a resource
langfuse api <resource> --help

# Show args/options for a specific action
langfuse api <resource> <action> --help

# Preview the curl command without executing
langfuse api <resource> <action> --curl
```

## Credentials

Source from `infra/.env` (gitignored) — never paste or print key values. The CLI expects `LANGFUSE_BASE_URL`; this project stores `LANGFUSE_HOST`:

```bash
set -a; source infra/.env; set +a
export LANGFUSE_BASE_URL="$LANGFUSE_HOST"   # http://localhost:3000
```

## Tips

- Use `--json` for machine-readable JSON output
- Use `--curl` to preview the HTTP request without executing
- All list commands support filtering — check `<resource> <action> --help` for available options
- Prefer `observations` over `legacy-observations-v1s` — `observations` is the modern high-performance endpoint (cursor pagination, selective field groups); `legacy-observations-v1s` is the deprecated v1
- Prefer `metrics` over `legacy-metrics-v1s` for the same reason
- Prefer `scores` over `legacy-score-v1s` for list/get operations
- For broad trace queries, prefer `observations list` (with `--trace-id` if you're traversing from a known trace) over `traces list`. See the [Observations API docs](https://langfuse.com/docs/api-and-data-platform/features/observations-api) for the v1 → v2 mapping.
- Pagination: legacy v1 endpoints use `--limit` and `--page`; modern endpoints (`observations`, `metrics`, `scores`) use cursor-based pagination — pass `--limit`, then thread `meta.cursor` from the response into the next request's `--cursor`
- `/v3-review` traces appear as `claude_agent_sdk.query` spans (one per review worker). Trace-level input/output may be null — content lives on the GENERATION observation (OTel-ingested traces).
