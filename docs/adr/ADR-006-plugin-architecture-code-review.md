# ADR-006: Plugin-Based Architecture for Code Review Workflows

## Status
Approved (2025-12-30)

## Context

The requirements framework initially started with hooks that enforce workflow requirements (commit planning, ADR review, test coverage). As the system evolved, we needed comprehensive code review capabilities to support the pre-commit and pre-PR requirements.

Two separate plugin structures emerged:
1. **requirements-framework** - Core hooks, configuration, CLI tool
2. **pre-pr-review** - 8 specialized review agents + 2 orchestrator commands

This created a dependency problem:
- requirements-framework referenced `/pre-pr-review:pre-commit` and `/pre-pr-review:quality-check` in global config
- pre-pr-review was not installed by `install.sh`
- Users installing requirements-framework got requirements that referenced missing skills
- pre-pr-review had no source repository (existed only as deployed directory)
- No version control for review agents
- Reinstallation didn't preserve review agents

## Decision

**Merge pre-pr-review plugin into requirements-framework as a unified plugin.**

The framework plugin structure now includes:
- `/hooks/` - Python hooks and libraries (copied to ~/.claude/hooks/)
- `/plugin/` - Plugin components (symlinked)
  - `/agents/` - 10 specialized agents
  - `/commands/` - 2 orchestrator commands
  - `/skills/` - 5 management skills
  - `/.claude-plugin/plugin.json` - Plugin manifest

## Allowed

**Single unified plugin pattern**:
- Core hooks deployed to ~/.claude/hooks/ (copied)
- Plugin components accessed via symlink to repo
- Commands use `/requirements-framework:` namespace
- Auto-satisfaction mapping in hooks/auto-satisfy-skills.py
- Single version number for entire system
- All components installed together via `./install.sh`

**Agent types integrated**:
- Workflow enforcement agents (adr-guardian, codex-review-agent)
- Code review agents (8 specialized reviewers)
- All agents accessed via plugin symlink

**Installation pattern**:
- Hooks copied (need to be in ~/.claude/hooks/)
- Plugin symlinked (live updates from repo)
- Both managed by single install script

## Prohibited

**Separate plugin dependencies**:
- Do NOT create separate plugins that depend on each other
- Do NOT reference skills from external plugins in requirements config
- Do NOT split related functionality across multiple plugins

**Copying plugin components**:
- Do NOT copy plugin files to ~/.claude/ (use symlink)
- Symlink enables live updates without reinstallation

**Mixed namespaces**:
- Do NOT mix `/pre-pr-review:` and `/requirements-framework:` namespaces
- Use single namespace for all framework commands/skills

## Consequences

### Positive
- ✅ Users get complete solution in one `./install.sh` command
- ✅ No missing dependency errors
- ✅ Single source of truth (one git repository)
- ✅ Version controlled together
- ✅ Simpler mental model (one framework, not two plugins)
- ✅ Easier to maintain (single codebase)
- ✅ Backed up during reinstallation
- ✅ Live updates via symlink

### Negative
- ⚠️ Tighter coupling between requirements and review agents
- ⚠️ Larger plugin surface area
- ⚠️ Framework scope expanded beyond just "requirements"

### Neutral
- Framework is now both requirements enforcement AND code review toolkit
- Plugin includes both workflow hooks and analysis agents
- Name "requirements-framework" slightly understates capabilities

## Alternatives Considered

### Alternative 1: Keep Separate Plugins
**Rejected because:**
- Dependency management complexity
- Installation friction (users must install both)
- Missing dependency errors
- No source repo for pre-pr-review
- Harder to version together

### Alternative 2: Merge Into Hooks Without Plugin
**Rejected because:**
- Agents less discoverable (not in plugin system)
- Harder to invoke (can't use /requirements-framework: namespace)
- Commands wouldn't be available as slash commands
- Skills wouldn't be available

### Alternative 3: Create Third "Uber-Plugin"
**Rejected because:**
- Unnecessary abstraction
- Three things to install instead of one
- Confusing mental model
- Dependency graph complexity

## Implementation

### Plugin Structure
```
plugin/
├── .claude-plugin/
│   └── plugin.json (v2.0.4 - updated from v2.0.3)
├── agents/ (10 total)
│   ├── adr-guardian.md
│   ├── codex-review-agent.md
│   ├── code-reviewer.md (NEW)
│   ├── silent-failure-hunter.md (NEW)
│   ├── test-analyzer.md (NEW)
│   ├── type-design-analyzer.md (NEW)
│   ├── comment-analyzer.md (NEW)
│   ├── code-simplifier.md (NEW)
│   ├── tool-validator.md (NEW)
│   └── backward-compatibility-checker.md (NEW)
├── commands/ (NEW directory)
│   ├── pre-commit.md (NEW)
│   └── quality-check.md (NEW)
└── skills/ (5 total)
    ├── codex-review/
    ├── requirements-framework-builder/
    ├── requirements-framework-development/
    ├── requirements-framework-status/
    └── requirements-framework-usage/
```

### Namespace Migration
- `/pre-pr-review:pre-commit` → `/requirements-framework:pre-commit`
- `/pre-pr-review:quality-check` → `/requirements-framework:quality-check`

### Auto-Satisfaction Mapping (hooks/auto-satisfy-skills.py)

**Default mappings** (backwards compatible):
```python
DEFAULT_SKILL_MAPPINGS = {
    'requirements-framework:pre-commit': 'pre_commit_review',
    'requirements-framework:quality-check': 'pre_pr_review',
    'requirements-framework:codex-review': 'codex_reviewer',
}
```

**Configurable mappings** (v2.1.0+):
Projects can define custom skill→requirement mappings using `satisfied_by_skill`:
```yaml
# In project's .claude/requirements.yaml
requirements:
  architecture_review:
    enabled: true
    type: blocking
    scope: single_use
    trigger_tools:
      - tool: Bash
        command_pattern: 'gh\s+pr\s+create'
    satisfied_by_skill: 'architecture-guardian'  # Custom project skill
```

When the specified skill completes, the requirement is automatically satisfied.
This enables project-specific workflows without modifying framework code.

### Global Config Updates (examples/global-requirements.yaml)
```yaml
pre_commit_review:
  message: Run `/requirements-framework:pre-commit` to review...

pre_pr_review:
  message: Run `/requirements-framework:quality-check` for comprehensive review...
```

## Enforcement

This architecture is enforced by:
1. **install.sh** - Installs framework hooks + symlinks plugin (single command)
2. **plugin.json** - Declares all 10 agents + 2 commands
3. **Auto-satisfy mapping** - Wires commands to requirements
4. **Global config** - References framework namespace only

New agents/commands must:
- Be added to `plugin/`
- Be registered in `plugin.json`
- Use `/requirements-framework:` namespace
- If auto-satisfying: Added to DEFAULT_SKILL_MAPPINGS or use `satisfied_by_skill` in config

## Related ADRs

- **ADR-007**: Deterministic Command Orchestrators - Documents how the merged commands achieve reliable execution
- **ADR-004**: Guard Requirement Strategy - Established extensible requirement types
- **ADR-005**: Per-Project Init Command - User onboarding for the unified framework

## References

- Commit: `57d0c1a` - feat: merge comprehensive pre-PR review toolkit into framework
- Analysis: 3 parallel Opus agents reviewed design, implementation, and usage
- Components merged: 8 agents, 2 commands (comprehensive improvements applied to all)
