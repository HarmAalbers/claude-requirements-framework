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

### 2. ⚠️ ACTIVE: SessionStart Hook Test Hangs

**Status**: Not fixed yet

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

**Proposed Fix**:
```bash
# Current (line 509):
if python3 "$HOME/.claude/hooks/handle-session-start.py" > /dev/null 2>&1; then

# Fixed:
if echo '{}' | python3 "$HOME/.claude/hooks/handle-session-start.py" > /dev/null 2>&1; then
```

**Testing**:
```bash
$ echo '{}' | python3 ~/.claude/hooks/handle-session-start.py
✓ Works - hook executes successfully with empty JSON input
```

**Files to Change**:
- `install.sh` line 509

---

### 3. ℹ️ INFO: disableAllHooks in settings.json

**Status**: Not an error, but potentially confusing

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

**Proposed Enhancement**:
Add a verification check after installation:
```bash
# Check if hooks are globally disabled
if grep -q '"disableAllHooks".*true' "$HOME/.claude/settings.json" 2>/dev/null; then
    echo ""
    echo "⚠️  WARNING: Hooks are globally disabled in ~/.claude/settings.json"
    echo "   Your hooks are registered but won't run until you set:"
    echo "   \"disableAllHooks\": false"
    echo ""
fi
```

**Impact**: Medium - hooks appear installed but don't work

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

### 5. ⚠️ ACTIVE: 'req' Command Test Fails

**Status**: Not fixed yet

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
Test runs `req --help &> /dev/null` at install.sh:485
The command actually works fine and returns proper help text
This might be a timing issue or environment issue during installation
Need further investigation - manual test shows it works

**Proposed Fix**:
Change test to use `req status` instead of `req --help` (more realistic):
```bash
if req status &> /dev/null; then
```

**Impact**: Low - causes confusing warning but doesn't affect functionality

---

## Summary of Required Fixes

### High Priority
1. ✅ **install.sh missing files** - FIXED
2. ⚠️ **SessionStart test hangs** - Needs fix

### Medium Priority
3. ⚠️ **No warning about disableAllHooks** - Enhancement recommended

### Low Priority
4. ℹ️ **Test file shown as warning in sync** - Cosmetic improvement

## Testing Checklist

After fixes, verify:
- [ ] All hook files copy successfully
- [ ] SessionStart test completes without hanging
- [ ] Warning shown if disableAllHooks is true
- [ ] All verification tests pass
- [ ] Installation completes in < 30 seconds

## Related Files

- `install.sh` - Main installation script
- `hooks/handle-session-start.py` - SessionStart hook that expects stdin
- `sync.sh` - Deployment sync checker
- `~/.claude/settings.json` - Global settings (user-controlled)
- `~/.claude/settings.local.json` - Hook registrations (managed by installer)
