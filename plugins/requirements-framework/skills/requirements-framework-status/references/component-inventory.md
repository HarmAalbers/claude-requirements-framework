# Component Inventory

Detailed inventory of all Requirements Framework components with line counts and purposes.

## Hooks (15 total)

| Hook File | Type | Purpose |
|-----------|------|---------|
| `check-requirements.py` | PreToolUse | Blocks Edit/Write if requirements unsatisfied |
| `handle-session-start.py` | SessionStart | Injects context, shows status on session start |
| `handle-prompt-submit.py` | UserPromptSubmit | Prompt context injection and metrics tracking |
| `handle-permission-request.py` | PermissionRequest | Auto-deny dangerous command patterns |
| `handle-plan-exit.py` | PostToolUse (ExitPlanMode) | Shows status after planning phase |
| `auto-satisfy-skills.py` | PostToolUse (Skill) | Auto-satisfy requirements when skills complete |
| `clear-single-use.py` | PostToolUse (Bash) | Clear single_use requirements after action |
| `handle-tool-failure.py` | PostToolUseFailure | Track failure patterns in session metrics |
| `handle-subagent-start.py` | SubagentStart | Inject requirement context into review subagents |
| `handle-pre-compact.py` | PreCompact | Save requirement state before compaction |
| `handle-stop.py` | Stop | Verifies requirements before Claude stops |
| `handle-session-end.py` | SessionEnd | Cleanup stale sessions |
| `handle-teammate-idle.py` | TeammateIdle | Team progress tracking (disabled by default) |
| `handle-task-completed.py` | TaskCompleted | Team task quality gates (disabled by default) |
| `ruff_check.py` | PreToolUse | Python linting integration |

---

## Core Libraries (hooks/lib/)

| Module | Purpose | Lines |
|--------|---------|-------|
| `requirements.py` | Core BranchRequirements API | 452 |
| `config.py` | Configuration cascade loader | 865 |
| `state_storage.py` | JSON state persistence in `.git/requirements/` | 272 |
| `session.py` | Session tracking & registry management | 312 |
| `registry_client.py` | Session registry client | 200 |

**Total Core Lines**: ~2,101

---

## Strategy Libraries

| Module | Purpose | Lines |
|--------|---------|-------|
| `strategy_registry.py` | Central dispatch mechanism for requirement types | 148 |
| `base_strategy.py` | Abstract base class for strategies | 92 |
| `blocking_strategy.py` | Blocking requirement implementation | 186 |
| `dynamic_strategy.py` | Dynamic requirement with calculators | 224 |
| `guard_strategy.py` | Guard requirement (condition checks) | 178 |
| `strategy_utils.py` | Shared strategy utilities | 87 |

**Total Strategy Lines**: ~915

---

## Utility Libraries

| Module | Purpose | Lines |
|--------|---------|-------|
| `branch_size_calculator.py` | Dynamic branch size calculation | 352 |
| `calculation_cache.py` | TTL-based results caching (30-sec default) | 154 |
| `calculator_interface.py` | Abstract calculator base class | 73 |
| `message_dedup_cache.py` | Message deduplication (5-min TTL) | 285 |
| `git_utils.py` | Git operations (branch, repo detection) | 160 |
| `config_utils.py` | Configuration utility functions | 98 |
| `colors.py` | Terminal colors (NO_COLOR support) | 157 |
| `logger.py` | Structured JSON logging | 151 |

**Total Utility Lines**: ~1,430

---

## Interactive Libraries

| Module | Purpose | Lines |
|--------|---------|-------|
| `init_presets.py` | Initialization wizard presets | 463 |
| `interactive.py` | Interactive UI components | 219 |
| `feature_selector.py` | Feature selection logic | 148 |

**Total Interactive Lines**: ~830

---

## CLI Tool

| File | Purpose | Lines |
|------|---------|-------|
| `requirements-cli.py` | `req` command implementation | 1,839 |

**Commands** (11 total):
- `req status` - Show requirement status
- `req satisfy` - Mark requirement satisfied
- `req clear` - Clear a requirement
- `req init` - Interactive project setup
- `req config` - View/modify configuration
- `req doctor` - Verify installation & sync
- `req verify` - Quick installation check
- `req sessions` - View active sessions
- `req list` - List all requirements
- `req prune` - Clean stale data
- `req enable` / `req disable` - Toggle requirements
- `req logging` - Configure logging

---

## Test Suite

