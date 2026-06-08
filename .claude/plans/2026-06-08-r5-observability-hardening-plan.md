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

## Arch-Review Binding Amendments (2026-06-08)

> Folded in from the team arch-review (adr-guardian, compat-checker, tdd-validator,
> solid-reviewer, refactor-advisor, commit-planner, codex-arch-reviewer). These are
> **binding** refinements to the tasks below — apply them as you implement each task.
> Verdict was APPROVED *contingent on these*; the commit/refactor sections already
> reflect the creds-reuse and CHANGELOG/docs-split decisions.

### Task 1 amendments
- **A1 — shared usage-key constant:** define `USAGE_DETAIL_KEYS = ("input", "output",
  "cache_read_input_tokens", "cache_creation_input_tokens")` once and reference it from
  both the `MODELS` price builder and `test_prices_keys_match_usage_details`. Do NOT
  re-type the four keys as a literal in the test (locks the cross-system contract to one
  source).
- **A2 — partial-existence test:** add `test_register_models_partial_existence` (fake list
  returns 1 of 3 modelNames → exactly 2 POSTs, the correct two). The per-model skip logic
  is the bug-prone part; the all/none tests miss the off-by-one case.
- **A3 — pagination: test it or drop the claim.** The design says `GET ...?limit=100
  (paginate)`. Either add a multi-page fake-list test driving the pagination, or remove the
  paginate claim if ≤100 models is guaranteed. No untested pagination code.
- **A4 — failure semantics for an importable API:** `register_models` must NOT `SystemExit`
  on a non-2xx POST — raise a domain `LangfuseModelSyncError`; the thin `main()` converts it
  to a nonzero exit. This is what lets Task 2's `setup` catch-and-warn after creds are
  already written (a bare `SystemExit` from inside `register_models` would abort setup
  post-write). Missing-creds may still hard-fail in `main()`/`_resolve_creds`. Keep the
  `list[str]` action-list return for the success path.
- **A5 — create-if-absent only; report drift:** the name-match skip means a pre-existing def
  with stale `prices`/`matchPattern`/`unit` survives forever and price updates are silently
  blocked. Document in the script docstring + ADR that `register_models` does NOT correct an
  existing def (delete it manually to re-register), and have `--check` REPORT drift
  (name present but spec differs), not just present/absent.

### Task 2 amendments
- **B1 — prune MUST be exact-match (load-bearing):** `_DEPRECATED_ENV_KEYS` is a literal
  `frozenset` of the 6 names; prune via `for k in _DEPRECATED_ENV_KEYS: env.pop(k, None)`.
  It MUST NOT be a `startswith("OTEL_EXPORTER_OTLP_")` prefix match — that would strip the
  V3 review stack's `OTEL_EXPORTER_OTLP_TRACES_*` keys (distinct namespace, ADR-019
  coexistence) and break its exporter. Add regression test
  `test_prune_preserves_v3_traces_keys`: pre-seed `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` →
  asserts it SURVIVES the prune.
- **B2 — existing test file is a BREAKING REWRITE, not "extend":** `tests/test_setup_langfuse_tracing.py`
  already exists and asserts the 11-key block in ≥4 sites: the "exactly 11 keys" set test,
  the `test_header_and_endpoint_normalization` test (asserts `OTEL_EXPORTER_OTLP_HEADERS`/
  `_ENDPOINT` present), and the "mentions var count (11)" stdout assertion. Task 2 must
  rewrite these: drop/adjust the count test to 5 keys, re-point the host-normalization
  assertion at `LANGFUSE_HOST` (trailing-slash normalization still matters), fix the
  var-count message assertion 11→5. `grep -n "11\|OTEL\|TELEMETRY" tests/test_setup_langfuse_tracing.py`
  to find every site. Task 2 Step 4 / Task 4b "full suite green" cannot pass until these are fixed.
- **B3 — model-sync failure tolerance test:** add `test_main_warns_but_continues_on_model_sync_failure`
  — inject a failing `register_models` (raising `LangfuseModelSyncError`) → `main` still
  exits 0 with settings written (the "creds already written, warn-but-continue" contract).
