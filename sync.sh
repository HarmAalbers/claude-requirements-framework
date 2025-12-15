#!/bin/bash

set -e  # Exit on error

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
DEPLOY_DIR="$HOME/.claude/hooks"

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

usage() {
    cat << EOF
Usage: $0 [COMMAND]

Sync the requirements framework between the git repository and deployed location.

Commands:
  deploy        Copy from repository → ~/.claude/hooks (default)
  pull          Copy from ~/.claude/hooks → repository
  diff          Show differences between repository and deployed
  status        Show sync status
  help          Show this help message

Examples:
  $0 deploy     # Deploy changes from repo to ~/.claude/hooks
  $0 pull       # Pull deployed changes back to repo
  $0 diff       # See what's different
EOF
    exit 0
}

show_status() {
    echo -e "${BLUE}📊 Sync Status${NC}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "Repository:  $REPO_DIR"
    echo "Deployed:    $DEPLOY_DIR"
    echo ""

    # Check if files exist
    local files_to_check=(
        "check-requirements.py"
        "requirements-cli.py"
        "test_requirements.py"
        "handle-session-start.py"
        "handle-stop.py"
        "handle-session-end.py"
        "lib/config.py"
        "lib/git_utils.py"
        "lib/requirements.py"
        "lib/session.py"
        "lib/state_storage.py"
    )

    echo "File Status:"
    for file in "${files_to_check[@]}"; do
        local repo_file="$REPO_DIR/hooks/$file"
        local deploy_file="$DEPLOY_DIR/$file"

        if [ ! -f "$repo_file" ]; then
            echo -e "  ${RED}✗${NC} $file - Missing in repository"
        elif [ ! -f "$deploy_file" ]; then
            echo -e "  ${YELLOW}⚠${NC} $file - Not deployed"
        else
            # Compare modification times
            if [ "$repo_file" -nt "$deploy_file" ]; then
                echo -e "  ${YELLOW}↑${NC} $file - Repository is newer"
            elif [ "$deploy_file" -nt "$repo_file" ]; then
                echo -e "  ${YELLOW}↓${NC} $file - Deployed is newer"
            else
                echo -e "  ${GREEN}✓${NC} $file - In sync"
            fi
        fi
    done
    echo ""
}

show_diff() {
    echo -e "${BLUE}📝 Differences${NC}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""

    local files_to_check=(
        "check-requirements.py"
        "requirements-cli.py"
        "test_requirements.py"
        "handle-session-start.py"
        "handle-stop.py"
        "handle-session-end.py"
        "lib/config.py"
        "lib/git_utils.py"
        "lib/requirements.py"
        "lib/session.py"
        "lib/state_storage.py"
    )

    local has_diff=false
    for file in "${files_to_check[@]}"; do
        local repo_file="$REPO_DIR/hooks/$file"
        local deploy_file="$DEPLOY_DIR/$file"

        if [ -f "$repo_file" ] && [ -f "$deploy_file" ]; then
            if ! diff -q "$repo_file" "$deploy_file" > /dev/null 2>&1; then
                echo -e "${YELLOW}Differences in $file:${NC}"
                diff -u "$deploy_file" "$repo_file" | head -20 || true
                echo ""
                has_diff=true
            fi
        fi
    done

    if [ "$has_diff" = false ]; then
        echo -e "${GREEN}✓ No differences found${NC}"
    fi
    echo ""
}

deploy_to_hooks() {
    echo -e "${BLUE}🚀 Deploying from repository → ~/.claude/hooks${NC}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""

    # Create lib directory if it doesn't exist
    mkdir -p "$DEPLOY_DIR/lib"

    # Copy main hook files
    echo "Copying hook files..."
    cp -v "$REPO_DIR/hooks/check-requirements.py" "$DEPLOY_DIR/"
    cp -v "$REPO_DIR/hooks/requirements-cli.py" "$DEPLOY_DIR/"
    cp -v "$REPO_DIR/hooks/test_requirements.py" "$DEPLOY_DIR/"
    cp -v "$REPO_DIR/hooks/handle-session-start.py" "$DEPLOY_DIR/"
    cp -v "$REPO_DIR/hooks/handle-stop.py" "$DEPLOY_DIR/"
    cp -v "$REPO_DIR/hooks/handle-session-end.py" "$DEPLOY_DIR/"

    # Copy library files
    echo ""
    echo "Copying library files..."
    cp -v "$REPO_DIR/hooks/lib/"*.py "$DEPLOY_DIR/lib/"

    # Ensure executable permissions
    chmod +x "$DEPLOY_DIR/check-requirements.py"
    chmod +x "$DEPLOY_DIR/requirements-cli.py"
    chmod +x "$DEPLOY_DIR/handle-session-start.py"
    chmod +x "$DEPLOY_DIR/handle-stop.py"
    chmod +x "$DEPLOY_DIR/handle-session-end.py"

    echo ""
    echo -e "${GREEN}✓ Deployment complete!${NC}"
    echo ""
    echo "Run tests to verify: python3 $DEPLOY_DIR/test_requirements.py"
    echo ""
}

pull_from_hooks() {
    echo -e "${BLUE}📥 Pulling from ~/.claude/hooks → repository${NC}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""

    # Create hooks/lib directory if it doesn't exist
    mkdir -p "$REPO_DIR/hooks/lib"

    # Copy main hook files
    echo "Copying hook files..."
    cp -v "$DEPLOY_DIR/check-requirements.py" "$REPO_DIR/hooks/"
    cp -v "$DEPLOY_DIR/requirements-cli.py" "$REPO_DIR/hooks/"
    cp -v "$DEPLOY_DIR/test_requirements.py" "$REPO_DIR/hooks/"
    cp -v "$DEPLOY_DIR/handle-session-start.py" "$REPO_DIR/hooks/"
    cp -v "$DEPLOY_DIR/handle-stop.py" "$REPO_DIR/hooks/"
    cp -v "$DEPLOY_DIR/handle-session-end.py" "$REPO_DIR/hooks/"

    # Copy library files
    echo ""
    echo "Copying library files..."
    cp -v "$DEPLOY_DIR/lib/"*.py "$REPO_DIR/hooks/lib/"

    echo ""
    echo -e "${GREEN}✓ Pull complete!${NC}"
    echo ""
    echo -e "${YELLOW}⚠ Don't forget to commit changes:${NC}"
    echo "  cd $REPO_DIR"
    echo "  git status"
    echo "  git add ."
    echo "  git commit -m \"Sync from deployed version\""
    echo ""
}

# Main script
COMMAND="${1:-deploy}"

case "$COMMAND" in
    deploy)
        deploy_to_hooks
        ;;
    pull)
        pull_from_hooks
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
