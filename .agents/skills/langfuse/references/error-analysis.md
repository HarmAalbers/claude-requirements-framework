---
name: langfuse-error-analysis
description: Deep-dive error analysis of an LLM pipeline or AI application using Langfuse traces.
  Use this skill whenever the user wants to understand why their AI system is producing
  bad outputs, where their pipeline is failing, how to categorise or label failures,
  what to prioritise fixing, or how to set up evaluators. Also trigger for "review my
  traces", "my outputs look wrong", "help me debug my LLM app", "I want to analyse
  errors", "build a failure taxonomy", "what's going wrong with my pipeline", or any
  request to systematically inspect, annotate, or score Langfuse traces. If the user
  is trying to understand or improve the quality of an AI system's outputs, use this skill.
---

# Error Analysis

## Project Context

The traces to analyse come from **`/v3-review`** runs: each review worker produces a `claude_agent_sdk.query` span (OpenInference + OTLP). Trace-level `input`/`output` is often **null** — the prompt/completion content lives on the GENERATION observation, so annotation queues must target `objectType: OBSERVATION` (see below). Existing eval scores on these traces: `finding_match` (deterministic, 0–1) and `agent_goal_accuracy` (LLM judge, 0–1) — check them before building a new taxonomy; they may already split pass/fail for you. Golden cases live in `golden_set/cases/*.json` and replay via `scripts/run_eval.py`.

## Primary Guide

**1. Fetch the guide in this blogpost**

https://langfuse.com/guides/cookbook/error-analysis-llm-applications.md

If fetch is not available query for langfuse.com error analysis guide

Read it in full. It defines the authoritative 5-step process (sample selection → open coding → clustering → labelling → deciding what to fix).

**2. Guide the user through this step by step**

You as a coding agent and the user go through this together to perform a full error analysis with their data in langfuse. Do everything you can achieve via CLI (look up traces, create annotation queues, ...) for the user. Provide them with direct links to UI wherever their action is required. Be proactive and narrate what is going on for the user. 

## Rules CRITICAL
Use Langfuse CLI wherever possible
Use charts where possible to display data

---

## Langfuse Implementation Notes

The guide describes the process. These notes cover the Langfuse-specific API and CLI mechanics required to execute it.

### Credentials

Source from `infra/.env` (this project stores `LANGFUSE_HOST`, the CLI wants `LANGFUSE_BASE_URL`). Check existence only — never print the keys:

```bash
set -a; source infra/.env; set +a
export LANGFUSE_BASE_URL="$LANGFUSE_HOST"   # http://localhost:3000
```

```bash
AUTH=$(echo -n "${LANGFUSE_PUBLIC_KEY}:${LANGFUSE_SECRET_KEY}" | base64)

# Verify before proceeding
STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
  -H "Authorization: Basic $AUTH" \
  "${LANGFUSE_BASE_URL}/api/public/projects")
echo "Auth check: $STATUS"
```

If status is not `200`, the docker stack is probably down — check `docker compose -f infra/docker-compose.yml ps` before suspecting credentials.

### Annotation target: OBSERVATION versus TRACE

> **CRITICAL:** In OpenTelemetry-instrumented apps, trace-level `input`/`output` can be null — content often lives in a GENERATION observation. Always consider if the right objectType to add is `objectType: OBSERVATION` pointing to the GENERATION observation ID to annotation queues. 

### Annotation queues

> **CRITICAL:** Queues cannot be updated or deleted after creation. Create score configs first, then the queue with all config IDs. To add new configs later, create a new queue.


**Always give the user a direct link immediately after creating a queue:**

```
http://localhost:3000/project/<projectId>/annotation-queues/<queueId>
```

Instruction to give: *"Please open code the first ~50 examples. For each trace, write what you observe in the `open_coding` field (describe behaviour, don't diagnose root causes), then set `pass_fail_assessment` to Pass or Fail."*


### Prompt fixes

When a category warrants a prompt fix, follow this project's **file-first** workflow: edit the source template in `hooks/lib/llm/prompts/*.md.j2`, then push to the registry with `python3 scripts/sync_prompts_to_langfuse.py` (see `references/prompt-migration.md`). Do NOT create/edit prompts directly in the Langfuse UI — the files are the source of truth and a sync would overwrite UI-only changes.

### Setup evaluators

When a category warrants an evaluator setup, propose the type of evaluator and offer to set it up for user via CLI


### Common gotchas

| Mistake | Fix |
|---------|-----|
| `objectType: TRACE` in queue | Use `objectType: OBSERVATION` with GENERATION obs ID |
| Creating score config without checking existing | `GET /api/public/score-configs` first; can't delete |
| Queue created before score configs | Create configs → collect IDs → create queue |
| `--limit` > 100 on traces list | API hard cap; paginate with `--page` |
| No rate limiting on queue item creation | `sleep 0.4` between calls to avoid 429 |
