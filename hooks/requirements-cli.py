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

# Add lib to path (resolve symlinks to find actual location)
lib_path = Path(__file__).resolve().parent / 'lib'
sys.path.insert(0, str(lib_path))

from requirements import BranchRequirements
from config import RequirementsConfig, load_yaml_or_json
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
        args: Parsed arguments with optional --verbose or --summary flags

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

    # Get session ID (explicit flag or registry lookup)
    if hasattr(args, 'session') and args.session:
        session_id = args.session
    else:
        try:
            session_id = get_session_id()
        except RuntimeError as e:
            # Status is informational - show warning but allow to continue
            print(warning("⚠️  No Claude Code session detected"), file=sys.stderr)
            print(dim("    Showing requirements state without session context"), file=sys.stderr)
            session_id = "no-session"

    # Check for summary mode
    summary_mode = hasattr(args, 'summary') and args.summary
    verbose_mode = hasattr(args, 'verbose') and args.verbose

    # Summary mode - one liner
    if summary_mode:
        return _cmd_status_summary(project_dir, branch, session_id)

    # Focused mode (default) - show only unsatisfied
    if not verbose_mode:
        return _cmd_status_focused(project_dir, branch, session_id, args)

    # Verbose mode - show everything (original behavior)
    return _cmd_status_verbose(project_dir, branch, session_id, args)


def _cmd_status_summary(project_dir: str, branch: str, session_id: str) -> int:
    """One-line summary of requirements status."""
    config = RequirementsConfig(project_dir)

    if not config.is_enabled():
        print(dim("Requirements framework disabled"))
        return 0

    all_reqs = config.get_all_requirements()
    if not all_reqs:
        print(dim("No requirements configured"))
        return 0

    reqs = BranchRequirements(branch, session_id, project_dir)

    satisfied_count = 0
    unsatisfied = []

    for req_name in all_reqs:
        if not config.is_requirement_enabled(req_name):
            continue

        req_type = config.get_requirement_type(req_name)

        # Handle dynamic requirements specially - check approval, not satisfaction
        if req_type == 'dynamic':
            if reqs.is_approved(req_name):
                satisfied_count += 1
            else:
                # For summary, dynamic requirements are "satisfied" unless they would block
                # We don't run expensive calculations here - assume passing unless approved
                satisfied_count += 1
        else:
            # Blocking/guard requirements - check satisfaction
            scope = config.get_scope(req_name)
            if reqs.is_satisfied(req_name, scope):
                satisfied_count += 1
            else:
                unsatisfied.append(req_name)

    total = satisfied_count + len(unsatisfied)

    if unsatisfied:
        print(warning(f"⚠️  {satisfied_count}/{total} requirements satisfied ({', '.join(unsatisfied)} needed)"))
        return 0  # Status command succeeds regardless
    else:
        print(success(f"✅ All {total} requirements satisfied"))
        return 0


def _cmd_status_focused(project_dir: str, branch: str, session_id: str, args) -> int:
    """Focused view - show only unsatisfied requirements."""
    # Header
    print(header("📋 Requirements Status"))
    print(f"Branch: {bold(branch)}")
    print()

    # Check for config
    config_file = Path(project_dir) / '.claude' / 'requirements.yaml'
    config_file_json = Path(project_dir) / '.claude' / 'requirements.json'

    if not config_file.exists() and not config_file_json.exists():
        print(info("ℹ️  No requirements configured for this project."))
        print(dim("   Run 'req init' to set up requirements"))
        return 0

    config = RequirementsConfig(project_dir)

    if not config.is_enabled():
        print(warning("⚠️  Requirements framework disabled"))
        return 0

    all_reqs = config.get_all_requirements()
    if not all_reqs:
        print(info("ℹ️  No requirements defined."))
        return 0

    reqs = BranchRequirements(branch, session_id, project_dir)

    # Find unsatisfied requirements (blocking/guard only - dynamic shown separately)
    unsatisfied_blocking = []
    unsatisfied_dynamic = []

    for req_name in all_reqs:
        if not config.is_requirement_enabled(req_name):
            continue

        req_type = config.get_requirement_type(req_name)

        if req_type == 'dynamic':
            # Dynamic requirements - check if approved (don't run expensive calculations)
            if not reqs.is_approved(req_name):
                unsatisfied_dynamic.append(req_name)
        else:
            # Blocking/guard requirements - check satisfaction
            scope = config.get_scope(req_name)
            if not reqs.is_satisfied(req_name, scope):
                unsatisfied_blocking.append((req_name, scope))

    if not unsatisfied_blocking and not unsatisfied_dynamic:
        print(success("✅ All requirements satisfied"))
        print()
        print(hint("💡 Use 'req status --verbose' for full details"))
        return 0

    # Show unsatisfied blocking requirements
    if unsatisfied_blocking:
        print(error("❌ Unsatisfied Requirements:"))
        print()

        for req_name, scope in unsatisfied_blocking:
            print(f"  • {bold(req_name)} ({dim(scope)} scope)")
            print(dim(f"    → req satisfy {req_name}"))
        print()

    # Show unapproved dynamic requirements (informational)
    if unsatisfied_dynamic:
        print(warning("⚠️  Dynamic Requirements (not yet approved):"))
        print()
        for req_name in unsatisfied_dynamic:
            print(f"  • {bold(req_name)} (needs approval after calculation)")
            print(dim(f"    → req satisfy {req_name}"))
        print()

    # Show combined satisfy hint
    all_unsatisfied_names = [r[0] for r in unsatisfied_blocking] + unsatisfied_dynamic
    if all_unsatisfied_names:
        print(hint(f"💡 Satisfy all: req satisfy {' '.join(all_unsatisfied_names)}"))
    print(dim("   Use 'req status --verbose' for full details"))

    return 0  # Status command succeeds even with unsatisfied requirements


