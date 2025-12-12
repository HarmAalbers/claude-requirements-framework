#!/usr/bin/env python3
"""
Requirements Framework CLI Tool

A command-line interface for managing requirements.

Usage:
    req status              # Show current status
    req satisfy <name>      # Mark requirement as satisfied
    req clear <name>        # Clear requirement
    req list                # List all tracked branches
    req prune               # Clean up stale state files

Shell Alias (add to ~/.zshrc or ~/.bashrc):
    alias req='python3 ~/.claude/hooks/requirements-cli.py'
"""
import argparse
import filecmp
import json
import os
import sys
from pathlib import Path

# Add lib to path
lib_path = Path(__file__).parent / 'lib'
sys.path.insert(0, str(lib_path))

from requirements import BranchRequirements
from config import RequirementsConfig
from git_utils import get_current_branch, is_git_repo
from session import get_session_id, get_active_sessions, cleanup_stale_sessions
from state_storage import list_all_states
import time


SYNC_FILES = [
    "check-requirements.py",
    "requirements-cli.py",
    "test_requirements.py",
    "lib/config.py",
    "lib/git_utils.py",
    "lib/requirements.py",
    "lib/session.py",
    "lib/state_storage.py",
]


def get_project_dir() -> str:
    """Get current project directory."""
    return os.environ.get('CLAUDE_PROJECT_DIR', os.getcwd())


