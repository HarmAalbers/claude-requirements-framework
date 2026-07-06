# Model-ID Refresh — Registry + Eval (2026-07-06)

## Goal

Bring the Langfuse cost-attribution registry and the eval judge label up to date
with current Claude model IDs. **No runtime model behavior changes** — the
functional callers stay on their current, still-supported models.

## Context

Grounded against `hooks/` and `scripts/` source plus the `claude-api` model
catalog (cached 2026-06-24):

- `claude-opus-4-8` — **current**, already in the registry. No change.
- `claude-haiku-4-5` — **current**, already in the registry and used by the
  summarizer + default eval judge. No change.
- `claude-sonnet-4-6` — **superseded** by `claude-sonnet-5`. Update.
- `claude-fable-5` — **new**, most-capable widely-released model. Add so traces
  running on it get cost-attributed.

Agent frontmatter uses tier **aliases** (`model: sonnet` / `model: haiku`) that
auto-resolve to the latest tier — no change needed.

## Decisions (confirmed with user)

- **Sonnet 5 price: standard $3/$15**, not the intro $2/$10 (intro expires
  2026-08-31 and would silently go stale). Matches how opus/haiku entries are
  defined and stays correct indefinitely.
- **Scope: registry + eval only.** Leave the summarizer / eval judge on
  Haiku 4.5 (current). Skip the excluded `_spikes/` files (never shipped).

## Changes (3 files)

### 1. `scripts/sync_langfuse_models.py` — `_PRICE_TABLE`

- Replace `claude-sonnet-4-6` → `claude-sonnet-5`:
  - `matchPattern`: `r"(?i)^claude-sonnet-5.*$"`
  - `prices`: `(0.000003, 0.000015, 0.0000003, 0.00000375)` — **unchanged**;
    Sonnet 5 list price is the same $3/$15 as 4.6, so the cache-read (0.1×) and
    cache-write (1.25×) tiers carry over exactly.
- Add `claude-fable-5`:
  - `matchPattern`: `r"(?i)^claude-fable-5.*$"`
  - `prices`: `(0.00001, 0.00005, 0.000001, 0.0000125)` — $10 input / $50 output
    / $1 cache-read (0.1×) / $12.50 cache-write (1.25×) per MTok.
- Leave `claude-opus-4-8` and `claude-haiku-4-5` untouched.

### 2. `scripts/run_eval.py:162`

- Judge label `"claude-sonnet-4-6"` → `"claude-sonnet-5"` (the `--judge sonnet`
  branch).

### 3. `tests/test_sync_langfuse_models.py`

- Mirror the registry change in the test's `EXPECTED_PRICES` / matchPattern
  fixtures.
- Update the `posted_names` assertions (currently expect `claude-sonnet-4-6`).
- Add the `claude-fable-5` expectation.

## Data flow / behavior

`sync_langfuse_models.py` is **create-if-absent + drift-report** against the
Langfuse models API — it does not delete existing definitions, so the historical
`claude-sonnet-4-6` def stays and old traces keep their pricing. New `sonnet-5`
and `fable-5` traces now get attributed. The script is **not** bundled into the
plugin (`build_plugin_hooks.py` only copies `hooks/lib`), so no bundle rebuild.

## Testing

- `python3 hooks/test_requirements.py` (full suite incl. the dedicated sync test).
- `ruff check .` (CI parity — the local TestRunner does not lint).

## Skipped (YAGNI)

- Intro pricing (temporary, would go stale).
- `_spikes/` model refs (excluded from the bundle, never shipped).
- Functional model bumps (summarizer / eval judge stay on Haiku 4.5).

---

# Model-ID Refresh Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use requirements-framework:executing-plans to implement this plan task-by-task.

**Goal:** Update the Langfuse price registry (`sonnet-4-6`→`sonnet-5`, add `fable-5`) and the eval sonnet judge label, with tests driving the change.

