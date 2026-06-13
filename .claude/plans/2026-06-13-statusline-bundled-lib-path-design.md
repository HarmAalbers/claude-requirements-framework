# Statusline bundled-lib path fix + regression guard — design

**Date:** 2026-06-13
**Branch:** `fix/statusline-bundled-lib-path`
**Status:** design approved

## Problem

`plugins/requirements-framework/statusline.sh` resolves its hook libs via
`$PLUGIN_ROOT/../../../hooks/lib` (→ `/Users/harm/Tools/hooks/lib`, nonexistent)
with a dead `~/.claude/hooks/lib` fallback. Since commit `652141b` made the
plugin self-contained, the libs are bundled at `$PLUGIN_ROOT/hooks/lib`. The
script fail-opens, so the phase and req-count fields silently render as
`[design]` / `[? req⬜]` on **every** render — the two computed fields are dead.

Confirmed live: direct `statusline_data.py master.json` → `ship 0`, but
`statusline.sh` renders `[design] [? req⬜]`. The bundled lib copies are
byte-identical to `hooks/lib/` and produce correct output when the path points
at `$PLUGIN_ROOT/hooks/lib`.

Root cause class: a fail-open script + no test that invokes `statusline.sh`
itself (existing tests only exercise the Python helpers), so the path break was
invisible.

## Change 1 — fix the path (`statusline.sh`)

Replace the lib-resolution block with a single bundled-first lookup:

```bash
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "$0")" && pwd)}"
HOOK_LIB="${PLUGIN_ROOT}/hooks/lib"
```

Correct for both layouts: `--plugin-dir` dev
(`plugins/requirements-framework/hooks/lib`) and the global cached install
(`~/.claude/plugins/.../requirements-framework/hooks/lib`). The two stale
fallbacks are deleted (no-backwards-compat-shims rule). Rest of the script is
unchanged; it stays fail-open (`set -uo pipefail`, per-field `?` degradation).

## Change 2 — regression guard (`hooks/test_requirements.py`)

Two layers (per user decision "Both"):

- `test_statusline_bundled_libs_present` — asserts `statusline_data.py`,
  `derive_phase.py`, `count_unsatisfied.py` all exist under the plugin's bundled
  `hooks/lib`. Catches a future build-copy that forgets to bundle them.
- `test_statusline_script_end_to_end` — `subprocess` runs `statusline.sh`,
  piping sample JSON, with `CLAUDE_PLUGIN_ROOT` set to the plugin dir and a tmp
  fixture state file (some gates satisfied). Asserts the rendered phase/count
  reflect the real state, i.e. it does NOT degrade to the `[design]`/`[? req⬜]`
  placeholder. This is the test that would have caught `652141b`.

Both registered in the run list next to `test_count_unsatisfied`. TDD: red
against the unfixed script, green after.

## Change 3 — plugin version bump

Patch bump in `plugins/requirements-framework/.claude-plugin/plugin.json`
(4.19.1 → 4.19.2), in the same patch as the fix per the bundled-version rule.

## Out of scope (deferred items confirmed blocked)

- `[✓ similar]` retrieval tag — needs unmerged V3 retrieval (`retrieval.json`).
- Output-side context % — upstream Claude Code issue #11535.
- Pure-jq rewrite (~100ms) — rejected in `docs/STATUSLINE.md`.

`docs/STATUSLINE.md` is still accurate; no doc changes needed.
