# Troubleshooting Guide

Solutions for common Requirements Framework issues.

## Quick Diagnostics

Run these commands first:

```bash
req doctor          # Comprehensive diagnostics
req verify          # Quick installation check
req status          # Current requirement status
req sessions        # Active sessions
```

---

## Hook Not Triggering

### Symptoms
- Requirements not blocking Edit/Write
- No error messages appearing
- Hook seems inactive

### Checklist

1. **On main/master branch?**
   - By design, some configurations skip these branches
   - Check if `protected_branch` guard is configured

2. **Config enabled?**
   ```bash
   cat .claude/requirements.yaml | grep enabled
   # Should show: enabled: true
   ```

3. **Specific requirement enabled?**
   ```bash
   req config plan_validated
   # Check: enabled: true
   ```

4. **Plugin installed and hooks registered?**

   Hook registration is **plugin-owned** — the plugin's `hooks.json` (resolved via
   `${CLAUDE_PLUGIN_ROOT}`) is the single source of truth. There is no
   `~/.claude/hooks` deploy and no `hooks` block in `~/.claude/settings.json`.
   ```bash
   req doctor        # Validates hooks.json + the scripts it registers
   /plugin           # Confirm requirements-framework is installed & enabled
   ```

5. **Wildcard permissions?**
   - Check if `Edit(*)` or `Write(*)` in `permissions.allow`
   - These bypass hooks entirely

6. **Skip flag set?**
   ```bash
   echo $CLAUDE_SKIP_REQUIREMENTS
   # Should be empty or not set
   echo $RF_STRICT_OFF
   # If "true", the strict-preflight kill-switch is active
   ```

### Resolution

```bash
# Validate plugin hook integrity
req doctor --verbose

# Reinstall the plugin if hooks are missing
# /plugin uninstall requirements-framework@requirements-framework
# /plugin marketplace update requirements-framework
# /plugin install requirements-framework@requirements-framework
```

---

## Session Not Found

### Symptoms
- `req satisfy` fails with "session not found"
- CLI can't auto-detect session

### Causes
- Running from terminal outside Claude session
- Session registry out of sync
- Stale session entries

### Resolution

```bash
# List active sessions
req sessions

# Use explicit session ID
req satisfy plan_validated --session <id-from-above>

# Clean stale sessions
req prune

# Check session registry
cat ~/.claude/sessions.json
```

---

## Plugin Changes Not Taking Effect

### Symptoms
- Changes to framework not taking effect
- Different behavior than expected
- `req doctor` reports hook issues

### Notes

The framework runs as a **self-contained plugin** — there is no `sync.sh` and no
`~/.claude/hooks` deploy step. Hooks load from the installed plugin via
`${CLAUDE_PLUGIN_ROOT}`.

### Resolution

```bash
# Validate plugin hook integrity
req doctor --verbose

# For local development, launch Claude Code with the repo plugin (live reload):
#   claude --plugin-dir ~/Tools/claude-requirements-framework/plugin

# For an installed plugin, reinstall to pick up the latest version:
#   /plugin uninstall requirements-framework@requirements-framework
#   /plugin marketplace update requirements-framework
#   /plugin install requirements-framework@requirements-framework
```

---

## Permission Denied

### Symptoms
- Requirement blocking file modifications
- Can't proceed with edits

### Resolution

```bash
# Check which requirement is blocking
req status

# Satisfy the requirement
req satisfy <requirement_name>

# Or temporarily disable
req config <requirement_name> --disable --local
```

---

## Tests Failing

Tests are run through `uv` from the repo (never a bare `python3` — the ambient
interpreter may lack `PyYAML` and the dev deps).

### Debugging

```bash
cd ~/Tools/claude-requirements-framework

# One-time: sync the uv-managed environment
uv sync

# Run the test suite
uv run python hooks/test_requirements.py

# Lint (pinned ruff, matches CI)
uv run ruff check .
```

### Common Causes

1. **Ran with bare `python3`** - Missing PyYAML/dev deps; use `uv run`
2. **Env not synced** - Run `uv sync` first
3. **Import errors** - `lib/` modules not on path (run from repo root via uv)
4. **Python version** - Requires 3.9+

---

## Error Messages Explained

### "Plan not validated for this session"

**Cause**: `plan_validated` requirement enabled but not satisfied (the Validate node).
Note: `commit_plan`, `adr_reviewed`, `tdd_planned`, and `solid_reviewed` were all
consolidated into `plan_validated` under ADR-022.

**Solution**:
1. Run the Validate team: `/requirements-framework:arch-review` (auto-satisfies `plan_validated`)
2. Or, as the user: `req satisfy plan_validated`

### "Session not found"

**Cause**: CLI can't auto-detect current session

**Solution**:
```bash
req sessions                  # Find session ID
req satisfy plan_validated --session <id>
```

### "Cannot edit files on protected branch"

**Cause**: Guard requirement blocking edits on main/master

**Solution**:
```bash
# Create feature branch
git checkout -b feature/your-feature

# Or emergency override (temporary)
req approve protected_branch
```

### "Branch has X changes (threshold: Y)"

**Cause**: Dynamic branch size limit exceeded

**Solution**:
- Split work into smaller PRs
- Or temporarily increase threshold:
  ```bash
  req config branch_size_limit --set threshold=600 --local
  ```

---

## Temporarily Disabling Requirements

### Option 1: Local Override (per project)

```yaml
# .claude/requirements.local.yaml
enabled: false
```

### Option 2: Environment Variable

```bash
export CLAUDE_SKIP_REQUIREMENTS=1
```

### Option 3: Disable Specific Requirement

```bash
req config plan_validated --disable --local
```

### Option 4: Pause Gates for This Session

```bash
req pause      # Blocking gates paused until session end (Claude may run this)
req resume     # Undo
```

---

## Configuration Not Loading

### Symptoms
- Changes to `.claude/requirements.yaml` ignored
- Default settings used instead

### Debugging

```bash
# Check config files exist
ls -la .claude/requirements.yaml
ls -la .claude/requirements.local.yaml
ls -la ~/.claude/requirements.yaml

# View effective config (and where each value came from)
req config
req config --sources

# Check YAML syntax (via uv)
uv run python -c "import yaml; yaml.safe_load(open('.claude/requirements.yaml'))"
```

> A project with **only** `.claude/requirements.local.yaml` (no committed
> `requirements.yaml`) is fully recognized — the local layer alone is enough.

### Common Causes

1. **YAML syntax errors** - Invalid indentation or formatting
2. **Wrong location** - File not in `.claude/` directory
3. **Inheritance issues** - `inherit: false` blocking global config

---

## Report Issues

If problems persist:

1. Run `req doctor --verbose` and capture output
2. Check logs: `tail -50 ~/.claude/requirements.log`
3. Check test suite (from the repo): `uv run python hooks/test_requirements.py`
4. Report at: https://github.com/HarmAalbers/claude-requirements-framework/issues

Include:
- `req doctor` output
- Relevant log entries
- Steps to reproduce
- Expected vs actual behavior
