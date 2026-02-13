---
name: commit-checks
description: "Auto-fix code quality issues - comment cleanup and import organization"
argument-hint: "[--skip-autofix]"
allowed-tools: ["Bash", "Glob", "Grep", "Read", "Task"]
git_hash: 6c6f980
---

# Pre-Commit Auto-Fix

Runs 2 auto-fix agents to clean up code before committing. Comments are cleaned and imports are organized, then changes are re-staged.

**Arguments:** "$ARGUMENTS"

## Agent Overview

| # | Agent | Focus | Auto-fix |
|---|-------|-------|----------|
| 1 | comment-cleaner | Remove useless comments | Yes |
| 2 | import-organizer | Move imports to top | Yes |

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
```

Set applicability flags based on detection results:
- **HAS_PYTHON** = true if /tmp/has_python.txt is not empty
- **HAS_CODE** = true if /tmp/has_code.txt is not empty

### Step 4: Execute Auto-Fix Agents (Sequential)

If SKIP_AUTOFIX is false AND HAS_CODE is true:

**4a. Run comment-cleaner**
1. Use the Task tool to launch subagent_type="requirements-framework:comment-cleaner"
2. Prompt: "Clean up useless comments in staged files. Read /tmp/commit_check_scope.txt for file list."
3. Wait for completion
4. Store results for reporting

**4b. Run import-organizer**
If HAS_PYTHON is true:
1. Use the Task tool to launch subagent_type="requirements-framework:import-organizer"
2. Prompt: "Organize imports in staged Python files. Read /tmp/commit_check_scope.txt for file list."
3. Wait for completion
4. Store results for reporting

**4c. Re-stage modified files**
After auto-fix agents complete, re-stage only the files from the original scope:

```bash
while IFS= read -r f; do git add "$f"; done < /tmp/commit_check_scope.txt
```

If SKIP_AUTOFIX is true:
- Skip to Step 5
- Note: "Auto-fix skipped per --skip-autofix flag"

### Step 5: Report Results

Output the report using this format:

```markdown
# Pre-Commit Auto-Fix Report

## Scope
- Files checked: X
- Agents run: [list]

## Auto-Fixes Applied
| Agent | Action | Files |
|-------|--------|-------|
| comment-cleaner | Removed X comments | Y files |
| import-organizer | Reorganized imports | Z files |

## Result
READY TO COMMIT - Auto-fixes applied and staged.
```

If SKIP_AUTOFIX was true, replace the Auto-Fixes and Result sections with:
```
## Auto-Fixes
Skipped per --skip-autofix flag. No files were modified.

## Result
Scope reported. No auto-fixes applied.
```

## Usage

```bash
/requirements-framework:commit-checks              # Full check with auto-fix
/requirements-framework:commit-checks --skip-autofix  # Skip auto-fix, just report scope
```

## Tips

- Run early to catch issues before they compound
- Use `--skip-autofix` to check which files are in scope without modifying them
- Auto-fix agents will re-stage modified files automatically
- For deeper analysis, use `/requirements-framework:pre-commit` or `/requirements-framework:quality-check`
