# Sync Deployment Checklist

## Critical Reminder
**Always run `./sync.sh status` before committing** to ensure new or modified files are properly deployed.

## Two-Location System
The framework exists in two places that must stay synchronized:

| Source | Destination | Content |
|--------|-------------|---------|
| `hooks/` | `~/.claude/hooks/` | Python hooks + library |
| `plugin/` | `~/.claude/plugins/requirements-framework/` | Agents, commands, skills |

## Common Issues

### New Files Not Available
If a new command/agent isn't working after adding it:
1. Run `./sync.sh status` - look for "Not deployed" warnings
2. Run `./sync.sh deploy` to sync
3. Restart Claude Code to pick up plugin changes

### Deleted Files Still Present
The deploy script copies files but doesn't remove orphaned files in the deployed location (except for skills which are fully replaced).

Check for orphans:
```bash
# Files in deployed but not in repo
./sync.sh status | grep "Missing in repository"
```

## Workflow
1. Make changes in repository
2. Run `./sync.sh status` to verify what needs deployment
3. Run `./sync.sh deploy` 
4. For plugin changes: restart Claude Code
5. Commit changes

## File Counts (Quick Sanity Check)
When in doubt, compare file counts:
```bash
# Hooks
ls hooks/*.py | wc -l
ls ~/.claude/hooks/*.py | wc -l

# Agents  
ls plugin/agents/*.md | wc -l
ls ~/.claude/plugins/requirements-framework/agents/*.md | wc -l

# Commands
ls plugin/commands/*.md | wc -l
ls ~/.claude/plugins/requirements-framework/commands/*.md | wc -l
```