def _cmd_status_verbose(project_dir: str, branch: str, session_id: str, args) -> int:
    """Verbose view - show all details (original behavior)."""
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

        # Priority 2: Auto-detect from registry
        else:
            try:
                session_id = get_session_id()
                print(success(f"✨ Auto-detected Claude session: {session_id}"))
            except RuntimeError as e:
                print(str(e), file=sys.stderr)
                return 1

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
            print(error(f"❌ Unknown requirement: '{req_name}'"), file=sys.stderr)

            # Provide did-you-mean suggestions
            available = config.get_all_requirements()
            if available:
                # Find close matches using simple edit distance
                import difflib
                close_matches = difflib.get_close_matches(req_name, available, n=3, cutoff=0.6)

                if close_matches:
                    print("", file=sys.stderr)
                    print(info("Did you mean?"), file=sys.stderr)
                    for match in close_matches:
                        print(f"  → {match}", file=sys.stderr)

                print("", file=sys.stderr)
                print(dim("Where to define requirements:"), file=sys.stderr)
                print(dim("  • Global:  ~/.claude/requirements.yaml"), file=sys.stderr)
                print(dim("  • Project: .claude/requirements.yaml"), file=sys.stderr)
                print(dim("  • Local:   .claude/requirements.local.yaml"), file=sys.stderr)
                print("", file=sys.stderr)
                print(hint(f"💡 Run 'req init' to set up project requirements"), file=sys.stderr)
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

    # Get session ID (explicit flag or registry lookup)
    if hasattr(args, 'session') and args.session:
        session_id = args.session
    else:
        try:
            session_id = get_session_id()
        except RuntimeError as e:
            print(str(e), file=sys.stderr)
            return 1

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
                content = path.read_text()
                return path, json.loads(content)
            except PermissionError:
                print(f"❌ Cannot read {path}: Permission denied", file=sys.stderr)
                return path, {}
            except UnicodeDecodeError as e:
                print(f"❌ {path} contains invalid UTF-8: {e}", file=sys.stderr)
                return path, {}
            except json.JSONDecodeError:
                print(f"❌ {path} is not valid JSON", file=sys.stderr)
                return path, {}
            except (OSError, IOError) as e:
                print(f"❌ Error reading {path}: {e}", file=sys.stderr)
                return path, {}
    return None, {}


def _extract_path_from_command(command: str, expected_script: str) -> str | None:
    """
    Extract file path from a command string.

    Looks for the expected script name in the command tokens and returns
    the path containing it. Handles various command formats like:
    - "python3 ~/.claude/hooks/check-requirements.py"
    - "~/.claude/hooks/check-requirements.py"
    - "/usr/bin/python3 /home/user/.claude/hooks/check-requirements.py --flag"

    Args:
        command: Command string from hook configuration
        expected_script: Script name to look for (e.g., "check-requirements.py")

    Returns:
        Extracted path if found, None otherwise
    """
    if not isinstance(command, str):
        return None

    # Split command into tokens
    tokens = command.split()

    # Find the token containing the expected script
    for token in tokens:
        if expected_script in token:
            # Strip common surrounding characters
            cleaned = token.strip('";,\'')

            # Verify the cleaned token still contains the script name
            if expected_script in cleaned:
                return cleaned

    return None


def _check_hook_registration(claude_dir: Path) -> tuple[bool, str]:
    """Verify PreToolUse hook is registered (new format only)."""

    settings_path, settings = _load_settings_file(claude_dir)
    expected_script = "check-requirements.py"

    # Safely expand path
    try:
        expected_path = str((claude_dir / "hooks" / expected_script).expanduser())
    except (RuntimeError, OSError) as e:
        return False, f"Failed to expand path for {expected_script}: {e}"

    if not settings_path:
        return False, "Missing ~/.claude/settings.json"

    hooks = settings.get("hooks", {})
    hook_value = hooks.get("PreToolUse")

    if not hook_value:
        return False, f"PreToolUse hook not registered in {settings_path}"

    # Detect old format (string) and show migration message
    if isinstance(hook_value, str):
        return False, (
            f"PreToolUse hook uses old format (string path).\n"
            f"Please upgrade to new format in {settings_path}.\n"
            f"See: https://github.com/anthropics/claude-code/releases"
        )

    # Check if new format (list)
    if not isinstance(hook_value, list):
        actual_type = type(hook_value).__name__
        return False, (
            f"PreToolUse hook has unexpected format in {settings_path}\n"
            f"Expected: list of matchers, Found: {actual_type}"
        )

    # Track validation issues for better diagnostics
    malformed_matchers = 0
    malformed_hooks = 0

    # Iterate through matchers to find our hook
    for matcher_obj in hook_value:
        if not isinstance(matcher_obj, dict):
            malformed_matchers += 1
            continue

        hooks_list = matcher_obj.get("hooks", [])

        # Validate hooks is a list
        if not isinstance(hooks_list, list):
            malformed_hooks += 1
            continue

        for hook_obj in hooks_list:
            if not isinstance(hook_obj, dict):
                malformed_hooks += 1
                continue

            command = hook_obj.get("command", "")
            found_path = _extract_path_from_command(command, expected_script)

            if found_path:
                # Normalize and compare - safely handle path expansion
                try:
                    normalized = str(Path(found_path).expanduser())
                except (RuntimeError, OSError) as e:
                    return False, f"Invalid path in hook configuration '{found_path}': {e}"

                if normalized != expected_path:
                    return False, f"PreToolUse hook points to {found_path} (expected {expected_path})"

                return True, f"PreToolUse hook registered in {settings_path}"

    # Hook not found - provide diagnostic info
    diagnostic_msg = f"PreToolUse hook does not reference {expected_script}"
    if malformed_matchers > 0 or malformed_hooks > 0:
        diagnostic_msg += f"\nWarning: Found {malformed_matchers} malformed matcher(s) and {malformed_hooks} malformed hook(s) in {settings_path}"
        diagnostic_msg += f"\nExpected format: [{{'matcher': '...', 'hooks': [{{'type': 'command', 'command': '...'}}]}}]"

    return False, diagnostic_msg


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


