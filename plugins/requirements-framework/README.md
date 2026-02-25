# Requirements Framework Plugin

Comprehensive workflow enforcement and code review automation for Claude Code.

## Overview

This plugin provides workflow enforcement, code review agents, and management tools that integrate seamlessly with the Requirements Framework hooks.

**Key Features**:
- ✨ **16 specialized review agents** - From tool validation to backward compatibility checking
- 🎯 **8 orchestrator commands** - From pre-commit to architecture review workflows
- 📋 **5 management skills** - Status reporting, usage help, and framework development
- 🔗 **Hook integration** - Auto-satisfies requirements when commands complete
- 🧪 **TDD-first** - 447 passing tests ensure reliability

## Features

### 🔒 Workflow Enforcement

**ADR Guardian** (`adr-guardian`)
- Validates plans and code against Architecture Decision Records
- **BLOCKING authority** - prevents architectural drift
- Ensures consistency with documented decisions
- Triggers: Before implementation, during code review

**Codex Review Agent** (`codex-review-agent`)
- Orchestrates OpenAI Codex CLI for AI-powered review
- Requires: `npm install -g @openai/codex`
- Provides: Advanced static analysis and pattern detection
- Triggers: On-demand via skill or requirement

### 🛠️ Pre-Commit Review Suite

8 specialized agents available via `/requirements-framework:pre-commit`:

**1. Tool Validator** (`tool-validator`)
- Runs pyright, ruff, eslint to catch CI errors locally
- **Fast**: Uses Haiku model for quick feedback
- **Blocking gate**: Must pass before AI review
- Detects: Type errors, linting issues, syntax problems

**2. Code Reviewer** (`code-reviewer`)
- Checks CLAUDE.md compliance, detects bugs, assesses code quality
- **Thorough**: Uses Opus model with 80% confidence threshold
- **Focused**: Reports only high-confidence issues
- Detects: Logic errors, security issues, best practice violations

**3. Silent Failure Hunter** (`silent-failure-hunter`)
- Audits error handling with zero tolerance for silent failures
- **Critical**: Uses Sonnet model for balanced analysis
- **Strict**: Flags swallowed exceptions, missing error logs
- Detects: Try-catch without logging, ignored errors, fallback abuse

**4. Test Analyzer** (`test-analyzer`)
- Reviews test coverage quality and completeness
- **Smart**: Marks untested code as CRITICAL gaps
- **Practical**: Focuses on meaningful coverage, not just metrics
- Detects: Missing edge cases, inadequate assertions, brittle tests

**5. Type Design Analyzer** (`type-design-analyzer`)
- Analyzes type invariants and encapsulation
- **Rigorous**: 4-dimensional rating (encapsulation, invariants, usefulness, enforcement)
- **Insightful**: Suggests type system improvements
- Detects: Weak invariants, primitive obsession, anemic types

**6. Comment Analyzer** (`comment-analyzer`)
- Checks documentation accuracy and detects comment rot
- **Maintenance-focused**: Prevents technical debt from stale docs
- **Precise**: Validates comments match actual code behavior
- Detects: Outdated comments, missing docs, misleading descriptions

**7. Code Simplifier** (`code-simplifier`)
- Final polish for clarity and maintainability
- **Conservative**: Preserves all functionality while improving readability
- **Best practices**: Follows project conventions from CLAUDE.md
- Improves: Complex logic, naming, structure

**8. Backward Compatibility Checker** (`backward-compatibility-checker`)
- Detects schema migrations and verifies Alembic migrations exist
- **Database-aware**: Prevents breaking changes without migrations
- **Safe**: Ensures reversible database changes
- Detects: Missing migrations, breaking schema changes

### ⚡ Commands

#### /requirements-framework:pre-commit [aspects]

Fast pre-commit review with smart agent selection.

**Default** (no arguments): Essential checks
- `tool-validator` - Catch CI errors early
- `code-reviewer` - Bug and quality check
- `silent-failure-hunter` - Error handling audit

**Arguments:**
- `tools` - Just tool validation (pyright/ruff/eslint)
- `code` - Code review only
- `errors` - Silent failure hunter only
- `compat` - Backward compatibility check
- `tests` - Test coverage analysis
- `types` - Type design analysis
- `comments` - Documentation accuracy
- `simplify` - Code simplification
- `all` - All 8 agents
- `parallel` - Run agents in parallel (faster)

**Examples:**
```bash
/requirements-framework:pre-commit              # Fast essential checks
/requirements-framework:pre-commit tools        # Just CI tools
/requirements-framework:pre-commit all parallel # Comprehensive + fast
/requirements-framework:pre-commit tests types  # Specific aspects
```

