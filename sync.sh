#!/bin/bash

set -e  # Exit on error

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
DEPLOY_DIR="$HOME/.claude/hooks"

# Plugin directories
PLUGIN_REPO_DIR="$REPO_DIR/plugins/requirements-framework"
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

# Get all Python and bundled-asset files recursively (excluding __pycache__).
# Used for hooks/lib so subpackages like lib/llm/ deploy without per-step
# sync.sh edits. Extensions included:
#   .py     — Python sources
#   .md.j2  — Jinja2 prompt sources for runtime rendering (Step 16+)
#   .j2     — Jinja2 partials included by runtime templates
# Without these the workers' file-fallback path raises FileNotFoundError when
# Langfuse is unreachable.
get_py_files_recursive() {
    local dir="$1"
    local prefix="$2"
    if [ -d "$dir" ]; then
        find "$dir" \( -name "*.py" -o -name "*.md.j2" -o -name "*.j2" \) -type f -not -path "*/__pycache__/*" 2>/dev/null | while read -r f; do
            echo "${prefix}${f#$dir/}"
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

# Get all files recursively from a directory with prefix
get_all_files_recursive() {
    local dir="$1"
    local base_dir="$2"
    if [ -d "$dir" ]; then
        find "$dir" -type f 2>/dev/null | while read -r f; do
            echo "${f#$base_dir/}"
        done
    fi
}

# Directories to skip in deployed plugin (marketplace cache, etc.)
is_deploy_only_dir() {
    local dirname="$1"
    case "$dirname" in
        marketplaces) return 0 ;;  # Marketplace cache
        *) return 1 ;;
    esac
}

