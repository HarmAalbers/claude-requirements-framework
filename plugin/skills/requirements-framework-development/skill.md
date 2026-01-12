---
name: requirements-framework-development
description: This skill should be used when the user asks to "develop requirements framework", "fix requirements framework bug", "sync requirements framework", "pull/deploy requirements changes", "update framework code", "test framework changes", or needs help with the framework development workflow including sync.sh usage, TDD for framework itself, and contributing changes.
git_hash: 000fe23
---

# Requirements Framework Development

Guide for developing, fixing, and maintaining the **Claude Code Requirements Framework** with proper sync workflow between repository and deployed installation.

**Repository**: `~/tools/claude-requirements-framework` (git-controlled source of truth)
**Deployed**: `~/.claude/hooks/` (active runtime environment)
**Remote**: https://github.com/HarmAalbers/claude-requirements-framework.git

## Core Concept: Two-Location Architecture

The framework lives in TWO places that must stay synchronized:

1. **Repository** (`~/tools/claude-requirements-framework/`)
   - Git version control
   - Source of truth
   - Where you make planned changes

2. **Deployed** (`~/.claude/hooks/`)
   - Active runtime (where Claude Code loads hooks)
   - Where framework actually executes
   - Where you can make emergency fixes

## sync.sh - The Essential Tool

**Location**: `~/tools/claude-requirements-framework/sync.sh`

### Commands

```bash
cd ~/tools/claude-requirements-framework

# Check sync status (ALWAYS run this first)
./sync.sh status

# Deploy: Repository → ~/.claude/hooks
./sync.sh deploy

# Pull: ~/.claude/hooks → Repository
./sync.sh pull

# Show differences
./sync.sh diff
```

### sync.sh status Output

```
📊 Sync Status
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Repository:  ~/tools/claude-requirements-framework
Deployed:    ~/.claude/hooks

File Status:
  ✓ check-requirements.py - In sync
  ↑ requirements-cli.py - Repository is newer (run deploy)
  ↓ test_requirements.py - Deployed is newer (run pull)
  ⚠ lib/config.py - Not deployed
```

**Symbols**:
- `✓` = In sync (no action needed)
- `↑` = Repository newer (run `./sync.sh deploy`)
- `↓` = Deployed newer (run `./sync.sh pull` then commit)
- `⚠` = File missing in one location

## Development Workflows

### Workflow A: Standard Development (Planned Changes)

**Pattern**: Edit in repository → Deploy → Test → Commit → Push

```bash
# 1. Start in repository
cd ~/tools/claude-requirements-framework

# 2. Make changes to code
vim hooks/lib/requirement_strategies.py

# 3. Deploy to active installation
./sync.sh deploy

# 4. Run tests
python3 ~/.claude/hooks/test_requirements.py

# 5. Test in real Claude session (optional)
# - Try triggering the hook by editing a file
# - Verify behavior matches expectations

# 6. Commit changes
git add .
git commit -m "feat: Add new feature"
git push origin master
```

**When to use**: Feature development, refactoring, planned improvements

---

### Workflow B: Quick Fix in Production (Emergency)

**Pattern**: Edit in ~/.claude/hooks → Test → Pull → Commit → Push

```bash
# 1. Fix directly in deployed location
vim ~/.claude/hooks/check-requirements.py

# 2. Test immediately (no deploy needed - already active!)
python3 ~/.claude/hooks/test_requirements.py

# 3. Verify fix works in Claude session

# 4. Pull changes back to repository
cd ~/tools/claude-requirements-framework
./sync.sh pull

# 5. Commit and push
git add .
git commit -m "fix: Emergency bug fix"
git push origin master
```

**When to use**: Critical bugs blocking work, quick patches, user is actively blocked

---

### Workflow C: Claude-Driven Development

**Pattern**: Claude edits in ~/.claude/hooks → Pull → Commit → Push

**This is the workflow we just used!**

```bash
# 1. Claude makes changes to deployed files
# (Claude edited ~/.claude/hooks/lib/message_dedup_cache.py)

# 2. Pull to repository
cd ~/tools/claude-requirements-framework
./sync.sh pull

# 3. Commit
git add .
git commit -m "feat: Your commit message"

# 4. Push
git push origin master
```

**When to use**: When Claude is developing features, fixing bugs found in analysis, implementing improvements

---

### Workflow D: Test-Driven Development

