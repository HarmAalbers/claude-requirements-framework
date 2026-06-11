# Strict Global Preflight — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use requirements-framework:executing-plans to implement this plan task-by-task.

**Goal:** Add an opt-in, fail-closed "strict mode" so a globally-installed plugin blocks all work in any non-compliant project (missing/invalid `requirements.local.yaml`, wrong Langfuse env, missing `uv`) until it's fixed or opted out — with a surgical escape hatch and a guaranteed kill-switch.

**Architecture:** A pure compliance evaluator (`hooks/lib/preflight.py`) computes a verdict from 3 invariants + opt-out + master-switch + env kill-switch. `check-requirements.py` (PreToolUse) consults it and denies everything except an escape allowlist when non-compliant. `handle-session-start.py` renders a loud briefing of failures. Two new slash-commands scaffold/opt-out. Strict mode is OFF by default (inert until `strict_preflight: true`).

**Tech Stack:** Python stdlib (`shutil.which`, `pathlib`, `os.environ`), PyYAML (already a dep), the repo's hand-rolled `TestRunner` under `tests/` (no pytest), Stacked Git, `build_plugin_hooks.py` bundle mirror, `render_prompts.py` for command `.md.j2`.

**Branch:** `feat/strict-global-preflight` (stg-initialized). One atomic stg patch per task; any patch touching `plugins/...` bumps `plugin.json` in the same patch.

---

## Design invariants (do NOT re-derive — from the approved design doc)

- **Compliance = all three:** (1) `.claude/requirements.local.yaml` exists, parses, ≥1 enabled requirement; (2) Langfuse env structurally valid (5 Layer-1 keys present, none of the 6 deprecated Layer-2 keys, creds non-empty); (3) `uv` on PATH.
- **Exempt when:** `.claude/.rf-optout` exists, OR `strict_preflight` master switch is off/unset, OR `RF_STRICT_OFF=true`.
- **Escape allowlist (always allowed, precedence over ALL gates):** Write/Edit to `.claude/requirements.local.yaml` or `.claude/.rf-optout`; Bash invoking `req` / the `/req-init` / `/req-optout` paths.
- **Fail-SAFE:** any exception inside the evaluator must resolve to "not strict / allow" — a preflight bug must never lock the user out. Kill-switch checked first.
- **Evaluate directly in both hooks** (no session-state cache — the checks are cheap and a stale cache is a worse failure mode). YAGNI.

The 6 deprecated Layer-2 keys (reuse the set, do not retype): `CLAUDE_CODE_ENABLE_TELEMETRY`, `CLAUDE_CODE_ENHANCED_TELEMETRY_BETA`, `OTEL_TRACES_EXPORTER`, `OTEL_EXPORTER_OTLP_PROTOCOL`, `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_EXPORTER_OTLP_HEADERS`. The 5 Layer-1 keys: `TRACE_TO_LANGFUSE`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST`, `CC_LANGFUSE_MAX_CHARS`.

---

## Task 1: Master switch + kill-switch in config

**Files:**
- Modify: `hooks/lib/config.py` (add `strict_preflight_enabled()` near `is_enabled()`, ~line 278 / 1257)
- Test: `tests/test_preflight.py` (new — start the file here)

**Step 1 — failing test.** In `tests/test_preflight.py` (repo `TestRunner` pattern; mirror `tests/test_setup_langfuse_tracing.py`'s harness):
```python
def test_strict_off_by_default(runner):
    c = RequirementsConfig(tmp_project_with_no_config)
    runner.test("strict off by default", c.strict_preflight_enabled() is False)

def test_strict_on_when_set(runner):
    # project .claude/requirements.local.yaml with `strict_preflight: true`
    runner.test("strict on when configured", c.strict_preflight_enabled() is True)
```
**Step 2 — run** `python3 tests/test_preflight.py` → FAIL (`AttributeError`).
**Step 3 — implement** in `config.py`:
```python
def strict_preflight_enabled(self) -> bool:
    """True only if `strict_preflight: true` is set somewhere in the cascade.
    Default False — the strict regime is inert until explicitly turned on."""
    return bool(self._config.get("strict_preflight", False))