**Integration:** Auto-satisfies `pre_commit_review` requirement when complete

**Workflow:**
```
Tool Validator (blocking gate)
      ↓ (if passes)
Selected AI Agents (parallel or sequential)
      ↓
Review Complete → auto-satisfy-skills.py → pre_commit_review satisfied
```

#### /requirements-framework:quality-check [parallel]

Comprehensive pre-PR review with all 8 agents.

**Features:**
- **Smart selection**: Conditionally runs agents based on file types
- **Deterministic execution**: 10-step workflow with enforced order
- **Blocking gate**: Tool-validator must pass before AI review
- **File type detection**: Runs test-analyzer only if tests exist, etc.

**Arguments:**
- `parallel` - Run agents in parallel for speed

**Examples:**
```bash
/requirements-framework:quality-check           # Sequential (thorough)
/requirements-framework:quality-check parallel  # Parallel (faster)
```

**Integration:** Auto-satisfies `pre_pr_review` requirement when complete

**Workflow:**
```
1. Tool Validator (BLOCKING)
2. File Type Detection
3. Code Reviewer
4. Silent Failure Hunter
5. Test Analyzer (if tests exist)
6. Type Design Analyzer (if types exist)
7. Comment Analyzer (if comments exist)
8. Backward Compatibility Checker (if schema changes)
9. Code Simplifier (final polish)
10. Review Complete → auto-satisfy → pre_pr_review satisfied
```

#### /requirements-framework:codex-review [focus]

AI-powered code review using OpenAI Codex CLI.

**Features:**
- **Autonomous agent**: Handles prerequisites, scope detection, error recovery
- **Focus areas**: `security`, `performance`, `bugs`, `style`, `all` (default)
- **Smart scope detection**: Automatically reviews uncommitted changes or branch diff
- **Comprehensive error handling**: Guides through installation, authentication, API issues

**Arguments:**
- `security` - Focus on security vulnerabilities
- `performance` - Focus on performance optimization
- `bugs` - Focus on potential bugs and logic errors
- `style` - Focus on code style and best practices
- `all` - All focus areas (default)

**Examples:**
```bash
/requirements-framework:codex-review            # All focus areas
/requirements-framework:codex-review security   # Security-focused
/requirements-framework:codex-review performance # Performance-focused
```

**Integration:** Auto-satisfies `codex_reviewer` requirement when complete

**Requirements:** OpenAI Codex CLI (`npm install -g @openai/codex` + `codex login`)

**Workflow:**
```
1. Parse focus area argument
2. Launch codex-review-agent (autonomous)
   - Check prerequisites (codex installed/authenticated)
   - Detect scope (uncommitted vs branch changes)
   - Execute codex review with focus
   - Parse and present results by severity
3. Auto-satisfy requirement (if successful)
```

### 📚 Skills

Skills trigger automatically from natural language:

**requirements-framework-status**
- **Triggers**: "Show requirements framework status", "requirements project context"
- **Provides**: Comprehensive status report with requirement states, session info, project context
- **Use when**: Checking framework state, debugging requirements

**requirements-framework-usage**
- **Triggers**: "How to use requirements framework", "requirements help", "troubleshoot requirements"
- **Provides**: Usage guidance, configuration help, troubleshooting steps
- **Use when**: Learning framework, solving issues, configuring requirements

**requirements-framework-builder**
- **Triggers**: "Extend requirements framework", "add new requirement type", "requirements status"
- **Provides**: Framework extension guidance, custom requirement creation, status checking
- **Use when**: Adding custom requirements, extending framework capabilities

**requirements-framework-development**
- **Triggers**: "Fix requirements framework bug", "sync requirements framework", "requirements development workflow"
- **Provides**: Development workflow, sync.sh usage, TDD guidance, contributing help
- **Use when**: Developing the framework itself, fixing bugs, syncing changes

## Usage

### Triggering Commands

Commands use slash command syntax:

```
Type: /requirements-framework:

Autocompletes to:
  • /requirements-framework:pre-commit [aspects]
  • /requirements-framework:quality-check [parallel]
```

**Example sessions:**

```
You: /requirements-framework:pre-commit

Claude: Running essential pre-commit checks...
  ✓ Tool Validator - No CI errors
  ✓ Code Reviewer - 3 suggestions (2 HIGH, 1 MEDIUM)
  ✓ Silent Failure Hunter - 1 CRITICAL issue found

Review complete. Address 1 CRITICAL issue before committing.
```

