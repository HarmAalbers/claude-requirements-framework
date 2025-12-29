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

# Create hooks directory if it doesn't exist
mkdir -p "$HOME/.claude/hooks/lib"

# Copy hook files
echo "📦 Copying hook files to ~/.claude/hooks/..."
cp -v "$REPO_DIR/hooks/check-requirements.py" "$HOME/.claude/hooks/"
cp -v "$REPO_DIR/hooks/requirements-cli.py" "$HOME/.claude/hooks/"
cp -v "$REPO_DIR/hooks/test_requirements.py" "$HOME/.claude/hooks/"
cp -v "$REPO_DIR/hooks/handle-session-start.py" "$HOME/.claude/hooks/"
cp -v "$REPO_DIR/hooks/handle-stop.py" "$HOME/.claude/hooks/"
cp -v "$REPO_DIR/hooks/handle-session-end.py" "$HOME/.claude/hooks/"

# Copy library files
echo "📚 Copying library files to ~/.claude/hooks/lib/..."
cp -v "$REPO_DIR/hooks/lib/"*.py "$HOME/.claude/hooks/lib/"

# Make scripts executable
chmod +x "$HOME/.claude/hooks/check-requirements.py"
chmod +x "$HOME/.claude/hooks/requirements-cli.py"
chmod +x "$HOME/.claude/hooks/handle-session-start.py"
chmod +x "$HOME/.claude/hooks/handle-stop.py"
chmod +x "$HOME/.claude/hooks/handle-session-end.py"
chmod +x "$HOME/.claude/hooks/auto-satisfy-skills.py"
chmod +x "$HOME/.claude/hooks/clear-single-use.py"
chmod +x "$HOME/.claude/hooks/handle-plan-exit.py"
chmod +x "$HOME/.claude/hooks/ruff_check.py"

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
    echo "  - Uses the /requirements-framework:codex-review skill"
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

# Create symlink for CLI tool
echo ""
echo "🔗 Creating symlink for 'req' command..."
mkdir -p "$HOME/.local/bin"
ln -sf "$HOME/.claude/hooks/requirements-cli.py" "$HOME/.local/bin/req"

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

# Call PATH configuration
configure_path

# Setup plugin symlink
setup_plugin_symlink() {
    echo ""
    echo "🔌 Setting up plugin symlink..."

    local plugin_source="$REPO_DIR/.claude/plugins/requirements-framework"
    local plugin_target="$HOME/.claude/plugins/requirements-framework"

    # Check if plugin exists in repo
    if [ ! -d "$plugin_source" ]; then
        echo "⚠️  Plugin directory not found at $plugin_source"
        echo "   Skipping plugin setup."
        return 0
    fi

    # Create plugins directory if it doesn't exist
    mkdir -p "$HOME/.claude/plugins"

    # Check if symlink or directory already exists
    if [ -L "$plugin_target" ]; then
        # It's a symlink - check if it points to the right place
        local current_target=$(readlink "$plugin_target")
        if [ "$current_target" = "$plugin_source" ]; then
            echo "✅ Plugin symlink already exists and is correct"
            return 0
        else
            echo "⚠️  Plugin symlink exists but points to: $current_target"
            read -p "Replace with correct symlink? [Y/n] " -n 1 -r
            echo
            if [[ ! $REPLY =~ ^[Nn]$ ]]; then
                rm "$plugin_target"
            else
                echo "   Skipped plugin setup"
                return 0
            fi
        fi
    elif [ -e "$plugin_target" ]; then
        # Something exists but it's not a symlink
        echo "⚠️  $plugin_target exists but is not a symlink"
        echo "   Please manually remove it to install the plugin."
        return 1
    fi

    # Create the symlink
    ln -s "$plugin_source" "$plugin_target"

    # Verify symlink
    if [ -L "$plugin_target" ] && [ -d "$plugin_target" ]; then
        echo "✅ Plugin symlinked: ~/.claude/plugins/requirements-framework"
        echo "   → $plugin_source"

        # Show plugin contents for verification
        if [ -f "$plugin_target/.claude-plugin/plugin.json" ]; then
            local plugin_version=$(python3 -c "import json; print(json.load(open('$plugin_target/.claude-plugin/plugin.json'))['version'])" 2>/dev/null || echo "unknown")
            echo "   Plugin version: $plugin_version"
        fi
    else
        echo "❌ Failed to create plugin symlink"
        return 1
    fi

    return 0
}

