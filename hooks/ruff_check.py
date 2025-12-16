#!/usr/bin/env python3
"""Run ruff check on modified Python files when Claude finishes responding.

Only runs if the project has ruff configured, and uses the project's
virtual environment (uv, poetry, venv) to ensure correct settings.
"""

import os
import subprocess
import sys
from pathlib import Path


def get_git_root() -> Path | None:
    """Get the root directory of the current git repository."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return Path(result.stdout.strip())
    except Exception:
        pass
    return None


def project_has_ruff_config(project_root: Path) -> bool:
    """Check if the project has ruff configured."""
    # Check for ruff-specific config files
    ruff_configs = ["ruff.toml", ".ruff.toml"]
    for config in ruff_configs:
        if (project_root / config).exists():
            return True

    # Check pyproject.toml for [tool.ruff] section
    pyproject = project_root / "pyproject.toml"
    if pyproject.exists():
        try:
            content = pyproject.read_text()
            if "[tool.ruff]" in content:
                return True
            # Also check if ruff is in dependencies
            if "ruff" in content.lower():
                return True
        except Exception:
            pass

    return False


def find_ruff_command(project_root: Path) -> list[str] | None:
    """Find the best way to run ruff for this project.

    Priority:
    1. uv run ruff (if uv.lock exists)
    2. poetry run ruff (if poetry.lock exists)
    3. .venv/bin/ruff or venv/bin/ruff (local venv)
    4. ruff in PATH (if project has ruff config)
    """
    # Check for uv project
    if (project_root / "uv.lock").exists():
        return ["uv", "run", "ruff"]

    # Check for poetry project
    if (project_root / "poetry.lock").exists():
        return ["poetry", "run", "ruff"]

    # Check for local virtual environments
    venv_paths = [
        project_root / ".venv" / "bin" / "ruff",
        project_root / "venv" / "bin" / "ruff",
        project_root / ".venv" / "Scripts" / "ruff.exe",  # Windows
        project_root / "venv" / "Scripts" / "ruff.exe",   # Windows
    ]
    for venv_ruff in venv_paths:
        if venv_ruff.exists():
            return [str(venv_ruff)]

    # Fallback: use global ruff if project has config
    if project_has_ruff_config(project_root):
        # Check if ruff is available globally
        try:
            result = subprocess.run(
                ["which", "ruff"],
                capture_output=True,
                timeout=5,
            )
            if result.returncode == 0:
                return ["ruff"]
        except Exception:
            pass

    return None


def get_modified_python_files(project_root: Path) -> list[str]:
    """Get Python files with uncommitted changes via git."""
    try:
        # Run git commands from project root
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=project_root,
        )
        files = [f for f in result.stdout.strip().split("\n") if f.endswith(".py") and f]

        # Also include untracked Python files
        untracked = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=project_root,
        )
        files.extend(
            [f for f in untracked.stdout.strip().split("\n") if f.endswith(".py") and f]
        )

        # Return absolute paths
        return [str(project_root / f) for f in set(files) if f]
    except Exception:
        return []


def main():
    # Find project root
    project_root = get_git_root()
    if not project_root:
        sys.exit(0)  # Not in a git repo, skip silently

    # Check if project has ruff configured
    if not project_has_ruff_config(project_root):
        print(
            f"⚠️  No ruff configuration found in {project_root}\n"
            f"   Add [tool.ruff] to pyproject.toml, or create ruff.toml\n"
            f"   To disable this hook for this project, add to .claude/settings.local.json:\n"
            f'   {{"hooks": {{"Stop": []}}}}',
            file=sys.stderr,
        )
        sys.exit(2)  # Block and show message to user

    # Find how to run ruff
    ruff_cmd = find_ruff_command(project_root)
    if not ruff_cmd:
        print(
            f"⚠️  Ruff is configured but not installed in {project_root}\n"
            f"   Install with: uv add --dev ruff  OR  pip install ruff",
            file=sys.stderr,
        )
        sys.exit(2)  # Block and show message to user

    # Get modified files
    files = get_modified_python_files(project_root)
    if not files:
        sys.exit(0)  # No Python files modified

    # Show what we're doing
    cmd_display = " ".join(ruff_cmd)
    print(f"🔍 Running `{cmd_display} check` on {len(files)} file(s)...")

    # Run ruff check from project root (so it picks up config)
    result = subprocess.run(
        ruff_cmd + ["check"] + files,
        capture_output=False,  # Show output directly
        cwd=project_root,
    )

    if result.returncode == 0:
        print("✅ No issues found")
    else:
        print(f"⚠️  Ruff found issues (exit code {result.returncode})")

    sys.exit(0)  # Don't block Claude


if __name__ == "__main__":
    main()
