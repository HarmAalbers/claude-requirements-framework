# ADR-021: Standardize Python Execution on `uv`

## Status

Approved (2026-07-06).

## Context

Every Python entrypoint in the framework — the 16 lifecycle hooks, the `req` CLI (a
symlink to `hooks/requirements-cli.py`), and the build/test tooling (`sync.sh`,
`update-plugin-versions.sh`, `scripts/render_prompts.py`, the test suites) — historically
shebanged `#!/usr/bin/env python3` and **trusted the ambient interpreter to already have
the right packages installed**. Those packages (`PyYAML`, plus `jinja2`/`pydantic` for the
build/test half) lived in per-developer pyenv/`.venv` site-packages that were never
declared as the source of truth.

When a batch of those stale environments was deleted, the fragility surfaced: the ambient
`python3` first on PATH (`~/.local/bin/python3`) had no `PyYAML`, so:

- The `req` CLI and the config-loading hooks silently **fail-open** on `import yaml` — the
  framework degrades to a no-op with no signal (the same "silent absence" failure ADR-020
  fights, here from a dependency gap rather than a config gap).
- `./sync.sh deploy` aborts at its render step (`python3 scripts/render_prompts.py` needs
  `jinja2`).
- The test suite only ran under a hand-assembled `uv run --with pyyaml --with pydantic --with jinja2`.

The infrastructure to fix this already existed but nothing routed through it: `pyproject.toml`
+ `uv.lock` + a uv-managed `.venv`. And `hooks/langfuse-trace.py` already demonstrated the
correct pattern — a stdlib wrapper that re-execs its real work under `uv run`.

## Decision

Make **`uv` the single, deterministic provider of interpreter + dependencies for every
execution path** — dev, build, test, CI, and runtime.

1. **Single source of dependency truth**: `pyproject.toml` + `uv.lock`.
   - Core runtime dep stays `PyYAML` (verified: no hook or the CLI imports `jinja2`/`pydantic`
     at runtime; message rendering uses `yaml`+`re`).
   - New lightweight `[dependency-groups].dev = {pydantic, jinja2, ruff==0.12.12}` — the
     "light half" the build (template rendering) and in-suite V3 tests need, auto-synced by
     `uv run`/`uv sync` without `--extra`. `pydantic` was previously a direct-but-undeclared
     import. The heavy `[llm]` extra (torch/sentence-transformers/ragas) stays opt-in.

2. **Dev/build/test/CI through uv**: `sync.sh` and `update-plugin-versions.sh` render via
   `uv run`; `install.sh` requires `uv` and runs `uv sync`; CI/publish workflows use
   `astral-sh/setup-uv` + `uv sync` + `uv run` (replacing the hand-maintained
   `pip install …` list, eliminating pyproject↔CI drift).

3. **Runtime self-bootstrap** (`hooks/lib/_bootstrap.py`): a stdlib sentinel that each hook
   and the CLI call right after `sys.path` setup. If `import yaml` fails **and** `uv` is on
   PATH, it re-execs the entrypoint once under `uv run --no-project --with PyYAML`. Chosen
   over the alternatives:
   - vs an `#!/usr/bin/env -S uv run --script` shebang — rejected: bypassed whenever a caller
     invokes via explicit `python …` (e.g. CI). The in-module sentinel is invocation-agnostic.
   - vs pinning hooks to an absolute `.venv/bin/python` at install time — rejected: not
     portable to the marketplace plugin running in arbitrary projects.

## Consequences

- **Reproducible everywhere**: a fresh machine with only `uv` runs the whole framework, the
  test suite, and CI identically. `uv sync && uv run python hooks/test_requirements.py` — no
  `--with` juggling.
- **Self-healing runtime**: a broken/incomplete ambient python no longer silently disables
  the framework; hooks re-exec under uv and function. Verified: piping an `ExitPlanMode`
  payload to `check-requirements.py` under a yaml-less `python3` now returns `deny` instead
  of fail-open.
- **Zero overhead on the good path**: the sentinel `import yaml` short-circuits when deps are
  already present (dev `.venv`, CI `uv sync`, or a correct ambient python) — no re-exec, no
  uv spawn. Cost is paid only in the broken-ambient case.
- **`uv` is now a hard prerequisite** (`install.sh` fails without it) — consistent with
  strict-preflight (ADR-020) and the R5 observability hook already requiring it.
- **Fail-open preserved**: if `uv` is absent, `ensure()` returns and the caller proceeds; a
  later missing-dep import degrades exactly as before. `RF_UV_BOOTSTRAPPED` guards against loops.

## Notes

- `--no-project` keeps the re-exec isolated: a hook firing inside some *other* python project
  never triggers a sync of that project's dependencies.
- The runtime bootstrap only provisions `PyYAML`; the `dev`/`llm` groups are a dev/CI concern,
  not a runtime one.
