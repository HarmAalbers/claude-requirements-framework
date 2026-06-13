#!/usr/bin/env bash
# Phase-aware statusline for Claude Code.
# Reads Claude's stdin JSON, derives the workflow phase from the
# requirements-framework state file, and emits a single line.
#
# Format:  [phase] [ctx N%] [$cost] [N req⬜]
# Fail-open: any tool/file failure degrades a single field to `?`,
# never errors out (Claude Code would hide a non-zero exit script).

set -uo pipefail

INPUT=$(cat)

# Locate the plugin's bundled hook libs. The plugin is self-contained
# (commit 652141b): the libs live under $PLUGIN_ROOT/hooks/lib in both the
# --plugin-dir dev layout and the global cached install.
# $CLAUDE_PLUGIN_ROOT is set when invoked through Claude Code's plugin loader;
# otherwise (e.g. the install.sh settings-runner path) we anchor on $0.
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "$0")" && pwd)}"
HOOK_LIB="${PLUGIN_ROOT}/hooks/lib"

# CWD detection: prefer Claude's reported workspace.
CWD=$(printf '%s' "$INPUT" | jq -r '.workspace.current_dir // .cwd // "."' 2>/dev/null || echo ".")

# Phase + count default to safe placeholders.
PHASE="design"
UNSAT="?"

BRANCH=$(git -C "$CWD" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")
if [[ -n "$BRANCH" ]]; then
  # Mirror branch_to_filename() in hooks/lib/state_storage.py:
  # slash → dash, then keep [A-Za-z0-9_-] (anything else → underscore).
  SAFE_BRANCH=$(printf '%s' "$BRANCH" | tr '/\\' '--' | tr -c '[:alnum:]_-' '_')
  STATE_FILE="$CWD/.git/requirements/${SAFE_BRANCH}.json"

  if [[ -f "$STATE_FILE" ]]; then
    # One python invocation: prints "<phase> <unsatisfied_count>".
    # PYTHONPATH lets statusline_data.py import its siblings.
    read -r PHASE UNSAT < <(
      PYTHONPATH="$HOOK_LIB" python3 "$HOOK_LIB/statusline_data.py" "$STATE_FILE" 2>/dev/null
    ) || true
    [[ -z "${PHASE:-}" ]] && PHASE="design"
    [[ -z "${UNSAT:-}" ]] && UNSAT="?"
  fi
fi

# Context % (input-side, the only one Claude Code currently exposes).
CTX=$(printf '%s' "$INPUT" | jq -r '.context_window.used_percentage // 0' 2>/dev/null | awk '{printf "%d", $1}')
[[ -z "$CTX" ]] && CTX="0"

# Session cost in USD.
COST=$(printf '%s' "$INPUT" | jq -r '.session.cost_usd // 0' 2>/dev/null | awk '{printf "%.2f", $1}')
[[ -z "$COST" ]] && COST="0.00"

printf "[%s] [ctx %s%%] [\$%s] [%s req⬜]" "$PHASE" "$CTX" "$COST" "$UNSAT"