**Pattern**: Write tests in repo → Deploy → RED → Implement → Deploy → GREEN → Commit

```bash
# 1. Write failing test in repository
cd ~/tools/claude-requirements-framework
vim hooks/test_requirements.py  # Add new test

# 2. Deploy tests
./sync.sh deploy

# 3. Run tests (RED - should fail)
python3 ~/.claude/hooks/test_requirements.py
# Expected: New test fails

# 4. Implement feature in repository
vim hooks/lib/requirements.py

# 5. Deploy implementation
./sync.sh deploy

# 6. Run tests (GREEN - should pass)
python3 ~/.claude/hooks/test_requirements.py
# Expected: All tests pass

# 7. Refactor if needed (keep tests green)

# 8. Commit when done
git add .
git commit -m "feat: Add feature (TDD)"
git push
```

**When to use**: Adding new features, refactoring with safety net

---

## File Sync Reference

The sync.sh script automatically syncs these files:

### Hook Files
- `check-requirements.py` - PreToolUse hook entry point
- `requirements-cli.py` - CLI tool (req command)
- `test_requirements.py` - Test suite

### Library Files (hooks/lib/)
- `__init__.py` - Package marker
- `branch_size_calculator.py` - Dynamic requirement calculator
- `calculation_cache.py` - TTL cache for calculations
- `calculator_interface.py` - Abstract calculator base class
- `config.py` - Configuration loader (YAML/JSON cascade)
- `git_utils.py` - Git operations
- `message_dedup_cache.py` - Message deduplication (new in v2.1)
- `requirement_strategies.py` - Strategy pattern for requirement types
- `requirements.py` - Requirement state management
- `session.py` - Session registry and tracking
- `state_storage.py` - Persistent state storage

## Common Tasks for Agents

### Task: Fix Bug in Framework

**Steps**:
1. Identify which file contains the bug
2. Check sync status: `cd ~/tools/claude-requirements-framework && ./sync.sh status`
3. If deployed is newer, pull first: `./sync.sh pull`
4. Edit the file in repository
5. Deploy: `./sync.sh deploy`
6. Run tests: `python3 ~/.claude/hooks/test_requirements.py`
7. Test in Claude session to verify fix
8. Commit: `git add . && git commit -m "fix: Description"`
9. Push: `git push origin master`

### Task: Add New Feature

**Steps**:
1. Check sync status (pull if needed)
2. Write tests first (TDD): Edit `hooks/test_requirements.py` in repo
3. Deploy tests: `./sync.sh deploy`
4. Run tests (should fail - RED)
5. Implement feature in repository
6. Deploy implementation: `./sync.sh deploy`
7. Run tests (should pass - GREEN)
8. Commit and push

### Task: Update Documentation

**Steps**:
1. Update relevant doc files in repository:
   - `README.md` - User-facing documentation
   - `DEVELOPMENT.md` - Development workflow
   - `docs/README-REQUIREMENTS-FRAMEWORK.md` - Detailed user guide
2. Commit docs separately: `git commit -m "docs: Description"`
3. Push: `git push origin master`

### Task: Sync After Claude Made Changes

**This is what you do after Claude fixes bugs or adds features!**

```bash
# 1. Claude edited files in ~/.claude/hooks/
# (This happens when Claude develops in the active location)

# 2. Pull changes to repository
cd ~/tools/claude-requirements-framework
./sync.sh pull

# 3. Review what changed
git diff

# 4. Run tests to verify
python3 hooks/test_requirements.py

# 5. Commit if tests pass
git add .
git commit -m "feat: <description of what Claude built>"
git push origin master
```

**Example**: We just did this for message deduplication!

---

## Testing

### Unit Tests

**Location**: `hooks/test_requirements.py` (89 tests)

**Run from deployed**:
```bash
python3 ~/.claude/hooks/test_requirements.py
```

**Run from repository**:
```bash
cd ~/tools/claude-requirements-framework
python3 hooks/test_requirements.py
```

**Expected output**:
```
🧪 Requirements Framework Test Suite
==================================================
Testing Configuration Loading...
  ✓ test_load_yaml_config (0.001s)
  ✓ test_load_json_config (0.001s)
  ... [87 more tests]

==================================================
Results: 89/89 tests passed ✓
Time: 2.5s
```

### Integration Testing

Test in real Claude Code session:

