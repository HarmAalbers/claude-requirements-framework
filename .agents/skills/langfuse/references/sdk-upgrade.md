---
name: langfuse-sdk-upgrade
description: Upgrade this project's Langfuse Python SDK from the pinned v3 to v4. Future task — includes the concrete list of files to touch in this repo.
---

# Langfuse SDK Upgrade Guide (Python v3 → v4, project-specific)

This project pins `langfuse>=3.0` in `pyproject.toml` and uses v3 idioms throughout. This file is the playbook for the eventual v4 migration.

## Migration Docs

Always fetch the latest migration guide before starting — it is the source of truth and may have changed since this file was written:

```bash
curl -s "https://langfuse.com/docs/observability/sdk/upgrade-path/python-v3-to-v4.md"
```

## This Project's Touch-List

Every file that exercises the Langfuse Python SDK. **Remember the dual-copy rule**: `hooks/lib/llm/` and `plugins/requirements-framework/hooks/lib/llm/` hold identical copies — change both.

| File (×2 where noted) | v3 idioms in use | v4 watch-out |
|---|---|---|
| `hooks/lib/llm/prompts.py` (×2) | `Langfuse()` lazy singleton, `get_prompt(name, label=...).prompt` | API surface of prompt client; `.prompt` attribute access on text prompts |
| `hooks/lib/llm/eval.py` (×2) | `client.create_score(trace_id=, name=, value=)` (v3 rename from `.score()` — the fail-open comment documents this) | Score API namespace changes (`score_v_2` → `scores`); metadata must be `dict[str, str]`, values ≤200 chars |
| `scripts/sync_prompts_to_langfuse.py` | `create_prompt(name, type, prompt, labels)`, `flush()` | Same prompt-API surface; verify idempotent-upsert behavior unchanged |
| `scripts/run_eval.py` | drives `post_to_langfuse()` | Indirect — verify after eval.py is migrated |
| `pyproject.toml` | `langfuse>=3.0` pin | Bump to `>=4.0`; v4 requires Pydantic v2 |
| `tests/test_eval.py`, `tests/test_prompts.py` | mock the v3 call shapes | Update mocks to v4 shapes — these tests are what proves the migration |

**NOT affected**: `hooks/lib/llm/observability.py` uses OpenInference + OTel exporters, not the Langfuse SDK — tracing keeps working during the SDK migration. But the **pinned self-hosted server** in `infra/docker-compose.yml` must satisfy the v4 SDK's minimum server version — check the migration guide and bump the stack deliberately (separate patch) if needed.

**Convention guard**: the migration must not break the project's raw-Jinja2 prompt convention (prompts stored as opaque text, client-side render, `keep_trailing_newline`). If v4 changes prompt object semantics, the fallback path in `prompts.py` and the sync script need joint verification.

## Upgrade Checklist

Work through each item in order. Skip items that don't apply.

- [ ] **Update the SDK package** to the latest v4
- [ ] **Audit span filtering**: Non-LLM spans no longer export by default in v4. (Likely moot here — tracing goes through OpenInference, not the Langfuse SDK — but verify nothing started depending on SDK-side spans)
- [ ] **Replace `update_current_trace()`** if any crept in: split into `propagate_attributes()` (correlating attributes), root-observation I/O, and `set_current_trace_as_public()`
- [ ] **Update API namespace references**: `observations_v_2` → `observations`, `score_v_2` → `scores`, `metrics_v_2` → `metrics`. Legacy v1 APIs moved to `api.legacy.*`
- [ ] **Validate metadata format**: must be `dict[str, str]` with values ≤200 characters
- [ ] **Move `release`/`environment`** from code parameters to env vars (`LANGFUSE_RELEASE`, `LANGFUSE_TRACING_ENVIRONMENT`)
- [ ] **Replace `start_span()` / `start_generation()`** with `start_observation()` (`as_type="generation"`)
- [ ] **Replace dataset `item.run()`** with `dataset.run_experiment(name=..., task=...)` — relevant if judge calibration (see `references/judge-calibration.md`) has created Langfuse datasets by then
- [ ] **Pydantic v2** — the v4 SDK requires it; check what else in the repo pins Pydantic
- [ ] **Update removed types**: `TraceMetadata`, `ObservationParams` gone from `langfuse.types`; import `MapValue`, `ModelUsage`, `PromptClient` from `langfuse.model`
- [ ] **Enable debug logging** during migration (`debug=True` / `LANGFUSE_DEBUG`)
- [ ] **Run the test suite** (`tests/test_eval.py`, `tests/test_prompts.py`, `tests/test_observability.py`) and the smoke spike (`hooks/lib/llm/_spikes/v3_langfuse_smoke.py` — user-run, hard-fails loudly) to verify end-to-end

## Common Pitfalls

| Pitfall | Impact | Fix |
| --- | --- | --- |
| Editing only one copy of `prompts.py`/`eval.py` | Repo and plugin diverge silently | Always change both copies |
| Metadata with non-string values | Values silently coerced or dropped | Ensure all metadata values are strings ≤200 characters |
| Fail-open masking a broken migration | `create_score` failures are swallowed by design | Run tests + smoke spike; don't trust silence |
| `release`/`environment` still passed as parameters | Silently ignored | Use `LANGFUSE_RELEASE` / `LANGFUSE_TRACING_ENVIRONMENT` env vars |
| Server too old for v4 SDK | API errors (swallowed in lib code!) | Check pinned `infra/docker-compose.yml` stack version against the migration guide first |

## Best Practices

1. **Fetch the migration docs first** — canonical source, may have been updated
2. **Migrate incrementally** — bump the SDK, fix breaking changes, then adopt new patterns; one stg patch per logical step
3. **Tests are the proof** — the fail-open design means runtime won't tell you the migration broke; only the test suite and smoke spike will
