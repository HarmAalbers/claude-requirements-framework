# R5 Observability Hardening — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use requirements-framework:executing-plans to implement this plan task-by-task.

**Goal:** Make R5 Langfuse traces cost-accurate and enriched for every opted-in project, and remove the hollow Layer-2 OTEL double-trace.

**Architecture:** Productize the fixes into the R5 setup path (`scripts/`) plus the vendored Stop hook, then backfill existing projects. New stdlib `sync_langfuse_models.py` registers project-scoped model-price definitions; `setup_langfuse_tracing.py` calls it on `--write`, drops the 6 Layer-2 env keys, and prunes them from existing settings; the vendored `_langfuse_hook.py` gains `# VENDOR-PATCH` trace enrichment.

**Tech Stack:** Python stdlib (urllib, base64, json, argparse), Langfuse v3 self-hosted REST (`POST /api/public/models`), stg, the repo's hand-rolled `TestRunner` (no pytest), `build_plugin_hooks.py` bundle mirror.

**Branch:** `feat/r5-observability-hardening` (already created, stg-initialized). Atomic stg patches; any patch touching `plugins/...` bumps `plugin.json` in the same patch.

---

## Verified API contract (resolved in plan phase — do NOT re-derive)

Live self-hosted Langfuse v3 (`/api/public/models`) model-definition shape:

```json
{
  "modelName": "claude-opus-4-8",
  "matchPattern": "(?i)^claude-opus-4-8.*$",
  "unit": "TOKENS",
  "prices": {
    "input": 0.000005,
    "output": 0.000025,
    "cache_read_input_tokens": 0.0000005,
    "cache_creation_input_tokens": 0.00000625
  }
}
```

