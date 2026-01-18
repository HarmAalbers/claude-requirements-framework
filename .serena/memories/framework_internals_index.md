# Framework Internals Index

> Quick navigation to detailed knowledge about how the requirements framework works internally

## Core Mechanisms

### 🔄 **auto_satisfaction_workflow**
How skills automatically satisfy requirements when they complete
- PostToolUse hook (`auto-satisfy-skills.py`)
- Skill-to-requirement mappings (built-in + config-based)
- State persistence in `.git/requirements/[branch].json`
- Complete workflow example

### 🤖 **agent_architecture**  
How plugin agents are structured, configured, and invoked
- YAML frontmatter structure
- Agent patterns (review, tool-execution, auto-fix, blocking)
- Invocation methods (commands, skills, hooks)
- Version tracking with git_hash

### 🚫 **blocking_requirements_flow**
Complete lifecycle from trigger to satisfaction
- PreToolUse hook (`check-requirements.py`)
- Trigger matching (simple + regex patterns)
- Requirement scopes (session/single_use/branch/permanent)
- State storage and satisfaction methods
- Message deduplication

### 🪝 **hook_lifecycle**
The six hooks and when they fire
- SessionStart → PreToolUse → PostToolUse → Stop → SessionEnd
- Each hook's purpose and timing
- Complete workflow example
- Hook configuration

### 🎯 **strategy_pattern_architecture**
How the framework uses strategy pattern for extensible requirement types
- Central registry (blocking/dynamic/guard strategies)
- Base strategy interface
- Dispatch flow in check-requirements.py
- Adding new strategy types

## Quick Reference by Task

### "How do requirements get satisfied automatically?"
→ Read `auto_satisfaction_workflow`

### "How do I create a new agent?"
→ Read `agent_architecture`

### "How does commit blocking work?"
→ Read `blocking_requirements_flow`

### "When do hooks fire?"
→ Read `hook_lifecycle`

### "How do I add a new requirement type?"
→ Read `strategy_pattern_architecture`

## File Locations (Most Important)

**Hooks**:
- `hooks/check-requirements.py` - PreToolUse (blocking entry point)
- `hooks/auto-satisfy-skills.py` - PostToolUse (auto-satisfaction)
- `hooks/clear-single-use.py` - PostToolUse (scope clearing)
- `hooks/handle-session-start.py` - SessionStart (initialization)

**Core Library**:
- `hooks/lib/requirements.py` - BranchRequirements class
- `hooks/lib/config.py` - Configuration loading
- `hooks/lib/blocking_strategy.py` - Blocking requirement logic
- `hooks/lib/strategy_registry.py` - Strategy dispatch

**Plugin**:
- `plugin/agents/*.md` - Agent definitions
- `plugin/commands/*.md` - Command orchestration
- `plugin/.claude-plugin/plugin.json` - Registration

**Config**:
- `.claude/requirements.yaml` - Project config
- `~/.claude/requirements.yaml` - Global defaults

## State Files

- `.git/requirements/[branch].json` - Per-branch requirement state
- `.claude/session_registry.json` - Active sessions

## Key Patterns

1. **Fail-Open**: Hooks never block on internal errors
2. **Cascade**: Config loads global → project → local
3. **Strategy**: Pluggable requirement types via strategy pattern
4. **Auto-Satisfy**: Skills auto-satisfy via PostToolUse hook
5. **Single-Use**: Scope clears after trigger completes
