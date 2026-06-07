---
name: langfuse
description: Interact with this project's self-hosted Langfuse instance and access Langfuse documentation. Use when needing to (1) query or modify Langfuse data via the CLI — traces, prompts, scores, sessions, and any other API resource, (2) work on the V3 observability stack (observability.py, prompts.py, eval.py, sync script), or (3) look up Langfuse documentation, concepts, or SDK usage. Tailored to claude-requirements-framework's self-hosted deployment.
allowed-tools:
  - WebFetch(domain:langfuse.com)
  - Bash(curl *langfuse.com/*)
  - Bash(npx langfuse-cli api __schema *)
  - Bash(npx langfuse-cli api * --help *)
  - Bash(npx langfuse-cli api * list *)
  - Bash(npx langfuse-cli api * get *)
  - Bash(bunx langfuse-cli api __schema *)
  - Bash(bunx langfuse-cli api * --help *)
  - Bash(bunx langfuse-cli api * list *)
  - Bash(bunx langfuse-cli api * get *)
---

# Langfuse (project-tailored)

This skill covers Langfuse work in **claude-requirements-framework**: the self-hosted instance, the V3 review observability stack, prompt registry, eval scoring, and Langfuse documentation access.

## This Project's Langfuse Setup

**Deployment**: Self-hosted Langfuse v3 via `infra/docker-compose.yml` (langfuse-web on `http://localhost:3000`, plus worker, postgres, clickhouse, minio, redis — all localhost-bound). Version-pinned; minimum v3.22.0 for OTLP ingestion.

**Credentials**: Live in `infra/.env` (gitignored; `infra/.env.example` documents the variable names). The project uses `LANGFUSE_HOST` (e.g. `http://localhost:3000`), not `LANGFUSE_BASE_URL`. Never print secret values; check existence only.

**Key integration files** (note: `hooks/lib/llm/` and `plugins/requirements-framework/hooks/lib/llm/` hold *identical copies* — edits must land in both):

| File | Role |
|------|------|
| `hooks/lib/llm/observability.py` | OpenInference Claude Agent SDK instrumentor + OTLP exporter. Lazy init, fail-open, idempotent. |
| `hooks/lib/llm/prompts.py` | Two-tier prompt loader: Langfuse `get_prompt()` first, bundled `.md.j2` fallback. Client-side Jinja2 render. |
| `hooks/lib/llm/eval.py` | Eval metrics (`finding_match`, `agent_goal_accuracy`) + `post_to_langfuse()` score posting. |
| `hooks/lib/llm/review_cli.py` | `/v3-review` orchestrator — loads dotenv, arms observability *before* SDK import, fans out workers. |
| `scripts/sync_prompts_to_langfuse.py` | Mirrors `hooks/lib/llm/prompts/*.md.j2` → Langfuse registry (`production` label). |
| `scripts/run_eval.py` | Replays `golden_set/cases/*.json`, scores, optionally posts to Langfuse. |
| `tests/test_observability.py`, `tests/test_eval.py`, `tests/test_prompts.py` | Dep-free unit tests for the above. |

**SDK**: `langfuse>=3.0` (Python v3 idioms: `create_score()`, `get_prompt()`, `create_prompt()`). See `references/sdk-upgrade.md` before any v4 migration.

**Project rules** (non-negotiable):

1. **Never launch `/v3-review` via the Bash tool** — hand it to the user to run via `!` so it executes in their session.
2. **Fail-open in library code** — Langfuse errors must never block the framework. But **smoke/spike scripts hard-fail loudly** on missing prereqs (see `hooks/lib/llm/_spikes/v3_langfuse_smoke.py`).
3. **No PII masking instrumentation** — self-hosted, single-user; out of scope by explicit decision.
4. **Prompts are raw Jinja2** stored as opaque text in Langfuse (not mustache-compiled). `keep_trailing_newline` is load-bearing in the renderer.

## Core Principles

1. **Documentation First**: NEVER implement based on memory. Always fetch current docs before writing code (Langfuse updates frequently). See the documentation section below.
2. **CLI for Data Access**: Use `langfuse-cli` when querying/modifying Langfuse data. Source creds from `infra/.env` first — see `references/cli.md`.
3. **Best Practices by Use Case**: Check the relevant reference file below before implementing.
4. **Respect the pinned versions**: the docker-compose stack and `langfuse>=3.0` are pinned deliberately — do not bump either as a side effect of other work.

## Use case specific references

- working on tracing/instrumentation of the V3 review stack: references/instrumentation.md
- adding or editing prompts in the registry (sync script workflow, Jinja2 convention): references/prompt-migration.md
- using the Langfuse CLI against the self-hosted instance: references/cli.md
- upgrading the Python SDK v3 → v4 (future task; concrete touch-list): references/sdk-upgrade.md
- judge calibration for `agent_goal_accuracy` (LLM-as-a-Judge reliability): references/judge-calibration.md
- systematic error analysis of /v3-review traces: references/error-analysis.md

## 1. Langfuse API via CLI

Use the `langfuse-cli` to interact with the full Langfuse REST API from the command line. Run via npx (no install required):

Start by discovering the schema and available arguments:

```bash
# Discover all available resources
npx langfuse-cli api __schema

# List actions for a resource
npx langfuse-cli api <resource> --help

# Show args/options for a specific action
npx langfuse-cli api <resource> <action> --help
```

### Credentials

Source from `infra/.env` and map the host variable (the CLI expects `LANGFUSE_BASE_URL`; this project stores `LANGFUSE_HOST`):

```bash
set -a; source infra/.env; set +a
export LANGFUSE_BASE_URL="$LANGFUSE_HOST"   # http://localhost:3000
```

Verify existence without printing secrets:

```bash
[ -n "$LANGFUSE_PUBLIC_KEY" ] && echo "public key: set" || echo "public key: MISSING"
[ -n "$LANGFUSE_SECRET_KEY" ] && echo "secret key: set" || echo "secret key: MISSING"
echo "base url: $LANGFUSE_BASE_URL"
```

If the instance isn't responding, the docker stack may be down: `docker compose -f infra/docker-compose.yml up -d`.

### Detailed CLI Reference

For common workflows, tips, and full usage patterns, see [references/cli.md](references/cli.md).

## 2. Langfuse Documentation

Three methods to access Langfuse docs, in order of preference. **Always prefer your application's native web fetch and search tools** (e.g., `WebFetch`, `WebSearch`, `mcp_fetch`, etc.) over `curl` when available. The URLs and patterns below work with any fetching method — the `curl` examples are just illustrative.

### 2a. Documentation Index (llms.txt)

Fetch the full index of all documentation pages:

```bash
curl -s https://langfuse.com/llms.txt
```

Returns a structured list of every doc page with titles and URLs. Use this to discover the right page for a topic, then fetch that page directly.

Alternatively, you can start on `https://langfuse.com/docs` and explore the site to find the page you need.

### 2b. Fetch Individual Pages as Markdown

Any page listed in llms.txt can be fetched as markdown by appending `.md` to its path or by using `Accept: text/markdown` in the request headers. Use this when you know which page contains the information needed. Returns clean markdown with code examples and configuration details.

```bash
curl -s "https://langfuse.com/docs/observability/overview.md"
curl -s "https://langfuse.com/docs/observability/overview" -H "Accept: text/markdown"
```

### 2c. Search Documentation

When you need to find information across all docs and github issues/discussions without knowing the specific page:

```bash
curl -s "https://langfuse.com/api/search-docs?query=<url-encoded-query>"
```

Returns a JSON response with `query` and `answer` (matching documents with `url`, `title`, and `source.content` excerpts).

Search is a great fallback if you cannot find the relevant pages or need more context. Especially useful when debugging issues as all GitHub Issues and Discussions are also indexed. Responses can be large — extract only the relevant portions.

**Docs caveat for this project**: docs default to Langfuse Cloud and current SDK versions. This project runs a *pinned self-hosted v3 stack* with the *Python SDK pinned to v3* — cross-check doc snippets against the pinned versions before applying them.

### Documentation Workflow

1. Start with **llms.txt** to orient — scan for relevant page titles
2. **Fetch specific pages** when you identify the right one
3. Fall back to **search** when the topic is unclear and you want more context
