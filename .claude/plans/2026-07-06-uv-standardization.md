# Plan: Standardize on `uv` for all Python execution

## Context

We deleted a batch of stale pyenv/`.venv` environments that "weren't properly used."
That exposed a latent fragility: **every Python entrypoint in this project shebangs
`#!/usr/bin/env python3` and trusts the ambient interpreter to already have the right
packages.** Those packages lived in the deleted venvs. Now `~/.local/bin/python3` (first
on PATH) has no PyYAML/jinja2/pydantic, so:

- `req` (a bare symlink → `hooks/requirements-cli.py`) and the 16 lifecycle hooks run under
  ambient python3 and silently fail-open on `import yaml` — the framework degrades to a no-op
  with no signal.
- `./sync.sh deploy` aborts at its render step (`python3 scripts/render_prompts.py` needs
  jinja2 — observed this session).
- The test suite only runs under a hand-assembled `uv run --with pyyaml --with pydantic --with jinja2`.

The infrastructure to fix this **already exists but nothing routes through it**: `pyproject.toml`
+ `uv.lock` + a uv-managed `.venv` (cpython-3.13.9, uv 0.8.17). The `.venv` is itself stale
(has `yaml`, missing `jinja2`/`pydantic`, no `pip`). And `hooks/langfuse-trace.py` already
demonstrates the correct pattern: a stdlib wrapper that re-execs its real work under `uv run`.

**Goal:** make `uv` the single, deterministic provider of interpreter + dependencies for every
execution path — dev, build, test, CI, and runtime — so nothing ever depends on ambient python
again. Decisions (confirmed with user): route dev tooling **and** runtime through uv; declare
build/test deps as a lightweight `dev` group; runtime hooks/CLI self-bootstrap per call via `uv run`.

## Key facts (verified against source)

- Dependency tiers (per `pyproject.toml` + the CI comment in `.github/workflows/ci.yml`):
  - **core**: `PyYAML` (config parsing). This is all the 15 lifecycle hooks + `requirements-cli.py`
    import at runtime — confirmed: no top-level hook imports `jinja2`/`pydantic`; `messages.py`
    renders with `yaml`+`re`, not jinja2.
  - **light build/test half**: `pydantic` + `jinja2` (imported by in-suite V3 tests like
    `test_supervisor_config_driven` and by `scripts/render_prompts.py`), plus `ruff==0.12.12`.
    `pydantic` is currently a **direct import that is undeclared** (only transitive via `llm`).
  - **heavy `llm` extra**: torch/sentence-transformers/ragas/llama-index — untouched; opt-in only.
- Hook preamble is uniform: shebang → stdlib imports → `lib_path = Path(__file__).parent/'lib'`
  → `sys.path.insert(0, str(lib_path))` → first dep-bearing import. Clean insertion point.
- Bootstrap target set = **15 lifecycle hooks + `requirements-cli.py`**. Excluded: `test_*.py`
  (run via `uv run`; they need the dev group, not just PyYAML), `_langfuse_hook.py` (PEP-723,
  already `uv run --script`), `langfuse-trace.py` (already self-manages under uv).

## Approach

### Tier 1 — dev / build / test / CI through uv

**1. `pyproject.toml`: declare a lightweight dev group + fix the pydantic gap.**
Add a uv **dependency-group** (auto-synced by `uv run`/`uv sync`, no `--extra` needed) — this is
the idiomatic home for dev-time tooling and makes `uv run` frictionless:
```toml
[dependency-groups]
dev = ["pydantic>=2", "jinja2>=3.1", "ruff==0.12.12"]
```
Keep the heavy `llm` extra as-is. Regenerate `uv.lock` (`uv lock`). Ensure `.venv/` and uv caches
are gitignored (verify — `.venv` currently is not).

**2. `sync.sh`: route the render step through uv.**
`python3 "$REPO_DIR/scripts/render_prompts.py"` → `uv run --project "$REPO_DIR" python scripts/render_prompts.py`.
Same for any other `python3 …` build calls in `sync.sh`.

**3. `install.sh`: make uv a prerequisite + sync on install.**
- Fail loudly if `uv` is not on PATH (with the install one-liner), consistent with strict-preflight
  already requiring uv.
- Run `uv sync` to materialize `.venv` during install.
- The `req` shim can stay a symlink — the runtime self-bootstrap (Tier 2) handles the interpreter.

**4. CI (`.github/workflows/ci.yml`, and `publish.yml` if it installs deps): replace pip with uv.**
- `astral-sh/setup-uv` instead of the manual `pip install pyyaml pydantic jinja2 ruff==0.12.12`.
- `uv sync` (auto-includes the `dev` group), then every step via `uv run`:
  `uv run ruff check .`, `uv run python hooks/requirements-cli.py doctor …`,
  `uv run python hooks/test_requirements.py`, `uv run python scripts/render_prompts.py --check`,
  and the `tests/` suite. Kills the pyproject↔CI dep drift (the hand-maintained pip list becomes
  the `dev` group).

### Tier 2 — runtime (hooks + `req` CLI) self-bootstrap under uv

