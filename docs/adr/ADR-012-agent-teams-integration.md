# ADR-012: Agent Teams Integration

## Status
Approved (2026-02-13)
Amended (2026-02-13): Team commands promoted to primary review approach
Amended (2026-02-16): /pre-commit upgraded to team-based with subagent fallback

## Context

The requirements framework currently uses subagents (Task tool) for all review orchestration. Commands like `/pre-commit`, `/quality-check`, and `/plan-review` launch specialized agents that report results back to a single orchestrator, which then aggregates findings and produces a verdict.

This model works well for sequential pipelines and single-agent tasks. However, it has a limitation: **agents cannot cross-validate each other's findings**. When a code-reviewer flags a potential bug and a silent-failure-hunter identifies missing error handling in the same area, both findings appear independently and the user must reconcile them.

Claude Code now supports **Agent Teams** — a coordination model where multiple Claude instances collaborate as a team. A lead coordinates work, teammates operate independently with their own context windows, and they communicate via direct messaging and a shared task list. This is fundamentally different from subagents: teammates can debate findings, corroborate or dispute each other, and produce unified verdicts.

Key considerations:
1. **Agent Teams** — now the primary recommended approach (env var gate removed)
2. **Higher token cost** — each teammate has its own context window and API calls
3. **New hook event types** — `TeammateIdle` and `TaskCompleted` are Claude Code hook event types (registered in `settings.json` alongside `PreToolUse`, `PostToolUse`, etc.) that enable progress tracking and quality gates
4. **Not all workflows benefit** — sequential pipelines and blocking gates don't need inter-agent debate

## Decision

**Team-based review commands are the primary recommended approach; existing subagent commands remain as lightweight alternatives.**

### New Commands

- `/deep-review` — Cross-validated code review where agents debate findings before presenting a unified verdict. Primary approach for `pre_pr_review`.
- `/arch-review` — Multi-perspective architecture review where agents debate architectural implications and generate commit strategy. Primary approach for all 4 planning requirements (`commit_plan`, `adr_reviewed`, `tdd_planned`, `solid_reviewed`).

### Execution Model

Team-based commands follow a hybrid approach:
- **Blocking gates** (tool-validator) still use subagents — no benefit from debate on deterministic linter output
- **Review phases** use Agent Teams — agents share findings via SendMessage, lead cross-validates
- **Final polish** (code-simplifier) still uses subagents — independent final pass

### New Hook Event Types

Two new Claude Code hook event types support team workflows. These are registered in `settings.json` as top-level event types (like `PreToolUse`, `PostToolUse`, `Stop`), not as PostToolUse matchers:

- `TeammateIdle` — Fires when a teammate goes idle during a team session. The hook receives JSON with teammate name, team name, and session ID. Enables progress logging and optional re-engagement (exit code 2 sends feedback to keep the teammate working).
- `TaskCompleted` — Fires when a team task is marked complete via TaskUpdate. The hook receives JSON with task ID, subject, team name, and session ID. Enables output quality validation before accepting task completion.

Both hooks are registered and enabled by default. They follow the same fail-open pattern as all existing hooks.

### Feature Gate (Removed)

