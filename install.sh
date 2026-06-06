#!/bin/bash

set -e  # Exit on error

# Get repository directory (where this script is located)
REPO_DIR="$(cd "$(dirname "$0")" && pwd)"

# Global flags for configuration choices
ENABLE_CODEX="false"

echo "🔧 Claude Code Requirements Framework Installer"
echo "================================================"
echo ""

# Check if Claude Code directory exists
if [ ! -d "$HOME/.claude" ]; then
    echo "❌ Error: Claude Code directory not found at ~/.claude"
    echo "   Please ensure Claude Code is installed first."
    exit 1
fi

# Lifecycle hooks are provided by the self-contained plugin — its
# hooks/hooks.json is the single source of truth for hook registration
# (commands resolved via ${CLAUDE_PLUGIN_ROOT}). install.sh no longer copies
# hook scripts to ~/.claude/hooks/ or edits settings.json hook blocks.
echo "🪝 Lifecycle hooks are provided by the requirements-framework plugin."
echo "   Nothing is copied to ~/.claude/hooks/ — install the plugin to activate them:"
echo "     /plugin install requirements-framework@requirements-framework"
echo "   For development (live reload):"
echo "     claude --plugin-dir $REPO_DIR/plugins/requirements-framework"

# Configure Codex requirement interactively
configure_codex_requirement() {
    echo ""
    echo "🤖 Codex AI Code Review"
    echo "======================="
    echo ""
    echo "The framework can optionally enforce AI-powered code review before PR creation."
    echo ""
    echo "What it does:"
    echo "  - Runs OpenAI Codex review before 'gh pr create'"
    echo "  - Checks for bugs, security issues, and code quality"
    echo "  - Uses the /requirements-framework:codex-review command"
    echo ""
    echo "Requirements:"
    echo "  - Codex CLI must be installed: npm install -g @openai/codex"
    echo "  - Must be logged in: codex login"
    echo ""

    # Check if Codex CLI is installed
    local codex_installed=false
    if command -v codex &> /dev/null; then
        codex_installed=true
        echo "✅ Codex CLI detected at: $(which codex)"
    else
        echo "⚠️  Codex CLI not found in PATH"
    fi

    echo ""
    read -p "Enable Codex AI review requirement? [y/N] " -n 1 -r
    echo
    echo ""

    if [[ $REPLY =~ ^[Yy]$ ]]; then
        ENABLE_CODEX="true"
        echo "✅ Codex requirement will be enabled"

        if [ "$codex_installed" = false ]; then
            echo ""
            echo "⚠️  Remember to install Codex CLI:"
            echo "   npm install -g @openai/codex"
            echo "   codex login"
        fi
    else
        ENABLE_CODEX="false"
        echo "ℹ️  Codex requirement will be disabled"
        echo "   You can enable it later by editing ~/.claude/requirements.yaml"
    fi

    return 0
}

# Ask about Codex configuration
configure_codex_requirement

# Install global configuration if it doesn't exist
if [ ! -f "$HOME/.claude/requirements.yaml" ]; then
    echo ""
    echo "⚙️  Installing global configuration to ~/.claude/requirements.yaml..."
    cp "$REPO_DIR/examples/global-requirements.yaml" "$HOME/.claude/requirements.yaml"

    # Update codex_reviewer setting based on user choice
    if [ "$ENABLE_CODEX" = "true" ]; then
        python3 - "$HOME/.claude/requirements.yaml" << 'EOF'
import re
import sys

config_file = sys.argv[1]

try:
    with open(config_file, 'r') as f:
        content = f.read()

    # Find codex_reviewer section and set enabled: true
    # This regex finds the codex_reviewer section and updates enabled
    content = re.sub(
        r'(codex_reviewer:\s*\n\s*enabled:\s*)false',
        r'\1true',
        content
    )

    with open(config_file, 'w') as f:
        f.write(content)

    print("   ✅ Enabled codex_reviewer requirement")