def cmd_verify(args) -> int:
    """
    Verify requirements framework installation.

    Runs a comprehensive check of the installation to ensure
    hooks are properly registered and functioning.

    Returns:
        0 if verification passed, 1 if issues found
    """
    print(header("🧪 Verifying Requirements Framework Installation"))
    print()

    issues_found = False

    # Test 1: Check hook files exist
    print(info("1. Checking hook files..."))
    hook_files = [
        "check-requirements.py",
        "handle-session-start.py",
        "handle-stop.py",
        "handle-session-end.py",
        "requirements-cli.py"
    ]

    hooks_dir = Path.home() / '.claude' / 'hooks'
    missing_files = []
    for hook_file in hook_files:
        hook_path = hooks_dir / hook_file
        if not hook_path.exists():
            missing_files.append(hook_file)
            print(error(f"  ❌ Missing: {hook_file}"))
            issues_found = True
        elif not os.access(hook_path, os.X_OK):
            print(warning(f"  ⚠️  Not executable: {hook_file}"))
            print(dim(f"     Fix: chmod +x ~/.claude/hooks/{hook_file}"))
            issues_found = True

    if not missing_files:
        print(success("  ✅ All hook files present and executable"))

    # Test 2: Check hook registration
    print()
    print(info("2. Checking hook registration..."))
    settings_file = Path.home() / '.claude' / 'settings.local.json'

    if not settings_file.exists():
        print(error("  ❌ settings.local.json not found"))
        print(dim("     Run: ./install.sh to register hooks"))
        issues_found = True
    else:
        try:
            with open(settings_file) as f:
                settings = json.load(f)

            hooks_config = settings.get('hooks', {})
            expected_hooks = ['PreToolUse', 'SessionStart', 'Stop', 'SessionEnd']
            missing_hooks = []

            for hook_type in expected_hooks:
                if hook_type not in hooks_config:
                    missing_hooks.append(hook_type)
                    print(error(f"  ❌ {hook_type} hook not registered"))
                    issues_found = True

            if not missing_hooks:
                print(success("  ✅ All hooks registered in settings"))

        except (json.JSONDecodeError, OSError) as e:
            print(error(f"  ❌ Cannot read settings.local.json: {e}"))
            issues_found = True

    # Test 3: Test PreToolUse hook responds
    print()
    print(info("3. Testing PreToolUse hook response..."))
    hook_path = hooks_dir / "check-requirements.py"

    if hook_path.exists():
        import subprocess
        result = subprocess.run(
            ["python3", str(hook_path)],
            input='{"tool_name":"Read"}',
            capture_output=True,
            text=True,
            timeout=5
        )

        if result.returncode == 0:
            print(success("  ✅ PreToolUse hook responds correctly"))
        else:
            print(error(f"  ❌ Hook exited with code {result.returncode}"))
            if result.stderr:
                print(dim(f"     Error: {result.stderr[:200]}"))
            issues_found = True
    else:
        print(warning("  ⚠️  Skipped (hook file missing)"))

    # Test 4: Check req command accessibility
    print()
    print(info("4. Checking 'req' command..."))
    req_link = Path.home() / '.local' / 'bin' / 'req'

    if req_link.exists():
        print(success("  ✅ 'req' command is accessible"))
    else:
        print(warning("  ⚠️  'req' symlink not found"))
        print(dim("     Run: ./install.sh to create symlink"))

    # Check PATH
    local_bin = str(Path.home() / '.local' / 'bin')
    if local_bin not in os.environ.get('PATH', ''):
        print(warning("  ⚠️  ~/.local/bin not in PATH"))
        print(dim("     Add: export PATH=\"$HOME/.local/bin:$PATH\""))

    # Test 5: Check config exists
    print()
    print(info("5. Checking configuration..."))
    global_config = Path.home() / '.claude' / 'requirements.yaml'

    if global_config.exists():
        print(success("  ✅ Global config exists"))
    else:
        print(warning("  ⚠️  No global config"))
        print(dim("     Run: ./install.sh to install default config"))

    # Summary
    print()
    print("=" * 50)
    if issues_found:
        print(error("❌ Verification failed - issues found"))
        print()
        print(hint("💡 Run './install.sh' to fix installation issues"))
        return 1
    else:
        print(success("✅ Framework fully functional!"))
        print()
        print(hint("💡 Next: Run 'req init' in your project to set up requirements"))
        return 0


# ============================================================================
# Enhanced Doctor Check Functions
# ============================================================================

def _check_python_version() -> dict:
    """Check Python version >= 3.8."""
    import sys
    version = sys.version_info
    passed = version >= (3, 8)
    return {
        'id': 'python_version',
        'category': 'environment',
        'status': 'pass' if passed else 'fail',
        'severity': 'critical',
        'message': f"Python version {version.major}.{version.minor}.{version.micro} {'>=' if passed else '<'} 3.8",
        'fix': None if passed else {
            'description': 'Upgrade Python to 3.8 or newer',
            'safe': False,
            'command': None
        }
    }


