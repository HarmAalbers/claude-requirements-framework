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
from config import RequirementsConfig, load_yaml
from git_utils import get_current_branch, is_git_repo, resolve_project_root
from session import get_session_id, get_active_sessions, cleanup_stale_sessions, SessionNotFoundError
from session_metrics import list_session_metrics, load_metrics
from learning_updates import get_recent_updates, get_learning_stats, mark_rolled_back, get_update_by_id
from state_storage import list_all_states
from colors import success, error, warning, info, header, hint, dim, bold
from console import emit_text
from progress import ProgressReporter, show_progress, clear_progress
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


def out(*args, **kwargs) -> None:
    """Emit CLI output through a single helper."""
    stream = kwargs.pop("file", sys.stdout)
    sep = kwargs.pop("sep", " ")
    end = kwargs.pop("end", "\n")
    if kwargs:
        raise TypeError(f"unexpected keyword arguments: {', '.join(kwargs.keys())}")

    message = sep.join(str(arg) for arg in args)
    if end == "\n":
        emit_text(message, stream=stream)
        return

    try:
        stream.write(f"{message}{end}")
        stream.flush()
    except Exception:
        pass


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
        out(error("❌ Not in a git repository"), file=sys.stderr)
        return 1

    branch = args.branch or get_current_branch(project_dir)

    if not branch:
        out(error("❌ Not on a branch (detached HEAD?)"), file=sys.stderr)
        return 1

    # Get session ID (explicit flag or registry lookup)
    if hasattr(args, 'session') and args.session:
        session_id = args.session
    else:
        try:
            session_id = get_session_id()
        except SessionNotFoundError:
            # Status is informational - show warning but allow to continue
            out(warning("⚠️  No Claude Code session detected"), file=sys.stderr)
            out(dim("    Showing requirements state without session context"), file=sys.stderr)
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
        out(dim("Requirements framework disabled"))
        return 0

    all_reqs = config.get_all_requirements()
    if not all_reqs:
        out(dim("No requirements configured"))
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

            # Context-aware checking for guard requirements
            if req_type == 'guard':
                context = {
                    'branch': branch,
                    'session_id': session_id,
                    'project_dir': project_dir,
                }
                if reqs.is_guard_satisfied(req_name, config, context):
                    satisfied_count += 1
                else:
                    unsatisfied.append(req_name)
            else:
                if reqs.is_satisfied(req_name, scope):
                    satisfied_count += 1
                else:
                    unsatisfied.append(req_name)

    total = satisfied_count + len(unsatisfied)

    if unsatisfied:
        out(warning(f"⚠️  {satisfied_count}/{total} requirements satisfied ({', '.join(unsatisfied)} needed)"))
        return 0  # Status command succeeds regardless
    else:
        out(success(f"✅ All {total} requirements satisfied"))
        return 0


def _cmd_status_focused(project_dir: str, branch: str, session_id: str, args) -> int:
    """Focused view - show only unsatisfied requirements."""
    # Header
    out(header("📋 Requirements Status"))
    out(f"Branch: {bold(branch)}")
    out()

    # Check for config
    config_file = Path(project_dir) / '.claude' / 'requirements.yaml'

    if not config_file.exists():
        out(info("ℹ️  No requirements configured for this project."))
        out(dim("   Run 'req init' to set up requirements"))
        return 0

    config = RequirementsConfig(project_dir)

    if not config.is_enabled():
        out(warning("⚠️  Requirements framework disabled"))
        return 0

    all_reqs = config.get_all_requirements()
    if not all_reqs:
        out(info("ℹ️  No requirements defined."))
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

            # Context-aware checking for guard requirements
            if req_type == 'guard':
                context = {
                    'branch': branch,
                    'session_id': session_id,
                    'project_dir': project_dir,
                }
                if not reqs.is_guard_satisfied(req_name, config, context):
                    unsatisfied_blocking.append((req_name, scope))
            else:
                if not reqs.is_satisfied(req_name, scope):
                    unsatisfied_blocking.append((req_name, scope))

    if not unsatisfied_blocking and not unsatisfied_dynamic:
        out(success("✅ All requirements satisfied"))
        out()
        out(hint("💡 Use 'req status --verbose' for full details"))
        return 0

    # Show unsatisfied blocking requirements
    if unsatisfied_blocking:
        out(error("❌ Unsatisfied Requirements:"))
        out()

        for req_name, scope in unsatisfied_blocking:
            out(f"  • {bold(req_name)} ({dim(scope)} scope)")
            out(dim(f"    → req satisfy {req_name}"))
        out()

    # Show unapproved dynamic requirements (informational)
    if unsatisfied_dynamic:
        out(warning("⚠️  Dynamic Requirements (not yet approved):"))
        out()
        for req_name in unsatisfied_dynamic:
            out(f"  • {bold(req_name)} (needs approval after calculation)")
            out(dim(f"    → req satisfy {req_name}"))
        out()

    # Show combined satisfy hint
    all_unsatisfied_names = [r[0] for r in unsatisfied_blocking] + unsatisfied_dynamic
    if all_unsatisfied_names:
        out(hint(f"💡 Satisfy all: req satisfy {' '.join(all_unsatisfied_names)}"))
    out(dim("   Use 'req status --verbose' for full details"))

    return 0  # Status command succeeds even with unsatisfied requirements


