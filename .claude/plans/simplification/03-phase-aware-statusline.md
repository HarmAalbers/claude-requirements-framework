# Step 03 — Phase-aware statusline

## Goal

A one-line, always-visible status: current phase, context %, session cost, unsatisfied-requirement count. Replaces the need for verbose session briefings — the user can *see* state.

## Why this matters

The briefing was bulky partly because the user had no other way to know "what should I do next." A statusline solves that without spending model tokens.

## Files touched

- `statusline.sh` (new) — bash script reading Claude's JSON + requirement state
- `install.sh` — register statusline path in user's `~/.claude/settings.json`
- `docs/STATUSLINE.md` (new) — short reference for customization

## Implementation

1. Create `statusline.sh`:
   ```bash
   #!/usr/bin/env bash
   set -euo pipefail
   INPUT=$(cat)
   CWD=$(echo "$INPUT" | jq -r '.workspace.current_dir // .cwd // "."')
   BRANCH=$(git -C "$CWD" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "?")
   STATE_FILE="$CWD/.git/requirements/$BRANCH.json"
   PHASE=$(python3 "$CLAUDE_PLUGIN_ROOT/hooks/lib/derive_phase.py" "$STATE_FILE" 2>/dev/null || echo "design")
   UNSAT=$(python3 "$CLAUDE_PLUGIN_ROOT/hooks/lib/count_unsatisfied.py" "$STATE_FILE" 2>/dev/null || echo "?")
   CTX=$(echo "$INPUT" | jq -r '.context_window.used_percentage // 0' | awk '{printf "%d", $1}')
   COST=$(echo "$INPUT" | jq -r '.session.cost_usd // 0' | awk '{printf "%.2f", $1}')
   printf "[%s] [ctx %s%%] [\$%s] [%s req⬜]" "$PHASE" "$CTX" "$COST" "$UNSAT"
   ```
2. Add `hooks/lib/derive_phase.py` (pure function — see Step 05 design notes).
3. Add `hooks/lib/count_unsatisfied.py` (already exists logic — extract as one-liner CLI).
4. In `install.sh`, write to `~/.claude/settings.json`:
   ```json
   "statusLine": { "type": "command", "command": "<plugin>/statusline.sh" }
   ```

## Example

Statusline at three moments of one session:

```
session start:  [design]      [ctx 1%]  [$0.00] [13 req⬜]
after /brainstorm: [plan]     [ctx 3%]  [$0.04] [12 req⬜]
after /deep-review: [ship]    [ctx 22%] [$1.13] [ 2 req⬜]
```

## Acceptance

- [ ] Running `echo '{"workspace":{"current_dir":"."},"context_window":{"used_percentage":12},"session":{"cost_usd":0.87}}' | bash statusline.sh` prints one line
- [ ] Statusline updates within one refresh tick after a `req satisfy` command
- [ ] Statusline degrades gracefully (prints `[?]` placeholders) outside a git repo
- [ ] Total script execution time < 100ms (no perceptible lag)

## Rollback

Remove the `statusLine` block from `~/.claude/settings.json`.

## Effort

0.5 day

## Depends on

Nothing.

## Honest scope note

Per Claude Code issue #11535, output-token counts are NOT in the statusline JSON yet. We use `used_percentage` (input-side only). When/if that ships, update the script to add output-side too.