# Get all plugin files to sync (union of repo and deployed)
get_all_plugin_files() {
    {
        # All subdirectories from repo (agents, commands, skills, mcps, etc.)
        for subdir in "$PLUGIN_REPO_DIR"/*/; do
            [ -d "$subdir" ] || continue
            local dirname=$(basename "$subdir")
            [[ "$dirname" == .* ]] && continue
            get_all_files_recursive "$subdir" "$PLUGIN_REPO_DIR"
        done
        # All subdirectories from deployed (only if also in repo)
        for subdir in "$PLUGIN_DEPLOY_DIR"/*/; do
            [ -d "$subdir" ] || continue
            local dirname=$(basename "$subdir")
            [[ "$dirname" == .* ]] && continue
            # Skip deploy-only directories (marketplaces, etc.)
            is_deploy_only_dir "$dirname" && continue
            get_all_files_recursive "$subdir" "$PLUGIN_DEPLOY_DIR"
        done
        # Root files
        [ -f "$PLUGIN_REPO_DIR/README.md" ] && echo "README.md"
        [ -f "$PLUGIN_DEPLOY_DIR/README.md" ] && echo "README.md"
        [ -f "$PLUGIN_REPO_DIR/.mcp.json" ] && echo ".mcp.json"
        [ -f "$PLUGIN_DEPLOY_DIR/.mcp.json" ] && echo ".mcp.json"
        [ -f "$PLUGIN_REPO_DIR/statusline.sh" ] && echo "statusline.sh"
        [ -f "$PLUGIN_DEPLOY_DIR/statusline.sh" ] && echo "statusline.sh"
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
        get_py_files_recursive "$REPO_DIR/hooks/lib" "lib/"
        get_py_files_recursive "$DEPLOY_DIR/lib" "lib/"
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

    # File count summary
    echo -e "${BLUE}Summary (repo → deployed):${NC}"

    # Hooks
    local repo_hooks=$(find "$REPO_DIR/hooks" -maxdepth 1 -name "*.py" -type f 2>/dev/null | wc -l | tr -d ' ')
    local deploy_hooks=$(find "$DEPLOY_DIR" -maxdepth 1 -name "*.py" -type f 2>/dev/null | wc -l | tr -d ' ')
    local repo_lib=$(find "$REPO_DIR/hooks/lib" \( -name "*.py" -o -name "*.txt" \) -type f 2>/dev/null | wc -l | tr -d ' ')
    local deploy_lib=$(find "$DEPLOY_DIR/lib" \( -name "*.py" -o -name "*.txt" \) -type f 2>/dev/null | wc -l | tr -d ' ')
    printf "  %-12s %s → %s\n" "Hooks:" "$repo_hooks" "$deploy_hooks"
    printf "  %-12s %s → %s\n" "Lib:" "$repo_lib" "$deploy_lib"

    # Plugin components (dynamic)
    for subdir in "$PLUGIN_REPO_DIR"/*/; do
        [ -d "$subdir" ] || continue
        local dirname=$(basename "$subdir")
        [[ "$dirname" == .* ]] && continue
        local repo_count=$(find "$subdir" -type f 2>/dev/null | wc -l | tr -d ' ')
        local deploy_count=$(find "$PLUGIN_DEPLOY_DIR/$dirname" -type f 2>/dev/null | wc -l | tr -d ' ')
        # Capitalize first letter for display
        local first_char=$(echo "$dirname" | cut -c1 | tr '[:lower:]' '[:upper:]')
        local rest=$(echo "$dirname" | cut -c2-)
        local display_name="${first_char}${rest}:"
        printf "  %-12s %s → %s\n" "$display_name" "$repo_count" "$deploy_count"
    done

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

    # Copy library files (recursive — supports subpackages like lib/llm/).
    # Extensions: .py + .md.j2 + .j2 (see get_py_files_recursive comment).
    # Clean the prompts/ subtree first so renamed files (e.g. Step 16's
    # .txt → .md.j2) don't leave orphans in the deployed runtime.
    echo ""
    echo "Cleaning bundled prompts subtree (removes orphans)..."
    rm -rf "$DEPLOY_DIR/lib/llm/prompts"

    echo ""
    echo "Copying library files..."
    (cd "$REPO_DIR/hooks/lib" && find . \( -name "*.py" -o -name "*.md.j2" -o -name "*.j2" \) -type f -not -path "*/__pycache__/*") | while read -r relpath; do
        local stripped="${relpath#./}"
        local target="$DEPLOY_DIR/lib/$stripped"
        mkdir -p "$(dirname "$target")"
        cp -v "$REPO_DIR/hooks/lib/$stripped" "$target"
    done

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

    # Render plugin .md.j2 sources to .md siblings before copying (Step 16+).
    # No-op for Step 16 (no plugin .md.j2 files exist yet); plumbing in place
    # so Step 16b's first plugin agent migration drops in clean.
    if [ -f "$REPO_DIR/scripts/render_prompts.py" ]; then
        echo "Rendering plugin .md.j2 sources..."
        if ! python3 "$REPO_DIR/scripts/render_prompts.py" "$PLUGIN_REPO_DIR"; then
            echo -e "${RED}ERROR: plugin template rendering failed; aborting deploy${NC}"
            exit 1
        fi
        echo ""
    fi

    # Create base plugin directory
    mkdir -p "$PLUGIN_DEPLOY_DIR"

    # Sync all subdirectories in plugins/requirements-framework/ (agents, commands, skills, mcps, etc.)
    # This is generic - adding new component types doesn't require script changes
    for dir in "$PLUGIN_REPO_DIR"/*/; do
        [ -d "$dir" ] || continue
        local dirname=$(basename "$dir")

        # Skip hidden directories (handled separately)
        [[ "$dirname" == .* ]] && continue

        echo "Copying $dirname..."
        # Remove old and copy fresh to avoid orphaned files
        rm -rf "$PLUGIN_DEPLOY_DIR/$dirname"
        # Use dirname without trailing slash to copy the directory itself
        cp -r "${dir%/}" "$PLUGIN_DEPLOY_DIR/"
        local count=$(find "$PLUGIN_DEPLOY_DIR/$dirname" -type f 2>/dev/null | wc -l | tr -d ' ')
        echo "  Copied $count file(s)"
        echo ""
    done

    # Copy plugin metadata (.claude-plugin/)
    echo "Copying plugin metadata..."
    mkdir -p "$PLUGIN_DEPLOY_DIR/.claude-plugin"
    cp -v "$PLUGIN_REPO_DIR/.claude-plugin/plugin.json" "$PLUGIN_DEPLOY_DIR/.claude-plugin/"

    # Copy .mcp.json if it exists
    if [ -f "$PLUGIN_REPO_DIR/.mcp.json" ]; then
        echo ""
        echo "Copying MCP configuration..."
        cp -v "$PLUGIN_REPO_DIR/.mcp.json" "$PLUGIN_DEPLOY_DIR/"
    fi

    # Copy README
    cp -v "$PLUGIN_REPO_DIR/README.md" "$PLUGIN_DEPLOY_DIR/"

    # Copy statusline. Preserves +x permission via cp -p.
    if [ -f "$PLUGIN_REPO_DIR/statusline.sh" ]; then
        cp -pv "$PLUGIN_REPO_DIR/statusline.sh" "$PLUGIN_DEPLOY_DIR/"
    fi

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
