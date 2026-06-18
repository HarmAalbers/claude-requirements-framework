#!/usr/bin/env python3
"""
SessionStart Hook for Requirements Framework.

Triggered when a Claude Code session starts or resumes.
Responsibilities:
1. Clean up stale sessions from registry
2. Update registry with current session
3. Inject requirement status into context (if configured)

Input (stdin JSON):
{
    "session_id": "abc123",
    "hook_event_name": "SessionStart",
    "source": "startup|resume|clear|compact",
    "cwd": "/path/to/project"
}

Output:
- Structured JSON with hookSpecificOutput.additionalContext (injected into Claude's context)
- May include session warnings even if inject_context is disabled
- Empty if no context to inject and no warnings
"""
import json
import os
import sys
from pathlib import Path

# Add lib to path
lib_path = Path(__file__).parent / 'lib'
sys.path.insert(0, str(lib_path))

from config import RequirementsConfig
from config_utils import summarize_triggers, get_requirement_description
from requirements import BranchRequirements
from session import update_registry, cleanup_stale_sessions, normalize_session_id, get_active_sessions
from logger import get_logger
from hook_utils import early_hook_setup
from console import emit_hook_context


# Stand-down directive appended to the SessionStart briefing ONLY when at least
# one gating requirement is unsatisfied (satisfied_count < total_count). It tells
# Claude not to blindly attempt blocked edits, to resolve via the listed skill,
# and that `req satisfy`/`req clear` are USER actions (the permission layer blocks
# Claude from running them). Kept to ~2 lines to respect the compact token budget.
_GATING_DIRECTIVE = (
    "**Gated**: edits/commits are blocked until the above are satisfied — do NOT "
    "attempt Edit/Write/MultiEdit first. To satisfy, run the listed resolution skill "
    "(you may run it). Do NOT run `req satisfy`/`req clear` yourself — those are USER "
    "actions (the permission layer blocks Claude from running them)."
)


# Visible breadcrumb appended when the status-briefing formatter throws, so a
# render bug degrades to a one-liner instead of injecting nothing (silence).
_BRIEFING_FALLBACK = (
    "## Requirements Framework active — run `req status` for details "
    "(briefing failed to render)."
)


def _best_effort(label: str, fn, logger) -> None:
    """Run an opportunistic side-effect; never let it break session start."""
    try:
        fn()
    except Exception as e:
        logger.debug(f"{label} failed (fail-open)", error=str(e))


def _init_session_metrics(session_id, project_dir, branch, logger):
    from session_metrics import SessionMetrics
    SessionMetrics(session_id, project_dir, branch).save()
    logger.debug("Session metrics initialized")


def _register_project(config, project_dir, logger):
    from project_registry import ProjectRegistry
    from feature_catalog import detect_configured_features
    raw = config.get_raw_config()
    features = detect_configured_features(raw)
    ProjectRegistry().register_project(
        project_dir, [f for f, e in features.items() if e], raw.get("inherit", False))
    logger.debug("Project registered in upgrade registry")


def _log_obsidian_start(config, session_id, project_dir, branch, logger):
    if not config.get_hook_config('obsidian', 'enabled', False):
        return
    from obsidian import ObsidianSessionLogger
    ObsidianSessionLogger(config).on_session_start(session_id, project_dir, branch)
    logger.debug("Obsidian session note created")


def _get_requirement_status_data(reqs: BranchRequirements, config: RequirementsConfig,
                                  session_id: str, branch: str) -> list[dict]:
    """
    Gather status data for all enabled requirements.

    Returns list of dicts with keys: name, type, scope, satisfied, triggers,
    resolve_action, description, config.
    """
    results = []
    for req_name in config.get_all_requirements():
        if not config.is_requirement_enabled(req_name):
            continue

        req_config = config.get_requirement(req_name)
        scope = req_config.get('scope', 'session')
        req_type = config.get_requirement_type(req_name)

        # Context-aware checking for guard requirements
        if req_type == 'guard':
            context = {
                'branch': branch,
                'session_id': session_id,
                'project_dir': reqs.project_dir,
            }
            satisfied = reqs.is_guard_satisfied(req_name, config, context)
        else:
            satisfied = reqs.is_satisfied(req_name, scope)

        # Get auto-resolve skill or provide default action
        auto_resolve = req_config.get('auto_resolve_skill', '')
        if auto_resolve:
            resolve_action = f"`/{auto_resolve}`"
        elif req_type == 'guard':
            guard_config = config.get_guard_config(req_name)
            if guard_config and guard_config.get('guard_type') == 'protected_branch':
                resolve_action = "Create feature branch"
            elif guard_config and guard_config.get('guard_type') == 'single_session':
                resolve_action = "Close other session"
            else:
                resolve_action = f"`req approve {req_name}`"
        elif req_type == 'dynamic':
            resolve_action = f"`req approve {req_name}`"
        else:
            resolve_action = f"`req satisfy {req_name}`"

        # Get triggers summary
        triggers = config.get_triggers(req_name)
        triggers_summary = summarize_triggers(triggers)

        # Get description
        description = get_requirement_description(req_config)

        results.append({
            'name': req_name,
            'type': req_type,
            'scope': scope,
            'satisfied': satisfied,
            'triggers': triggers_summary,
            'resolve_action': resolve_action,
            'description': description,
            'config': req_config,
        })

    return results


