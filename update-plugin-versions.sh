#!/bin/bash

set -e  # Exit on error

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$REPO_DIR"

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Parse arguments
CHECK_MODE=false
VERIFY_MODE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --check)
            CHECK_MODE=true
            shift
            ;;
        --verify)
            VERIFY_MODE=true
            shift
            ;;
        --help|-h)
            show_usage
            exit 0
            ;;
        *)
            echo -e "${RED}Error: Unknown option '$1'${NC}"
            show_usage
            exit 1
            ;;
    esac
done

show_usage() {
    cat << EOF
Usage: $0 [OPTIONS]

Update git_hash fields in plugin component YAML frontmatter.

Options:
  --check       Dry-run mode (report changes, don't modify files)
  --verify      Verify all files have current git_hash values
  --help, -h    Show this help message

Examples:
  $0                  # Update all plugin files
  $0 --check          # Report what would change
  $0 --verify         # Verify hashes are current

EOF
}

# Function: Get git hash for a file
get_file_hash() {
    local file="$1"

    # Check if tracked by git
    if ! git ls-files --error-unmatch "$file" &>/dev/null; then
        echo "uncommitted"
        return
    fi

    # Get last commit hash for this specific file
    local hash=$(git log -1 --format=%h -- "$file" 2>/dev/null)

    if [ -z "$hash" ]; then
        echo "uncommitted"
        return
    fi

    # Check for uncommitted changes (unstaged or staged)
    if ! git diff --quiet -- "$file" 2>/dev/null || \
       ! git diff --cached --quiet -- "$file" 2>/dev/null; then
        echo "${hash}*"
    else
        echo "$hash"
    fi
}

# Function: Get current git_hash from file (for --verify mode)
get_current_hash_from_file() {
    local file="$1"

    # Extract git_hash value from YAML frontmatter
    if [ -f "$file" ]; then
        grep "^git_hash:" "$file" 2>/dev/null | awk '{print $2}' || echo ""
    else
        echo ""
    fi
}

# Function: Update git_hash in file using Python
update_file_hash() {
    local file="$1"
    local hash="$2"

    python3 - "$file" "$hash" <<'PYTHON_SCRIPT'
import re
import sys

def update_git_hash(file_path, new_hash):
    """Update or add git_hash field in YAML frontmatter"""

    try:
        with open(file_path, 'r') as f:
            content = f.read()
    except Exception as e:
        print(f"ERROR: Cannot read {file_path}: {e}", file=sys.stderr)
        return False

    # Match YAML frontmatter (--- ... ---)
    frontmatter_pattern = r'^---\n(.*?)\n---'
    match = re.search(frontmatter_pattern, content, re.DOTALL)

    if not match:
        print(f"ERROR: No YAML frontmatter found in {file_path}", file=sys.stderr)
        return False

    frontmatter = match.group(1)

    # Check if git_hash already exists
    if re.search(r'^git_hash:', frontmatter, re.MULTILINE):
        # Update existing git_hash
        updated_frontmatter = re.sub(
            r'^git_hash:.*$',
            f'git_hash: {new_hash}',
            frontmatter,
            flags=re.MULTILINE
        )
    else:
        # Add git_hash as last field (preserve structure)
        updated_frontmatter = frontmatter.rstrip() + f'\ngit_hash: {new_hash}'

    # Reconstruct file content
    updated_content = content.replace(
        f'---\n{frontmatter}\n---',
        f'---\n{updated_frontmatter}\n---'
    )

    # Write back
    try:
        with open(file_path, 'w') as f:
            f.write(updated_content)
    except Exception as e:
        print(f"ERROR: Cannot write {file_path}: {e}", file=sys.stderr)
        return False

    return True

if __name__ == '__main__':
    if len(sys.argv) != 3:
        print("Usage: python3 script.py <file_path> <new_hash>", file=sys.stderr)
        sys.exit(1)

    file_path = sys.argv[1]
    new_hash = sys.argv[2]

    success = update_git_hash(file_path, new_hash)
    sys.exit(0 if success else 1)
PYTHON_SCRIPT
}

# Main execution
main() {
    echo -e "${BLUE}🔖 Plugin Version Updater${NC}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""

    # Discover plugin component files
    if [ "$VERIFY_MODE" = true ] || [ "$CHECK_MODE" = true ]; then
        echo "Discovering plugin components..."
    else
        echo "Discovering plugin components to update..."
    fi

    local files=()

    # Find all agents
    while IFS= read -r file; do
        [ -f "$file" ] && files+=("$file")
    done < <(find plugins/requirements-framework/agents/ github-issues-plugin/agents/ -name "*.md" -type f 2>/dev/null)

    # Find all commands
    while IFS= read -r file; do
        [ -f "$file" ] && files+=("$file")
    done < <(find plugins/requirements-framework/commands/ -name "*.md" -type f 2>/dev/null)

    # Find all skills
    while IFS= read -r file; do
        [ -f "$file" ] && files+=("$file")
    done < <(find plugins/requirements-framework/skills/ -name "skill.md" -type f 2>/dev/null)

    if [ ${#files[@]} -eq 0 ]; then
        echo -e "${RED}✗ No plugin component files found${NC}"
        exit 1
    fi

    echo "Found ${#files[@]} files to process"
    echo ""

    local updated=0
    local unchanged=0
    local errors=0

    for file in "${files[@]}"; do
        local expected_hash=$(get_file_hash "$file")

        if [ "$CHECK_MODE" = true ]; then
            # Check mode: Report what would change
            local current_hash=$(get_current_hash_from_file "$file")
            if [ "$current_hash" = "$expected_hash" ]; then
                echo -e "${GREEN}✓${NC} $file (current: $expected_hash)"
                ((unchanged++))
            else
                echo -e "${YELLOW}→${NC} $file (would update: $current_hash → $expected_hash)"
                ((updated++))
            fi
        elif [ "$VERIFY_MODE" = true ]; then
            # Verify mode: Check if hash matches current value
            local current_hash=$(get_current_hash_from_file "$file")
            if [ -z "$current_hash" ]; then
                echo -e "${RED}✗${NC} $file (missing git_hash field)"
                ((errors++))
            elif [ "$current_hash" = "$expected_hash" ]; then
                echo -e "${GREEN}✓${NC} $file (current: $expected_hash)"
                ((unchanged++))
            else
                echo -e "${RED}✗${NC} $file (expected: $expected_hash, found: $current_hash)"
                ((errors++))
            fi
        else
            # Update mode: Actually modify files
            if update_file_hash "$file" "$expected_hash"; then
                echo -e "${GREEN}✓${NC} Updated $file → git_hash: $expected_hash"
                ((updated++))
            else
                echo -e "${RED}✗${NC} Failed to update $file"
                ((errors++))
            fi
        fi
    done

    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    if [ "$VERIFY_MODE" = true ]; then
        echo -e "Verification: ${GREEN}$unchanged${NC} current, ${RED}$errors${NC} outdated"
        if [ $errors -gt 0 ]; then
            echo ""
            echo -e "${YELLOW}⚠ Run without --verify to update outdated files${NC}"
        fi
        exit $((errors > 0 ? 1 : 0))
    elif [ "$CHECK_MODE" = true ]; then
        echo -e "Check complete: ${YELLOW}$updated${NC} would be updated, ${GREEN}$unchanged${NC} already current"
        if [ $updated -gt 0 ]; then
            echo ""
            echo -e "${YELLOW}⚠ Run without --check to perform actual updates${NC}"
        fi
    else
        echo -e "Complete: ${GREEN}$updated${NC} updated, ${RED}$errors${NC} errors"
        if [ $errors -gt 0 ]; then
            echo ""
            echo -e "${RED}⚠ Some files failed to update - check errors above${NC}"
            exit 1
        else
            echo ""
            echo -e "${GREEN}✓ All plugin components versioned successfully!${NC}"
            echo ""
            echo "Next steps:"
            echo "  1. Review changes: git diff plugins/requirements-framework/ github-issues-plugin/"
            echo "  2. Commit: git add . && git commit -m 'feat: add git hash version tracking'"
            echo "  3. Deploy: ./sync.sh deploy"
        fi
    fi
}

# Run main
main