# Call plugin setup
setup_plugin_symlink

# Register hooks in Claude Code settings
SETTINGS_FILE="$HOME/.claude/settings.local.json"

echo "📝 Registering hooks (PreToolUse, SessionStart, Stop, SessionEnd)..."

if [ -f "$SETTINGS_FILE" ]; then
    # Settings file exists - update hooks
    echo "   Updating existing settings file..."
    python3 << EOF
import json

settings_file = "$SETTINGS_FILE"

with open(settings_file, 'r') as f:
    settings = json.load(f)

if 'hooks' not in settings:
    settings['hooks'] = {}

# Register all four hooks using new array-of-matchers format
# This format is required by Claude Code's current API
settings['hooks']['PreToolUse'] = [{
    "matcher": "*",
    "hooks": [{
        "type": "command",
        "command": "~/.claude/hooks/check-requirements.py"
    }]
}]

settings['hooks']['SessionStart'] = [{
    "matcher": "*",
    "hooks": [{
        "type": "command",
        "command": "~/.claude/hooks/handle-session-start.py"
    }]
}]

settings['hooks']['Stop'] = [{
    "matcher": "*",
    "hooks": [{
        "type": "command",
        "command": "~/.claude/hooks/handle-stop.py"
    }]
}]

settings['hooks']['SessionEnd'] = [{
    "matcher": "*",
    "hooks": [{
        "type": "command",
        "command": "~/.claude/hooks/handle-session-end.py"
    }]
}]

with open(settings_file, 'w') as f:
    json.dump(settings, f, indent=2)

print("   ✅ Registered all hooks in", settings_file)
EOF
else
    # Create new settings file with proper format
    echo "   Creating new settings file..."
    cat > "$SETTINGS_FILE" << 'EOF'
{
  "hooks": {
    "PreToolUse": [{
      "matcher": "*",
      "hooks": [{
        "type": "command",
        "command": "~/.claude/hooks/check-requirements.py"
      }]
    }],
    "SessionStart": [{
      "matcher": "*",
      "hooks": [{
        "type": "command",
        "command": "~/.claude/hooks/handle-session-start.py"
      }]
    }],
    "Stop": [{
      "matcher": "*",
      "hooks": [{
        "type": "command",
        "command": "~/.claude/hooks/handle-stop.py"
      }]
    }],
    "SessionEnd": [{
      "matcher": "*",
      "hooks": [{
        "type": "command",
        "command": "~/.claude/hooks/handle-session-end.py"
      }]
    }]
  }
}
EOF
    echo "   ✅ Created $SETTINGS_FILE"
fi

echo ""
echo "🧪 Verifying installation..."
echo ""

VERIFICATION_PASSED=true

# Test 1: Check if hooks are executable
echo "1️⃣  Checking hook permissions..."
HOOK_OK=true
for hook in check-requirements.py requirements-cli.py handle-session-start.py handle-stop.py handle-session-end.py; do
    if [ ! -x "$HOME/.claude/hooks/$hook" ]; then
        echo "   ❌ Hook not executable: $hook"
        HOOK_OK=false
        VERIFICATION_PASSED=false
    fi
done

if [ "$HOOK_OK" = true ]; then
    echo "   ✅ All hooks are executable"
fi

# Test 2: Check if hooks are registered in settings
echo ""
echo "2️⃣  Checking hook registration..."
if [ -f "$SETTINGS_FILE" ]; then
    python3 - "$SETTINGS_FILE" << 'EOF'
import json
import sys