```
You: /requirements-framework:quality-check parallel

Claude: Running comprehensive quality check...
  ✓ Tool Validator - Passed
  ✓ Code Reviewer - 5 suggestions
  ✓ Silent Failure Hunter - Clean
  ✓ Test Analyzer - Coverage gap in UserService
  ✓ Type Design Analyzer - 2 type improvements
  ✓ Comment Analyzer - 1 stale comment
  ✓ Code Simplifier - 3 clarity improvements

Quality check complete. pre_pr_review requirement satisfied.
```

### Triggering Skills

Skills use natural language:

```
You: "Show requirements framework status"

Claude: [Triggers requirements-framework-status skill]
📋 Requirements Framework Status
...detailed status report...
```

```
You: "How do I configure the pre_commit_review requirement?"

Claude: [Triggers requirements-framework-usage skill]
Here's how to configure pre_commit_review...
```

### Triggering Agents

Agents are invoked via commands (not directly):

```
Want tool validation? → /requirements-framework:pre-commit tools
Want test review? → /requirements-framework:pre-commit tests
Want everything? → /requirements-framework:quality-check
```

## Testing During Development

To test plugin components without persistent installation, use Claude Code's official `--plugin-dir` flag:

```bash
# Launch Claude Code with plugin loaded
claude --plugin-dir ~/.claude/plugins/requirements-framework
```

**Benefits:**
- ✅ Zero risk - no system modifications
- ✅ Live reload - changes immediately available
- ✅ Instant verification of component structure
- ✅ Official, documented approach

**Test Checklist:**

1. **Commands** - Type `/requirements-framework:` and verify autocomplete shows 6 commands
2. **Command execution** - Run `/requirements-framework:pre-commit tools` and verify it works
3. **Skills** - Say "Show requirements framework status" and verify skill triggers
4. **Agents** - Check that agents are available via Task tool

**Troubleshooting:**
- If commands don't autocomplete → Check plugin.json manifest structure
- If skills don't trigger → Verify skill description patterns match exact phrases
- If agents unavailable → Check agent markdown files exist in agents/ directory