except Exception as e:
    print(f"   ⚠️  Could not update codex setting: {e}", file=sys.stderr)
    print("   You can manually enable it in ~/.claude/requirements.yaml")
EOF
    else
        echo "   ℹ️  Codex requirement disabled (default)"
    fi
else
    echo ""
    echo "ℹ️  Global configuration already exists at ~/.claude/requirements.yaml"
    echo "   (Not overwriting - see examples/global-requirements.yaml for reference)"
fi

# Create symlink for CLI tool (points at the repo copy; requirements-cli.py
# resolves its lib/ via the real path, so the symlink target works directly).
echo ""
echo "🔗 Creating symlink for 'req' command..."
mkdir -p "$HOME/.local/bin"
ln -sf "$REPO_DIR/hooks/requirements-cli.py" "$HOME/.local/bin/req"

# Configure ENABLE_TOOL_SEARCH=true in user's shell rc
# Reduces Claude Code's initial context by deferring tool schemas (Claude Code v2.0.74+).
configure_tool_search() {
    echo ""
    echo "⚡ On-demand tool loading (ENABLE_TOOL_SEARCH)"
    echo "=============================================="
    echo ""
    echo "Setting ENABLE_TOOL_SEARCH=true reduces Claude Code's initial context by"
    echo "loading tool schemas on demand via ToolSearch (requires Claude Code v2.0.74+)."
    echo ""

    # Detect shell and config file (mirrors configure_path)
    local shell_name
    shell_name=$(basename "$SHELL")
    local config_file=""

    case "$shell_name" in
        zsh)
            if [ -f "$HOME/.zshrc" ]; then
                config_file="$HOME/.zshrc"
            elif [ -f "$HOME/.zprofile" ]; then
                config_file="$HOME/.zprofile"
            fi
            ;;
        bash)
            if [ -f "$HOME/.bashrc" ]; then
                config_file="$HOME/.bashrc"
            elif [ -f "$HOME/.bash_profile" ]; then
                config_file="$HOME/.bash_profile"
            elif [ -f "$HOME/.profile" ]; then
                config_file="$HOME/.profile"
            fi
            ;;
        fish)
            mkdir -p "$HOME/.config/fish"
            config_file="$HOME/.config/fish/config.fish"
            ;;
        *)
            echo "Unknown shell: $shell_name"
            echo "Please manually add to your shell profile:"
            echo "  export ENABLE_TOOL_SEARCH=true"
            return 1
            ;;
    esac

    if [ -z "$config_file" ]; then
        echo "No shell configuration file found."
        echo "Please manually add to your shell profile:"
        echo "  export ENABLE_TOOL_SEARCH=true"
        return 1
    fi

    # Idempotent: skip if already present
    if grep -q "ENABLE_TOOL_SEARCH" "$config_file" 2>/dev/null; then
        echo "✅ ENABLE_TOOL_SEARCH already configured in $config_file"
        return 0
    fi

    echo "This installer can add ENABLE_TOOL_SEARCH=true to $config_file."
    echo ""
    read -p "Add ENABLE_TOOL_SEARCH=true to your shell? [Y/n] " -n 1 -r
    echo

    if [[ $REPLY =~ ^[Nn]$ ]]; then
        echo "Skipped. You can manually add to $config_file:"
        if [ "$shell_name" = "fish" ]; then
            echo "  set -x ENABLE_TOOL_SEARCH true"
        else
            echo "  export ENABLE_TOOL_SEARCH=true"
        fi
        return 0
    fi

    {
        echo ""
        echo "# Added by claude-requirements-framework installer on $(date)"
        if [ "$shell_name" = "fish" ]; then
            echo "set -x ENABLE_TOOL_SEARCH true"
        else
            echo "export ENABLE_TOOL_SEARCH=true"
        fi
    } >> "$config_file"

    echo "✅ Added ENABLE_TOOL_SEARCH=true to $config_file"
    echo "   Restart your shell or run: source $config_file"

    return 0
}