| File | Purpose | Lines |
|------|---------|-------|
| `test_requirements.py` | Comprehensive test suite | 3,792 |
| `test_branch_size_calculator.py` | Branch size calculator tests | 312 |

**Total Tests**: 1079 tests (100% pass rate)

**Test Categories** (16+):
- Session management (77 tests)
- Configuration loading (cascade, inheritance)
- State storage (atomic writes, locking)
- Requirement strategies (Blocking, Dynamic, Guard)
- Hook integration (PreToolUse, PostToolUse, Stop, SessionStart)
- CLI commands (all 11 commands)
- Branch size calculator
- Message deduplication
- Auto-satisfaction
- Single-use requirements
- Error handling & fail-open
- Edge cases & race conditions

---

## Plugin Components

### Agents (19 total)

| Agent | Purpose |
|-------|---------|
| `adr-guardian.md` | ADR compliance validation |
| `backward-compatibility-checker.md` | Breaking change detection |
| `code-reviewer.md` | General code review |
| `code-simplifier.md` | Complexity reduction |
| `codex-arch-reviewer.md` | Codex architecture review |
| `codex-review-agent.md` | OpenAI Codex integration |
| `comment-analyzer.md` | Comment quality review |
| `comment-cleaner.md` | Remove stale/unnecessary comments |
| `commit-planner.md` | Plan commits before making them |
| `frontend-reviewer.md` | React/frontend best practices review |
| `import-organizer.md` | Organize and clean imports |
| `refactor-advisor.md` | Preparatory refactoring identification |
| `session-analyzer.md` | Session metrics analysis |
| `silent-failure-hunter.md` | Find silent failures |
| `solid-reviewer.md` | SOLID principles validation |
| `tdd-validator.md` | TDD strategy validation |
| `test-analyzer.md` | Test coverage analysis |
| `tool-validator.md` | Tool usage validation |
| `type-design-analyzer.md` | Type system analysis |

### Commands (11 total)

| Command | Purpose |
|---------|---------|
| `arch-review.md` | Team-based architecture review (recommended for planning) |
| `brainstorm.md` | Design-first development |
| `codex-review.md` | Codex-powered review |
| `commit-checks.md` | Pre-commit auto-fix (comments + imports) |
| `deep-review.md` | Cross-validated team review (recommended for PR) |
| `execute-plan.md` | Execute plan with checkpoints |
| `plan-review.md` | Lightweight plan review (alternative to /arch-review) |
| `pre-commit.md` | Quick pre-commit review |
| `quality-check.md` | Lightweight PR review (alternative to /deep-review) |
| `session-reflect.md` | Session learning and reflection |
| `write-plan.md` | Create implementation plan |

### Skills (19 total)

**Framework Skills (5):**

| Skill | Purpose |
|-------|---------|
| `requirements-framework-usage` | Usage help and configuration |
| `requirements-framework-status` | Status reporting |
| `requirements-framework-development` | Development workflow |
| `requirements-framework-builder` | Extension guidance |
| `session-learning` | Session learning workflow |

**Process Skills (14):**

| Skill | Purpose |
|-------|---------|
| `using-requirements-framework` | Bootstrap skill (session start injection) |
| `brainstorming` | Design-first exploration |
| `writing-plans` | Implementation plan creation |
| `executing-plans` | Plan execution with checkpoints |
| `test-driven-development` | RED-GREEN-REFACTOR enforcement |
| `systematic-debugging` | Root-cause investigation |
| `verification-before-completion` | Evidence-based completion |
| `subagent-driven-development` | Parallel task execution |
| `finishing-a-development-branch` | Branch completion options |
| `using-git-worktrees` | Isolated workspaces |
| `dispatching-parallel-agents` | Concurrent problem solving |
| `receiving-code-review` | Technical feedback evaluation |
| `requesting-code-review` | Review agent dispatch |
| `writing-skills` | TDD-for-documentation meta-skill |

---

## Summary

| Category | Count |
|----------|-------|
| Hooks | 15 |
| Core Libraries | 5 |
| Strategy Libraries | 6 |
| Utility Libraries | 11 |
| Session Learning Libraries | 2 |
| Message Libraries | 2 |
| Interactive Libraries | 3 |
| CLI Tool | 1 |
| Test Suite | 1079 tests |

| Plugin Components | Count |
|-------------------|-------|
| Agents | 19 |
| Commands | 11 |
| Skills | 19 |
