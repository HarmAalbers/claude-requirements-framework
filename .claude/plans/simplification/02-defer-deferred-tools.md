# Step 02 — Default `ENABLE_TOOL_SEARCH=true`

## Goal

Make on-demand tool discovery the default for new installs. Reduces initial context by ~3,000 tokens of deferred-tool descriptions.

## Why now

Already supported by Claude Code v2.0.74+. Already documented in `CLAUDE.md`. Just not the default. Pure config change.

## Files touched

- `install.sh` — append `ENABLE_TOOL_SEARCH=true` to user's `~/.zshrc` if missing (with confirmation)
- `README.md` — note the new default and rationale
- `CLAUDE.md` — promote the existing "Token Efficiency" section from optional to standard

## Implementation

1. In `install.sh`, add detection block:
   ```bash
   if ! grep -q "ENABLE_TOOL_SEARCH" ~/.zshrc 2>/dev/null; then
     echo "" >> ~/.zshrc
     echo "# Reduce Claude Code context size (added by requirements-framework installer)" >> ~/.zshrc
     echo "export ENABLE_TOOL_SEARCH=true" >> ~/.zshrc
     echo "Note: added ENABLE_TOOL_SEARCH=true to ~/.zshrc. Reload your shell."
   fi
   ```
2. Detect bash users (`$SHELL`) and write to `~/.bashrc` instead.
3. Print a clear message instructing the user to `source ~/.zshrc` or open a new terminal.

## Example

**Before install**: User's `~/.zshrc` has no Claude Code env vars. Initial Claude Code context dumps full schemas of ~30 deferred tools.

**After install**: `~/.zshrc` has `export ENABLE_TOOL_SEARCH=true`. Initial context shows only tool *names*; schemas load on first use via `ToolSearch`.

## Acceptance

- [ ] `install.sh` modifies `~/.zshrc` exactly once (idempotent)
- [ ] Reopening the terminal sets `$ENABLE_TOOL_SEARCH=true`
- [ ] In a fresh Claude Code session, the initial tool list shows names only (not full schemas)
- [ ] The user can still call any deferred tool — Claude resolves the schema via `ToolSearch`

## Rollback

Remove the line from `~/.zshrc`:
```bash
sed -i '' '/ENABLE_TOOL_SEARCH=true/d' ~/.zshrc
```

## Effort

0.5 day

## Depends on

Nothing.

## Honest scope note

This **does not** reduce the "Available agent types" block at the top of the system prompt — that's a Claude Code core feature driven by `plugin.json`. To reduce that, agents would need to be split into separate plugins (a later, larger initiative).