def _shorten_skill_name(skill_path: str) -> str:
    """
    Convert full skill path to short name.

    Examples:
        '/requirements-framework:arch-review' -> '/arch-review'
        '`/requirements-framework:arch-review`' -> '/arch-review'
        'req satisfy foo' -> 'req satisfy foo'  (unchanged)
        '/simple-skill' -> '/simple-skill'  (unchanged, no namespace)
    """
    # Strip backticks
    skill_path = skill_path.strip('`')

    # Extract short name from namespaced path
    if ':' in skill_path and skill_path.startswith('/'):
        # '/requirements-framework:arch-review' -> '/arch-review'
        return '/' + skill_path.split(':')[-1]

    return skill_path


def _group_by_resolve_action(req_data: list[dict]) -> dict[str, list[dict]]:
    """
    Group unsatisfied requirements by their resolve action (short name).

    Returns dict mapping action -> list of requirement dicts.
    Groups that resolve via skill commands come first.
    """
    groups: dict[str, list[dict]] = {}
    for r in req_data:
        if r['satisfied']:
            continue
        action = _shorten_skill_name(r['resolve_action'])
        if action not in groups:
            groups[action] = []
        groups[action].append(r)

    # Sort: skill commands first, then manual commands
    skill_groups = {k: v for k, v in groups.items() if k.startswith('/')}
    other_groups = {k: v for k, v in groups.items() if not k.startswith('/')}

    return {**skill_groups, **other_groups}


def _format_quick_start(req_data: list[dict]) -> list[str]:
    """
    Format the Quick Start section showing actions grouped by resolve command.

    Returns list of lines for the Quick Start section, or empty list if
    all requirements are satisfied.
    """
    groups = _group_by_resolve_action(req_data)

    if not groups:
        return []

    lines = ["### Quick Start", ""]

    for action, reqs in groups.items():
        req_names = ", ".join(f"`{r['name']}`" for r in reqs)

        # Determine trigger context
        triggers = set()
        for r in reqs:
            if 'git commit' in r['triggers']:
                triggers.add('commit')
            elif 'Edit' in r['triggers'] or 'Write' in r['triggers']:
                triggers.add('edit')

        if action.startswith('/'):
            # Skill command
            if 'commit' in triggers:
                lines.append(f"🔍 **Run `{action}`** before `git commit` → satisfies {req_names}")
            else:
                lines.append(f"🚀 **Run `{action}`** → satisfies {req_names}")
        else:
            # Manual action (e.g., "Create feature branch", "req satisfy foo")
            lines.append(f"📋 **{action}** → satisfies {req_names}")

        lines.append("")

    return lines