# Configure PATH interactively
configure_path() {
    # Check if ~/.local/bin is already in PATH
    if [[ ":$PATH:" == *":$HOME/.local/bin:"* ]]; then
        echo "✅ ~/.local/bin is already in PATH"
        return 0
    fi

    echo ""
    echo "⚠️  ~/.local/bin is not in your PATH"
    echo ""

    # Detect shell and config file
    local shell_name=$(basename "$SHELL")
    local config_file=""

    case "$shell_name" in
        zsh)
            if [ -f "$HOME/.zshrc" ]; then
                config_file="$HOME/.zshrc"
            elif [ -f "$HOME/.zprofile" ]; then
                config_file="$HOME/.zprofile"
            fi
            ;;
        bash)
            if [ -f "$HOME/.bashrc" ]; then
                config_file="$HOME/.bashrc"
            elif [ -f "$HOME/.bash_profile" ]; then
                config_file="$HOME/.bash_profile"
            elif [ -f "$HOME/.profile" ]; then
                config_file="$HOME/.profile"
            fi
            ;;
        fish)
            mkdir -p "$HOME/.config/fish"
            config_file="$HOME/.config/fish/config.fish"
            ;;
        *)
            echo "Unknown shell: $shell_name"
            echo "Please manually add to your shell profile:"
            echo "  export PATH=\"\$HOME/.local/bin:\$PATH\""
            return 1
            ;;
    esac

    if [ -z "$config_file" ]; then
        echo "No shell configuration file found."
        echo "Please manually add to your shell profile:"
        echo "  export PATH=\"\$HOME/.local/bin:\$PATH\""
        return 1
    fi

    # Show what we'll add
    echo "This installer can automatically add ~/.local/bin to your PATH."
    echo ""
    echo "The following line will be added to $config_file:"
    echo ""
    echo "  # Added by claude-requirements-framework installer"
    echo "  export PATH=\"\$HOME/.local/bin:\$PATH\""
    echo ""

    # Interactive prompt with default to 'yes'
    read -p "Add to PATH automatically? [Y/n] " -n 1 -r
    echo

    if [[ $REPLY =~ ^[Nn]$ ]]; then
        echo "Skipped. You can manually add:"
        echo "  export PATH=\"\$HOME/.local/bin:\$PATH\""
        echo "to $config_file"
        return 0
    fi

    # Backup config file first (if it exists)
    if [ -f "$config_file" ]; then
        local backup_file="${config_file}.backup-$(date +%Y%m%d-%H%M%S)"
        cp "$config_file" "$backup_file"
        echo "📋 Backed up $config_file to $backup_file"
    fi

    # Add PATH export (syntax depends on shell)
    echo "" >> "$config_file"
    echo "# Added by claude-requirements-framework installer on $(date)" >> "$config_file"
    if [ "$shell_name" = "fish" ]; then
        echo "fish_add_path ~/.local/bin" >> "$config_file"
    else
        echo "export PATH=\"\$HOME/.local/bin:\$PATH\"" >> "$config_file"
    fi

    echo "✅ Added ~/.local/bin to PATH in $config_file"
    echo "   Restart your shell or run: source $config_file"

    return 0
}

# Configure on-demand tool loading (reduces Claude Code context size)
configure_tool_search

# Call PATH configuration
configure_path

# Display marketplace installation instructions
display_marketplace_instructions() {
    echo ""
    echo "📦 Plugin Installation Options:"
    echo ""
    echo "   **Option 1: Test with CLI Flag (Recommended for Development)**"
    echo "   Launch Claude Code with plugin temporarily loaded:"
    echo "   $ claude --plugin-dir $REPO_DIR/plugins/requirements-framework"
    echo ""
    echo "   **Option 2: Persistent Installation via Local Marketplace**"
    echo "   For permanent installation from your local clone:"
    echo "   1. In Claude Code session, run:"
    echo "      /plugin marketplace add $REPO_DIR"
    echo "   2. Then install the plugin:"
    echo "      /plugin install requirements-framework@requirements-framework"
    echo "   3. Verify:"
    echo "      /requirements-framework:pre-commit"
    echo ""
    echo "   **Option 3: GitHub Marketplace (for other users)**"
    echo "   Share with others who don't have a local clone:"
    echo "      /plugin marketplace add https://github.com/HarmAalbers/claude-requirements-framework"
    echo "      /plugin install requirements-framework@requirements-framework"
    echo ""
    echo "   📖 For more details: $REPO_DIR/docs/PLUGIN-INSTALLATION.md"
}