```bash
# 1. Enable requirements in a project
cd ~/some-project
cat > .claude/requirements.yaml <<EOF
version: "1.0"
enabled: true
requirements:
  commit_plan:
    enabled: true
    scope: session
EOF

# 2. Start Claude Code and try to edit a file
# Should be blocked with requirement message

# 3. Satisfy requirement
req satisfy commit_plan

# 4. Try to edit again
# Should work now
```

## Troubleshooting

### Problem: Changes not taking effect

**Symptoms**: You edited code but behavior didn't change

**Solutions**:
1. Check which location you edited: `pwd`
2. If you edited in repo: `./sync.sh deploy`
3. If you edited in ~/.claude/hooks: File should be active immediately
4. Check file actually changed: `./sync.sh diff`
5. Restart Claude Code session if needed

### Problem: Sync status shows conflicts

**Symptoms**: Both `↑` (repo newer) and `↓` (deployed newer) for different files

**Solution**:
```bash
# Check what's different
./sync.sh diff

# Choose direction based on which changes to keep:
# - Keep repo changes: ./sync.sh deploy
# - Keep deployed changes: ./sync.sh pull
# - Manual merge if both have important changes
```

### Problem: Tests fail after deploy

**Symptoms**: Tests passed in one location, fail in other

**Debugging**:
```bash
# 1. Check file permissions
ls -la ~/.claude/hooks/check-requirements.py
# Should be: -rwx--x--x (executable)

# 2. Check Python import paths
python3 -c "import sys; print(sys.path)"

# 3. Run test with verbose output
python3 ~/.claude/hooks/test_requirements.py -v

# 4. Check for missing files
./sync.sh status
```

### Problem: Git merge conflicts after pull

**Symptoms**: Someone else pushed while you were working

**Solution**:
```bash
cd ~/tools/claude-requirements-framework

# 1. Stash local changes
git stash

# 2. Pull remote changes
git pull origin master

# 3. Reapply your changes
git stash pop

# 4. Resolve conflicts if any

# 5. Deploy merged version
./sync.sh deploy

# 6. Test
python3 ~/.claude/hooks/test_requirements.py

# 7. Commit merge
git add .
git commit -m "merge: Resolve conflicts"
git push
```

## Quick Reference for Agents

### When Claude needs to fix a bug:

```bash
# Fix in deployed location (immediate effect)
vim ~/.claude/hooks/lib/FILE.py

# Pull to repo
cd ~/tools/claude-requirements-framework && ./sync.sh pull

# Commit
git add . && git commit -m "fix: Bug description" && git push
```

### When Claude adds a feature:

```bash
# Pull any recent changes first
cd ~/tools/claude-requirements-framework && ./sync.sh pull

# Edit in repo
vim hooks/lib/FILE.py

# Deploy and test
./sync.sh deploy && python3 ~/.claude/hooks/test_requirements.py

# Commit and push
git add . && git commit -m "feat: Feature description" && git push
```

### After ANY code changes:

```bash
# ALWAYS check sync status
cd ~/tools/claude-requirements-framework
./sync.sh status

# If deployed is newer (↓), pull first
./sync.sh pull

# Then commit
git add . && git commit -m "Message" && git push
```

## Best Practices for Agents

1. **Check sync status BEFORE committing** - Always run `./sync.sh status`
2. **Pull before editing in repo** - Ensure you have latest from deployed: `./sync.sh pull`
3. **Deploy after editing in repo** - Make changes active: `./sync.sh deploy`
4. **Test after every change** - Run: `python3 ~/.claude/hooks/test_requirements.py`
5. **Commit atomically** - One logical change per commit
6. **Use conventional commits** - `feat:`, `fix:`, `docs:`, `test:`

## Key Files (from latest sync)

Recently synced files include:
- `hooks/lib/message_dedup_cache.py` (NEW - deduplication cache)
- `hooks/lib/requirement_strategies.py` (MODIFIED - integrated deduplication)
- `hooks/check-requirements.py` (hook entry point)
- `hooks/requirements-cli.py` (CLI tool)
- `hooks/test_requirements.py` (test suite)

## Debugging sync.sh

If sync.sh itself has issues:

```bash
# Check if executable
ls -la ~/tools/claude-requirements-framework/sync.sh
# Should be: -rwx--x--x

# Make executable if needed
chmod +x ~/tools/claude-requirements-framework/sync.sh

# Run with bash explicitly
bash ~/tools/claude-requirements-framework/sync.sh status
```

