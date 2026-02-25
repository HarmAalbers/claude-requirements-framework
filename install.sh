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
cp -v "$REPO_DIR/hooks/auto-satisfy-skills.py" "$HOME/.claude/hooks/"
cp -v "$REPO_DIR/hooks/clear-single-use.py" "$HOME/.claude/hooks/"
cp -v "$REPO_DIR/hooks/handle-plan-exit.py" "$HOME/.claude/hooks/"
cp -v "$REPO_DIR/hooks/ruff_check.py" "$HOME/.claude/hooks/"
cp -v "$REPO_DIR/hooks/handle-teammate-idle.py" "$HOME/.claude/hooks/"
cp -v "$REPO_DIR/hooks/handle-task-completed.py" "$HOME/.claude/hooks/"

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
chmod +x "$HOME/.claude/hooks/handle-teammate-idle.py"
chmod +x "$HOME/.claude/hooks/handle-task-completed.py"

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

# Display marketplace installation instructions
display_marketplace_instructions() {
    echo ""
    echo "📦 Plugin Installation Options:"
    echo ""
    echo "   **Option 1: Test with CLI Flag (Recommended for Development)**"
    echo "   Launch Claude Code with plugin temporarily loaded:"
    echo "   $ claude --plugin-dir $REPO_DIR/plugins/requirements-framework"
    echo ""
    echo "   **Option 2: Persistent Installation via Marketplace**"
    echo "   For permanent installation, use the local marketplace:"
    echo "   1. In Claude Code session, run:"
    echo "      /plugin marketplace add $REPO_DIR"
    echo "   2. Then install the plugin:"
    echo "      /plugin install requirements-framework@requirements-framework"
    echo "   3. Verify:"
    echo "      /requirements-framework:pre-commit"
    echo ""
    echo "   📖 For more details: $REPO_DIR/docs/PLUGIN-INSTALLATION.md"
}

# Show marketplace instructions
display_marketplace_instructions

# Configure hooks in settings.json (primary hook registration location)
configure_settings_json_hooks() {
    local settings_file="$HOME/.claude/settings.json"

    # Use Python to safely create/merge hooks into settings.json
    python3 << 'PYTHON_SCRIPT'
import json
import os
import sys

settings_file = os.path.expanduser("~/.claude/settings.json")

# Required hooks configuration
REQUIRED_HOOKS = {
    "PreToolUse": [{
        "matcher": "*",
        "hooks": [{
            "type": "command",
            "command": "~/.claude/hooks/check-requirements.py"
        }]
    }],
    "PostToolUse": [{
        "matcher": "*",
        "hooks": [
            {"type": "command", "command": "~/.claude/hooks/auto-satisfy-skills.py"},
            {"type": "command", "command": "~/.claude/hooks/clear-single-use.py"},
            {"type": "command", "command": "~/.claude/hooks/handle-plan-exit.py"}
        ]
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
    }],
    "TeammateIdle": [{
        "matcher": "*",
        "hooks": [{
            "type": "command",
            "command": "~/.claude/hooks/handle-teammate-idle.py"
        }]
    }],
    "TaskCompleted": [{
        "matcher": "*",
        "hooks": [{
            "type": "command",
            "command": "~/.claude/hooks/handle-task-completed.py"
        }]
    }]
}

try:
    # Load existing settings or create new
    if os.path.exists(settings_file):
        with open(settings_file, 'r') as f:
            settings = json.load(f)
        print("   Updating existing settings.json...")
    else:
        settings = {}
        print("   Creating new settings.json...")

    # Get existing hooks or empty dict
    existing_hooks = settings.get("hooks", {})

    # Merge: add our hooks if not already present or if empty
    for hook_name, hook_config in REQUIRED_HOOKS.items():
        if hook_name not in existing_hooks:
            existing_hooks[hook_name] = hook_config
        # If exists but empty, replace it
        elif not existing_hooks[hook_name]:
            existing_hooks[hook_name] = hook_config

    settings["hooks"] = existing_hooks

    # Ensure disableAllHooks is false
    settings["disableAllHooks"] = False

    with open(settings_file, 'w') as f:
        json.dump(settings, f, indent=2)

    print("   ✅ Hooks configured in settings.json")

except (IOError, OSError, json.JSONDecodeError) as e:
    print(f"   ❌ Could not configure settings.json: {e}", file=sys.stderr)
    sys.exit(1)
except Exception as e:
    print(f"   ❌ Unexpected error configuring settings.json: {e}", file=sys.stderr)
    sys.exit(1)
PYTHON_SCRIPT

    if [ $? -ne 0 ]; then
        echo "   ❌ Hook configuration failed"
        return 1
    fi
}

