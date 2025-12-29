# Installation Friction Points Found

## Issues Discovered During Fresh Reinstallation

### 1. ✅ FIXED: Missing Hook Files in install.sh
**Status**: Fixed in commit 63a35d9

**Problem**:
- `install.sh` was missing 4 hook files in the copy commands:
  - `auto-satisfy-skills.py`
  - `clear-single-use.py`
  - `handle-plan-exit.py`
  - `ruff_check.py`
- These files existed in repo and were made executable by `chmod` commands
- But they were never copied to `~/.claude/hooks/`
- Installation would fail with: `chmod: No such file or directory`

**Root Cause**:
Files were added to repo but not added to install script's copy section

**Fix Applied**:
Added missing `cp -v` commands for all 4 files in install.sh:25-36

---

### 2. ✅ FIXED: SessionStart Hook Test Hangs

**Status**: Fixed in commit 6c02813

**Problem**:
- Install script test #5 hangs indefinitely at "Testing SessionStart hook..."
- Line 509 of install.sh: `python3 "$HOME/.claude/hooks/handle-session-start.py"`
- The hook expects JSON input on stdin but gets none
- `sys.stdin.read()` blocks waiting for input
- Process must be manually killed
- Shows as failure in output: `./install.sh: line 514: 14833 Terminated: 15`

**Evidence from user's install output**:
```
5️⃣  Testing SessionStart hook...
./install.sh: line 514: 14833 Terminated: 15          python3 "$HOME/.claude/hooks/handle-session-start.py" > /dev/null 2>&1
   ❌ SessionStart hook failed
```

**Root Cause**:
SessionStart hook at hooks/handle-session-start.py:133 calls `sys.stdin.read()` which blocks when no stdin provided

**Fix Applied**:
Changed install.sh line 509 from:
```bash
if python3 "$HOME/.claude/hooks/handle-session-start.py" > /dev/null 2>&1; then
```
to:
```bash
if echo '{}' | python3 "$HOME/.claude/hooks/handle-session-start.py" > /dev/null 2>&1; then
```

**Testing**:
```bash
$ echo '{}' | python3 ~/.claude/hooks/handle-session-start.py
📋 **Requirements Framework Status**
✓ Hook executes successfully and instantly
```

**Impact**: High - Test no longer hangs, installation completes smoothly

---

### 3. ✅ FIXED: disableAllHooks in settings.json

**Status**: Fixed in commit 6c02813

**Problem**:
- User's `~/.claude/settings.json` has `"disableAllHooks": true`
- Install script registers hooks in `settings.local.json`
- Hooks are registered correctly but won't actually run
- User may be confused why hooks don't work after installation

**Evidence**:
```json
{
  "hooks": {},
  "disableAllHooks": true,
  ...
}
```

**Root Cause**:
- This is user configuration (not a bug)
- But install script doesn't check for or warn about this setting

**Fix Applied**:
Added check in install.sh after verification tests:
```bash
# Check if hooks are globally disabled in settings.json
echo ""
if grep -q '"disableAllHooks"[[:space:]]*:[[:space:]]*true' "$HOME/.claude/settings.json" 2>/dev/null; then
    echo "⚠️  WARNING: Hooks are globally disabled"
    echo "   Your hooks are registered but won't run because ~/.claude/settings.json has:"
    echo "   \"disableAllHooks\": true"
    echo ""
    echo "   To enable hooks, edit ~/.claude/settings.json and change to:"
    echo "   \"disableAllHooks\": false"
    echo ""
fi
```

**Impact**: Medium - Users now clearly warned when hooks won't work

---

### 4. ℹ️ INFO: test_branch_size_calculator.py Not Deployed

**Status**: Expected behavior, but shown as warning in sync

**Problem**:
- `./sync.sh status` shows: `⚠ test_branch_size_calculator.py - Not deployed`
- This is correct (test files shouldn't be deployed)
- But it appears as a warning, suggesting something is wrong

**Evidence**:
```
Sync Status:
  ✓ 27/28 files deployed and in sync
  ⚠ test_branch_size_calculator.py - Not deployed (exists in repository)
```

**Root Cause**:
- sync.sh treats any file in repo but not deployed as a warning
- Test files are intentionally not deployed

**Proposed Enhancement**:
- Add ignore pattern in sync.sh for test files
- Or change warning message: "⚠" → "ℹ (test file, not deployed)"

**Impact**: Low - cosmetic issue only

---

### 5. ✅ FIXED: 'req' Command Test Fails

**Status**: Fixed in commit 442581b

**Problem**:
- Test #3 reports: `⚠️ 'req' command found but failed to run`
- The `req` command exists and is in PATH
- But the test considers it a failure
- However, manual testing shows `req status` works perfectly

**Evidence from user's install output**:
```
3️⃣  Checking 'req' command...
   ⚠️  'req' command found but failed to run
```

**Evidence from manual testing**:
```bash
$ req status
📋 Requirements Status
Branch: master
✅ All requirements satisfied
```

**Root Cause**:
The symlink at `~/.local/bin/req` failed because requirements-cli.py used `Path(__file__).parent` to find the lib directory, which doesn't follow symlinks. When run via symlink:
- `__file__` = `/Users/harm/.local/bin/req` (symlink location)
- Looked for lib at `/Users/harm/.local/bin/lib` (doesn't exist)
- Failed with: `ModuleNotFoundError: No module named 'requirements'`

**Fix Applied**:
Changed line 25 in hooks/requirements-cli.py from:
```python
lib_path = Path(__file__).parent / 'lib'
```
to:
```python
lib_path = Path(__file__).resolve().parent / 'lib'
```

The `.resolve()` method follows symlinks to the actual file location at `~/.claude/hooks/`, where `lib/` exists.

**Testing**:
```bash
$ ~/.local/bin/req --help
usage: req [-h] {status,satisfy,clear,...
✓ Works perfectly
```

**Impact**: Medium - Fixed installation test failure and made symlink work correctly

---

## Summary of Required Fixes

### High Priority - All Fixed! ✅
1. ✅ **install.sh missing files** - FIXED (63a35d9)
2. ✅ **SessionStart test hangs** - FIXED (6c02813)
3. ✅ **req command symlink fails** - FIXED (442581b)

### Medium Priority - All Fixed! ✅
4. ✅ **No warning about disableAllHooks** - FIXED (6c02813)

### Low Priority
5. ℹ️ **Test file shown as warning in sync** - Cosmetic improvement (not critical)

## Testing Checklist

After fixes, verify:
- [x] All hook files copy successfully
- [x] SessionStart test completes without hanging
- [x] req command symlink works correctly
- [x] Warning shown if disableAllHooks is true
- [x] All verification tests pass (or show appropriate warnings)
- [x] Installation completes in < 30 seconds

## Commits
- `63a35d9` - fix: copy all required hook files in install.sh
- `6c02813` - fix: improve install.sh verification and user warnings
- `442581b` - fix: resolve symlinks when finding lib directory in req CLI

## Related Files

- `install.sh` - Main installation script
- `hooks/handle-session-start.py` - SessionStart hook that expects stdin
- `sync.sh` - Deployment sync checker
- `~/.claude/settings.json` - Global settings (user-controlled)
- `~/.claude/settings.local.json` - Hook registrations (managed by installer)