- **B4 — print-mode + restart:** the non-`--write` (print/paste) path must loudly state that
  model sync was skipped and show the exact `--write` follow-up command (else a project can
  opt in via paste yet stay cost-inaccurate). Add to Acceptance: "affected sessions
  restarted; no Layer-2 trace from a post-restart turn."

### Task 3 amendments
- **C1 — pin the test seam decisively (no conditional RED):** commit up front to the pure
  `_enrichment(payload, transcript) -> dict` helper PLUS a call-capture test that mocks
  `propagate_attributes(...)` and the trace `update(...)`/`_start_backdated` path and
  asserts `user_id`/`tags`/`release` actually REACH the trace (two distinct sinks — the
  helper alone tests computation, not wiring). Drop the "skip-if-SDK-absent smoke" as the
  PRIMARY guard: skip==green in the repo's default SDK-absent env, so it would let the
  enrichment regress silently. Keep the smoke only as a belt-and-suspenders integration check.
- **C2 — VENDOR-PATCH bookkeeping (don't conflate two inventories):** the enrichment is a
  NEW hunk — add it as an enumerated `# VENDOR-PATCH (e)` in the header's hunk list, and
  keep the fail-hard "5 patched failure points" coverage count UNCHANGED (enrichment adds no
  new failure point). Task 3 Step 3's current "update the patched-failure-point count"
  wording conflates the hunk enumeration with the failure-point count — fix the wording.
  Recommended: adopt `# VENDOR-PATCH-BEGIN/END <id>` block markers and a check asserting the
  enrichment id exists in BOTH `hooks/_langfuse_hook.py` and the plugin bundle mirror.
- **C3 — keep `_enrichment` pure; split ttft:** `_enrichment` must not mutate the client or
  do I/O — return a dict, caller applies it. Put ttft recovery in its own `_ttft(transcript)`
  helper so the deferred-ttft path stays cleanly excisable.
- **C4 — incremental-read seam:** the hook emits only newly-read transcript rows; if
  `userId`/`release` live only in earlier rows, later turns may lack them. Bound the metadata
  scan and/or cache stable session-level enrichment in session state. Verify the helper shape
  against a real transcript JSONL before finalizing (same read used for the ttft probe).

### Task 4 amendments (lands in Patch 4a, docs)
- **D1 — ADR-019 amendment is single-layer, not a one-section supersede:** (a) rewrite the
  Context (it currently frames R5 as a TWO-layer design), (b) mark Layer-2 decision content
  superseded, (c) EXPLICITLY PRESERVE Decisions 1 (fail-hard), 2 (vendoring), 3 (uv-prereq) —
  they are layer-independent and still in force, so a reader doesn't think the whole ADR is
  dead, (d) update the Coexistence section in place (do NOT blank it): record the generic
  `OTEL_EXPORTER_OTLP_*` namespace is now UNUSED (Layer-2 removed) while the V3 stack's
  signal-specific `OTEL_EXPORTER_OTLP_TRACES_*` stands alone (no precedence contest remains),
  and state whether the prior "/v3-review trace shows up twice" overlap still holds now that
  only the Stop-hook turn trace exists.
- **D2 — shared-registry cross-reference:** add one line to the ADR-019 amendment noting the
  model-pricing registry is now SHARED infrastructure — it also backs `/v3-review` (ADR-018)
  Sonnet-worker cost attribution — so a future editor doesn't scope it R5-only and break V3
  costing.
- **D3 — CHANGELOG minor-vs-major justification:** the `### Removed` entry must include a
  one-line rationale that a MINOR bump (4.18.0) is correct because the 6 keys are emitted
  local env in a gitignored `settings.local.json` (not an ADR-015 enumerated "public
  artifact" like a command/agent/manifest entry); a clean removal + prune with no shim is the
  intended cadence. (If they were public artifacts, ADR-015 Policy 1 would force a major —
  state the call, don't leave it silent.)
- **D4 (optional, INFO) — pre-existing CHANGELOG drift:** newest CHANGELOG entry is 4.15.0
  while plugin.json is already 4.17.1 (4.16.0/R5 + 4.17.x undocumented). Optional to backfill
  the 4.16.0 anchor in this branch; not required for the gate.

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

## Preparatory Refactoring

> These refactorings make the planned change easier to implement. Each is a standalone improvement
> that should be committed separately, before the main feature work begins.

**Verdict for this plan: no prep refactoring required — the flagged "5th reader" trigger does NOT actually fire here.** The known signal (`setup_langfuse_tracing.py`'s docstring: "extraction target if a 5th appears") was assessed and found not to apply at this scale. Recorded below so a future reviewer doesn't re-open it.

### Why the creds/auth-helper extraction is NOT worth doing now

The `infra/.env` readers form **two non-interchangeable families**, and the new script joins the smaller one without growing it:

- **Family A (stdlib, base64-basic-auth, raw `urllib`, `cwd`-relative `infra/.env`, hard-fail):** only `setup_langfuse_tracing.py::_resolve_creds`. Runs from the *target project's* cwd (often not this repo), so its `Path.cwd()/infra/.env` resolution is load-bearing and deliberately different from the others.
- **Family B (`python-dotenv` soft-dep, mutates `os.environ`, `REPO_ROOT`-relative, hands creds to the `langfuse` SDK, no base64/urllib):** `sync_prompts_to_langfuse.py`, `sync_golden_set_to_langfuse.py`, `hooks/lib/llm/review_cli.py`, and the `_spikes/`. These never build an auth header — the SDK reads env itself.

`sync_langfuse_models.py` is stdlib + base64 + `urllib` POST (Family A shape), but per Task 1/Task 2 its importable `register_models(creds)` **takes the creds dict as a parameter** — when `setup_langfuse_tracing.py` calls it after `--write`, the creds are already resolved and passed in, so **no second reader runs on the hot path**. The new script only self-resolves inside its own thin `main()`/`--check`.

Net effect of proceeding without extraction:
- **Zero new divergence** between A and B (the two families stay exactly as they are).
- The only duplication added is one small stdlib `infra/.env` parse inside `sync_langfuse_models.main()` — and even that can be **avoided entirely** by importing `setup_langfuse_tracing._resolve_creds` (same package, Family A, identical semantics) instead of re-hand-rolling it. **Prefer the import over a copy.**

Extracting a shared `langfuse_creds.py` now would mean reconciling A's cwd-relative/stdlib/base64 contract with B's REPO_ROOT/dotenv/SDK contract — that reconciliation is **larger and riskier than the entire model-sync feature** (it would touch 4–5 stable, separately-tested files: `test_setup_langfuse_tracing.py`, `test_sync_prompts.py`, `test_sync_golden_set.py`, plus `review_cli`). That fails the effort-ratio and proportionality bars.

### Recommended (do inside Task 1, not as separate prep)
- In `sync_langfuse_models.main()`, **import and reuse** `setup_langfuse_tracing._resolve_creds()` rather than copying the `.env` parse loop. This keeps Family A single-sourced for the urllib/base64 path without any standalone refactor commit, and is the cheapest way to honor the docstring's intent.
- **Update the "4th reader / 5th appears" docstring note** in `setup_langfuse_tracing._resolve_creds` to record that the 5th consumer (`sync_langfuse_models`) reuses this function rather than adding a reader — so the extraction trigger is explicitly retired, not silently tripped. (Pattern: Harden Before Depending — a one-line doc correction on the dependency you're about to lean on.)

### Skip Conditions
- If reusing `_resolve_creds` proves awkward (e.g. you want `register_models`-only callers to avoid importing the setup module), a 3-line stdlib copy in `main()` is acceptable — it stays within Family A and adds no cross-family coupling. Still update the docstring note either way.

## Acceptance (whole plan)
- [ ] 3 model defs registered per project; `prices` keys == usageDetails keys; cost > 0 on R5 traces.
- [ ] Env block is 5 keys; existing settings pruned of the 6 OTEL keys; no new `claude_code.interaction` traces.
- [ ] R5 traces carry `userId` + `release` + project tag; ttft resolved or documented-deferred.
- [ ] `build_plugin_hooks.py --check` + `render_prompts.py --check` clean; full suite + new tests green.
- [ ] ADR-019 + CLAUDE.md updated; plugin 4.18.0.

## Deferred
- Bucket 3 (agent behavior).
- ttft if transcript recovery is infeasible.

---

## Commit Plan

> Stacked Git workflow: each entry is `stg new <patch-name>` → edit → `stg refresh`
> (iterate until the patch is right), then `stg new <next>`. One logical change per
> patch. Any patch touching `plugins/...` bumps
> `plugins/requirements-framework/.claude-plugin/plugin.json` in the **same** patch.

### Validation of the plan's proposed 4-patch breakdown

The plan's Task 1–4 → 4-patch mapping is **sound and approved as the baseline**:

| Task | Patch | Touches `plugins/`? | Plugin bump? |
|---|---|---|---|
| 1 | `sync-langfuse-models` | No (`scripts/`, `tests/`) | No |
| 2 | `setup-drop-layer2` | No (`scripts/`, `tests/`) | No |
| 3 | `hook-enrichment` | No (`hooks/_langfuse_hook.py` is the **vendored source**, not the bundle) | No |
| 4 | `r5-hardening-docs-bundle` | **Yes** (`plugins/.../hooks/_langfuse_hook.py` mirror + `plugin.json`) | **Yes → 4.18.0** |

Key correctness points the breakdown already gets right:
- **Bundle mirror + plugin bump are co-located in Patch 4.** Task 3 edits only the vendored source `hooks/_langfuse_hook.py`; the plugin bundle copy (`plugins/requirements-framework/hooks/_langfuse_hook.py`) is regenerated via `build_plugin_hooks.py` in Patch 4, alongside the `plugin.json` bump — satisfying the same-patch rule. Do **not** mirror the bundle in Patch 3.
- **Patch 3 carries no plugin bump** because the vendored `hooks/` source is not under `plugins/`. The bundle (and therefore the bump) only materializes in Patch 4.
- **Dependency order** is linear: 1 → 2 (lazy `register_models` import) → 3 → 4 (mirrors Patch-3 hook). Patch 4 must come last because `build_plugin_hooks.py` mirrors whatever is in `hooks/_langfuse_hook.py` at that point.

### Refinement (recommended): split Patch 4 into 4a + 4b

Honors both reviewer flags. The single Patch 4 mixes a pure-docs change (ADR-019),
a pure-docs change (CHANGELOG `### Removed`), and a build artifact + version bump.
Splitting the docs ahead keeps the version-bump patch focused on the bundle + bump
and makes each independently revertible. **The plugin bump + bundle mirror must stay
together in the final patch; the docs may precede it.**

If you prefer minimal patch count, the baseline 4-patch plan is acceptable — fold
ADR-019 + CLAUDE.md + CHANGELOG into Patch 4. The 5-patch refinement below is the
recommendation.

### Commit Sequence (recommended 5-patch)

| Order | Patch name | Commit message | Files | Depends On | Rollback Safe |
|-------|-----------|----------------|-------|------------|---------------|
| 1 | `sync-langfuse-models` | `feat(observability): sync_langfuse_models.py — project-scoped model price defs` | `scripts/sync_langfuse_models.py`, `tests/test_sync_langfuse_models.py` | - | Yes |
| 2 | `setup-drop-layer2` | `feat(observability): setup drops Layer-2 OTEL keys + prunes them + syncs models` | `scripts/setup_langfuse_tracing.py`, `tests/test_setup_langfuse_tracing.py` | 1 | Yes |
| 3 | `hook-enrichment` | `feat(observability): R5 hook enrichment (userId/release/tags); ttft investigated` | `hooks/_langfuse_hook.py`, `tests/test_langfuse_hook_enrichment.py` (or smoke) | - | Yes |
| 4a | `r5-hardening-docs` | `docs(adr): supersede ADR-019 Layer-2 section; record model-pricing + enrichment` | `docs/adr/ADR-019-*.md`, `CLAUDE.md`, `CHANGELOG.md` | 2, 3 (documents their behavior) | Yes |
| 4b | `r5-bundle-plugin-bump` | `chore(plugin): mirror enriched hook into bundle; bump plugin 4.18.0` | `plugins/requirements-framework/hooks/_langfuse_hook.py`, `plugins/requirements-framework/.claude-plugin/plugin.json` | 3 (source), 4a (docs land first) | No (version bump + build artifact) |

### Commit Details

#### Patch 1: `feat(observability): sync_langfuse_models.py — project-scoped model price defs`
**Purpose**: New stdlib model-price sync; foundation that Patch 2 imports.
**Files**:
- `scripts/sync_langfuse_models.py` — new; `register_models(creds, *, check=False)` + thin `main()`/`--check`. Per the Preparatory Refactoring note, `main()` **imports and reuses** `setup_langfuse_tracing._resolve_creds()` rather than re-hand-rolling the `.env` parse, and updates that function's "4th reader / 5th appears" docstring note to record reuse (retire the extraction trigger).
- `tests/test_sync_langfuse_models.py` — new; 5 tests (posts-three, idempotent-skip, prices-keys-contract, check-never-posts, missing-creds-hard-fails), urllib opener monkeypatched (no network).
**Test**:
- `python3 tests/test_sync_langfuse_models.py` → all green (was RED before implementation).
**Rollback**: Safe to revert independently — nothing else imports it yet.

#### Patch 2: `feat(observability): setup drops Layer-2 OTEL keys + prunes them + syncs models`
**Purpose**: 5-key env block, prune the 6 deprecated OTEL keys from existing settings, call model sync after `--write`.
**Files**:
- `scripts/setup_langfuse_tracing.py` — `_build_env_block` → 5 keys; add `_DEPRECATED_ENV_KEYS` + prune in `_write_settings`; `main` lazily calls `register_models(creds)` (warn-but-continue on failure).
- `tests/test_setup_langfuse_tracing.py` — create-or-extend; `test_env_block_is_five_keys`, `test_write_prunes_deprecated_otel_keys`.
**Test**:
- `python3 tests/test_setup_langfuse_tracing.py` → green.
- `python3 hooks/test_requirements.py` → full suite green (sanity; this file is import-coupled to Patch 1).
**Rollback**: Safe — clean removal, no shim. Revert with Patch 1 if reverting the whole model-sync feature.
**Note**: This patch hard-depends on Patch 1 (lazy import of `register_models`). The lazy import means Patch 2 still loads even if Patch 1 is absent until the call site is hit — but they should land/revert together.

#### Patch 3: `feat(observability): R5 hook enrichment (userId/release/tags); ttft investigated`
**Purpose**: `# VENDOR-PATCH` enrichment of the vendored Stop hook (set `user_id`, `release`, append project `tag`); ttft feasibility investigated (set `completion_start_time` if recoverable, else document deferral in docstring + ADR).
**Files**:
- `hooks/_langfuse_hook.py` — `# VENDOR-PATCH` hunks; extract a pure `_enrichment(payload, transcript) -> dict` helper for testability; bump the docstring's `# VENDOR-PATCH` hunk count.
- `tests/test_langfuse_hook_enrichment.py` — new; asserts enrichment fields on the constructed payload via the pure helper (or skip-if-SDK-absent smoke).
**Test**:
- `python3 tests/test_langfuse_hook_enrichment.py` → green.
**Rollback**: Safe at the source level. **Do not** run `build_plugin_hooks.py` here — the bundle stays stale until Patch 4b (so 3 carries no `plugins/` change and no bump).
**Critical**: This is the only patch editing the vendored source. Patch 4b's `build_plugin_hooks.py --check` will fail until this patch's hook change is mirrored — that ordering is intentional.

#### Patch 4a: `docs(adr): supersede ADR-019 Layer-2 section; record model-pricing + enrichment`
**Purpose**: Documentation only — ADR-019 supersede + CLAUDE.md R5 section + CHANGELOG `### Removed` (ADR-015 compliance for the 6 dropped env keys).
**Files**:
- `docs/adr/ADR-019-*.md` — supersede the "Layer 2 OTEL beta traces" section: removal + rationale + model-pricing sync + enrichment; note the parallel-namespace coexistence section is now moot for Layer 2.
- `CLAUDE.md` — R5 section: env block is now 5 keys, Layer-2 removed, model pricing auto-registered, enrichment fields (`userId`/`release`/project tag).
- `CHANGELOG.md` — `### Removed` entry listing the 6 dropped env keys (`CLAUDE_CODE_ENABLE_TELEMETRY`, `CLAUDE_CODE_ENHANCED_TELEMETRY_BETA`, `OTEL_TRACES_EXPORTER`, `OTEL_EXPORTER_OTLP_PROTOCOL`, `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_EXPORTER_OTLP_HEADERS`).
**Test**:
- No code; visual/markdown review only. (If CHANGELOG has a lint/format check, run it.)
**Rollback**: Safe — docs-only, independently revertible.

#### Patch 4b: `chore(plugin): mirror enriched hook into bundle; bump plugin 4.18.0`
**Purpose**: Regenerate the plugin bundle copy of the enriched hook and bump the plugin version — kept together per the same-patch version-bump rule.
**Files**:
- `plugins/requirements-framework/hooks/_langfuse_hook.py` — regenerated via `python3 scripts/build_plugin_hooks.py` (mirrors Patch 3).
- `plugins/requirements-framework/.claude-plugin/plugin.json` — minor bump `4.17.1 → 4.18.0`.
**Test**:
- `python3 scripts/build_plugin_hooks.py` then `python3 scripts/build_plugin_hooks.py --check` → "in sync".
- `python3 scripts/render_prompts.py --check` → fresh.
- `python3 hooks/test_requirements.py` + all new `tests/` files → green.
**Rollback**: **Not independently safe** — version bump + generated artifact. Revert with Patch 3 (its source) if backing out enrichment.
**Critical**: Must be the last patch. `build_plugin_hooks.py` mirrors whatever is in `hooks/_langfuse_hook.py` at this point, so Patch 3 must already be applied.

### Baseline fallback (4-patch, if minimizing patch count)

Fold 4a into 4b: single patch `docs(observability): supersede ADR-019 Layer-2 section; CHANGELOG; bundle+plugin 4.18.0` containing ADR-019 + CLAUDE.md + CHANGELOG + bundle mirror + `plugin.json`. Still satisfies the same-patch bump rule. The 5-patch split is preferred for reviewability and independent revert of the docs.

### Test Strategy
- Run the patch's own test file after each `stg refresh` (RED → GREEN per task).
- After Patch 2 and Patch 4b, run the **full suite** `python3 hooks/test_requirements.py` (import-coupling and bundle/render checks).
- CI/green gates at each patch boundary: Patches 1–3 leave the bundle deliberately stale (no `--check` run), so do not gate `build_plugin_hooks.py --check` until 4b — that's the patch that re-syncs it.
- `render_prompts.py --check` only needs to pass at 4b (no prompt templates change in 1–3).

### Notes
- **Bundle/bump co-location is the load-bearing constraint**: the bundle mirror and `plugin.json` bump are inseparable and live in the final patch (4b, or 4 in the baseline). Never mirror the bundle in Patch 3.
- **No backwards-compat shims** (per project memory): the 6 OTEL keys are deleted cleanly from `_build_env_block` and pruned from existing settings — no deprecated aliases retained.
- **ADR-015 compliance**: the CHANGELOG `### Removed` entry is the documented mechanism for the dropped env keys; it lands no later than the patch that removes them is documented (4a).
- **Live backfill (Task 5) is NOT a commit** — run via `!` after 4b deploys; out of scope for this commit plan.
- **stg reminder**: `stg init` is already done on `feat/r5-observability-hardening`. Bump `plugin.json` inside Patch 4b's `stg refresh`, not a separate patch.

---

## Verdict

APPROVED

Reviewed: feat/r5-observability-hardening @ 2026-06-08T13:45:41Z

Team arch-review (adr-guardian, backward-compatibility-checker, tdd-validator,
solid-reviewer, refactor-advisor, commit-planner, codex-arch-reviewer). No CRITICAL
findings and no fundamental architectural conflict. adr-guardian's initial BLOCKED was
contingent on three HIGH plan-scope gaps (ADR-019 single-layer supersession, CHANGELOG
`### Removed` entry, VENDOR-PATCH hunk enumeration) — all now folded into the **Arch-Review
Binding Amendments** section above, clearing the block. No new ADR required (Layer-2 removal
is a supersession-in-place of ADR-019, consistent with how ADR-015 amended ADR-012). The
creds-extraction "5th reader" trigger was assessed and correctly retired (reuse
`_resolve_creds`). Proceed to implementation per the 5-patch Commit Plan, applying the
binding amendments per task.