```
(Mirror on the `RequirementsConfig` facade if it wraps `_config` — add a passthrough like the other `get_*` delegates at ~line 336.)
**Step 4 — run** → PASS.
**Step 5 — commit:** `stg new preflight-config-switch` / refresh: `feat(preflight): strict_preflight master switch in config cascade`.

---

## Task 2: Pure compliance evaluator

**Files:**
- Create: `hooks/lib/preflight.py`
- Test: extend `tests/test_preflight.py`

Design: pure functions, dependency-injectable for tests (pass `env`, `which_fn`, `project_dir`). No hook I/O.

```python
# hooks/lib/preflight.py
import os, shutil
from dataclasses import dataclass, field
from pathlib import Path
import yaml

LAYER1_KEYS = ("TRACE_TO_LANGFUSE","LANGFUSE_PUBLIC_KEY","LANGFUSE_SECRET_KEY","LANGFUSE_HOST","CC_LANGFUSE_MAX_CHARS")
DEPRECATED_L2_KEYS = ("CLAUDE_CODE_ENABLE_TELEMETRY","CLAUDE_CODE_ENHANCED_TELEMETRY_BETA","OTEL_TRACES_EXPORTER","OTEL_EXPORTER_OTLP_PROTOCOL","OTEL_EXPORTER_OTLP_ENDPOINT","OTEL_EXPORTER_OTLP_HEADERS")
OPTOUT_RELPATH = Path(".claude") / ".rf-optout"
LOCAL_CFG_RELPATH = Path(".claude") / "requirements.local.yaml"

@dataclass
class ComplianceResult:
    strict_active: bool          # is strict mode governing this project at all
    compliant: bool              # all invariants pass (only meaningful if strict_active)
    failures: list = field(default_factory=list)  # [(code, human_msg, fix_cmd)]

def is_kill_switched(env=None) -> bool:
    env = env if env is not None else os.environ
    return (env.get("RF_STRICT_OFF") or "").lower() == "true"

def is_opted_out(project_dir) -> bool:
    return (Path(project_dir) / OPTOUT_RELPATH).exists()

def evaluate(project_dir, *, strict_enabled: bool, env=None, which_fn=shutil.which) -> ComplianceResult:
    """Top-level verdict. Fail-SAFE: callers wrap in try/except and treat exceptions as allow."""
    env = env if env is not None else os.environ
    if is_kill_switched(env) or not strict_enabled or is_opted_out(project_dir):
        return ComplianceResult(strict_active=False, compliant=True)
    failures = []
    failures += _check_local_config(project_dir)
    failures += _check_langfuse_env(env)
    failures += _check_uv(which_fn)
    return ComplianceResult(strict_active=True, compliant=not failures, failures=failures)
```
Implement the three `_check_*` helpers returning `[(code, msg, fix)]`:
- `_check_local_config`: file missing → `("no_config","no .claude/requirements.local.yaml","/req-init")`; unparseable → `("bad_config",...)`; 0 enabled requirements → `("empty_config",...)`.
- `_check_langfuse_env`: any deprecated L2 key present → `("stale_layer2",..., "python3 scripts/setup_langfuse_tracing.py --write")`; any L1 key missing/empty → `("langfuse_env",...)`.
- `_check_uv`: `which_fn("uv") is None` → `("no_uv","uv not on PATH","install uv")`.

**Tests** (extend `tests/test_preflight.py`, all injected — no real FS/env/PATH):
- `test_killswitch_short_circuits` (RF_STRICT_OFF=true → strict_active False, compliant True).
- `test_optout_short_circuits`.
- `test_strict_disabled_is_inert` (strict_enabled=False).
- `test_compliant_when_all_pass` (config w/ 1 enabled req + 5 L1 keys + which→path).
- `test_missing_config_fails` / `test_stale_layer2_fails` / `test_missing_uv_fails` / `test_empty_config_fails`.
- `test_failures_carry_fix_commands` (each failure has a non-empty fix string).

RED → implement → GREEN. **Commit:** `stg new preflight-evaluator`: `feat(preflight): pure compliance evaluator (config/langfuse/uv + optout/killswitch)`.

---

## Task 3: Escape allowlist

**Files:**
- Modify: `hooks/lib/preflight.py` (add `is_escape_allowed`)
- Test: extend `tests/test_preflight.py`

```python
def is_escape_allowed(tool_name: str, tool_input: dict, project_dir) -> bool:
    """True if this call must be allowed even when non-compliant: editing the config
    or opt-out sentinel, or running req / req-init / req-optout. Tight by exact target."""
    if tool_name in ("Edit","Write","MultiEdit"):
        fp = (tool_input or {}).get("file_path","")
        try: rel = Path(fp).resolve().relative_to(Path(project_dir).resolve())
        except Exception: return False
        return rel in (LOCAL_CFG_RELPATH, OPTOUT_RELPATH)
    if tool_name == "Bash":
        cmd = (tool_input or {}).get("command","")
        import re
        return bool(re.search(r"\breq(uirements-cli\.py)?\s+(init|optout)\b", cmd) or re.search(r"\breq-(init|optout)\b", cmd))
    return False
