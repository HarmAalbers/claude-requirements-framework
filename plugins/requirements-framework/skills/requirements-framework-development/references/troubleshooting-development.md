# Troubleshooting Development

Solutions for common development issues with the Requirements Framework.

> All Python runs through **`uv`** (ADR-021) — never bare `python3` (the only
> exception is `statusline.sh`). The runtime is the plugin at
> `plugins/requirements-framework/`; the bundle under
> `plugins/requirements-framework/hooks/` is a **build-copy** of `hooks/`
> produced by `scripts/build_plugin_hooks.py`. There is no `~/.claude/hooks`
> deployment and no `sync.sh`.

## Test Failures

### Tests Behave Differently From the Running Plugin

**Symptoms**: A change works when you run the test suite from `hooks/`, but the
live plugin doesn't reflect it (or vice versa).

**Cause**: The plugin bundle is stale — you edited `hooks/` but never rebuilt.

**Solution**:
```bash
cd ~/Tools/claude-requirements-framework

# 1. Check whether the bundle drifted from hooks/
uv run python scripts/build_plugin_hooks.py --check

# 2. Rebuild if drift is reported
uv run python scripts/build_plugin_hooks.py

# 3. Run tests from source
uv run python hooks/test_requirements.py

# 4. Start a fresh --plugin-dir session to reload the runtime
```

### Import Errors

**Symptoms**: `ModuleNotFoundError: No module named 'lib.something'`

**Solution**:
```bash
# Confirm the module exists in source
ls hooks/lib/requirements.py

# Ensure the uv env is synced (missing deps surface as import errors)
uv sync

# Rebuild the bundle so it matches source, then retest
uv run python scripts/build_plugin_hooks.py
uv run python hooks/test_requirements.py
```

### Test State Conflicts

**Symptoms**: Tests fail due to leftover state files.

**Solution**:
```bash
# Clean test artifacts
rm -rf /tmp/test-requirements-*

# Run tests fresh
uv run python hooks/test_requirements.py
```

---

## Hook Not Working

### Hook Not Triggering

**Check 1: Plugin Loaded**
```bash
# Hooks only fire when the plugin is loaded. In development, launch with:
claude --plugin-dir ~/Tools/claude-requirements-framework/plugins/requirements-framework
```

**Check 2: Hook Registration**
```bash
# Registration is owned by the plugin, NOT ~/.claude/settings*.json
cat plugins/requirements-framework/hooks/hooks.json

# Every lifecycle hook is wired here via ${CLAUDE_PLUGIN_ROOT}
```

**Check 3: Bundle Is Current**
```bash
# A stale bundle can run old hook code
uv run python scripts/build_plugin_hooks.py --check
uv run python scripts/build_plugin_hooks.py   # rebuild if drift
```

**Check 4: Python Syntax**
```bash
uv run python -m py_compile hooks/check-requirements.py
```

### Hook Errors Not Visible

**Symptoms**: Hook seems to do nothing, no errors shown.

**Solution**:
```bash
# Enable debug logging
req logging --level debug --local

# View logs
tail -f ~/.claude/requirements.log

# Reproduce the action, then check log output
```

---

## Bundle Issues

### build_plugin_hooks.py --check Reports Drift

**Symptoms**: `--check` exits non-zero (missing / stale-extra / content-differs).

**Cause**: The bundle no longer matches `hooks/` — usually because source was
edited without a rebuild, or a stray file was added to the bundle.

**Solution**:
```bash
# Rebuild to reconcile the bundle with source
uv run python scripts/build_plugin_hooks.py

# Verify it is now clean
uv run python scripts/build_plugin_hooks.py --check
```

### Prompt Changes Not Reflected

**Symptoms**: You edited a command/agent/skill prompt but the plugin shows the
old text.

**Cause**: You edited a rendered `.md` (which is regenerated) instead of its
`.md.j2` source, or you edited the `.md.j2` but never re-rendered.