The env var gate (`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`) has been removed. Team commands now execute directly without requiring an opt-in flag. If `TeamCreate` fails at runtime (e.g., Agent Teams not available in the user's Claude Code version), the command should catch the error and fall back to the equivalent subagent command gracefully.

### Configuration

```yaml
hooks:
  agent_teams:
    enabled: true           # Enabled by default
    keep_working_on_idle: false
    validate_task_completion: false
    max_teammates: 5        # Token cost cap
    fallback_to_subagents: true  # Graceful degradation
```

## Allowed

**Team-based commands as new commands, not flags on existing**:
- `/deep-review` for cross-validated code review
- `/arch-review` for architecture review with debate
- `/pre-commit` upgraded to team-based (2026-02-16): uses Agent Teams when 2+ review agents enabled, falls back to subagents for single-agent runs
- Existing `/quality-check`, `/plan-review` remain unchanged as lightweight alternatives

**Hybrid execution within team commands**:
- Blocking gates and final polish via subagents (no debate needed)
- Review phases via Agent Teams (cross-validation adds value)

**Hook events for team workflow support**:
- `TeammateIdle` for progress tracking
- `TaskCompleted` for quality gates
- Both opt-in via configuration

**Auto-satisfaction at command level**:
- Team task completion is internal plumbing
- Requirement satisfaction happens when the Skill (command) completes
- Uses existing `auto-satisfy-skills.py` mechanism

## Prohibited

**Removing existing subagent commands**:
- `/plan-review` and `/quality-check` must remain available as lightweight alternatives
- Users who prefer lower token cost should always have a working option

**Team mode for blocking gates**:
- Tool-validator runs deterministic linters — no value from debate
- Code-simplifier is a final independent pass — debate would slow it down

**Hook events that block by default**:
- TeammateIdle and TaskCompleted must be no-ops when config is disabled
- Fail-open on all errors

## Consequences

### Positive
- Higher-quality reviews through cross-validation and debate
- Corroborated findings have increased confidence
- Disputed findings surface ambiguity that single-agent reviews miss
- Framework stays current with Claude Code capabilities
- No impact on users who don't opt in

### Negative
- Higher token cost for team-based reviews (each teammate has own context)
- More complex orchestration logic in team commands
- Two additional hooks to maintain
- Team cleanup required (shutdown teammates, TeamDelete)
- Plugin command count increases from 6 to 8 (documentation updates needed in CLAUDE.md and ADR-006)

### Neutral
- Existing commands unchanged — no migration needed
- May need updates as Agent Teams API evolves
- Hook events (TeammateIdle, TaskCompleted) may gain more capabilities over time

## Alternatives Considered

### Add `--team` flag to existing commands
Rejected. Mixing subagent and team execution models in a single command makes the code harder to test and document. Users would need to understand when `--team` helps vs. wastes tokens. Separate commands make the cost/quality tradeoff explicit.

### Make team mode the default when Agent Teams are available
Initially rejected due to experimental nature of Agent Teams API. **Later approved** (2026-02-13): team commands are now the primary recommended approach with subagent commands retained as lightweight alternatives. The env var gate was removed and `auto_resolve_skill` was updated to point to team commands.

### Use PostToolUse hooks instead of new event types
Considered but not chosen. TeammateIdle and TaskCompleted are distinct lifecycle events that don't map cleanly to existing tool use patterns. Registering them as their own hook event types keeps the hook contract clean and avoids overloading PostToolUse with non-tool concerns.

## Implementation Notes

1. **ADR-007 compliance**: Team commands follow the same deterministic step pattern as existing commands
2. **ADR-006 compliance**: New commands and hooks integrate into the existing unified plugin structure; command count increases from 6 to 8
3. **Fail-open design**: All new hooks follow the framework's fail-open principle, including structured logging via `get_logger`
4. **TDD workflow**: Hook tests written first in `test_requirements.py`, then implementation
5. **Cross-validation severity adjustment**: Findings confirmed by 2+ agents get escalated; contradicted findings note disagreement
6. **Teammate timeout**: Team commands should set a per-teammate response timeout (configurable, default 120s). If a teammate fails to produce findings, the lead proceeds with available findings and notes the gap in output. Partial results are better than no results.
7. **Team cleanup resilience**: Team artifacts are cleaned up at command completion. If cleanup fails (teammate rejects shutdown, TeamDelete errors), log the failure and proceed. Stale teams do not block future operations.
8. **Graceful TeamCreate failure**: If `TeamCreate` fails (e.g., Agent Teams not available in the user's Claude Code version), catch the error and fall back to the equivalent subagent command (`/plan-review` for `/arch-review`, `/quality-check parallel` for `/deep-review`). Log the fallback for debugging.

## Files Created/Modified

### New Files
- `hooks/handle-teammate-idle.py` — TeammateIdle hook
- `hooks/handle-task-completed.py` — TaskCompleted hook
- `plugins/requirements-framework/commands/deep-review.md` — Team-based code review command
- `plugins/requirements-framework/commands/arch-review.md` — Team-based architecture review command

### Modified Files
- `hooks/auto-satisfy-skills.py` — Add skill mappings for new commands
- `hooks/test_requirements.py` — Add tests for new hooks
- `install.sh` — Register new hook events
- `examples/global-requirements.yaml` — Add `hooks.agent_teams` configuration section
- `plugins/requirements-framework/.claude-plugin/plugin.json` — Register new commands
- `CLAUDE.md` — Document Agent Teams integration

## Related ADRs

- **ADR-006**: Plugin-Based Architecture — New commands and hooks integrate into the unified plugin structure
- **ADR-007**: Deterministic Command Orchestrators — Team commands follow the same deterministic step pattern
- **ADR-009**: Agent Auto-Fix for Plan Validation — Related agent coordination patterns for plan review
