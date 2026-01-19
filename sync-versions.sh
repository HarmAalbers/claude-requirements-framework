#!/bin/bash

# sync-versions.sh - Keep version numbers in sync across plugin files
#
# This script reads the version from plugins/requirements-framework/.claude-plugin/plugin.json (source of truth)
# and updates it in:
#   - .claude-plugin/marketplace.json
#   - docs/PLUGIN-INSTALLATION.md
#
# Usage:
#   ./sync-versions.sh           # Update all files
#   ./sync-versions.sh --check   # Dry-run (show what would change)
#   ./sync-versions.sh --verify  # Verify versions are in sync

set -e

# Get repository directory (where this script is located)
REPO_DIR="$(cd "$(dirname "$0")" && pwd)"

# Files
PLUGIN_JSON="$REPO_DIR/plugins/requirements-framework/.claude-plugin/plugin.json"
MARKETPLACE_JSON="$REPO_DIR/.claude-plugin/marketplace.json"
DOCS_FILE="$REPO_DIR/docs/PLUGIN-INSTALLATION.md"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Parse arguments
CHECK_ONLY=false
VERIFY_ONLY=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --check)
            CHECK_ONLY=true
            shift
            ;;
        --verify)
            VERIFY_ONLY=true
            shift
            ;;
        *)
            echo "Usage: $0 [--check|--verify]"
            echo "  --check   Dry-run (show what would change)"
            echo "  --verify  Verify versions are in sync"
            exit 1
            ;;
    esac
done

# Check if required files exist
if [ ! -f "$PLUGIN_JSON" ]; then
    echo -e "${RED}Error: plugin.json not found at $PLUGIN_JSON${NC}"
    exit 1
fi

# Get the authoritative version from plugin.json
VERSION=$(python3 -c "import json; print(json.load(open('$PLUGIN_JSON'))['version'])" 2>/dev/null)

if [ -z "$VERSION" ]; then
    echo -e "${RED}Error: Could not read version from plugin.json${NC}"
    exit 1
fi

echo "📦 Plugin version (source of truth): $VERSION"
echo ""

# Function to check/update marketplace.json
sync_marketplace() {
    if [ ! -f "$MARKETPLACE_JSON" ]; then
        echo -e "${YELLOW}⚠️  marketplace.json not found${NC}"
        return 1
    fi

    current_version=$(python3 -c "import json; print(json.load(open('$MARKETPLACE_JSON'))['plugins'][0]['version'])" 2>/dev/null || echo "unknown")

    if [ "$current_version" = "$VERSION" ]; then
        echo -e "${GREEN}✅ marketplace.json: v$current_version (in sync)${NC}"
        return 0
    fi

    if [ "$VERIFY_ONLY" = true ] || [ "$CHECK_ONLY" = true ]; then
        echo -e "${RED}❌ marketplace.json: v$current_version (needs update to v$VERSION)${NC}"
        return 1
    fi

    # Update marketplace.json
    python3 << EOF
import json

with open('$MARKETPLACE_JSON', 'r') as f:
    data = json.load(f)

data['plugins'][0]['version'] = '$VERSION'

with open('$MARKETPLACE_JSON', 'w') as f:
    json.dump(data, f, indent=2)
    f.write('\n')
EOF

    echo -e "${GREEN}✅ marketplace.json: updated v$current_version → v$VERSION${NC}"
    return 0
}

# Function to check/update documentation
sync_docs() {
    if [ ! -f "$DOCS_FILE" ]; then
        echo -e "${YELLOW}⚠️  PLUGIN-INSTALLATION.md not found${NC}"
        return 1
    fi

    # Check for version references in docs
    outdated_count=$(grep -c "v2\.[0-9]\+\.[0-9]\+" "$DOCS_FILE" 2>/dev/null | grep -v "$VERSION" | wc -l | tr -d ' ')
    current_refs=$(grep -o "v2\.[0-9]\+\.[0-9]\+" "$DOCS_FILE" 2>/dev/null | sort -u | tr '\n' ' ')

    # More precise check - look for the main version patterns
    doc_version=$(grep -o "Plugin Version:\*\* [0-9]\+\.[0-9]\+\.[0-9]\+" "$DOCS_FILE" 2>/dev/null | grep -o "[0-9]\+\.[0-9]\+\.[0-9]\+" || echo "unknown")

    if [ "$doc_version" = "$VERSION" ]; then
        echo -e "${GREEN}✅ PLUGIN-INSTALLATION.md: v$doc_version (in sync)${NC}"
        return 0
    fi

    if [ "$VERIFY_ONLY" = true ] || [ "$CHECK_ONLY" = true ]; then
        echo -e "${RED}❌ PLUGIN-INSTALLATION.md: v$doc_version (needs update to v$VERSION)${NC}"
        return 1
    fi

    # Update documentation using sed
    # Update **Plugin Version:** X.Y.Z
    sed -i '' "s/\*\*Plugin Version:\*\* [0-9]\+\.[0-9]\+\.[0-9]\+/**Plugin Version:** $VERSION/" "$DOCS_FILE"

    # Update "version": "X.Y.Z" in JSON examples
    sed -i '' "s/\"version\": \"[0-9]\+\.[0-9]\+\.[0-9]\+\"/\"version\": \"$VERSION\"/" "$DOCS_FILE"

    # Update - **vX.Y.Z** in version history
    old_version_pattern="v[0-9]\+\.[0-9]\+\.[0-9]\+ - Current stable"
    sed -i '' "s/$old_version_pattern/v$VERSION - Current stable/" "$DOCS_FILE"

    echo -e "${GREEN}✅ PLUGIN-INSTALLATION.md: updated to v$VERSION${NC}"
    return 0
}

# Run sync operations
ERRORS=0

sync_marketplace || ERRORS=$((ERRORS + 1))
sync_docs || ERRORS=$((ERRORS + 1))

echo ""

if [ "$VERIFY_ONLY" = true ]; then
    if [ $ERRORS -gt 0 ]; then
        echo -e "${RED}❌ Version mismatch detected! Run './sync-versions.sh' to fix.${NC}"
        exit 1
    else
        echo -e "${GREEN}✅ All versions are in sync!${NC}"
        exit 0
    fi
fi

if [ "$CHECK_ONLY" = true ]; then
    if [ $ERRORS -gt 0 ]; then
        echo -e "${YELLOW}Would update $ERRORS file(s). Run './sync-versions.sh' to apply.${NC}"
        exit 1
    else
        echo -e "${GREEN}All versions already in sync. No changes needed.${NC}"
        exit 0
    fi
fi

if [ $ERRORS -gt 0 ]; then
    echo -e "${RED}⚠️  Some files could not be updated${NC}"
    exit 1
else
    echo -e "${GREEN}✅ Version sync complete!${NC}"
    echo ""
    echo "Next steps:"
    echo "  git add .claude-plugin/marketplace.json docs/PLUGIN-INSTALLATION.md"
    echo "  git commit -m 'chore: sync version to $VERSION'"
fi
