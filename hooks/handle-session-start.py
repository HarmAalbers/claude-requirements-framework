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
- Plain text status (injected into Claude's context)
- Or empty if inject_context is disabled
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
from console import emit_text


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


def format_compact_status(reqs: BranchRequirements, config: RequirementsConfig,
                          session_id: str, branch: str) -> str:
    """
    Format compact status (targets ~150 tokens for typical configurations) for context compaction.

    Shows minimal info with high context survival. Used when `source=compact`.

    Example output:
        ## Requirements: 2/4 satisfied

        **Unsatisfied**: `adr_reviewed`, `commit_plan` → `/plan-review`
        **Fallback**: `req satisfy adr_reviewed commit_plan --session abc123`
    """
    req_data = _get_requirement_status_data(reqs, config, session_id, branch)

    if not req_data:
        return "## Requirements: No requirements configured"

    satisfied_count = sum(1 for r in req_data if r['satisfied'])
    total_count = len(req_data)

    lines = [f"## Requirements: {satisfied_count}/{total_count} satisfied"]

    unsatisfied = [r for r in req_data if not r['satisfied']]
    if unsatisfied:
        names = ", ".join(f"`{r['name']}`" for r in unsatisfied)
        # Find common resolve action if any
        resolve_skills = set()
        for r in unsatisfied:
            if r['resolve_action'].startswith('`/'):
                resolve_skills.add(r['resolve_action'])
        if len(resolve_skills) == 1:
            lines.append(f"\n**Unsatisfied**: {names} → {resolve_skills.pop()}")
        else:
            lines.append(f"\n**Unsatisfied**: {names}")

    lines.append(f"**Fallback**: `req satisfy {' '.join(r['name'] for r in unsatisfied)} --session {session_id}`" if unsatisfied else "")

    return "\n".join(line for line in lines if line)


def format_standard_status(reqs: BranchRequirements, config: RequirementsConfig,
                           session_id: str, branch: str) -> str:
    """
    Format standard status (targets ~400 tokens for typical configurations) for session resume.

    Shows tabular status with triggers and resolve actions. Best actionability.
    Used when `source=resume`.

    Example output:
        ## Requirements Framework Active

        **Branch**: `master` @ `/project/path` | **Session**: `6d4487f4`

        | Requirement | Type | Scope | Status | Triggers | Resolve |
        |-------------|------|-------|--------|----------|---------|
        | adr_reviewed | blocking | session | ⬜ | Edit, Write | `/plan-review` |
        ...

        ### Workflow
        - **Edit/Write blocked?** → Run `/plan-review` first

        **Fallback**: `req satisfy <name> --session 6d4487f4`
    """
    req_data = _get_requirement_status_data(reqs, config, session_id, branch)

    lines = ["## Requirements Framework Active", ""]
    lines.append(f"**Branch**: `{branch}` @ `{reqs.project_dir}` | **Session**: `{session_id}`")
    lines.append("")

    # Table header
    lines.append("| Requirement | Type | Scope | Status | Triggers | Resolve |")
    lines.append("|-------------|------|-------|--------|----------|---------|")

    unsatisfied_reqs = []
    for r in req_data:
        status = "✅" if r['satisfied'] else "⬜"
        scope_display = r['scope'] if r['type'] != 'guard' else "-"
        lines.append(f"| {r['name']} | {r['type']} | {scope_display} | {status} | {r['triggers']} | {r['resolve_action']} |")
        if not r['satisfied']:
            unsatisfied_reqs.append(r)

    if not req_data:
        lines.append("| (none configured) | - | - | - | - | - |")

    # Workflow hints based on what's unsatisfied
    lines.append("")
    lines.append("### Workflow")

    edit_blocked = any(r for r in unsatisfied_reqs if 'Edit' in r['triggers'] or 'Write' in r['triggers'])
    commit_blocked = any(r for r in unsatisfied_reqs if 'git commit' in r['triggers'])

    if edit_blocked:
        edit_skills = set()
        for r in unsatisfied_reqs:
            if ('Edit' in r['triggers'] or 'Write' in r['triggers']) and r['resolve_action'].startswith('`/'):
                edit_skills.add(r['resolve_action'])
        if edit_skills:
            lines.append(f"- **Edit/Write blocked?** → Run {', '.join(sorted(edit_skills))} first")
        else:
            lines.append("- **Edit/Write blocked?** → Satisfy requirements first")

    if commit_blocked:
        commit_skills = set()
        for r in unsatisfied_reqs:
            if 'git commit' in r['triggers'] and r['resolve_action'].startswith('`/'):
                commit_skills.add(r['resolve_action'])
        if commit_skills:
            lines.append(f"- **Commit blocked?** → Run {', '.join(sorted(commit_skills))} first")

    if not edit_blocked and not commit_blocked and unsatisfied_reqs:
        lines.append("- Requirements ready for most operations")

    # Fallback
    if unsatisfied_reqs:
        lines.append("")
        lines.append(f"**Fallback**: `req satisfy {' '.join(r['name'] for r in unsatisfied_reqs)} --session {session_id}`")

    return "\n".join(lines)


def format_rich_status(reqs: BranchRequirements, config: RequirementsConfig,
                       session_id: str, branch: str) -> str:
    """
    Format rich status (targets ~800 tokens for typical configurations) for session startup.

    Full context with requirement definitions, scope reference, and workflow guide.
    Used when `source=startup` or `source=clear`.

    Provides comprehensive briefing for new sessions.
    """
    req_data = _get_requirement_status_data(reqs, config, session_id, branch)

    lines = ["## Requirements Framework: Session Briefing", ""]
    lines.append(f"**Project**: `{reqs.project_dir}`")
    lines.append(f"**Branch**: `{branch}` | **Session**: `{session_id}`")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Requirement Definitions
    lines.append("### Requirement Definitions")
    lines.append("")

    for r in req_data:
        scope_info = f", {r['scope']}-scoped" if r['type'] != 'guard' else ""
        lines.append(f"**{r['name']}** ({r['type']}{scope_info})")
        lines.append(f"> {r['description']}")
        lines.append(f"> Triggers: {r['triggers']}")
        lines.append(f"> Resolve: {r['resolve_action']}")
        lines.append("")

    if not req_data:
        lines.append("(No requirements configured)")
        lines.append("")

    # Scope Reference
    lines.append("---")
    lines.append("")
    lines.append("### Scope Reference")
    lines.append("| Scope | Behavior |")
    lines.append("|-------|----------|")
    lines.append("| session | Cleared when session ends |")
    lines.append("| branch | Persists across sessions on same branch |")
    lines.append("| single_use | Cleared after trigger command completes |")
    lines.append("| permanent | Never auto-cleared |")
    lines.append("")

    # Current Status
    lines.append("---")
    lines.append("")
    lines.append("### Current Status")
    lines.append("")
    lines.append("| Requirement | Status |")
    lines.append("|-------------|--------|")

    unsatisfied_reqs = []
    for r in req_data:
        status_text = "✅ Satisfied" if r['satisfied'] else "⬜ Not satisfied"
        # Add context for guards
        if r['type'] == 'guard' and r['satisfied']:
            req_config = r['config']
            if req_config.get('guard_type') == 'protected_branch':
                status_text = "✅ (not on protected branch)"
            elif req_config.get('guard_type') == 'single_session':
                status_text = "✅ (no other sessions)"
        lines.append(f"| {r['name']} | {status_text} |")
        if not r['satisfied']:
            unsatisfied_reqs.append(r)

    if not req_data:
        lines.append("| (none configured) | - |")

    lines.append("")

    # Workflow Guide
    lines.append("---")
    lines.append("")
    lines.append("### Workflow Guide")
    lines.append("")

    # Determine what skills are needed
    planning_skills = set()
    commit_skills = set()
    pr_skills = set()

    for r in unsatisfied_reqs:
        if 'Edit' in r['triggers'] or 'Write' in r['triggers']:
            if r['resolve_action'].startswith('`/'):
                planning_skills.add(r['resolve_action'].strip('`'))
        if 'git commit' in r['triggers']:
            if r['resolve_action'].startswith('`/'):
                commit_skills.add(r['resolve_action'].strip('`'))
        if 'gh pr' in r['triggers']:
            if r['resolve_action'].startswith('`/'):
                pr_skills.add(r['resolve_action'].strip('`'))

    if planning_skills or unsatisfied_reqs:
        lines.append("**Starting implementation?**")
        step = 1
        if planning_skills:
            lines.append(f"{step}. Run `/{list(planning_skills)[0]}` to satisfy planning requirements")
            step += 1
        lines.append(f"{step}. Make your edits")
        step += 1
        if commit_skills:
            lines.append(f"{step}. Run `/{list(commit_skills)[0]}` before committing")
        lines.append("")

    lines.append("**Common patterns**:")
    lines.append("- New session → satisfy planning requirements first")
    if commit_skills:
        lines.append(f"- Before commit → `/{list(commit_skills)[0]}`")
    if pr_skills:
        lines.append(f"- Creating PR → `/{list(pr_skills)[0]}`")
    lines.append("")

    # Fallback
    if unsatisfied_reqs:
        lines.append(f"**Fallback**: `req satisfy {' '.join(r['name'] for r in unsatisfied_reqs)} --session {session_id}`")

    return "\n".join(lines)


def format_adaptive_status(reqs: BranchRequirements, config: RequirementsConfig,
                           session_id: str, branch: str, source: str) -> str:
    """
    Select and apply the appropriate format based on source and config.

    Implements tiered progressive disclosure:
    - compact: ~150 tokens, high context survival (for compaction)
    - standard: ~400 tokens, best actionability (for resume)
    - rich: ~800 tokens, full context (for startup/clear)

    Args:
        reqs: BranchRequirements manager
        config: RequirementsConfig instance
        session_id: Current session ID
        branch: Current git branch
        source: Hook source ('startup', 'resume', 'compact', 'clear')

    Returns:
        Formatted status string appropriate for the context
    """
    # Get configured injection mode (default: 'auto')
    mode = config.get_hook_config('session_start', 'injection_mode', 'auto')

    # Add custom header if configured (applies to all formats)
    custom_header = config.get_hook_config('session_start', 'custom_header')
    prefix = f"{custom_header.strip()}\n\n" if custom_header and isinstance(custom_header, str) else ""

    # Select format based on mode
    if mode == 'auto':
        # Adaptive selection based on source
        if source == 'compact':
            return prefix + format_compact_status(reqs, config, session_id, branch)
        elif source == 'resume':
            return prefix + format_standard_status(reqs, config, session_id, branch)
        else:  # startup, clear, or unknown
            return prefix + format_rich_status(reqs, config, session_id, branch)
    elif mode == 'compact':
        return prefix + format_compact_status(reqs, config, session_id, branch)
    elif mode == 'standard':
        return prefix + format_standard_status(reqs, config, session_id, branch)
    elif mode == 'rich':
        return prefix + format_rich_status(reqs, config, session_id, branch)
    else:
        # Unknown mode - fall back to standard (good balance)
        get_logger().warning(f"Unknown injection_mode '{mode}', using 'standard'")
        return prefix + format_standard_status(reqs, config, session_id, branch)


def format_full_status(reqs: BranchRequirements, config: RequirementsConfig,
                       session_id: str, branch: str) -> str:
    """
    Format detailed requirement status with rules for autonomous operation.

    DEPRECATED: Use format_adaptive_status() instead for source-aware formatting.
    This function is kept for backwards compatibility.

    Args:
        reqs: BranchRequirements manager
        config: RequirementsConfig instance
        session_id: Current session ID
        branch: Current git branch

    Returns:
        Formatted status string for context injection
    """
    # Delegate to adaptive status with 'startup' as default source
    return format_adaptive_status(reqs, config, session_id, branch, 'startup')


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
            emit_text("""💡 **No requirements config found for this project**

To set up the requirements framework, run:
  `req init`

Or create `.claude/requirements.yaml` manually.
See `req init --help` for options.
""")
            return 0

        # Skip if config wasn't loaded (shouldn't happen given checks above)
        if not config:
            return 0

        # Skip if framework disabled
        if not config.is_enabled():
            return 0

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

        # 2b. Check for other sessions and warn if single_session guard is enabled
        other_sessions_warning = check_other_sessions_warning(
            config, project_dir, session_id, logger
        )
        if other_sessions_warning:
            emit_text(other_sessions_warning)
            emit_text("")  # Add blank line before status

        # 3. Inject context if configured (default: True)
        if config.get_hook_config('session_start', 'inject_context', True):
            reqs = BranchRequirements(branch, session_id, project_dir)
            status = format_adaptive_status(reqs, config, session_id, branch, source)
            emit_text(status)

        return 0

    except Exception as e:
        # FAIL OPEN - never block on errors
        logger.error("Unhandled error in SessionStart hook", error=str(e))
        return 0


if __name__ == '__main__':
    sys.exit(main())