# Show marketplace instructions
display_marketplace_instructions

# Register the phase-aware statusline in settings.json. Hook registration is
# NOT done here — the plugin's hooks/hooks.json is the single source of truth.
configure_statusline() {
    python3 << 'PYTHON_SCRIPT'
import json
import os
import sys

settings_file = os.path.expanduser("~/.claude/settings.json")

try:
    # Load existing settings or create new
    if os.path.exists(settings_file):
        with open(settings_file, 'r') as f:
            settings = json.load(f)
        print("   Updating existing settings.json...")
    else:
        settings = {}
        print("   Creating new settings.json...")

    # Register the phase-aware statusline, but never clobber a user's
    # existing statusLine — only fill it in when absent or empty.
    STATUSLINE_CMD = "~/.claude/plugins/requirements-framework/statusline.sh"
    existing_status = settings.get("statusLine") or {}
    existing_cmd = existing_status.get("command", "")
    if not existing_cmd:
        settings["statusLine"] = {"type": "command", "command": STATUSLINE_CMD}
        print("   ✅ Statusline registered")
    elif "requirements-framework/statusline.sh" in existing_cmd:
        print("   ✅ Statusline already registered")
    else:
        print("   ℹ️  Existing statusLine preserved (custom command detected)")

    with open(settings_file, 'w') as f:
        json.dump(settings, f, indent=2)

except (IOError, OSError, json.JSONDecodeError) as e:
    print(f"   ❌ Could not configure statusline in settings.json: {e}", file=sys.stderr)
    sys.exit(1)
except Exception as e:
    print(f"   ❌ Unexpected error configuring statusline: {e}", file=sys.stderr)
    sys.exit(1)
PYTHON_SCRIPT

    if [ $? -ne 0 ]; then
        echo "   ⚠️  Statusline configuration failed (non-fatal — hooks are unaffected)"
    fi
    return 0
}

# Register the statusline (hooks come from the plugin's hooks.json)
echo "📝 Registering statusline in settings.json..."
configure_statusline

echo ""
echo "🧪 Verifying installation..."
echo ""

VERIFICATION_PASSED=true

# Hook registration is owned by the plugin's hooks.json — nothing to verify here.

# Test 1: Check if req command works
echo "1️⃣  Checking 'req' command..."
if command -v req &> /dev/null; then
    if req --help &> /dev/null; then
        echo "   ✅ 'req' command is accessible and working"
    else
        echo "   ⚠️  'req' command found but failed to run"
        VERIFICATION_PASSED=false
    fi
else
    echo "   ⚠️  'req' command not in PATH"
    echo "      (Will be available after restarting shell or adding ~/.local/bin to PATH)"
fi

# Test 2: Check plugin marketplace
echo ""
echo "2️⃣  Checking plugin marketplace..."
if [ -f "$REPO_DIR/.claude-plugin/marketplace.json" ]; then
    marketplace_version=$(python3 -c "import json; print(json.load(open('$REPO_DIR/.claude-plugin/marketplace.json'))['plugins'][0]['version'])" 2>/dev/null || echo "unknown")
    echo "   ✅ Local marketplace available (v$marketplace_version)"
    echo "   ℹ️  Install plugin via: /plugin install requirements-framework@requirements-framework"
else
    echo "   ⚠️  Marketplace manifest not found"
fi

