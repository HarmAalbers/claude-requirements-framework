---
description: "AI-powered code review using OpenAI Codex"
argument-hint: "[focus]"
allowed-tools: ["Task"]
---

# Codex Code Review

Runs OpenAI Codex AI code review on your changes.

**Usage:**
- `/requirements-framework:codex-review` - Review all changes
- `/requirements-framework:codex-review security` - Focus on security
- `/requirements-framework:codex-review performance` - Focus on performance

**Focus areas:** security, performance, bugs, style, all (default)

This launches an intelligent agent that:
1. Checks Codex CLI prerequisites
2. Generates appropriate diff
3. Runs Codex review
4. Parses and presents findings
5. Auto-satisfies codex_reviewer requirement

**Integration:** Complements `/pre-pr-review:quality-check`:
- quality-check: 8 rule-based agents (objective, systematic)
- codex-review: AI perspective (patterns, novel insights)
- Together: Comprehensive pre-PR coverage

## How It Works

When you run this skill, it launches the codex-review-agent which:

1. **Prerequisite Check**: Verifies Codex CLI is installed and authenticated
2. **Smart Diff Detection**: Auto-detects what to review (uncommitted changes, branch changes, etc.)
3. **Codex Execution**: Runs the appropriate `codex review` command with optional focus area
4. **Intelligent Parsing**: Processes Codex output and formats findings by severity
5. **Error Handling**: Provides helpful guidance for common issues (not installed, not logged in, no changes, API errors)

## Error Handling

This agent gracefully handles:
- Codex CLI not installed → Installation instructions
- Not authenticated → Login guidance
- No changes to review → Friendly message
- API errors → Retry suggestions
- Rate limits → Wait guidance

## Auto-Satisfaction

When this skill completes successfully, it automatically satisfies the `codex_reviewer` requirement, allowing you to proceed with creating your PR.

---

<task>
You are launching the codex-review-agent to perform an AI-powered code review using OpenAI's Codex CLI.

**Agent to launch**: codex-review-agent
**Focus area** (if provided in arguments): $ARGUMENTS
**Task**: Orchestrate a complete Codex code review workflow with intelligent error handling

Launch the agent using the Task tool with subagent_type="codex-review-agent" and provide it with the focus area if one was specified.

The agent will handle:
- Prerequisites verification
- Diff detection and generation
- Codex CLI execution
- Output parsing and presentation
- Comprehensive error handling

After completion, this skill will auto-satisfy the codex_reviewer requirement via the PostToolUse hook.
</task>
