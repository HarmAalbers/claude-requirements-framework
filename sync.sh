#!/bin/bash

set -e  # Exit on error

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
DEPLOY_DIR="$HOME/.claude/hooks"

# Plugin directories
PLUGIN_REPO_DIR="$REPO_DIR/plugin"
PLUGIN_DEPLOY_DIR="$HOME/.claude/plugins/requirements-framework"

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

usage() {
    cat << EOF
Usage: $0 [COMMAND]

Sync the requirements framework between the git repository and deployed locations.

Locations:
  Hooks:   repository/hooks → ~/.claude/hooks
  Plugin:  repository/plugin → ~/.claude/plugins/requirements-framework

Commands:
  deploy        Copy hooks + plugin from repository → deployed locations (default)
  diff          Show differences between repository and deployed
  status        Show sync status
  help          Show this help message

Examples:
  $0 deploy     # Deploy hooks and plugin from repo
  $0 diff       # See what's different
  $0 status     # Check sync status
EOF
    exit 0
}

# Get all Python files from a directory (excluding __pycache__)
get_py_files() {
    local dir="$1"
    local prefix="$2"
    if [ -d "$dir" ]; then
        find "$dir" -maxdepth 1 -name "*.py" -type f 2>/dev/null | while read -r f; do
            echo "${prefix}$(basename "$f")"
        done
    fi
}

# Get all markdown files from a plugin subdirectory
get_plugin_md_files() {
    local dir="$1"
    local prefix="$2"
    if [ -d "$dir" ]; then
        find "$dir" -maxdepth 1 -name "*.md" -type f 2>/dev/null | while read -r f; do
            echo "${prefix}$(basename "$f")"
        done
    fi
}

# Get all skill markdown files recursively
get_skill_md_files() {
    local dir="$1"
    local base_dir="$2"  # The plugin root (repo or deploy)
    if [ -d "$dir" ]; then
        find "$dir" -name "*.md" -type f 2>/dev/null | while read -r f; do
            # Get relative path from plugin root
            echo "${f#$base_dir/}"
        done
    fi
}