## Golden Rules

1. **Repository is source of truth** - Always commit from here
2. **Deployed is active** - Changes here take effect immediately
3. **sync.sh keeps them aligned** - Use it liberally
4. **Pull before you push** - Check sync status first
5. **Test after every sync** - Run test suite to verify

## Example: Full Development Cycle

```bash
# Scenario: Add new requirement type

# 1. Pull latest
cd ~/tools/claude-requirements-framework
./sync.sh pull

# 2. Write test (TDD)
vim hooks/test_requirements.py
# Add test_new_requirement_type()

# 3. Deploy and run test (RED)
./sync.sh deploy
python3 ~/.claude/hooks/test_requirements.py
# Expected: 89/90 tests passed (new test fails)

# 4. Implement feature
vim hooks/lib/requirement_strategies.py

# 5. Deploy and run test (GREEN)
./sync.sh deploy
python3 ~/.claude/hooks/test_requirements.py
# Expected: 90/90 tests passed

# 6. Integration test in Claude
# Try using the new requirement type

# 7. Commit
git add .
git commit -m "feat(strategies): Add new requirement type"

# 8. Push
git push origin master

# 9. Verify sync
./sync.sh status
# Should show: All files in sync
```

## Documentation Structure

Update these files when changing the framework:

| File | Purpose | Update When |
|------|---------|-------------|
| `README.md` | User guide, quick start | Adding user-facing features |
| `DEVELOPMENT.md` | Development workflow | Changing dev process or tools |
| `docs/README-REQUIREMENTS-FRAMEWORK.md` | Detailed user docs | Configuration changes |
| `docs/implementation-plan.md` | Original build plan | Historical reference only |

## Common Agent Tasks

### When User Says: "Fix the hook spam issue"

1. Edit `~/.claude/hooks/check-requirements.py` or relevant file
2. Test: `python3 ~/.claude/hooks/test_requirements.py`
3. Pull to repo: `cd ~/tools/claude-requirements-framework && ./sync.sh pull`
4. Commit: `git add . && git commit -m "fix: Hook spam issue"`
5. Push: `git push`

### When User Says: "Add debug mode to the framework"

1. Check sync: `cd ~/tools/claude-requirements-framework && ./sync.sh status`
2. Pull if needed: `./sync.sh pull`
3. Edit in repo: `vim hooks/lib/config.py`
4. Deploy: `./sync.sh deploy`
5. Test: `python3 ~/.claude/hooks/test_requirements.py`
6. Commit and push

### When User Says: "The framework broke, help!"

1. Check deployed version: `ls -la ~/.claude/hooks/`
2. Check sync: `cd ~/tools/claude-requirements-framework && ./sync.sh status`
3. Check tests: `python3 ~/.claude/hooks/test_requirements.py`
4. If tests fail, check recent changes: `git log -5 --oneline`
5. If needed, revert: `git revert HEAD && ./sync.sh deploy`

## Integration with User's CLAUDE.md

The user's global CLAUDE.md has rules:
- "We always work TDD"
- "Plan files are never committed"
- "Always use commit agent with skills when planning code changes"

**Apply these when developing the framework itself**:
- Write tests first for new features
- Use EnterPlanMode for non-trivial changes
- Keep plan files in `~/.claude/plans/` (excluded from commits)

## Advanced: sync.sh Internals

The script syncs these file patterns:

```bash
# Main hooks
check-requirements.py
requirements-cli.py
test_requirements.py

# Library modules (hooks/lib/)
*.py files in lib/ directory
```

**It does NOT sync**:
- Example files (`examples/`)
- Documentation (`docs/`, `README.md`)
- Scripts (`sync.sh`, `install.sh`)
- Git files (`.git/`, `.gitignore`)

**Why?** These are repo-only files that don't need to be deployed to `~/.claude/hooks/`.

## Workflow Summary

| Scenario | Location to Edit | Sync Command | When to Commit |
|----------|-----------------|--------------|----------------|
| Planned feature | Repository | `./sync.sh deploy` | After testing |
| Emergency fix | `~/.claude/hooks/` | `./sync.sh pull` | After fix verified |
| Claude developed | `~/.claude/hooks/` | `./sync.sh pull` | Immediately after |
| TDD development | Repository | `./sync.sh deploy` | After GREEN phase |

**Remember**: `./sync.sh status` is your friend - run it frequently!
