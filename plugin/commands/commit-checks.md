---
name: commit-checks
description: "Quality checks before committing - runs 6 specialized agents"
argument-hint: "[--skip-autofix]"
allowed-tools: ["Bash", "Glob", "Grep", "Read", "Task"]
git_hash: 7d4da24
---

# Pre-Commit Quality Checks

Runs 6 specialized quality agents before committing. Auto-fix agents run first to clean up issues, then analysis agents run in parallel.

**Arguments:** "$ARGUMENTS"

## Agent Overview

| # | Agent | Focus | Auto-fix |
|---|-------|-------|----------|
| 1 | comment-cleaner | Remove useless comments | Yes |
| 2 | import-organizer | Move imports to top | Yes |
| 3 | exception-auditor | Flag bare exceptions | No |
| 4 | type-checker | Type coverage & strictness | No |
| 5 | solid-checker | SOLID principles | No |
| 6 | test-pyramid-checker | Test distribution | No |

## Deterministic Execution Workflow

You MUST follow these steps in exact order. Do not skip steps or interpret - execute as written.

### Step 1: Identify Staged Files

Execute these bash commands to get the scope:

```bash
git diff --cached --name-only --diff-filter=ACMR > /tmp/commit_check_scope.txt 2>&1
```

Check the result:
- If /tmp/commit_check_scope.txt is empty: Output "No staged changes to check" and EXIT
- Otherwise: Read the file list and continue

### Step 2: Parse Arguments

Arguments received: "$ARGUMENTS"

Initialize flags:
- **SKIP_AUTOFIX** = false
  - Set to true if: $ARGUMENTS contains "--skip-autofix" or "skip-autofix"

### Step 3: Detect File Types

Execute these commands to determine which agents apply:

```bash
# Check for Python files
grep -E '\.py$' /tmp/commit_check_scope.txt > /tmp/has_python.txt 2>&1 || true

# Check for code files (for comment cleaning)
grep -E '\.(py|js|ts|tsx|jsx|go|rs|java|c|cpp|h|hpp)$' /tmp/commit_check_scope.txt > /tmp/has_code.txt 2>&1 || true

# Check for test files
grep -E '(test_|_test\.py|\.test\.|\.spec\.)' /tmp/commit_check_scope.txt > /tmp/has_tests.txt 2>&1 || true

# Check for class definitions (for SOLID check)
git diff --cached | grep -E '^[+].*class\s+\w+' > /tmp/has_classes.txt 2>&1 || true
```

Set applicability flags based on detection results:
- **HAS_PYTHON** = true if /tmp/has_python.txt is not empty
- **HAS_CODE** = true if /tmp/has_code.txt is not empty
- **HAS_TESTS** = true if /tmp/has_tests.txt is not empty
- **HAS_CLASSES** = true if /tmp/has_classes.txt is not empty

### Step 4: Execute Auto-Fix Agents (Sequential)

If SKIP_AUTOFIX is false AND HAS_CODE is true:

**4a. Run comment-cleaner**
1. Use the Task tool to launch subagent_type="requirements-framework:comment-cleaner"
2. Prompt: "Clean up useless comments in staged files. Read /tmp/commit_check_scope.txt for file list."
3. Wait for completion
4. Store results for aggregation

**4b. Run import-organizer**
If HAS_PYTHON is true:
1. Use the Task tool to launch subagent_type="requirements-framework:import-organizer"
2. Prompt: "Organize imports in staged Python files. Read /tmp/commit_check_scope.txt for file list."
3. Wait for completion
4. Store results for aggregation

**4c. Re-stage modified files**
After auto-fix agents complete:

```bash
git add -u
```

If SKIP_AUTOFIX is true:
- Skip to Step 5
- Note: "Auto-fix skipped per --skip-autofix flag"

### Step 5: Execute Analysis Agents (Parallel)

Build agent list based on applicability:

**Required agents** (always run if applicable):
- requirements-framework:exception-auditor (if HAS_CODE)
- requirements-framework:type-checker (if HAS_PYTHON)

**Conditional agents**:
- requirements-framework:solid-checker (if HAS_CLASSES)
- requirements-framework:test-pyramid-checker (if HAS_TESTS)

**Execution:**
Launch ALL applicable agents in a SINGLE message with multiple Task tool calls:

For each agent, use prompt format:
- exception-auditor: "Audit exception handling in staged files. Focus on bare except and overly broad catches."
- type-checker: "Check type coverage and strictness in staged Python files."
- solid-checker: "Analyze staged code for SOLID principle violations."
- test-pyramid-checker: "Analyze test distribution across the test pyramid."

Wait for ALL agents to complete before proceeding.

### Step 6: Aggregate Results

After all agents complete, aggregate their findings:

1. **Count by severity across all agents**:
   - CRITICAL_COUNT = total CRITICAL issues
   - IMPORTANT_COUNT = total IMPORTANT issues
   - INFO_COUNT = total INFO/suggestions

2. **Track auto-fixes applied**:
   - Comments removed by comment-cleaner
   - Imports reorganized by import-organizer

3. **Group findings by agent**:
   - Preserve which agent found each issue
   - Include file:line references

### Step 7: Provide Verdict

Based on aggregated counts, provide ONE of these verdicts:

**If CRITICAL_COUNT > 0:**
```
❌ **FIX REQUIRED**

Critical issues must be resolved before committing:
- [ ] Issue 1 [file:line]
- [ ] Issue 2 [file:line]

Run `/requirements-framework:commit-checks` again after fixing.
```

**Else if IMPORTANT_COUNT > 3:**
```
⚠️ **REVIEW RECOMMENDED**

Several important issues found. Consider fixing before commit:
- Issue 1 [file:line]
- Issue 2 [file:line]

You can proceed, but these should be addressed.
```

**Else:**
```
✅ **READY TO COMMIT**

Code passed quality checks.
- Auto-fixes applied: X
- Issues found: Y (minor)

Safe to proceed with commit.
```

## Output Format

```markdown
# Pre-Commit Quality Check

## Scope
- Files checked: X
- Agents run: [list]

## Auto-Fixes Applied
| Agent | Action | Files |
|-------|--------|-------|
| comment-cleaner | Removed X comments | Y files |
| import-organizer | Reorganized imports | Z files |

## Critical Issues (must fix)
- [agent]: Issue [file:line]

## Important Issues (should fix)
- [agent]: Issue [file:line]

## Suggestions
- [agent]: Suggestion [file:line]

## Summary
| Check | Status |
|-------|--------|
| Useless comments | ✅ Cleaned |
| Import organization | ✅ Organized |
| Exception handling | ⚠️ 2 issues |
| Type coverage | ✅ 85% |
| SOLID principles | ✅ OK |
| Test pyramid | ✅ Healthy |

## Verdict
✅ READY TO COMMIT
```

## Usage

```bash
/requirements-framework:commit-checks              # Full check with auto-fix
/requirements-framework:commit-checks --skip-autofix  # Analysis only, no edits
```

## Integration with Requirements

This command is triggered by the `pre_commit_checks` requirement. Running it auto-satisfies the requirement, allowing the commit to proceed.

Workflow:
1. Stage changes: `git add .`
2. Attempt commit: `git commit -m "..."` → Blocked
3. Run this command: `/requirements-framework:commit-checks`
4. Fix any critical issues
5. Retry commit: `git commit -m "..."` → Success

## Tips

- Run early to catch issues before they compound
- Use `--skip-autofix` if you want to review what would be changed
- Critical issues block commit - they must be fixed
- Auto-fix agents will re-stage modified files automatically
- For speed, this runs analysis agents in parallel
