---
name: requirements-framework-status
description: This skill should be used when the user asks to "requirements framework status", "show requirements project context", "what's the state of requirements framework", "requirements framework overview", or wants a comprehensive status report of the requirements framework implementation and current state.
git_hash: 000fe23
---

# Requirements Framework - Complete Status Report

Provides comprehensive project context and current state of the **Claude Code Requirements Framework**.

## Current Implementation Status

**Version**: 2.0.1
**Status**: ✅ Production Ready & Feature Complete
**Last Updated**: 2025-12-28
**Repository**: https://github.com/HarmAalbers/claude-requirements-framework

---

## Implementation Timeline

### Phase 1: MVP (Completed 2025-12-09)
**Goal**: Basic commit_plan requirement working
**Status**: ✅ Complete - All 11 steps (100%)

**Deliverables**:
- Core framework structure
- Session management
- Git utilities
- State storage (`.git/requirements/`)
- Configuration cascade (global → project → local)
- Requirements manager API
- PreToolUse hook
- CLI tool (`req` command)
- Basic test suite

### Phase 2: Additional Requirements
**Status**: ⏭️ Skipped - Not needed for current use cases

**Rationale**: Phase 1 + Phase 3 features cover all current requirements. GitHub ticket extraction and additional requirements can be added later if needed.

### Phase 3: Polish & UX (Completed 2025-12-24)
**Goal**: Production-ready with excellent UX
**Status**: ✅ Complete - All 6 steps (100%)

**Deliverables**:

1. **Session Registry & Auto-Detection** (77 tests)
   - Session registry infrastructure (`~/.claude/sessions.json`)
   - CLI auto-detects correct session
   - `req sessions` command
   - PID validation and stale cleanup

2. **Enhanced Error Messages** (4 sub-steps)
   - Session context in all error messages
   - Session bootstrap bug fix
   - Permission override bypass fix
   - Plan file whitelisting (chicken-and-egg fix)

3. **Terminal Colors**
   - Full color module with NO_COLOR support
   - Professional, readable output
   - TERM=dumb detection

4. **Per-Project Setup - `req init`** (42 tests)
   - Interactive wizard with 5 presets
   - Non-interactive mode
   - SessionStart hook suggestion
   - Auto-gitignore updates

5. **CLI Configuration Management - `req config`** (14 tests)
   - View/modify requirements without editing YAML
   - Interactive prompts
   - Preview before applying
   - Set arbitrary fields with JSON parsing

6. **Documentation Updates**
   - Updated README with all features
   - Created ADR-005
   - Comprehensive guides

---

## Deployment Architecture

### Deployed Components

**Location**: `~/.claude/hooks/` (active deployment)
**Repository**: `/Users/harm/Tools/claude-requirements-framework/`
**Sync Command**: `./sync.sh` (status, deploy, pull, diff)

### Hooks Deployed (9 total)

| Hook File | Type | Purpose | Lines |
|-----------|------|---------|-------|
| `check-requirements.py` | PreToolUse | Blocks Edit/Write if requirements unsatisfied | 374 |
| `handle-session-start.py` | SessionStart | Injects context, shows status | 183 |
| `handle-stop.py` | Stop | Verifies requirements before stopping | 155 |
| `handle-session-end.py` | SessionEnd | Cleanup stale sessions | 123 |
| `handle-plan-exit.py` | PostToolUse (ExitPlanMode) | Shows status after planning | 139 |
| `auto-satisfy-skills.py` | PostToolUse (Skill) | Auto-satisfy when skills complete | 137 |
| `clear-single-use.py` | PostToolUse (Bash) | Clear single_use after action | 136 |
| `ruff_check.py` | PreToolUse | Python linting | 182 |
| (1 additional hook) | - | - | - |

### Libraries (17 modules)

