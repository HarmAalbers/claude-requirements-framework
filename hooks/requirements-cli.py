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
from git_utils import get_current_branch, is_git_repo, resolve_project_root
from session import get_session_id, get_active_sessions, cleanup_stale_sessions
from state_storage import list_all_states
from colors import success, error, warning, info, header, hint, dim, bold
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
    """Get current project directory (resolves to git root from subdirectories)."""
    return resolve_project_root()


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
        print(error("❌ Not in a git repository"), file=sys.stderr)
        return 1

    branch = args.branch or get_current_branch(project_dir)

    if not branch:
        print(error("❌ Not on a branch (detached HEAD?)"), file=sys.stderr)
        return 1

    # Get session ID (explicit flag, env var, or PPID)
    if hasattr(args, 'session') and args.session:
        session_id = args.session
    else:
        session_id = get_session_id()

    # Header
    print(header("📋 Requirements Status"))
    print(dim(f"{'─' * 40}"))
    print(f"Branch:  {bold(branch)}")
    print(f"Session: {dim(session_id)}")
    print(f"Project: {dim(project_dir)}")

    # Show active Claude sessions for context
    active_sessions = get_active_sessions(project_dir=project_dir, branch=branch)
    if active_sessions:
        print(info(f"\n🔍 Active Claude Sessions for {branch}:"))
        for sess in active_sessions:
            marker = "→" if sess['id'] == session_id else " "
            age_mins = int((time.time() - sess['last_active']) // 60)
            age_str = f"{age_mins}m ago" if age_mins > 0 else "just now"
            print(dim(f"  {marker} {sess['id']} [PID {sess['pid']}, {age_str}]"))

    print()

    # Check for config
    config_file = Path(project_dir) / '.claude' / 'requirements.yaml'
    config_file_json = Path(project_dir) / '.claude' / 'requirements.json'

    if not config_file.exists() and not config_file_json.exists():
        print(info("ℹ️  No requirements configured for this project."))
        print(dim("   Create .claude/requirements.yaml to enable."))
        return 0

    config = RequirementsConfig(project_dir)

    validation_errors = config.get_validation_errors()
    if validation_errors:
        print(warning("⚠️  Configuration validation failed:"))
        for err in validation_errors:
            print(dim(f"   - {err}"))
        print(dim("   Fix .claude/requirements.yaml and rerun `req status`."))
        print()

    if not config.is_enabled():
        print(warning("⚠️  Requirements framework disabled for this project"))
        return 0

    all_reqs = config.get_all_requirements()
    if not all_reqs:
        print(info("ℹ️  No requirements defined in config."))
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
        print(header("📌 Blocking Requirements:"))
        for req_name in blocking_reqs:
            scope = config.get_scope(req_name)
            satisfied = reqs.is_satisfied(req_name, scope)
            if satisfied:
                print(success(f"  ✅ {req_name}") + dim(f" ({scope})"))
            else:
                print(error(f"  ❌ {req_name}") + dim(f" ({scope})"))

    # Show dynamic requirements
    if dynamic_reqs:
        print(header("\n📊 Dynamic Requirements:"))
        for req_name in dynamic_reqs:
            try:
                # Load calculator
                calculator_name = config.get_attribute(req_name, 'calculator')
                if not calculator_name:
                    print(warning(f"  ⚠️  {req_name}: No calculator configured"))
                    continue

                calc_module = __import__(f'lib.{calculator_name}', fromlist=[calculator_name])
                calculator = calc_module.Calculator()

                # Calculate current value
                result = calculator.calculate(project_dir, branch)

                if result:
                    thresholds = config.get_attribute(req_name, 'thresholds', {})
                    value = result.get('value', 0)

                    # Determine status and color
                    if value >= thresholds.get('block', float('inf')):
                        print(error(f"  🛑 {req_name}: {value} changes"))
                    elif value >= thresholds.get('warn', float('inf')):
                        print(warning(f"  ⚠️ {req_name}: {value} changes"))
                    else:
                        print(success(f"  ✅ {req_name}: {value} changes"))

                    print(dim(f"      {result.get('summary', '')}"))
                    print(dim(f"      Base: {result.get('base_branch', 'N/A')}"))

                    # Show approval status
                    if reqs.is_approved(req_name):
                        req_state = reqs._get_req_state(req_name)
                        session_state = req_state.get('sessions', {}).get(session_id, {})
                        expires_at = session_state.get('expires_at', 0)
                        remaining = int(expires_at - time.time())
                        if remaining > 0:
                            mins = remaining // 60
                            secs = remaining % 60
                            print(info(f"      ⏰ Approved ({mins}m {secs}s remaining)"))
                else:
                    print(info(f"  ℹ️  {req_name}: Not applicable (skipped)"))
            except Exception as e:
                print(warning(f"  ⚠️  {req_name}: Error calculating ({e})"))

    if not blocking_reqs and not dynamic_reqs:
        print(info("ℹ️  No requirements configured."))

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
        print(error("❌ Not in a git repository"), file=sys.stderr)
        return 1

    # Check if --branch was explicitly provided (triggers branch-level satisfaction)
    branch_level_mode = args.branch is not None

    branch = args.branch or get_current_branch(project_dir)

    if not branch:
        print(error("❌ Not on a branch (detached HEAD?)"), file=sys.stderr)
        return 1

    # Check for config
    config_file = Path(project_dir) / '.claude' / 'requirements.yaml'
    config_file_json = Path(project_dir) / '.claude' / 'requirements.json'

    if not config_file.exists() and not config_file_json.exists():
        print(warning("⚠️  No requirements configured for this project."), file=sys.stderr)
        # Still allow satisfying (for testing)

    # Branch-level mode: no session detection needed
    if branch_level_mode:
        session_id = 'branch-override'
        print(info(f"🌿 Using branch-level satisfaction for: {branch}"))
    else:
        # Smart session detection
        session_id = None

        # Priority 1: Explicit --session flag
        if hasattr(args, 'session') and args.session:
            session_id = args.session
            print(info(f"🎯 Using explicit session: {session_id}"))

        # Priority 2: CLAUDE_SESSION_ID env var
        elif 'CLAUDE_SESSION_ID' in os.environ:
            session_id = os.environ['CLAUDE_SESSION_ID']
            print(info(f"🔍 Using env session: {session_id}"))

        # Priority 3: Auto-detect from registry
        else:
            matches = get_active_sessions(project_dir=project_dir, branch=branch)

            if len(matches) == 1:
                session_id = matches[0]['id']
                print(success(f"✨ Auto-detected Claude session: {session_id}"))
            elif len(matches) > 1:
                print(warning("⚠️  Multiple Claude Code sessions found:"), file=sys.stderr)
                for i, sess in enumerate(matches, 1):
                    print(dim(f"   {i}. {sess['id']} [PID {sess['pid']}]"), file=sys.stderr)
                print(hint("\n💡 Use --session flag, or use --branch to satisfy all sessions"), file=sys.stderr)
                return 1
            else:
                # No matches - fall back to PPID
                session_id = get_session_id()
                print(warning(f"⚠️  No active Claude session detected. Using terminal session: {session_id}"))
                print(hint("💡 This may not satisfy requirements in Claude Code."))

    # Get config for scope
    config = RequirementsConfig(project_dir)

    # Parse metadata if provided
    metadata = {}
    if args.metadata:
        try:
            metadata = json.loads(args.metadata)
        except json.JSONDecodeError:
            print(error("❌ Invalid JSON metadata"), file=sys.stderr)
            return 1

    # Initialize requirements manager
    reqs = BranchRequirements(branch, session_id, project_dir)

    # Handle multiple requirements
    requirements = args.requirements
    satisfied_count = 0

    for req_name in requirements:
        # Check if requirement exists in config
        if req_name not in config.get_all_requirements():
            print(warning(f"⚠️  Unknown requirement: {req_name}"), file=sys.stderr)
            available = config.get_all_requirements()
            if available:
                print(dim(f"   Available: {', '.join(available)}"))
            # Still allow satisfying (manual override)

        # Handle based on requirement type
        req_type = config.get_requirement_type(req_name)

        if req_type == 'dynamic':
            if branch_level_mode:
                # Branch-level mode: use branch scope for dynamic requirements too
                reqs.satisfy(req_name, scope='branch', method='cli', metadata=metadata if metadata else None)
                if len(requirements) == 1:
                    print(success(f"✅ Satisfied '{req_name}' at branch level for {branch}"))
                    print(info(f"   ℹ️  All current and future sessions on this branch are now satisfied"))
            else:
                # Dynamic requirement - use approval workflow with TTL
                ttl = config.get_attribute(req_name, 'approval_ttl', 300)

                # Add metadata about method
                req_metadata = metadata.copy() if metadata else {}
                req_metadata['method'] = 'cli'

                reqs.approve_for_session(req_name, ttl, metadata=req_metadata)

                mins = ttl // 60
                secs = ttl % 60
                if len(requirements) == 1:
                    print(success(f"✅ Approved '{req_name}' for {branch}"))
                    print(dim(f"   Duration: {mins}m {secs}s (session scope)"))
                    print(dim(f"   Session: {session_id}"))
        else:
            # Blocking requirement - standard satisfaction
            if branch_level_mode:
                # Force branch scope when --branch is explicit
                reqs.satisfy(req_name, scope='branch', method='cli', metadata=metadata if metadata else None)
                if len(requirements) == 1:
                    print(success(f"✅ Satisfied '{req_name}' at branch level for {branch}"))
                    print(info(f"   ℹ️  All current and future sessions on this branch are now satisfied"))
            else:
                # Use config's scope (existing behavior)
                scope = config.get_scope(req_name)
                reqs.satisfy(req_name, scope, method='cli', metadata=metadata if metadata else None)
                if len(requirements) == 1:
                    print(success(f"✅ Satisfied '{req_name}' for {branch} ({scope} scope)"))

        satisfied_count += 1

    # Summary for multiple requirements
    if len(requirements) > 1:
        if branch_level_mode:
            print(success(f"✅ Satisfied {satisfied_count} requirement(s) at branch level"))
            print(dim(f"   Branch: {branch}"))
            print(info(f"   ℹ️  All current and future sessions on this branch are now satisfied"))
        else:
            print(success(f"✅ Satisfied {satisfied_count} requirement(s) for {branch}"))
        for req_name in requirements:
            scope = 'branch' if branch_level_mode else config.get_scope(req_name)
            print(dim(f"   - {req_name} ({scope} scope)"))

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
        print(error("❌ Not in a git repository"), file=sys.stderr)
        return 1

    branch = args.branch or get_current_branch(project_dir)

    if not branch:
        print(error("❌ Not on a branch (detached HEAD?)"), file=sys.stderr)
        return 1

    # Get session ID (explicit flag, env var, or PPID)
    if hasattr(args, 'session') and args.session:
        session_id = args.session
    else:
        session_id = get_session_id()

    reqs = BranchRequirements(branch, session_id, project_dir)

    if args.all:
        reqs.clear_all()
        print(success(f"✅ Cleared all requirements for {branch}"))
    else:
        if not args.requirement:
            print(error("❌ Specify requirement name or use --all"), file=sys.stderr)
            return 1
        reqs.clear(args.requirement)
        print(success(f"✅ Cleared '{args.requirement}' for {branch}"))

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
        print(error("❌ Not in a git repository"), file=sys.stderr)
        return 1

    states = list_all_states(project_dir)

    if not states:
        print(info("ℹ️  No tracked branches in this project."))
        return 0

    print(header(f"📋 Tracked Branches ({len(states)})"))
    print(dim(f"{'─' * 40}"))

    for branch, path in states:
        # Load state to show requirement count
        try:
            with open(path) as f:
                state = json.load(f)
                req_count = len(state.get('requirements', {}))
                print(f"  {bold(branch)}: {dim(f'{req_count} requirement(s)')}")
        except Exception:
            print(f"  {bold(branch)}: {warning('(error reading state)')}")

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
        print(error("❌ Not in a git repository"), file=sys.stderr)
        return 1

    print(info("🧹 Cleaning up stale state files..."))
    count = BranchRequirements.cleanup_stale_branches(project_dir)
    print(success(f"✅ Removed {count} state file(s) for deleted branches"))

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

    # Project config (informational only - not fatal)
    config_ok, config_msg = _check_project_config(project_dir)
    # Don't fail doctor if project config is missing - it's optional
    icon = "✅" if config_ok else "⚠️"
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
        print(info("ℹ️  No active Claude Code sessions found."))
        return 0

    # Display sessions
    print(header(f"📋 Active Claude Code Sessions ({len(sessions)})"))
    print(dim(f"{'─' * 60}"))

    for sess in sessions:
        age_mins = int((time.time() - sess['last_active']) // 60)
        age_str = f"{age_mins}m ago" if age_mins > 0 else "just now"

        print(f"  {bold(sess['id'])} - {dim(sess['project_dir'])}")
        print(dim(f"             {sess['branch']} [PID {sess['pid']}, {age_str}]"))

    return 0


def cmd_enable(args) -> int:
    """
    Enable requirements framework for current project.

    Creates/updates .claude/requirements.local.yaml with enabled: true.
    This is a local override (gitignored) that doesn't affect the team.

    Usage:
        req enable              # Enable framework
        req enable commit_plan  # Enable specific requirement (future)

    Returns:
        Exit code (0 = success, 1 = error)
    """
    project_dir = get_project_dir()

    # Check if in git repo
    if not is_git_repo(project_dir):
        print(error("❌ Not in a git repository"), file=sys.stderr)
        print(dim("   Requirements framework only works in git repositories"))
        return 1

    # Check if project has any config
    config_file = Path(project_dir) / '.claude' / 'requirements.yaml'
    config_file_json = Path(project_dir) / '.claude' / 'requirements.json'

    if not config_file.exists() and not config_file_json.exists():
        print(info("ℹ️  No requirements configured for this project."), file=sys.stderr)
        print(dim("   Create .claude/requirements.yaml to configure requirements."))
        print(dim("   See: ~/.claude/requirements.yaml for examples"))
        return 1

    config = RequirementsConfig(project_dir)

    # Phase 1: Framework-level enable/disable only
    requirement_name = args.requirement if hasattr(args, 'requirement') and args.requirement else None

    if requirement_name:
        # Phase 2: Requirement-level enable (future enhancement)
        print(error("❌ Requirement-level enable/disable not yet implemented"), file=sys.stderr)
        print(dim("   Use: req enable  (without requirement name)"))
        return 1

    # Enable framework
    try:
        file_path = config.write_local_override(enabled=True)
        print(success("✅ Requirements framework enabled for this project"))
        print(dim(f"   Modified: {file_path}"))
        print()
        print(hint("💡 Run 'req status' to see current requirements"))
        return 0
    except Exception as e:
        print(error(f"❌ Failed to enable framework: {e}"), file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


def cmd_disable(args) -> int:
    """
    Disable requirements framework for current project.

    Creates/updates .claude/requirements.local.yaml with enabled: false.
    This is a local override (gitignored) that doesn't affect the team.

    Usage:
        req disable              # Disable framework
        req disable commit_plan  # Disable specific requirement (future)

    Returns:
        Exit code (0 = success, 1 = error)
    """
    project_dir = get_project_dir()

    # Check if in git repo
    if not is_git_repo(project_dir):
        print(error("❌ Not in a git repository"), file=sys.stderr)
        print(dim("   Requirements framework only works in git repositories"))
        return 1

    config = RequirementsConfig(project_dir)

    # Phase 1: Framework-level enable/disable only
    requirement_name = args.requirement if hasattr(args, 'requirement') and args.requirement else None

    if requirement_name:
        # Phase 2: Requirement-level disable (future enhancement)
        print(error("❌ Requirement-level enable/disable not yet implemented"), file=sys.stderr)
        print(dim("   Use: req disable  (without requirement name)"))
        return 1

    # Disable framework
    try:
        file_path = config.write_local_override(enabled=False)
        print(success("✅ Requirements framework disabled for this project"))
        print(dim(f"   Modified: {file_path}"))
        print()
        print(hint("💡 This only affects your local environment (file is gitignored)"))
        print(hint("💡 To re-enable: req enable"))
        return 0
    except Exception as e:
        print(error(f"❌ Failed to disable framework: {e}"), file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


def cmd_config(args) -> int:
    """
    Manage requirement configuration.

    Show or modify individual requirement settings.

    Args:
        args: Parsed arguments

    Returns:
        Exit code
    """
    project_dir = get_project_dir()

    # Check if git repo
    if not is_git_repo(project_dir):
        print(error("❌ Not in a git repository"), file=sys.stderr)
        return 1

    # Load config
    config = RequirementsConfig(project_dir)
    requirement_name = args.requirement

    # Check if any write flags present
    has_write_flags = (
        args.enable or args.disable or
        args.scope is not None or
        args.message is not None or
        (hasattr(args, 'set') and args.set is not None)
    )

    # Check if requirement exists (unless we're trying to enable a new one)
    req_config = config.get_requirement(requirement_name)
    if not req_config and not has_write_flags:
        print(error(f"❌ Requirement '{requirement_name}' not found"), file=sys.stderr)
        available = config.get_all_requirements()
        if available:
            print(dim(f"   Available: {', '.join(available)}"))
        return 1

    # Read-only mode: show current config
    if not has_write_flags:
        print(header(f"📋 Configuration: {requirement_name}"))
        print(dim("─" * 50))

        # Show all fields with nice formatting
        for key, value in req_config.items():
            if key == 'message':
                # Show truncated message
                if len(str(value)) > 100:
                    lines = str(value).split('\n')
                    print(f"{bold(key)}: {lines[0][:80]}...")
                else:
                    print(f"{bold(key)}: {value}")
            elif isinstance(value, list):
                print(f"{bold(key)}:")
                for item in value:
                    print(f"  - {item}")
            elif isinstance(value, dict):
                print(f"{bold(key)}:")
                for k, v in value.items():
                    print(f"  {k}: {v}")
            else:
                print(f"{bold(key)}: {value}")

        # Show if it's enabled
        print()
        is_enabled = config.is_requirement_enabled(requirement_name)
        if is_enabled:
            print(success(f"✅ Currently enabled"))
        else:
            print(dim(f"⚠️  Currently disabled"))

        return 0

    # Write mode: modify configuration
    from interactive import select, confirm

    # Ask which config to modify (unless explicitly specified)
    if not args.project and not args.local and not args.yes:
        choice = select(
            "Which configuration file to modify?",
            [
                "Local (.claude/requirements.local.yaml) - personal, gitignored",
                "Project (.claude/requirements.yaml) - team-shared, versioned",
            ],
            default=0
        )
        modify_local = "Local" in choice
    else:
        modify_local = args.local or not args.project  # Default to local

    # Build updates dict
    updates = {}
    if args.enable:
        updates['enabled'] = True
    if args.disable:
        updates['enabled'] = False
    if args.scope:
        updates['scope'] = args.scope
    if args.message:
        updates['message'] = args.message

    # Handle --set KEY=VALUE flags
    if hasattr(args, 'set') and args.set:
        for item in args.set:
            if '=' not in item:
                print(error(f"❌ Invalid --set format: {item}"), file=sys.stderr)
                print(dim("   Use: --set KEY=VALUE"), file=sys.stderr)
                return 1
            key, value = item.split('=', 1)
            key = key.strip()
            value = value.strip()

            # Try to parse value as JSON for booleans/numbers/lists
            try:
                import json
                parsed_value = json.loads(value)
                updates[key] = parsed_value
            except (json.JSONDecodeError, ValueError):
                # Keep as string if not valid JSON
                updates[key] = value

    # Show preview
    print()
    print(header(f"Preview changes to {requirement_name}:"))
    print(dim("─" * 50))

    for key, new_value in updates.items():
        old_value = req_config.get(key, "(not set)") if req_config else "(not set)"
        # Truncate long values
        if isinstance(old_value, str) and len(old_value) > 60:
            old_value = old_value[:60] + "..."
        if isinstance(new_value, str) and len(new_value) > 60:
            new_value = new_value[:60] + "..."

        print(f"  {bold(key)}:")
        print(f"    {dim('Before:')} {old_value}")
        print(f"    {success('After:')} {new_value}")

    print()
    target_file = "requirements.local.yaml" if modify_local else "requirements.yaml"
    print(dim(f"Target: .claude/{target_file}"))
    print()

    # Confirm
    if not args.yes:
        if not confirm("Apply these changes?", default=True):
            print(info("ℹ️  Cancelled"))
            return 0

    # Write changes
    try:
        if modify_local:
            file_path = config.write_local_override(
                requirement_overrides={requirement_name: updates}
            )
        else:
            # For project config, need to write differently
            # For now, only support local (will add project support later)
            print(warning("⚠️  Project config modification not yet implemented"))
            print(dim("   Use --local flag to modify local config"))
            return 1

        print(success(f"✅ Updated {requirement_name}"))
        print(dim(f"   Modified: {file_path}"))
        return 0

    except Exception as e:
        print(error(f"❌ Failed to update config: {e}"), file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


def cmd_init(args) -> int:
    """
    Initialize requirements framework for a project.

    Creates .claude/requirements.yaml (and optionally .local.yaml) with
    preset configurations.

    Args:
        args: Parsed arguments

    Returns:
        Exit code
    """
    from init_presets import generate_config, config_to_yaml
    from interactive import select, confirm

    project_dir = get_project_dir()

    # Check if git repo
    if not is_git_repo(project_dir):
        print(error("❌ Not in a git repository"), file=sys.stderr)
        print(dim("   Requirements framework only works in git repositories"))
        return 1

    # Paths
    claude_dir = Path(project_dir) / '.claude'
    project_config = claude_dir / 'requirements.yaml'
    local_config = claude_dir / 'requirements.local.yaml'

    # Interactive mode (default) vs non-interactive (--yes)
    if not args.yes and not args.preview:
        # Show header
        print(header("🚀 Requirements Framework Setup"))
        print(dim("─" * 50))
        print()

        # Detection
        print(info("Detecting project:"))
        print(success(f"  ✓ Git repository at {project_dir}"))
        if claude_dir.exists():
            print(success("  ✓ .claude/ directory exists"))
        else:
            print(dim("  ○ .claude/ directory will be created"))

        if project_config.exists():
            print(warning(f"  ⚠ Project config exists: {project_config.name}"))
        if local_config.exists():
            print(warning(f"  ⚠ Local config exists: {local_config.name}"))
        print()

        # Ask config type (unless --local or --project specified)
        if not args.local and not args.project:
            config_choice = select(
                "Which configuration file to create?",
                [
                    "Project config (.claude/requirements.yaml) - shared with team",
                    "Local config (.claude/requirements.local.yaml) - personal only",
                ],
                default=0
            )
            create_local = "Local" in config_choice
        else:
            create_local = args.local

        # Ask preset (unless --preset specified)
        if not args.preset:
            preset_choice = select(
                "Choose a preset profile:",
                [
                    "relaxed - Light touch: commit_plan only (recommended)",
                    "strict - Full enforcement: commit_plan + protected_branch",
                    "minimal - Framework enabled, no requirements (configure later)",
                ],
                default=0
            )
            if "strict" in preset_choice:
                preset = 'strict'
            elif "minimal" in preset_choice:
                preset = 'minimal'
            else:
                preset = 'relaxed'
        else:
            preset = args.preset

        # Generate and preview
        config = generate_config(preset)
        yaml_content = config_to_yaml(config)

        print()
        print(header("Preview:"))
        print(dim("─" * 50))
        # Show first 20 lines of config
        lines = yaml_content.split('\n')[:20]
        for line in lines:
            print(line)
        if len(yaml_content.split('\n')) > 20:
            print(dim("  ... (truncated)"))
        print(dim("─" * 50))
        print()

        # Confirm
        target_config = local_config if create_local else project_config
        if target_config.exists() and not args.force:
            if not confirm(f"Overwrite existing {target_config.name}?", default=False):
                print(info("ℹ️  Cancelled"))
                return 0
        else:
            if not confirm(f"Create {target_config.name}?", default=True):
                print(info("ℹ️  Cancelled"))
                return 0
    else:
        # Non-interactive mode
        create_local = args.local
        preset = args.preset or 'relaxed'
        config = generate_config(preset)
        yaml_content = config_to_yaml(config)

        # Preview mode (non-interactive)
        if args.preview:
            target = "local" if create_local else "project"
            print(header(f"📋 Preview: {target} config ({preset} preset)"))
            print(dim("─" * 50))
            print(yaml_content)
            print(dim("─" * 50))
            print(info(f"ℹ️  Would create: {local_config if create_local else project_config}"))
            return 0

        # Check for existing config (non-interactive mode only)
        target_config = local_config if create_local else project_config
        if target_config.exists() and not args.force:
            print(warning(f"⚠️  Config already exists: {target_config}"))
            print(hint("💡 Use --force to overwrite"))
            return 0

    # Determine target
    target_config = local_config if create_local else project_config

    # Create .claude directory
    claude_dir.mkdir(parents=True, exist_ok=True)

    # Write config
    try:
        target_config.write_text(yaml_content)
        config_type = "local" if create_local else "project"
        print(success(f"✅ Created {config_type} config ({preset} preset)"))
        print(dim(f"   {target_config}"))
        print()
        print(hint("💡 Next steps:"))
        print(dim("   • Run 'req status' to see your requirements"))
        print(dim("   • Make changes - you'll be prompted to satisfy requirements"))
        print(dim(f"   • Edit {target_config.name} to customize"))
        return 0
    except Exception as e:
        print(error(f"❌ Failed to create config: {e}"), file=sys.stderr)
        return 1


def main() -> int:
    """
    CLI entry point.

    Returns:
        Exit code
    """
    parser = argparse.ArgumentParser(
        prog='req',
        description='Requirements Framework CLI - Manage requirements for Claude Code',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
    req init                            # Initialize with relaxed preset
    req init --preset strict            # Initialize with strict preset
    req init --local                    # Create local config only
    req init --preview                  # Preview config without writing
    req status                          # Show current status
    req config commit_plan              # Show config for commit_plan
    req config adr_reviewed --set adr_path=/docs/adr  # Set ADR location
    req satisfy commit_plan             # Mark commit_plan as satisfied
    req satisfy github_ticket -m '{"ticket":"#123"}'
    req clear commit_plan               # Clear commit_plan
    req clear --all                     # Clear all requirements
    req list                            # List tracked branches
    req prune                           # Clean up stale state
    req sessions                        # List active Claude Code sessions
    req enable                          # Enable framework for this project
    req disable                         # Disable framework for this project

Environment Variables:
    CLAUDE_SKIP_REQUIREMENTS=1          # Globally disable all requirements checks
'''
    )

    subparsers = parser.add_subparsers(dest='command', help='Command')

    # status
    status_parser = subparsers.add_parser('status', help='Show requirements status')
    status_parser.add_argument('--branch', '-b', help='Branch name (default: current)')
    status_parser.add_argument('--session', '-s', metavar='ID', help='Explicit session ID (8 chars)')

    # satisfy
    satisfy_parser = subparsers.add_parser('satisfy', help='Satisfy one or more requirements')
    satisfy_parser.add_argument('requirements', nargs='+', help='Requirement name(s)')
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

    # enable
    enable_parser = subparsers.add_parser('enable', help='Enable requirements framework')
    enable_parser.add_argument('requirement', nargs='?', help='Requirement name (optional, for future use)')

    # disable
    disable_parser = subparsers.add_parser('disable', help='Disable requirements framework')
    disable_parser.add_argument('requirement', nargs='?', help='Requirement name (optional, for future use)')

    # init
    init_parser = subparsers.add_parser('init', help='Initialize requirements framework for project')
    init_parser.add_argument('--yes', '-y', action='store_true', help='Non-interactive mode (use defaults)')
    init_parser.add_argument('--preset', '-p', choices=['strict', 'relaxed', 'minimal'],
                             help='Preset profile (default: relaxed)')
    init_parser.add_argument('--project', action='store_true', help='Create project config only')
    init_parser.add_argument('--local', action='store_true', help='Create local config only')
    init_parser.add_argument('--force', '-f', action='store_true', help='Overwrite existing config')
    init_parser.add_argument('--preview', '--dry-run', action='store_true', help='Preview without writing')

    # config
    config_parser = subparsers.add_parser('config', help='View or modify requirement configuration')
    config_parser.add_argument('requirement', help='Requirement name')
    config_parser.add_argument('--enable', action='store_true', help='Enable requirement')
    config_parser.add_argument('--disable', action='store_true', help='Disable requirement')
    config_parser.add_argument('--scope', choices=['session', 'branch', 'permanent', 'single_use'],
                              help='Set scope')
    config_parser.add_argument('--message', help='Set custom message')
    config_parser.add_argument('--set', action='append', metavar='KEY=VALUE',
                              help='Set arbitrary field (e.g., --set adr_path=/docs/adr)')
    config_parser.add_argument('--project', action='store_true', help='Modify project config')
    config_parser.add_argument('--local', action='store_true', help='Modify local config')
    config_parser.add_argument('--yes', '-y', action='store_true', help='Skip confirmation')

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
        'enable': cmd_enable,
        'disable': cmd_disable,
        'init': cmd_init,
        'config': cmd_config,
        'doctor': cmd_doctor,
    }

    return commands[args.command](args)


if __name__ == '__main__':
    sys.exit(main())