def cmd_status(args) -> int:
    """
    Show requirements status for current branch.

    Args:
        args: Parsed arguments

    Returns:
        Exit code
    """
    project_dir = get_project_dir()

    # Check if git repo
    if not is_git_repo(project_dir):
        print("❌ Not in a git repository", file=sys.stderr)
        return 1

    branch = args.branch or get_current_branch(project_dir)

    if not branch:
        print("❌ Not on a branch (detached HEAD?)", file=sys.stderr)
        return 1

    # Get session ID (explicit flag, env var, or PPID)
    if hasattr(args, 'session') and args.session:
        session_id = args.session
    else:
        session_id = get_session_id()

    # Header
    print(f"📋 Requirements Status")
    print(f"{'─' * 40}")
    print(f"Branch:  {branch}")
    print(f"Session: {session_id}")
    print(f"Project: {project_dir}")

    # Show active Claude sessions for context
    active_sessions = get_active_sessions(project_dir=project_dir, branch=branch)
    if active_sessions:
        print(f"\n🔍 Active Claude Sessions for {branch}:")
        for sess in active_sessions:
            marker = "→" if sess['id'] == session_id else " "
            age_mins = int((time.time() - sess['last_active']) // 60)
            age_str = f"{age_mins}m ago" if age_mins > 0 else "just now"
            print(f"  {marker} {sess['id']} [PID {sess['pid']}, {age_str}]")

    print()

    # Check for config
    config_file = Path(project_dir) / '.claude' / 'requirements.yaml'
    config_file_json = Path(project_dir) / '.claude' / 'requirements.json'

    if not config_file.exists() and not config_file_json.exists():
        print("ℹ️  No requirements configured for this project.")
        print(f"   Create .claude/requirements.yaml to enable.")
        return 0

    config = RequirementsConfig(project_dir)

    validation_errors = config.get_validation_errors()
    if validation_errors:
        print("⚠️  Configuration validation failed:")
        for error in validation_errors:
            print(f"   - {error}")
        print("   Fix .claude/requirements.yaml and rerun `req status`.")
        print()

    if not config.is_enabled():
        print("⚠️  Requirements framework disabled for this project")
        return 0

    all_reqs = config.get_all_requirements()
    if not all_reqs:
        print("ℹ️  No requirements defined in config.")
        return 0

    # Initialize requirements manager
    reqs = BranchRequirements(branch, session_id, project_dir)

    # Separate requirements by type
    blocking_reqs = []
    dynamic_reqs = []

    for req_name in all_reqs:
        if not config.is_requirement_enabled(req_name):
            continue
        req_type = config.get_requirement_type(req_name)
        if req_type == 'dynamic':
            dynamic_reqs.append(req_name)
        else:
            blocking_reqs.append(req_name)

    # Show blocking requirements
    if blocking_reqs:
        print("📌 Blocking Requirements:")
        for req_name in blocking_reqs:
            scope = config.get_scope(req_name)
            satisfied = reqs.is_satisfied(req_name, scope)
            icon = "✅" if satisfied else "❌"
            print(f"  {icon} {req_name} ({scope})")

    # Show dynamic requirements
    if dynamic_reqs:
        print("\n📊 Dynamic Requirements:")
        for req_name in dynamic_reqs:
            try:
                # Load calculator
                calculator_name = config.get_attribute(req_name, 'calculator')
                if not calculator_name:
                    print(f"  ⚠️  {req_name}: No calculator configured")
                    continue

                calc_module = __import__(f'lib.{calculator_name}', fromlist=[calculator_name])
                calculator = calc_module.Calculator()

                # Calculate current value
                result = calculator.calculate(project_dir, branch)

                if result:
                    thresholds = config.get_attribute(req_name, 'thresholds', {})
                    value = result.get('value', 0)

                    # Determine status icon
                    if value >= thresholds.get('block', float('inf')):
                        status = "🛑"
                    elif value >= thresholds.get('warn', float('inf')):
                        status = "⚠️"
                    else:
                        status = "✅"

                    print(f"  {status} {req_name}: {value} changes")
                    print(f"      {result.get('summary', '')}")
                    print(f"      Base: {result.get('base_branch', 'N/A')}")

                    # Show approval status
                    if reqs.is_approved(req_name):
                        req_state = reqs._get_req_state(req_name)
                        session_state = req_state.get('sessions', {}).get(session_id, {})
                        expires_at = session_state.get('expires_at', 0)
                        remaining = int(expires_at - time.time())
                        if remaining > 0:
                            mins = remaining // 60
                            secs = remaining % 60
                            print(f"      ⏰ Approved ({mins}m {secs}s remaining)")
                else:
                    print(f"  ℹ️  {req_name}: Not applicable (skipped)")
            except Exception as e:
                print(f"  ⚠️  {req_name}: Error calculating ({e})")

    if not blocking_reqs and not dynamic_reqs:
        print("ℹ️  No requirements configured.")

    return 0


def cmd_satisfy(args) -> int:
    """
    Satisfy a requirement.

    Args:
        args: Parsed arguments

    Returns:
        Exit code
    """
    project_dir = get_project_dir()

    if not is_git_repo(project_dir):
        print("❌ Not in a git repository", file=sys.stderr)
        return 1

    branch = args.branch or get_current_branch(project_dir)

    if not branch:
        print("❌ Not on a branch (detached HEAD?)", file=sys.stderr)
        return 1

    # Check for config
    config_file = Path(project_dir) / '.claude' / 'requirements.yaml'
    config_file_json = Path(project_dir) / '.claude' / 'requirements.json'

    if not config_file.exists() and not config_file_json.exists():
        print("⚠️  No requirements configured for this project.", file=sys.stderr)
        # Still allow satisfying (for testing)

    # Smart session detection
    session_id = None

    # Priority 1: Explicit --session flag
    if hasattr(args, 'session') and args.session:
        session_id = args.session
        print(f"🎯 Using explicit session: {session_id}")

    # Priority 2: CLAUDE_SESSION_ID env var
    elif 'CLAUDE_SESSION_ID' in os.environ:
        session_id = os.environ['CLAUDE_SESSION_ID']
        print(f"🔍 Using env session: {session_id}")

    # Priority 3: Auto-detect from registry
    else:
        matches = get_active_sessions(project_dir=project_dir, branch=branch)

        if len(matches) == 1:
            session_id = matches[0]['id']
            print(f"✨ Auto-detected Claude session: {session_id}")
        elif len(matches) > 1:
            print("⚠️  Multiple Claude Code sessions found:", file=sys.stderr)
            for i, sess in enumerate(matches, 1):
                print(f"   {i}. {sess['id']} [PID {sess['pid']}]", file=sys.stderr)
            print("\n💡 Use --session flag or export CLAUDE_SESSION_ID", file=sys.stderr)
            return 1
        else:
            # No matches - fall back to PPID
            session_id = get_session_id()
            print(f"⚠️  No active Claude session detected. Using terminal session: {session_id}")
            print(f"💡 This may not satisfy requirements in Claude Code.")

    # Get config for scope
    config = RequirementsConfig(project_dir)
    req_name = args.requirement

    # Check if requirement exists in config
    if req_name not in config.get_all_requirements():
        print(f"⚠️  Unknown requirement: {req_name}", file=sys.stderr)
        available = config.get_all_requirements()
        if available:
            print(f"   Available: {', '.join(available)}")
        else:
            print("   No requirements configured.")
        # Still allow satisfying (manual override)

    # Parse metadata if provided
    metadata = {}
    if args.metadata:
        try:
            metadata = json.loads(args.metadata)
        except json.JSONDecodeError:
            print("❌ Invalid JSON metadata", file=sys.stderr)
            return 1

    # Initialize requirements manager
    reqs = BranchRequirements(branch, session_id, project_dir)

    # Handle based on requirement type
    req_type = config.get_requirement_type(req_name)

    if req_type == 'dynamic':
        # Dynamic requirement - use approval workflow with TTL
        ttl = config.get_attribute(req_name, 'approval_ttl', 300)

        # Add metadata about method
        if metadata:
            metadata['method'] = 'cli'
        else:
            metadata = {'method': 'cli'}

        reqs.approve_for_session(req_name, ttl, metadata=metadata)

        mins = ttl // 60
        secs = ttl % 60
        print(f"✅ Approved '{req_name}' for {branch}")
        print(f"   Duration: {mins}m {secs}s (session scope)")
        print(f"   Session: {session_id}")

    else:
        # Blocking requirement - standard satisfaction
        scope = config.get_scope(req_name)
        reqs.satisfy(req_name, scope, method='cli', metadata=metadata if metadata else None)
        print(f"✅ Satisfied '{req_name}' for {branch} ({scope} scope)")

    return 0


def cmd_clear(args) -> int:
    """
    Clear a requirement.

    Args:
        args: Parsed arguments

    Returns:
        Exit code
    """
    project_dir = get_project_dir()

    if not is_git_repo(project_dir):
        print("❌ Not in a git repository", file=sys.stderr)
        return 1

    branch = args.branch or get_current_branch(project_dir)

    if not branch:
        print("❌ Not on a branch (detached HEAD?)", file=sys.stderr)
        return 1

    # Get session ID (explicit flag, env var, or PPID)
    if hasattr(args, 'session') and args.session:
        session_id = args.session
    else:
        session_id = get_session_id()

    reqs = BranchRequirements(branch, session_id, project_dir)

    if args.all:
        reqs.clear_all()
        print(f"✅ Cleared all requirements for {branch}")
    else:
        if not args.requirement:
            print("❌ Specify requirement name or use --all", file=sys.stderr)
            return 1
        reqs.clear(args.requirement)
        print(f"✅ Cleared '{args.requirement}' for {branch}")

    return 0


def cmd_list(args) -> int:
    """
    List all tracked branches.

    Args:
        args: Parsed arguments

    Returns:
        Exit code
    """
    project_dir = get_project_dir()

    if not is_git_repo(project_dir):
        print("❌ Not in a git repository", file=sys.stderr)
        return 1

    states = list_all_states(project_dir)

    if not states:
        print("ℹ️  No tracked branches in this project.")
        return 0

    print(f"📋 Tracked Branches ({len(states)})")
    print(f"{'─' * 40}")

    for branch, path in states:
        # Load state to show requirement count
        try:
            with open(path) as f:
                state = json.load(f)
                req_count = len(state.get('requirements', {}))
                print(f"  {branch}: {req_count} requirement(s)")
        except Exception:
            print(f"  {branch}: (error reading state)")

    return 0


def cmd_prune(args) -> int:
    """
    Clean up stale state files.

    Args:
        args: Parsed arguments

    Returns:
        Exit code
    """
    project_dir = get_project_dir()

    if not is_git_repo(project_dir):
        print("❌ Not in a git repository", file=sys.stderr)
        return 1

    print("🧹 Cleaning up stale state files...")
    count = BranchRequirements.cleanup_stale_branches(project_dir)
    print(f"✅ Removed {count} state file(s) for deleted branches")

    return 0


def _load_settings_file(claude_dir: Path) -> tuple[Path | None, dict]:
    """Load the first available settings file."""

    for filename in ["settings.json", "settings.local.json"]:
        path = claude_dir / filename
        if path.exists():
            try:
                return path, json.loads(path.read_text())
            except json.JSONDecodeError:
                print(f"❌ {path} is not valid JSON", file=sys.stderr)
                return path, {}
    return None, {}


def _check_hook_registration(claude_dir: Path) -> tuple[bool, str]:
    """Verify PreToolUse hook is registered."""

    settings_path, settings = _load_settings_file(claude_dir)
    expected_path = str((claude_dir / "hooks" / "check-requirements.py").expanduser())

    if not settings_path:
        return False, "Missing ~/.claude/settings.json"

    hooks = settings.get("hooks", {})
    hook_path = hooks.get("PreToolUse")

    if not hook_path:
        return False, f"PreToolUse hook not registered in {settings_path}"

    normalized = str(Path(hook_path).expanduser())
    if normalized != expected_path:
        return False, f"PreToolUse hook points to {hook_path} (expected {expected_path})"

    return True, f"PreToolUse hook registered in {settings_path}"


def _check_executable(path: Path) -> tuple[bool, str]:
    """Check that a script exists and is executable."""

    if not path.exists():
        return False, f"Missing {path}"
    if not os.access(path, os.X_OK):
        return False, f"{path} is not executable"
    return True, f"{path} is executable"


def _check_project_config(project_dir: str) -> tuple[bool, str]:
    """Ensure project has a requirements config file."""

    config_path = Path(project_dir) / ".claude" / "requirements.yaml"
    if config_path.exists():
        return True, f"Found project config at {config_path}"

    legacy_path = Path(project_dir) / ".claude" / "requirements.json"
    if legacy_path.exists():
        return False, "Found requirements.json; migrate to requirements.yaml"

    return False, "Missing .claude/requirements.yaml in project"


def _find_repo_dir(explicit: str | None = None) -> Path | None:
    """Locate the hooks repository directory containing sync.sh."""

    candidates = []
    if explicit:
        candidates.append(Path(explicit).expanduser())

    script_repo = Path(__file__).resolve().parent.parent
    candidates.append(script_repo)

    default_repo = Path.home() / "Tools" / "claude-requirements-framework"
    candidates.append(default_repo)

    seen = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        if (candidate / "sync.sh").exists():
            return candidate
    return None


def _compare_repo_and_deployed(repo_dir: Path, deployed_dir: Path) -> tuple[list[tuple[str, str]], list[str]]:
    """Compare repository files to deployed files and suggest actions."""

    results: list[tuple[str, str]] = []
    actions: set[str] = set()

    for relative in SYNC_FILES:
        repo_file = repo_dir / "hooks" / relative
        deployed_file = deployed_dir / relative

        if repo_file.exists() and deployed_file.exists():
            if filecmp.cmp(repo_file, deployed_file, shallow=False):
                results.append((relative, "✓ In sync"))
            else:
                repo_newer = repo_file.stat().st_mtime > deployed_file.stat().st_mtime
                if repo_newer:
                    results.append((relative, "↑ Repository is newer"))
                    actions.add("Deploy repo changes to ~/.claude/hooks (./sync.sh deploy)")
                else:
                    results.append((relative, "↓ Deployed is newer"))
                    actions.add("Pull deployed changes into the repo (./sync.sh pull)")
        elif repo_file.exists():
            results.append((relative, "⚠ Not deployed"))
            actions.add("Deploy repo changes to ~/.claude/hooks (./sync.sh deploy)")
        elif deployed_file.exists():
            results.append((relative, "✗ Missing in repository"))
            actions.add("Pull deployed changes into the repo (./sync.sh pull)")
        else:
            results.append((relative, "✗ Missing in both locations"))

    return results, sorted(actions)


def cmd_doctor(args) -> int:
    """Run environment diagnostics for the requirements framework."""

    project_dir = get_project_dir()
    claude_dir = Path.home() / ".claude"
    hooks_dir = claude_dir / "hooks"

    print("🩺 Running requirements doctor\n")

    status_ok = True

    # Hook registration check
    hook_ok, hook_msg = _check_hook_registration(claude_dir)
    status_ok &= hook_ok
    icon = "✅" if hook_ok else "❌"
    print(f"{icon} {hook_msg}")

    # Executable bits
    for script_name in ["check-requirements.py", "requirements-cli.py"]:
        ok, msg = _check_executable(hooks_dir / script_name)
        status_ok &= ok
        icon = "✅" if ok else "❌"
        print(f"{icon} {msg}")

    # Project config
    config_ok, config_msg = _check_project_config(project_dir)
    status_ok &= config_ok
    icon = "✅" if config_ok else "❌"
    print(f"{icon} {config_msg}")

    # Sync status
    repo_dir = _find_repo_dir(args.repo)
    if repo_dir:
        print("\n📊 Repo vs Deployed")
        results, actions = _compare_repo_and_deployed(repo_dir, hooks_dir)
        for relative, message in results:
            if message.startswith("✓"):
                prefix = "✅"
            elif message.startswith(("↑", "↓", "⚠", "✗")):
                prefix = "⚠️"
            else:
                prefix = "ℹ️"
            print(f"  {prefix} {relative}: {message}")

        if actions:
            status_ok = False
            print("\nRecommended actions:")
            for action in actions:
                print(f"  - {action}")
    else:
        print("\n⚠️ Could not locate repository copy (set --repo to specify path)")

    return 0 if status_ok else 1


def cmd_sessions(args) -> int:
    """
    List active Claude Code sessions.

    Args:
        args: Parsed arguments

    Returns:
        Exit code
    """
    # Clean up stale entries first
    cleanup_stale_sessions()

    # Get project dir filter if requested
    project_dir = get_project_dir() if args.project else None

    # Get active sessions
    sessions = get_active_sessions(project_dir=project_dir)

    if not sessions:
        print("ℹ️  No active Claude Code sessions found.")
        return 0

    # Display sessions
    print(f"📋 Active Claude Code Sessions ({len(sessions)})")
    print(f"{'─' * 60}")

    for sess in sessions:
        age_mins = int((time.time() - sess['last_active']) // 60)
        age_str = f"{age_mins}m ago" if age_mins > 0 else "just now"

        print(f"  {sess['id']} - {sess['project_dir']}")
        print(f"             {sess['branch']} [PID {sess['pid']}, {age_str}]")

    return 0


def main() -> int:
    """
    CLI entry point.

    Returns:
        Exit code
    """
    parser = argparse.ArgumentParser(
        prog='req',
        description='Requirements Framework CLI',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
    req status                          # Show current status
    req satisfy commit_plan             # Mark commit_plan as satisfied
    req satisfy github_ticket -m '{"ticket":"#123"}'
    req clear commit_plan               # Clear commit_plan
    req clear --all                     # Clear all requirements
    req list                            # List tracked branches
    req prune                           # Clean up stale state
'''
    )

    subparsers = parser.add_subparsers(dest='command', help='Command')

    # status
    status_parser = subparsers.add_parser('status', help='Show requirements status')
    status_parser.add_argument('--branch', '-b', help='Branch name (default: current)')
    status_parser.add_argument('--session', '-s', metavar='ID', help='Explicit session ID (8 chars)')

    # satisfy
    satisfy_parser = subparsers.add_parser('satisfy', help='Satisfy a requirement')
    satisfy_parser.add_argument('requirement', help='Requirement name')
    satisfy_parser.add_argument('--branch', '-b', help='Branch name (default: current)')
    satisfy_parser.add_argument('--metadata', '-m', help='JSON metadata')
    satisfy_parser.add_argument('--session', '-s', metavar='ID', help='Explicit session ID (8 chars)')

    # clear
    clear_parser = subparsers.add_parser('clear', help='Clear a requirement')
    clear_parser.add_argument('requirement', nargs='?', help='Requirement name')
    clear_parser.add_argument('--branch', '-b', help='Branch name (default: current)')
    clear_parser.add_argument('--all', '-a', action='store_true', help='Clear all')
    clear_parser.add_argument('--session', '-s', metavar='ID', help='Explicit session ID (8 chars)')

    # list
    subparsers.add_parser('list', help='List tracked branches')

    # prune
    subparsers.add_parser('prune', help='Clean up stale state')

    # sessions
    sessions_parser = subparsers.add_parser('sessions', help='List active Claude Code sessions')
    sessions_parser.add_argument('--project', action='store_true', help='Only show sessions for current project')

    # doctor
    doctor_parser = subparsers.add_parser('doctor', help='Verify hook installation and sync status')
    doctor_parser.add_argument('--repo', help='Path to hooks repository (defaults to auto-detect)')

    args = parser.parse_args()

    if not args.command:
        # Default to status
        args.command = 'status'
        args.branch = None

    commands = {
        'status': cmd_status,
        'satisfy': cmd_satisfy,
        'clear': cmd_clear,
        'list': cmd_list,
        'prune': cmd_prune,
        'sessions': cmd_sessions,
        'doctor': cmd_doctor,
    }

    return commands[args.command](args)


if __name__ == '__main__':
    sys.exit(main())