def _cmd_status_verbose(project_dir: str, branch: str, session_id: str, args) -> int:
    """Verbose view - show all details (original behavior)."""
    # Check if timing mode is enabled
    timing_mode = hasattr(args, 'timing') and args.timing

    # Start timing if requested
    timing_reporter = ProgressReporter("Status check", debug=True) if timing_mode else None
    if timing_reporter:
        timing_reporter.status("loading config")

    # Header
    out(header("📋 Requirements Status"))
    out(dim(f"{'─' * 40}"))
    out(f"Branch:  {bold(branch)}")
    out(f"Session: {dim(session_id)}")
    out(f"Project: {dim(project_dir)}")

    # Show active Claude sessions for context
    active_sessions = get_active_sessions(project_dir=project_dir, branch=branch)
    if active_sessions:
        out(info(f"\n🔍 Active Claude Sessions for {branch}:"))
        for sess in active_sessions:
            marker = "→" if sess['id'] == session_id else " "
            age_mins = int((time.time() - sess['last_active']) // 60)
            age_str = f"{age_mins}m ago" if age_mins > 0 else "just now"
            out(dim(f"  {marker} {sess['id']} [PID {sess['pid']}, {age_str}]"))

    out()

    # Check for config
    config_file = Path(project_dir) / '.claude' / 'requirements.yaml'

    if not config_file.exists():
        out(info("ℹ️  No requirements configured for this project."))
        out(dim("   Create .claude/requirements.yaml to enable."))
        return 0

    config = RequirementsConfig(project_dir)

    validation_errors = config.get_validation_errors()
    if validation_errors:
        out(warning("⚠️  Configuration validation failed:"))
        for err in validation_errors:
            out(dim(f"   - {err}"))
        out(dim("   Fix .claude/requirements.yaml and rerun `req status`."))
        out()

    if not config.is_enabled():
        out(warning("⚠️  Requirements framework disabled for this project"))
        return 0

    all_reqs = config.get_all_requirements()
    if not all_reqs:
        out(info("ℹ️  No requirements defined in config."))
        return 0

    # Initialize requirements manager
    if timing_reporter:
        timing_reporter.status("initializing requirements manager")
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
        if timing_reporter:
            timing_reporter.status("checking blocking requirements")
        out(header("📌 Blocking Requirements:"))
        for req_name in blocking_reqs:
            scope = config.get_scope(req_name)
            req_type = config.get_requirement_type(req_name)

            # Context-aware checking for guard requirements
            if req_type == 'guard':
                context = {
                    'branch': branch,
                    'session_id': session_id,
                    'project_dir': project_dir,
                }
                satisfied = reqs.is_guard_satisfied(req_name, config, context)
            else:
                satisfied = reqs.is_satisfied(req_name, scope)

            if satisfied:
                out(success(f"  ✅ {req_name}") + dim(f" ({scope})"))
            else:
                out(error(f"  ❌ {req_name}") + dim(f" ({scope})"))

    # Show dynamic requirements
    if dynamic_reqs:
        if timing_reporter:
            timing_reporter.status("calculating dynamic requirements")
        out(header("\n📊 Dynamic Requirements:"))
        for req_name in dynamic_reqs:
            try:
                # Show progress for slow dynamic calculations
                if timing_reporter:
                    timing_reporter.status(f"calculating {req_name}")
                show_progress("Calculating", req_name)

                # Get dynamic config using type-safe accessor
                req_config = config.get_dynamic_config(req_name)
                if not req_config:
                    clear_progress()
                    out(warning(f"  ⚠️  {req_name}: Dynamic requirement not found"))
                    continue

                # Type system now guarantees these fields exist
                calculator_name = req_config['calculator']
                thresholds = req_config['thresholds']

                calc_module = __import__(f'lib.{calculator_name}', fromlist=[calculator_name])
                calculator = calc_module.Calculator()

                # Calculate current value
                result = calculator.calculate(project_dir, branch)
                clear_progress()

                if result:
                    value = result.get('value', 0)

                    # Determine status and color
                    if value >= thresholds.get('block', float('inf')):
                        out(error(f"  🛑 {req_name}: {value} changes"))
                    elif value >= thresholds.get('warn', float('inf')):
                        out(warning(f"  ⚠️ {req_name}: {value} changes"))
                    else:
                        out(success(f"  ✅ {req_name}: {value} changes"))

                    out(dim(f"      {result.get('summary', '')}"))
                    out(dim(f"      Base: {result.get('base_branch', 'N/A')}"))

                    # Show approval status
                    if reqs.is_approved(req_name):
                        req_state = reqs._get_req_state(req_name)
                        session_state = req_state.get('sessions', {}).get(session_id, {})
                        expires_at = session_state.get('expires_at', 0)
                        remaining = int(expires_at - time.time())
                        if remaining > 0:
                            mins = remaining // 60
                            secs = remaining % 60
                            out(info(f"      ⏰ Approved ({mins}m {secs}s remaining)"))
                else:
                    out(info(f"  ℹ️  {req_name}: Not applicable (skipped)"))
            except Exception as e:
                out(warning(f"  ⚠️  {req_name}: Error calculating ({e})"))

    if not blocking_reqs and not dynamic_reqs:
        out(info("ℹ️  No requirements configured."))

    # Output timing report if requested
    if timing_reporter:
        timing_reporter.status("complete")
        out()
        out(header("⏱️  Timing Breakdown:"))
        out(dim(timing_reporter.get_timing_report()))

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
        out(error("❌ Not in a git repository"), file=sys.stderr)
        return 1

    # Check if --branch was explicitly provided (triggers branch-level satisfaction)
    branch_level_mode = args.branch is not None

    branch = args.branch or get_current_branch(project_dir)

    if not branch:
        out(error("❌ Not on a branch (detached HEAD?)"), file=sys.stderr)
        return 1

    # Check for config
    config_file = Path(project_dir) / '.claude' / 'requirements.yaml'

    if not config_file.exists():
        out(warning("⚠️  No requirements configured for this project."), file=sys.stderr)
        # Still allow satisfying (for testing)

    # Branch-level mode: no session detection needed
    if branch_level_mode:
        session_id = 'branch-override'
        out(info(f"🌿 Using branch-level satisfaction for: {branch}"))
    else:
        # Smart session detection
        session_id = None

        # Priority 1: Explicit --session flag
        if hasattr(args, 'session') and args.session:
            session_id = args.session
            out(info(f"🎯 Using explicit session: {session_id}"))

        # Priority 2: Auto-detect from registry
        else:
            try:
                session_id = get_session_id()
                out(success(f"✨ Auto-detected Claude session: {session_id}"))
            except SessionNotFoundError as e:
                out(str(e), file=sys.stderr)
                return 1

    # Get config for scope
    config = RequirementsConfig(project_dir)

    # Parse metadata if provided
    metadata = {}
    if args.metadata:
        try:
            metadata = json.loads(args.metadata)
        except json.JSONDecodeError:
            out(error("❌ Invalid JSON metadata"), file=sys.stderr)
            return 1

    # Initialize requirements manager
    reqs = BranchRequirements(branch, session_id, project_dir)

    # Handle multiple requirements
    requirements = args.requirements
    satisfied_count = 0

    for req_name in requirements:
        # Check if requirement exists in config
        if req_name not in config.get_all_requirements():
            out(error(f"❌ Unknown requirement: '{req_name}'"), file=sys.stderr)

            # Provide did-you-mean suggestions
            available = config.get_all_requirements()
            if available:
                # Find close matches using simple edit distance
                import difflib
                close_matches = difflib.get_close_matches(req_name, available, n=3, cutoff=0.6)

                if close_matches:
                    out("", file=sys.stderr)
                    out(info("Did you mean?"), file=sys.stderr)
                    for match in close_matches:
                        out(f"  → {match}", file=sys.stderr)

                out("", file=sys.stderr)
                out(dim("Where to define requirements:"), file=sys.stderr)
                out(dim("  • Global:  ~/.claude/requirements.yaml"), file=sys.stderr)
                out(dim("  • Project: .claude/requirements.yaml"), file=sys.stderr)
                out(dim("  • Local:   .claude/requirements.local.yaml"), file=sys.stderr)
                out("", file=sys.stderr)
                out(hint("💡 Run 'req init' to set up project requirements"), file=sys.stderr)
            # Still allow satisfying (manual override)

        # Handle based on requirement type
        req_type = config.get_requirement_type(req_name)

        if req_type == 'dynamic':
            if branch_level_mode:
                # Branch-level mode: use branch scope for dynamic requirements too
                reqs.satisfy(req_name, scope='branch', method='cli', metadata=metadata if metadata else None)
                if len(requirements) == 1:
                    out(success(f"✅ Satisfied '{req_name}' at branch level for {branch}"))
                    out(info("   ℹ️  All current and future sessions on this branch are now satisfied"))
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
                    out(success(f"✅ Approved '{req_name}' for {branch}"))
                    out(dim(f"   Duration: {mins}m {secs}s (session scope)"))
                    out(dim(f"   Session: {session_id}"))
        else:
            # Blocking requirement - standard satisfaction
            # Track bypass for plan-related requirements satisfied via CLI
            plan_requirements = {'commit_plan', 'adr_reviewed', 'tdd_planned'}
            if req_name in plan_requirements:
                method = 'cli_bypass'
                req_metadata = metadata.copy() if metadata else {}
                req_metadata['bypass'] = True
                req_metadata['method'] = 'cli_manual'
            else:
                method = 'cli'
                req_metadata = metadata if metadata else None

            if branch_level_mode:
                # Force branch scope when --branch is explicit
                reqs.satisfy(req_name, scope='branch', method=method, metadata=req_metadata)
                if len(requirements) == 1:
                    out(success(f"✅ Satisfied '{req_name}' at branch level for {branch}"))
                    out(info("   ℹ️  All current and future sessions on this branch are now satisfied"))
            else:
                # Use config's scope (existing behavior)
                scope = config.get_scope(req_name)
                reqs.satisfy(req_name, scope, method=method, metadata=req_metadata)
                if len(requirements) == 1:
                    out(success(f"✅ Satisfied '{req_name}' for {branch} ({scope} scope)"))

        satisfied_count += 1

    # Summary for multiple requirements
    if len(requirements) > 1:
        if branch_level_mode:
            out(success(f"✅ Satisfied {satisfied_count} requirement(s) at branch level"))
            out(dim(f"   Branch: {branch}"))
            out(info("   ℹ️  All current and future sessions on this branch are now satisfied"))
        else:
            out(success(f"✅ Satisfied {satisfied_count} requirement(s) for {branch}"))
        for req_name in requirements:
            scope = 'branch' if branch_level_mode else config.get_scope(req_name)
            out(dim(f"   - {req_name} ({scope} scope)"))

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
        out(error("❌ Not in a git repository"), file=sys.stderr)
        return 1

    branch = args.branch or get_current_branch(project_dir)

    if not branch:
        out(error("❌ Not on a branch (detached HEAD?)"), file=sys.stderr)
        return 1

    # Get session ID (explicit flag or registry lookup)
    if hasattr(args, 'session') and args.session:
        session_id = args.session
    else:
        try:
            session_id = get_session_id()
        except SessionNotFoundError as e:
            out(str(e), file=sys.stderr)
            return 1

    reqs = BranchRequirements(branch, session_id, project_dir)

    if args.all:
        reqs.clear_all()
        out(success(f"✅ Cleared all requirements for {branch}"))
    else:
        if not args.requirement:
            out(error("❌ Specify requirement name or use --all"), file=sys.stderr)
            return 1
        reqs.clear(args.requirement)
        out(success(f"✅ Cleared '{args.requirement}' for {branch}"))

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
        out(error("❌ Not in a git repository"), file=sys.stderr)
        return 1

    states = list_all_states(project_dir)

    if not states:
        out(info("ℹ️  No tracked branches in this project."))
        return 0

    out(header(f"📋 Tracked Branches ({len(states)})"))
    out(dim(f"{'─' * 40}"))

    for branch, path in states:
        # Load state to show requirement count
        try:
            with open(path) as f:
                state = json.load(f)
                req_count = len(state.get('requirements', {}))
                out(f"  {bold(branch)}: {dim(f'{req_count} requirement(s)')}")
        except Exception:
            out(f"  {bold(branch)}: {warning('(error reading state)')}")

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
        out(error("❌ Not in a git repository"), file=sys.stderr)
        return 1

    out(info("🧹 Cleaning up stale state files..."))
    count = BranchRequirements.cleanup_stale_branches(project_dir)
    out(success(f"✅ Removed {count} state file(s) for deleted branches"))

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
                out(f"❌ Cannot read {path}: Permission denied", file=sys.stderr)
                return path, {}
            except UnicodeDecodeError as e:
                out(f"❌ {path} contains invalid UTF-8: {e}", file=sys.stderr)
                return path, {}
            except json.JSONDecodeError:
                out(f"❌ {path} is not valid JSON", file=sys.stderr)
                return path, {}
            except (OSError, IOError) as e:
                out(f"❌ Error reading {path}: {e}", file=sys.stderr)
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
        diagnostic_msg += "\nExpected format: [{'matcher': '...', 'hooks': [{'type': 'command', 'command': '...'}]}]"

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
                    actions.add("Copy deployed changes into the repo before deploying")
        elif repo_file.exists():
            results.append((relative, "⚠ Not deployed"))
            actions.add("Deploy repo changes to ~/.claude/hooks (./sync.sh deploy)")
        elif deployed_file.exists():
            results.append((relative, "✗ Missing in repository"))
            actions.add("Copy deployed changes into the repo before deploying")
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
    out(header("🧪 Verifying Requirements Framework Installation"))
    out()

    issues_found = False

    # Test 1: Check hook files exist
    out(info("1. Checking hook files..."))
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
            out(error(f"  ❌ Missing: {hook_file}"))
            issues_found = True
        elif not os.access(hook_path, os.X_OK):
            out(warning(f"  ⚠️  Not executable: {hook_file}"))
            out(dim(f"     Fix: chmod +x ~/.claude/hooks/{hook_file}"))
            issues_found = True

    if not missing_files:
        out(success("  ✅ All hook files present and executable"))

    # Test 2: Check hook registration
    out()
    out(info("2. Checking hook registration..."))
    settings_path, settings = _load_settings_file(claude_dir)

    if not settings_path:
        out(error("  ❌ settings.json not found"))
        out(dim("     Run: ./install.sh to register hooks"))
        issues_found = True
    else:
        hooks_config = settings.get('hooks', {})
        expected_hooks = ['PreToolUse', 'SessionStart', 'Stop', 'SessionEnd']
        missing_hooks = []

        for hook_type in expected_hooks:
            if hook_type not in hooks_config:
                missing_hooks.append(hook_type)
                out(error(f"  ❌ {hook_type} hook not registered"))
                issues_found = True

        if not missing_hooks:
            out(success("  ✅ All hooks registered in settings"))

    # Test 3: Test PreToolUse hook responds
    out()
    out(info("3. Testing PreToolUse hook response..."))
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
            out(success("  ✅ PreToolUse hook responds correctly"))
        else:
            out(error(f"  ❌ Hook exited with code {result.returncode}"))
            if result.stderr:
                out(dim(f"     Error: {result.stderr[:200]}"))
            issues_found = True
    else:
        out(warning("  ⚠️  Skipped (hook file missing)"))

    # Test 4: Check req command accessibility
    out()
    out(info("4. Checking 'req' command..."))
    req_link = Path.home() / '.local' / 'bin' / 'req'

    if req_link.exists():
        out(success("  ✅ 'req' command is accessible"))
    else:
        out(warning("  ⚠️  'req' symlink not found"))
        out(dim("     Run: ./install.sh to create symlink"))

    # Check PATH
    local_bin = str(Path.home() / '.local' / 'bin')
    if local_bin not in os.environ.get('PATH', ''):
        out(warning("  ⚠️  ~/.local/bin not in PATH"))
        out(dim("     Add: export PATH=\"$HOME/.local/bin:$PATH\""))

    # Test 5: Check config exists
    out()
    out(info("5. Checking configuration..."))
    global_config = Path.home() / '.claude' / 'requirements.yaml'

    if global_config.exists():
        out(success("  ✅ Global config exists"))
    else:
        out(warning("  ⚠️  No global config"))
        out(dim("     Run: ./install.sh to install default config"))

    # Summary
    out()
    out("=" * 50)
    if issues_found:
        out(error("❌ Verification failed - issues found"))
        out()
        out(hint("💡 Run './install.sh' to fix installation issues"))
        return 1
    else:
        out(success("✅ Framework fully functional!"))
        out()
        out(hint("💡 Next: Run 'req init' in your project to set up requirements"))
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
    """Check if PyYAML is installed."""
    try:
        import yaml  # noqa: F401 - imported only to check availability
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
            'status': 'fail',
            'severity': 'critical',
            'message': 'PyYAML not installed (required for config parsing)',
            'fix': {
                'description': 'Install PyYAML: pip install pyyaml',
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
                'message': f'{hook_type} hook: settings.json not found',
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
                'description': 'Fix settings.json syntax or run ./install.sh',
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
    settings_path, _ = _load_settings_file(claude_dir)
    settings_file = settings_path or (claude_dir / "settings.json")

    # Run all checks
    all_checks = []

    # Environment checks
    all_checks.append(_check_python_version())
    all_checks.append(_check_pyyaml_available())

    # Hook file checks
    all_checks.extend(_check_all_hook_files(hooks_dir))

    # Hook registration checks (skip in CI mode - settings files won't exist)
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
                        'description': 'Copy deployed changes into the repo, then deploy',
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
        out(json.dumps(result, indent=2))
        return 1 if critical_issues else 0

    # Default/Verbose output mode
    out(header("🩺 Requirements Framework Health Check"))
    out()

    # Show issues if any
    if critical_issues:
        out(error("❌ CRITICAL Issues:"))
        out()
        for check in critical_issues:
            out(f"  ❌ {check['message']}")
            if check['fix']:
                out(dim(f"     Fix: {check['fix']['description']}"))
            out()

    if warnings:
        out(error("⚠️  Warnings:"))
        out()
        for check in warnings:
            out(f"  ⚠️  {check['message']}")
            if check['fix']:
                out(dim(f"     Fix: {check['fix']['description']}"))
            out()

    # Summary
    if not critical_issues and not warnings:
        out(success("✅ All checks passed!"))
        out()
        out(f"  {passed}/{total} checks completed successfully")
    else:
        out(f"  Status: {passed}/{total} checks passed")
        if critical_issues:
            out(f"  Critical issues: {len(critical_issues)}")
        if warnings:
            out(f"  Warnings: {len(warnings)}")
        out()

    # Verbose mode: show all checks
    if verbose and info_items:
        out(header("ℹ️  All Checks:"))
        out()
        for check in all_checks:
            icon = "✅" if check['status'] == 'pass' else "❌" if check['severity'] == 'critical' else "⚠️"
            out(f"  {icon} {check['message']}")
        out()

    # Hints
    if not verbose and (critical_issues or warnings):
        out(hint("💡 Use 'req doctor --verbose' for full diagnostics"))
        out(hint("💡 Use 'req doctor --json' for machine-readable output"))

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
        out(info("ℹ️  No active Claude Code sessions found."))
        return 0

    # Display sessions
    out(header(f"📋 Active Claude Code Sessions ({len(sessions)})"))
    out(dim(f"{'─' * 60}"))

    for sess in sessions:
        age_mins = int((time.time() - sess['last_active']) // 60)
        age_str = f"{age_mins}m ago" if age_mins > 0 else "just now"

        out(f"  {bold(sess['id'])} - {dim(sess['project_dir'])}")
        out(dim(f"             {sess['branch']} [PID {sess['pid']}, {age_str}]"))

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
        out(error("❌ Not in a git repository"), file=sys.stderr)
        out(dim("   Requirements framework only works in git repositories"))
        return 1

    # Check if project has any config
    config_file = Path(project_dir) / '.claude' / 'requirements.yaml'

    if not config_file.exists():
        out(info("ℹ️  No requirements configured for this project."), file=sys.stderr)
        out(dim("   Create .claude/requirements.yaml to configure requirements."))
        out(dim("   See: ~/.claude/requirements.yaml for examples"))
        return 1

    config = RequirementsConfig(project_dir)

    # Phase 1: Framework-level enable/disable only
    requirement_name = args.requirement if hasattr(args, 'requirement') and args.requirement else None

    if requirement_name:
        # Phase 2: Requirement-level enable (future enhancement)
        out(error("❌ Requirement-level enable/disable not yet implemented"), file=sys.stderr)
        out(dim("   Use: req enable  (without requirement name)"))
        return 1

    # Enable framework
    try:
        file_path = config.write_local_override(enabled=True)
        out(success("✅ Requirements framework enabled for this project"))
        out(dim(f"   Modified: {file_path}"))
        out()
        out(hint("💡 Run 'req status' to see current requirements"))
        return 0
    except Exception as e:
        out(error(f"❌ Failed to enable framework: {e}"), file=sys.stderr)
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
        out(error("❌ Not in a git repository"), file=sys.stderr)
        out(dim("   Requirements framework only works in git repositories"))
        return 1

    config = RequirementsConfig(project_dir)

    # Phase 1: Framework-level enable/disable only
    requirement_name = args.requirement if hasattr(args, 'requirement') and args.requirement else None

    if requirement_name:
        # Phase 2: Requirement-level disable (future enhancement)
        out(error("❌ Requirement-level enable/disable not yet implemented"), file=sys.stderr)
        out(dim("   Use: req disable  (without requirement name)"))
        return 1

    # Disable framework
    try:
        file_path = config.write_local_override(enabled=False)
        out(success("✅ Requirements framework disabled for this project"))
        out(dim(f"   Modified: {file_path}"))
        out()
        out(hint("💡 This only affects your local environment (file is gitignored)"))
        out(hint("💡 To re-enable: req enable"))
        return 0
    except Exception as e:
        out(error(f"❌ Failed to disable framework: {e}"), file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


def cmd_logging(args) -> int:
    """
    View or modify logging configuration.

    Args:
        args: Parsed arguments

    Returns:
        Exit code
    """
    project_dir = get_project_dir()

    # Check if git repo
    if not is_git_repo(project_dir):
        out(error("❌ Not in a git repository"), file=sys.stderr)
        return 1

    # Load config
    config = RequirementsConfig(project_dir)

    # Check if any write flags present
    has_write_flags = (
        args.level is not None or
        args.destinations is not None or
        args.file is not None
    )

    # Read-only mode: show current logging config
    if not has_write_flags:
        out(header("🪵 Logging Configuration"))
        out(dim("─" * 50))
        out()

        logging_config = config.get_logging_config()

        # Show current settings
        level = logging_config.get('level', 'error')
        destinations = logging_config.get('destinations', ['file'])
        log_file = logging_config.get('file', str(Path.home() / '.claude' / 'requirements.log'))

        if not isinstance(destinations, list):
            destinations = [destinations]

        out(f"{bold('Level')}: {level}")
        out(f"{bold('Destinations')}: {', '.join(destinations)}")
        out(f"{bold('File')}: {log_file}")
        out()

        # Show available levels
        out(dim("Available levels: debug, info, warning, error"))
        out(dim("Available destinations: file, stdout"))
        out()

        # Usage hint
        out(hint("💡 To change settings:"))
        out(dim("   req logging --level debug --local"))
        out(dim("   req logging --destinations file stdout --local"))
        out(dim("   req logging --file /custom/path/app.log --local"))

        return 0

    # Write mode: modify logging configuration
    try:
        from interactive import select, confirm
    except ImportError:
        # Fallback if interactive module missing
        out(error("❌ Interactive prompts not available"), file=sys.stderr)
        out(dim("   Use --local or --project flag to specify target"), file=sys.stderr)
        return 1

    # Ask which config to modify (unless explicitly specified)
    if not args.project and not args.local and not args.yes:
        try:
            choice = select(
                "Which configuration file to modify?",
                [
                    "Local (.claude/requirements.local.yaml) - personal, gitignored",
                    "Project (.claude/requirements.yaml) - team-shared, versioned",
                ],
            )
            modify_local = choice == 0
        except (EOFError, KeyboardInterrupt):
            out(warning("\n⚠️  Cancelled"), file=sys.stderr)
            return 1
        except Exception as e:
            out(error(f"❌ Interactive prompt failed: {e}"), file=sys.stderr)
            out(dim("   Use --local or --project flag to specify target"), file=sys.stderr)
            return 1
    else:
        modify_local = not args.project

    # Build logging config dict
    logging_config_update = {}

    if args.level:
        # Validate level
        valid_levels = ['debug', 'info', 'warning', 'error']
        if args.level.lower() not in valid_levels:
            out(error(f"❌ Invalid log level: {args.level}"), file=sys.stderr)
            out(dim(f"   Valid levels: {', '.join(valid_levels)}"), file=sys.stderr)
            return 1
        logging_config_update['level'] = args.level.lower()

    if args.destinations:
        # Validate destinations
        valid_destinations = ['file', 'stdout']
        destinations = [d.lower().strip() for d in args.destinations]

        # Check for empty
        if not destinations or all(d == '' for d in destinations):
            out(error("❌ No destinations specified"), file=sys.stderr)
            out(dim(f"   Valid destinations: {', '.join(valid_destinations)}"), file=sys.stderr)
            return 1

        # Remove duplicates (preserve order)
        seen = set()
        unique_destinations = []
        for dest in destinations:
            if dest not in seen:
                seen.add(dest)
                unique_destinations.append(dest)

        # Warn if duplicates were removed
        if len(unique_destinations) < len(destinations):
            out(warning("⚠️  Removed duplicate destinations"), file=sys.stderr)

        # Validate each destination
        for dest in unique_destinations:
            if dest not in valid_destinations:
                out(error(f"❌ Invalid destination: {dest}"), file=sys.stderr)
                out(dim(f"   Valid destinations: {', '.join(valid_destinations)}"), file=sys.stderr)
                return 1

        logging_config_update['destinations'] = unique_destinations

    if args.file:
        # Validate the file path is writable
        log_path = Path(args.file)

        # Expand user home directory
        if str(log_path).startswith('~'):
            log_path = log_path.expanduser()

        # Check parent directory exists or can be created
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
        except (PermissionError, OSError) as e:
            out(error(f"❌ Cannot create log directory: {log_path.parent}"), file=sys.stderr)
            out(dim(f"   {e}"), file=sys.stderr)
            return 1

        # Test write permission by attempting to touch the file
        try:
            log_path.touch(exist_ok=True)
        except (PermissionError, OSError) as e:
            out(error(f"❌ Cannot write to log file: {log_path}"), file=sys.stderr)
            out(dim(f"   {e}"), file=sys.stderr)
            return 1

        logging_config_update['file'] = str(log_path.absolute())
        out(dim(f"   Log file will be: {log_path.absolute()}"))

    # Show preview
    out()
    out(header("📝 Preview"))
    out(dim("─" * 50))
    for key, value in logging_config_update.items():
        if isinstance(value, list):
            out(f"{bold(key)}: {', '.join(value)}")
        else:
            out(f"{bold(key)}: {value}")
    out()

    # Confirm unless --yes
    if not args.yes:
        target = "local config (.gitignored)" if modify_local else "project config (version-controlled)"
        try:
            if not confirm(f"Update {target}?"):
                out(warning("⚠️  Aborted"))
                return 1
        except (EOFError, KeyboardInterrupt):
            out(warning("\n⚠️  Cancelled"), file=sys.stderr)
            return 1

    # Write config
    try:
        if modify_local:
            file_path = config.write_local_override(logging_config=logging_config_update)
        else:
            file_path = config.write_project_override(logging_config=logging_config_update)

        out(success("✅ Logging configuration updated"))
        out(dim(f"   Modified: {file_path}"))
        out()

        # Show what changed
        for key, value in logging_config_update.items():
            if isinstance(value, list):
                out(f"   {bold(key)}: {', '.join(value)}")
            else:
                out(f"   {bold(key)}: {value}")

        out()
        out(hint("💡 Logging changes take effect on next hook execution"))

        if 'level' in logging_config_update and logging_config_update['level'] == 'debug':
            out(hint("💡 View debug logs: tail -f ~/.claude/requirements.log"))

        return 0

    except ImportError:
        out(error("❌ PyYAML is required to write config files"), file=sys.stderr)
        out(dim("   Install with: pip install pyyaml"), file=sys.stderr)
        from logger import get_logger
        get_logger().error("PyYAML import failed", exc_info=True)
        return 1

    except PermissionError as e:
        out(error("❌ Permission denied writing config file"), file=sys.stderr)
        out(dim(f"   Check file permissions: {e.filename}"), file=sys.stderr)
        from logger import get_logger
        get_logger().error("Config write permission denied", path=e.filename, exc_info=True)
        return 1

    except OSError as e:
        # Disk full, read-only filesystem, etc.
        out(error(f"❌ Failed to write config file: {e.strerror}"), file=sys.stderr)
        if e.filename:
            out(dim(f"   File: {e.filename}"), file=sys.stderr)
        from logger import get_logger
        get_logger().error("Config write I/O error", path=e.filename, error=e.strerror, exc_info=True)
        return 1

    except ValueError as e:
        # Validation errors from config
        out(error(f"❌ Invalid configuration: {e}"), file=sys.stderr)
        from logger import get_logger
        get_logger().error("Config validation failed", exc_info=True)
        return 1

    except Exception as e:
        # Truly unexpected errors - log with full context
        out(error(f"❌ Unexpected error updating config: {e}"), file=sys.stderr)
        out(dim("   This may be a bug. Please report with logs."), file=sys.stderr)
        from logger import get_logger
        get_logger().error(
            "Unexpected error in cmd_logging",
            logging_config=str(logging_config_update),
            modify_local=modify_local,
            exc_info=True,
        )
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
        out(error("❌ Not in a git repository"), file=sys.stderr)
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
        out(error("❌ Requirement name required when using write flags"), file=sys.stderr)
        out(dim("   Usage: req config <requirement> --enable|--disable|--scope|..."), file=sys.stderr)
        return 1

    # Check for "show" mode (display full merged config)
    if not requirement_name or requirement_name == 'show':
        return _cmd_config_show(config, args)

    # Check if requirement exists (unless we're trying to enable a new one)
    req_config = config.get_requirement(requirement_name)
    if not req_config and not has_write_flags:
        out(error(f"❌ Requirement '{requirement_name}' not found"), file=sys.stderr)
        available = config.get_all_requirements()
        if available:
            out(dim(f"   Available: {', '.join(available)}"))
        return 1

    # Read-only mode: show current config
    if not has_write_flags:
        out(header(f"📋 Configuration: {requirement_name}"))
        out(dim("─" * 50))

        # Show all fields with nice formatting
        for key, value in req_config.items():
            if key == 'message':
                # Show truncated message
                if len(str(value)) > 100:
                    lines = str(value).split('\n')
                    out(f"{bold(key)}: {lines[0][:80]}...")
                else:
                    out(f"{bold(key)}: {value}")
            elif isinstance(value, list):
                out(f"{bold(key)}:")
                for item in value:
                    out(f"  - {item}")
            elif isinstance(value, dict):
                out(f"{bold(key)}:")
                for k, v in value.items():
                    out(f"  {k}: {v}")
            else:
                out(f"{bold(key)}: {value}")

        # Show if it's enabled
        out()
        is_enabled = config.is_requirement_enabled(requirement_name)
        if is_enabled:
            out(success("✅ Currently enabled"))
        else:
            out(dim("⚠️  Currently disabled"))

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
                out(error(f"❌ Invalid --set format: {item}"), file=sys.stderr)
                out(dim("   Use: --set KEY=VALUE"), file=sys.stderr)
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
    out()
    out(header(f"Preview changes to {requirement_name}:"))
    out(dim("─" * 50))

    for key, new_value in updates.items():
        old_value = req_config.get(key, "(not set)") if req_config else "(not set)"
        # Truncate long values
        if isinstance(old_value, str) and len(old_value) > 60:
            old_value = old_value[:60] + "..."
        if isinstance(new_value, str) and len(new_value) > 60:
            new_value = new_value[:60] + "..."

        out(f"  {bold(key)}:")
        out(f"    {dim('Before:')} {old_value}")
        out(f"    {success('After:')} {new_value}")

    out()
    target_file = "requirements.local.yaml" if modify_local else "requirements.yaml"
    out(dim(f"Target: .claude/{target_file}"))
    out()

    # Confirm
    if not args.yes:
        if not confirm("Apply these changes?", default=True):
            out(info("ℹ️  Cancelled"))
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
                out(error(f"❌ {e}"), file=sys.stderr)
                return 1

        out(success(f"✅ Updated {requirement_name}"))
        out(dim(f"   Modified: {file_path}"))
        return 0

    except Exception as e:
        out(error(f"❌ Failed to update config: {e}"), file=sys.stderr)
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
        out(header("📋 Requirements Framework Configuration"))
        out(dim("─" * 60))
        out(dim("Merged from: global → project → local"))
        out()

        # Output JSON
        output = json.dumps(merged_config, indent=2, sort_keys=False)
        out(output)

    except TypeError as e:
        out(error(f"❌ Config contains non-serializable value: {e}"), file=sys.stderr)
        out(dim("   Check your config files for invalid types"), file=sys.stderr)
        return 1
    except Exception as e:
        out(error(f"❌ Failed to load config: {e}"), file=sys.stderr)
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
                sources[name] = load_yaml(path)
            except (OSError, IOError) as e:
                out(warning(f"⚠️  Failed to read {name} config: {path}"), file=sys.stderr)
                out(dim(f"   Error: {e}"), file=sys.stderr)
                sources[name] = {}
            except (json.JSONDecodeError, ValueError) as e:
                out(warning(f"⚠️  Failed to parse {name} config: {path}"), file=sys.stderr)
                out(dim(f"   Error: {e}"), file=sys.stderr)
                sources[name] = {}
            except Exception as e:
                out(warning(f"⚠️  Unexpected error loading {name} config: {path}"), file=sys.stderr)
                out(dim(f"   Error: {type(e).__name__}: {e}"), file=sys.stderr)
                sources[name] = {}
        else:
            sources[name] = {}

    # Display each level
    out(header("📋 Configuration Sources"))
    out(dim("─" * 60))

    for level in ['global', 'project', 'local']:
        config_data = sources[level]
        file_path = _get_config_path(level, project_dir)

        out()
        out(bold(f"{level.upper()} ({file_path}):"))
        if config_data:
            try:
                out(json.dumps(config_data, indent=2))
            except TypeError as e:
                out(error(f"❌ Non-serializable value in {level} config: {e}"), file=sys.stderr)
                out(dim("  (skipped)"))
        else:
            out(dim("  (not present)"))

    # Show merged result
    out()
    out(header("MERGED RESULT:"))
    out(dim("─" * 60))
    try:
        merged = config.get_raw_config()
        out(json.dumps(merged, indent=2))
    except TypeError as e:
        out(error(f"❌ Merged config contains non-serializable value: {e}"), file=sys.stderr)
        out(dim("   Check your config files for invalid types"), file=sys.stderr)
        return 1
    except Exception as e:
        out(error(f"❌ Failed to load merged config: {e}"), file=sys.stderr)
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
        out(warning("⚠️  Path resolution failed, defaulting to project context"), file=sys.stderr)
        out(dim(f"   Error: {e}"), file=sys.stderr)

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
        out(error("❌ Not in a git repository"), file=sys.stderr)
        out(dim("   Requirements framework only works in git repositories"))
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
    elif context == 'local':
        target_file = local_config
    else:  # project
        target_file = project_config

    # Interactive mode (default) vs non-interactive (--yes)
    if not args.yes and not args.preview:
        # Show context-specific header
        if context == 'global':
            out(header("🌍 Global Requirements Framework Setup"))
            out(dim("   Setting up defaults for all your projects"))
        elif context == 'local':
            out(header("📝 Local Requirements Override Setup"))
            out(dim("   Creating personal overrides (gitignored)"))
        else:  # project
            out(header("🚀 Project Requirements Setup"))
            if global_config.exists():
                out(dim("   Configuring project-specific requirements"))
            else:
                out(dim("   Setting up project requirements"))
        out(dim("─" * 50))
        out()

        # Context-specific detection info
        out(info("Detecting environment:"))
        out(success(f"  ✓ Git repository at {project_dir}"))

        if context == 'global':
            if global_config.exists():
                out(warning("  ⚠ Global config exists"))
        else:
            if claude_dir.exists():
                out(success("  ✓ .claude/ directory exists"))
            else:
                out(dim("  ○ .claude/ directory will be created"))

            if context == 'project' and global_config.exists():
                out(success("  ✓ Global config found"))
                out(dim("     Project will inherit from global defaults"))

            if project_config.exists():
                out(warning("  ⚠ Project config exists"))
            if local_config.exists() and context == 'local':
                out(warning("  ⚠ Local config exists"))

        if context == 'project' and not global_config.exists():
            out(warning("  ⚠ No global config found"))
            out(dim("     Tip: Run 'req init' to create global defaults first"))

        out()

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

        out()
        out(header("Preview:"))
        out(dim("─" * 50))
        # Show first 20 lines of config
        lines = yaml_content.split('\n')[:20]
        for line in lines:
            out(line)
        if len(yaml_content.split('\n')) > 20:
            out(dim("  ... (truncated)"))
        out(dim("─" * 50))
        out()

        # Confirm
        if target_file.exists() and not args.force:
            if not confirm(f"Overwrite existing {target_file.name}?", default=False):
                out(info("ℹ️  Cancelled"))
                return 0
        else:
            if not confirm(f"Create {target_file.name}?", default=True):
                out(info("ℹ️  Cancelled"))
                return 0
    else:
        # Non-interactive mode
        preset = args.preset or 'relaxed'
        config = generate_config(preset, context=context)
        yaml_content = config_to_yaml(config)

        # Preview mode (non-interactive)
        if args.preview:
            context_name = context.capitalize()
            out(header(f"📋 Preview: {context_name} config ({preset} preset)"))
            out(dim("─" * 50))
            out(yaml_content)
            out(dim("─" * 50))
            out(info(f"ℹ️  Would create: {target_file}"))
            return 0

        # Check for existing config (non-interactive mode only)
        if target_file.exists() and not args.force:
            out(warning(f"⚠️  Config already exists: {target_file}"))
            out(hint("💡 Use --force to overwrite"))
            return 0

    # Create parent directory if needed
    target_file.parent.mkdir(parents=True, exist_ok=True)

    # Write config
    try:
        target_file.write_text(yaml_content)
        context_name = context.capitalize() if context != 'project' else 'project'
        out(success(f"✅ Created {context_name} config ({preset} preset)"))
        out(dim(f"   {target_file}"))
        out()
        out(hint("💡 Next steps:"))
        out(dim("   • Run 'req status' to see your requirements"))
        out(dim("   • Make changes - you'll be prompted to satisfy requirements"))
        out(dim(f"   • Edit {target_file.name} to customize"))
        return 0
    except Exception as e:
        out(error(f"❌ Failed to create config: {e}"), file=sys.stderr)
        return 1


def cmd_learning(args) -> int:
    """
    Manage session learning system.

    Subcommands:
        list     - Show recent learning updates
        stats    - Show learning statistics
        rollback - Rollback a specific update
        disable  - Disable learning for this project

    Args:
        args: Parsed arguments

    Returns:
        Exit code
    """
    project_dir = get_project_dir()

    if not is_git_repo(project_dir):
        out(error("❌ Not in a git repository"), file=sys.stderr)
        return 1

    subcommand = args.learning_command or 'stats'

    if subcommand == 'list':
        return _cmd_learning_list(project_dir, args)
    elif subcommand == 'stats':
        return _cmd_learning_stats(project_dir)
    elif subcommand == 'rollback':
        return _cmd_learning_rollback(project_dir, args)
    elif subcommand == 'disable':
        return _cmd_learning_disable(project_dir)
    else:
        out(error(f"❌ Unknown subcommand: {subcommand}"), file=sys.stderr)
        return 1


def _cmd_learning_list(project_dir: str, args) -> int:
    """List recent learning updates."""
    count = getattr(args, 'count', 10)
    updates = get_recent_updates(project_dir, count=count)

    if not updates:
        out(info("No learning updates recorded yet."))
        out(dim("Run /session-reflect to analyze a session and create updates."))
        return 0

    out(header("📚 Recent Learning Updates"))
    out()

    for update in updates:
        update_id = update.get('id', '?')
        timestamp = update.get('datetime', 'unknown')
        update_type = update.get('type', 'unknown')
        target = update.get('target', 'unknown')
        action = update.get('action', 'unknown')
        rolled_back = update.get('rolled_back', False)

        status = dim("[rolled back]") if rolled_back else ""
        out(f"  {bold(f'#{update_id}')} {timestamp} {status}")
        out(f"      Type: {update_type}")
        out(f"      Target: {target}")
        out(f"      Action: {action}")

        metadata = update.get('metadata', {})
        if metadata.get('confidence'):
            out(f"      Confidence: {metadata['confidence']:.0%}")
        out()

    out(hint("Use 'req learning rollback <id>' to undo an update"))
    return 0


def _cmd_learning_stats(project_dir: str) -> int:
    """Show learning statistics."""
    stats = get_learning_stats(project_dir)

    out(header("📊 Learning Statistics"))
    out()

    total = stats.get('total_updates', 0)
    if total == 0:
        out(info("No learning updates recorded yet."))
        out(dim("Run /session-reflect to start learning from your sessions."))
        return 0

    out(f"  Total Updates:     {bold(str(total))}")
    out(f"  Memories Updated:  {stats.get('memories_updated', 0)}")
    out(f"  Skills Updated:    {stats.get('skills_updated', 0)}")
    out(f"  Commands Updated:  {stats.get('commands_updated', 0)}")
    out(f"  Rollbacks:         {stats.get('rollbacks', 0)}")
    out()

    # Show session metrics summary
    sessions = list_session_metrics(project_dir, max_age_days=7)
    if sessions:
        out(header("📈 Recent Sessions (last 7 days)"))
        out()
        for sess in sessions[:5]:
            sess_id = sess.get('session_id', 'unknown')
            branch = sess.get('branch', 'unknown')
            tool_count = sess.get('tool_count', 0)
            out(f"  {sess_id} on {branch}: {tool_count} tool uses")
        if len(sessions) > 5:
            out(dim(f"  ... and {len(sessions) - 5} more"))
    else:
        out(dim("No session metrics available."))

    return 0


def _cmd_learning_rollback(project_dir: str, args) -> int:
    """Rollback a specific update."""
    update_id = getattr(args, 'update_id', None)

    if update_id is None:
        out(error("❌ Please specify an update ID to rollback"), file=sys.stderr)
        out(hint("Use 'req learning list' to see available updates"))
        return 1

    try:
        update_id = int(update_id)
    except ValueError:
        out(error(f"❌ Invalid update ID: {update_id}"), file=sys.stderr)
        return 1

    # Get the update first
    update = get_update_by_id(project_dir, update_id)
    if not update:
        out(error(f"❌ Update #{update_id} not found"), file=sys.stderr)
        return 1

    if update.get('rolled_back'):
        out(warning(f"⚠️  Update #{update_id} was already rolled back"))
        return 0

    if not update.get('rollback_available'):
        out(error(f"❌ Rollback not available for update #{update_id}"), file=sys.stderr)
        out(dim("This update was a create action without previous content."))
        out(hint("You can manually delete the file or use git to restore."))
        return 1

    # Mark as rolled back
    if mark_rolled_back(project_dir, update_id):
        out(success(f"✅ Marked update #{update_id} as rolled back"))
        out()
        out(warning("⚠️  Note: The file content was not automatically restored."))
        out(hint("Use git to restore the file, or manually edit it:"))
        out(dim(f"   git checkout -- {update.get('target', 'unknown')}"))
        return 0
    else:
        out(error(f"❌ Failed to rollback update #{update_id}"), file=sys.stderr)
        return 1


def _cmd_learning_disable(project_dir: str) -> int:
    """Disable learning for this project."""
    config_path = Path(project_dir) / '.claude' / 'requirements.local.yaml'

    try:
        # Load existing config or create new
        if config_path.exists():
            with open(config_path) as f:
                config_data = load_yaml(f)
        else:
            config_data = {}

        # Disable session learning
        if 'hooks' not in config_data:
            config_data['hooks'] = {}
        if 'session_learning' not in config_data['hooks']:
            config_data['hooks']['session_learning'] = {}

        config_data['hooks']['session_learning']['enabled'] = False

        # Write config
        config_path.parent.mkdir(parents=True, exist_ok=True)
        import yaml
        with open(config_path, 'w') as f:
            yaml.safe_dump(config_data, f, default_flow_style=False, sort_keys=False)

        out(success("✅ Session learning disabled for this project"))
        out(dim(f"   Config: {config_path}"))
        out()
        out(hint("To re-enable: remove 'session_learning.enabled: false' from config"))
        return 0

    except Exception as e:
        out(error(f"❌ Failed to disable learning: {e}"), file=sys.stderr)
        return 1


# ============================================================================
# UPGRADE COMMAND
# ============================================================================

def cmd_upgrade(args) -> int:
    """
    Manage cross-project feature upgrades.

    Subcommands:
        scan      - Scan machine for projects using the framework
        status    - Show feature status for a project
        recommend - Generate YAML recommendations for missing features

    Args:
        args: Parsed arguments

    Returns:
        Exit code
    """
    subcommand = args.upgrade_command or 'status'

    if subcommand == 'scan':
        return _cmd_upgrade_scan(args)
    elif subcommand == 'status':
        return _cmd_upgrade_status(args)
    elif subcommand == 'recommend':
        return _cmd_upgrade_recommend(args)
    elif subcommand == 'apply':
        return _cmd_upgrade_apply(args)
    else:
        out(error(f"❌ Unknown subcommand: {subcommand}"), file=sys.stderr)
        return 1


def _cmd_upgrade_scan(args) -> int:
    """Scan machine for projects using the requirements framework."""
    from project_registry import ProjectRegistry

    registry = ProjectRegistry()

    # Parse custom scan paths if provided
    scan_paths = None
    if hasattr(args, 'paths') and args.paths:
        scan_paths = [Path(p) for p in args.paths]

    out(header("🔍 Scanning for projects..."))
    out()

    result = registry.update_and_scan(scan_paths)

    out(success(f"✅ Scan complete"))
    out()
    out(f"   New projects:     {result['new']}")
    out(f"   Updated:          {result['updated']}")
    out(f"   Removed (stale):  {result['removed']}")
    out(f"   Total tracked:    {result['total']}")
    out()

    if result['total'] > 0:
        out(hint("Run 'req upgrade --all' to see feature status across all projects"))
    else:
        out(info("No projects found with .claude/requirements.yaml"))
        out(hint("Run 'req init' in a project to get started"))

    return 0


def _cmd_upgrade_status(args) -> int:
    """Show feature status for a project or all projects."""
    from feature_catalog import (
        get_all_features,
        detect_configured_features,
        CATEGORY_REQUIREMENTS,
        CATEGORY_HOOKS,
        CATEGORY_GUARDS,
    )
    from project_registry import ProjectRegistry

    registry = ProjectRegistry()

    # Determine which project(s) to show
    if hasattr(args, 'all') and args.all:
        # Show all tracked projects
        projects = registry.list_projects()
        if not projects:
            out(info("No projects tracked. Run 'req upgrade scan' first."))
            return 0

        out(header("📊 Feature Status: All Projects"))
        out()

        for project in projects:
            _show_project_status(project['path'], brief=True)
            out()

        out(hint("Run 'req upgrade status <path>' for detailed view of a specific project"))
        return 0

    # Single project
    if hasattr(args, 'path') and args.path:
        project_path = args.path
    else:
        project_path = get_project_dir()

    if not is_git_repo(project_path):
        out(error("❌ Not in a git repository"), file=sys.stderr)
        return 1

    # Check if config exists
    config_path = Path(project_path) / ".claude" / "requirements.yaml"
    if not config_path.exists():
        out(warning(f"⚠️  No requirements config found at {config_path}"))
        out(hint("Run 'req init' to create one"))
        return 1

    return _show_project_status(project_path, brief=False)


def _show_project_status(project_path: str, brief: bool = False) -> int:
    """Show feature status for a single project."""
    from feature_catalog import (
        get_all_features,
        detect_configured_features,
        CATEGORY_REQUIREMENTS,
        CATEGORY_HOOKS,
        CATEGORY_GUARDS,
    )

    try:
        config = RequirementsConfig(project_dir=project_path)
        raw_config = config.get_raw_config()
    except Exception as e:
        out(error(f"❌ Failed to load config: {e}"), file=sys.stderr)
        return 1

    configured = detect_configured_features(raw_config)
    features = get_all_features()

    # Group by category
    categories = {
        CATEGORY_REQUIREMENTS: [],
        CATEGORY_GUARDS: [],
        CATEGORY_HOOKS: [],
    }

    for name, info in features.items():
        cat = info.get('category', CATEGORY_REQUIREMENTS)
        status = configured.get(name, False)
        categories[cat].append((name, info, status))

    if brief:
        # One-line summary
        enabled = sum(1 for s in configured.values() if s)
        total = len(configured)
        path_display = project_path
        if len(path_display) > 50:
            path_display = "..." + path_display[-47:]
        out(f"  {path_display}")
        out(dim(f"     {enabled}/{total} features enabled"))
        return 0

    # Full status display
    out(header(f"Feature Status: {project_path}"))
    out(dim("─" * 60))

    # Category display order
    category_order = [
        (CATEGORY_REQUIREMENTS, "Requirements"),
        (CATEGORY_GUARDS, "Guards"),
        (CATEGORY_HOOKS, "Hooks"),
    ]

    missing_count = 0
    for cat_key, cat_label in category_order:
        items = categories.get(cat_key, [])
        if not items:
            continue

        out()
        out(bold(f"  {cat_label}:"))

        for name, info, enabled in sorted(items, key=lambda x: x[0]):
            if enabled:
                status_str = success("✓ Enabled")
            else:
                status_str = dim("○ Not configured")
                missing_count += 1

            introduced = info.get('introduced', '1.0')
            name_display = f"{name:<25}"
            out(f"    {name_display} {status_str}")
            if not enabled and not brief:
                out(dim(f"      └─ {info.get('description', '')}"))

    out()
    out(dim("─" * 60))

    enabled_count = sum(1 for s in configured.values() if s)
    total_count = len(configured)
    out(f"  Enabled: {enabled_count}/{total_count} features")

    if missing_count > 0:
        out()
        out(hint(f"Run 'req upgrade recommend' to see integration snippets for {missing_count} unconfigured features"))

    return 0


def _cmd_upgrade_recommend(args) -> int:
    """Generate YAML recommendations for missing features."""
    from feature_catalog import (
        get_all_features,
        detect_configured_features,
        get_missing_features,
        get_feature_yaml,
        get_feature_info,
    )

    # Determine project
    if hasattr(args, 'path') and args.path:
        project_path = args.path
    else:
        project_path = get_project_dir()

    if not is_git_repo(project_path):
        out(error("❌ Not in a git repository"), file=sys.stderr)
        return 1

    # Check if config exists
    config_path = Path(project_path) / ".claude" / "requirements.yaml"
    if not config_path.exists():
        out(warning(f"⚠️  No requirements config found at {config_path}"))
        out(hint("Run 'req init' to create one"))
        return 1

    try:
        config = RequirementsConfig(project_dir=project_path)
        raw_config = config.get_raw_config()
    except Exception as e:
        out(error(f"❌ Failed to load config: {e}"), file=sys.stderr)
        return 1

    # Get missing features
    missing = get_missing_features(raw_config)

    # Filter to specific feature if requested
    if hasattr(args, 'feature') and args.feature:
        if args.feature not in missing:
            if args.feature in get_all_features():
                out(success(f"✓ '{args.feature}' is already configured"))
            else:
                out(error(f"❌ Unknown feature: {args.feature}"), file=sys.stderr)
            return 0
        missing = [args.feature]

    if not missing:
        out(success("✅ All available features are configured!"))
        return 0

    out(header(f"Recommendations for: {project_path}"))
    out(dim("─" * 60))
    out()

    for feature_name in sorted(missing):
        info = get_feature_info(feature_name)
        if not info:
            continue

        yaml_snippet = get_feature_yaml(feature_name)
        if not yaml_snippet:
            continue

        introduced = info.get('introduced', '1.0')
        version_note = f" (New in v{introduced})" if introduced != "1.0" else ""

        out(bold(f"### {info.get('name', feature_name)}{version_note}"))
        out(dim(info.get('description', '')))
        out()
        out(f"Add to {config_path.name}:")
        out(dim("```yaml"))
        for line in yaml_snippet.strip().split('\n'):
            out(line)
        out(dim("```"))
        out()
        out(dim("─" * 60))
        out()

    out(hint("Copy the YAML snippets above to your config file"))
    out(hint("Then run 'req upgrade status' to verify"))

    return 0


def _cmd_upgrade_apply(args) -> int:
    """Apply missing features to a config file."""
    import tempfile

    import yaml
    from config_utils import deep_merge
    from feature_catalog import (
        get_all_features,
        get_unconfigured_features,
        get_feature_info,
        get_feature_yaml,
    )
    from interactive import confirm, checkbox

    # Determine project directory once for consistent use
    project_dir = get_project_dir()

    # Determine target file path
    target = getattr(args, 'target', 'global')
    if target == 'global':
        target_path = Path.home() / '.claude' / 'requirements.yaml'
    elif target == 'project':
        target_path = Path(project_dir) / '.claude' / 'requirements.yaml'
    elif target == 'local':
        target_path = Path(project_dir) / '.claude' / 'requirements.local.yaml'
    else:
        out(error(f"Unknown target: {target}"), file=sys.stderr)
        return 1

    if not target_path.exists():
        out(error(f"Target config not found: {target_path}"), file=sys.stderr)
        out(hint("Run 'req init' to create one"))
        return 1

    # Load existing config (cascade-merged for detection, raw target for writing)
    try:
        config = RequirementsConfig(project_dir=project_dir)
        merged_config = config.get_raw_config()
    except Exception as e:
        out(error(f"Failed to load config: {e}"), file=sys.stderr)
        return 1

    # Find truly unconfigured features (absent, not just disabled)
    unconfigured = get_unconfigured_features(merged_config)

    if not unconfigured:
        out(success("All features are already configured!"))
        return 0

    # Filter by specific feature if requested
    specific_feature = getattr(args, 'feature', None)
    if specific_feature:
        if specific_feature not in unconfigured:
            all_features = get_all_features()
            if specific_feature in all_features:
                out(success(f"'{specific_feature}' is already configured"))
                return 0
            else:
                out(error(f"Unknown feature: {specific_feature}"), file=sys.stderr)
                return 1
        selected = [specific_feature]
    elif getattr(args, 'yes', False):
        selected = unconfigured
    else:
        # Interactive selection
        choices = []
        for name in sorted(unconfigured):
            feat_info = get_feature_info(name)
            desc = feat_info.get('description', '') if feat_info else ''
            choices.append(f"{name} - {desc}")

        selected_labels = checkbox(
            "Select features to apply:",
            choices,
            default=choices,  # All selected by default
        )

        if not selected_labels:
            out(info("No features selected"))
            return 0

        # Extract feature names from labels
        selected = [label.split(' - ')[0] for label in selected_labels]

    # Parse and merge each feature's YAML
    features_to_merge = {}
    merged_features = []
    for feature_name in selected:
        yaml_snippet = get_feature_yaml(feature_name)
        if not yaml_snippet:
            out(warning(f"Skipping {feature_name}: no YAML template in catalog"))
            continue
        try:
            parsed = yaml.safe_load(yaml_snippet)
            if isinstance(parsed, dict):
                deep_merge(features_to_merge, parsed)
                merged_features.append(feature_name)
            else:
                out(warning(f"Skipping {feature_name}: YAML template is not a mapping"))
        except yaml.YAMLError as e:
            out(warning(f"Skipping {feature_name}: invalid YAML ({e})"))
            continue

    if not features_to_merge:
        out(warning("No features to apply"))
        return 0

    # Show what will be added
    out(header(f"Features to apply to {target_path.name}:"))
    out()
    for name in merged_features:
        feat_info = get_feature_info(name)
        desc = feat_info.get('description', '') if feat_info else ''
        out(f"  + {bold(name)}: {desc}")
    out()

    dry_run = getattr(args, 'dry_run', False)
    if dry_run:
        out(dim("--- Dry run: YAML to merge ---"))
        out(yaml.safe_dump(features_to_merge, default_flow_style=False, sort_keys=False))
        out(dim("--- End dry run ---"))
        return 0

    # Confirm
    skip_confirm = getattr(args, 'yes', False) or specific_feature
    if not skip_confirm:
        out(warning("PyYAML will strip comments from the target file."))
        if not confirm(f"Apply {len(merged_features)} feature(s) to {target_path.name}?"):
            out(info("Cancelled"))
            return 0

    # Load raw target file (not cascade-merged)
    try:
        with open(target_path, 'r') as f:
            target_config = yaml.safe_load(f) or {}
    except Exception as e:
        out(error(f"Failed to read {target_path}: {e}"), file=sys.stderr)
        return 1

    # Create backup
    backup_path = target_path.with_suffix('.yaml.bak')
    try:
        import shutil
        shutil.copy2(target_path, backup_path)
        out(dim(f"Backup: {backup_path}"))
    except Exception as e:
        out(error(f"Could not create backup: {e}"), file=sys.stderr)
        if not getattr(args, 'yes', False):
            if not confirm("Continue WITHOUT backup?", default=False):
                out(info("Cancelled"))
                return 1
        else:
            out(warning("Proceeding without backup (--yes flag)"))

    # Deep merge and write atomically
    deep_merge(target_config, features_to_merge)

    tmp_path = None
    try:
        fd, tmp_path = tempfile.mkstemp(
            suffix='.yaml',
            dir=str(target_path.parent),
        )
        with os.fdopen(fd, 'w') as f:
            yaml.safe_dump(target_config, f, default_flow_style=False, sort_keys=False)
        os.replace(tmp_path, target_path)
    except Exception as e:
        out(error(f"Failed to write {target_path}: {e}"), file=sys.stderr)
        try:
            if tmp_path:
                os.unlink(tmp_path)
        except OSError:
            pass
        return 1

    out()
    out(success(f"Applied {len(merged_features)} feature(s) to {target_path.name}"))
    out(hint("Run 'req upgrade status' to verify"))

    return 0


def cmd_messages(args) -> int:
    """
    Manage externalized message files.

    Subcommands:
        validate - Validate all message files
        list     - List loaded message files and their sources

    Args:
        args: Parsed arguments

    Returns:
        Exit code
    """
    subcommand = args.messages_command or 'validate'

    if subcommand == 'validate':
        return _cmd_messages_validate(args)
    elif subcommand == 'list':
        return _cmd_messages_list(args)
    else:
        out(error(f"Unknown subcommand: {subcommand}"), file=sys.stderr)
        return 1


def _cmd_messages_validate(args) -> int:
    """Validate all message files for configured requirements."""
    from messages import MessageLoader
    from message_validator import MessageValidator

    project_dir = get_project_dir()

    if not is_git_repo(project_dir):
        out(error("Not in a git repository"), file=sys.stderr)
        return 1

    # Load config to get list of requirements
    try:
        config = RequirementsConfig(project_dir)
    except Exception as e:
        out(error(f"Failed to load config: {e}"), file=sys.stderr)
        return 1

    requirements = list(config.get_all_requirements())

    if not requirements:
        out(info("No requirements configured."))
        out(hint("Run 'req init' to configure requirements."))
        return 0

    out(header("Validating Message Files"))
    out()

    # Use MessageLoader to validate
    loader = MessageLoader(project_dir, strict=True)
    errors = loader.validate_all(requirements)

    # Also run the full validator on all cascade directories
    validator = MessageValidator()
    summary = validator.validate_cascade(project_dir)

    if errors or not summary.is_valid:
        out(error("Validation failed"))
        out()

        if errors:
            out(bold("Requirement message errors:"))
            for err in errors:
                out(f"  - {err}")
            out()

        if not summary.is_valid:
            out(bold("File validation errors:"))
            for result in summary.results:
                if not result.is_valid:
                    out(f"  {result.file_path}:")
                    for err in result.errors:
                        out(f"    - {err}")
            out()

        # Show fix hint
        fix_mode = getattr(args, 'fix', False)
        if fix_mode:
            out(info("Generating missing message files..."))
            _generate_missing_messages(project_dir, config, requirements)
        else:
            out(hint("Run 'req messages validate --fix' to generate missing files"))

        return 1

    out(success(f"All message files valid ({len(requirements)} requirements)"))

    # Show summary of loaded files
    out()
    out(dim("Loaded from:"))
    for req_name in requirements:
        file_path = loader.get_message_file_path(req_name)
        if file_path:
            out(dim(f"  {req_name}: {file_path}"))
        else:
            out(dim(f"  {req_name}: (using template defaults)"))

    return 0


def _generate_missing_messages(project_dir: str, config: RequirementsConfig, requirements: list) -> None:
    """Generate missing message files from templates."""
    from messages import MessageLoader
    from message_validator import generate_message_file

    loader = MessageLoader(project_dir, strict=False)
    global_dir = loader.paths.global_dir

    # Ensure directory exists
    global_dir.mkdir(parents=True, exist_ok=True)

    generated = 0
    for req_name in requirements:
        file_path = global_dir / f"{req_name}.yaml"
        if file_path.exists():
            continue

        # Get requirement config for type info
        req_config = config.get_requirement(req_name)
        if not req_config:
            continue

        req_type = req_config.get('type', 'blocking')
        auto_skill = req_config.get('auto_resolve_skill', '')
        description = req_config.get('description', '')

        # Generate and write the file
        content = generate_message_file(req_name, req_type, auto_skill, description)
        file_path.write_text(content)
        out(success(f"  Generated: {file_path}"))
        generated += 1

    if generated:
        out()
        out(info(f"Generated {generated} message file(s)"))
    else:
        out(info("No files to generate"))


def _cmd_messages_list(args) -> int:
    """List message files and their cascade sources."""
    from messages import MessageLoader

    project_dir = get_project_dir()

    if not is_git_repo(project_dir):
        out(error("Not in a git repository"), file=sys.stderr)
        return 1

    loader = MessageLoader(project_dir, strict=False)

    out(header("Message File Locations"))
    out()

    # Show cascade directories
    out(bold("Cascade directories (priority order):"))
    out(f"  1. Local:   {loader.paths.local_dir}")
    local_exists = loader.paths.local_dir.exists()
    out(dim(f"              {'(exists)' if local_exists else '(not found)'}"))

    out(f"  2. Project: {loader.paths.project_dir}")
    project_exists = loader.paths.project_dir.exists()
    out(dim(f"              {'(exists)' if project_exists else '(not found)'}"))

    out(f"  3. Global:  {loader.paths.global_dir}")
    global_exists = loader.paths.global_dir.exists()
    out(dim(f"              {'(exists)' if global_exists else '(not found)'}"))

    out()

    # List files in each directory
    for name, dir_path in [
        ("Global", loader.paths.global_dir),
        ("Project", loader.paths.project_dir),
        ("Local", loader.paths.local_dir),
    ]:
        if not dir_path.exists():
            continue

        files = list(dir_path.glob("*.yaml"))
        if files:
            out(bold(f"{name} messages ({dir_path}):"))
            for f in sorted(files):
                out(f"  {f.name}")
            out()

    # Show requirement resolution
    try:
        config = RequirementsConfig(project_dir)
        requirements = list(config.get_all_requirements())

        if requirements:
            out(bold("Requirement message resolution:"))
            for req_name in requirements:
                file_path = loader.get_message_file_path(req_name)
                if file_path:
                    # Determine which cascade level
                    if str(file_path).startswith(str(loader.paths.local_dir)):
                        level = "local"
                    elif str(file_path).startswith(str(loader.paths.project_dir)):
                        level = "project"
                    else:
                        level = "global"
                    out(f"  {req_name}: {file_path.name} [{level}]")
                else:
                    out(dim(f"  {req_name}: (template defaults)"))
    except Exception:
        pass

    return 0


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
    req logging                         # Show current logging configuration
    req logging --level debug --local   # Set debug logging (local only)
    req logging --destinations file stdout --local  # Log to file and stdout

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
    status_parser.add_argument('--timing', '-t', action='store_true', help='Show detailed timing breakdown')

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

    # logging
    logging_parser = subparsers.add_parser('logging', help='View or modify logging configuration')
    logging_parser.add_argument('--level', '-l', choices=['debug', 'info', 'warning', 'error'],
                               help='Set log level')
    logging_parser.add_argument('--destinations', '-d', nargs='+', metavar='DEST',
                               help='Set log destinations (file, stdout)')
    logging_parser.add_argument('--file', '-f', metavar='PATH',
                               help='Set custom log file path')
    logging_parser.add_argument('--project', action='store_true', help='Modify project config')
    logging_parser.add_argument('--local', action='store_true', help='Modify local config (default)')
    logging_parser.add_argument('--yes', '-y', action='store_true', help='Skip confirmation')

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

    # learning
    learning_parser = subparsers.add_parser('learning', help='Manage session learning system')
    learning_subparsers = learning_parser.add_subparsers(dest='learning_command', help='Learning subcommand')

    # learning list
    learning_list = learning_subparsers.add_parser('list', help='Show recent learning updates')
    learning_list.add_argument('--count', '-n', type=int, default=10, help='Number of updates to show')

    # learning stats
    learning_subparsers.add_parser('stats', help='Show learning statistics')

    # learning rollback
    learning_rollback = learning_subparsers.add_parser('rollback', help='Rollback a specific update')
    learning_rollback.add_argument('update_id', type=int, help='Update ID to rollback')

    # learning disable
    learning_subparsers.add_parser('disable', help='Disable learning for this project')

    # upgrade
    upgrade_parser = subparsers.add_parser('upgrade', help='Manage cross-project feature upgrades')
    upgrade_subparsers = upgrade_parser.add_subparsers(dest='upgrade_command', help='Upgrade subcommand')

    # upgrade scan
    upgrade_scan = upgrade_subparsers.add_parser('scan', help='Scan machine for projects using the framework')
    upgrade_scan.add_argument('paths', nargs='*', help='Additional paths to scan')

    # upgrade status
    upgrade_status = upgrade_subparsers.add_parser('status', help='Show feature status for a project')
    upgrade_status.add_argument('path', nargs='?', help='Project path (default: current directory)')
    upgrade_status.add_argument('--all', '-a', action='store_true', help='Show all tracked projects')

    # upgrade recommend
    upgrade_recommend = upgrade_subparsers.add_parser('recommend', help='Generate YAML recommendations')
    upgrade_recommend.add_argument('path', nargs='?', help='Project path (default: current directory)')
    upgrade_recommend.add_argument('--feature', '-f', help='Show recommendation for specific feature only')

    # upgrade apply
    upgrade_apply = upgrade_subparsers.add_parser('apply', help='Apply missing features to a config file')
    upgrade_apply.add_argument('--feature', '-f', help='Apply specific feature only')
    upgrade_apply.add_argument('--target', '-t', choices=['global', 'project', 'local'],
                               default='global', help='Target config file (default: global)')
    upgrade_apply.add_argument('--dry-run', action='store_true', help='Show what would be added without writing')
    upgrade_apply.add_argument('--yes', '-y', action='store_true', help='Skip confirmation prompt')

    # messages
    messages_parser = subparsers.add_parser('messages', help='Manage externalized message files')
    messages_subparsers = messages_parser.add_subparsers(dest='messages_command', help='Messages subcommand')

    # messages validate
    messages_validate = messages_subparsers.add_parser('validate', help='Validate all message files')
    messages_validate.add_argument('--fix', action='store_true', help='Generate missing message files')

    # messages list
    messages_subparsers.add_parser('list', help='List message files and their sources')

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
        'logging': cmd_logging,
        'init': cmd_init,
        'config': cmd_config,
        'verify': cmd_verify,
        'doctor': cmd_doctor,
        'learning': cmd_learning,
        'upgrade': cmd_upgrade,
        'messages': cmd_messages,
    }

    return commands[args.command](args)


if __name__ == '__main__':
    sys.exit(main())