def format_compact_status(reqs: BranchRequirements, config: RequirementsConfig,
                          session_id: str, branch: str, paused: bool = False) -> str:
    """
    Format compact status (targets ~150 tokens for typical configurations) for context compaction.

    Shows minimal info with high context survival. Used when `source=compact`.

    Example output:
        ## Requirements: 2/4 satisfied

        **Run `/arch-review`** → `adr_reviewed`, `commit_plan`
        **Fallback**: `req satisfy adr_reviewed commit_plan --session abc123`
    """
    req_data = _get_requirement_status_data(reqs, config, session_id, branch)

    if not req_data:
        return "## Requirements: No requirements configured"

    satisfied_count = sum(1 for r in req_data if r['satisfied'])
    total_count = len(req_data)

    lines = [f"## Requirements: {satisfied_count}/{total_count} satisfied"]

    # Group unsatisfied requirements by their short resolve action
    groups = _group_by_resolve_action(req_data)
    if groups:
        lines.append("")
        for action, reqs_in_group in groups.items():
            names = ", ".join(f"`{r['name']}`" for r in reqs_in_group)
            if action.startswith('/'):
                lines.append(f"**Run `{action}`** → {names}")
            else:
                lines.append(f"**{action}** → {names}")

    # Fallback with all unsatisfied requirements
    unsatisfied = [r for r in req_data if not r['satisfied']]
    if unsatisfied:
        lines.append(f"**Fallback**: `req satisfy {' '.join(r['name'] for r in unsatisfied)} --session {session_id}`")
        if not paused:
            lines.append(_GATING_DIRECTIVE)

    return "\n".join(line for line in lines if line)


def format_standard_status(reqs: BranchRequirements, config: RequirementsConfig,
                           session_id: str, branch: str, paused: bool = False) -> str:
    """
    Format standard status (targets ~400 tokens for typical configurations) for session resume.

    Shows tabular status with triggers and resolve actions. Best actionability.
    Used when `source=resume`.

    Example output:
        ## Requirements Framework Active

        **Branch**: `master` @ `/project/path` | **Session**: `6d4487f4`

        ### Quick Start
        🚀 **Run `/arch-review`** → satisfies `adr_reviewed`, `commit_plan`

        | Requirement | Status | Triggers | Resolve |
        ...

        **Fallback**: `req satisfy <name> --session 6d4487f4`
    """
    req_data = _get_requirement_status_data(reqs, config, session_id, branch)

    lines = ["## Requirements Framework Active", ""]
    lines.append(f"**Branch**: `{branch}` @ `{reqs.project_dir}` | **Session**: `{session_id}`")
    lines.append("")

    # Quick Start section (action-oriented)
    quick_start = _format_quick_start(req_data)
    if quick_start:
        lines.extend(quick_start)

    # Status table (compact version without Type column)
    lines.append("| Requirement | Status | Triggers | Resolve |")
    lines.append("|-------------|--------|----------|---------|")

    unsatisfied_reqs = []
    for r in req_data:
        status = "✅" if r['satisfied'] else "⬜"
        short_resolve = _shorten_skill_name(r['resolve_action'])
        if short_resolve.startswith('/'):
            short_resolve = f"`{short_resolve}`"
        lines.append(f"| {r['name']} | {status} | {r['triggers']} | {short_resolve} |")
        if not r['satisfied']:
            unsatisfied_reqs.append(r)

    if not req_data:
        lines.append("| (none configured) | - | - | - |")

    # Fallback
    if unsatisfied_reqs:
        lines.append("")
        lines.append(f"**Fallback**: `req satisfy {' '.join(r['name'] for r in unsatisfied_reqs)} --session {session_id}`")
        if not paused:
            lines.append("")
            lines.append(_GATING_DIRECTIVE)

    return "\n".join(lines)


def format_adaptive_status(reqs: BranchRequirements, config: RequirementsConfig,
                           session_id: str, branch: str, source: str,
                           paused: bool = False) -> str:
    """
    Select and apply the appropriate format based on config.

    Verbosity is controlled by `hooks.session_start.briefing_format`:
    - compact (default): ~150 tokens, high context survival
    - standard: ~400 tokens, best actionability

    Args:
        reqs: BranchRequirements manager
        config: RequirementsConfig instance
        session_id: Current session ID
        branch: Current git branch
        source: Hook source ('startup', 'resume', 'compact', 'clear') — accepted but unused
            since briefing_format selects the formatter directly.
        paused: When True the session has paused the framework's gates; the
            briefing omits the "edits are blocked" gating directive.

    Returns:
        Formatted status string appropriate for the context
    """
    mode = config.get_hook_config('session_start', 'briefing_format', 'compact')

    custom_header = config.get_hook_config('session_start', 'custom_header')
    prefix = f"{custom_header.strip()}\n\n" if custom_header and isinstance(custom_header, str) else ""

    if mode == 'rich':
        get_logger().warning(
            "briefing_format='rich' was removed in 4.0.0; falling back to 'compact'. "
            "Update your config to 'compact' or 'standard' to silence this warning."
        )
        # Fall through to compact
    elif mode == 'standard':
        return prefix + format_standard_status(reqs, config, session_id, branch, paused=paused)
    elif mode != 'compact':
        get_logger().warning(f"Unknown briefing_format '{mode}', using 'compact'")
    return prefix + format_compact_status(reqs, config, session_id, branch, paused=paused)


