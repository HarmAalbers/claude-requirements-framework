#!/bin/bash

set -e  # Exit on error

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
cp -v hooks/check-requirements.py "$HOME/.claude/hooks/"
cp -v hooks/requirements-cli.py "$HOME/.claude/hooks/"
cp -v hooks/test_requirements.py "$HOME/.claude/hooks/"
cp -v hooks/handle-session-start.py "$HOME/.claude/hooks/"
cp -v hooks/handle-stop.py "$HOME/.claude/hooks/"
cp -v hooks/handle-session-end.py "$HOME/.claude/hooks/"

# Copy library files
echo "📚 Copying library files to ~/.claude/hooks/lib/..."
cp -v hooks/lib/*.py "$HOME/.claude/hooks/lib/"

# Make scripts executable
chmod +x "$HOME/.claude/hooks/check-requirements.py"
chmod +x "$HOME/.claude/hooks/requirements-cli.py"
chmod +x "$HOME/.claude/hooks/handle-session-start.py"
chmod +x "$HOME/.claude/hooks/handle-stop.py"
chmod +x "$HOME/.claude/hooks/handle-session-end.py"

# Install global configuration if it doesn't exist
if [ ! -f "$HOME/.claude/requirements.yaml" ]; then
    echo "⚙️  Installing global configuration to ~/.claude/requirements.yaml..."
    cp -v examples/global-requirements.yaml "$HOME/.claude/requirements.yaml"
else
    echo "ℹ️  Global configuration already exists at ~/.claude/requirements.yaml"
    echo "   (Not overwriting - see examples/global-requirements.yaml for reference)"
fi

# Create symlink for CLI tool
echo "🔗 Creating symlink for 'req' command..."
mkdir -p "$HOME/.local/bin"
ln -sf "$HOME/.claude/hooks/requirements-cli.py" "$HOME/.local/bin/req"

# Check if ~/.local/bin is in PATH
if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
    echo ""
    echo "⚠️  Warning: $HOME/.local/bin is not in your PATH"
    echo "   Add this to your ~/.bashrc or ~/.zshrc:"
    echo "   export PATH=\"\$HOME/.local/bin:\$PATH\""
fi

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

# Register all four hooks
settings['hooks']['PreToolUse'] = "~/.claude/hooks/check-requirements.py"
settings['hooks']['SessionStart'] = "~/.claude/hooks/handle-session-start.py"
settings['hooks']['Stop'] = "~/.claude/hooks/handle-stop.py"
settings['hooks']['SessionEnd'] = "~/.claude/hooks/handle-session-end.py"

with open(settings_file, 'w') as f:
    json.dump(settings, f, indent=2)

print("   ✅ Registered all hooks in", settings_file)
EOF
else
    # Create new settings file
    echo "   Creating new settings file..."
    cat > "$SETTINGS_FILE" << 'EOF'
{
  "hooks": {
    "PreToolUse": "~/.claude/hooks/check-requirements.py",
    "SessionStart": "~/.claude/hooks/handle-session-start.py",
    "Stop": "~/.claude/hooks/handle-stop.py",
    "SessionEnd": "~/.claude/hooks/handle-session-end.py"
  }
}
EOF
    echo "   ✅ Created $SETTINGS_FILE"
fi

echo ""
echo "✅ Installation complete!"
echo ""
echo "📋 Next steps:"
echo "   1. Review the global configuration: ~/.claude/requirements.yaml"
echo "   2. Enable requirements for your projects by creating .claude/requirements.yaml"
echo "   3. Run 'req status' to check your requirements"
echo "   4. Run 'python3 ~/.claude/hooks/test_requirements.py' to verify installation"
echo ""
echo "📖 For more information, see README.md"
echo ""
