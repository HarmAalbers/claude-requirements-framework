# ADR-003: Dynamic File Discovery in sync.sh

## Status
Accepted

## Date
2024-12-16

## Context

The `sync.sh` script synchronizes files between the git repository and the deployed location (`~/.claude/hooks`). Originally, it used a hardcoded list of files:

```bash
local files_to_check=(
    "check-requirements.py"
    "requirements-cli.py"
    "test_requirements.py"
    # ... etc
)
```

This approach had problems:
1. **Files missed**: New files like `ruff_check.py` and `test_branch_size_calculator.py` weren't synced
2. **Maintenance burden**: Every new file required manual updates to the script
3. **Silent failures**: Missing files weren't detected until something broke

## Decision

Use dynamic file discovery with `find` and glob patterns instead of hardcoded lists.

### Implementation

```bash
# Get all Python files from a directory
get_py_files() {
    local dir="$1"
    local prefix="$2"
    if [ -d "$dir" ]; then
        find "$dir" -maxdepth 1 -name "*.py" -type f 2>/dev/null | while read -r f; do
            echo "${prefix}$(basename "$f")"
        done
    fi
}

# Get all files to sync (union of repo and deployed)
get_all_files() {
    {
        get_py_files "$REPO_DIR/hooks" ""
        get_py_files "$DEPLOY_DIR" ""
        get_py_files "$REPO_DIR/hooks/lib" "lib/"
        get_py_files "$DEPLOY_DIR/lib" "lib/"
    } | sort -u
}
```

### Key Features
1. **Union of both locations**: Discovers files that exist in either repo OR deployed
2. **Detects missing files**: Shows "Missing in repository" or "Not deployed" for files in only one location
3. **Automatic discovery**: New `.py` files are automatically included
4. **lib/ subdirectory support**: Handles nested lib directory correctly

## Consequences

### Positive
- New files are automatically included in sync operations
- Missing files are clearly reported in status output
- No maintenance required when adding new hook files
- Follows "convention over configuration" principle

### Negative
- Slightly more complex script logic
- Could potentially sync unwanted `.py` files (mitigated by using specific directories)

### Neutral
- Existing workflows unchanged (deploy/pull/status/diff commands work the same)

## Files Added in This Change
- `hooks/ruff_check.py` - Ruff linter hook (was in deployed but not repo)
- `hooks/test_branch_size_calculator.py` - Branch size calculator tests (was in deployed but not repo)