def _check_pyyaml_available() -> dict:
    """Check if PyYAML is installed (optional)."""
    try:
        import yaml
        return {
            'id': 'pyyaml',
            'category': 'environment',
            'status': 'pass',
            'severity': 'info',
            'message': 'PyYAML is installed',
            'fix': None
        }
    except ImportError:
        return {
            'id': 'pyyaml',
            'category': 'environment',
            'status': 'pass',  # Not critical
            'severity': 'info',
            'message': 'PyYAML not installed (optional - framework uses JSON fallback)',
            'fix': {
                'description': 'Install PyYAML for better config handling: pip install pyyaml',
                'safe': False,
                'command': None
            }
        }


def _check_hook_file_exists(hook_name: str, hooks_dir: Path) -> dict:
    """Check if a specific hook file exists and is executable."""
    hook_path = hooks_dir / hook_name
    exists = hook_path.exists()
    executable = hook_path.is_file() and os.access(hook_path, os.X_OK) if exists else False

    if not exists:
        status = 'fail'
        message = f"{hook_name} not found"
        fix = {
            'description': f'Reinstall framework to restore {hook_name}',
            'safe': False,
            'command': None
        }
    elif not executable:
        status = 'fail'
        message = f"{hook_name} exists but is not executable"
        fix = {
            'description': f'Make {hook_name} executable',
            'safe': True,
            'command': ['chmod', '+x', str(hook_path)]
        }
    else:
        status = 'pass'
        message = f"{hook_name} exists and is executable"
        fix = None

    return {
        'id': f'hook_file_{hook_name}',
        'category': 'hook_files',
        'status': status,
        'severity': 'critical' if hook_name in ['check-requirements.py', 'handle-session-start.py', 'handle-stop.py'] else 'warning',
        'message': message,
        'fix': fix
    }


def _check_all_hook_files(hooks_dir: Path) -> list:
    """Check all hook files."""
    hooks = [
        'check-requirements.py',
        'handle-session-start.py',
        'handle-stop.py',
        'handle-session-end.py',
        'requirements-cli.py',
        'auto-satisfy-skills.py',
        'clear-single-use.py',
        'handle-plan-exit.py',
        'ruff_check.py'
    ]
    return [_check_hook_file_exists(hook, hooks_dir) for hook in hooks]


def _check_hook_registered(hook_type: str, settings_file: Path) -> dict:
    """Check if a specific hook type is registered in settings."""
    try:
        if not settings_file.exists():
            return {
                'id': f'hook_reg_{hook_type.lower()}',
                'category': 'hook_registration',
                'status': 'fail',
                'severity': 'critical',
                'message': f'{hook_type} hook: settings.local.json not found',
                'fix': {
                    'description': 'Run ./install.sh to create settings file',
                    'safe': False,
                    'command': None
                }
            }

        with open(settings_file, 'r') as f:
            settings = json.load(f)

        if 'hooks' not in settings or hook_type not in settings['hooks']:
            return {
                'id': f'hook_reg_{hook_type.lower()}',
                'category': 'hook_registration',
                'status': 'fail',
                'severity': 'critical',
                'message': f'{hook_type} hook not registered',
                'fix': {
                    'description': 'Run ./install.sh to register hooks',
                    'safe': False,
                    'command': None
                }
            }

        return {
            'id': f'hook_reg_{hook_type.lower()}',
            'category': 'hook_registration',
            'status': 'pass',
            'severity': 'critical',
            'message': f'{hook_type} hook registered',
            'fix': None
        }
    except Exception as e:
        return {
            'id': f'hook_reg_{hook_type.lower()}',
            'category': 'hook_registration',
            'status': 'error',
            'severity': 'critical',
            'message': f'{hook_type} hook: Error reading settings ({e})',
            'fix': {
                'description': 'Fix settings.local.json syntax or run ./install.sh',
                'safe': False,
                'command': None
            }
        }


def _check_all_hook_registrations(settings_file: Path) -> list:
    """Check all required hook registrations."""
    return [_check_hook_registered(hook, settings_file)
            for hook in ['PreToolUse', 'SessionStart', 'Stop', 'SessionEnd']]


def _check_path_configured() -> dict:
    """Check if ~/.local/bin is in PATH."""
    local_bin = str(Path.home() / ".local" / "bin")
    in_path = local_bin in os.environ.get('PATH', '').split(os.pathsep)

    return {
        'id': 'path_configured',
        'category': 'cli',
        'status': 'pass' if in_path else 'fail',
        'severity': 'warning',
        'message': '~/.local/bin is in PATH' if in_path else '~/.local/bin not in PATH',
        'fix': None if in_path else {
            'description': 'Add ~/.local/bin to PATH in your shell profile',
            'safe': False,
            'command': None
        }
    }


def _check_req_command() -> dict:
    """Check if req command is accessible."""
    import shutil
    req_path = shutil.which('req')

    if req_path:
        return {
            'id': 'req_command',
            'category': 'cli',
            'status': 'pass',
            'severity': 'warning',
            'message': f"'req' command accessible at {req_path}",
            'fix': None
        }
    else:
        return {
            'id': 'req_command',
            'category': 'cli',
            'status': 'fail',
            'severity': 'warning',
            'message': "'req' command not found in PATH",
            'fix': {
                'description': 'Ensure ~/.local/bin/req symlink exists and PATH is configured',
                'safe': True,
                'command': ['ln', '-sf', str(Path.home() / '.claude' / 'hooks' / 'requirements-cli.py'),
                           str(Path.home() / '.local' / 'bin' / 'req')]
            }
        }