# Migrate old settings.local.json hooks if present
migrate_settings_local_json() {
    local local_settings="$HOME/.claude/settings.local.json"

    if [[ ! -f "$local_settings" ]]; then
        return 0
    fi

    # Check if it has our hooks and clean them up
    python3 << 'PYTHON_SCRIPT'
import json
import os
import sys

local_settings = os.path.expanduser("~/.claude/settings.local.json")

try:
    with open(local_settings, 'r') as f:
        settings = json.load(f)

    hooks = settings.get("hooks", {})
    if not hooks:
        sys.exit(0)  # No hooks to migrate

    # Check if these are our hooks (contain our hook paths)
    our_hooks = [
        "check-requirements.py", "handle-session-start.py", "handle-stop.py",
        "handle-session-end.py", "auto-satisfy-skills.py", "clear-single-use.py",
        "handle-plan-exit.py"
    ]
    has_our_hooks = False

    for hook_config in hooks.values():
        if isinstance(hook_config, list):
            for matcher in hook_config:
                if isinstance(matcher, dict):
                    for h in matcher.get("hooks", []):
                        cmd = h.get("command", "")
                        if any(our_hook in cmd for our_hook in our_hooks):
                            has_our_hooks = True
                            break

    if has_our_hooks:
        # Remove hooks section (our hooks are now in settings.json)
        del settings["hooks"]

        if settings:
            # Other settings exist, keep the file
            with open(local_settings, 'w') as f:
                json.dump(settings, f, indent=2)
            print("   📦 Migrated hooks from settings.local.json (file kept with other settings)")
        else:
            # File only had our hooks, remove it
            os.remove(local_settings)
            print("   📦 Removed settings.local.json (hooks migrated to settings.json)")

except Exception as e:
    # Non-fatal - just skip migration
    print(f"   ⚠️  Could not migrate settings.local.json: {e}")
PYTHON_SCRIPT
}

# Register hooks in Claude Code settings.json (single source of truth)
echo "📝 Registering hooks in settings.json..."
if ! configure_settings_json_hooks; then
    echo ""
    echo "❌ Critical: Hook configuration failed. Installation cannot continue."
    exit 1
fi

# Migrate any old settings.local.json hooks
migrate_settings_local_json

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

# Test 2: Check if hooks are registered in settings.json
echo ""
echo "2️⃣  Checking hook registration in settings.json..."
if [ -f "$HOME/.claude/settings.json" ]; then
    python3 - "$HOME/.claude/settings.json" << 'EOF'
import json
import sys

try:
    with open(sys.argv[1], 'r') as f:
        settings = json.load(f)

    required_hooks = ['PreToolUse', 'SessionStart', 'Stop', 'SessionEnd', 'PostToolUse']
    missing = []
    empty = []

    hooks = settings.get('hooks', {})

    # Check for empty hooks object
    if hooks == {}:
        print("   ❌ hooks object is empty in settings.json")
        sys.exit(1)

    for hook in required_hooks:
        if hook not in hooks:
            missing.append(hook)
        elif not hooks[hook]:
            empty.append(hook)

    if missing:
        print(f"   ❌ Missing hooks: {', '.join(missing)}")
        sys.exit(1)

    if empty:
        print(f"   ❌ Empty hooks: {', '.join(empty)}")
        sys.exit(1)

    print("   ✅ All hooks registered in settings.json")
    sys.exit(0)
except Exception as e:
    print(f"   ❌ Hook registration issue: {e}")
    sys.exit(1)
EOF

    if [ $? -ne 0 ]; then
        VERIFICATION_PASSED=false
    fi
else
    echo "   ❌ settings.json not found"
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
if echo '{}' | python3 "$HOME/.claude/hooks/handle-session-start.py" > /dev/null 2>&1; then
    echo "   ✅ SessionStart hook responds correctly"
else
    echo "   ❌ SessionStart hook failed"
    VERIFICATION_PASSED=false
fi

# Test 6: Check plugin marketplace
echo ""
echo "6️⃣  Checking plugin marketplace..."
if [ -f "$REPO_DIR/.claude-plugin/marketplace.json" ]; then
    marketplace_version=$(python3 -c "import json; print(json.load(open('$REPO_DIR/.claude-plugin/marketplace.json'))['plugins'][0]['version'])" 2>/dev/null || echo "unknown")
    echo "   ✅ Local marketplace available (v$marketplace_version)"
    echo "   ℹ️  Install plugin via: /plugin install requirements-framework@requirements-framework"
else
    echo "   ⚠️  Marketplace manifest not found"
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
    echo "  1. Check ~/.claude/hooks/ directory permissions"
    echo "  2. Verify Python 3 is installed and accessible"
    echo "  3. Review ~/.claude/settings.json for hook configuration"
    echo "  4. Run: python3 ~/.claude/hooks/test_requirements.py"
    echo ""
fi

# Check if hooks are globally disabled in settings.json
echo ""
if grep -q '"disableAllHooks"[[:space:]]*:[[:space:]]*true' "$HOME/.claude/settings.json" 2>/dev/null; then
    echo "⚠️  WARNING: Hooks are globally disabled"
    echo "   Your hooks are registered but won't run because ~/.claude/settings.json has:"
    echo "   \"disableAllHooks\": true"
    echo ""
    echo "   To enable hooks, edit ~/.claude/settings.json and change to:"
    echo "   \"disableAllHooks\": false"
    echo ""
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Installation Complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📦 What was installed:"
echo "   • 7 lifecycle hooks (PreToolUse, PostToolUse, SessionStart, Stop, SessionEnd, TeammateIdle, TaskCompleted)"
echo "   • 'req' CLI command at ~/.local/bin/req"
echo "   • Global configuration at ~/.claude/requirements.yaml"
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
echo "   • Main README: $REPO_DIR/README.md"
echo "   • Plugin installation: $REPO_DIR/docs/PLUGIN-INSTALLATION.md"
echo "   • Plugin README: $REPO_DIR/plugins/requirements-framework/README.md"
echo "   • Plugin commands: /requirements-framework:pre-commit, /requirements-framework:quality-check"
echo "   • Plugin skills: Type 'show requirements framework status' in Claude Code"
echo "   • Config reference: $REPO_DIR/examples/"
echo ""
echo "🎯 Quick Start:"
echo "   The framework is now active for all Claude Code sessions."
echo "   You'll see requirement prompts when editing files."
echo "   Use 'req satisfy <requirement>' to mark requirements as met."
echo ""