**5. New `hooks/lib/_bootstrap.py` (stdlib-only).**
A dependency-sentinel re-exec — cheap when the env is already correct, self-healing when not:
```python
import os, shutil, sys

def ensure(packages=("PyYAML>=6.0",)):
    """Guarantee runtime deps by re-execing under `uv run` iff they're missing."""
    try:
        import yaml  # noqa: F401  — core-dep sentinel
        return                      # already provisioned (dev .venv, CI uv sync, good ambient)
    except ImportError:
        pass
    uv = shutil.which("uv")
    if uv is None or os.environ.get("RF_UV_BOOTSTRAPPED") == "1":
        return                      # no uv, or already retried → fail-open (framework design)
    os.environ["RF_UV_BOOTSTRAPPED"] = "1"
    os.execvp(uv, [uv, "run", *(f"--with={p}" for p in packages), "python",
                   sys.argv[0], *sys.argv[1:]])   # replaces process; stdin/argv/exit preserved
```
Why this shape:
- **No-op in the common good case** — when `yaml` already imports (CI under `uv sync`, dev under
  `.venv`, or a correctly provisioned ambient python) there is zero re-exec, zero uv overhead.
- **Self-heals** only when `yaml` is missing AND `uv` exists (exactly the user's broken-ambient
  case) — one `uv run` re-exec, cached after warm.
- **Invocation-agnostic** — works whether launched via shebang, `python x.py`, or the `req`
  symlink (guard lives inside the module, not the shebang). `RF_UV_BOOTSTRAPPED` prevents any loop.
- `--with PyYAML` suffices for all 16 targets (verified: none import jinja2/pydantic at runtime).

**6. Call it in all 16 targets**, immediately after `sys.path.insert(0, str(lib_path))` and before
the first dep-bearing import:
```python
sys.path.insert(0, str(lib_path))
import _bootstrap; _bootstrap.ensure()
```
`_bootstrap.py` ships in `lib/` so it lands in the plugin bundle and `~/.claude/hooks/lib` via the
existing copy paths.

**7. Rebuild plugin bundle + version bump + deploy.**
`python3 scripts/build_plugin_hooks.py` (regenerates the twins incl. `_bootstrap.py`), bump
`plugins/requirements-framework/.claude-plugin/plugin.json` (minor), `./sync.sh deploy`.

### Docs / ADR

**8.** Update `CLAUDE.md` "Build & Test Commands" to the `uv run …` forms; add a short "uv is
required" note. Write a brief ADR (`docs/adr/ADR-021-uv-standardization.md`) recording the
decision and the self-bootstrap rationale.

## Critical files
- `pyproject.toml`, `uv.lock`, `.gitignore`
- `sync.sh`, `install.sh`
- `.github/workflows/ci.yml` (+ `publish.yml` if it installs deps)
- `hooks/lib/_bootstrap.py` (new) + the 16 targets (15 lifecycle hooks + `requirements-cli.py`)
- `plugins/requirements-framework/.claude-plugin/plugin.json`, regenerated `plugins/**/hooks/**`
- `CLAUDE.md`, `docs/adr/ADR-021-*.md`

## Non-goals
- Not touching the heavy `llm` extra or how V3 scripts run (they already use uv).
- Not adopting `env -S uv run --script` shebangs (rejected: breaks when a caller invokes via
  explicit `python`, e.g. CI; the in-module sentinel guard is invocation-agnostic).
- Not pinning hooks to an absolute `.venv/bin/python` (rejected per user: not portable to the
  marketplace plugin running in arbitrary projects).

## Tests
- `hooks/test_requirements.py` (register in `main()`): unit-test `_bootstrap.ensure()` —
  (a) returns without re-exec when `yaml` is importable (monkeypatch to simulate present);
  (b) with the `RF_UV_BOOTSTRAPPED` guard set it never execs even when the sentinel is missing.
  (The actual `execvp` path is asserted via a fake `execvp`/`which` injection, not a real re-exec.)
- Keep the full suite green under `uv run python hooks/test_requirements.py`.

## Verification (end-to-end, reproduces the exact breakage)
1. **Broken-ambient repro**: the user's `~/.local/bin/python3` already lacks PyYAML. Pipe a
   SessionStart/PreToolUse payload to a hook via that interpreter:
   `~/.local/bin/python3 hooks/check-requirements.py < payload` → **before**: fail-open / no gate;
   **after**: `_bootstrap.ensure()` re-execs under uv and the gate fires (deny). Prove the flip.
2. **`req` works from a bare shell**: `req status` in a configured project returns real status
   (not a yaml ImportError / empty), driven by the same re-exec.
3. **`./sync.sh deploy`** completes including the render step (no jinja2 abort).
4. **CI parity locally**: `uv sync && uv run ruff check . && uv run python hooks/test_requirements.py
   && uv run python scripts/render_prompts.py --check` all green — no `--with` juggling.
5. **No-op proof**: under `uv run` (yaml present), confirm a hook does **not** re-exec
   (e.g. `RF_UV_BOOTSTRAPPED` stays unset), so the common path pays no uv penalty.

## Suggested patch sequence (stg, branch off origin/master)
1. `pyproject` dev group + `uv lock` + `.gitignore`.
2. `sync.sh` + `install.sh` uv routing.
3. CI/publish workflows → setup-uv + `uv sync` + `uv run`.
4. `hooks/lib/_bootstrap.py` + wire into the 16 targets + tests.
5. Rebuild bundle + `plugin.json` minor bump.
6. `CLAUDE.md` + ADR-021.