def _check_plugin_installation() -> dict:
    """Check if plugin is symlinked."""
    plugin_path = Path.home() / ".claude" / "plugins" / "requirements-framework"

    if plugin_path.is_symlink() and plugin_path.is_dir():
        return {
            'id': 'plugin_installed',
            'category': 'plugin',
            'status': 'pass',
            'severity': 'info',
            'message': 'Plugin symlink is valid',
            'fix': None
        }
    elif plugin_path.exists():
        return {
            'id': 'plugin_installed',
            'category': 'plugin',
            'status': 'pass',
            'severity': 'info',
            'message': 'Plugin directory exists (not symlinked)',
            'fix': None
        }
    else:
        return {
            'id': 'plugin_installed',
            'category': 'plugin',
            'status': 'fail',
            'severity': 'info',
            'message': 'Plugin not installed',
            'fix': {
                'description': 'Run enhanced install.sh to set up plugin symlink',
                'safe': False,
                'command': None
            }
        }


def _test_hook_dry_run(hook_name: str, test_input: dict, hooks_dir: Path) -> dict:
    """Test hook execution with sample input (dry-run)."""
    import subprocess
    import json

    hook_path = hooks_dir / hook_name

    if not hook_path.exists():
        return {
            'id': f'hook_test_{hook_name}',
            'category': 'hook_functionality',
            'status': 'fail',
            'severity': 'warning',
            'message': f'{hook_name}: File not found',
            'fix': None
        }

    try:
        result = subprocess.run(
            ['python3', str(hook_path)],
            input=json.dumps(test_input),
            text=True,
            capture_output=True,
            timeout=5
        )

        if result.returncode == 0:
            return {
                'id': f'hook_test_{hook_name}',
                'category': 'hook_functionality',
                'status': 'pass',
                'severity': 'warning',
                'message': f'{hook_name}: Responds correctly',
                'fix': None
            }
        else:
            return {
                'id': f'hook_test_{hook_name}',
                'category': 'hook_functionality',
                'status': 'fail',
                'severity': 'warning',
                'message': f'{hook_name}: Exited with code {result.returncode}',
                'fix': {
                    'description': 'Check hook for errors or reinstall',
                    'safe': False,
                    'command': None
                }
            }
    except subprocess.TimeoutExpired:
        return {
            'id': f'hook_test_{hook_name}',
            'category': 'hook_functionality',
            'status': 'fail',
            'severity': 'warning',
            'message': f'{hook_name}: Timed out after 5 seconds',
            'fix': {
                'description': 'Check hook for infinite loops or reinstall',
                'safe': False,
                'command': None
            }
        }
    except Exception as e:
        return {
            'id': f'hook_test_{hook_name}',
            'category': 'hook_functionality',
            'status': 'error',
            'severity': 'warning',
            'message': f'{hook_name}: Test error ({e})',
            'fix': None
        }


def _test_all_hooks(hooks_dir: Path) -> list:
    """Run dry-run tests on all hooks."""
    tests = [
        ('check-requirements.py', {'tool_name': 'Read'}),
        ('handle-session-start.py', {'hook_event_name': 'SessionStart', 'session_id': 'test1234'}),
        ('handle-stop.py', {'hook_event_name': 'Stop', 'session_id': 'test1234', 'stop_hook_active': False}),
        ('handle-session-end.py', {'hook_event_name': 'SessionEnd', 'session_id': 'test1234'}),
    ]
    return [_test_hook_dry_run(hook, test_input, hooks_dir) for hook, test_input in tests]