# Test 3: Check global config
echo ""
echo "3️⃣  Checking global configuration..."
if [ -f "$HOME/.claude/requirements.yaml" ]; then
    python3 - "$HOME/.claude/requirements.yaml" << 'EOF' > /dev/null 2>&1
import sys
try:
    import yaml
    with open(sys.argv[1], 'r') as f:
        yaml.safe_load(f)
    sys.exit(0)
except ImportError:
    print("ERROR: PyYAML is required to parse requirements.yaml", file=sys.stderr)
    sys.exit(1)
except Exception as e:
    print(f"ERROR: {e}", file=sys.stderr)
    sys.exit(1)
EOF

    if [ $? -eq 0 ]; then
        echo "   ✅ Global configuration is valid"
    else
        echo "   ❌ Global configuration has syntax errors"
        VERIFICATION_PASSED=false
    fi
else
    echo "   ❌ Global configuration not found"
    VERIFICATION_PASSED=false
fi

echo ""
if [ "$VERIFICATION_PASSED" = true ]; then
    echo "✅ All verification checks passed!"
else
    echo "⚠️  Some verification checks failed"
    echo ""
    echo "Troubleshooting steps:"
    echo "  1. Verify Python 3 is installed and accessible"
    echo "  2. Ensure the plugin is installed: /plugin install requirements-framework@requirements-framework"
    echo "  3. Run: python3 $REPO_DIR/hooks/test_requirements.py"
    echo ""
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Installation Complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📦 What was installed:"
echo "   • 'req' CLI command at ~/.local/bin/req"
echo "   • Global configuration at ~/.claude/requirements.yaml"
echo "   • Phase-aware statusline registered in ~/.claude/settings.json"
echo ""
echo "   🪝 Lifecycle hooks ship with the plugin (single source of truth: hooks.json)."
echo "      Install it to activate them:"
echo "      /plugin install requirements-framework@requirements-framework"
echo ""

# Show Codex status
if [ "$ENABLE_CODEX" = "true" ]; then
    echo "🤖 Codex AI Review: ENABLED"
    if ! command -v codex &> /dev/null; then
        echo "   ⚠️  Next: Install Codex CLI"
        echo "      npm install -g @openai/codex"
        echo "      codex login"
    fi
else
    echo "🤖 Codex AI Review: DISABLED"
    echo "   Enable in ~/.claude/requirements.yaml if needed"
fi
echo ""

# Show PATH status
if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
    echo "⚠️  Action required: Restart your shell to activate 'req' command"
    echo "   Or run: source ~/.zshrc  (or your shell config file)"
    echo ""
fi

echo "📋 Next Steps:"
echo ""
echo "   1. Test the installation:"
echo "      req status"
echo "      req init          # Set up requirements for a project"
echo ""
echo "   2. Review global settings:"
echo "      cat ~/.claude/requirements.yaml"
echo ""
echo "   3. Run comprehensive tests (optional):"
echo "      python3 $REPO_DIR/hooks/test_requirements.py"
echo ""
echo "   4. Enable for your projects:"
echo "      cd your-project"
echo "      req init minimal   # Creates .claude/requirements.yaml"
echo ""
echo "📖 Documentation:"
echo "   • Main README: $REPO_DIR/README.md"
echo "   • Plugin installation: $REPO_DIR/docs/PLUGIN-INSTALLATION.md"
echo "   • Plugin README: $REPO_DIR/plugins/requirements-framework/README.md"
echo "   • Plugin commands: /requirements-framework:pre-commit, /requirements-framework:quality-check"
echo "   • Plugin skills: Type 'show requirements framework status' in Claude Code"
echo "   • Config reference: $REPO_DIR/examples/"
echo ""
echo "🎯 Quick Start:"
echo "   Install the plugin (above) to activate requirement hooks in your sessions."
echo "   You'll then see requirement prompts when editing files."
echo "   Use 'req satisfy <requirement>' to mark requirements as met."
echo ""
