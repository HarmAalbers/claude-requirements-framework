#!/bin/bash

# sync-versions.sh - Propagate the plugin version to the marketplace manifest.
#
# plugins/requirements-framework/.claude-plugin/plugin.json holds the version;
# .claude-plugin/marketplace.json holds the one Claude Code resolves an install
# from. They must agree, or a release is published that nobody can install.
#
# Usage:
#   ./sync-versions.sh           # Update marketplace.json
#   ./sync-versions.sh --check   # Dry-run (show what would change)
#   ./sync-versions.sh --verify  # Exit 1 if the two disagree
#
# This used to also rewrite docs/PLUGIN-INSTALLATION.md through three `sed -i ''`
# calls. All three targeted markers that file no longer carries, and the BSD-only
# `-i ''` form made GNU sed read the expression as a filename — so on CI it
# printed three "can't read" errors and then reported success anyway. The doc is
# a how-to with no version line to maintain; that half is gone rather than
# repaired.

set -e

# Get repository directory (where this script is located)
REPO_DIR="$(cd "$(dirname "$0")" && pwd)"

# Files
PLUGIN_JSON="$REPO_DIR/plugins/requirements-framework/.claude-plugin/plugin.json"
MARKETPLACE_JSON="$REPO_DIR/.claude-plugin/marketplace.json"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
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

if [ ! -f "$PLUGIN_JSON" ]; then
    echo -e "${RED}Error: plugin.json not found at $PLUGIN_JSON${NC}"
    exit 1
fi

if [ ! -f "$MARKETPLACE_JSON" ]; then
    echo -e "${RED}Error: marketplace.json not found at $MARKETPLACE_JSON${NC}"
    exit 1
fi

# Name and version both come from plugin.json, so the marketplace entry is
# matched by name rather than by position — an added plugin must not silently
# shift which entry gets the version.
read -r PLUGIN_NAME VERSION < <(python3 -c "
import json
data = json.load(open('$PLUGIN_JSON'))
print(data['name'], data['version'])
")

if [ -z "$VERSION" ] || [ -z "$PLUGIN_NAME" ]; then
    echo -e "${RED}Error: Could not read name/version from plugin.json${NC}"
    exit 1
fi

echo "📦 Plugin version (source of truth): $VERSION"
echo ""

marketplace_version() {
    python3 -c "
import json, sys
plugins = json.load(open('$MARKETPLACE_JSON')).get('plugins', [])
match = [p for p in plugins if p.get('name') == '$PLUGIN_NAME']
if not match:
    sys.exit(1)
print(match[0].get('version', ''))
"
}

if ! CURRENT=$(marketplace_version); then
    echo -e "${RED}❌ marketplace.json has no '$PLUGIN_NAME' entry${NC}"
    exit 1
fi

if [ "$CURRENT" = "$VERSION" ]; then
    echo -e "${GREEN}✅ marketplace.json: v$CURRENT (in sync)${NC}"
    exit 0
fi

if [ "$VERIFY_ONLY" = true ]; then
    echo -e "${RED}❌ marketplace.json: v$CURRENT (needs update to v$VERSION)${NC}"
    echo ""
    echo -e "${RED}Version mismatch detected! Run './sync-versions.sh' to fix.${NC}"
    exit 1
fi

if [ "$CHECK_ONLY" = true ]; then
    echo -e "${RED}❌ marketplace.json: v$CURRENT (would update to v$VERSION)${NC}"
    exit 1
fi

python3 -c "
import json

path = '$MARKETPLACE_JSON'
with open(path) as f:
    data = json.load(f)

for plugin in data['plugins']:
    if plugin.get('name') == '$PLUGIN_NAME':
        plugin['version'] = '$VERSION'

with open(path, 'w') as f:
    json.dump(data, f, indent=2)
    f.write('\n')
"

# Read it back rather than trusting the write. The previous version of this
# script announced success unconditionally, which is how three failing seds
# went unnoticed for months.
AFTER=$(marketplace_version)
if [ "$AFTER" != "$VERSION" ]; then
    echo -e "${RED}❌ marketplace.json still reads v$AFTER after the update${NC}"
    exit 1
fi

echo -e "${GREEN}✅ marketplace.json: updated v$CURRENT → v$VERSION${NC}"
echo ""
echo "Next steps:"
echo "  git add .claude-plugin/marketplace.json"
echo "  git commit -m 'chore: sync version to $VERSION'"