def cmd_doctor(args) -> int:
    """
    Run comprehensive environment diagnostics for the requirements framework.

    Args:
        args: Parsed arguments with --verbose, --json, --ci flags

    Returns:
        Exit code (0 if all checks pass, 1 if issues found)
    """
    verbose = hasattr(args, 'verbose') and args.verbose
    json_output = hasattr(args, 'json') and args.json
    ci_mode = hasattr(args, 'ci') and args.ci

    claude_dir = Path.home() / ".claude"
    hooks_dir = claude_dir / "hooks"
    settings_file = claude_dir / "settings.local.json"

    # Run all checks
    all_checks = []

    # Environment checks
    all_checks.append(_check_python_version())
    all_checks.append(_check_pyyaml_available())

    # Hook file checks
    all_checks.extend(_check_all_hook_files(hooks_dir))

    # Hook registration checks (skip in CI mode - settings.local.json won't exist)
    if not ci_mode:
        all_checks.extend(_check_all_hook_registrations(settings_file))

    # CLI checks (skip in CI mode - PATH not relevant)
    if not ci_mode:
        all_checks.append(_check_path_configured())
        all_checks.append(_check_req_command())

    # Plugin check (skip in CI mode - plugin not relevant for code validation)
    if not ci_mode:
        all_checks.append(_check_plugin_installation())

    # Sync status check (if repo is available)
    repo_dir = _find_repo_dir(args.repo if hasattr(args, 'repo') else None)
    if repo_dir:
        results, actions = _compare_repo_and_deployed(repo_dir, hooks_dir)
        for relative, message in results:
            if message.startswith("✓"):
                # In sync
                all_checks.append({
                    'id': f'sync_{relative.replace("/", "_")}',
                    'category': 'sync',
                    'status': 'pass',
                    'severity': 'info',
                    'message': f'{relative}: In sync',
                    'fix': None
                })
            elif message.startswith("↑"):
                # Repository has newer changes
                all_checks.append({
                    'id': f'sync_{relative.replace("/", "_")}',
                    'category': 'sync',
                    'status': 'fail',
                    'severity': 'warning',
                    'message': f'{relative}: Repository has changes',
                    'fix': {
                        'description': 'Run ./sync.sh deploy to sync changes',
                        'safe': False,
                        'command': None
                    }
                })
            elif message.startswith("↓"):
                # Deployed has newer changes
                all_checks.append({
                    'id': f'sync_{relative.replace("/", "_")}',
                    'category': 'sync',
                    'status': 'fail',
                    'severity': 'warning',
                    'message': f'{relative}: Deployed has changes',
                    'fix': {
                        'description': 'Run ./sync.sh pull to sync changes',
                        'safe': False,
                        'command': None
                    }
                })

    # Hook functionality tests (dry-run) - skip in CI mode as hooks won't have full dependencies
    if not ci_mode:
        all_checks.extend(_test_all_hooks(hooks_dir))

    # Analyze results
    critical_issues = [c for c in all_checks if c['status'] in ['fail', 'error'] and c['severity'] == 'critical']
    warnings = [c for c in all_checks if c['status'] in ['fail', 'error'] and c['severity'] == 'warning']
    info_items = [c for c in all_checks if c['status'] == 'pass' or c['severity'] == 'info']

    passed = len([c for c in all_checks if c['status'] == 'pass'])
    total = len(all_checks)

    # JSON output mode
    if json_output:
        result = {
            'status': 'fail' if critical_issues or warnings else 'pass',
            'exit_code': 1 if critical_issues else 0,
            'summary': {
                'total': total,
                'passed': passed,
                'warnings': len(warnings),
                'critical': len(critical_issues)
            },
            'checks': all_checks
        }
        print(json.dumps(result, indent=2))
        return 1 if critical_issues else 0

    # Default/Verbose output mode
    print(header("🩺 Requirements Framework Health Check"))
    print()

    # Show issues if any
    if critical_issues:
        print(error("❌ CRITICAL Issues:"))
        print()
        for check in critical_issues:
            print(f"  ❌ {check['message']}")
            if check['fix']:
                print(dim(f"     Fix: {check['fix']['description']}"))
            print()

    if warnings:
        print(error("⚠️  Warnings:"))
        print()
        for check in warnings:
            print(f"  ⚠️  {check['message']}")
            if check['fix']:
                print(dim(f"     Fix: {check['fix']['description']}"))
            print()

    # Summary
    if not critical_issues and not warnings:
        print(success("✅ All checks passed!"))
        print()
        print(f"  {passed}/{total} checks completed successfully")
    else:
        print(f"  Status: {passed}/{total} checks passed")
        if critical_issues:
            print(f"  Critical issues: {len(critical_issues)}")
        if warnings:
            print(f"  Warnings: {len(warnings)}")
        print()

    # Verbose mode: show all checks
    if verbose and info_items:
        print(header("ℹ️  All Checks:"))
        print()
        for check in all_checks:
            icon = "✅" if check['status'] == 'pass' else "❌" if check['severity'] == 'critical' else "⚠️"
            print(f"  {icon} {check['message']}")
        print()

    # Hints
    if not verbose and (critical_issues or warnings):
        print(hint("💡 Use 'req doctor --verbose' for full diagnostics"))
        print(hint("💡 Use 'req doctor --json' for machine-readable output"))

    return 1 if critical_issues else 0


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

    # Write flags require a requirement name
    if has_write_flags and not requirement_name:
        print(error("❌ Requirement name required when using write flags"), file=sys.stderr)
        print(dim("   Usage: req config <requirement> --enable|--disable|--scope|..."), file=sys.stderr)
        return 1

    # Check for "show" mode (display full merged config)
    if not requirement_name or requirement_name == 'show':
        return _cmd_config_show(config, args)

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
            # Project config modification
            try:
                file_path = config.write_project_override(
                    requirement_overrides={requirement_name: updates}
                )
            except ImportError as e:
                print(error(f"❌ {e}"), file=sys.stderr)
                return 1

        print(success(f"✅ Updated {requirement_name}"))
        print(dim(f"   Modified: {file_path}"))
        return 0

    except Exception as e:
        print(error(f"❌ Failed to update config: {e}"), file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


def _cmd_config_show(config: RequirementsConfig, args) -> int:
    """Show full merged configuration from all cascade levels."""

    # Handle --sources mode separately
    if args.sources:
        return _cmd_config_show_with_sources(config, args)

    try:
        # Get fully merged config
        merged_config = config.get_raw_config()

        # Display header
        print(header("📋 Requirements Framework Configuration"))
        print(dim("─" * 60))
        print(dim("Merged from: global → project → local"))
        print()

        # Output JSON
        output = json.dumps(merged_config, indent=2, sort_keys=False)
        print(output)

    except TypeError as e:
        print(error(f"❌ Config contains non-serializable value: {e}"), file=sys.stderr)
        print(dim("   Check your config files for invalid types"), file=sys.stderr)
        return 1
    except Exception as e:
        print(error(f"❌ Failed to load config: {e}"), file=sys.stderr)
        return 1

    return 0


def _cmd_config_show_with_sources(config: RequirementsConfig, args) -> int:
    """Show configuration with source file breakdown."""
    project_dir = config.project_dir

    # Load each level separately
    global_file = Path.home() / '.claude' / 'requirements.yaml'
    project_file = Path(project_dir) / '.claude' / 'requirements.yaml'
    local_file = Path(project_dir) / '.claude' / 'requirements.local.yaml'

    sources = {}
    for name, path in [
        ('global', global_file),
        ('project', project_file),
        ('local', local_file)
    ]:
        if path.exists():
            try:
                sources[name] = load_yaml_or_json(path)
            except (OSError, IOError) as e:
                print(warning(f"⚠️  Failed to read {name} config: {path}"), file=sys.stderr)
                print(dim(f"   Error: {e}"), file=sys.stderr)
                sources[name] = {}
            except (json.JSONDecodeError, ValueError) as e:
                print(warning(f"⚠️  Failed to parse {name} config: {path}"), file=sys.stderr)
                print(dim(f"   Error: {e}"), file=sys.stderr)
                sources[name] = {}
            except Exception as e:
                print(warning(f"⚠️  Unexpected error loading {name} config: {path}"), file=sys.stderr)
                print(dim(f"   Error: {type(e).__name__}: {e}"), file=sys.stderr)
                sources[name] = {}
        else:
            sources[name] = {}

    # Display each level
    print(header("📋 Configuration Sources"))
    print(dim("─" * 60))

    for level in ['global', 'project', 'local']:
        config_data = sources[level]
        file_path = _get_config_path(level, project_dir)

        print()
        print(bold(f"{level.upper()} ({file_path}):"))
        if config_data:
            try:
                print(json.dumps(config_data, indent=2))
            except TypeError as e:
                print(error(f"❌ Non-serializable value in {level} config: {e}"), file=sys.stderr)
                print(dim("  (skipped)"))
        else:
            print(dim("  (not present)"))

    # Show merged result
    print()
    print(header("MERGED RESULT:"))
    print(dim("─" * 60))
    try:
        merged = config.get_raw_config()
        print(json.dumps(merged, indent=2))
    except TypeError as e:
        print(error(f"❌ Merged config contains non-serializable value: {e}"), file=sys.stderr)
        print(dim("   Check your config files for invalid types"), file=sys.stderr)
        return 1
    except Exception as e:
        print(error(f"❌ Failed to load merged config: {e}"), file=sys.stderr)
        return 1

    return 0


def _get_config_path(level: str, project_dir: str) -> str:
    """Get config file path for given level.

    Args:
        level: One of 'global', 'project', or 'local'
        project_dir: Project directory path

    Returns:
        File path as string

    Raises:
        ValueError: If level is not a valid option
    """
    if level == 'global':
        return str(Path.home() / '.claude' / 'requirements.yaml')
    elif level == 'project':
        return str(Path(project_dir) / '.claude' / 'requirements.yaml')
    elif level == 'local':
        return str(Path(project_dir) / '.claude' / 'requirements.local.yaml')

    raise ValueError(f"Invalid config level: {level!r}. Must be 'global', 'project', or 'local'")


def _detect_init_context(args, project_dir: str) -> str:
    """
    Detect if user is creating global, project, or local config.

    Returns: 'global', 'project', or 'local'
    """
    # Explicit flags take precedence
    if args.local:
        return 'local'
    if args.project:
        return 'project'

    # Check if we're in home directory or .claude directory
    home_claude = Path.home() / '.claude'
    try:
        if Path(project_dir).resolve() == home_claude.resolve():
            return 'global'
    except (OSError, RuntimeError) as e:
        # Path resolution failed - log warning and default to project
        print(warning(f"⚠️  Path resolution failed, defaulting to project context"), file=sys.stderr)
        print(dim(f"   Error: {e}"), file=sys.stderr)

    # Default: project
    return 'project'


def _get_preset_options_for_context(context: str) -> tuple:
    """
    Return (preset_options, default_index) for context.

    Args:
        context: 'global', 'project', or 'local'

    Returns:
        Tuple of (list of preset option strings, default index)
    """
    if context == 'global':
        return (
            [
                'advanced - All features (recommended for global)',
                'relaxed - Baseline requirements only',
                'minimal - Framework enabled, configure later',
            ],
            0  # Default to 'advanced'
        )
    elif context == 'local':
        return (
            [
                'minimal - Override specific settings only',
            ],
            0
        )
    else:  # project
        global_config = Path.home() / '.claude' / 'requirements.yaml'
        if global_config.exists():
            return (
                [
                    'inherit - Use global defaults (recommended)',
                    'relaxed - Override with relaxed preset',
                    'minimal - Start minimal',
                ],
                0  # Default to 'inherit'
            )
        else:
            return (
                [
                    'inherit - Use global when created',
                    'relaxed - Standalone requirements',
                    'minimal - Framework enabled, no requirements',
                ],
                1  # Default to 'relaxed' if no global
            )


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

    # Detect context (global/project/local)
    context = _detect_init_context(args, project_dir)

    # Paths
    claude_dir = Path(project_dir) / '.claude'
    project_config = claude_dir / 'requirements.yaml'
    local_config = claude_dir / 'requirements.local.yaml'
    global_config = Path.home() / '.claude' / 'requirements.yaml'

    # Determine target file based on context
    if context == 'global':
        target_file = global_config
        create_local = False
    elif context == 'local':
        target_file = local_config
        create_local = True
    else:  # project
        target_file = project_config
        create_local = False

    # Interactive mode (default) vs non-interactive (--yes)
    if not args.yes and not args.preview:
        # Show context-specific header
        if context == 'global':
            print(header("🌍 Global Requirements Framework Setup"))
            print(dim("   Setting up defaults for all your projects"))
        elif context == 'local':
            print(header("📝 Local Requirements Override Setup"))
            print(dim("   Creating personal overrides (gitignored)"))
        else:  # project
            print(header("🚀 Project Requirements Setup"))
            if global_config.exists():
                print(dim("   Configuring project-specific requirements"))
            else:
                print(dim("   Setting up project requirements"))
        print(dim("─" * 50))
        print()

        # Context-specific detection info
        print(info("Detecting environment:"))
        print(success(f"  ✓ Git repository at {project_dir}"))

        if context == 'global':
            if global_config.exists():
                print(warning(f"  ⚠ Global config exists"))
        else:
            if claude_dir.exists():
                print(success("  ✓ .claude/ directory exists"))
            else:
                print(dim("  ○ .claude/ directory will be created"))

            if context == 'project' and global_config.exists():
                print(success(f"  ✓ Global config found"))
                print(dim("     Project will inherit from global defaults"))

            if project_config.exists():
                print(warning(f"  ⚠ Project config exists"))
            if local_config.exists() and context == 'local':
                print(warning(f"  ⚠ Local config exists"))

        if context == 'project' and not global_config.exists():
            print(warning("  ⚠ No global config found"))
            print(dim("     Tip: Run 'req init' to create global defaults first"))

        print()

        # Ask: preset or custom feature selection?
        if not args.preset:
            mode = select(
                "How would you like to configure?",
                [
                    "Quick Preset - Choose from preset profiles (recommended)",
                    "Custom Selection - Pick specific features",
                    "Manual Setup - Start minimal, configure later",
                ],
                default=0
            )

            if "Custom" in mode:
                # Custom feature selection
                from lib.feature_selector import FeatureSelector

                selector = FeatureSelector()
                selected_features = selector.select_features_interactive()

                config = selector.build_config_from_features(selected_features, context)
                preset = f"custom ({len(selected_features)} features)"

            elif "Manual" in mode:
                # Manual setup - minimal preset
                preset = 'minimal'
                config = generate_config(preset, context=context)

            else:  # Quick Preset
                # Get context-appropriate preset options
                preset_options, default_idx = _get_preset_options_for_context(context)

                preset_choice = select(
                    "Choose a preset profile:",
                    preset_options,
                    default=default_idx
                )
                # Extract preset name from choice
                preset = preset_choice.split(' - ')[0]
                config = generate_config(preset, context=context)
        else:
            # --preset flag specified
            preset = args.preset
            config = generate_config(preset, context=context)

        # Generate YAML
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
        if target_file.exists() and not args.force:
            if not confirm(f"Overwrite existing {target_file.name}?", default=False):
                print(info("ℹ️  Cancelled"))
                return 0
        else:
            if not confirm(f"Create {target_file.name}?", default=True):
                print(info("ℹ️  Cancelled"))
                return 0
    else:
        # Non-interactive mode
        preset = args.preset or 'relaxed'
        config = generate_config(preset, context=context)
        yaml_content = config_to_yaml(config)

        # Preview mode (non-interactive)
        if args.preview:
            context_name = context.capitalize()
            print(header(f"📋 Preview: {context_name} config ({preset} preset)"))
            print(dim("─" * 50))
            print(yaml_content)
            print(dim("─" * 50))
            print(info(f"ℹ️  Would create: {target_file}"))
            return 0

        # Check for existing config (non-interactive mode only)
        if target_file.exists() and not args.force:
            print(warning(f"⚠️  Config already exists: {target_file}"))
            print(hint("💡 Use --force to overwrite"))
            return 0

    # Create parent directory if needed
    target_file.parent.mkdir(parents=True, exist_ok=True)

    # Write config
    try:
        target_file.write_text(yaml_content)
        context_name = context.capitalize() if context != 'project' else 'project'
        print(success(f"✅ Created {context_name} config ({preset} preset)"))
        print(dim(f"   {target_file}"))
        print()
        print(hint("💡 Next steps:"))
        print(dim("   • Run 'req status' to see your requirements"))
        print(dim("   • Make changes - you'll be prompted to satisfy requirements"))
        print(dim(f"   • Edit {target_file.name} to customize"))
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
    status_parser.add_argument('--verbose', '-v', action='store_true', help='Show all details (sessions, all requirements)')
    status_parser.add_argument('--summary', action='store_true', help='One-line summary only')

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
    init_parser.add_argument('--preset', '-p', choices=['strict', 'relaxed', 'minimal', 'advanced', 'inherit'],
                             help='Preset profile (context-aware defaults)')
    init_parser.add_argument('--project', action='store_true', help='Create project config only')
    init_parser.add_argument('--local', action='store_true', help='Create local config only')
    init_parser.add_argument('--force', '-f', action='store_true', help='Overwrite existing config')
    init_parser.add_argument('--preview', '--dry-run', action='store_true', help='Preview without writing')

    # config
    config_parser = subparsers.add_parser('config', help='View or modify requirement configuration')
    config_parser.add_argument('requirement', nargs='?',
                              help='Requirement name (or "show" to display full config)')
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
    config_parser.add_argument('--sources', action='store_true',
                              help='Show which file each setting comes from')

    # verify
    subparsers.add_parser('verify', help='Verify framework installation is working correctly')

    # doctor
    doctor_parser = subparsers.add_parser('doctor', help='Run comprehensive framework diagnostics')
    doctor_parser.add_argument('--repo', help='Path to hooks repository (defaults to auto-detect)')
    doctor_parser.add_argument('--verbose', '-v', action='store_true', help='Show all checks including passing ones')
    doctor_parser.add_argument('--json', action='store_true', help='Output results in JSON format for scripting')
    doctor_parser.add_argument('--ci', action='store_true', help='CI-friendly mode: only fail on code/hook issues, not missing Claude Code config')

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
        'verify': cmd_verify,
        'doctor': cmd_doctor,
    }

    return commands[args.command](args)


if __name__ == '__main__':
    sys.exit(main())