- **`prices` keys MUST match the ingested `usageDetails` keys exactly.** R5 generations emit: `input`, `output`, `cache_read_input_tokens`, `cache_creation_input_tokens` (+ derived `total`, which gets NO price). Confirmed from the live trace dump.
- **Prices are per-token** = `$/MTok ÷ 1_000_000`.
- `matchPattern` is a regex; `(?i)^claude-opus-4-8.*$` covers both `claude-opus-4-8` and the `claude-opus-4-8[1m]` variant (`.*` matches `[1m]` literally).
- Model defs are **project-scoped** (created under the authenticating key's project) — hence backfill runs per project.
- Auth: HTTP Basic `base64(public:secret)`, same as `setup_langfuse_tracing.py`.

Per-token price table (write to the script as a constant):

| modelName | input | output | cache_read_input_tokens | cache_creation_input_tokens |
|---|---|---|---|---|
| claude-opus-4-8 | 0.000005 | 0.000025 | 0.0000005 | 0.00000625 |
| claude-haiku-4-5 | 0.000001 | 0.000005 | 0.0000001 | 0.00000125 |
| claude-sonnet-4-6 | 0.000003 | 0.000015 | 0.0000003 | 0.00000375 |

matchPatterns: `(?i)^claude-opus-4-8.*$`, `(?i)^claude-haiku-4-5.*$`, `(?i)^claude-sonnet-4-6.*$`.

---

## Task 1: `scripts/sync_langfuse_models.py` (model-price sync)

**Files:**
- Create: `scripts/sync_langfuse_models.py`
- Test: `tests/test_sync_langfuse_models.py`

Stdlib-only (mirror `setup_langfuse_tracing.py`: `_resolve_creds()` reading process env then `infra/.env`; urllib POST; base64 auth). Expose an importable `register_models(creds: dict, *, check: bool=False) -> list[str]` (returns a human-readable action list) plus a thin `main()` with `--check`. `register_models` is what `setup_langfuse_tracing.py` will call after `--write`.

Design points:
- `MODELS` constant = list of dicts (modelName, matchPattern, prices) from the table above; `unit="TOKENS"` constant.
- Idempotent: `GET /api/public/models?limit=100` (paginate), match by `modelName`; if a model with that name already exists for the project, **skip** (or in non-check mode, leave as-is — do not duplicate). Langfuse allows multiple models with the same name/pattern, so guard on existence to stay idempotent.
- `--check`: report which of the 3 are present vs missing; never POST.
- Loud-fail on missing creds / non-2xx POST (setup-script stance), matching `setup_langfuse_tracing.py`.

**Step 1: Write failing tests** (`tests/test_sync_langfuse_models.py`, repo `TestRunner` pattern; monkeypatch the urllib opener so no network):
- `test_register_models_posts_three_when_absent`: fake "list" returns `[]` → 3 POSTs captured, each body has correct `modelName`, `matchPattern`, `unit="TOKENS"`, and `prices` with all four keys at the table values.
- `test_register_models_idempotent_skips_existing`: fake list returns all 3 modelNames → 0 POSTs.
- `test_prices_keys_match_usage_details`: assert each model's `prices` keys == `{input, output, cache_read_input_tokens, cache_creation_input_tokens}` (the contract guard).
- `test_check_mode_never_posts`: `check=True` → 0 POSTs regardless of existing.
- `test_missing_creds_hard_fails`: empty creds → SystemExit / nonzero.

**Step 2:** Run `python3 tests/test_sync_langfuse_models.py` → expect FAIL (module missing).

**Step 3:** Implement `scripts/sync_langfuse_models.py` per design points.

**Step 4:** Run the test → expect PASS.

**Step 5:** Commit — `stg new sync-langfuse-models` / `stg refresh`:
`feat(observability): sync_langfuse_models.py — project-scoped model price defs`

---

## Task 2: `setup_langfuse_tracing.py` — drop Layer-2, prune, call model sync

**Files:**
- Modify: `scripts/setup_langfuse_tracing.py` (`_build_env_block`, `_write_settings`/new prune, `main`)
- Test: `tests/test_setup_langfuse_tracing.py` (create if absent; else extend)

Changes:
1. `_build_env_block`: return only the 5 Layer-1 keys — `TRACE_TO_LANGFUSE`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST`, `CC_LANGFUSE_MAX_CHARS`. Delete the 6 Layer-2 keys (`CLAUDE_CODE_ENABLE_TELEMETRY`, `CLAUDE_CODE_ENHANCED_TELEMETRY_BETA`, `OTEL_TRACES_EXPORTER`, `OTEL_EXPORTER_OTLP_PROTOCOL`, `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_EXPORTER_OTLP_HEADERS`) and the now-unused `base64`/`basic` lines in that function if not otherwise used.
2. Add `_DEPRECATED_ENV_KEYS` = the 6 removed keys. In `_write_settings`, after merging the new block, **delete** any deprecated keys present in `settings["env"]` (clean removal, no shim).
3. `main`: after a successful `--write`, call `sync_langfuse_models.register_models(creds)` (import lazily). Loud-warn (not fatal) on model-sync failure — creds are already written; cost backfill can be re-run. Mirror the `_warm_uv_cache` "warn but continue" stance.

**Step 1: Write/extend failing tests:**
- `test_env_block_is_five_keys`: `_build_env_block(creds)` returns exactly the 5 keys; none of the 6 OTEL keys present.
- `test_write_prunes_deprecated_otel_keys`: pre-seed a temp `settings.local.json` with the 6 OTEL keys + an unrelated key → after `_write_settings`, the 6 are gone, the unrelated key and the 5 new keys remain.

**Step 2:** Run → FAIL.

**Step 3:** Implement the three changes.

**Step 4:** Run → PASS. Also run full suite `python3 hooks/test_requirements.py` (sanity).

**Step 5:** Commit: `stg new setup-drop-layer2`:
`feat(observability): setup drops Layer-2 OTEL keys + prunes them + syncs models`

---

## Task 3: Vendored `_langfuse_hook.py` enrichment (`# VENDOR-PATCH`)

**Files:**
- Modify: `hooks/_langfuse_hook.py` (add `# VENDOR-PATCH` hunks: set `user_id`, `release`, project `tag` on the trace)
- Modify (mirror): run `build_plugin_hooks.py` (Task 4 handles the bundle commit)
- Test: extend `tests/` if the vendored hook has importable seams; otherwise a smoke assertion.

Sub-steps:
1. **Investigate ttft feasibility first** (read-only): inspect a CC transcript JSONL (`transcript_path`) for any per-assistant-turn first-token timing. If present → set `completion_start_time`; if absent → document "ttft not recoverable post-Layer-2; deferred" in the hook docstring and ADR. Do NOT block the task on ttft.
2. Locate where the vendored hook builds the trace (the `langfuse` client `trace`/`start_span` call). Add `# VENDOR-PATCH` lines pulling `user_id` (transcript account id), `release` (CC version — from env `CLAUDE_*` or transcript), and appending a project `tag` (repo basename of cwd) to the existing `claude-code` tag. Keep changes minimal and clearly marked for re-vendor.
3. Update the patched-failure-point count in the docstring (the docstring tracks `# VENDOR-PATCH` hunks).

**Step 1:** Write a test asserting the enrichment fields are set on a captured trace call (mock the langfuse client; feed a minimal transcript fixture). If the hook isn't unit-testable without the SDK, add a `tests/`-level skip-if-absent smoke that runs the hook on a fixture and asserts the constructed payload dict (refactor a tiny pure helper `_enrichment(payload, transcript) -> dict` to make it testable — preferred).

**Step 2:** Run → FAIL.

**Step 3:** Implement the `# VENDOR-PATCH` enrichment (+ helper).

**Step 4:** Run → PASS.

**Step 5:** Commit (defer bundle mirror to Task 4 OR mirror here): `stg new hook-enrichment`:
`feat(observability): R5 hook enrichment (userId/release/tags); ttft investigated`

---

## Task 4: ADR-019 + CLAUDE.md + plugin bump + bundle re-mirror

**Files:**
- Modify: `docs/adr/ADR-019-*.md` (supersede the "Layer 2 OTEL beta traces" section: record removal + rationale + the model-pricing sync + enrichment; note the parallel-namespace coexistence section is now moot for Layer 2)
- Modify: `CLAUDE.md` (R5 section: env block is 5 keys, Layer-2 removed, model pricing auto-registered, enrichment fields)
- Modify: `plugins/requirements-framework/.claude-plugin/plugin.json` (minor bump, current 4.17.1 → 4.18.0)
- Regenerate: `plugins/requirements-framework/hooks/_langfuse_hook.py` via `python3 scripts/build_plugin_hooks.py`

**Step 1:** Edit ADR-019 + CLAUDE.md as above.

**Step 2:** Bump `plugin.json` to `4.18.0`.

**Step 3:** Run `python3 scripts/build_plugin_hooks.py` to mirror the Task-3 hook change into the bundle; then `python3 scripts/build_plugin_hooks.py --check` → expect "in sync".

**Step 4:** Run `python3 scripts/render_prompts.py --check` (expect fresh) + full suite `python3 hooks/test_requirements.py` + the new `tests/` files → expect all green.

**Step 5:** Commit: `stg new r5-hardening-docs-bundle`:
`docs(observability): supersede ADR-019 Layer-2 section; bundle+plugin 4.18.0`

(If Task 3 didn't mirror the bundle, this patch includes the bundled `_langfuse_hook.py` — same patch as the plugin bump, per the version-bump rule.)

---

## Task 5: Backfill (live, user-run via `!` — not a code commit)

Not a code task. After Tasks 1–4 land and are deployed:

1. **solarmonkey-app:** re-run setup from its dir with its keys inline (creates project-scoped model defs + strips OTEL keys):
   ```bash
   cd /Users/harm/Work/solarmonkey-app
   LANGFUSE_HOST=http://localhost:3000 \
   LANGFUSE_PUBLIC_KEY=pk-lf-... LANGFUSE_SECRET_KEY=sk-lf-... \
   python3 /Users/harm/Tools/claude-requirements-framework/scripts/setup_langfuse_tracing.py --write
   ```
2. **This framework repo:** `python3 scripts/setup_langfuse_tracing.py --write` (creds from `infra/.env`).
3. **Verify (live):** existing session `3de54086` now shows non-zero cost in the solarmonkey-app project; the next turn produces no new `claude_code.interaction` trace (Layer-2 off). Restart the affected sessions so the new 5-key env block loads.

> Run setup commands via `!` so secrets stay in the shell. Do NOT run them via the Bash tool.

---

## Acceptance (whole plan)
- [ ] 3 model defs registered per project; `prices` keys == usageDetails keys; cost > 0 on R5 traces.
- [ ] Env block is 5 keys; existing settings pruned of the 6 OTEL keys; no new `claude_code.interaction` traces.
- [ ] R5 traces carry `userId` + `release` + project tag; ttft resolved or documented-deferred.
- [ ] `build_plugin_hooks.py --check` + `render_prompts.py --check` clean; full suite + new tests green.
- [ ] ADR-019 + CLAUDE.md updated; plugin 4.18.0.

## Deferred
- Bucket 3 (agent behavior).
- ttft if transcript recovery is infeasible.