# Get all plugin files to sync (union of repo and deployed)
get_all_plugin_files() {
    {
        # Agents
        get_plugin_md_files "$PLUGIN_REPO_DIR/agents" "agents/"
        get_plugin_md_files "$PLUGIN_DEPLOY_DIR/agents" "agents/"
        # Commands
        get_plugin_md_files "$PLUGIN_REPO_DIR/commands" "commands/"
        get_plugin_md_files "$PLUGIN_DEPLOY_DIR/commands" "commands/"
        # Skills (recursive)
        get_skill_md_files "$PLUGIN_REPO_DIR/skills" "$PLUGIN_REPO_DIR"
        get_skill_md_files "$PLUGIN_DEPLOY_DIR/skills" "$PLUGIN_DEPLOY_DIR"
        # Root README
        [ -f "$PLUGIN_REPO_DIR/README.md" ] && echo "README.md"
        [ -f "$PLUGIN_DEPLOY_DIR/README.md" ] && echo "README.md"
        # Plugin metadata
        [ -f "$PLUGIN_REPO_DIR/.claude-plugin/plugin.json" ] && echo ".claude-plugin/plugin.json"
        [ -f "$PLUGIN_DEPLOY_DIR/.claude-plugin/plugin.json" ] && echo ".claude-plugin/plugin.json"
    } | sort -u
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

show_status() {
    echo -e "${BLUE}📊 Sync Status${NC}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""

    # Hooks status
    echo -e "${BLUE}Hooks:${NC}"
    echo "  Repository:  $REPO_DIR/hooks"
    echo "  Deployed:    $DEPLOY_DIR"
    echo ""

    local has_hook_issues=false
    while IFS= read -r file; do
        local repo_file="$REPO_DIR/hooks/$file"
        local deploy_file="$DEPLOY_DIR/$file"

        if [ ! -f "$repo_file" ]; then
            echo -e "  ${RED}✗${NC} $file - Missing in repository (exists in deployed)"
            has_hook_issues=true
        elif [ ! -f "$deploy_file" ]; then
            echo -e "  ${YELLOW}⚠${NC} $file - Not deployed (exists in repository)"
            has_hook_issues=true
        else
            # Compare file contents (not timestamps)
            if diff -q "$repo_file" "$deploy_file" > /dev/null 2>&1; then
                echo -e "  ${GREEN}✓${NC} $file - In sync"
            else
                # Files differ - repository is source of truth
                echo -e "  ${YELLOW}↑${NC} $file - Out of sync"
                has_hook_issues=true
            fi
        fi
    done < <(get_all_files)

    echo ""

    # Plugin status
    echo -e "${BLUE}Plugin:${NC}"
    echo "  Repository:  $PLUGIN_REPO_DIR"
    echo "  Deployed:    $PLUGIN_DEPLOY_DIR"
    echo ""

    local has_plugin_issues=false
    while IFS= read -r file; do
        local repo_file="$PLUGIN_REPO_DIR/$file"
        local deploy_file="$PLUGIN_DEPLOY_DIR/$file"

        if [ ! -f "$repo_file" ]; then
            echo -e "  ${RED}✗${NC} $file - Missing in repository (exists in deployed)"
            has_plugin_issues=true
        elif [ ! -f "$deploy_file" ]; then
            echo -e "  ${YELLOW}⚠${NC} $file - Not deployed (exists in repository)"
            has_plugin_issues=true
        else
            # Compare file contents (not timestamps)
            if diff -q "$repo_file" "$deploy_file" > /dev/null 2>&1; then
                echo -e "  ${GREEN}✓${NC} $file - In sync"
            else
                # Files differ - repository is source of truth
                echo -e "  ${YELLOW}↑${NC} $file - Out of sync"
                has_plugin_issues=true
            fi
        fi
    done < <(get_all_plugin_files)

    echo ""
    if [ "$has_hook_issues" = false ] && [ "$has_plugin_issues" = false ]; then
        echo -e "${GREEN}✓ All files in sync${NC}"
    else
        echo -e "${YELLOW}Run './sync.sh deploy' to synchronize${NC}"
    fi
    echo ""
}

show_diff() {
    echo -e "${BLUE}📝 Differences${NC}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""

    local has_diff=false

    # Hooks differences
    echo -e "${BLUE}Hooks:${NC}"
    local has_hook_diff=false
    while IFS= read -r file; do
        local repo_file="$REPO_DIR/hooks/$file"
        local deploy_file="$DEPLOY_DIR/$file"

        if [ -f "$repo_file" ] && [ -f "$deploy_file" ]; then
            if ! diff -q "$repo_file" "$deploy_file" > /dev/null 2>&1; then
                echo -e "${YELLOW}Differences in $file:${NC}"
                diff -u "$deploy_file" "$repo_file" | head -20 || true
                echo ""
                has_diff=true
                has_hook_diff=true
            fi
        elif [ -f "$deploy_file" ] && [ ! -f "$repo_file" ]; then
            echo -e "${RED}$file exists only in deployed${NC}"
            has_diff=true
            has_hook_diff=true
        elif [ -f "$repo_file" ] && [ ! -f "$deploy_file" ]; then
            echo -e "${YELLOW}$file exists only in repository${NC}"
            has_diff=true
            has_hook_diff=true
        fi
    done < <(get_all_files)

    if [ "$has_hook_diff" = false ]; then
        echo -e "  ${GREEN}✓ No hook differences${NC}"
    fi
    echo ""

    # Plugin differences
    echo -e "${BLUE}Plugin:${NC}"
    local has_plugin_diff=false
    while IFS= read -r file; do
        local repo_file="$PLUGIN_REPO_DIR/$file"
        local deploy_file="$PLUGIN_DEPLOY_DIR/$file"

        if [ -f "$repo_file" ] && [ -f "$deploy_file" ]; then
            if ! diff -q "$repo_file" "$deploy_file" > /dev/null 2>&1; then
                echo -e "${YELLOW}Differences in $file:${NC}"
                diff -u "$deploy_file" "$repo_file" | head -20 || true
                echo ""
                has_diff=true
                has_plugin_diff=true
            fi
        elif [ -f "$deploy_file" ] && [ ! -f "$repo_file" ]; then
            echo -e "${RED}$file exists only in deployed${NC}"
            has_diff=true
            has_plugin_diff=true
        elif [ -f "$repo_file" ] && [ ! -f "$deploy_file" ]; then
            echo -e "${YELLOW}$file exists only in repository${NC}"
            has_diff=true
            has_plugin_diff=true
        fi
    done < <(get_all_plugin_files)

    if [ "$has_plugin_diff" = false ]; then
        echo -e "  ${GREEN}✓ No plugin differences${NC}"
    fi
    echo ""

    if [ "$has_diff" = false ]; then
        echo -e "${GREEN}✓ No differences found${NC}"
    fi
    echo ""
}

deploy_to_hooks() {
    echo -e "${BLUE}🚀 Deploying hooks from repository → ~/.claude/hooks${NC}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""

    # Create lib directory if it doesn't exist
    mkdir -p "$DEPLOY_DIR/lib"

    # Copy main hook files (all .py files in hooks/)
    echo "Copying hook files..."
    for f in "$REPO_DIR/hooks/"*.py; do
        [ -f "$f" ] && cp -v "$f" "$DEPLOY_DIR/"
    done

    # Copy library files
    echo ""
    echo "Copying library files..."
    cp -v "$REPO_DIR/hooks/lib/"*.py "$DEPLOY_DIR/lib/"

    # Ensure executable permissions for known entry points
    for f in "$DEPLOY_DIR/"*.py; do
        [ -f "$f" ] && chmod +x "$f"
    done

    echo ""
    echo -e "${GREEN}✓ Hooks deployment complete!${NC}"
    echo ""
}

deploy_plugin() {
    echo -e "${BLUE}🔌 Deploying plugin from repository → ~/.claude/plugins/requirements-framework${NC}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""

    # Create plugin directories if they don't exist
    mkdir -p "$PLUGIN_DEPLOY_DIR/agents"
    mkdir -p "$PLUGIN_DEPLOY_DIR/commands"
    mkdir -p "$PLUGIN_DEPLOY_DIR/skills"
    mkdir -p "$PLUGIN_DEPLOY_DIR/.claude-plugin"

    # Copy agents
    echo "Copying agent files..."
    for f in "$PLUGIN_REPO_DIR/agents/"*.md; do
        [ -f "$f" ] && cp -v "$f" "$PLUGIN_DEPLOY_DIR/agents/"
    done

    # Copy commands
    echo ""
    echo "Copying command files..."
    for f in "$PLUGIN_REPO_DIR/commands/"*.md; do
        [ -f "$f" ] && cp -v "$f" "$PLUGIN_DEPLOY_DIR/commands/"
    done

    # Copy skills (recursively - skills have subdirectories with references)
    echo ""
    echo "Copying skill files..."
    if [ -d "$PLUGIN_REPO_DIR/skills" ]; then
        # Remove old skills and copy fresh to avoid orphaned files
        rm -rf "$PLUGIN_DEPLOY_DIR/skills"
        cp -r "$PLUGIN_REPO_DIR/skills" "$PLUGIN_DEPLOY_DIR/"
        echo "  Copied skills directory (recursive)"
    fi

    # Copy plugin metadata
    echo ""
    echo "Copying plugin metadata..."
    cp -v "$PLUGIN_REPO_DIR/.claude-plugin/plugin.json" "$PLUGIN_DEPLOY_DIR/.claude-plugin/"

    # Copy README
    cp -v "$PLUGIN_REPO_DIR/README.md" "$PLUGIN_DEPLOY_DIR/"

    echo ""
    echo -e "${GREEN}✓ Plugin deployment complete!${NC}"
    echo ""
}

deploy_all() {
    deploy_to_hooks
    deploy_plugin
    echo "Run tests to verify: python3 $DEPLOY_DIR/test_requirements.py"
    echo ""
}

# Main script
COMMAND="${1:-deploy}"

case "$COMMAND" in
    deploy)
        deploy_all
        ;;
    diff)
        show_diff
        ;;
    status)
        show_status
        ;;
    help|--help|-h)
        usage
        ;;
    *)
        echo -e "${RED}Error: Unknown command '$COMMAND'${NC}"
        echo ""
        usage
        ;;
esac