**Architecture:** Data-only edit. `_PRICE_TABLE` in `sync_langfuse_models.py` is the single source; `test_sync_langfuse_models.py` asserts against the materialized `MODELS`. TDD order: update the test fixtures/assertions first (RED — `MODELS` still has the old set), then the price table (GREEN).

**Tech Stack:** Python stdlib, custom `TestRunner` (not unittest), `ruff`.

---

### Task 1: Update the test spec (RED)

**Files:**
- Modify: `tests/test_sync_langfuse_models.py`

**Step 1 — edit fixtures + assertions.** In `EXPECTED_PRICES` (lines ~124-143): rename the `claude-sonnet-4-6` key to `claude-sonnet-5` (values unchanged) and add a `claude-fable-5` entry `{input: 0.00001, output: 0.00005, cache_read_input_tokens: 0.000001, cache_creation_input_tokens: 0.0000125}`. In `EXPECTED_PATTERNS` (lines ~144-148): rename `claude-sonnet-4-6` → `claude-sonnet-5` with pattern `r"(?i)^claude-sonnet-5.*$"` and add `claude-fable-5` → `r"(?i)^claude-fable-5.*$"`.

Update every hardcoded count/list that assumed a 3-model set:
- `test_register_models_posts_three_when_absent`: `len(opener.posts) == 3` → `== 4`, label "exactly 3 POSTs" → "exactly 4 POSTs".
- `test_register_models_idempotent_skips_existing`: `len(actions) == 3` → `== 4`, label.
- `test_register_models_partial_existence`: `len(opener.posts) == 2` → `== 3` (+label); `posted_names == ["claude-haiku-4-5", "claude-sonnet-4-6"]` → `["claude-fable-5", "claude-haiku-4-5", "claude-sonnet-5"]`.
- `test_check_reports_would_create` (~line 280): `len(would_create) == 3` → `== 4` (+label).
- `test_pagination_followed`: comment + `posted_names == ["claude-sonnet-4-6"]` → `["claude-fable-5", "claude-sonnet-5"]`; label "only the truly-absent model posted" → "models".
- `test_drift_reported_not_updated` (~line 334): `("claude-haiku-4-5", "claude-sonnet-4-6")` → `("claude-haiku-4-5", "claude-sonnet-5", "claude-fable-5")`.
- `test_managed_nested_prices_drift_detected` (~line 412): same tuple change.

(Tests that iterate `EXPECTED_PRICES`/`MODELS` — idempotent existing list, managed-recognized — auto-adjust; no edit.)

**Step 2 — run, expect RED:** `python3 hooks/test_requirements.py` → the sync tests fail (MODELS still has `sonnet-4-6`, lacks `fable-5`).

### Task 2: Update the price registry (GREEN)

**Files:**
- Modify: `scripts/sync_langfuse_models.py:80-83`

**Step 1 — edit `_PRICE_TABLE`:** replace the `claude-sonnet-4-6` block with `claude-sonnet-5` (matchPattern `^claude-sonnet-5.*$`, same prices tuple), and add a `claude-fable-5` block: matchPattern `^claude-fable-5.*$`, prices `(0.00001, 0.00005, 0.000001, 0.0000125)`.

**Step 2 — run, expect GREEN:** `python3 hooks/test_requirements.py`.

### Task 3: Update the eval judge label

**Files:**
- Modify: `scripts/run_eval.py:162`

**Step 1:** `"claude-sonnet-4-6"` → `"claude-sonnet-5"` in the `--judge sonnet` branch.

**Step 2 — verify:** `python3 hooks/test_requirements.py` and `ruff check scripts/ tests/`.

### Task 4: Commit

One stg patch: `feat(observability): register sonnet-5 + fable-5 model prices; retire sonnet-4-6 label`. No plugin bundle rebuild (sync script + eval are not bundled). No `plugin.json` bump (no plugin component touched).