```
**Tests:** config-path write allowed; optout-path write allowed; arbitrary source-file write NOT allowed; `req init`/`req optout` Bash allowed; arbitrary Bash not allowed; path-traversal outside project not allowed.
RED → implement → GREEN. **Commit:** `stg new preflight-escape-allowlist`: `feat(preflight): escape allowlist (config + optout + req init/optout)`.

---

## Task 4: Wire the fail-closed gate into PreToolUse

**Files:**
- Modify: `hooks/check-requirements.py` (`main()`, ~line 288 after `early_hook_setup`, BEFORE the normal requirement loop)
- Test: `tests/test_check_requirements_strict.py` (new — subprocess-style or direct `main()` call with mocked input; mirror existing check-requirements tests if any, else direct-call with monkeypatched config/env)

Insert a guarded strict-gate block right after `project_dir, branch, config, logger = early_hook_setup(...)` and after `tool_name`/`tool_input` are parsed:
```python
# --- strict preflight gate (fail-SAFE: never let a bug here block work) ---
try:
    from preflight import evaluate, is_escape_allowed
    verdict = evaluate(project_dir, strict_enabled=config.strict_preflight_enabled())
    if verdict.strict_active and not verdict.compliant:
        if is_escape_allowed(tool_name, tool_input, project_dir):
            return 0  # escape hatch: always allow config/optout/req
        print(json.dumps(_strict_denial(verdict)))  # deny everything else
        return 0
except Exception as e:
    logger.debug("strict preflight skipped (fail-open)", error=str(e))