**For persistent installation**, see [Installation](#installation) section below.

## Installation

### Recommended Installation (Marketplace)

The plugin is installed via Claude Code's marketplace system:

```bash
# 1. Run install.sh to set up hooks and local marketplace
cd ~/Tools/claude-requirements-framework
./install.sh

# 2. In Claude Code session, add the local marketplace
/plugin marketplace add ~/Tools/claude-requirements-framework

# 3. Install the plugin
/plugin install requirements-framework@requirements-framework
```

**What happens:**
1. Hooks copied to `~/.claude/hooks/`
2. Plugin installed to cache: `~/.claude/plugins/cache/requirements-framework/`
3. Verification checks run
4. Component count displayed

**Verify installation:**
```bash
# Check installed version
/plugin list
# Should show: requirements-framework@2.1.0

# Test commands
/requirements-framework:pre-commit tools

# Test skills
"Show requirements framework status"
```

**To update the plugin:**
```bash
/plugin uninstall requirements-framework@requirements-framework
/plugin marketplace update requirements-framework
/plugin install requirements-framework@requirements-framework
```

For detailed installation, troubleshooting, and verification steps:
- **[Plugin Installation Guide](../../docs/PLUGIN-INSTALLATION.md)** - Comprehensive reference

### Alternative: CLI Flag (For Development)

Use the `--plugin-dir` flag for live development without persistent installation:

```bash
# Launch Claude Code with plugin loaded temporarily
claude --plugin-dir ~/Tools/claude-requirements-framework/plugin
```

**Benefits:**
- Changes to plugin files are immediately available (live reload)
- No need to reinstall after each change
- Ideal for developing and testing plugin components

## Configuration

Respects the same 3-level cascade as hooks:

1. **`~/.claude/requirements.yaml`** (Global defaults)
2. **`.claude/requirements.yaml`** (Project config)
3. **`.claude/requirements.local.yaml`** (Local overrides)

See [Configuration System](../../README.md#configuration-system) for details.

### Enabling Plugin-Related Requirements

**Example ~/.claude/requirements.yaml:**
```yaml
requirements:
  pre_commit_review:
    scope: single_use
    message: "Run /requirements-framework:pre-commit before committing"
    trigger_tools:
      - tool: Write
      - tool: Edit

  pre_pr_review:
    scope: single_use
    message: "Run /requirements-framework:quality-check before creating PR"
    trigger_tools:
      - tool: Bash
        command_pattern: 'gh\s+pr\s+create'
```

**How it works:**
1. Requirement blocks Edit/Write (or specified triggers)
2. User runs plugin command
3. Command completes → PostToolUse hook (`auto-satisfy-skills.py`)
4. Hook auto-satisfies requirement
5. Edits unblocked

## Integration with Hooks

The plugin integrates via `auto-satisfy-skills.py` (PostToolUse hook):

### Auto-Satisfaction Mapping

| Command | Satisfies | Scope |
|---------|-----------|-------|
| `/requirements-framework:pre-commit` | `pre_commit_review` | `single_use` |
| `/requirements-framework:quality-check` | `pre_pr_review` | `single_use` |
| `/requirements-framework:codex-review` | `codex_reviewer` | `single_use` |

**Mechanism:**
```python
# In ~/.claude/hooks/auto-satisfy-skills.py
DEFAULT_SKILL_MAPPINGS = {
    'requirements-framework:pre-commit': 'pre_commit_review',
    'requirements-framework:quality-check': 'pre_pr_review',
    'requirements-framework:codex-review': 'codex_reviewer',
}
```

### Workflow Diagram

```
┌──────────────────────────────────────┐
│  Edit/Write blocked by requirement  │
└──────────────────────────────────────┘
              │
              ▼
┌──────────────────────────────────────┐
│  Run plugin command                  │
│  /requirements-framework:pre-commit  │
└──────────────────────────────────────┘
              │
              ▼
┌──────────────────────────────────────┐
│  Command completes                   │
│  → PostToolUse hook triggers         │
└──────────────────────────────────────┘
              │
              ▼
┌──────────────────────────────────────┐
│  auto-satisfy-skills.py              │
│  • Detects command finished          │
│  • Looks up mapping                  │
│  • Satisfies requirement             │
└──────────────────────────────────────┘
              │
              ▼
┌──────────────────────────────────────┐
│  Edit/Write unblocked                │
└──────────────────────────────────────┘
```

See [Plugin vs. Hooks](../../docs/PLUGIN-INSTALLATION.md#plugin-vs-hooks) for architecture details.

## Technical Details

### Plugin Structure

```
~/.claude/plugins/cache/requirements-framework/requirements-framework/2.0.5/
├── .claude-plugin/
│   └── plugin.json (v2.1.0)
├── agents/ (16 agents)
│   ├── adr-guardian.md
│   ├── backward-compatibility-checker.md
│   ├── code-reviewer.md
│   ├── code-simplifier.md
│   ├── codex-review-agent.md
│   ├── comment-analyzer.md
│   ├── comment-cleaner.md
│   ├── commit-planner.md
│   ├── import-organizer.md
│   ├── session-analyzer.md
│   ├── silent-failure-hunter.md
│   ├── tdd-validator.md
│   ├── test-analyzer.md
│   ├── tool-validator.md
│   └── type-design-analyzer.md
├── commands/ (8 commands)
│   ├── codex-review.md
│   ├── commit-checks.md
│   ├── plan-review.md
│   ├── pre-commit.md
│   ├── quality-check.md
│   └── session-reflect.md
└── skills/ (5 skills)
    ├── requirements-framework-builder/
    ├── requirements-framework-development/
    ├── requirements-framework-status/
    └── requirements-framework-usage/
```

### Component Versioning

All plugin components (agents, commands, skills) include a `git_hash` field in their YAML frontmatter that tracks the last commit that modified each file. This enables:

- **Version tracking**: Know exactly which version of each component was used
- **A/B testing**: Compare effectiveness of different agent versions
- **Debugging**: Correlate behavior with specific code versions
- **Audit trail**: Understand when components were last modified

**Example frontmatter with git_hash:**
```yaml
---
name: code-reviewer
description: Use this agent to review code...
model: opus
color: green
allowed-tools: ["Bash", "Glob", "Grep", "Read"]
git_hash: 57d0c1a
---
```

**Updating versions** (run after modifying components):
```bash
./update-plugin-versions.sh           # Update all git_hash fields
./update-plugin-versions.sh --check   # Preview changes
./update-plugin-versions.sh --verify  # Verify hashes are current
```

See [CLAUDE.md](../../CLAUDE.md#plugin-component-versioning) for complete workflow details.

### Agent Execution Models

| Agent | Model | Rationale | Confidence Filter |
|-------|-------|-----------|-------------------|
| tool-validator | Haiku | Fast tool execution | N/A (tool output) |
| code-reviewer | Opus | Deep analysis needed | ≥80% |
| silent-failure-hunter | Sonnet | Balanced analysis | None (zero tolerance) |
| test-analyzer | Sonnet | Code understanding | CRITICAL for gaps |
| type-design-analyzer | Sonnet | Type system analysis | Rating-based |
| comment-analyzer | Sonnet | Doc accuracy | None (all issues) |
| code-simplifier | Sonnet | Code transformation | None (safe changes) |
| backward-compat | Sonnet | Schema analysis | None (breaking changes) |
| adr-guardian | Opus | Architectural decisions | BLOCKING |
| codex-review | External | Codex CLI | N/A (external tool) |

### Command Workflows

**pre-commit workflow:**
1. Parse arguments (`tools`, `code`, etc.)
2. Run tool-validator (blocking gate)
3. If tool-validator fails → Stop, report errors
4. Run selected agents (parallel if `parallel` flag)
5. Collect results
6. Report summary
7. PostToolUse hook auto-satisfies requirement

**quality-check workflow:**
1. Parse arguments (`parallel` flag)
2. Run tool-validator (blocking gate)
3. Detect file types (tests, types, comments, schemas)
4. Run agents in deterministic order (or parallel)
5. Conditional execution based on file types
6. Collect results
7. Report comprehensive summary
8. PostToolUse hook auto-satisfies requirement

## Common Patterns

### Fast Iteration

```bash
# Make changes
vim src/user-service.ts

# Quick check before commit
/requirements-framework:pre-commit

# Fix issues
vim src/user-service.ts

# Commit
git commit -m "feat: add user validation"
```

### Thorough Review

```bash
# Complete feature
git add .

# Comprehensive review
/requirements-framework:quality-check parallel

# Address all feedback
# (iterate until clean)

# Create PR
gh pr create
```

### Targeted Review

```bash
# Just added tests
/requirements-framework:pre-commit tests

# Just error handling changes
/requirements-framework:pre-commit errors

# Just type changes
/requirements-framework:pre-commit types
```

### Requirement-Driven Workflow

```bash
# Try to edit file
vim src/critical.ts

# Blocked: "pre_commit_review not satisfied"

# Satisfy requirement
/requirements-framework:pre-commit

# Now unblocked
vim src/critical.ts  # Works!
```

## Limitations

- **Codex Review**: Requires separate `@openai/codex` CLI installation and API key
- **Agent Autonomy**: Agents suggest improvements but don't auto-fix (intentional)
- **File Type Detection**: quality-check detection is heuristic-based (checks file extensions)
- **Parallel Execution**: Some agents may have overlapping findings when run in parallel
- **Language Support**: Tool-validator supports Python (ruff/pyright) and JS/TS (eslint)

## Future Enhancements

Potential additions:
- Auto-fix mode for simple issues (opt-in)
- Custom agent configuration per project
- Integration with additional linters (Go, Rust, Java)
- Progressive results streaming for long reviews
- Review result caching for unchanged files
- Custom requirement → command mappings via config

## Support

For issues, questions, or enhancements:

**GitHub**:
- Issues: https://github.com/HarmAalbers/claude-requirements-framework/issues
- Discussions: https://github.com/HarmAalbers/claude-requirements-framework/discussions

**Self-Service**:
1. Check [Plugin Installation Guide](../../docs/PLUGIN-INSTALLATION.md#troubleshooting)
2. Run `req doctor`
3. Review [Main README](../../README.md)
4. Use "How to use requirements framework" skill

## Related Documentation

**Main Docs**:
- [Main README](../../README.md) - Framework overview
- [Plugin Components](../../README.md#plugin-components) - Component descriptions
- [Plugin Installation](../../docs/PLUGIN-INSTALLATION.md) - Installation & troubleshooting

**Architecture**:
- [ADR-006](../../docs/adr/ADR-006-plugin-architecture-code-review.md) - Plugin architecture decisions
- [ADR-007](../../docs/adr/ADR-007-deterministic-command-orchestrators.md) - Command execution design

**Development**:
- [CLAUDE.md](../../CLAUDE.md) - Development workflow & TDD
- [Contributing](../../README.md#development) - How to contribute

## Version History

- **v2.1.0** (2025-01-19)
  - Current stable release
  - 16 agents, 8 commands, 5 skills
  - **Plugin installation via marketplace** (replaces symlink method)
  - Added `sync-versions.sh` for version consistency
  - Fixed relative path issues in plugin.json
  - Auto-satisfy mechanism via PostToolUse hook
  - Comprehensive code review suite
  - Integration with requirements framework hooks

- **v2.0.4** (2024-12-30)
  - 17 agents, 3 commands, 4 skills (pre-refactor counts)
  - Plugin installation via install.sh symlink (deprecated)