| Module | Purpose | Lines |
|--------|---------|-------|
| `requirements.py` | Core BranchRequirements API | 452 |
| `config.py` | Configuration cascade loader | 865 |
| `requirement_strategies.py` | Strategy pattern (Blocking/Dynamic/Guard) | 574 |
| `state_storage.py` | JSON state persistence | 272 |
| `session.py` | Session tracking & registry | 312 |
| `branch_size_calculator.py` | Dynamic branch size calculation | 352 |
| `calculation_cache.py` | Results caching (30-sec TTL) | 154 |
| `message_dedup_cache.py` | Message deduplication (5-min TTL) | 285 |
| `logger.py` | Structured JSON logging | 151 |
| `git_utils.py` | Git operations | 160 |
| `registry_client.py` | Session registry management | 200 |
| `init_presets.py` | Interactive init wizard presets | 463 |
| `interactive.py` | Interactive UI components | 219 |
| `feature_selector.py` | Feature selection UI | 148 |
| `calculator_interface.py` | Calculator abstraction | 73 |
| `colors.py` | Terminal colors (NO_COLOR support) | 157 |
| (1 additional module) | - | - |

**Total Lines**: ~12,360 lines of production code

### CLI Tool

**File**: `requirements-cli.py` (1,839 lines)

**Commands** (11 total):
- `req status` - Show requirement status
- `req satisfy` - Mark requirement satisfied
- `req clear` - Clear a requirement
- `req init` - Interactive project setup (Phase 3.4)
- `req config` - View/modify configuration (Phase 3.5)
- `req doctor` - Verify installation & sync (Phase 3)
- `req verify` - Quick installation check (Phase 3)
- `req sessions` - View active sessions
- `req list` - List all requirements
- `req prune` - Clean stale data
- `req enable` / `req disable` - Toggle requirements

---

## Test Coverage

**Test Suite**: `hooks/test_requirements.py` (3,792 lines)
**Total Tests**: **421 passing** (100% pass rate)
**Coverage**: Comprehensive TDD coverage

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

## Architecture & Design

### Requirement Strategies (3 types)

**1. Blocking Strategy**
- Manual satisfaction required
- Examples: `commit_plan`, `adr_reviewed`, `github_ticket`
- User runs: `req satisfy <name>`

**2. Dynamic Strategy**
- Auto-calculates conditions at runtime
- Example: `branch_size_limit`
- Uses: `branch_size_calculator.py`
- Caches results (30-second TTL)

**3. Guard Strategy**
- Conditions must pass (no manual satisfy)
- Example: `protected_branch`
- Prevents edits on main/master
- Emergency override: `req approve <name>`

### Configuration Cascade

```
1. Global (~/.claude/requirements.yaml)
        ↓ (merge if inherit=true)
2. Project (.claude/requirements.yaml) - Version controlled
        ↓ (always merge)
3. Local (.claude/requirements.local.yaml) - Gitignored
```

### Requirement Scopes

| Scope | Lifetime | Use Case |
|-------|----------|----------|
| `session` | Until Claude session ends | Daily planning, ADR review |
| `branch` | Persists across sessions | GitHub ticket, branch setup |
| `permanent` | Never auto-cleared | Project initialization |
| `single_use` | Cleared after each action | Pre-commit review (every commit) |

### Session Lifecycle (4 hooks)

```
1. SessionStart → Inject status, cleanup stale sessions
2. PreToolUse → Check requirements before Edit/Write
3. Stop → Verify session requirements before allowing stop
4. SessionEnd → Clean session state
```

Plus **3 PostToolUse hooks**:
- ExitPlanMode → Show status after planning
- Skill → Auto-satisfy when skills complete
- Bash → Clear single_use after action

---

## Advanced Features

### Auto-Satisfaction
- Skills automatically satisfy requirements when they complete
- Example: `/pre-pr-review:pre-commit` → satisfies `pre_commit_review`
- Configured via `auto_satisfy.on_skill_complete`

### Single-Use Requirements
- Must satisfy before EVERY action (not just once per session)
- Perfect for: Pre-commit review, pre-deploy checks
- Automatically cleared by PostToolUse hook

### Message Deduplication
- 5-minute TTL cache prevents spam
- 90% reduction in repeated prompts
- Handles parallel tool calls gracefully

### Stop Hook Verification
- Prevents Claude from stopping with unsatisfied requirements
- Ensures commit plan created before session ends
- Configurable scopes to check

### Protected Branch Guards
- Blocks direct edits on main/master
- Encourages feature branch workflow
- Emergency override available

### Branch Size Calculator
- Dynamic requirement based on diff size
- Suggests splitting large branches (>400 changes)
- 30-second result caching for performance