# --- fall through to normal requirement checks ---
```
Add `_strict_denial(verdict)` building the `hookSpecificOutput.permissionDecision="deny"` payload (reuse the shape from `create_batched_denial`), listing each `(code,msg,fix)` and a footer naming the escape hatch + `RF_STRICT_OFF=true` kill-switch.

**Tests:**
- strict+noncompliant+arbitrary edit → deny payload emitted.
- strict+noncompliant+config-edit → allowed (return 0, no deny).
- strict+compliant → falls through to normal checks.
- strict_enabled False → falls through (no strict behavior).
- evaluator raises → falls through (fail-safe), work NOT blocked.

RED → implement → GREEN. Also run `python3 hooks/test_requirements.py` (sanity). **Commit:** `stg new preflight-pretooluse-gate`: `feat(preflight): fail-closed PreToolUse strict gate + escape + fail-safe`.

---

## Task 5: Loud SessionStart briefing

**Files:**
- Modify: `hooks/handle-session-start.py` (`main()`, ~line 452 after `early_hook_setup`; render before/alongside the normal briefing)
- Test: extend `tests/test_preflight.py` with a pure render test for the briefing formatter

Add `format_strict_warning(verdict) -> str` (pure) that, when `strict_active and not compliant`, returns an unmissable block:
```
## ⛔ STRICT MODE — project not compliant (edits are BLOCKED)
- ❌ no .claude/requirements.local.yaml → run `/req-init`
- ❌ stale Layer-2 Langfuse keys → `python3 scripts/setup_langfuse_tracing.py --write`
Fix the above, opt out with `/req-optout`, or set RF_STRICT_OFF=true to disable strict mode.
```
In `main()`, compute the verdict (same guarded try/except, fail-open) and `emit_hook_context("SessionStart", format_strict_warning(verdict))` when non-compliant — in ADDITION to the normal status. Compliant/inert → no extra output.

**Tests:** formatter lists each failure + fix; returns empty when compliant; returns empty when strict inactive.
RED → implement → GREEN. **Commit:** `stg new preflight-sessionstart-briefing`: `feat(preflight): loud SessionStart non-compliance briefing`.

---

## Task 6: `/req-init` + `/req-optout` slash-commands + bundle/bump

**Files:**
- Create: `plugins/requirements-framework/commands/req-init.md.j2`, `req-optout.md.j2`
- Generate: their `.md` via `python3 scripts/render_prompts.py`
- Modify: `plugins/requirements-framework/.claude-plugin/plugin.json` (minor bump 4.18.0 → 4.19.0)
- Regenerate: bundle via `python3 scripts/build_plugin_hooks.py` (mirrors the modified `hooks/` from Tasks 1–5 into the plugin bundle)

`req-init.md.j2`: a command that scaffolds `.claude/requirements.local.yaml` (offer stage presets: instrument-only / front-gates / full-chain), ensures it's gitignored, and tells the user to restart. `req-optout.md.j2`: creates `.claude/.rf-optout` (+ gitignore note) and confirms the project is now inert. Keep them as deterministic instruction commands mirroring an existing command's frontmatter (`git_hash`, `description`).

**Steps:**
1. Write both `.md.j2`; `python3 scripts/render_prompts.py` to emit `.md`; `--check` clean.
2. `python3 scripts/build_plugin_hooks.py` then `--check` → "in sync" (mirrors Tasks 1–5 lib/hook changes into the bundle — they are NOT mirrored until now).
3. Bump `plugin.json` → 4.19.0.
4. `python3 hooks/test_requirements.py` + all new `tests/` files green.
**Commit:** `stg new preflight-commands-bundle`: `feat(preflight): /req-init + /req-optout commands; bundle mirror; plugin 4.19.0`.

---

## Task 7: ADR + CLAUDE.md + CHANGELOG + version finalize

**Files:**
- Create: `docs/adr/ADR-020-strict-global-preflight-fail-closed.md` (records the deliberate fail-open→fail-closed inversion, scoped to opt-in strict mode; the kill-switch + escape-hatch as the safety contract; references ADR-019's opt-in fail-hard precedent).
- Modify: `CLAUDE.md` (new "Strict Global Preflight" section: enable via `strict_preflight: true` in global `~/.claude/requirements.yaml`, GitHub install + auto-update, opt-out, `RF_STRICT_OFF` bailout).
- Modify: `CHANGELOG.md` (4.19.0 `### Added`: strict mode, commands, switches).

**Steps:** write ADR + CLAUDE.md + CHANGELOG; `render_prompts.py --check` + `build_plugin_hooks.py --check` clean; full suite green. **Commit:** `stg new preflight-docs`: `docs(preflight): ADR-020 + CLAUDE.md + CHANGELOG 4.19.0`.

---

## Acceptance (whole plan)
- [ ] Strict OFF by default (no `strict_preflight` → fully inert; every existing test stays green).
- [ ] With `strict_preflight: true`: a non-compliant project DENIES an arbitrary edit, ALLOWS writing `requirements.local.yaml` / `.rf-optout` / `req init`, and unblocks once compliant.
- [ ] `.rf-optout` makes a project inert; `RF_STRICT_OFF=true` disables strict instantly; an evaluator exception never blocks (fail-safe test).
- [ ] SessionStart prints the loud non-compliance briefing with fix commands.
- [ ] `/req-init` + `/req-optout` exist; `render_prompts.py --check` + `build_plugin_hooks.py --check` clean; full suite + new tests green; plugin 4.19.0; ADR-020 + CHANGELOG updated.

## Out of scope / deferred
- Functional Langfuse checks (reachability/model-registration) in the blocking gate — stays trace-time warning.
- Caching the verdict in session state (evaluate directly; revisit only if profiling shows cost).
- Auto-enabling strict mode on install (the user turns it on deliberately via the master switch).
