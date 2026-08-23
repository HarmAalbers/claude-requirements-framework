# ADR-024: The Statusline Bootstraps Under uv

**Status:** Amended by ADR-025
**Date:** 2026-08-23
**Related:** ADR-021 (uv standardization) — extends the self-heal to the one entrypoint it had skipped

> **Amended the same day by [ADR-025](ADR-025-workflow-cache-in-state-file.md).** The diagnosis and
> measurements below stand, and the `_find_uv` probe still matters for every other entrypoint. What
> changed is the mechanism: the alternative this ADR called *"genuinely the better end state"* and
> then declined to build was built. The unconditional re-exec is now a cache-miss fallback, and the
> statusline's common path costs 27ms rather than 79ms.

## Context

`hooks/lib/_bootstrap.py::ensure()` guarantees PyYAML by re-execing under `uv run --no-project --with PyYAML` when the ambient interpreter lacks it. Every one of the 14 hook entrypoints and the `req` CLI calls it.

`hooks/lib/statusline_data.py` did not — and it is the single hottest Python entrypoint in the framework. Both statuslines invoke it with a bare `python3`:

- `~/.claude/statusline-command.sh:877` — the active statusline on this machine, pointed at the repo working tree
- `plugins/requirements-framework/statusline.sh:56` — the plugin's own, for installed users

On this machine `python3` resolves to `~/.local/bin/python3`, which has no PyYAML. So `derive_phase._resolve_workflow` failed on **every render**: `RequirementsConfig` loaded, `config_utils.load_yaml` hit its `ImportError` branch, returned `{}`, and derivation silently fell back to the module constants `PHASE_GATES` / `DEFAULT_PHASE` / `SHIP_PHASE`.

Two consequences, one of which hid the other:

1. **The log flood.** That `ImportError` branch logged at *error* level — three lines per render, 85221 lines between 17 June and 23 August, in a 20MB log. Fixed separately by demoting it to debug, which is what made the second consequence visible.
2. **The silent wrong answer.** The fallback constants are kept byte-for-byte in sync with `WORKFLOW_DEFAULTS`, so a zero-config project sees a correct phase and nothing looks wrong. A project that defines its own `workflow:` section gets the *default* phase name in its statusline instead of its own, with no error, no log line at a level anyone reads, and no way to tell from the statusline that config was never consulted.

The file's own docstring argues against fixing it: *"Python startup is the dominant cost — two invocations doubles the lag."* That reasoning is why the gap was left open, and it is why the decision needed measuring rather than asserting.

## Decision

`statusline_data.py` calls `_bootstrap.ensure()` before importing `derive_phase`.

Measured on this machine, warm uv cache, 12 renders averaged:

| path | per render |
|---|---|
| bare `python3`, before | 35 ms |
| bare `python3`, after (re-exec fires) | 79 ms |
| interpreter that already has PyYAML (no re-exec) | 53 ms |

So the honest cost is **+44 ms per render on a machine with a broken ambient python**, and **zero** on one whose `python3` can import yaml — the sentinel check short-circuits before any `uv` process is spawned. A statusline that reports the wrong phase is not cheaper than one that takes 44 ms longer, and the cost is removable by provisioning the ambient interpreter rather than by accepting a wrong answer.

`_bootstrap._find_uv()` additionally probes `~/.local/bin/uv` when `shutil.which("uv")` comes up empty, mirroring `hooks/langfuse-trace.py::_find_uv`. GUI-launched sessions (the desktop app, a terminal spawned by launchd) inherit a bare PATH without `~/.local/bin`, which is where the official uv installer puts the binary — on exactly those machines the self-heal would otherwise never have fired at all. `langfuse-trace.py` stays a self-contained PEP-723 script and cannot import this module, so the duplication is deliberate.

Fail-open is unchanged. When uv is missing entirely, `ensure()` returns and derivation falls back to the constants exactly as before — the worst case is today's behaviour, not a new one.

## Alternatives considered

**Keep the fail-open path and document that config is optional there.** Free, and honest about a limitation, but it leaves a class of project permanently misinformed by its own statusline, and the failure is invisible by construction — the fallback is *designed* to look normal. Documenting a silent wrong answer does not make it a right one.

**Cache the resolved phase list into `.git/requirements/<branch>.json`.** Hooks have PyYAML; they could write the resolved workflow into the state file for the statusline to read with stdlib `json`. Correct *and* free at render time, and genuinely the better end state. Rejected for now as disproportionate: it changes the state schema, adds a staleness question (config edited, no hook fired yet), and buys 44 ms on one hot path. Worth revisiting if the statusline ever needs more config than the phase list.

**Point the statusline shell scripts at an interpreter that has PyYAML.** The framework does not control `~/.claude/statusline-command.sh` (a user file) and cannot assume a `.venv` exists next to an installed plugin. Fixing it per-machine also leaves the next machine broken. `ensure()` is the right layer precisely because it is invocation-agnostic.

## Consequences

- A project with a custom `workflow:` section now sees its own phase names in the statusline.
- Renders cost +44 ms where the ambient python lacks PyYAML; nothing where it does not.
- `config_utils.load_yaml`'s ImportError branch is now reached only when uv is *also* unavailable. Its comment says so; if that stops being true, the comment is the thing that lied.
- `hooks/test_requirements.py` guards both halves: `_find_uv` finds a `~/.local/bin/uv` absent from PATH (and refuses a non-executable one), and `statusline_data.py` resolves a custom `workflow:` when run under `uv run --no-project --isolated` from outside the repo — an environment that genuinely has no PyYAML. The second test was verified to fail when `ensure()` is removed.