---

## Recent Features & Improvements

### December 2025 Updates

**UX Polish** (Commits: d1772da, 1ed3702):
- Enhanced `req status` with focused/verbose modes
- Improved `req doctor` output formatting
- Better error messages throughout
- Critical error handling fixes

**Configuration Extraction** (Commit: d429f34):
- Hard-coded config moved to `.md` files
- More maintainable and discoverable
- issue-manager agent enhanced

**Global Installation Pattern** (Commit: 98f0e5a):
- README updated for global installation
- Clearer deployment model
- Better onboarding documentation

---

## Architecture Decision Records

Located in `docs/adr/`:

- **ADR-001**: Remove main/master branch skip - Requirements enforced on all branches
- **ADR-002**: Use Claude Code's native session_id - Better session correlation
- **ADR-003**: Dynamic sync file discovery - `sync.sh` auto-discovers new files
- **ADR-004**: Guard requirement strategy - New requirement type for condition checks
- **ADR-005**: Per-project init command - Context-aware initialization design

---

## Key Metrics

| Metric | Value |
|--------|-------|
| **Total Lines of Code** | ~12,360 |
| **Test Suite** | 421 tests (100% pass) |
| **Hooks Deployed** | 9 |
| **Library Modules** | 17 |
| **CLI Commands** | 11 |
| **Requirement Types** | 3 strategies |
| **Built-in Requirements** | 7 pre-configured |
| **Phase Completion** | 2/3 (Phase 2 skipped) |
| **Overall Progress** | 100% (production ready) |

---

## Production Readiness Checklist

- ✅ **Comprehensive test coverage** - 421 tests, 100% pass rate
- ✅ **TDD methodology** - All features test-driven
- ✅ **Fail-open design** - Errors don't block Claude
- ✅ **Session management** - Robust tracking & cleanup
- ✅ **Interactive setup** - `req init` wizard with 5 presets
- ✅ **Configuration management** - `req config` for easy modifications
- ✅ **Diagnostics** - `req doctor` for troubleshooting
- ✅ **Documentation** - README, ADRs, skills, guides
- ✅ **Sync workflow** - `./sync.sh` for deployment
- ✅ **Git repository** - Version controlled, public
- ✅ **Installation script** - `./install.sh` for easy setup
- ✅ **Zero external dependencies** - Pure Python stdlib
- ✅ **Color support** - Professional terminal output
- ✅ **Message deduplication** - Spam prevention
- ✅ **Performance optimization** - Result caching

---

## How to Use This Information

### For New Users
- **Getting Started**: Run `req init` in your project
- **Learn Commands**: See requirements-framework-usage skill
- **Troubleshooting**: Run `req doctor`

### For Framework Developers
- **Extend Framework**: See requirements-framework-builder skill
- **Add Requirements**: Edit `.claude/requirements.yaml`
- **Run Tests**: `python3 ~/.claude/hooks/test_requirements.py`
- **Sync Changes**: `./sync.sh deploy`

### For Team Leads
- **Adoption**: Framework is production-ready
- **Team Onboarding**: Use `req init --preset strict`
- **Customization**: Per-project `.claude/requirements.yaml`
- **Monitoring**: `req doctor` verifies installation

---

## Resources

- **Repository**: https://github.com/HarmAalbers/claude-requirements-framework
- **README**: `/Users/harm/Tools/claude-requirements-framework/README.md`
- **Development Guide**: `DEVELOPMENT.md`
- **Framework Docs**: `docs/README-REQUIREMENTS-FRAMEWORK.md`
- **Sync Tool**: `./sync.sh` (status, deploy, pull, diff)
- **Tests**: `hooks/test_requirements.py`

---

## Summary

The Requirements Framework is a **production-ready, feature-complete system** with:
- 421 passing tests (comprehensive TDD coverage)
- 9 hooks covering the full session lifecycle
- 17 library modules implementing advanced features
- 11 CLI commands for complete control
- Interactive setup wizard with 5 presets
- Configuration management without editing YAML
- Comprehensive diagnostics and troubleshooting
- Professional documentation and ADRs

**Current Mode**: Maintenance & Extension - Framework is stable, new features can be added as needed.