def _status_or_fallback(reqs: BranchRequirements, config: RequirementsConfig,
                        session_id: str, branch: str, source: str,
                        paused: bool, logger) -> str:
    """Render the status briefing, degrading to a visible breadcrumb on failure.

    The status formatter must never leave the session silent: if rendering
    throws, return `_BRIEFING_FALLBACK` instead of nothing. Kept as a seam so
    the fallback wiring (not just the constant) is unit-testable.
    """
    try:
        return format_adaptive_status(reqs, config, session_id, branch, source, paused=paused)
    except Exception as e:
        logger.error("Failed to format status", error=str(e))
        return _BRIEFING_FALLBACK


def check_other_sessions_warning(config: RequirementsConfig, project_dir: str,
                                  session_id: str, logger) -> str | None:
    """
    Check if other sessions are active on this project and generate warning.

    Only generates a warning if a single_session guard is configured.
    This is informational only - does not block.

    Args:
        config: RequirementsConfig instance
        project_dir: Current project directory
        session_id: Current session ID
        logger: Logger instance

    Returns:
        Warning message string if other sessions exist, None otherwise
    """
    # Check if any single_session guard is configured
    has_single_session_guard = False
    for req_name in config.get_all_requirements():
        if not config.is_requirement_enabled(req_name):
            continue
        req_type = config.get_requirement_type(req_name)
        if req_type != 'guard':
            continue
        try:
            guard_config = config.get_guard_config(req_name)
            if guard_config and guard_config.get('guard_type') == 'single_session':
                has_single_session_guard = True
                break
        except (ValueError, KeyError):
            continue

    if not has_single_session_guard:
        return None

    # Check for other active sessions on this project
    try:
        active = get_active_sessions(project_dir=project_dir)
        other_sessions = [s for s in active if s.get('id') != session_id]

        if not other_sessions:
            return None

        # Generate warning message
        import time
        lines = ["⚠️  **Other Claude Code sessions detected on this project**", ""]

        for sess in other_sessions:
            sess_id = sess.get('id', 'unknown')
            branch = sess.get('branch', 'unknown')
            last_active = sess.get('last_active', 0)

            if last_active:
                elapsed = int(time.time()) - last_active
                if elapsed < 60:
                    time_str = f"{elapsed}s ago"
                elif elapsed < 3600:
                    time_str = f"{elapsed // 60}m ago"
                else:
                    time_str = f"{elapsed // 3600}h ago"
            else:
                time_str = "unknown"

            lines.append(f"  • `{sess_id}` on `{branch}` (active {time_str})")

        lines.append("")
        lines.append("**Note**: Edits may be blocked to prevent conflicts.")
        lines.append("Use `req approve single_session_per_project` to override if needed.")

        return "\n".join(lines)

    except Exception as e:
        logger.warning("Failed to check other sessions", error=str(e))
        return None