try:
    with open(sys.argv[1], 'r') as f:
        settings = json.load(f)

    required_hooks = ['PreToolUse', 'SessionStart', 'Stop', 'SessionEnd']
    missing = []

    if 'hooks' not in settings:
        print("   ❌ No hooks section found")
        sys.exit(1)

    for hook in required_hooks:
        if hook not in settings['hooks']:
            missing.append(hook)

    if missing:
        print(f"   ❌ Missing hooks: {', '.join(missing)}")
        sys.exit(1)

    print("   ✅ All hooks registered in settings.local.json")
    sys.exit(0)
except Exception as e:
    print(f"   ❌ Hook registration issue: {e}")
    sys.exit(1)
EOF

    if [ $? -ne 0 ]; then
        VERIFICATION_PASSED=false
    fi
else
    echo "   ❌ settings.local.json not found"
    VERIFICATION_PASSED=false
fi

# Test 3: Check if req command works
echo ""
echo "3️⃣  Checking 'req' command..."
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

# Test 4: Test PreToolUse hook responds correctly
echo ""
echo "4️⃣  Testing PreToolUse hook..."
if echo '{"tool_name":"Read"}' | python3 "$HOME/.claude/hooks/check-requirements.py" > /dev/null 2>&1; then
    echo "   ✅ PreToolUse hook responds correctly"
else
    echo "   ❌ PreToolUse hook failed to respond"
    VERIFICATION_PASSED=false
fi

# Test 5: Test SessionStart hook
echo ""
echo "5️⃣  Testing SessionStart hook..."
if python3 "$HOME/.claude/hooks/handle-session-start.py" > /dev/null 2>&1; then
    echo "   ✅ SessionStart hook responds correctly"
else
    echo "   ❌ SessionStart hook failed"
    VERIFICATION_PASSED=false
fi

# Test 6: Check plugin installation
echo ""
echo "6️⃣  Checking plugin installation..."
if [ -L "$HOME/.claude/plugins/requirements-framework" ]; then
    if [ -d "$HOME/.claude/plugins/requirements-framework" ]; then
        echo "   ✅ Plugin symlink is valid"
    else
        echo "   ❌ Plugin symlink is broken"
        VERIFICATION_PASSED=false
    fi
elif [ -d "$HOME/.claude/plugins/requirements-framework" ]; then
    echo "   ⚠️  Plugin directory exists (not symlinked)"
else
    echo "   ⚠️  Plugin not installed"
fi

# Test 7: Check global config
echo ""
echo "7️⃣  Checking global configuration..."
if [ -f "$HOME/.claude/requirements.yaml" ]; then
    python3 - "$HOME/.claude/requirements.yaml" << 'EOF' > /dev/null 2>&1
import sys
try:
    import yaml
    with open(sys.argv[1], 'r') as f:
        yaml.safe_load(f)
    sys.exit(0)
except ImportError:
    # PyYAML not installed, try JSON fallback
    import json
    with open(sys.argv[1], 'r') as f:
        f.read()
    sys.exit(0)
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
    echo "  1. Check ~/.claude/hooks/ directory permissions"
    echo "  2. Verify Python 3 is installed and accessible"
    echo "  3. Review ~/.claude/settings.local.json for hook configuration"
    echo "  4. Run: python3 ~/.claude/hooks/test_requirements.py"
    echo ""
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Installation Complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📦 What was installed:"
echo "   • 4 lifecycle hooks (PreToolUse, SessionStart, Stop, SessionEnd)"
echo "   • 'req' CLI command at ~/.local/bin/req"
echo "   • Global configuration at ~/.claude/requirements.yaml"
echo "   • Plugin at ~/.claude/plugins/requirements-framework"
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
echo "      python3 ~/.claude/hooks/test_requirements.py"
echo ""
echo "   4. Enable for your projects:"
echo "      cd your-project"
echo "      req init minimal   # Creates .claude/requirements.yaml"
echo ""
echo "📖 Documentation:"
echo "   • README: $REPO_DIR/README.md"
echo "   • Plugin skills: /requirements-framework:*"
echo "   • Config reference: $REPO_DIR/examples/"
echo ""
echo "🎯 Quick Start:"
echo "   The framework is now active for all Claude Code sessions."
echo "   You'll see requirement prompts when editing files."
echo "   Use 'req satisfy <requirement>' to mark requirements as met."
echo ""