**Solution**:
```bash
# 1. Edit the *.md.j2 template, not the rendered *.md
# 2. Re-render
uv run python scripts/render_prompts.py
# 3. Reload in a fresh --plugin-dir session
```

---

## Git Issues

### Never Use git commit — Use Stacked Git

This project authors every local commit through **Stacked Git (`stg`)**.

```bash
# Per-branch setup (once)
git checkout -b feat/your-branch
stg init

# Atomic patches
stg new <patch-name>   # opens editor for description
# ... edit files ...
stg refresh            # fold working-tree changes into the top patch
```

### Detached HEAD

**Solution**:
```bash
git checkout master

# If you have changes, stash first
git stash
git checkout master
git stash pop
```

### Merge Conflicts

**Solution**:
```bash
# Integrate remote work
git pull --rebase origin master

# Resolve conflicts (files marked <<<<< ===== >>>>>), then continue
git add .
git rebase --continue

# Rebuild the bundle (source may have changed) and retest
uv run python scripts/build_plugin_hooks.py
uv run python hooks/test_requirements.py
```

---

## Performance Issues

### Hooks Running Slowly

**Symptoms**: Claude operations feel sluggish.

**Solution**:
```bash
# Check cache configuration
req config branch_size_limit

# Look for slow operations in the log
grep "slow\|timeout\|delay" ~/.claude/requirements.log
```

### Tests Running Slowly

**Solution**:
```bash
# Run a specific test category
uv run python hooks/test_requirements.py -k "test_session"

# Skip slow tests during development
uv run python hooks/test_requirements.py -k "not slow"
```

---

## Development Environment

### uv Not Found / Wrong Interpreter

**Symptoms**: Import errors, missing PyYAML, or "python3 has no module …".

**Cause**: Something ran under the ambient `python3` instead of the uv-managed
env. Every entrypoint must run via `uv run`.

**Solution**:
```bash
# Materialize the uv env once
uv sync

# Always prefix Python with `uv run`
uv run python hooks/test_requirements.py
```

### Editor Not Recognizing Types

**Symptoms**: IDE shows type errors that don't affect runtime.

**Solution**:
```bash
# Point the IDE at the uv-managed interpreter
uv run python -c "import sys; print(sys.executable)"
# Use that path as the IDE's interpreter
```

---

## Recovery Procedures

### Reconcile a Broken Bundle

If the bundle is in a confusing state:

```bash
cd ~/Tools/claude-requirements-framework

# 1. Rebuild straight from source (hooks/ is the source of truth)
uv run python scripts/build_plugin_hooks.py

# 2. Re-render prompts
uv run python scripts/render_prompts.py

# 3. Verify bundle is clean and tests pass
uv run python scripts/build_plugin_hooks.py --check
uv run python hooks/test_requirements.py
```

### Inspect a Previous Version

```bash
cd ~/Tools/claude-requirements-framework

# See recent commits
git log --oneline -10

# Inspect a specific commit's source without moving your branch
git show <commit-hash>:hooks/lib/requirements.py

# Or check it out on a scratch branch, rebuild, and test
git checkout -b scratch-<hash> <commit-hash>
uv run python scripts/build_plugin_hooks.py
uv run python hooks/test_requirements.py
```

---

## Debugging Tips

### Add Debug Logging

```python
# In any hook or library file
from lib.logger import logger

logger.debug("Variable value", extra={"variable": value})
```

### View Logs in Real-Time

```bash
# Terminal 1: Tail logs
tail -f ~/.claude/requirements.log

# Terminal 2: Work in Claude Code
# Logs appear in Terminal 1
```

### Run a Hook Manually

```bash
# Feed a hook synthetic stdin and inspect the result, all under uv
echo '{"tool_name":"Edit","tool_input":{"file_path":"/test/file.py"},"session_id":"test123"}' \
  | uv run python hooks/check-requirements.py
```