def main() -> int:
    """Hook entry point."""
    # Parse stdin input
    input_data = {}
    try:
        stdin_content = sys.stdin.read()
        if stdin_content:
            input_data = json.loads(stdin_content)
    except json.JSONDecodeError as e:
        # Log parse error but fail open
        logger = get_logger(base_context={"hook": "SessionStart"})
        logger.error(
            "Failed to parse hook input JSON",
            error=str(e),
            stdin_preview=stdin_content[:200] if stdin_content else "empty"
        )

    # Get session ID from stdin (Claude Code always provides this)
    raw_session = input_data.get('session_id')
    if not raw_session:
        # This should NEVER happen - Claude Code always provides session_id
        # If it does, fail open with a logged warning
        logger = get_logger(base_context={"hook": "SessionStart"})
        logger.error("No session_id in hook input!", input_keys=list(input_data.keys()))
        return 0  # Fail open

    session_id = normalize_session_id(raw_session)

    # Early hook setup: loads config, creates logger with correct level
    project_dir, branch, config, logger = early_hook_setup(
        session_id, "SessionStart", cwd=input_data.get('cwd')
    )

    try:
        # Skip if requirements explicitly disabled
        if os.environ.get('CLAUDE_SKIP_REQUIREMENTS'):
            return 0

        # Skip if no project context
        if not project_dir or not branch:
            return 0

        # Check if project has its own config
        project_config_yaml = Path(project_dir) / '.claude' / 'requirements.yaml'
        has_project_config = project_config_yaml.exists()

        # Suggest init if no project config (only on startup, not resume/compact)
        source = input_data.get('source', 'startup')
        if not has_project_config and source == 'startup':
            emit_hook_context("SessionStart", """💡 **No requirements config found for this project**

To set up the requirements framework, run:
  `req init`

Or create `.claude/requirements.yaml` manually.
See `req init --help` for options.""")
            return 0

        # Skip if config wasn't loaded (shouldn't happen given checks above)
        if not config:
            return 0

        # Skip if framework disabled
        if not config.is_enabled():
            return 0

        # Pause state (gates suppressed): drives a pause-aware briefing below.
        try:
            from pause import is_paused as _is_paused
            session_paused = _is_paused(session_id, project_dir)
        except Exception:
            session_paused = False

        logger.info("Session starting", source=source)

        # 1. Clean stale sessions
        stale_count = cleanup_stale_sessions()
        if stale_count > 0:
            logger.info("Cleaned stale sessions", count=stale_count)

        # 2. Update registry with current session
        try:
            update_registry(session_id, project_dir, branch)
        except Exception as e:
            logger.error("Failed to update registry", error=str(e))

        # 2a. Initialize session metrics for learning system
        _best_effort("session metrics", lambda: _init_session_metrics(session_id, project_dir, branch, logger), logger)

        # 2b. Auto-register project in project registry (for upgrade discovery)
        _best_effort("project registry", lambda: _register_project(config, project_dir, logger), logger)

        # 2c. WIP tracking: register session and detect merged branches
        wip_summary = None
        try:
            wip_enabled = config.get_hook_config('wip_tracking', 'enabled', False)
            wip_inject = config.get_hook_config('wip_tracking', 'inject_on_start', True)
            exclude_branches = config.get_hook_config(
                'wip_tracking', 'exclude_branches',
                ['main', 'master', 'develop']
            )

            if wip_enabled and branch not in exclude_branches:
                from wip_tracker import WipTracker
                tracker = WipTracker()
                tracker.add_session(project_dir, branch, session_id)

                # Auto-detect merged branches
                merged = []
                if config.get_hook_config('wip_tracking', 'auto_detect_merged', True):
                    merged = tracker.check_merged_branches(project_dir)

                # Build WIP summary for context injection
                if wip_inject:
                    entries = tracker.list_entries()
                    # Filter out done entries for the summary
                    active = [e for e in entries if e.get("status") != "done"]
                    if active:
                        lines = ["### WIP Branches", "| Branch | Status | Summary | Commits |",
                                 "|--------|--------|---------|---------|"]
                        for e in active[:10]:  # Cap at 10 entries
                            proj_name = Path(e["project_dir"]).name
                            b = e.get("branch", "?")
                            s = e.get("status", "?").upper()
                            summary = e.get("summary", "")[:40]
                            commits = e.get("git_metrics", {}).get("commit_count", 0)
                            lines.append(f"| {proj_name}/{b} | {s} | {summary} | {commits} |")
                        if merged:
                            lines.append(f"\n{len(merged)} branch(es) merged since last session (auto-marked DONE)")
                        wip_summary = "\n".join(lines)

                logger.debug("WIP tracking initialized", entries=len(active) if wip_inject and 'active' in dir() else 0)
        except Exception as e:
            logger.debug("WIP tracking failed (fail-open)", error=str(e))

        # 2e. Obsidian session logging: create session note
        _best_effort("obsidian session note", lambda: _log_obsidian_start(config, session_id, project_dir, branch, logger), logger)

        # 2d. Check for other sessions and warn if single_session guard is enabled
        other_sessions_warning = check_other_sessions_warning(
            config, project_dir, session_id, logger
        )

        # 2f. Retrieval pipeline (Step 14): query Qdrant for similar prior
        # sessions, render a compact block, prepend to context. Off by default.
        # Same fail-open + sys.path trick as Step 13's SessionEnd qdrant block:
        # the llm.* package is only installed if `pip install -e '.[llm]'` has
        # been run; an ImportError just means retrieval stays disabled.
        retrieval_block = ""
        try:
            retrieval_enabled = config.get_hook_config('retrieval', 'enabled', False)
            if retrieval_enabled:
                repo_root = Path(__file__).resolve().parent.parent
                if str(repo_root) not in sys.path:
                    sys.path.insert(0, str(repo_root))
                from hooks.lib.llm.memory import (
                    write_retrieval_json,
                    render_retrieval,
                    _recent_commit_subjects,
                )
                query = f"{branch} {_recent_commit_subjects(3)}".strip()
                payload = write_retrieval_json(
                    branch,
                    query,
                    top_k=config.get_hook_config('retrieval', 'top_k', 3),
                    timeout_s=config.get_hook_config('retrieval', 'timeout_s', 1.5),
                )
                retrieval_block = render_retrieval(
                    payload.get('hits', []),
                    max_hits=config.get_hook_config('retrieval', 'max_hits', 3),
                    min_score=config.get_hook_config('retrieval', 'min_score', 0.5),
                )
                logger.debug(
                    "Retrieval pipeline ran",
                    hits=len(payload.get('hits', [])),
                    rendered=bool(retrieval_block),
                )
        except Exception as e:
            logger.debug("Retrieval pipeline failed (fail-open)", error=str(e))

        # 3. Assemble and inject context (warnings + status) if applicable
        inject_context = config.get_hook_config('session_start', 'inject_context', True)

        parts = []
        if retrieval_block:
            parts.append(retrieval_block)
        if wip_summary:
            parts.append(wip_summary)
        if other_sessions_warning:
            parts.append(other_sessions_warning)
        if inject_context:
            try:
                reqs = BranchRequirements(branch, session_id, project_dir)

                # Carry over session-scoped requirements from recent sessions
                # (plan-then-execute workflow: /clear creates new session ID)
                if source in ('startup', 'clear'):
                    try:
                        carry_cfg = config.get_hook_config(
                            'session_start', 'carry_over', {}
                        )
                        if carry_cfg.get('enabled', True):
                            guard_names = {
                                name for name in config.requirements.get_all_requirements()
                                if config.requirements.get_requirement_type(name) == 'guard'
                            }
                            carried = reqs.carry_over_from_recent_session(
                                window_seconds=carry_cfg.get('window_seconds', 300),
                                scopes=carry_cfg.get('scopes', ['session']),
                                guard_names=guard_names,
                            )
                            if carried:
                                names = ', '.join(f'`{n}`' for n in carried)
                                parts.append(
                                    f"Carried over {len(carried)} requirement(s) "
                                    f"from previous session: {names}"
                                )
                                logger.info(
                                    "Carried over requirements",
                                    count=len(carried),
                                    requirements=list(carried.keys()),
                                )
                    except Exception as e:
                        logger.warning("Carry-over failed (fail-open)", error=str(e))

                parts.append(_status_or_fallback(
                    reqs, config, session_id, branch, source, session_paused, logger))
            except Exception as e:
                # Setup/carry-over failed before rendering — still never go silent.
                logger.error("Failed to build status briefing", error=str(e))
                parts.append(_BRIEFING_FALLBACK)

            # Lazy-dev ladder: ride the single SessionStart emit (fires once/
            # session, so no dedup needed). Flag-gated + fail-open in the helper.
            from lazy_dev.rules import ladder_text
            _ladder = ladder_text(config)
            if _ladder:
                parts.append(_ladder)

        # Session pause: prepend a visible banner so a paused session is never
        # silently off (the gates are suppressed but status still shows).
        try:
            from pause import paused_banner
            _pb = paused_banner(session_id, project_dir)
            if _pb:
                parts.insert(0, _pb)
        except Exception:
            pass

        if parts:
            emit_hook_context("SessionStart", "\n\n".join(parts))

        # --- strict preflight: loud non-compliance briefing (fail-open) ---
        # Skipped while paused: the gates are suppressed, so nagging about
        # strict-mode non-compliance would contradict the pause-aware briefing.
        if not session_paused:
            try:
                from preflight import evaluate, format_strict_warning
                _verdict = evaluate(
                    project_dir, strict_enabled=config.strict_preflight_enabled()
                )
                _warn = format_strict_warning(_verdict)
                if _warn:
                    emit_hook_context("SessionStart", _warn)
            except Exception as e:
                logger.debug("strict preflight briefing skipped", error=str(e))

        return 0

    except Exception as e:
        # FAIL OPEN - never block on errors
        logger.error("Unhandled error in SessionStart hook", error=str(e))
        return 0


if __name__ == '__main__':
    sys.exit(main())
